"""Versioned typed matching. Normalize only the comparison view, never raw facts."""
from copy import deepcopy
import re,unicodedata
from .evidence import prepare_task

def text(value):
    return ' '.join(re.findall(r'\w+',unicodedata.normalize('NFKC',str(value)).casefold()))

def normalize_task(task,policy=None):
    if (policy or task.get('matching_policy'))=='typed_v5':
        from .matching_v5 import normalize
        return normalize(task)
    if (policy or task.get('matching_policy'))=='typed_v4':
        from .matching_v4 import normalize
        return normalize(task)
    if (policy or task.get('matching_policy'))=='typed_v3':return _normalize_task_v3(task)
    t=prepare_task(deepcopy(task));q=t['question'].strip().rstrip('?')
    stem=re.sub(r'^will\s+','',q,flags=re.I)
    patterns=[
        (r'(.+?)\s+strikes?\s+(.+?)(?:\s+in\s+(20\d{2}))?$','strike'),
        (r'(.+?)\s+closes?\s+(.+?)\s+by\s+(.+)$','close'),
        (r'(.+?)\s+increases?\s+(.+?)\s+after\s+(.+)$','increase'),
        (r'(.+?)\s+obtains?\s+(.+?)\s+by\s+(.+)$','obtain'),
    ]
    for pattern,action in patterns:
        m=re.fullmatch(pattern,stem,re.I)
        if m:
            subject,obj,when=m.groups()
            t['target_elements']={'subject':subject,'action':action,'object':re.sub(r'^its\s+','',obj,flags=re.I)}
            if when:t['target_elements']['time']=when
            break
    m=re.fullmatch(r'US x Iran (permanent peace deal) by (.+)',stem,re.I)
    if m:t['target_elements']={'subject':'US and Iran','action':'agree','object':m[1],'time':m[2]}
    t['matching_policy']='typed_v2'
    t['task_extraction']='typed_question_v2'
    return t

def canonical_action(value):
    s=text(value)
    # Closed synonym sets; a different event verb must not count as a match.
    if re.search(r'\b(strike|strikes|struck|airstrike|airstrikes)\b',s):return 'strike'
    if re.fullmatch(r'(?:airspace )?(?:remains? |is |was )?(close|closes|closed)(?: to all civilian traffic)?',s):return 'close'
    return {'wins':'win','won':'win','increases':'increase','increased':'increase',
            'obtains':'obtain','obtained':'obtain'}.get(s,s)

def typed_relevance(elements,task):
    if task.get('matching_policy')=='typed_v5':
        from .matching_v5 import evaluate
        return evaluate(elements,task)
    if task.get('matching_policy')=='typed_v4':
        from .matching_v4 import relevance
        return relevance(elements,task)
    target=normalize_task(task)['target_elements']
    matched=[];reasons={}
    for key,value in target.items():
        actual=elements.get(key)
        if not actual:continue
        candidates=[value]+task.get('element_aliases',{}).get(key,[])
        equal=any(text(actual)==text(c) for c in candidates)
        reason='exact_or_declared_alias'
        if not equal and key=='action':
            equal=any(canonical_action(actual)==canonical_action(c) for c in candidates)
            reason='closed_action_synonyms'
        if not equal and key=='time' and re.fullmatch(r'20\d{2}',str(value)):
            years=set(re.findall(r'\b20\d{2}\b',str(actual)))
            equal=years=={str(value)};reason='explicit_single_year'
        if equal:matched.append(key);reasons[key]=reason
    return len(matched)/len(target),dict(policy=task.get('matching_policy','typed_v2'),target=target,matched=matched,reasons=reasons)

NONFACT=re.compile(r'\b(poll(?:s|ing)?|forecast\w*|predict\w*|projected|projection\w*|odds)\b',re.I)
def validate_direction(annotation):
    support=annotation['support']
    if any(support):
        if len(support)==2 and support[0]==support[1]:
            raise ValueError('Same-direction support for mutually exclusive outcomes')
        if NONFACT.search(annotation['quote']+' '+annotation['rationale']):
            raise ValueError('Directional claim relies on a poll or forecast')

def _normalize_task_v3(task):
    t=normalize_task(task,policy='typed_v2')
    q=re.sub(r'^will\s+','',t['question'].strip().rstrip('?'),flags=re.I)
    if 'action' not in t['target_elements']:
        verbs={'gain':'gain','gains':'gain','capture':'capture','captures':'capture',
               'meet':'meet','meets':'meet','recognize':'recognize','recognizes':'recognize',
               'control':'control','controls':'control','withdraw':'withdraw','withdraws':'withdraw',
               'declare':'declare','declares':'declare','agree':'agree','agrees':'agree',
               'change':'change','changes':'change','released':'release','called':'call','held':'hold'}
        pattern=r'(.+?)\s+(?:officially\s+)?('+('|'.join(verbs))+r')(?:\s+(.*))?$'
        m=re.fullmatch(pattern,q,re.I)
        if m:
            subject,verb,rest=m.groups();verb=verb.lower();rest=rest or ''
            temporal=re.search(r'\b(by|before|after)\s+(.+)$',rest,re.I)
            when=temporal[2] if temporal else None
            obj=rest[:temporal.start()].strip() if temporal else rest.strip()
            elements={'action':verbs[verb]}
            if verb in ('released','called','held'):elements['object']=subject
            else:
                elements['subject']=subject
                if obj:elements['object']=obj
            if verbs[verb]=='meet':
                location=re.fullmatch(r'(?:next\s+)?in\s+(.+)',obj,re.I)
                if location:
                    elements.pop('object',None);elements['location']=location[1]
            if when:elements['time']=when
            t['target_elements']=elements
    supported='action' in t['target_elements']
    t['matching_policy']='typed_v3'
    t['task_extraction']='typed_question_v3' if supported else 'unsupported_question_v3'
    t['matching_warnings']=[] if supported else ['Question requires a compound/unsupported task parser; no successful normalization claim.']
    return t
