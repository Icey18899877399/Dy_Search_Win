"""Bounded, label-blind preparation of candidate cohorts for human review.

Metadata gates do not prove that a question is semantically prospective. Every
accepted candidate remains pending deadline and evidence review.
"""
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from .data.store import utc_iso
from .evidence import extract, prepare_task


TASK_FIELDS = ('market_id', 'event_id', 'question', 'description', 'outcomes',
               'observed_at', 'metadata_quality', 'source_file')
MONTHS = {name.lower(): number for number, name in enumerate(
    ('January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'), 1)}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def _question_dates(question):
    dates = []
    for value in re.findall(r'\b\d{4}-\d{2}-\d{2}\b', question):
        try:
            dates.append(date.fromisoformat(value))
        except ValueError:
            pass
    pattern = r'\b(' + '|'.join(MONTHS) + r')\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*|\s+)(\d{4})\b'
    for month, day, year in re.findall(pattern, question, re.I):
        try:
            dates.append(date(int(year), MONTHS[month.lower()], int(day)))
        except ValueError:
            pass
    return sorted(set(dates))


def _eligibility(task, obj, cutoff, max_age):
    if not isinstance(obj, dict) or not isinstance(obj.get('events'), list):
        return None, 'malformed_source'
    try:
        observed = utc_iso(obj.get('collected_at'))
    except ValueError:
        return None, 'invalid_collected_at'
    if observed != task['observed_at'] or observed > cutoff:
        return None, 'source_observation_mismatch'
    events = [e for e in obj['events'] if isinstance(e, dict)
              and str(e.get('event_id')) == task['event_id']]
    if len(events) != 1:
        return None, 'ambiguous_event_record'
    markets = events[0].get('markets')
    if not isinstance(markets, list):
        return None, 'malformed_market_records'
    records = [m for m in markets if isinstance(m, dict)
               and str(m.get('market_id')) == task['market_id']]
    if len(records) != 1:
        return None, 'ambiguous_market_record'
    market = records[0]
    outcomes = market.get('outcomes')
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except ValueError:
            return None, 'source_snapshot_mismatch'
    if (market.get('question') != task['question'] or
            str(market.get('description') or '') != task['description'] or
            'description' not in market or outcomes != task['outcomes']):
        return None, 'source_snapshot_mismatch'
    if market.get('active') is not True:
        return None, 'active_not_explicit_true'
    if market.get('closed') is not False:
        return None, 'closed_not_explicit_false'
    try:
        end = utc_iso(market.get('end_date'))
    except ValueError:
        return None, 'invalid_end_date'
    if end <= cutoff:
        return None, 'end_date_not_future'
    start = None
    if 'start_date' in market:
        try:
            start = utc_iso(market['start_date'])
        except ValueError:
            return None, 'invalid_start_date'
        if start > cutoff:
            return None, 'start_date_after_cutoff'
    age = datetime.fromisoformat(cutoff.replace('Z', '+00:00')) - datetime.fromisoformat(observed.replace('Z', '+00:00'))
    if age > timedelta(days=max_age):
        return None, 'stale_metadata'
    dates = _question_dates(task['question'])
    if any(value < date.fromisoformat(cutoff[:10]) for value in dates):
        return None, 'expired_question_date'
    return dict(active=True, closed=False, end_date=end, start_date=start,
                observed_at=observed, metadata_age_days=age.total_seconds() / 86400,
                exact_question_dates=[value.isoformat() for value in dates],
                semantic_deadline_review='pending',
                status='metadata_candidate_pending_human_review'), None


