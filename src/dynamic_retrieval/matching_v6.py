"""Opt-in comparison extension for two explicit task contracts.

This module does not rewrite annotations, support, task bindings or V5. It admits
only dated, reported completed procedural developments; a procedure is not a
resolved outcome. All other task templates retain the exact V5 decision.
"""
from copy import deepcopy
from datetime import date, datetime
import re
from . import matching_v5

_POLICY='typed_v6'
_WEEKDAY=r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+'
_DATE=r'\b(?:\d{4}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b'
_UNCERTAIN=r'\b(?:expected|scheduled|plans?|planned|planning|will|would|could|might|likely|forecast\w*|if|unless|not|never|denied|disputed|alleged\w*)\b'


def _kind(task):
    q=task.get('question','').strip().rstrip('?').strip()
    if re.fullmatch(r'(?:Will )?Israeli parliament (?:be )?dissolved by July 31(?:,? 2026)?',q,re.I):
        return 'knesset_dissolution'
    if re.fullmatch(r'Will Kevin Warsh be confirmed as Fed Chair',q,re.I):
        return 'warsh_confirmation'
    return None


def normalize(task):
    kind=_kind(task)
    if kind is None:return matching_v5.normalize(task)
    t=deepcopy(task)
    if kind=='knesset_dissolution':
        target={'subject':'Israeli parliament','action':'dissolve','time':'July 31'}
        conditions=['Completed proposal submission or preliminary approval is procedural context only.',
                    'Final dissolution requires later legal stages and is not inferred from a proposal or preliminary reading.']
    else:
        target={'subject':'Kevin Warsh','action':'confirm','object':'Federal Reserve Chair','time':task['cutoff'][:10]}
        conditions=['Completed Senate Banking Committee action is a procedural step, not full Senate confirmation.',
                    'Scheduled votes, announced intentions and expected confirmation do not establish completed stages.']
    t.update(target_elements=target,matching_policy=_POLICY,task_extraction='bounded_procedural_question_v6',
             task_parse={'status':'supported_template','kind':kind,'conditions':conditions},matching_warnings=[])
    return t


def _day(value):
    value=re.sub(_WEEKDAY,'',str(value).strip(),flags=re.I)
    if not re.fullmatch(_DATE,value,re.I):return None
    for fmt in ('%Y-%m-%d','%B %d, %Y','%B %d %Y','%d %B %Y'):
        try:return datetime.strptime(value,fmt).date()
        except ValueError:pass
    return None


def _stage_info(kind, text):
    """Return the completed relation span with its actor, patient and office bound."""
    s=matching_v5.clean(text)
    parliament=r'(?:knesset|israeli parliament|israel s parliament)'
    patient=r'(?:the )?(?:knesset|israeli parliament|parliament)'
    if kind=='knesset_dissolution':
        patterns=[
            ('preliminary_approval',r'\b(?:the )?'+parliament+r' (?:has )?(?:given|gave) initial approval to a bill (?:seeking )?to dissolve '+patient+r'\b'),
            ('preliminary_approval',r'\b(?:the )?(?:knesset dissolution bill|bill to dissolve (?:the )?'+parliament+r') (?:was )?passed in (?:the )?preliminary (?:vote|reading)\b'),
            ('proposal_submission',r'\b(?:the )?(?:likud(?: party(?: of prime minister benjamin netanyahu)?)?|(?:israel s |israeli )?ruling coalition|(?:netanyahu s|netanyahu led) coalition) (?:submitted|has submitted) a (?:proposal|bill) to dissolve (?:the )?(?:israeli parliament|knesset)\b'),
        ]
    else:
        patterns=[
            ('committee_approval',r'\b(?:the )?senate banking committee (?:has )?(?:approved|advanced) (?:kevin )?warsh(?: s)? nomination as (?:federal reserve|fed) (?:chair|chairman)\b'),
            ('full_senate_confirmation_statement',r'\b(?:the )?(?:full|u s|united states) senate (?:has )?confirmed (?:kevin )?warsh as (?:federal reserve|fed) (?:chair|chairman)\b'),
        ]
    matches=[(stage,m) for stage,pattern in patterns for m in re.finditer(pattern,s)]
    return matches[0] if len(matches)==1 else (None,None)


def _stage(kind,text):
    return _stage_info(kind,text)[0]


