"""Opt-in bounded cross-sentence grounding; exact overlap and fact keys unchanged.

Only adjacent explicit anaphora can extend an assertion. The model's direction
is never accepted as a rule result. Reporting a response is not a mutual pact.
"""
from copy import deepcopy
import re
from . import patent_evidence_v2 as v2
from .core import fact_key

POLICY='patent_elements_v3'
effective_task=v2.effective_task
validate_support_rules=v2.validate_support_rules
MAX_LINKED_SENTENCES=4
MAX_LINKED_CHARS=2400
NEGATED=re.compile(r"\b(?:not|never|no|neither|nor|without|reject(?:ed|s)?|den(?:y|ies|ied))\b|\b\w+n['’]t\b",re.I)


def _w(text,a,b):
 return dict(text=text[a:b],start=a,end=b,scope='original_title_and_body')


def _linked(text,anchor,c,lo,hi):
 rows=[(s,a,b) for s,a,b in v2._sentences(text) if a>=lo and b<=hi]
 index=next((i for i,(_,a,b) in enumerate(rows) if a<=anchor['start']<b),None)
 if index is None:return []
 result=[_w(text,anchor['start'],anchor['end'])]
 prefix=r'^[\s"“]*(?:(?:This|The)\s+(?:ceasefire|truce|agreement)|Both\s+(?:sides|countries))\b'
 if c['kind']=='knesset_dissolution':prefix=r'^[\s"“]*(?:(?:This|The)\s+(?:bill|dissolution bill)|It)\b'
 for s,a,b in rows[index+1:index+MAX_LINKED_SENTENCES]:
  # Stop at the first unrelated sentence: never leap across another event.
  if not re.search(prefix,s,re.I) or b-anchor['start']>MAX_LINKED_CHARS:break
  if c['kind']=='bilateral_ceasefire' and not re.search(r'^[\s"“]*(?:(?:This|The)\s+(?:ceasefire|truce|agreement)\s+(?:wasn.t|isn.t|never|not|rejected|denied|was|is|covers|has|had|does|will|would|may|might|could)|Both\s+(?:sides|countries)\s+(?:mutually|agreed|signed|never|rejected|denied|didn.t|have|had|did|may|might|could))\b',s,re.I):break
  if re.search(r'\b(?:by|between|with)\s+[A-Z][a-z]+\s+and\s+[A-Z]',s) and not all(v2._has_entity(s,p) for p in c['participants']):break
  if re.search(r'\b(?:another|different|previous|last year|earlier)\b',s,re.I):break
  if re.search(r'\bbetween\s+',s,re.I) and not all(v2._has_entity(s,p) for p in c['participants']):break
  result.append(_w(text,a,b))
 return result


def _reported_parties(text,anchor,c,e,w,info):
 s=anchor['text'];a=anchor['start']
 if c['kind']!='bilateral_ceasefire':return False
 if v2.CONFLICT.search(s) or NEGATED.search(s):return False
 # Explicit grammatical pair, including reversed target order. No co-occurrence.
 p1,p2=map(v2._entity_pattern,c['participants'])
 pair=re.search(r'(?P<one>'+p1+r')\s+and\s+(?P<two>'+p2+r')\s+(?:will\s+cease\s+fire|agree\s+to\s+(?:(?:a|an|the|Orthodox|Easter|general|comprehensive)\s+){0,4}(?:ceasefire|truce)\b)',s,re.I)
 reverse=False
 if not pair:
  pair=re.search(r'(?P<one>'+p2+r')\s+and\s+(?P<two>'+p1+r')\s+(?:will\s+cease\s+fire|agree\s+to\s+(?:(?:a|an|the|Orthodox|Easter|general|comprehensive)\s+){0,4}(?:ceasefire|truce)\b)',s,re.I);reverse=True
 if pair:
  for key,value,group in [('subject',c['participants'][0],'two' if reverse else 'one'),('object',c['participants'][1],'one' if reverse else 'two')]:
   x,y=pair.span(group);e[key]=value;w[key]=[_w(text,a+x,a+y)]
  e['action']='ceasefire announced intent';w['action']=[_w(text,a+pair.start(),a+pair.end())]
  info.update(complete=False,stage='reported_intent');return True
 if c['participants']!=['russia','ukraine']:return False
 # National role and counterpart are explicit in this same reported assertion.
 m=re.search(r'(?P<one>Russian President\s+[A-Z][\w-]+\s+[A-Z][\w-]+)[^.!?;]{0,100}\bannounced\b[^.!?;]{0,90}\bceasefire\b[^.!?;]{0,140}\band\s+his\s+(?P<two>Ukrainian counterpart\s+[A-Z][\w-]+\s+[A-Z][\w-]+)\s+said\s+Kyiv\s+would\s+abide\s+by\s+the\s+measure\b',s)
 if not m:return False
 for key,value,group in [('subject','russia','one'),('object','ukraine','two')]:
  x,y=m.span(group);e[key]=value;w[key]=[_w(text,a+x,a+y)]
 e['action']='announce ceasefire with counterpart response';w['action']=[_w(text,a+m.start(),a+m.end())]
 info.update(complete=False,stage='reported_response');return True


