"""Generate or verify Phase14 event-only holdout readiness without model/label access."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dynamic_retrieval.exposure_registry import audit_index, build_registry, digest

CUTOFFS = [day + 'T23:59:59Z' for day in ('2026-04-17', '2026-04-30', '2026-05-15',
           '2026-05-31', '2026-06-30', '2026-07-31', '2026-08-28')]
CODE = ['src/dynamic_retrieval/exposure_registry.py', 'scripts/audit_phase14_holdout.py',
        'tests/test_exposure_registry.py']


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def verify(output, index):
    registry = json.loads((output / 'registry.json').read_text(encoding='utf-8'))
    summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    checks = json.loads((output / 'audit-files.json').read_text(encoding='utf-8'))
    for rel, expected in checks['files'].items():
        path = (output / rel).resolve()
        if not path.is_relative_to(output) or digest(path) != expected:
            raise ValueError('Audit output changed: ' + rel)
    for rel, expected in {**registry['source_sha256'], **checks['code_sha256']}.items():
        path = (ROOT / rel).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != expected:
            raise ValueError('Frozen source changed: ' + rel)
    recomputed = audit_index(index, registry, CUTOFFS)
    if recomputed != summary:
        raise ValueError('Readiness summary no longer matches task metadata')
    # Independent set calculation; no calls to registry discovery or selection logic.
    with closing(sqlite3.connect(index.as_uri() + '?mode=ro', uri=True)) as c:
        indexed = {str(row[0]) for row in c.execute('SELECT DISTINCT event_id FROM tasks')}
    excluded = {entry['event_id'] for entry in registry['entries']}
    if excluded != set(registry['excluded_events']):
        raise ValueError('Registry entries differ from exclusion list')
    for entry in registry['entries']:
        if not entry['sources']:
            raise ValueError('Event without historical evidence')
        for source in entry['sources']:
            if source['sha256'] != registry['source_sha256'][source['path']]:
                raise ValueError('Entry source hash mismatch')
    if len(indexed - excluded) != summary['unexposed_event_count']:
        raise ValueError('Independent event difference disagrees')
    return {'status': 'verified', 'audited_source_files': len(registry['source_sha256']),
            'excluded_event_count': len(excluded), 'indexed_event_count': len(indexed),
            'unexposed_event_count': len(indexed - excluded),
            'audit_complete': registry['audit_complete'], 'ready_for_model': False,
            'source_hashes_verified': True, 'output_hashes_verified': True,
            'independent_event_set_check': True, 'labels_read': False,
            'command': 'python -B scripts/audit_phase14_holdout.py --verify'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='artifacts/phase14-holdout-audit-20261023')
    parser.add_argument('--index', default='artifacts/index.sqlite')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    output = (ROOT / args.output).resolve(); index = (ROOT / args.index).resolve()
    if not output.is_relative_to(ROOT / 'artifacts'):
        raise ValueError('Audit output must remain inside project artifacts')
    if args.verify:
        result = verify(output, index)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if output.exists():
        raise ValueError('Preserve existing audit; use --verify or choose a new --output')
    registry = build_registry(ROOT, index)
    summary = audit_index(index, registry, CUTOFFS)
    output.mkdir(parents=True)
    write(output / 'registry.json', registry)
    write(output / 'summary.json', summary)
    write(output / 'audit-files.json', {
        'artifact_type': 'event_only_holdout_audit',
        'files': {name: digest(output / name) for name in ('registry.json', 'summary.json')},
        'code_sha256': {rel: digest(ROOT / rel) for rel in CODE}})
    checked = verify(output, index)
    write(output / 'verification.json', checked)
    print(json.dumps({k: summary[k] for k in ('status', 'audit_complete',
        'excluded_event_count', 'indexed_event_count', 'unexposed_event_count', 'ready_for_model')}, indent=2))
    if registry['errors']:
        print(json.dumps({'audit_errors': registry['errors']}, ensure_ascii=False, indent=2))
    return 0 if registry['audit_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
