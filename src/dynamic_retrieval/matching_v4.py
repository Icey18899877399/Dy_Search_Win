"""Conservative, comparison-only semantic matching; never changes support or fact keys."""
import calendar
import re
from datetime import date, datetime, timedelta

# Closed identities, not substring matching or country/official equivalence.
IDENTITIES = (
    {'us', 'u s', 'united states', 'united states of america'},
    {'starmer', 'keir starmer'}, {'trump', 'donald trump'},
    {'epstein', 'jeffrey epstein'},
)
MILITARY = {'russia': {'russian forces', 'russian army', 'russian troops'},
            'ukraine': {'ukrainian forces', 'ukrainian army', 'ukrainian troops'}}
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}


def entity(value):
    from .matching import text
    return re.sub(r'^the ', '', text(value))


def same_entity(a, b, action):
    a, b = entity(a), entity(b)
    if a == b:
        return True
    if any(a in group and b in group for group in IDENTITIES):
        return True
    return action in ('capture', 'invade', 'strike', 'control') and a in MILITARY.get(b, set())


def normalize(task):
    from .matching import _normalize_task_v3
    t = _normalize_task_v3(task)
    # Preserve the operator and complete deadline lost by the legacy lexical parser.
    m = re.search(r'\b(by|before|after|in)\s+([^?]+)\??$', t['question'], re.I)
    if m and (m[1].lower() != 'in' or re.search(r'\b20\d{2}\b', m[2]) or any(month in m[2].lower().split() for month in MONTHS)):
        t['target_elements']['time'] = m[2].strip()
        t['temporal_operator'] = m[1].lower()
    t['matching_policy'] = 'typed_v4'
    t['task_extraction'] = t['task_extraction'].replace('v3', 'v4')
    return t


def date_interval(value, assumed_year=None):
    """Only unambiguous whole date expressions. Mixed event dates remain unknown."""
    s = str(value).strip().lower()
    s = re.sub(r'^(?:the )?end of (20\d{2})$', r'december 31, \1', s)
    s = re.sub(r'^as of\s+', '', s)
    phase = re.match(r'^(early|mid|late)\s+', s)
    if phase:
        s = s[phase.end():]
    try:
        if re.fullmatch(r'20\d{2}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:z|[+-]\d{2}:\d{2})?', s):
            d = datetime.fromisoformat(s.upper().replace('Z', '+00:00')).date()
            return d, d
        if re.fullmatch(r'20\d{2}-\d{2}', s):
            y, month = map(int, s.split('-'))
            return date(y, month, 1), date(y, month, calendar.monthrange(y, month)[1])
        if re.fullmatch(r'20\d{2}-\d{2}-\d{2}', s):
            d = date.fromisoformat(s)
            return d, d
        if re.fullmatch(r'20\d{2}', s):
            y = int(s)
            return date(y, 1, 1), date(y, 12, 31)
        m = re.fullmatch(r'([a-z]+)\s+(?:(\d{1,2})(?:st|nd|rd|th)?(?:,\s*|\s+|$))?(20\d{2})?', s)
        if not m or m[1] not in MONTHS:
            return None
        y = int(m[3]) if m[3] else assumed_year
        if y is None:
            return None
        month = MONTHS[m[1]]
        if m[2]:
            d = date(y, month, int(m[2]))
            return d, d
        last = calendar.monthrange(y, month)[1]
        low, high = (1, 10) if phase and phase[1] == 'early' else (11, 20) if phase and phase[1] == 'mid' else (21, last) if phase else (1, last)
        return date(y, month, low), date(y, month, high)
    except ValueError:
        return None


def time_check(actual, target, task):
    result = dict(status='unknown', operator=task.get('temporal_operator'),
                  note='Event time only; publication time is never substituted.')
    try:
        cutoff = date.fromisoformat(task['cutoff'][:10])
    except (KeyError, ValueError):
        return result
    # A missing target year is explicitly anchored to the frozen forecast year.
    bound = date_interval(target, cutoff.year)
    event = date_interval(actual)  # no invented year for an evidence date
    if not bound:
        return result
    op = result['operator']
    start = date(cutoff.year, 1, 1)
    end = cutoff
    if op == 'before':
        deadline = bound[0]
        end = min(end, deadline - timedelta(days=1))
    elif op == 'by':
        deadline = bound[1]
        end = min(end, deadline)
    elif op == 'after':
        deadline = bound[1]
        start = max(start, deadline + timedelta(days=1))
    else:
        deadline = bound[1]
        start, end = max(start, bound[0]), min(end, bound[1])
    result.update(deadline=deadline.isoformat(), lower=start.isoformat(), upper=end.isoformat(),
                  target_year_assumed=not bool(re.search(r'\b20\d{2}\b', str(target))),
                  scope='current_forecast_year_observed_event_context')
    if event:
        result['event_interval'] = [d.isoformat() for d in event]
        result['status'] = ('outside' if event[1] < start or event[0] > end else
                            'within' if event[0] >= start and event[1] <= end else 'overlap_unknown')
    return result


