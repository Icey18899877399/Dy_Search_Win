"""Traceable element extraction; unreviewed lexical mode abstains on outcome support.

Reviewed annotations, bound machine annotations or task-specific rules enable support.
This module never consumes market prices or evaluation labels.
"""
import re
from copy import deepcopy
from .core import relevance, ELEMENTS

SPECULATION = re.compile(r'\b(if|could|might|may|would|will|forecast|predict\w*|poll\w*|odds)\b|\?', re.I)


def _contains(text, term):
    return bool(term and re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I))


def prepare_task(task):
    result = deepcopy(task)
    outcomes = result.get('outcomes', ['Yes','No'])
    if len(outcomes) < 2 or len(set(outcomes)) != len(outcomes):
        raise ValueError('At least two distinct outcomes required')
    if len(outcomes)!=2 or {str(x).lower() for x in outcomes} != {'yes','no'}:
        raise ValueError('First release supports one binary Yes/No market per task')
    result['outcomes'] = outcomes
    question = str(result.get('question','')).strip()
    if not question: raise ValueError('Question is required')
    if not result.get('target_elements'):
        stem = re.sub(r'^(will|does|did|is|can|has)\s+', '', question, flags=re.I).rstrip('?')
        verbs = r'win|acquire|invade|visit|fall|confirm|announce|leave|resign|end|be|out'
        match = re.search(r'\b('+verbs+r')\b',stem,re.I)
        if match:
            subject=stem[:match.start()].strip()
            action=match.group(0).lower()
            rest=stem[match.end():].strip()
            obj=re.split(r'\b(?:by|before|after|in|on)\b',rest,flags=re.I)[0].strip()
            obj=re.sub(r'^(the|a|an)\s+','',obj,flags=re.I)
            elements={'subject':subject,'action':action,'object':obj}
        else:
            elements={'subject':stem}
        years=re.findall(r'\b20\d{2}\b',question)
        if years:elements['time']=years[-1]
        result['target_elements']={k:v for k,v in elements.items() if v}
        result['task_extraction']='lexical_question_v1'
    else:
        result['task_extraction']='configured_elements'
    if any(k not in ELEMENTS for k in result['target_elements']):
        raise ValueError('Unknown target element type')
    if not any(result['target_elements'].values()):raise ValueError('Empty target elements')
    result.setdefault('element_aliases',{})
    for name in ('positive_patterns','negative_patterns'):
        for pattern in result.get(name,[]):re.compile(pattern,re.I)
    return result


def evidence_rules(policy):
    """Resolve explicit versions without silently migrating frozen evidence."""
    if policy == 'patent_elements_v1':
        from . import patent_evidence
        return patent_evidence
    if policy == 'patent_elements_v2':
        from . import patent_evidence_v2
        return patent_evidence_v2
    if policy == 'patent_elements_v3':
        from . import patent_evidence_v3
        return patent_evidence_v3
    if policy == 'patent_elements_v4':
        from . import patent_evidence_v4
        return patent_evidence_v4
    raise ValueError('Unknown evidence policy')


