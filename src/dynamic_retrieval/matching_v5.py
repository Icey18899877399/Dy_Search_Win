"""Versioned task contracts and conservative evidence-relation checks.

Comparison-only: never mutates the frozen task, annotation or outcome support.
Supported templates are explicit; unsupported tasks abstain.
"""
from copy import deepcopy
from datetime import date
import re
from .matching_v4 import date_interval, same_entity

def clean(s):
    return ' '.join(re.findall(r'\w+',str(s).casefold()))

def normalize(task):
    from .matching_v4 import normalize as old_normalize
    t=deepcopy(task);q=t['question'].strip().rstrip('?');stem=re.sub(r'^will\s+','',q,flags=re.I)
    target={};kind=None;conditions=[]
    patterns=[
        (r'US announces end of Iranian blockade by (.+)','blockade_announcement',{'subject':'US','action':'announce_termination','object':'naval blockade of Iran'}),
        (r'(?:there be no change in|no change in) Fed interest rates after the (.+?) meeting','rate_decision',{'subject':'Federal Reserve','action':'maintain_rate','object':'federal funds rate'}),
        (r'Bab el-Mandeb Strait effectively closed by (.+)','strait_closure',{'subject':'Bab el-Mandeb Strait','action':'close'}),
        (r'Iran agrees? to surrender enriched uranium stockpile by (.+)','uranium_agreement',{'subject':'Iran','action':'agree_surrender','object':'enriched uranium stockpile'}),
        (r'(Trump) be impeached by (.+)','impeachment',None),
        (r'Billionaire one-time wealth tax passes in California election (20\d{2})','wealth_tax',{'subject':'billionaire one-time wealth tax','action':'pass','location':'California'}),
        (r'Israel closes its airspace by (.+)','airspace_closure',{'subject':'Israel','action':'close','object':'airspace'}),
        (r'Russia test a nuclear weapon by (.+)','nuclear_test',{'subject':'Russia','action':'test','object':'nuclear weapon'}),
        (r'Reza Pahlavi lead Iran in (20\d{2})','leadership',{'subject':'Reza Pahlavi','action':'lead','object':'Iran'}),
    ]
    for pattern,label,elements in patterns:
        m=re.fullmatch(pattern,stem,re.I)
        if m:
            kind=label;target=dict(elements or {'subject':m[1],'action':'impeach'})
            target['time']=m.groups()[-1];break
    if kind is None:
        legacy=old_normalize(t);target=legacy['target_elements']
        supported=bool(target.get('action')) and clean(target.get('action')) not in ('be','end') and not legacy.get('matching_warnings')
        kind='legacy_typed' if supported else 'unsupported'
    if kind=='strait_closure':conditions=['IMF PortWatch 7-day moving average transit calls <= 10; background disruption is not threshold observation']
    if kind=='wealth_tax':conditions=['one-time tax threshold at least USD 1 billion','qualifying ballot certification','passage in named California election']
    if kind=='impeachment':conditions=['House approval; filing articles is only a procedural step']
    if kind=='blockade_announcement':conditions=['authorized official public announcement of a decided termination/suspension; current enforcement is background']
    if kind=='airspace_closure':conditions=['major general closure by Israel; isolated airline cancellation is insufficient']
    if kind=='uranium_agreement':conditions=['public Iranian agreement to surrender; conflicting anonymous reports are not agreement']
    t.update(target_elements=target,matching_policy='typed_v5',task_extraction='typed_question_v5',
        task_parse=dict(status='unsupported' if kind=='unsupported' else 'supported_template',kind=kind,conditions=conditions),
        matching_warnings=['Unsupported task; no evidence admission'] if kind=='unsupported' else [])
    return t

def event_interval(value):
    s=str(value).strip()
    # Distinguish an observed qualification date from a later planned election.
    s=s.split(';')[0]
    s=re.sub(r'^(?:certified|announced|reported|on)\s+','',s,flags=re.I)
    s=re.sub(r',?\s+(?:ahead of|before)\s+.*$','',s,flags=re.I)
    m=re.fullmatch(r'([A-Za-z]+)\s+(\d{1,2})[–-](\d{1,2}),?\s+(20\d{2})',s)
    if m:
        a=date_interval(f'{m[1]} {m[2]}, {m[4]}');b=date_interval(f'{m[1]} {m[3]}, {m[4]}')
        return (a[0],b[1]) if a and b and a[0]<=b[1] else None
    return date_interval(s)

