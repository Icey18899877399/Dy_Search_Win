"""Opt-in source-time and finite progress rules; no model direction or date imputation.

Progress support is an uncalibrated compatibility mapping, not a resolved outcome.
Exact overlap, five-element identity and scheduler mathematics remain unchanged.
"""
from copy import deepcopy
from datetime import datetime, date, time, timedelta, timezone
import re
from . import patent_evidence_v2 as v2, patent_evidence_v3 as v3
from .core import fact_key

POLICY = 'patent_elements_v4'
DATE = '(?:' + v2.STAMP_PATTERN + '|' + v2.DATE_PATTERN + ')'


def _contract(task):
    c = deepcopy(v2._contract(task))
    c['version'] = 'patent_contract_v4'
    c['condition_blockers'] = []
    desc, visible = v2._visible_description(task)
    conditions = []
    for pattern, name in [
        (r'publicly announced', 'public_announcement'),
        (r'mutually agreed', 'mutual_agreement'),
        (r'general (?:pause|halt)', 'general_halt'),
        (r'effective on a specific date|explicit, dated commitment', 'framework_dated_halt'),
        (r'sitting Israeli Knesset', 'sitting_parliament'),
        (r'Post Counter', 'specified_count_metric')]:
        for m in re.finditer(pattern, desc, re.I):
            conditions.append(dict(name=name, text=m[0], start=m.start(), end=m.end(), source='description'))
    # These additional constraints are not implemented by the bounded templates.
    # Never silently treat a more restrictive task as the base template.
    for m in re.finditer(r'\b(?:at least|at most|minimum|maximum|consecutive|permanent|lasting|last for|only if|provided that|must|requires?|required|subject to|conditional on)\b', desc, re.I):
        c['condition_blockers'].append('unsupported_additional_task_condition')
        conditions.append(dict(name='unsupported', text=m[0], start=m.start(), end=m.end(), source='description'))
    # Exclusion/qualification clauses must match an implemented template in full.
    accepted_qualifications = [
        r'Agreement reached before deadline qualifies even if starts afterward',
        r'Humanitarian pauses and energy infrastructure ceasefires do not qualify',
        r'Only ceasefires which constitute a general pause in the conflict will qualify',
        r'Ceasefires which only apply to energy infrastructure, the Black Sea, or other similar agreements will not qualify',
        r'A peace deal or political framework will qualify if it includes a publicly announced and mutually agreed halt in military engagement, effective on a specific date',
    ]
    for sentence, a, b in v2._sentences(desc):
        if re.search(r'\bqualif(?:y|ies|ication|ications)\b', sentence, re.I) and not any(re.fullmatch(pat+r'[.]*', sentence, re.I) for pat in accepted_qualifications):
            c['condition_blockers'].append('unsupported_qualification_clause')
            conditions.append(dict(name='unsupported_qualification',text=sentence,start=a,end=b,source='description'))
    if (c.get('deadline') or {}).get('date'):
        declared = []
        for m in re.finditer(r'(?:\bby\s+|\bbetween\s+'+v2.DATE_PATTERN+r'\s+and\s+|\band\s+)('+v2.DATE_PATTERN+r')', desc, re.I):
            d = v2._date(m[1])
            if d: declared.append(d.isoformat())
        if any(d != c['deadline']['date'] for d in declared):
            c['condition_blockers'].append('task_deadline_conflict')
    c['condition_witnesses'] = conditions
    c['condition_coverage'] = 'finite_template_not_general_description_parser'
    return c


def effective_task(task):
    out = v2.effective_task(task)
    out['_patent_contract'] = _contract(task)
    return out


def validate_support_rules(task):
    rules = v2.validate_support_rules(task)
    c = _contract(task)
    if c['kind'] in ('knesset_dissolution', 'bilateral_ceasefire'):
        for stage, outcome in [('advance', 'yes'), ('setback', 'no')]:
            rules.append(dict(id=c['kind']+'.progress.'+stage,
                requirements={'participants':'exact', 'time':'source_bound_within_task_and_cutoff', 'stage':stage},
                assertion_pattern='finite_completed_progress_predicate_v4',
                support={o:int(v2._clean(o)==outcome) for o in task['outcomes']},
                reason='Nonterminal compatibility only; the alternative outcome is not contradicted.'))
    return rules


def _parse_time(value):
    stamp = v2._instant(value)
    day = v2._date(value)
    return stamp.isoformat() if stamp else day.isoformat() if day else None