def evaluate(elements,task,*,quote,text,original_support,annotation=None):
 text=str(text);c=v2._contract(task)
 # Never expand a model-selected quote beyond the context actually supplied.
 lo,hi=0,len(text)
 if annotation is not None and 'excerpt' in annotation:
  excerpt=annotation['excerpt'];lo=text.find(excerpt) if isinstance(excerpt,str) and excerpt else -1
  if lo<0:raise ValueError('Source excerpt not bound to original')
  hi=lo+len(excerpt)
 q=str(quote).strip();pos=text.find(q,lo,hi) if q else -1
 if pos<0:
  e,r,s,tr=v2.evaluate({},task,quote='',text=text,original_support=[0]*len(task['outcomes']),annotation=annotation)
  tr['policy']=POLICY;tr['normalization']['linked_sentences']=[];tr['support']['blockers'].append('quote_outside_supplied_context')
  return e,r,s,tr
 visible_text=' '*lo+text[lo:hi]+' '*(len(text)-hi)
 incomplete=any(a<lo or b>hi for _,a,b in v2._sentences(text) if b>pos and a<pos+len(q))
 if incomplete:
  e,r,s,tr=v2.evaluate({},task,quote='',text=text,original_support=[0]*len(task['outcomes']),annotation=annotation)
  tr['policy']=POLICY;tr['normalization'].update(linked_sentences=[],context_read_span=[lo,hi]);tr['support']['blockers'].append('incomplete_original_sentence_in_context');return e,r,s,tr
 old=v2.evaluate(elements,task,quote=quote,text=visible_text,original_support=original_support,annotation=annotation)
 if c['fallback_v1'] or c['kind']=='publisher_monthly_count':
  e,r,s,tr=old;tr['policy']=POLICY;tr['normalization'].update(linked_sentences=[],context_read_span=[lo,hi]);return e,r,s,tr
 # Restrict to body when the quote covers a title and body together.
 start=lo
 newline=text.find('\n',lo,hi)
 if newline>=0 and pos<=newline and pos+len(q)>newline:start=newline+1
 candidates=[]
 for sent,a,b in v2._sentences(text):
  if a<start or b>hi:continue
  if b<=pos or a>=pos+len(q):continue
  anchor=dict(text=sent,start=a,end=b,scope='original_source_sentence',quote_bound=True,quote_span=[pos,pos+len(q)])
  e,w,info=v2._extract(anchor,c,elements)
  reported=_reported_parties(text,anchor,c,e,w,info)
  score=sum(e.get(k)==p for k,p in zip(('subject','object'),c['participants']))
  if not e.get('action'):score=-1
  candidates.append((score,-a,anchor,e,w,info,reported))
 if not candidates:
  e,r,s,tr=v2.evaluate({},task,quote='',text=text,original_support=[0]*len(task['outcomes']),annotation=annotation)
  tr['policy']=POLICY;tr['normalization']['linked_sentences']=[];tr['support']['blockers'].append('no_complete_sentence_in_supplied_context');return e,r,s,tr
 _,_,anchor,e,w,info,reported=max(candidates,key=lambda row:row[:2])
 linked=_linked(text,anchor,c,lo,hi);extra=linked[1:];extra_text=' '.join(x['text'] for x in extra)
 safety=[]
 # If a selected assertion is under anaphoric correction, it is not a positive fact.
 if any(v2.CONFLICT.search(x['text']) or NEGATED.search(x['text']) for x in extra):
  safety.append('linked_claim_conflict')
 if any((v2.UNCERTAIN.search(v2.DATES.sub('',x['text'])) or re.search(r'\bmay\b',v2.DATES.sub('',x['text']),re.I)) for x in extra):safety.append('linked_conditions_uncertain')
 if c['kind']=='knesset_dissolution' and re.search(r'preliminary|still requires|final approval|committee',extra_text,re.I):
  info.update(stage='procedural',complete=False)
  if e.get('action')=='dissolve':
   e['action']='dissolution preliminary';w['action']=[linked[0]]+extra
 # Dates are attached to an explicit signing assertion, never a publication line.
 dates=[]
 if c['kind']=='bilateral_ceasefire':
  for row in extra:
   m=re.search(r'^(?:This|The)\s+(?:agreement|ceasefire agreement)\s+was\s+(?:signed|announced|reached)\s+on\s+('+v2.DATE_PATTERN+r')[."”]*\s*$',row['text'],re.I)
   if m:
    d=v2._date(m[1]);stamp=v2._instant(m[1])
    if d or stamp:dates.append((stamp.isoformat() if stamp else d.isoformat(),_w(text,row['start']+m.start(1),row['start']+m.end(1))))
 if dates:
  values={d for d,_ in dates}|({e['time']} if e.get('time') else set())
  if len(values)>1:safety.append('linked_event_dates_conflict')
  elif not e.get('time'):e['time']=dates[0][0];w['time']=[x for _,x in dates]
 rules=validate_support_rules(task)
 visible_text=' '*lo+text[lo:hi]+' '*(len(text)-hi)
 support,st=v2._support(e,c,task,anchor,info,visible_text,annotation,rules)
 blockers=list(st['blockers'])+safety
 facets={}
 if c['kind']=='bilateral_ceasefire' and not reported:
  # Positive conditions require complete, narrowly bound source predicates.
  mutual=r'Both (?:sides|countries) (?:mutually )?(?:agreed to|signed) (?:this|the) (?:(?:general|comprehensive) )?(?:ceasefire|truce|agreement)'
  scope=r'(?:This|The) (?:ceasefire|truce|agreement) (?:covers all military (?:operations|engagement)|halts all military operations|is a (?:general|comprehensive) halt|was a (?:general|comprehensive) halt)'
  official=r'(?:This|The) (?:ceasefire|truce|agreement) was (?:publicly|officially) announced'
  patterns={'mutual_agreement_unestablished':mutual,'general_halt_unestablished':scope,'public_official_agreement_unestablished':official}
  for blocker,pattern in patterns.items():
   hits=[row for row in extra if re.fullmatch(pattern+r'[.\"”]*',row['text'].strip(),re.I)]
   if blocker=='general_halt_unestablished':
    hits += [row for row in extra if re.fullmatch(mutual+r'[.\"”]*',row['text'].strip(),re.I) and re.search(r' (?:general|comprehensive) (?:ceasefire|truce|agreement)',row['text'],re.I)]
   if hits:facets[blocker]=hits;blockers=[b for b in blockers if b!=blocker]
  if re.search(r'\b(?:humanitarian|energy infrastructure|Black Sea|informal)\b',extra_text,re.I):blockers.append('excluded_ceasefire_scope')
 if reported:blockers.append('reported_response_or_intent_not_formal_agreement')
 blockers=list(dict.fromkeys(blockers))
 # V2 retains all temporal, actual-party, completed-assertion and task checks.
 direction=0 if blockers else -1 if info.get('explicit_negative') else 1
 support=[direction if v2._clean(o)=='yes' else -direction for o in task['outcomes']]
 if safety and e.get('action'):
  e['action']='unresolved '+e['action'];w['action']=linked
 target=effective_task(task)['target_elements'];matched=[k for k,v in target.items() if e.get(k)==v]
 relevance=len(matched)/len(target) if target else 0.
 st.update(rule_table_version='patent_support_v3',blockers=blockers,linked_condition_witnesses=facets,
  matched_rule_ids=[r['id'] for r in rules if direction and r['support']==dict(zip(task['outcomes'],support))],
  resolution='matched' if direction else 'no_unambiguous_rule_abstain')
 for rule in st['rules']:rule.update(matched=rule['id'] in st['matched_rule_ids'],blockers=blockers,assertion_source_scope='source_bound_adjacent_anaphora')
 tr=deepcopy(old[3]);tr.update(policy=POLICY,effective_elements=e,support=st,
  normalization=dict(witnesses=w,removed={k:'not_source_bound' for k in elements if k not in e},publication_time_substituted=False,
   alias_source='explicit_actor_roles_and_adjacent_anaphora_v3',assertion=anchor,assertion_status=info.get('stage'),linked_sentences=linked,context_read_span=[lo,hi]),
  overlap=dict(target=target,matched=matched,matched_count=len(matched),target_count=len(target),relevance=relevance,semantic_gate_applied=False),
  fact_group=dict(key=list(fact_key(e)),policy='exact_normalized_five_elements',fuzzy_merge=False,weighting='gamma ** chronological_rank'))
 return e,relevance,support,tr
