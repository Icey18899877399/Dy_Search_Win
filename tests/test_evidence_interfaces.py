import unittest
from types import SimpleNamespace
from unittest.mock import patch
from dynamic_retrieval.models import Config
from dynamic_retrieval.web_jobs import validated_execution
from dynamic_retrieval.web_catalog import Catalog
from dynamic_retrieval import cli
from test_engine import TASK,document

POLICY='patent_elements_v1'
class EvidenceInterfaceTests(unittest.TestCase):
 def test_explicit_web_policy_roundtrip_and_invalid_values(self):
  self.assertEqual(validated_execution({'evidence_policy':POLICY},Config())['evidence_policy'],POLICY)
  self.assertEqual(validated_execution(None,Config(),{'provenance':{'evidence_policy':POLICY}})['evidence_policy'],POLICY)
  for bad in ['other',{},True]:
   with self.assertRaises(ValueError):validated_execution({'evidence_policy':bad},Config())
 def test_cli_and_demand_forward_policy(self):
  args=cli.parser().parse_args(['run','--market','x','--cutoff',TASK['cutoff'],'--output','unused','--evidence-policy',POLICY])
  self.assertEqual(cli.execution_options(args,'fixed')['evidence_policy'],POLICY)
  from dynamic_retrieval.on_demand import run_on_demand
  from dynamic_retrieval.call_cost import CallCostLedger
  with patch('dynamic_retrieval.on_demand.run',return_value={'diagnostics':{}}) as runner:
   run_on_demand(TASK,[],Config(mode='fixed'),SimpleNamespace(cost_ledger=CallCostLedger()),evidence_policy=POLICY)
   self.assertEqual(runner.call_args.kwargs['evidence_policy'],POLICY)
 def test_diagnostic_uses_saved_evidence_policy_not_legacy(self):
  doc=document('x','2026-06-18')
  result={'provenance':{'evidence_policy':POLICY},'rounds':[],'evidence':[],'config':{'admission':.6}}
  fake=SimpleNamespace(get=lambda _:dict(run=result),_inputs=lambda *a:(TASK,[doc],{}),path=lambda _:'unused')
  with patch('dynamic_retrieval.evidence.extract',return_value={'id':'x','relevance':.4,'support':[0,0]}) as extract:
   diag=Catalog.diagnostics_evidence(fake,'id')
   self.assertEqual(extract.call_args.kwargs['evidence_policy'],POLICY)
   self.assertFalse(diag['evidence'][0]['admitted'])
 def test_diagnostic_uses_saved_comparison_policy(self):
  doc=document('x','2026-06-18')
  result={'provenance':{'comparison_policy':'typed_v6'},'rounds':[],'evidence':[],'config':{'admission':.6}}
  fake=SimpleNamespace(get=lambda _:dict(run=result),_inputs=lambda *a:(TASK,[doc],{}),path=lambda _:'unused')
  with patch('dynamic_retrieval.evidence.extract',return_value={'id':'x','relevance':0,'support':[0,0]}) as extract:
   Catalog.diagnostics_evidence(fake,'id')
   self.assertEqual(extract.call_args.kwargs['comparison_policy'],'typed_v6')

 def test_demand_diagnostic_never_invents_missing_annotation(self):
  doc=document('x','2026-06-18')
  result={'provenance':{'extraction_mode':'on_demand'},'rounds':[], 'evidence':[], 'config':{'admission':.6}}
  fake=SimpleNamespace(get=lambda _:dict(run=result),_inputs=lambda *a:(TASK,[doc],{}),path=lambda _:'unused')
  with patch('dynamic_retrieval.evidence.extract') as extract:
   diag=Catalog.diagnostics_evidence(fake,'id')
   extract.assert_not_called()
   self.assertIsNone(diag['evidence'][0]['admitted'])
   self.assertEqual(diag['evidence'][0]['extraction_method'],'on_demand_annotation_unavailable')
   self.assertEqual(diag['evidence'][0]['rejection_reason'],'not_read_no_frozen_annotation')
 def test_demand_replay_rejected_before_lexical_fallback(self):
  value={'provenance':{'extraction_mode':'on_demand'}}
  fake=SimpleNamespace(path=lambda _:'unused',_verify_manifest=lambda _:'verified_saved_manifest',_inputs=lambda *a:(TASK,[],{}),_validate_current_inputs=lambda *a:None)
  with patch('dynamic_retrieval.web_catalog.read_json',return_value=value),patch('dynamic_retrieval.web_catalog.validate_result',side_effect=lambda x:x):
   with self.assertRaisesRegex(ValueError,'On-demand'):Catalog.replay_inputs(fake,'id')
 def test_invalid_response_preserves_parsed_model_data(self):
  from dynamic_retrieval.on_demand import ModelAnnotationProvider
  provider=ModelAnnotationProvider(SimpleNamespace(complete_json=lambda *a,**k:dict(data={'quote':'returned','support':'malformed'},metadata={})))
  with self.assertRaises(ValueError):provider(TASK,document('x','2026-06-18'))
  self.assertEqual(provider.traces[0]['parsed_response'],{'quote':'returned','support':'malformed'})