def _date_witnesses(kind, statement, actual):
    """Date attaches to this exact completed clause, not another event in its sentence."""
    stage,match=_stage_info(kind,statement)
    if not stage:return []
    normalized=matching_v5.clean(statement)
    prefix=normalized[:match.start()].strip()
    suffix=normalized[match.end():].strip()
    witnesses=[]
    for raw in re.findall(_DATE,statement,re.I):
        if _day(raw)!=actual:continue
        normalized_date=re.escape(matching_v5.clean(raw))
        # Closed leading 'On DATE, [actor completed relation]' or direct trailing
        # '[complete relation] on [weekday,] DATE'. Article datelines do not qualify.
        leading=bool(re.fullmatch(r'on '+normalized_date,prefix))
        trailing=bool(re.match(r'^on (?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday) )?'+normalized_date+r'(?:\b|$)',suffix))
        if leading or trailing:witnesses.append(raw)
    return witnesses

def evaluate(elements,task,*,quote='',context='',rationale=''):
    kind=_kind(task)
    if kind is None:return matching_v5.evaluate(elements,task,quote=quote,context=context,rationale=rationale)
    t=normalize(task);blockers=[];target=t['target_elements'];matched=[];reasons={}
    bound=bool(quote.strip()) and quote in context
    if not bound:blockers.append('quote_not_grounded_in_frozen_excerpt')
    # A date in an article header or a different sentence cannot ground this fact.
    sentences=[s for s in re.split(r'(?<=[.!?])\s+|\n+',quote) if s.strip()]
    candidates=[(s,_stage(kind,s)) for s in sentences if _stage(kind,s)]
    stage=candidates[0][1] if len(candidates)==1 else None
    if len(candidates)>1:blockers.append('multiple_procedural_statements_ambiguous')
    if not stage:blockers.append('completed_target_procedure_not_grounded')
    no_dates=re.sub(_DATE,'',quote,flags=re.I)
    if re.search(_UNCERTAIN,no_dates,re.I) or re.search(r'\bmay\b',no_dates,re.I):
        blockers.append('speculative_conditional_or_negated_statement')
    if re.search(r'\b(?:conflicting|denied|disputed|inconsistent with reality)\b',rationale,re.I):
        blockers.append('conflicting_claims')
    actual=_day(elements.get('time',''))
    cutoff=date.fromisoformat(task['cutoff'][:10])
    upper=min(cutoff,date(cutoff.year,7,31)) if kind=='knesset_dissolution' else cutoff
    lower=date(cutoff.year,1,1)
    date_witnesses=[]
    if stage and actual:
        date_witnesses=_date_witnesses(kind,candidates[0][0],actual)
    if actual is None:blockers.append('event_time_unknown')
    elif actual<lower or actual>upper:blockers.append('event_time_outside')
    if not date_witnesses:blockers.append('event_date_not_grounded_in_event_statement')
    # Elements with explicit contradictory lexical status are never repaired from quote.
    if re.search(r'\b(?:reject\w*|denied|not|failed|refus\w*)\b',str(elements.get('action','')),re.I):
        blockers.append('annotation_action_conflicts_with_completed_stage')
    if stage:
        for key in target:
            if key=='time':continue
            matched.append(key);reasons[key]='closed_actor_role_and_completed_procedural_stage_in_quote'
    if date_witnesses and actual and lower<=actual<=upper:
        matched.append('time');reasons['time']='exact_annotation_date_in_same_bound_event_statement'
    blockers=list(dict.fromkeys(blockers))
    score=len(matched)/len(target)
    trace=dict(policy=_POLICY,target=target,matched=matched,reasons=reasons,blockers=blockers,
        relation='procedural_step' if stage in ('preliminary_approval','proposal_submission','committee_approval') else 'confirmation_statement' if stage else 'unresolved',
        stage=stage,time_check=dict(status='within' if actual and lower<=actual<=upper and date_witnesses else 'unknown' if actual is None or not date_witnesses else 'outside',
            lower=lower.isoformat(),upper=upper.isoformat(),event_interval=[actual.isoformat(),actual.isoformat()] if actual else None,
            date_witnesses=date_witnesses,publication_time_substituted=False,date_scope='direct_leading_or_trailing_date_on_completed_relation'),
        comparison_elements=deepcopy(elements),ungated_relevance=score,task_parse=t['task_parse'],warnings=[],
        establishes_outcome=False,support_policy='frozen_annotation_unchanged_only_admission_gated',
        evidence_strength='weak_procedural_context_not_settlement_proof',audit_scope='two_development_templates_not_independent_truth')
    return (0. if blockers else score),trace


