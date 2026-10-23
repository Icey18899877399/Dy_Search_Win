import copy
import importlib.util
import unittest
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from test_engine import TASK,document,annotations

GRID=dict(version='patent_grid_v1',cap_fraction=.31,width_fraction=.5)
POLICY='bm25_read_guard_v1'

class FeasibleRetrievalTests(unittest.TestCase):
    def test_unexecutable_grid_rejected_before_provider_or_ranking(self):
        calls=[]
        with self.assertRaisesRegex(ValueError,'fresh read'):
            run(TASK,[document('x','2026-06-12')],Config(),annotation_provider=lambda *a:calls.append(a),
                budget_policy='patent_budget_v1',grid_policy=dict(GRID,cap_fraction=.2,width_fraction=.25),retrieval_policy=POLICY)
        self.assertEqual(calls,[])
    def test_partial_request_cannot_afford_body_never_debits_query(self):
        docs=[document('x','2026-06-18')]
        out=run(TASK,docs,Config(mode='fixed',rounds=2,total_budget=2.4),annotations(docs),
            budget_policy='patent_budget_v1',retrieval_policy='read_guard_v1')
        self.assertEqual(out['diagnostics']['body_reads'],1)
        self.assertAlmostEqual(out['result']['spent'],1.2)
        self.assertEqual(out['rounds'][1]['spent'],0)
        self.assertEqual(out['rounds'][1]['decision_trace']['read_execution']['requests_executed'],0)
    def test_remaining_fragment_does_not_charge_next_source(self):
        docs=[document('a','2026-06-18','a'),document('b','2026-06-18','b')]
        out=run(TASK,docs,Config(mode='fixed',rounds=1,total_budget=1.3),annotations(docs),
            budget_policy='patent_budget_v1',retrieval_policy='read_guard_v1')
        self.assertAlmostEqual(out['result']['spent'],1.2)
        self.assertEqual(out['diagnostics']['body_reads'],1)
        events=out['rounds'][0]['decision_trace']['read_execution']['skipped']
        self.assertTrue(any(e['reason']=='insufficient_request_and_read_budget' for e in events))
    def test_ranker_finds_body_fact_and_keeps_original_annotation_input(self):
        bad=document('a_bad','2026-06-18');bad.update(title='Alice report',text='Traffic weather bulletin.')
        good=document('z_good','2026-06-17');good.update(title='Official bulletin',text='weather '*500+' Alice won election final result Alice win election.')
        docs=[bad,good];before=copy.deepcopy(docs)
        out=run(TASK,docs,Config(mode='fixed',rounds=1,total_budget=1.2),annotations(docs),
            budget_policy='patent_budget_v1',retrieval_policy=POLICY)
        self.assertEqual(out['rounds'][0]['retrieved_ids'],['z_good'])
        ev=out['rounds'][0]['decision_trace']['retrieval_events'][0]
        span=ev['candidate_rank'];self.assertGreater(span['start_char'],0)
        self.assertIn('Alice',good['text'][span['start_char']:span['end_char']])
        self.assertEqual(docs,before)
    def test_scope_does_not_import_foreign_future_or_outside_window(self):
        valid=document('valid','2026-06-18');valid['title']='neutral'
        foreign=document('foreign','2026-06-18');foreign['event_id']='else'
        future=document('future','2026-06-21')
        outside=document('outside','2026-05-01')
        missing=document('missing','2026-06-18');missing.pop('observed_at')
        docs=[valid,foreign,future,outside,missing]
        out=run(TASK,docs,Config(mode='fixed',rounds=1,total_budget=10),annotations(docs),
            budget_policy='patent_budget_v1',retrieval_policy=POLICY)
        self.assertEqual(out['rounds'][0]['retrieved_ids'],['valid'])
        self.assertEqual(out['diagnostics']['retrieval_execution']['indexed_document_ids'],['valid'])
    def test_annotations_never_change_candidate_order(self):
        docs=[document('a','2026-06-18'),document('b','2026-06-18')]
        options=dict(budget_policy='patent_budget_v1',retrieval_policy=POLICY)
        a=run(TASK,docs,Config(mode='fixed',rounds=1,total_budget=1.2),annotations(docs),**options)
        flipped=annotations(docs);flipped['a']['support']=[-1,1];flipped['b']['support']=[1,-1]
        b=run(TASK,docs,Config(mode='fixed',rounds=1,total_budget=1.2),flipped,**options)
        self.assertEqual(a['rounds'][0]['retrieved_ids'],b['rounds'][0]['retrieved_ids'])
    def test_budget_formula_and_loss_accounting_not_replaced_by_rank_score(self):
        docs=[document('old','2026-06-12'),document('recent','2026-06-18')]
        out=run(TASK,docs,Config(rounds=3,total_budget=60,initial_window_days=5,band_days=5),annotations(docs),
            budget_policy='patent_budget_v1',grid_policy=GRID,retrieval_policy=POLICY)
        for row in out['rounds']:
            self.assertAlmostEqual(sum(row['budget'].values()),row['spent'])
            self.assertLessEqual(row['spent'],20+1e-8)
            cells=row['decision_trace']['grid_budget']['cells']
            self.assertTrue(all(c['spent']<=c['nominal_budget']+1e-8 for c in cells))
            obs=row['decision_trace']['loss_observation']
            self.assertAlmostEqual(obs['loss'],sum(x['contribution'] for x in obs['band_evidence']))
            self.assertIn('unread_band_documents',obs)
    def test_provider_receives_original_body_even_when_best_chunk_is_late(self):
        doc=document('late','2026-06-18');doc['text']='weather '*600+'Alice election final result'
        calls=[]
        def provider(task, received):
            calls.append(received)
            raise ValueError('intentional provider failure')
        result=run(TASK,[doc],Config(mode='fixed',rounds=1,total_budget=1.2),
            annotation_provider=provider,budget_policy='patent_budget_v1',retrieval_policy=POLICY)
        self.assertEqual(calls[0]['text'],doc['text'])
        self.assertEqual(result['diagnostics']['body_reads'],1)
        self.assertEqual(result['diagnostics']['admitted_documents'],0)
        self.assertEqual(result['rounds'][0]['decision_trace']['retrieval_events'][0]['status'],'extraction_failed')
    def test_scope_score_is_unchanged_by_excluded_document(self):
        doc=document('valid','2026-06-18');foreign=document('foreign','2026-06-18');foreign['event_id']='other'
        cfg=Config(mode='fixed',rounds=1,total_budget=1.2)
        def rank(ds):
            result=run(TASK,ds,cfg,annotations(ds),budget_policy='patent_budget_v1',retrieval_policy=POLICY)
            return result['rounds'][0]['decision_trace']['retrieval_events'][0]['candidate_rank']
        self.assertEqual(rank([doc]),rank([doc,foreign]))
    def test_policy_validation(self):
        for value in ['unknown',{},True]:
            with self.assertRaises(ValueError):run(TASK,[],retrieval_policy=value)
        with self.assertRaises(ValueError):run(TASK,[],retrieval_policy=POLICY)
        with self.assertRaises(ValueError):run(TASK,[],Config(),budget_policy='patent_budget_v1',retrieval_policy=POLICY)

if __name__=='__main__':unittest.main()
