import unittest
from copy import deepcopy
from test_engine import TASK,document,annotations
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from dynamic_retrieval.evidence import extract
import test_quality

class RemediationTests(unittest.TestCase):
    def test_atomic_subject_and_aliases_preserve_raw_fact(self):
        from dynamic_retrieval.matching import normalize_task,typed_relevance
        task=dict(TASK,question='Will Israel strike 15 or more countries in 2026?')
        task.pop('target_elements')
        t=normalize_task(task)
        self.assertEqual(t['target_elements']['subject'],'Israel')
        self.assertEqual(t['target_elements']['action'],'strike')
        self.assertIn('15',t['target_elements']['object'])
        fact={'subject':'Israel','action':'conducted airstrikes','time':'2026-05-01'}
        saved=deepcopy(fact)
        score,trace=typed_relevance(fact,t)
        self.assertGreaterEqual(score,.4);self.assertEqual(fact,saved)
        self.assertNotIn('object',trace['matched'])
        t['element_aliases']={'subject':['State of Israel']}
        self.assertIn('subject',typed_relevance({'subject':'State of Israel'},t)[1]['matched'])
        self.assertNotIn('subject',typed_relevance({'subject':'Israel opposition'},t)[1]['matched'])

    def test_airspace_and_rates_and_uranium_subjects(self):
        from dynamic_retrieval.matching import normalize_task
        for question,subject,action in [
            ('Iran closes its airspace by May 18?','Iran','close'),
            ('Will the Fed increase interest rates by 25 bps after the June 2026 meeting?','the Fed','increase'),
            ('US obtains Iranian enriched uranium by December 31?','US','obtain'),
            ('US x Iran permanent peace deal by May 31, 2026?','US and Iran','agree')]:
            t=normalize_task(dict(TASK,question=question))
            self.assertEqual(t['target_elements']['subject'],subject)
            self.assertEqual(t['target_elements']['action'],action)

    def test_evidence_opt_in_matching_trace(self):
        task=dict(TASK,matching_policy='typed_v2',target_elements={'subject':'Alice','action':'win','object':'election','time':'2026'})
        doc=document('a','2026-06-18')
        ann=annotations([doc]);ann['a']['elements']['time']='June 2026'
        row=extract(doc,task,ann)
        self.assertEqual(row['relevance'],1)
        self.assertEqual(row['elements']['time'],'june 2026')
        self.assertEqual(row['matching_trace']['policy'],'typed_v2')

    def test_small_grid_budget_can_eventually_read(self):
        docs=[document('a','2026-06-19'),document('old','2026-05-26','old-paper')]
        task=dict(TASK,scheduler_policy='grid_credit_v2')
        cfg=Config(rounds=16,round_budget=20,total_budget=200,low_loss=0)
        result=run(task,docs,cfg,annotations(docs))
        ids={i for r in result['rounds'] for i in r['retrieved_ids']}
        self.assertIn('old',ids)
        self.assertTrue(any(r['action']=='expand' for r in result['rounds']))
        self.assertLessEqual(result['result']['spent'],cfg.total_budget)
        for row in result['rounds']:
            self.assertAlmostEqual(sum(row['budget'].values()),row['spent'])
        self.assertEqual(result,run(task,docs,cfg,annotations(docs)))

    def test_new_policy_rejects_nonfact_direction(self):
        from dynamic_retrieval.matching import validate_direction
        base=dict(support=[1,-1],quote='Alice received the nomination.',rationale='A confirmed nomination.',elements={'subject':'Alice'})
        validate_direction(base)
        for change in (dict(support=[-1,-1]),dict(quote='Alice leads the polls.'),dict(rationale='Analysts forecast a victory.')):
            with self.assertRaises(ValueError):validate_direction(dict(base,**change))

