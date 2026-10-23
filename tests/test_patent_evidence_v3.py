import unittest
from copy import deepcopy
from test_patent_evidence_v2 import task,cease,count
try:
 from dynamic_retrieval import patent_evidence_v3 as p
except ImportError:
 from dynamic_retrieval import patent_evidence_v2 as p
from dynamic_retrieval.evidence import extract

class CrossSentenceTests(unittest.TestCase):
 def ev(self,text,t=None,quote=None,ann=None):
  return p.evaluate({},t or cease(),quote=quote or text,text=text,original_support=[1,-1],annotation=ann)
 def test_linked_facets_are_source_bound(self):
  s='Russia and Ukraine publicly announced a ceasefire agreement on May 28, 2026. Both sides mutually agreed to this ceasefire. This ceasefire covers all military operations.'
  e,r,d,tr=self.ev(s)
  self.assertEqual(d,[1,-1]);self.assertGreater(len(tr['normalization']['linked_sentences']),1)
  for spans in tr['normalization']['witnesses'].values():
   for w in spans:self.assertEqual(s[w['start']:w['end']],w['text'])
 def test_anaphoric_date(self):
  s='Russia and Ukraine publicly announced a mutually agreed general ceasefire. This agreement was signed on May 28, 2026.'
  e,r,d,tr=self.ev(s);self.assertEqual(e.get('time'),'2026-05-28');self.assertEqual(d,[1,-1])
 def test_other_event_cannot_supply_facets(self):
  s='Russia and Ukraine publicly announced a ceasefire on May 28, 2026. Israel and Hamas mutually agreed to a general ceasefire.'
  self.assertEqual(self.ev(s)[2],[0,0])
 def test_unlinked_date_not_borrowed(self):
  s='Russia and Ukraine publicly announced a mutually agreed general ceasefire. A ceremony took place on May 28, 2026.'
  self.assertNotIn('time',self.ev(s)[0]);self.assertEqual(self.ev(s)[2],[0,0])
 def test_linked_denial_blocks(self):
  s='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026. This agreement was denied as false.'
  self.assertEqual(self.ev(s)[2],[0,0])
 def test_different_named_event_denial_does_not_contaminate(self):
  s='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026. The ceasefire between Israel and Hamas was denied.'
  self.assertEqual(self.ev(s)[2],[1,-1])
 def test_future_clause_not_completed(self):
  s='Russia and Ukraine publicly announced a ceasefire on May 28, 2026. Both sides might agree to a general ceasefire.'
  self.assertEqual(self.ev(s)[2],[0,0])
 def test_cannot_read_outside_model_excerpt(self):
  a='Russia and Ukraine publicly announced a ceasefire on May 28, 2026.'
  s=a+' Both sides mutually agreed to this ceasefire. This ceasefire covers all military operations.'
  self.assertEqual(self.ev(s,quote=a,ann={'excerpt':a,'time_scope':'target_compatible','factual_status':'reported'})[2],[0,0])
 def test_reported_counterpart_response_not_final_agreement(self):
  s='Russian President Vladimir Putin announced a 32-hour ceasefire and his Ukrainian counterpart Volodymyr Zelenskiy said Kyiv would abide by the measure.'
  e,r,d,tr=self.ev(s)
  self.assertEqual(e.get('subject'),'russia');self.assertEqual(e.get('object'),'ukraine')
  self.assertGreaterEqual(r,0.5);self.assertEqual(d,[0,0]);self.assertNotEqual(e.get('action'),'agree ceasefire')
 def test_partial_model_sentence_cannot_hide_denial(self):
  full='It is false that Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.'
  q=full[17:]
  self.assertEqual(self.ev(full,quote=q,ann={'excerpt':q})[2],[0,0])
 def test_wrong_counterpart_no_target_copy(self):
  s='Russian President Vladimir Putin announced a ceasefire and his Iranian counterpart said Tehran would abide by the measure.'
  self.assertNotEqual(self.ev(s)[0].get('object'),'ukraine')
 def test_procedural_chain_never_completed(self):
  s='The Knesset approved a bill to dissolve itself. The bill passed a preliminary reading. It still requires final approval.'
  e,r,d,tr=self.ev(s,task());self.assertEqual(d,[0,0]);self.assertNotEqual(e.get('action'),'dissolve')
  self.assertTrue(tr['normalization']['linked_sentences'])
 def test_different_event_stops_anaphora(self):
  s='Russia and Ukraine publicly announced a ceasefire on May 28, 2026. Israel and Hamas signed an agreement. Both sides mutually agreed to this general ceasefire.'
  self.assertEqual(self.ev(s,quote=s.split('.')[0]+'.')[2],[0,0])
 def test_fact_identity_dates_remain_distinct(self):
  s='Russia and Ukraine publicly announced a mutually agreed general ceasefire. This agreement was signed on May 28, 2026.'
  self.assertNotEqual(self.ev(s)[3]['fact_group']['key'],self.ev(s.replace('28','29'))[3]['fact_group']['key'])
 def test_count_not_yet_final_stays_neutral(self):
  self.assertEqual(self.ev('Elon Musk posted 500 tweets in April 2026. This count is provisional.',count())[2],[0,0])
 def test_engine_entry_accepts_neutral_relevant_fact(self):
  t=cease();doc={'id':'one','title':'','text':'Russian President Vladimir Putin announced a ceasefire and his Ukrainian counterpart Volodymyr Zelenskiy said Kyiv would abide by the measure.'}
  row=extract(doc,t,evidence_policy='patent_elements_v3')
  self.assertGreaterEqual(row['relevance'],0.5);self.assertEqual(row['support'],[0,0])
  self.assertFalse(row['patent_evidence_trace']['overlap']['semantic_gate_applied'])

