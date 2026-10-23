"""Opt-in patent element overlap, auditable outcome rules, exact fact identity.

No semantic inference is performed. Configured support rules are trusted task
contracts, never model-produced patterns. Missing contracts abstain except for
one closed, complete election-winner question/statement template.
"""
from copy import deepcopy
from datetime import datetime
import re
import unicodedata
from .core import ELEMENTS, fact_key
from .semantic import MARKET_ODDS

POLICY = 'patent_elements_v1'
_UNCERTAIN = re.compile(r'\b(?:if|unless|could|might|may|would|will|expected|scheduled|plans?|forecast\w*|predict\w*|alleged\w*|disputed|denied|not|never)\b|\?', re.I)
_CONFLICT = re.compile(r'\b(?:not|never|denied|disputed|retracted|false|incorrect|untrue|conflicting|contradicted|contradictory|debunked)\b', re.I)
_DATE = re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b', re.I)


def _clean(value):
    return ' '.join(unicodedata.normalize('NFKC',str(value)).casefold().split())


def _value(key,value):
    value=_clean(value)
    if key=='time':
        for fmt in ('%Y-%m-%d','%B %d, %Y','%B %d %Y','%d %B %Y'):
            try:return datetime.strptime(value,fmt).date().isoformat()
            except ValueError:pass
    return value


def _canonical(key,value,task):
    value=_value(key,value)
    target=task['target_elements'].get(key)
    if target and value in {_value(key,x) for x in [target]+task.get('element_aliases',{}).get(key,[])}:
        return _value(key,target)
    return value


def _witnesses(key,value,task,text):
    candidates=[value]
    target=task['target_elements'].get(key)
    if target and _canonical(key,value,task)==_value(key,target):
        candidates += [target]+task.get('element_aliases',{}).get(key,[])
    found=[]
    for candidate in candidates:
        pattern=r'(?<!\w)'+r'\s+'.join(re.escape(part) for part in str(candidate).strip().split())+r'(?!\w)'
        if not str(candidate).strip():continue
        for match in re.finditer(pattern,text,re.I):
            found.append(dict(text=match.group(),start=match.start(),end=match.end(),scope='original_title_and_body'))
    if key=='time':
        for match in _DATE.finditer(text):
            if _value('time',match.group())==_canonical(key,value,task):
                found.append(dict(text=match.group(),start=match.start(),end=match.end(),scope='original_title_and_body'))
    unique={(w['start'],w['end']):w for w in found}
    return list(unique.values())


def effective_task(task):
    """Parse closed known questions, keeping frozen task/annotation bindings intact."""
    effective=deepcopy(task)
    original=task['target_elements']
    question=str(task['question']).strip().rstrip('?')
    if re.fullmatch(r'(?:Will )?Israeli parliament (?:be )?dissolved by July 31(?:,? 2026)?',question,re.I):
        effective['target_elements']={'subject':'Israeli parliament','action':'dissolve',
            'time':'July 31, 2026' if re.search(r'2026',question) else 'July 31'}
        parsed=dict(status='supported_template',kind='knesset_dissolution',
            reason='Closed question identifies parliament dissolution; proposal stages do not establish dissolution.')
    elif re.fullmatch(r'Will Kevin Warsh be confirmed as Fed Chair',question,re.I):
        effective['target_elements']={'subject':'Kevin Warsh','action':'confirm','object':'Federal Reserve Chair'}
        parsed=dict(status='supported_template',kind='warsh_confirmation',
            reason='Closed question identifies full confirmation; committee stages do not establish it. No date invented.')
    else:
        from .matching_v5 import normalize
        candidate=normalize(task)
        parse=candidate['task_parse']
        if parse['status']=='supported_template' and parse['kind']!='legacy_typed':
            effective['target_elements']=candidate['target_elements']
            parsed=deepcopy(parse)
            parsed['reason']='Closed existing question parser only; its semantic relevance gate is not used.'
        elif not original.get('action') or not original.get('subject') or _clean(original.get('action')) in ('be','end'):
            parsed=dict(status='unsupported',kind='unresolved_target',
                reason='Missing concrete action/subject or compound question stored as subject; no closed task parser available.')
        else:
            parsed=dict(status='configured_elements',kind='explicit_target',
                reason='Configured target elements retained; support still requires a complete outcome contract.')
    effective['_patent_task_parse']=parsed
    return effective