def prepare_cohort(store, data_root, cutoff, count=5, min_documents=5,
                   max_metadata_age_days=7, seed='patent-v1', task_filter=None,
                   document_selector=None, create_drafts=True):
    """Return a JSON-safe review draft, never labels or verified cohort claims.

    Selection uses a seeded stable hash. Raw metadata files are read once per
    invocation and checked against the index audit; document bodies are requested
    only after metadata gates and only until the requested count is reached.
    """
    cutoff = utc_iso(cutoff)
    if type(count) is not int or count < 1 or type(min_documents) is not int or min_documents < 1:
        raise ValueError('count and min_documents must be positive integers')
    if (type(max_metadata_age_days) not in (int, float) or
            not 0 <= max_metadata_age_days <= 36500):
        raise ValueError('max_metadata_age_days must be finite and nonnegative (at most 36500)')
    if not isinstance(seed, str):
        raise ValueError('seed must be a string')
    root = Path(data_root).resolve()
    meta = dict(store.connection.execute("SELECT key,value FROM meta WHERE key IN ('audit','data_root')"))
    if Path(meta.get('data_root', '')).resolve() != root:
        raise ValueError('data_root does not match indexed source root')
    try:
        audit = json.loads(meta['audit'])
        entries = audit['source_manifest']
        if not isinstance(entries, list):
            raise ValueError('Invalid source manifest')
        manifest = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
                raise ValueError('Invalid source manifest entry')
            if entry['path'] in manifest:
                raise ValueError('Duplicate source manifest path')
            manifest[entry['path']] = entry.get('sha256')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Index has no valid source audit') from exc
    tasks = [{key: task[key] for key in TASK_FIELDS} for task in store.tasks(cutoff)]
    tasks.sort(key=lambda task: (_digest([seed, task['event_id'], task['market_id'], task['observed_at']]), task['market_id']))
    source_cache, document_cache = {}, {}
    selected, exclusions, chosen_events = [], [], set()
    verified_sources, input_documents = {}, {}

    def source(rel):
        if rel in source_cache:
            return source_cache[rel]
        path = (root / rel).resolve()
        obj, error, digest = None, None, None
        if Path(rel).is_absolute() or root not in path.parents or any(p.casefold() == 'ground_truth' for p in Path(rel).parts):
            error = 'unsafe_source_path'
        elif not isinstance(manifest.get(rel), str) or not re.fullmatch('[0-9a-f]{64}', manifest[rel]):
            error = 'source_audit_missing'
        else:
            try:
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if digest != manifest[rel]:
                    error = 'source_hash_mismatch'
                else:
                    obj = json.loads(raw.decode('utf-8-sig'))
                    verified_sources[rel] = digest
            except (OSError, UnicodeError, ValueError):
                error = 'source_read_or_parse_error'
        source_cache[rel] = obj, error, digest
        return source_cache[rel]

    for task in tasks:
        if len(selected) >= count:
            break
        reason = None
        if task_filter is not None and not task_filter(task):
            reason = 'excluded_by_frozen_task_policy'
        elif task['metadata_quality'] != 'full_metadata':
            reason = 'full_metadata_required'
        elif task['event_id'] in chosen_events:
            reason = 'event_already_selected'
        else:
            obj, reason, source_hash = source(task['source_file'])
            if reason is None:
                eligibility, reason = _eligibility(task, obj, cutoff, max_metadata_age_days)
            if reason is None:
                eid = task['event_id']
                if eid not in document_cache:
                    document_cache[eid] = store.documents(eid, cutoff)
                documents = document_cache[eid]
                if document_selector is not None:
                    documents = document_selector(task, documents)
                if len(documents) < min_documents:
                    reason = 'insufficient_documents'
                else:
                    task = prepare_task(dict(task, cutoff=cutoff))
                    annotations = {}
                    for document in documents:
                        extracted = extract(document, task) if create_drafts else None
                        if create_drafts: annotations[document['id']] = dict(
                            reviewed=False, elements=extracted['elements'], support=[0, 0],
                            quote=document['text'][:300], title=document['title'],
                            source_file=document['source_file'], body_sha256=document['content_hash'],
                            review_status='pending_human_review')
                        input_documents[document['id']] = dict(body_sha256=document['content_hash'],
                            source_file=document['source_file'],
                            indexed_source_sha256=manifest.get(document['source_file']))
                    eligibility['source_sha256'] = source_hash
                    selected.append(dict(task=task, eligibility=eligibility,
                                         documents=documents, annotations=annotations))
                    chosen_events.add(eid)
        if reason:
            exclusions.append(dict(market_id=task['market_id'], event_id=task['event_id'], reason=reason))
    return dict(requested=count, completed=len(selected), selected=selected, exclusions=exclusions,
                exclusion_counts=dict(sorted(Counter(row['reason'] for row in exclusions).items())),
                provenance=dict(format='dynamic-retrieval-preparation-v1', data_root=str(root), cutoff=cutoff, seed=seed,
                    min_documents=min_documents, max_metadata_age_days=max_metadata_age_days,
                    candidate_tasks=len(tasks), examined_tasks=len(selected) + len(exclusions),
                    selection_status='draft_pending_human_review',
                    source_files=verified_sources, input_documents=input_documents,
                    input_documents_sha256=_digest(input_documents),
                    source_policy='Raw metadata SHA256 matches indexed audit; collected_at matches task observed_at.',
                    time_policy='Documents require published_at and observed_at <= cutoff.',
                    semantic_deadline_review='pending',
                    limitations=['Metadata eligibility is not verified semantic prospectivity.',
                                 'Question date scanning is conservative and incomplete.',
                                 'Source timestamps are not independently verified.',
                                 'Evidence and outcome support require human review.']))
