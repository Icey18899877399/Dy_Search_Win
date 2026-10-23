import copy,json,unittest
from types import SimpleNamespace
from dynamic_retrieval.semantic import evidence_context,validate_semantic,validate_model_annotation
from dynamic_retrieval.semantic_pipeline import _extract_one
from dynamic_retrieval.on_demand import ModelAnnotationProvider
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from test_fact_coverage import task,doc

class FactWindowTests(unittest.TestCase):
 def setUp(self):
  self.t=dict(task(),evidence_context_policy='fact_window_v1',observed_at='2026-01-27T00:00:00Z')
  self.quote='The Knesset was dissolved on May 20, 2026.'
  self.d=doc('Neutral background. '*1000+'\n'+self.quote+'\nEnd of report.')
 def response(self):return dict(elements={'subject':'Knesset','action':'dissolved','time':'2026-05-20'},support=[1,-1],quote=self.quote,rationale='Fixture source assertion.',factual_status='reported',time_scope='target_compatible')
 def client(self):
  seen=[]
  def complete(messages,**kw):seen.append(json.loads(messages[1]['content']));return dict(data=self.response(),metadata={'model':'fixture'})
  return SimpleNamespace(complete_json=complete),seen
 def test_legacy_prefix_unchanged_and_optin_finds_beyond_head(self):
  t=task();old=evidence_context(t,self.d)
  self.assertEqual(old['evidence'],{'id':'x','excerpt':(self.d['title']+'\n'+self.d['text'])[:12000]})
  new=evidence_context(self.t,self.d);e=new['evidence'];self.assertIn(self.quote,e['excerpt']);self.assertGreater(e['excerpt_start'],0)
  self.assertEqual((self.d['title']+'\n'+self.d['text'])[e['excerpt_start']:e['excerpt_end']],e['excerpt']);self.assertLessEqual(len(e['excerpt']),12000)
 def test_shared_and_demand_preserve_bound_context(self):
  client,seen=self.client();a,trace=_extract_one(client,self.t,self.d,12000)
  self.assertIsNotNone(a);self.assertGreater(a['excerpt_start'],0);self.assertFalse(a['reviewed']);validate_model_annotation(a,self.t,self.d)
  b=ModelAnnotationProvider(client)(self.t,self.d);self.assertEqual(a,b);self.assertEqual(trace['excerpt_context']['context_policy'],'fact_window_v1')
 def test_tampered_offset_or_policy_is_rejected(self):
  client,_=self.client();a,_=_extract_one(client,self.t,self.d,12000);self.assertIsNotNone(a)
  for change in ({'excerpt_start':0},{'excerpt_end':1},{'context_policy':'legacy'}):
   with self.subTest(change=change),self.assertRaises(ValueError):validate_model_annotation(dict(a,**change),self.t,self.d)
  with self.assertRaises(ValueError):validate_model_annotation(a,task(),self.d)
 def test_future_body_and_wrapper_fail_before_model_call(self):
  for d in (dict(self.d,observed_at='2026-06-01T00:00:00Z'),doc('The Wayback Machine - https://web.archive.org/web/1/https://example.test/article')):
   client,seen=self.client()
   with self.assertRaises(ValueError):ModelAnnotationProvider(client)(self.t,d)
   self.assertEqual(seen,[])
 def test_unknown_policy_rejected(self):
  with self.assertRaises(ValueError):evidence_context(dict(self.t,evidence_context_policy='typo'),self.d)
 def test_engine_provider_keeps_optin_policy_and_cutoff_metadata(self):
  d=dict(self.d,published_at='2026-05-30T00:00:00Z',observed_at='2026-05-30T01:00:00Z')
  client,seen=self.client();out=run(self.t,[d],Config(mode='fixed',rounds=1),annotation_provider=ModelAnnotationProvider(client),evidence_policy='patent_elements_v2')
  self.assertEqual(out['diagnostics']['annotation_failures'],[]);self.assertEqual(out['diagnostics']['admitted_documents'],1);self.assertEqual(seen[0]['task']['evidence_context_policy'],'fact_window_v1')
 def test_foreign_task_metadata_and_labels_not_forwarded(self):
  t=dict(self.t,resolved_outcome='LEAK',private_notes='LEAK')
  context=evidence_context(t,self.d);self.assertNotIn('LEAK',json.dumps(context));self.assertEqual(context['task']['observed_at'],self.t['observed_at'])
 def test_future_task_definition_rejected_before_model_call(self):
  t=dict(self.t,observed_at='2026-06-01T00:00:00Z');client,seen=self.client()
  with self.assertRaises(ValueError):ModelAnnotationProvider(client)(t,self.d)
  self.assertEqual(seen,[])
 def test_shared_invalid_source_returns_failed_trace_without_request(self):
  client,seen=self.client();a,trace=_extract_one(client,self.t,dict(self.d,observed_at='2026-06-01T00:00:00Z'),12000)
  self.assertIsNone(a);self.assertFalse(trace['model_request_made']);self.assertEqual(seen,[])