def _default_rules(task):
    t={k:_value(k,v) for k,v in task['target_elements'].items() if v}
    if set(t)!={'subject','action','object','time'} or t['action']!='win' or not re.fullmatch(r'20\d{2}',t['time']):
        return []
    # A question-derived winner relation is the only built-in outcome contract.
    # Acquisition, confirmation, thresholds and procedural stages require an explicit rule.
    if not re.search(r'\b(?:election|race)\b',t['object']):return []
    question=r'will '+re.escape(t['subject'])+r' win (?:the )?'+re.escape(t['object'])+r' in '+t['time']+r'\?'
    if not re.fullmatch(question,_clean(task['question'])):return []
    pattern=(r'(?P<subject>'+re.escape(t['subject'])+r') (?P<action>won) (?:the )?'
        r'(?P<object>'+re.escape(t['object'])+r') in (?P<time>'+t['time']+r')\.?')
    # A past-tense action must also be an explicitly configured alias of win.
    if _canonical('action','won',task)!='win':return []
    return [dict(id='closed_election_winner_v1',requirements=t,assertion_pattern=pattern,
        support={o:1 if o.casefold()=='yes' else -1 for o in task['outcomes']},
        reason='Exact complete winner assertion for the event asked in the closed binary question.')]


def validate_support_rules(task):
    """Validate before retrieval/model work; returns an isolated finite rule table.

    Each pattern is fullmatched against a sentence and must bind a named group
    for every requirement. Non-action identity requirements must equal the task.
    A differing action is permitted only as an explicitly configured contract.
    """
    task=effective_task(task)
    contract=task.get('support_rules')
    if contract is None:return _default_rules(task)
    if not isinstance(contract,dict) or set(contract)!={'version','rules'} or contract['version']!='patent_support_v1':
        raise ValueError('support_rules requires version patent_support_v1 and rules')
    rules=contract['rules']
    if not isinstance(rules,list) or len(rules)>32:raise ValueError('support_rules must contain at most 32 rules')
    target={k:_value(k,v) for k,v in task['target_elements'].items() if v}
    identifiers=set()
    for rule in rules:
        if not isinstance(rule,dict) or set(rule)!={'id','requirements','assertion_pattern','support','reason'}:
            raise ValueError('Each support rule requires id, requirements, assertion_pattern, support, reason')
        if not isinstance(rule['id'],str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',rule['id']) or rule['id'] in identifiers:
            raise ValueError('Support rule ids must be short and unique')
        identifiers.add(rule['id'])
        requirements=rule['requirements']
        if not isinstance(requirements,dict) or not set(target)<=set(requirements) or not {'subject','action'}<=set(requirements):
            raise ValueError('Support rule must cover every target element and bind subject/action')
        if any(k not in ELEMENTS or not isinstance(v,str) or not v.strip() or len(v)>300 for k,v in requirements.items()):
            raise ValueError('Invalid support rule element requirement')
        if any(k!='action' and _canonical(k,requirements[k],task)!=v for k,v in target.items()):
            raise ValueError('Support rule cannot infer direction from a different identity or time')
        if not isinstance(rule['reason'],str) or not 1<=len(rule['reason'].strip())<=1000:
            raise ValueError('Support rule requires a bounded audit reason')
        support=rule['support']
        if not isinstance(support,dict) or set(support)!=set(task['outcomes']) or any(type(v) is not int or v not in (-1,0,1) for v in support.values()):
            raise ValueError('Support rule requires one -1/0/1 integer per outcome')
        if len(set(support.values()))==1 and any(support.values()):
            raise ValueError('Exclusive binary outcomes cannot share nonzero direction')
        pattern=rule['assertion_pattern']
        if not isinstance(pattern,str) or not 1<=len(pattern)<=2000:
            raise ValueError('Support assertion pattern must be bounded')
        try:compiled=re.compile(pattern,re.I)
        except re.error as error:raise ValueError('Invalid support assertion pattern') from error
        if set(compiled.groupindex)!=set(requirements):
            raise ValueError('Support assertion must bind exactly every required element as a named group')
    return deepcopy(rules)


def _support(elements,task,quote,text,annotation,rules):
    outcomes=task['outcomes'];evaluations=[];vectors=[];matched_ids=[]
    blockers=[]
    if task['_patent_task_parse']['status']=='unsupported':blockers.append('unsupported_task')
    if annotation and annotation.get('factual_status','asserted') not in ('asserted','reported'):
        blockers.append('annotation_not_asserted_or_reported')
    if annotation and annotation.get('time_scope') in ('unknown','historical_other_cycle'):
        blockers.append('annotation_temporal_compatibility_unresolved')
    if MARKET_ODDS.search(quote):blockers.append('market_derived_claim')
    # Full source context may qualify or retract a cherry-picked quotation.
    # Conservative abstention is deliberate: this lexical checker cannot safely
    # resolve which event a denial refers to, and never converts it into No.
    if _CONFLICT.search(quote):blockers.append('quote_contains_negation_or_conflict')
    if _CONFLICT.search(text):blockers.append('source_contains_negation_or_conflict')
    # Check even zero-support model extraction before deriving new direction.
    # A year/month describes an interval, not an exact instant. Reject intervals
    # wholly after cutoff; an interval spanning cutoff is not itself a future claim.
    event_time=elements.get('time','')
    timing=dict(status='not_present',event_time=event_time,cutoff=task.get('cutoff'),
        publication_time_substituted=False)
    if event_time:
        from .matching_v4 import date_interval
        try:
            cutoff=datetime.fromisoformat(str(task.get('cutoff','')).replace('Z','+00:00'))
            if cutoff.tzinfo is None:raise ValueError('Cutoff needs timezone')
            if re.match(r'^\d{4}-\d{2}-\d{2}t',event_time,re.I):
                instant=datetime.fromisoformat(event_time.upper().replace('Z','+00:00'))
                if instant.tzinfo is None:raise ValueError('Event timestamp needs timezone')
                future=instant>cutoff
                timing.update(granularity='timestamp',event_interval=[instant.isoformat(),instant.isoformat()])
            else:
                interval=date_interval(event_time)
                if interval is None:raise ValueError('Unresolved event-time interval')
                future=interval[0]>cutoff.date()
                timing.update(granularity='calendar_interval',event_interval=[day.isoformat() for day in interval])
            timing['status']='after_cutoff' if future else 'not_wholly_after_cutoff'
            if future:blockers.append('event_after_cutoff')
        except (ValueError,TypeError,OverflowError):
            timing['status']='unresolved'
            blockers.append('event_time_or_cutoff_unresolved')
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+',quote) if s.strip()]
    original_sentences={s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+',text) if s.strip()}
    for rule in rules:
        reasons=list(blockers);witness=None
        requirements={k:_canonical(k,v,task) for k,v in rule['requirements'].items()}
        if any(elements.get(k)!=v for k,v in requirements.items()):reasons.append('missing_or_incompatible_required_elements')
        for sentence in sentences:
            if len(sentence)>4000 or sentence not in original_sentences:continue
            # Month May is a date, not the modal verb may.
            if _UNCERTAIN.search(_DATE.sub('',sentence)):continue
            match=re.fullmatch(rule['assertion_pattern'],sentence,re.I)
            if match and all(match.group(k) is not None and _canonical(k,match.group(k),task)==v for k,v in requirements.items()):
                witness=sentence;break
        if witness is None:reasons.append('complete_assertion_not_grounded')
        accepted=not reasons
        evaluations.append(dict(rule_id=rule['id'],requirements=requirements,reason=rule['reason'],
            assertion_pattern=rule['assertion_pattern'],configured_support=rule['support'],
            matched=accepted,blockers=reasons,assertion_witness=witness,
            assertion_source_scope='complete_original_title_or_body_sentence'))
        if accepted:
            matched_ids.append(rule['id']);vectors.append(tuple(rule['support'][o] for o in outcomes))
    unique=set(vectors)
    final=list(next(iter(unique))) if len(unique)==1 else [0]*len(outcomes)
    return final,dict(rule_table_version='patent_support_v1',contract_source='task.support_rules' if 'support_rules' in task else 'closed_question_template',
        matched_rule_ids=matched_ids,rules=evaluations,blockers=blockers,time_check=timing,
        resolution='conflicting_rules_abstain' if len(unique)>1 else 'matched' if unique else 'no_unambiguous_rule_abstain',
        original_model_support_used=False,reviewed=False)


def evaluate(elements,task,*,quote,text,original_support,annotation=None):
    rules=validate_support_rules(task)
    original_target=deepcopy(task['target_elements'])
    task=effective_task(task)
    effective={};witnesses={};removed={}
    for key,value in elements.items():
        if not value:continue
        witnesses[key]=_witnesses(key,value,task,text)
        if witnesses[key]:effective[key]=_canonical(key,value,task)
        else:removed[key]='no_original_text_witness'
    target={k:_value(k,v) for k,v in task['target_elements'].items() if v}
    matched=[k for k,v in target.items() if effective.get(k)==v]
    score=len(matched)/len(target)
    support,support_trace=_support(effective,task,quote,text,annotation,rules)
    trace=dict(policy=POLICY,original_target=original_target,effective_target=target,task_parse=task['_patent_task_parse'],raw_elements=deepcopy(elements),original_support=list(original_support),
        effective_elements=deepcopy(effective),normalization=dict(witnesses=witnesses,removed=removed,
            publication_time_substituted=False,alias_source='explicit_task_element_aliases'),
        overlap=dict(target=target,matched=matched,matched_count=len(matched),target_count=len(target),relevance=score,semantic_gate_applied=False),
        support=support_trace,fact_group=dict(key=list(fact_key(effective)),policy='exact_normalized_five_elements',
            fuzzy_merge=False,weighting='gamma ** chronological_rank'))
    return effective,score,support,trace
