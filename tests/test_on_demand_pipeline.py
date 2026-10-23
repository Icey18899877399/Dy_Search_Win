import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dynamic_retrieval.call_cost import CallCostLedger, CallCostError
from dynamic_retrieval.semantic import DeepSeekClient
from dynamic_retrieval.models import Config
from test_engine import TASK, document
from test_on_demand import machine

class DemandPipelineTests(unittest.TestCase):
    def pipeline(self):
        self.assertIsNotNone(importlib.util.find_spec('dynamic_retrieval.on_demand'))
        from dynamic_retrieval.on_demand import run_on_demand
        return run_on_demand

    def client(self,cache,ledger,docs):
        client=DeepSeekClient(cache,api_key='fake',max_attempts=1,cost_ledger=ledger)
        class Opener:
            def open(self,request,timeout):
                payload=json.loads(request.data)
                context=json.loads(payload['messages'][1]['content'])
                # One valid quote-based annotation, independent of candidate count.
                data={k:v for k,v in machine(TASK,docs[0]).items() if k in
                    ('elements','support','quote','rationale','factual_status','time_scope')}
                return io.BytesIO(json.dumps(dict(id='r',model='fixture',
                    usage=dict(prompt_tokens=10,completion_tokens=5,total_tokens=15),
                    choices=[dict(finish_reason='stop',message=dict(content=json.dumps(data)))] )).encode())
        client._opener=Opener();return client

    def test_one_selected_read_one_request_then_cache_no_new_usage(self):
        run_pipeline=self.pipeline()
        docs=[document(str(i),'2026-06-18') for i in range(3)]
        cfg=Config(mode='fixed',rounds=1,total_budget=2,round_budget=2)
        with tempfile.TemporaryDirectory() as tmp:
            first=run_pipeline(TASK,docs,cfg,self.client(tmp,CallCostLedger(),docs))
            second=run_pipeline(TASK,docs,cfg,self.client(tmp,CallCostLedger(),docs))
        self.assertEqual(first['diagnostics']['model_calls']['network_attempts'],1)
        self.assertEqual(first['diagnostics']['model_calls']['actual_usage']['total_tokens'],15)
        self.assertEqual(len(first['extraction_trace']),1)
        self.assertEqual(second['diagnostics']['model_calls']['network_attempts'],0)
        self.assertEqual(second['diagnostics']['model_calls']['cache_hits'],1)
        self.assertEqual(second['diagnostics']['model_calls']['actual_usage']['total_tokens'],0)
        self.assertEqual(second['diagnostics']['model_calls']['historical_cache_usage']['total_tokens'],15)
        self.assertEqual(first['result'],second['result'])

    def test_cost_persistence_failure_aborts_instead_of_abstaining(self):
        run_pipeline=self.pipeline()
        docs=[document('a','2026-06-18')]
        with tempfile.TemporaryDirectory() as tmp:
            ledger=CallCostLedger()
            client=self.client(tmp,ledger,docs)
            with patch.object(ledger,'preflight',side_effect=CallCostError('ledger unavailable')):
                with self.assertRaises(CallCostError):
                    run_pipeline(TASK,docs,Config(mode='fixed',rounds=1),client)

    def test_reused_ledger_rejected_to_avoid_cross_run_cost_attribution(self):
        run_pipeline=self.pipeline()
        ledger=CallCostLedger()
        ledger.record('cache_read',elapsed_seconds=0,outcome='success')
        with tempfile.TemporaryDirectory() as tmp:
            client=self.client(tmp,ledger,[document('a','2026-06-18')])
            with self.assertRaises(ValueError):run_pipeline(TASK,[],Config(),client)

class PipelinePrivacyTests(unittest.TestCase):
    def test_invalid_model_fields_are_not_copied_to_failure_trace(self):
        from dynamic_retrieval.on_demand import run_on_demand
        from test_on_demand import machine
        docs=[document('a','2026-06-18')]
        class Client:
            cost_ledger=CallCostLedger()
            def complete_json(self,*args,**kwargs):
                data={k:v for k,v in machine(TASK,docs[0]).items() if k in
                    ('elements','support','quote','rationale','factual_status','time_scope')}
                data['reasoning_content']='PRIVATE_REASONING_SENTINEL'
                return dict(data=data,metadata=dict(model='fixture'))
        result=run_on_demand(TASK,docs,Config(mode='fixed',rounds=1),Client())
        self.assertEqual(result['evidence'],[])
        self.assertNotIn('PRIVATE_REASONING_SENTINEL',str(result))

class ComparisonPolicyTests(unittest.TestCase):
    def test_v6_compares_without_rebinding_or_mutating_frozen_annotations(self):
        from dynamic_retrieval.evidence import extract
        from dynamic_retrieval.semantic import validate_semantic
        import copy
        task=dict(TASK,question='Israeli parliament dissolved by July 31?',
            cutoff='2026-05-31T23:59:59Z',matching_policy='typed_v5')
        quote='On May 20, 2026, the Knesset gave initial approval to a bill to dissolve parliament.'
        doc=dict(document('v6','2026-05-21'),text=quote,title='Knesset progress',
                 observed_at='2026-05-22T00:00:00Z')
        annotation=validate_semantic(dict(elements={'subject':'Israeli Knesset',
            'action':'gave initial approval to dissolution bill','time':'May 20, 2026','location':'Israel'},
            support=[1,0],quote=quote,rationale='Completed procedural stage only',
            factual_status='reported',time_scope='target_compatible'),task,doc,
            dict(model='fixture',excerpt=doc['title']+'\n'+quote))
        original=copy.deepcopy(annotation)
        old=extract(doc,task,{doc['id']:annotation})
        new=extract(doc,task,{doc['id']:annotation},comparison_policy='typed_v6')
        self.assertEqual(old['relevance'],0)
        self.assertGreaterEqual(new['relevance'],.4)
        self.assertEqual(annotation,original)
        self.assertEqual(new['support'],old['support'])
        result=__import__('dynamic_retrieval.engine',fromlist=['run']).run(
            task,[doc],Config(mode='fixed',rounds=1),{doc['id']:annotation},comparison_policy='typed_v6')
        self.assertEqual(result['result']['supporting_evidence_count'],1)
        self.assertFalse(result['evidence'][0]['matching_trace']['establishes_outcome'])
        self.assertEqual(result['provenance']['comparison_policy'],'typed_v6')

class EagerAccountingTests(unittest.TestCase):
    def test_eager_helper_propagates_ledger_failure(self):
        from dynamic_retrieval.semantic_pipeline import _extract_one
        class Client:
            def complete_json(self,*args,**kwargs):raise CallCostError('unavailable')
        with self.assertRaises(CallCostError):
            _extract_one(Client(),TASK,document('a','2026-06-18'),12000)
