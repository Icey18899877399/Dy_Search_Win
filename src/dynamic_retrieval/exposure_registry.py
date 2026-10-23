"""Conservative event exposure audit; never authorizes evaluation or reads labels."""
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from .data.store import utc_iso

KNOWN = {'task.json', 'result.json', 'cohort.json', 'plan.json', 'bundle-plan.json',
         'effective-tasks.json', 'pre-model-plan.json'}
VARIANTS = {'basic.json', 'enhanced.json', 'fixed.json', 'v5_legacy.json',
            'v5_conservative_facts.json', 'v6_admission.json', 'v6_conservative_facts.json'}
COLLECTIONS = ('selected', 'exclusions', 'skipped', 'tasks', 'events', 'unsupported_tasks')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_registry(project_root, index_path=None):
    """Extract only declared identity fields from recognized historical schemas.

    Results lacking manifests and failed/prepared/rejected candidates still count.
    Unknown arbitrary JSON is not interpreted as a task. Experiment manifests extend
    recognized variant filenames through their runs/baseline/ablations paths.
    """
    root = Path(project_root).resolve()
    events = defaultdict(set); files = {}; errors = []; pending = []
    candidates = set(); expectations = defaultdict(list)

    def relative(p):
        return p.relative_to(root).as_posix()

    def error(p, reason):
        errors.append({'path': relative(p), 'reason': reason})

    def read(p):
        try:
            raw = p.read_bytes()
            files[relative(p)] = hashlib.sha256(raw).hexdigest()
        except OSError:
            error(p, 'unreadable_file'); return None
        try:
            value = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(value, (dict, list)):
                error(p, 'invalid_top_level_schema'); return None
            return value
        except (UnicodeError, ValueError):
            error(p, 'invalid_json'); return None

    artifacts = root / 'artifacts'
    if not artifacts.is_dir():
        error(artifacts, 'missing_history_directory')
    inventory = sorted(artifacts.rglob('*.json'))
    for p in inventory:
        if p.name in KNOWN or (p.name in VARIANTS and any(x in p.parts for x in ('runs', 'baseline', 'runtime-demo', 'ablations'))):
            candidates.add(p)
        if p.name not in ('manifest.json', 'experiment-manifest.json'):
            continue
        manifest = read(p)
        if manifest is None:
            continue
        if not isinstance(manifest, dict) or not isinstance(manifest.get('files', {}), dict):
            error(p, 'invalid_manifest_schema'); continue
        for rel, expected in manifest.get('files', {}).items():
            q = (p.parent / str(rel).replace('\\', '/')).resolve()
            if not q.is_relative_to(root) or not q.is_relative_to(p.parent):
                error(p, 'unsafe_manifest_path'); continue
            parts = Path(str(rel).replace('\\', '/')).parts
            variant = p.name == 'experiment-manifest.json' and q.suffix == '.json' and any(v in parts for v in ('runs', 'baseline', 'runtime-demo', 'ablations', 'sensitivity')) and q.name not in {'on-demand-cache.json', 'calibration-status.json'}
            if q.name in KNOWN or q.name in VARIANTS or variant:
                candidates.add(q)
                expectations[q].append((p, expected))
    docs = root / 'docs'
    candidates.update(docs.glob('*diagnostic.json'))

    def record(row, p, reason, required=False):
        if not isinstance(row, dict):
            error(p, 'invalid_identity_schema'); return
        identity = row.get('task', row)
        if not isinstance(identity, dict):
            error(p, 'invalid_task_schema'); return
        eid = identity.get('event_id')
        if isinstance(eid, (str, int)) and not isinstance(eid, bool) and str(eid).strip():
            events[str(eid)].add((relative(p), reason))
        elif identity.get('market_id') is not None:
            pending.append((str(identity['market_id']), p, reason))
        elif required:
            error(p, 'missing_event_identity')

    for p in sorted(candidates):
        d = read(p)
        if d is None:
            continue
        for manifest_path, expected in expectations[p]:
            if files[relative(p)] != expected:
                error(p, 'manifest_hash_mismatch')
        is_diagnostic = p.parent == docs and p.name.endswith('diagnostic.json')
        if p.name == 'effective-tasks.json' or (isinstance(d, list) and (p.name == 'cohort.json' or is_diagnostic)):
            if not isinstance(d, list):
                error(p, 'invalid_task_list_schema')
            else:
                for row in d:
                    record(row, p, 'effective_task', True)
            continue
        if not isinstance(d, dict):
            error(p, 'invalid_object_schema'); continue
        if p.name == 'cohort.json' and not any(k in d for k in ('selected', 'exclusions', 'tasks')):
            error(p, 'unknown_cohort_schema')
        if p.name == 'task.json':
            record(d, p, 'task_input', True)
        if 'task' in d:
            record(d, p, 'result_or_variant_task', True)
        elif p.name == 'result.json':
            error(p, 'missing_result_task')
        for field in COLLECTIONS + (('rows', 'event_results') if is_diagnostic else ()):
            if field not in d:
                continue
            rows = d[field]
            # Diagnostic summaries may use scalar counts; only these two fields
            # have a defined list-of-identities contract in preparation files.
            if not isinstance(rows, list):
                if is_diagnostic and field == 'tasks' and type(rows) is int:
                    continue
                if field in ('selected', 'exclusions', 'skipped', 'tasks', 'rows', 'event_results'):
                    error(p, 'invalid_' + field + '_schema')
                continue
            for row in rows:
                reason = field
                if isinstance(row, dict) and isinstance(row.get('reason'), str):
                    reason += ':' + row['reason']
                record(row, p, reason, field in ('selected', 'exclusions', 'skipped'))
        if 'excluded_events' in d:
            if not isinstance(d['excluded_events'], list):
                error(p, 'invalid_excluded_events_schema')
            else:
                for eid in d['excluded_events']:
                    record({'event_id': eid}, p, 'prior_excluded_event', True)

    if pending:
        mapping = defaultdict(set)
        if index_path is not None:
            with closing(sqlite3.connect(Path(index_path).resolve().as_uri() + '?mode=ro', uri=True)) as c:
                for mid, eid in c.execute('SELECT DISTINCT market_id,event_id FROM tasks'):
                    mapping[str(mid)].add(str(eid))
        for mid, p, reason in pending:
            if not mapping[mid]:
                error(p, 'unresolved_market_identity')
            for eid in mapping[mid]:
                events[eid].add((relative(p), reason + ':indexed_market_identity'))
    entries = [{'event_id': eid, 'sources': [{'path': p, 'sha256': files[p], 'reason': why}
                for p, why in sorted(refs)]} for eid, refs in sorted(events.items())]
    errors = sorted({(e['path'], e['reason']) for e in errors})
    return {'format': 'conservative_event_exposure_v1', 'audit_complete': not errors,
            'excluded_events': sorted(events), 'entries': entries,
            'source_sha256': dict(sorted(files.items())),
            'errors': [{'path': p, 'reason': why} for p, why in errors],
            'policy': 'Exclude all prepared, inspected, rejected, skipped, failed and executed events; no success requirement.',
            'limitations': ['Only explicit historical schemas are recognized; unrecorded human exposure cannot be reconstructed.',
                           'Event isolation is sufficient for zero candidates, not proof of URL/body or factual independence for future cohorts.',
                           'No document bodies, model probabilities or outcome labels are exported.']}