def _time_bounds(value):
    stamp = v2._instant(value)
    if stamp:return stamp,stamp,'explicit_offset'
    day = v2._date(value)
    if not day:return None,None,'unresolved'
    # A date without a source timezone can occur anywhere from UTC+14 to UTC-12.
    base = datetime.combine(day,time.min,timezone.utc)
    return base-timedelta(hours=14),base+timedelta(days=1,hours=12)-timedelta(microseconds=1),'date_only_unknown_zone'


def _temporal(e,c,task):
    low,high,precision = _time_bounds(e.get('time',''))
    cutoff = v2._instant(task.get('cutoff'))
    tr = dict(event_time=e.get('time'),cutoff=task.get('cutoff'),precision=precision,
              interval_start=low.isoformat() if low else None,interval_end=high.isoformat() if high else None,
              publication_time_substituted=False,status='unresolved')
    blockers = []
    if low is None:return ['event_time_unresolved'],tr
    if cutoff is None:blockers.append('cutoff_unresolved')
    elif high>cutoff:blockers.append('event_time_not_fully_before_cutoff')
    start = c['time_interval'].get('start'); end = c['time_interval'].get('end')
    tz = c.get('deadline',{}).get('timezone','unspecified')
    if start:
        d = date.fromisoformat(start)
        boundary = v2._end_of_day(d-timedelta(days=1),tz)
        # Unknown task zone: require containment for every possible civil zone.
        boundary = boundary+timedelta(seconds=1) if boundary else datetime.combine(d,time.min,timezone.utc)+timedelta(hours=12)
        if low<boundary:blockers.append('event_time_not_fully_in_task_interval')
    if end:
        d = date.fromisoformat(end)
        boundary = v2._end_of_day(d,tz)
        boundary = boundary if boundary else datetime.combine(d+timedelta(days=1),time.min,timezone.utc)-timedelta(hours=14,microseconds=1)
        tr['deadline_boundary_utc'] = boundary.astimezone(timezone.utc).isoformat()
        if high>boundary:blockers.append('event_time_not_fully_before_deadline')
    tr['status'] = 'compatible' if not blockers else 'incompatible_or_ambiguous'
    return blockers,tr


def _adjacent(text,anchor,lo,hi,kind):
    rows = list(v2._sentences(text)); result=[]
    index = next((i for i,(_,a,b) in enumerate(rows) if a==anchor['start']),None)
    if index is None:return result
    for s,a,b in rows[index+1:index+4]:
        if a<lo or b>hi or b-anchor['start']>2400:break
        noun = r'(?:vote|bill|dissolution bill)' if kind=='knesset_dissolution' else r'(?:ceasefire|truce|agreement|negotiations)'
        if not re.match(r'^(?:This|These|The)\s+'+noun+r'\s+(?:was|were|is|took place|takes effect|will take effect|never|did|has|must|still)\b',s,re.I):break
        if re.search(r'\b(?:another|previous|different|between|in Gaza|for Israel and Hamas)\b',s,re.I):break
        result.append(v3._w(text,a,b))
    return result


def _progress(anchor,c):
    s = anchor['text'].strip(); leading=r'(?:On (?P<leading>'+DATE+r'),?\s+)?'
    trailing=r'(?: on (?P<trailing>'+DATE+r'))?[.\"”]*'
    if c['kind']=='knesset_dissolution':
        pattern=leading+r'(?P<subject>'+v2.KNESS+r')\s+(?P<verb>passed|approved|rejected|defeated)\s+(?:a|the)\s+preliminary dissolution bill'+trailing
    elif c['kind']=='bilateral_ceasefire':
        one,two=map(v2._entity_pattern,c['participants'])
        pair='(?:'+one+r' and '+two+'|'+two+r' and '+one+')'
        pattern=leading+r'(?P<subject>'+pair+r')\s+(?P<verb>began|opened|suspended|terminated) formal negotiations for a general ceasefire'+trailing
    else:return None
    m=re.fullmatch(pattern,s,re.I)
    if not m and c['kind']=='knesset_dissolution':
        vote=leading+r'(?P<subject>The 120-member Knesset) (?P<verb>voted) in a preliminary reading on the proposal to disband itself, with (?P<votes>\d+) lawmakers supporting the measure and no votes cast against it or recorded abstentions'+trailing
        m=re.fullmatch(vote,s,re.I)
        if m and not 61<=int(m['votes'])<=120:return None
    if not m:return None
    advance = m['verb'].lower() in ('passed','approved','began','opened','voted')
    action = ('dissolution bill preliminary ' if c['kind']=='knesset_dissolution' else 'general ceasefire negotiations ')+('passed' if advance and c['kind']=='knesset_dissolution' else 'opened' if advance else 'rejected' if c['kind']=='knesset_dissolution' else 'suspended')
    if m['verb'].lower()=='voted':action='dissolution bill preliminary favorable majority vote'
    return m, action, 'advance' if advance else 'setback'