if __name__=='__main__':unittest.main()


class CrossSentenceEngineTests(unittest.TestCase):
 def test_neutral_admission_contributes_equivalent_not_direction(self):
  from dynamic_retrieval.engine import run
  from dynamic_retrieval.models import Config
  t=cease();d=dict(id='one',title='',text='Russian President Vladimir Putin announced a ceasefire and his Ukrainian counterpart Volodymyr Zelenskiy said Kyiv would abide by the measure.',source_id='wire',published_at='2026-05-30T00:00:00Z',observed_at='2026-05-30T01:00:00Z')
  out=run(t,[d],Config(mode='fixed',rounds=1),evidence_policy='patent_elements_v3')
  self.assertEqual(out['diagnostics']['admitted_documents'],1)
  self.assertEqual(out['result']['supporting_evidence_count'],0)
  self.assertEqual(out['rounds'][0]['volume'],1)
 def test_shared_and_demand_v3_derive_same_source_support(self):
  from types import SimpleNamespace
  from dynamic_retrieval.semantic_pipeline import _extract_one
  from dynamic_retrieval.on_demand import ModelAnnotationProvider
  s='Russia and Ukraine publicly announced a ceasefire agreement on May 28, 2026. Both sides mutually agreed to this ceasefire. This ceasefire covers all military operations.'
  t=cease();d=dict(id='same',title='',text=s,source_id='wire',published_at='2026-05-30T00:00:00Z',observed_at='2026-05-30T01:00:00Z')
  response=dict(elements={'subject':'Russia','object':'Ukraine'},support=[0,0],quote=s.split('.')[0]+'.',rationale='Fixture.',factual_status='reported',time_scope='target_compatible')
  client=SimpleNamespace(complete_json=lambda *args,**kw:dict(data=deepcopy(response),metadata={'model':'fixture'}))
  a,_=_extract_one(client,t,d,12000);b=ModelAnnotationProvider(client)(t,d)
  x=extract(d,t,{'same':a},evidence_policy='patent_elements_v3');y=extract(d,t,{'same':b},evidence_policy='patent_elements_v3')
  self.assertEqual(x,y);self.assertEqual(x['support'],[1,-1]);self.assertFalse(x['human_reviewed'])