def extract(document, task, annotations=None, *, comparison_policy=None, evidence_policy=None):
    if evidence_policy not in (None, "patent_elements_v1", "patent_elements_v2", "patent_elements_v3", "patent_elements_v4"):
        raise ValueError("Unknown evidence policy")
    if evidence_policy is not None and comparison_policy is not None:
        raise ValueError("evidence_policy and comparison_policy are mutually exclusive")
    if evidence_policy is not None:
        evidence_rules(evidence_policy).validate_support_rules(task)
    if comparison_policy not in (None,'typed_v6'):
        raise ValueError('Unknown comparison policy')
    row=deepcopy(document)
    body=str(document.get('text',''))
    text=str(document.get('title',''))+'\n'+body
    annotation=(annotations or {}).get(document['id'])
    machine=False
    if annotation and annotation.get('origin')=='model':
        from .semantic import validate_model_annotation
        annotation=validate_model_annotation(annotation,task,document)
        machine=True
    elif annotation and annotation.get('reviewed') is not True:annotation=None
    if annotation:
        elements=annotation['elements']
        support=annotation['support']
        quote=annotation.get('quote','')
        if not quote or quote not in text:raise ValueError(f"Annotation quote missing from {document['id']}")
        if len(support)!=len(task['outcomes']) or any(type(x) is not int or x not in (-1,0,1) for x in support):
            raise ValueError('Support must contain one -1/0/1 integer per outcome')
        if (not elements and not machine) or any(k not in ELEMENTS or not isinstance(v,str) for k,v in elements.items()):
            raise ValueError('Invalid annotation elements')
        method='model_validated_unreviewed' if machine else 'reviewed_annotation'
    else:
        extraction_task=task
        if evidence_policy is not None:
            extraction_task=evidence_rules(evidence_policy).effective_task(task)
        elements={}
        for key,value in extraction_task['target_elements'].items():
            aliases=[value]+extraction_task['element_aliases'].get(key,[])
            if any(_contains(text,str(alias)) for alias in aliases):elements[key]=value
        # Nonmatching explicit date distinguishes facts, never copies publication time as fact time.
        if 'time' not in elements:
            date=re.search(r'\b20\d{2}-\d{2}-\d{2}\b',text)
            if date:elements['time']=date.group()
        support=[0]*len(task['outcomes']);quote=''
        votes=set()
        for sentence in re.split(r'(?<=[.!?])\s+|\n+',text):
            if SPECULATION.search(sentence):continue
            subject=task['target_elements'].get('subject','')
            if subject and not any(_contains(sentence,a) for a in [subject]+task['element_aliases'].get('subject',[])):
                continue
            for value,key in ((1,'positive_patterns'),(-1,'negative_patterns')):
                if any(re.search(p,sentence,re.I) for p in task.get(key,[])):
                    votes.add(value);quote=sentence[:2000]
        if len(votes)==1:
            vote=next(iter(votes));support=[vote if str(x).lower()=='yes' else -vote for x in task['outcomes']]
        else:quote=text[:800]
        method='configured_rules_v1' if task.get('positive_patterns') or task.get('negative_patterns') else 'lexical_v1'
    row.update(elements={k:str(v).strip().casefold() for k,v in elements.items() if v},
               support=list(support),quote=quote,extraction_method=method,extraction_version='1',
               relevance=relevance(elements,task['target_elements']))
    if evidence_policy is None and task.get('matching_policy') in ('typed_v2','typed_v3','typed_v4'):
        from .matching import typed_relevance
        row['relevance'],row['matching_trace']=typed_relevance(elements,task)
    if evidence_policy is None and task.get('matching_policy')=='typed_v5':
        from .matching_v5 import evaluate
        row['relevance'],row['matching_trace']=evaluate(elements,task,quote=quote,
            context=annotation.get('excerpt',text) if annotation else text,
            rationale=annotation.get('rationale','') if annotation else '')
    if comparison_policy == 'typed_v6':
        from .matching_v6 import evaluate
        row['relevance'],row['matching_trace']=evaluate(elements,task,quote=quote,
            context=annotation.get('excerpt',text) if annotation else text,
            rationale=annotation.get('rationale','') if annotation else '')
    if evidence_policy is not None:
        canonical,score,direction,trace=evidence_rules(evidence_policy).evaluate(elements,task,quote=quote,text=text,
            original_support=support,annotation=annotation)
        row.update(elements=canonical,relevance=score,support=direction,patent_evidence_trace=trace,
                   extraction_version=evidence_policy,
                   matching_trace=dict(policy=evidence_policy,target=trace['effective_target'],
                       matched=trace['overlap']['matched'],task_parse=trace['task_parse'],
                       ungated_relevance=score,blockers=[],semantic_gate_applied=False,
                       support_policy='explicit_compatibility_rules_not_model_direction'))
    if machine:
        row.update(human_reviewed=False,model=annotation['model'],
                   prompt_version=annotation['prompt_version'],
                   factual_status=annotation['factual_status'],time_scope=annotation['time_scope'],
                   rationale=annotation['rationale'],validation_status=annotation['validation_status'])
    return row