def evaluate(elements,task,*,quote,text,original_support,annotation=None):
    e,r,s,tr=v3.evaluate(elements,task,quote=quote,text=text,original_support=original_support,annotation=annotation)
    c=_contract(task);tr['policy']=POLICY;tr['structured_contract']=c
    st=tr['support'];st.update(rule_table_version='patent_support_v4',evidence_class='terminal_assertion' if any(s) else 'neutral',outcome_determined=bool(any(s)),condition_witnesses=c['condition_witnesses'])
    if c['fallback_v1']:return e,r,s,tr
    blockers=list(st['blockers'])+c['condition_blockers']
    anchor=tr['normalization'].get('assertion')
    if not anchor or 'quote_outside_supplied_context' in blockers or 'incomplete_original_sentence_in_context' in blockers:
        st['blockers']=list(dict.fromkeys(blockers));return e,r,[0]*len(s),tr
    lo,hi=tr['normalization'].get('context_read_span',[0,len(text)])
    linked=_adjacent(text,anchor,lo,hi,c['kind'])
    progress=_progress(anchor,c)
    st['progress_candidate']=progress[2] if progress else None
    w=tr['normalization']['witnesses'];event_dates=[];effective_dates=[]
    if e.get('time'):event_dates.append(e['time'])
    # Collect every date grammatically attached to the same assertion.
    attachment=r'(?:^On\s+|(?:dissolved(?: itself)?|ceasefire(?: agreement)?|truce|agreement|bill)\s+on\s+)('+DATE+r')'
    claim=v2._extract(anchor,c,elements)[2].get('clause',anchor['text'])
    for dm in re.finditer(attachment,claim if e.get('time') else '',re.I):
        parsed=_parse_time(dm[1])
        if parsed:event_dates.append(parsed)
    for dm in re.finditer(r'\beffective (?:on )?('+DATE+r')',claim,re.I):
        parsed=_parse_time(dm[1])
        if parsed:effective_dates.append(parsed)
    allowed_future=[]
    if progress:
        m,action,stage=progress
        e['subject']=c['participants'][0];w['subject']=[v3._w(text,anchor['start']+m.start('subject'),anchor['start']+m.end('subject'))]
        if len(c['participants'])==2:e['object']=c['participants'][1];w['object']=deepcopy(w['subject'])
        e['action']=action;w['action']=[v3._w(text,anchor['start'],anchor['end'])]
        for name in ('leading','trailing'):
            if m[name]:
                parsed=_parse_time(m[name])
                if parsed:
                    event_dates.append(parsed);w['time']=[v3._w(text,anchor['start']+m.start(name),anchor['start']+m.end(name))]
        # Only final-outcome requirements are replaced, never conflict/context checks.
        final_only={'procedural_not_completed','no_completed_assertion','agreement_participant_relation_unbound','public_official_agreement_unestablished','mutual_agreement_unestablished','general_halt_unestablished','missing_task_participant'}
        blockers=[b for b in blockers if b not in final_only]
    for row in linked:
        event=re.fullmatch(r'(?:This|The) (?:vote|dissolution bill) (?:took place|was passed|was rejected) on ('+DATE+r')[.\"”]*',row['text'],re.I)
        effect=re.fullmatch(r'(?:This|The) (?:ceasefire|truce) (?:takes effect|will take effect) on ('+DATE+r')[.\"”]*',row['text'],re.I)
        if event:
            parsed=_parse_time(event[1])
            if parsed:
                event_dates.append(parsed);w.setdefault('time',[]).append(v3._w(text,row['start']+event.start(1),row['start']+event.end(1)))
        if effect:
            parsed=_parse_time(effect[1])
            if parsed:effective_dates.append(parsed);allowed_future.append(row['text'])
        # A known future effective start isn't uncertainty about the past agreement.
        if not effect and (v2.CONFLICT.search(row['text']) or v3.NEGATED.search(row['text'])):blockers.append('linked_progress_or_time_conflict')
        if not effect and (v2.UNCERTAIN.search(v2.DATES.sub('',row['text'])) or re.search(r'\b(?:hypothetical|may|imaginary|simulation|conditional|subject to|pending validation)\b',v2.DATES.sub('',row['text']),re.I)):blockers.append('linked_progress_uncertain')
    if allowed_future:
        others=[row['text'] for row in tr['normalization'].get('linked_sentences',[])[1:] if row['text'] not in allowed_future]
        if not any(v2.UNCERTAIN.search(v2.DATES.sub('',x)) or re.search(r'\bmay\b',v2.DATES.sub('',x),re.I) for x in others):
            blockers=[b for b in blockers if b!='linked_conditions_uncertain']
            if e.get('action','').startswith('unresolved ') and 'linked_claim_conflict' not in blockers and not progress:
                canonical=v2._extract(anchor,c,elements)[0].get('action')
                if canonical:e['action']=canonical
    if len(set(event_dates))==1:e['time']=event_dates[0]
    elif len(set(event_dates))>1:blockers.append('conflicting_event_times')
    if len(set(effective_dates))>1:blockers.append('conflicting_effective_start_times')
    if c['kind']!='publisher_monthly_count':
        temporal, timing=_temporal(e,c,task)
        if e.get('action') in ('not dissolved','no ceasefire agreement') and e.get('time')==c.get('deadline',{}).get('date') and re.search(r'\bby\s+'+v2.DATE_PATTERN,anchor['text'],re.I):
            # A negative statement covers the deadline; it is not an event on that date.
            # V2's deadline_not_elapsed and negative_does_not_cover_deadline remain.
            temporal=[b for b in temporal if b not in ('event_time_not_fully_before_deadline','event_time_not_fully_before_cutoff')]
            timing.update(status='coverage_through_task_deadline',precision='explicit_negative_coverage')
        obsolete={'event_time_unresolved','event_after_cutoff','historical_other_cycle','event_after_deadline_not_task_failure'}
        blockers=[b for b in blockers if b not in obsolete]+temporal
        timing['effective_start']=effective_dates[0] if len(set(effective_dates))==1 else None
        st['time_check']=timing
        if c['kind']=='bilateral_ceasefire' and re.search(r'\b(?:framework|peace deal)\b',anchor['text'],re.I) and not timing['effective_start']:blockers.append('framework_effective_start_unresolved')
    blockers=list(dict.fromkeys(blockers))
    identity_conflicts={'linked_claim_conflict','matched_claim_conflict','linked_progress_or_time_conflict','linked_progress_uncertain','conflicting_event_times','conflicting_effective_start_times'}
    if e.get('action') and identity_conflicts.intersection(blockers) and not e['action'].startswith('unresolved '):
        e['action']='unresolved '+e['action'];w['action']=[v3._w(text,anchor['start'],anchor['end'])]+linked
    if progress and not blockers:
        stage=progress[2];outcome='yes' if stage=='advance' else 'no'
        s=[int(v2._clean(o)==outcome) for o in task['outcomes']]
        st.update(evidence_class='nonterminal_progress',outcome_determined=False,progress_stage=stage)
    elif blockers:
        s=[0]*len(task['outcomes']);st.update(evidence_class='neutral',outcome_determined=False)
    else:
        # Re-evaluate terminal compatibility after correcting timezone/calendar checks.
        yes=-1 if e.get('action') in ('not dissolved','no ceasefire agreement') else 1
        if c['kind']!='publisher_monthly_count':s=[yes if v2._clean(o)=='yes' else -yes for o in task['outcomes']]
        st.update(evidence_class='terminal_assertion' if any(s) else 'neutral',outcome_determined=bool(any(s)))
    rules=validate_support_rules(task)
    matched=[x['id'] for x in rules if any(s) and x['support']==dict(zip(task['outcomes'],s))]
    st.update(blockers=blockers,matched_rule_ids=matched,resolution='matched' if any(s) else 'no_unambiguous_rule_abstain',rules=[dict(x,matched=x['id'] in matched,blockers=blockers) for x in rules])
    tr['normalization']['temporal_linked_sentences']=linked
    tr['normalization']['assertion_status']='progress_'+progress[2] if progress else tr['normalization'].get('assertion_status')
    target=tr['effective_target'];matched=[k for k,v in target.items() if e.get(k)==v];r=len(matched)/len(target) if target else 0.
    tr.update(effective_elements=e,overlap=dict(target=target,matched=matched,matched_count=len(matched),target_count=len(target),relevance=r,semantic_gate_applied=False),fact_group=dict(key=list(fact_key(e)),policy='exact_normalized_five_elements',fuzzy_merge=False,weighting='gamma ** chronological_rank'))
    return e,r,s,tr