def audit_index(index_path, registry, cutoffs):
    """Read task identity/time metadata only. Positive counts are not eligibility."""
    excluded = set(registry['excluded_events'])
    with closing(sqlite3.connect(Path(index_path).resolve().as_uri() + '?mode=ro', uri=True)) as c:
        rows = c.execute('SELECT event_id,MIN(observed_at),MAX(observed_at),COUNT(*) FROM tasks GROUP BY event_id').fetchall()
    first = {str(e): utc_iso(lo) for e, lo, hi, n in rows}
    indexed = set(first); unexposed = indexed - excluded
    status = ('audit_incomplete' if not registry['audit_complete'] else
              'unexposed_metadata_requires_freeze' if unexposed else 'no_unexposed_events')
    cutoff_rows = []
    for raw in cutoffs:
        cutoff = utc_iso(raw); visible = {eid for eid, observed in first.items() if observed <= cutoff}
        cutoff_rows.append({'cutoff': cutoff, 'indexed_event_count': len(visible),
                            'excluded_event_count': len(visible & excluded),
                            'unexposed_event_count': len(visible - excluded)})
    return {'format': 'phase14_holdout_readiness_v1', 'status': status,
            'audit_complete': registry['audit_complete'], 'ready_for_model': False,
            'excluded_event_count': len(excluded), 'indexed_event_count': len(indexed),
            'excluded_indexed_event_count': len(indexed & excluded),
            'excluded_nonindex_events': sorted(excluded - indexed),
            'unexposed_event_count': len(unexposed), 'task_rows': sum(r[3] for r in rows),
            'latest_observed_at': max((utc_iso(r[2]) for r in rows), default=None),
            'cutoffs': cutoff_rows, 'model_requests': 0, 'labels_read': False,
            'new_candidate_bodies_read': False,
            'freeze_protocol': [
                'Require new, never-exposed event metadata; stop if event pool is exhausted.',
                'Freeze candidate cutoff sequence, seed, target and minimum counts, inspection bounds and rejection rules before reading candidate bodies.',
                'Freeze code, full-band comparator, model settings, real-call accounting, retry and failure policies before model calls.',
                'Register every attempted or rejected event; record source hashes and both publication/observation cutoff checks.',
                'Check event, canonical-URL and raw/normalized-body overlap before freezing future inputs; current event-only audit does not implement body deduplication.',
                'Freeze predictions before loading terminal outcome labels; retain failed, abstained and unscoreable cases in denominators.',
                'Treat the existing 18 events as development/calibration only; retrospective model-knowledge contamination remains possible.']}