class CrossSentenceReviewTests(unittest.TestCase):
 def ev(self,s,ann=None):return p.evaluate({},cease(),quote=s.split('.')[0]+'.',text=s,original_support=[0,0],annotation=ann)
 def test_negation_and_uncertainty_do_not_supply_facets(self):
  anchor='Russia and Ukraine publicly announced a ceasefire on May 28, 2026. '
  for tail in ['Both sides never mutually agreed to this general ceasefire.', 'Both sides mutually agreed to this ceasefire. This ceasefire does not cover all military operations.', 'Both sides mutually agreed to this ceasefire. This ceasefire may cover all military operations.']:
   with self.subTest(tail=tail):self.assertEqual(self.ev(anchor+tail)[2],[0,0])
 def test_new_location_cannot_supply_other_event_facets(self):
  s='Russia and Ukraine publicly announced a ceasefire on May 28, 2026. The ceasefire in Gaza was a publicly announced mutually agreed general halt.'
  self.assertEqual(self.ev(s)[2],[0,0])
 def test_conflict_outside_model_read_range_not_consumed(self):
  a='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.'
  s=a+' Officials denied that Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.'
  self.assertEqual(self.ev(s,{'excerpt':a})[2],[1,-1])

class CrossSentenceRelationReviewTests(unittest.TestCase):
 def test_agreement_to_other_activity_is_not_ceasefire(self):
  s='Russia and Ukraine agree to build a bridge.'
  e,r,d,tr=p.evaluate({},cease(),quote=s,text=s,original_support=[0,0]);self.assertNotIn('action',e);self.assertLess(r,0.4)
 def test_signed_date_by_other_parties_not_borrowed(self):
  s='Russia and Ukraine publicly announced a mutually agreed general ceasefire. This agreement was signed on May 28, 2026, by Israel and Hamas.'
  e,r,d,tr=p.evaluate({},cease(),quote=s,text=s,original_support=[0,0]);self.assertNotIn('time',e);self.assertEqual(d,[0,0])
 def test_quote_outside_excerpt_no_unrestricted_fallback(self):
  q='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026.'
  e,r,d,tr=p.evaluate({},cease(),quote=q,text='Background. '+q,original_support=[0,0],annotation={'excerpt':'Background.'})
  self.assertEqual(d,[0,0]);self.assertEqual(r,0)

class CrossSentenceStrictFacetTests(unittest.TestCase):
 def ev(self,s,ann=None,t=None):return p.evaluate({},t or cease(),quote=s.split('.')[0]+'.',text=s,original_support=[0,0],annotation=ann)
 def test_anaphoric_corrections_cannot_disappear(self):
  anchor='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026. '
  for tail in ["This agreement wasn't reached.",'This agreement never existed.','Both sides rejected this agreement.']:
   with self.subTest(tail=tail):self.assertEqual(self.ev(anchor+tail)[2],[0,0])
 def test_facets_must_describe_same_ceasefire_not_general_keywords(self):
  anchor='Russia and Ukraine publicly announced a ceasefire agreement on May 28, 2026. '
  for tail in ['This ceasefire was discussed while Israel and Hamas mutually agreed to a general halt.','This ceasefire was discussed at a general meeting. Both sides mutually agreed to more talks.']:
   with self.subTest(tail=tail):self.assertEqual(self.ev(anchor+tail)[2],[0,0])
 def test_count_fallback_cannot_read_after_excerpt(self):
  q='XTracker Post Counter for Elon Musk for April 2026';s=q+' finalized the entire month at 1000 posts.'
  e,r,d,tr=p.evaluate({},count(),quote=q,text=s,original_support=[0,0],annotation={'excerpt':q})
  self.assertNotIn('object',e);self.assertEqual(d,[0,0])

class CrossSentenceIdentityTests(unittest.TestCase):
 def test_other_event_denial_does_not_change_valid_anchor(self):
  a='Russia and Ukraine publicly announced a mutually agreed general ceasefire on May 28, 2026. '
  for tail in ['The ceasefire in Gaza was never signed.','The agreement for Israel and Hamas was denied.']:
   with self.subTest(tail=tail):self.assertEqual(p.evaluate({},cease(),quote=a.strip(),text=a+tail,original_support=[0,0])[2],[1,-1])
 def test_reported_override_preserves_polarity_identity(self):
  a='Russia and Ukraine agree to a ceasefire.';b='It is false that '+a
  x=p.evaluate({},cease(),quote=a,text=a,original_support=[0,0]);y=p.evaluate({},cease(),quote=b,text=b,original_support=[0,0])
  self.assertNotEqual(x[3]['fact_group']['key'],y[3]['fact_group']['key'])
