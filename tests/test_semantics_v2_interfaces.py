import unittest
from dynamic_retrieval.cli import parser,execution_options
from dynamic_retrieval.web_jobs import validated_execution
from dynamic_retrieval.models import Config

class SemanticsV2InterfaceTests(unittest.TestCase):
 def test_frozen_v2_policy_survives_web_roundtrip_and_is_distinct_from_v1(self):
  policy='patent_elements_v2'
  execution=validated_execution({'evidence_policy':policy},Config())
  self.assertEqual(execution['evidence_policy'],policy)
  self.assertEqual(validated_execution(None,Config(),{'provenance':execution}),execution)
  self.assertEqual(validated_execution(None,Config(),{'provenance':{'evidence_policy':'patent_elements_v1'}})['evidence_policy'],'patent_elements_v1')
 def test_cli_passes_v2_to_all_comparison_modes(self):
  args=parser().parse_args(['compare','--market','test','--cutoff','2026-05-31T23:59:59Z','--output','unused','--evidence-policy','patent_elements_v2'])
  for mode in ('fixed','basic','enhanced'):
   self.assertEqual(execution_options(args,mode)['evidence_policy'],'patent_elements_v2')

class SemanticsV2MachinePipelineTests(unittest.TestCase):
 def test_shared_and_demand_preserve_bound_machine_annotations_and_rule_direction(self):
  from copy import deepcopy
  from dynamic_retrieval.engine import run
  from dynamic_retrieval.evidence import prepare_task
  from dynamic_retrieval.semantic import validate_semantic
  from test_engine import document
  task=prepare_task(dict(question='Israeli parliament dissolved by July 31?',description='The sitting Israeli Knesset is dissolved between January 27 and July 31, 2026, 11:59 PM ET.',observed_at='2026-01-27T00:00:00Z',cutoff='2026-06-01T23:59:59Z',outcomes=['Yes','No']))
  doc=document('v2-pipeline','2026-05-31')
  doc.update(observed_at='2026-05-31T12:00:00Z',title='Israeli parliament update',text='The Knesset was dissolved on May 28, 2026.')
  ann=validate_semantic(dict(elements={'subject':'Knesset','action':'dissolved','time':'May 28, 2026'},support=[-1,1],quote=doc['text'],rationale='Fixture deliberately reverses model direction.',factual_status='reported',time_scope='target_compatible'),task,doc,dict(model='fixture',excerpt=doc['title']+'\n'+doc['text']))
  self.assertFalse(ann['reviewed'])
  original=deepcopy((task,doc,ann)); calls=[]
  cfg=Config(mode='fixed',rounds=1,admission=.4)
  eager=run(task,[doc],cfg,{doc['id']:ann},evidence_policy='patent_elements_v2')
  def provider(t,d):
   calls.append(d['id']);return ann
  lazy=run(task,[doc],cfg,annotation_provider=provider,evidence_policy='patent_elements_v2')
  self.assertEqual(calls,[doc['id']]);self.assertEqual((task,doc,ann),original)
  for field in ('rounds','result','evidence'):self.assertEqual(eager[field],lazy[field])
  self.assertEqual(eager['diagnostics']['admitted_documents'],1)
  self.assertEqual(eager['evidence'][0]['support'],[1,-1])
  self.assertFalse(eager['evidence'][0]['human_reviewed'])
  self.assertEqual(eager['evidence'][0]['extraction_version'],'patent_elements_v2')
  self.assertEqual(eager['provenance']['evidence_policy'],'patent_elements_v2')


