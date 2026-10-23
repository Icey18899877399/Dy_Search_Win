"""Opt-in, quote-grounded fact identity. No inference, fuzzy matching or mutation.

All five fields must have lexical grounding in a bound quote. Exact complete dates
and two closed country-name alias sets may normalize. Qualifiers, uncertain times,
unknown sources and incomplete evidence stay document-specific. This is lexical
identity auditing, not truth validation or independence across syndicating sources.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import re
from .core import ELEMENTS

POLICY = 'conservative_v1'
_ALIASES = (
    ('united states', ('united states', 'united states of america', 'u.s.', 'u.s.a.', 'usa')),
    ('united kingdom', ('united kingdom', 'u.k.', 'uk')),
)
_UNKNOWN = {'', 'unknown', 'unspecified', 'not specified', 'n/a', 'none', 'here', 'there'}
_QUALIFIERS = re.compile(r'\b(?:if|unless|conditionally|conditional|might|may|could|would|allegedly|reportedly|denied|not|never|no)\b', re.I)
_MONTHS = ('January','February','March','April','May','June','July','August','September','October','November','December')


def _lexical(value):
    return ' '.join(str(value).strip().casefold().split())


def _day(value):
    # Entire values only: do not erase ranges, precision, before/after or a clock.
    value = str(value).strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        try:return datetime.strptime(value, '%Y-%m-%d').date().isoformat()
        except ValueError:return None
    for pattern in ('%B %d, %Y', '%B %d %Y', '%d %B %Y', '%b %d, %Y', '%d %b %Y'):
        try:return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:pass
    return None


def _canonical(field, value):
    lexical = _lexical(value)
    if field == 'time':return _day(value) or lexical
    if field in ('subject', 'location'):
        for canonical, aliases in _ALIASES:
            if lexical in aliases:return canonical
    return lexical


def _contains(text, value):
    return bool(value and re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', text))


def _forms(field, value):
    canonical = _canonical(field, value)
    forms = {_lexical(value)}
    if field in ('subject','location'):
        for name, aliases in _ALIASES:
            if name == canonical:forms.update(aliases)
    day = _day(value) if field == 'time' else None
    if day:
        dt = datetime.strptime(day, '%Y-%m-%d')
        month = _MONTHS[dt.month-1].casefold()
        forms.update((day, f'{month} {dt.day}, {dt.year}', f'{month} {dt.day} {dt.year}',
                      f'{dt.day} {month} {dt.year}', f'{month[:3]} {dt.day}, {dt.year}',
                      f'{dt.day} {month[:3]} {dt.year}'))
    return forms


def row_audit(row):
    """Return a comparison-only audit, including raw values and grounding witnesses."""
    if not isinstance(row.get('id'),str) or not row['id']:
        raise ValueError('Each row needs a nonempty string id')
    elements = row.get('elements', {})
    quote = row.get('quote','')
    # Require actual document/excerpt binding; a quote cannot attest to itself.
    contexts = [str(row.get('title',''))+'\n'+str(row.get('text',''))]
    if isinstance(row.get('excerpt'),str):contexts.append(row['excerpt'])
    bound = isinstance(quote,str) and bool(quote.strip()) and any(quote in x for x in contexts)
    normalized_quote = _lexical(quote)
    blockers=[];grounding={};canonical={}
    if not bound:blockers.append('quote_not_bound')
    qualifier_text=re.sub(r'\bMay\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}\s+May\s+\d{4}\b', '', quote, flags=re.I)
    if _QUALIFIERS.search(qualifier_text):blockers.append('quote_has_qualification_or_negation')
    if not isinstance(row.get('source_id'),str) or not row['source_id'].strip():blockers.append('source_unknown')
    if row.get('factual_status') in ('conflicting','speculative','opinion','irrelevant'):
        blockers.append('nonfactual_or_conflicting_status')
    if row.get('time_scope') in ('unknown','historical_other_cycle'):
        blockers.append('time_scope_not_compatible')
    for field in ELEMENTS:
        raw=elements.get(field,'')
        if not isinstance(raw,str) or _lexical(raw) in _UNKNOWN:
            blockers.append(field+'_missing_or_unknown');continue
        canonical[field]=_canonical(field,raw)
        if field == 'time' and _day(raw) is None:blockers.append('time_not_exact_day')
        matches=sorted(form for form in _forms(field,raw) if _contains(normalized_quote,form))
        grounding[field]={'grounded':bound and bool(matches),'quote_forms':matches}
        if not matches:blockers.append(field+'_not_in_bound_quote')
    support=row.get('support')
    if not isinstance(support,list) or len(support)!=2 or any(type(x) is not int or x not in (-1,0,1) for x in support):
        blockers.append('invalid_support')
    return dict(document_id=row['id'],eligible=not blockers,blockers=blockers,
                raw_elements=dict(elements),canonical_elements=canonical,support=support,
                quote=quote,quote_bound=bound,grounding=grounding,
                reason='all_five_grounded_exact_day_same_support_closed_aliases' if not blockers else 'document_specific_no_coalescing')


def row_key(row):
    """Hashable key for a task-local optional engine callback; support is part of identity."""
    audit=row_audit(row)
    if not audit['eligible']:return (POLICY,'document',row['id'])
    return (POLICY,'fact',tuple(audit['canonical_elements'][k] for k in ELEMENTS),tuple(row['support']))


def _order(row):
    try:
        stamp=datetime.fromisoformat(row.get('published_at','').replace('Z','+00:00'))
        stamp=(stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError,TypeError):stamp=float('inf')
    return (stamp,str(row.get('source_id','')),row['id'])


def group_facts(rows):
    """Deterministic report; same-source duplicates are retained and listed separately."""
    rows=list(rows);ids=[x['id'] for x in rows]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate document ids are ambiguous')
    groups=defaultdict(list)
    for row in rows:groups[row_key(row)].append(row)
    result=[]
    for key,members in groups.items():
        ordered=sorted(members,key=_order);sources=defaultdict(list)
        for row in ordered:sources[str(row.get('source_id',''))].append(row['id'])
        encoded=json.dumps(key,ensure_ascii=False,separators=(',',':'))
        audits=[row_audit(row) for row in ordered]
        result.append(dict(group_id=hashlib.sha256(encoded.encode('utf-8')).hexdigest(),
            eligible=audits[0]['eligible'],document_ids=[row['id'] for row in ordered],
            independent_source_count=len(sources) if audits[0]['eligible'] else 0,
            source_representatives={s:ids[0] for s,ids in sorted(sources.items())},
            same_source_duplicates={s:ids[1:] for s,ids in sorted(sources.items()) if len(ids)>1},
            rows=audits))
    return dict(policy=POLICY,groups=sorted(result,key=lambda x:x['group_id']),
                input_documents=len(rows),eligible_documents=sum(row_audit(row)['eligible'] for row in rows),
                grouped_documents=sum(len(g['document_ids']) for g in result if len(g['document_ids'])>1),
                limitation='Lexical grounding is not truth validation; distinct source IDs do not prove independent reporting.')


def independent_fact_weights(rows, gamma):
    """Gamma discounts distinct source representatives; same-source copies weigh zero.

Incomplete/ungrounded rows each remain a singleton of weight one. No elements or
support are changed. Every unique input document ID occurs in the returned map.
"""
    if not 0 < gamma < 1:raise ValueError('gamma must be strictly between zero and one')
    weights={}
    for group in group_facts(rows)['groups']:
        rank=0
        representatives=set(group['source_representatives'].values())
        for id in group['document_ids']:
            if id not in representatives:weights[id]=0.
            else:weights[id]=gamma**rank;rank+=1
    return weights