def time_check(actual,target,task):
    cutoff=date.fromisoformat(task['cutoff'][:10]);interval=event_interval(actual)
    bound=date_interval(target,cutoff.year);end=min(cutoff,bound[1]) if bound else cutoff
    start=date(cutoff.year,1,1)
    result=dict(status='unknown',lower=start.isoformat(),upper=end.isoformat(),
        scope='current_year_observed_context_not_resolution_proof',publication_time_substituted=False,
        target_year_assumed=not bool(re.search(r'20\d{2}',str(target))))
    if interval:
        result['event_interval']=[x.isoformat() for x in interval]
        result['status']='outside' if interval[0]>end or interval[1]<start else 'within' if interval[0]>=start and interval[1]<=end else 'overlap_unknown'
    return result

def evaluate(elements,task,*,quote='',context='',rationale=''):
    t=normalize(task);target=t['target_elements'];kind=t['task_parse']['kind']
    blockers=[];matched=[];reasons={};relation='unresolved';legacy_timing=None
    pos=context.find(quote) if quote else -1
    local=context[max(0,pos-750):pos+len(quote)+750] if pos>=0 else context
    raw=clean(quote);ctx=clean(local);a=clean(elements.get('action',''));obj=clean(elements.get('object',''));subject=elements.get('subject','')
    def mark(k,why):
        if k in target and k not in matched:matched.append(k)
        reasons[k]=why
    def topic(pattern):return bool(re.search(pattern,ctx))
    if kind=='unsupported':blockers.append('unsupported_task')
    source_actors={'nuclear_test':r'\brussia(?:n)?\b','leadership':r'\bpahlavi\b',
        'rate_decision':r'\b(?:fed|federal reserve|policymakers)\b',
        'blockade_announcement':r'\b(?:us|u s|united states)\b','airspace_closure':r'\bisrael(?:i)?\b'}
    if kind in source_actors and not re.search(source_actors[kind],raw):blockers.append('actor_not_grounded')
    # This audits the source of a directional argument, not every occurrence of modal language.
    if re.search(r'\b(?:are|is) likely\b|\bexpected to\b|\bforecast(?:s|ed)?\b',raw) or re.search(r'\btraders?\b.{0,60}\bbets?\b|\bodds\b|\bimplied probability\b',clean(rationale)):
        blockers.append('forecast_or_market_basis')
    if re.search(r'\b(?:disputed|denied|inconsistent with reality)\b',clean(rationale)) and re.search(r'\b(?:agreed|accepted|agreement|surrender)\b',raw):
        blockers.append('conflicting_claims')
    if kind=='strait_closure':
        named=bool(re.search(r'\bbab (?:el mandeb|al mandab)\b',raw))
        if not named and re.search(r'\bhormuz\b|\bsoh\b',ctx):blockers.append('place_coreference_conflict')
        if not named and not re.search(r'\bbab (?:el mandeb|al mandab)\b',ctx):blockers.append('target_not_grounded')
        if re.search(r'\bbab (?:el mandeb|al mandab)\b',ctx):mark('subject','explicit_target_waterway_in_source_context')
        if re.search(r'\b(?:disrupt\w*|closed|closure|blockade|attacks?|attacked|threatened)\b',a+' '+raw):
            mark('action','related_shipping_event')
            relation='declaration_or_threat' if re.search(r'\b(?:declared|threatened)\b',raw) else 'reported_attack' if re.search(r'\battack\w*\b',raw) else 'disruption_context'
    elif kind=='uranium_agreement':
        if not re.search(r'\biran(?:ian)?\b',raw):blockers.append('actor_not_grounded')
        if not re.search(r'\b(?:agree\w*|accepted|refus\w*)\b',raw):blockers.append('claim_relation_not_grounded')
        if same_entity(subject,'Iran','agree'):mark('subject','exact_actor')
        if 'uranium' in obj and topic(r'\burani\w*\b'):mark('object','explicit_uranium_stockpile_topic')
        if re.search(r'\b(?:agree\w*|accepted|refus\w*)\b',a) and re.search(r'\b(?:surrender|relinquish|give up|handover)\b',a+' '+obj):
            mark('action','agreement_or_opposition_same_transfer_topic');relation='opposing_state' if re.search(r'\b(?:not|refus\w*)\b',a) else 'agreement_statement'
    elif kind=='blockade_announcement':
        if same_entity(subject,'US','announce'):mark('subject','closed_us_identity')
        if topic(r'\bblockade\b') and topic(r'\biran\w*\b'):
            mark('object','explicit_iran_blockade_topic')
            if re.search(r'\b(?:maintain\w*|enforc\w*|remain\w*)\b',a+' '+raw):mark('action','opposing_execution_state');relation='opposing_state'
            elif re.search(r'\b(?:lift\w*|terminat\w*|suspend\w*|end\w*)\b',a+' '+raw):mark('action','termination_statement');relation='termination_statement'
    elif kind=='wealth_tax':
        wealth=topic(r'\b(?:billionaire|billionaires)\b') and topic(r'\b(?:tax|levy)\b')
        if wealth:mark('subject','explicit_billionaire_tax_identity_in_context')
        if clean(elements.get('location',''))=='california' and topic(r'\bcalifornia\b'):mark('location','explicit_california_scope')
        if re.search(r'\b(?:certif\w*|on the ballot)\b',a+' '+raw):mark('action','ballot_qualification');relation='qualification_step'
        elif re.search(r'\b(?:endors\w*|support)\b',a+' '+ctx):mark('action','endorsement_background');relation='endorsement_context'
        elif re.search(r'\b(?:passed|approved)\b',a+' '+raw):mark('action','passage_statement');relation='passage_statement'
    elif kind=='impeachment':
        if re.search(r'\btrump\b',clean(subject)+' '+obj) and topic(r'\btrump\b'):mark('subject','patient_role_trump')
        if re.search(r'\bimpeach\w*\b',a+' '+obj) and topic(r'\bimpeach\w*\b'):
            mark('action','impeachment_process_relation');relation='procedural_step' if re.search(r'\bfile\w*\b',a+' '+raw) else 'impeachment_statement'
    elif kind=='airspace_closure':
        if same_entity(subject,'Israel','close'):mark('subject','exact_actor')
        if topic(r'\b(?:israeli|israel)\b') and topic(r'\bairspace\b'):
            mark('object','airspace_explicit_in_action_or_context')
            if re.search(r'\b(?:close\w*|closure)\b',a+' '+raw):mark('action','closure_nominalization');relation='closure_statement'
        if not re.search(r'\b(?:all civilian|all commercial|entire|nationwide|majority)\b',ctx):blockers.append('closure_scope_unverified')
    elif kind in ('nuclear_test','leadership','rate_decision'):
        aliases={'nuclear_test':['Russia'],'leadership':['Reza Pahlavi'],'rate_decision':['Federal Reserve','Federal Reserve policymakers','Fed']}
        if any(same_entity(subject,x,target['action']) for x in aliases[kind]):mark('subject','closed_target_identity')
        if kind=='nuclear_test' and re.search(r'\bnuclear\b',obj) and topic(r'\bnuclear\b'):
            mark('object','nuclear_weapon_topic')
            if re.search(r'\btest\w*\b',a):mark('action','test_inflection');relation='test_statement'
        if kind=='leadership' and obj=='iran' and topic(r'\biran\b'):
            mark('object','exact_country')
            if re.search(r'\b(?:lead|leads|led|leader)\b',a):mark('action','leadership_statement');relation='leadership_statement'
        if kind=='rate_decision' and re.search(r'\b(?:rate|rates)\b',obj) and topic(r'\b(?:rate|rates)\b'):
            mark('object','policy_rate_topic')
            if re.search(r'\b(?:unchanged|maintain\w*|held|hold)\b',a):mark('action','rate_maintenance');relation='rate_decision_statement'
    elif kind=='legacy_typed':
        from .matching_v4 import relevance
        _,old=relevance(elements,task)
        legacy_timing=old['time_check']
        matched.extend(x for x in old['matched'] if x!='time');reasons.update(old['reasons'])
        blockers.extend(x for x in old['blockers'] if x!='event_time_outside_interval');relation=old['relation']
    for key in target:
        if key!='time' and key not in matched:blockers.append(key+'_unresolved_or_mismatch')
    timing=legacy_timing or time_check(elements.get('time',''),target.get('time',''),t)
    if timing['status'] in ('within','overlap_unknown'):mark('time','observed_interval_intersects_frozen_context')
    else:blockers.append('event_time_'+timing['status'])
    blockers=list(dict.fromkeys(blockers));score=len(matched)/max(1,len(target))
    return (0. if blockers else score),dict(policy='typed_v5',target=target,matched=matched,reasons=reasons,blockers=blockers,
        relation=relation,time_check=timing,comparison_elements=deepcopy(elements),ungated_relevance=score,
        task_parse=t['task_parse'],warnings=t['matching_warnings'],establishes_outcome=False,
        support_policy='frozen_annotation_unchanged_only_admission_gated',audit_scope='bounded_context_checks_not_independent_truth')