class WinnerEvidenceTests(unittest.TestCase):
    def fixture(self):
        task,gamma,res=test_quality.QualityTests().fixtures()
        res['data'][0].pop('payouts');res['data'][0].pop('resolved_at')
        res['data'][0].update(last_update_timestamp='1780272000',question_id='0x'+'c'*64)
        gamma['clobTokenIds']='["10","20"]'
        clob=dict(condition_id=gamma['conditionId'],question_id='0x'+'c'*64,
                  question=task['question'],closed=True,tokens=[
                    dict(token_id='10',outcome='No',winner=False,price=1),
                    dict(token_id='20',outcome='Yes',winner=True,price=0)])
        return task,gamma,res,clob
    def test_final_winner_ignores_prices_and_maps_tokens(self):
        from dynamic_retrieval.quality import validate_final_winner
        t,g,r,c=self.fixture()
        x=validate_final_winner(t,g,r,c,'2026-10-22T00:00:00Z')
        self.assertEqual(x['status'],'official_resolved')
        self.assertEqual(x['outcome'],'Yes')
        self.assertEqual(x['verification'],'official_api_terminal_winner_not_payout_audit')
        c['tokens'].reverse()
        self.assertEqual(validate_final_winner(t,g,r,c,'2026-10-22T00:00:00Z')['outcome'],'Yes')
    def test_reject_mismatch_proposals_unknown_winners_and_invalid_times(self):
        from dynamic_retrieval.quality import validate_final_winner
        for mutate in [
            lambda t,g,r,c:c.update(closed=False),
            lambda t,g,r,c:c.update(condition_id='0x'+'d'*64),
            lambda t,g,r,c:c['tokens'][0].update(winner=True),
            lambda t,g,r,c:c['tokens'][1].update(winner='true'),
            lambda t,g,r,c:c['tokens'][1].update(token_id='99'),
            lambda t,g,r,c:r['data'][0].update(status='proposed'),
            lambda t,g,r,c:r['data'][0].update(last_update_timestamp='1'),
            lambda t,g,r,c:r['data'][0].update(transaction_hash=''),
            lambda t,g,r,c:r['data'][0].update(payouts=[.5,.5]),
        ]:
            t,g,r,c=self.fixture();mutate(t,g,r,c)
            self.assertNotEqual(validate_final_winner(t,g,r,c,'2026-10-22T00:00:00Z')['status'],'official_resolved')

    def test_collector_opt_in_records_clob_and_declared_protocol(self):
        from dynamic_retrieval.official import collect,GAMMA,RESOLUTIONS
        t,g,r,c=self.fixture();urls=[]
        def getter(url):
            urls.append(url)
            return g if url.startswith(GAMMA) else r if url.startswith(RESOLUTIONS) else c
        snapshot=collect(t,getter=getter,allow_final_winner=True)
        self.assertEqual(snapshot['label']['status'],'official_resolved')
        self.assertEqual(snapshot['clob'],c)
        self.assertEqual(len(urls),3)

class OperationalPolicyTests(unittest.TestCase):
    def test_future_pipeline_freezes_effective_policy_before_calls(self):
        import tempfile,json
        from pathlib import Path
        import test_semantic_pipeline as f
        from dynamic_retrieval.data.store import Store
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=f.SemanticPipelineTests().fixture(root)
            output=root/'out'
            class Inspect(f.FakeClient):
                def complete_json(self,messages,max_tokens=1800):
                    tasks=json.loads((output/'inputs/effective-tasks.json').read_text())
                    assert tasks[0]['semantic_policy']=='fact_v3'
                    assert tasks[0]['scheduler_policy']=='grid_credit_v2'
                    return super().complete_json(messages,max_tokens)
            with Store(db) as store:
                summary=run_semantic_pipeline(store,data,f.CUTOFF,output,count=1,min_documents=1,
                    max_documents=4,client=Inspect(),cache=root/'cache',repair_policies=True)
            self.assertEqual(summary['completed_runs'],3)
            task=json.loads((output/'inputs/tasks/m0/task.json').read_text())
            annotations=json.loads((output/'runs/m0/machine-annotations.json').read_text())
            self.assertEqual(task['matching_policy'],'typed_v3')
            self.assertTrue(all(a['prompt_version']=='evidence-semantics-v3' for a in annotations.values()))

