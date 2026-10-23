"""Read-only historical body recovery candidates. Never replaces prediction input.

Only exact technical stubs may be skipped. A substantive correction, failed
scrape with substantive text, or oversized aggregation stops the search. Older
body visibility is established by its own two clocks, not the latest record.
"""
from copy import deepcopy
import hashlib
import re
from .data.store import utc_iso

VERSION = 'source_history_candidate_v1'


def technical_stub(body):
    """Conservative whole-body patterns; incidental mentions are substantive."""
    if not body.strip():
        return 'empty_body'
    if re.fullmatch(r'\s*The Wayback Machine\s*-\s*https?://web\.archive\.org/\S+\s*', body, re.I):
        return 'archive_wrapper_only'
    if re.fullmatch(r'\s*(?:access denied|just a moment|enable javascript|verify you are human)[.!…\s]*', body, re.I):
        return 'access_page_only'
    return None


def historical_body_candidate(task, documents):
    cutoff = utc_iso(task['cutoff'])
    if task.get('observed_at') is not None and utc_iso(task['observed_at']) > cutoff:
        raise ValueError('Task definition is after cutoff')
    rows = list(documents)
    if any(not d.get('canonical_url') or str(d.get('event_id')) != str(task['event_id']) for d in rows):
        raise ValueError('Expected same task event and nonempty canonical URL')
    if len({d['canonical_url'] for d in rows}) > 1:
        raise ValueError('Mixed canonical URLs')
    out = dict(version=VERSION, status='no_visible_substantive_body', document=None,
               latest_visible_id=None, skipped=[], excluded=[], reviewed=False,
               prediction_input_replaced=False, event_date_imputed=False,
               scope='diagnostic_candidate_only_not_latest_content_or_truth')
    visible = []
    for d in rows:
        reasons = []
        for field in ('published_at', 'observed_at'):
            try:
                if utc_iso(d.get(field)) > cutoff: reasons.append(field+'_after_cutoff')
            except (TypeError, ValueError):
                reasons.append(field+'_invalid')
        if reasons:
            out['excluded'].append(dict(id=d['id'], reasons=reasons))
            continue
        if hashlib.sha256(d['text'].encode('utf-8')).hexdigest() != d.get('content_hash'):
            raise ValueError('Body content hash mismatch: '+str(d['id']))
        visible.append(d)
    visible.sort(key=lambda d: str(d['id']))
    visible.sort(key=lambda d: utc_iso(d['observed_at']), reverse=True)
    if visible: out['latest_visible_id'] = visible[0]['id']
    for d in visible:
        reason = technical_stub(d['text'])
        if reason:
            out['skipped'].append(dict(id=d['id'], content_hash=d['content_hash'],
                observed_at=d['observed_at'], published_at=d['published_at'], reason=reason))
            continue
        out['document'] = deepcopy(d)
        out['status'] = 'historical_body_candidate' if out['skipped'] else 'latest_substantive_body'
        break
    return out