def relevance(elements, task):
    from .matching import text, canonical_action
    t = normalize(task)
    target = t['target_elements']
    matched, reasons, blockers = [], {}, []
    action = text(target.get('action', ''))
    observed = text(elements.get('action', ''))
    relation = 'unresolved'
    comparison = dict(elements)

    def mark(key, reason):
        if key not in matched:
            matched.append(key)
        reasons[key] = reason

    for key, value in target.items():
        if key == 'time':
            continue
        actual = elements.get(key, '')
        candidates = [value] + task.get('element_aliases', {}).get(key, [])
        if actual and any(text(actual) == text(c) for c in candidates):
            mark(key, 'exact_or_declared_alias')
        if key == 'subject' and actual and any(same_entity(actual, c, action) for c in candidates):
            mark(key, 'closed_identity_or_contextual_military_alias')

    disarm = r'\b(?:disarm|disarms|disarmed|disarming|disarmament)\b'
    if action == 'agree' and re.search(disarm, text(target.get('object', ''))):
        third_party = re.search(r'\b(?:calls? on|urges?|urged|asks?|asked|requires?|required)\b.+\bto disarm\b', observed)
        obj = text(elements.get('object', ''))
        object_topic = not obj or bool(re.match(r'^(?:to disarm|disarmament|weapons disarmament)\b', obj))
        if re.search(r'\bdisarmament of\b', obj):
            object_topic = False  # Unknown owner is not silently rewritten.
        self_statement = re.search(r'\b(?:agree|agrees|agreed|refuse|refuses|refused|refusal|reject|rejects|rejected|rebuff|rebuffs|rebuffed|disarmed)\b', observed)
        if re.search(r'\bdisarmament of\b', observed):
            self_statement = False
        if re.search(disarm, observed) and self_statement and not third_party and object_topic:
            mark('action', 'same_disarmament_event_including_refusal')
            # Only project the missing/topic object; unrelated explicit objects cannot be overwritten.
            obj = text(elements.get('object', ''))
            if not obj or re.search(disarm, obj):
                mark('object', 'disarmament_topic_from_action_or_object')
                comparison['object'] = target['object']
            relation = 'same_event_opposing_or_related_statement'
    elif action == 'capture':
        if re.fullmatch(r'(?:has |have )?(?:captured|capture|captures)', observed):
            mark('action', 'closed_capture_inflection')
            relation = 'capture_statement'
        elif re.search(r'\b(?:advanced|advancing|penetrating|surrounded|surrounding)\b', observed):
            mark('action', 'related_military_progress')
            relation = 'military_progress_not_capture'
    elif action == 'release':
        if re.search(r'\b(?:released|unsealed)\b|made publicly available', observed):
            mark('action', 'public_release_or_unsealing')
            relation = 'release_statement_not_authenticity_claim'
            obj = text(target.get('object', ''))
            # A narrow passive-note projection with explicit owner identity and note topic.
            suffix = ' suicide note'
            if obj.endswith(suffix):
                owner = obj[:-len(suffix)]
                subject = entity(elements.get('subject', ''))
                subject_owner = re.sub(r'^(?:purported|alleged) ', '', subject)
                subject_owner = re.sub(r' suicide note$', '', subject_owner)
                raw_obj = text(elements.get('object', ''))
                owner_ok = same_entity(subject_owner, owner, action)
                topic_ok = 'suicide note' in observed or 'suicide note' in subject
                object_ok = not raw_obj or bool(re.search(r'\b'+re.escape(owner)+r'\b', raw_obj))
                if owner_ok and topic_ok and object_ok:
                    mark('object', 'passive_note_owner_and_topic_projection')
                    comparison['object'] = target['object']
    elif action == 'out':
        if re.search(r'\b(?:resign|resigned|resignation|departure)\b|step down', observed):
            mark('action', 'leadership_departure_related_statement')
            relation = 'departure_statement_or_pressure_not_completed_exit'
    else:
        if observed and canonical_action(observed) == canonical_action(action):
            mark('action', 'closed_action_synonyms')
            relation = 'same_action'

    # Explicit mismatches and unknown relations cannot pass merely on shared actor/date.
    for key in ('subject', 'object', 'location'):
        if target.get(key) and key not in matched:
            blockers.append(key + ('_mismatch' if elements.get(key) else '_unresolved'))
    if target.get('action') and 'action' not in matched:
        blockers.append('action_relation_unresolved')
    timing = time_check(elements.get('time', ''), target.get('time', ''), t)
    if timing['status'] == 'within':
        mark('time', 'explicit_event_interval_within_frozen_scope')
    elif timing['status'] == 'outside':
        blockers.append('event_time_outside_interval')
    score = len(matched) / len(target)
    return (0.0 if blockers else score), dict(
        policy='typed_v4', target=target, matched=matched, reasons=reasons,
        blockers=blockers, relation=relation, time_check=timing,
        comparison_elements=comparison, ungated_relevance=score,
        support_policy='unchanged_frozen_annotation_not_completion_or_truth',
        warnings=t.get('matching_warnings', []))