class NegativeRiskEvidenceTests(unittest.TestCase):
    def test_request_question_mapping_requires_all_three_sources(self):
        from dynamic_retrieval.quality import validate_final_winner
        t,g,r,c=WinnerEvidenceTests().fixture()
        request='0x'+'d'*64;market='0x'+'e'*64;question=c['question_id']
        g.update(negRisk=True,questionID=question,negRiskRequestID=request,negRiskMarketID=market)
        c.update(neg_risk=True,neg_risk_request_id=request,neg_risk_market_id=market)
        r['data'][0]['question_id']=request
        self.assertEqual(validate_final_winner(t,g,r,c,'2026-10-22T00:00:00Z')['status'],'official_resolved')
        for field,value in [('negRisk',False),('questionID','0x'+'f'*64),
                            ('negRiskRequestID',question),('negRiskMarketID',question)]:
            bad=dict(g,**{field:value})
            self.assertNotEqual(validate_final_winner(t,bad,r,c,'2026-10-22T00:00:00Z')['status'],'official_resolved')

class ReviewRegressionTests(unittest.TestCase):
    def test_explicit_resolution_before_cutoff_cannot_use_late_update(self):
        from dynamic_retrieval.quality import validate_final_winner
        t,g,r,c=WinnerEvidenceTests().fixture()
        for stamp in ('2026-04-01T00:00:00Z','2028-01-01T00:00:00Z','bad-time'):
            r['data'][0]['resolved_at']=stamp
            self.assertNotEqual(validate_final_winner(t,g,r,c,'2026-10-22T00:00:00Z')['status'],'official_resolved')

    def test_v3_additional_verbs_and_explicit_unsupported(self):
        from dynamic_retrieval.matching import normalize_task,typed_relevance
        cases=[
          ('Will Russia capture Kostyantynivka by May 31?','Russia','capture','Kostyantynivka'),
          ('Will the Democratic Party control the Senate after the 2026 Midterm elections?','the Democratic Party','control','the Senate'),
          ('Will the US officially declare war on Iran by December 31, 2026?','the US','declare','war on Iran'),
          ('Will Hamas agree to disarm by June 30?','Hamas','agree','to disarm')]
        for question,subject,action,obj in cases:
            task=dict(TASK,question=question,matching_policy='typed_v3')
            task.pop('target_elements')
            t=normalize_task(task)
            self.assertEqual(t['target_elements']['subject'],subject)
            self.assertEqual(t['target_elements']['action'],action)
            self.assertEqual(t['target_elements']['object'],obj)
            self.assertGreaterEqual(typed_relevance({'subject':subject,'action':action,'object':obj},task)[0],.75)
        task=dict(TASK,question='2026 Balance of Power: R Senate, D House',matching_policy='typed_v3')
        task.pop('target_elements')
        self.assertEqual(normalize_task(task)['task_extraction'],'unsupported_question_v3')

    def test_two_tasks_export_their_own_final_elements(self):
        import tempfile,json
        from pathlib import Path
        from unittest.mock import patch
        import test_semantic_pipeline as f
        from dynamic_retrieval.data.store import Store
        from dynamic_retrieval.semantic_pipeline import run_semantic_pipeline
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data,db=f.SemanticPipelineTests().fixture(root,count=2)
            output=root/'out'
            def rules(task):
                return dict(target_elements={'subject':task['market_id'],'action':'win'},element_aliases={})
            with Store(db) as store,patch('dynamic_retrieval.semantic_pipeline.automatic_rules',side_effect=rules):
                run_semantic_pipeline(store,data,f.CUTOFF,output,count=2,min_documents=1,
                    max_documents=2,client=f.FakeClient(),cache=root/'cache',repair_policies=True)
            for path in (output/'inputs/tasks').glob('*/task.json'):
                task=json.loads(path.read_text())
                targets=json.loads((path.parent/'target-elements.json').read_text())
                self.assertEqual(targets['target_elements'],task['target_elements'])

class AblationIsolationTests(unittest.TestCase):
    def test_disabled_variant_removes_source_policies(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from run_remediation import variant_task
        source=dict(TASK,matching_policy='typed_v2',scheduler_policy='grid_credit_v2',semantic_policy='fact_v3')
        baseline=variant_task(source,False,False,'typed_v3')
        self.assertNotIn('matching_policy',baseline);self.assertNotIn('scheduler_policy',baseline)
        self.assertEqual(baseline['semantic_policy'],'fact_v3')
        self.assertEqual(source['matching_policy'],'typed_v2')
        self.assertEqual(variant_task(source,True,False,'typed_v3')['matching_policy'],'typed_v3')
