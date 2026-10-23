"""Explicit whole-band comparator; fixtures are synthetic scheduling evidence."""
import hashlib
import json
import unittest
from dynamic_retrieval.engine import run, day
from dynamic_retrieval.models import Config
from dynamic_retrieval.call_cost import CallCostLedger
from dynamic_retrieval.on_demand import run_on_demand
from test_engine import TASK, document, annotations

POLICY='patent_full_band_v1'

class FullBandTests(unittest.TestCase):
    def config(self, **kw):
        values=dict(rounds=1,total_budget=100,round_budget=20,initial_window_days=5,
            earliest_days=30,min_window_days=2,band_days=5,grid_days=5,high_loss=.1,
            low_loss=0,band_fraction=.3,recovery_fraction=.4,stable_distance=0)
        values.update(kw)
        return Config(**values)

    def execute(self, docs=None, **kw):
        docs=docs if docs is not None else [document('old','2026-06-12')]
        return run(TASK,docs,self.config(**kw),annotations(docs),recovery_policy=POLICY)

    def test_full_band_changes_next_boundary_and_current_probability(self):
        for mode in ('basic','enhanced'):
            with self.subTest(mode=mode):
                out=self.execute(mode=mode,rounds=2)
                row=out['rounds'][0];rec=row['decision_trace']['recovery']
                self.assertEqual(row['action'],'expand')
                self.assertEqual(row['boundary_before'],'2026-06-15T00:00:00+00:00')
                self.assertEqual(row['boundary_after'],'2026-06-10T00:00:00+00:00')
                self.assertEqual(out['rounds'][1]['boundary_before'],row['boundary_after'])
                self.assertEqual(row['recovered_ids'],['old'])
                self.assertEqual(row['volume'],1)
                self.assertGreater(row['probabilities'][0],.9)
                self.assertEqual(rec['requested_full_width_days'],5)
                self.assertAlmostEqual(rec['full_required_budget'],1.45)
                self.assertEqual(rec['actual_recovery_step_days'],5)
                self.assertEqual(rec['loss_basis'],'full_transition_band')
                self.assertEqual(rec['effective_policy'],POLICY)
                self.assertIsNone(rec['block_reason'])
                self.assertEqual(out['provenance']['recovery_policy'],POLICY)

    def test_no_partial_fallback_when_full_band_cannot_be_afforded(self):
        docs=[document('old','2026-06-12')]
        for mode in ('basic','enhanced'):
            with self.subTest(mode=mode):
                legacy=run(TASK,docs,self.config(mode=mode,cost_per_day=2),annotations(docs))
                self.assertEqual(legacy['rounds'][0]['action'],'expand')
                row=self.execute(docs,mode=mode,cost_per_day=2)['rounds'][0]
                rec=row['decision_trace']['recovery']
                self.assertEqual(row['action'],'hold')
                self.assertEqual(row['boundary_before'],row['boundary_after'])
                self.assertEqual(row['budget']['recovery'],0)
                self.assertEqual(rec['candidate_width_days'],0)
                self.assertEqual(rec['actual_recovery_step_days'],0)
                self.assertAlmostEqual(rec['full_required_budget'],11.2)
                self.assertEqual(rec['block_reason'],'insufficient_full_band_budget')

    def test_basic_and_enhanced_both_reject_negative_full_band_gain(self):
        for mode in ('basic','enhanced'):
            with self.subTest(mode=mode):
                row=self.execute(mode=mode,round_budget=50,cost_per_day=3)['rounds'][0]
                rec=row['decision_trace']['recovery']
                self.assertEqual(row['action'],'hold')
                self.assertEqual(row['net_gain'],-5)
                self.assertEqual(rec['candidate_covered_loss'],1)
                self.assertEqual(rec['candidate_net_gain'],-5)
                self.assertTrue(rec['net_gain_required'])
                self.assertEqual(rec['block_reason'],'negative_net_gain')

    def test_zero_net_gain_is_accepted(self):
        row=self.execute(mode='basic',conversion_cap=.25)['rounds'][0]
        self.assertEqual(row['action'],'expand')
        self.assertEqual(row['net_gain'],0)

    def test_full_band_rejected_when_archive_horizon_truncates_nominal_band(self):
        row=self.execute(earliest_days=8)['rounds'][0]
        rec=row['decision_trace']['recovery']
        self.assertEqual(row['action'],'hold')
        self.assertEqual(row['boundary_after'],'2026-06-15T00:00:00+00:00')
        self.assertEqual(rec['requested_full_width_days'],5)
        self.assertEqual(rec['available_archive_width_days'],3)
        self.assertAlmostEqual(rec['full_required_budget'],1.45)
        self.assertEqual(rec['actual_recovery_step_days'],0)
        self.assertEqual(rec['candidate_width_days'],0)
        self.assertEqual(rec['block_reason'],'insufficient_archive_horizon')
        self.assertTrue(rec['clipped_by_earliest_boundary'])
        self.assertTrue(rec['clipped_by_archive_horizon'])
        self.assertFalse(rec['nominal_full_band'])
        self.assertEqual(row['recovered_ids'],[])

    def test_decimal_full_band_at_archive_horizon_is_not_rejected_for_roundoff(self):
        doc=document('decimal','2026-06-14')
        doc['published_at']='2026-06-14T23:00:00Z'
        for earliest in (5.1,5.1-5e-10):
            with self.subTest(earliest_days=earliest):
                row=self.execute([doc],earliest_days=earliest,initial_window_days=5,
                    band_days=.1,grid_days=.1)['rounds'][0]
                rec=row['decision_trace']['recovery']
                self.assertEqual(row['action'],'expand')
                self.assertEqual(row['recovered_ids'],['decimal'])
                self.assertEqual(rec['candidate_width_days'],.1)
                self.assertAlmostEqual(rec['actual_recovery_step_days'],.1,delta=1e-9)
                self.assertGreaterEqual(day(row['boundary_after']),day(TASK['cutoff'])-earliest-1e-11)
                self.assertTrue(rec['nominal_full_band'])
                self.assertFalse(rec['clipped_by_archive_horizon'])
                self.assertFalse(rec['clipped_by_earliest_boundary'])
                self.assertIsNone(rec['block_reason'])

    def test_decimal_band_with_real_archive_shortage_is_still_rejected(self):
        doc=document('decimal','2026-06-14')
        doc['published_at']='2026-06-14T23:00:00Z'
        row=self.execute([doc],earliest_days=5.1-5e-8,initial_window_days=5,
            band_days=.1,grid_days=.1)['rounds'][0]
        rec=row['decision_trace']['recovery']
        self.assertEqual(row['action'],'hold')
        self.assertEqual(row['boundary_after'],row['boundary_before'])
        self.assertEqual(rec['candidate_width_days'],0)
        self.assertEqual(rec['actual_recovery_step_days'],0)
        self.assertEqual(rec['block_reason'],'insufficient_archive_horizon')
        self.assertFalse(rec['nominal_full_band'])
        self.assertTrue(rec['clipped_by_archive_horizon'])

    def test_cooldown_applies_to_explicit_basic_comparator(self):
        docs=[document('a','2026-06-12'),document('b','2026-06-07'),document('c','2026-06-03')]
        out=self.execute(docs,mode='basic',rounds=10)
        expanded=[r['round'] for r in out['rounds'] if r['action']=='expand']
        self.assertGreaterEqual(len(expanded),2)
        self.assertTrue(all(b-a>3 for a,b in zip(expanded,expanded[1:])))
        self.assertEqual(out['rounds'][1]['decision_trace']['recovery']['block_reason'],'cooldown')
        rec=out['rounds'][1]['decision_trace']['recovery']
        self.assertEqual(rec['candidate_net_gain'],out['rounds'][0]['frozen_net_gain'])
        self.assertEqual(rec['net_gain_status'],'frozen_during_cooldown')
        self.assertIsNone(out['rounds'][1]['net_gain'])

    def test_full_budget_counts_all_eligible_sources_and_one_read_reserve(self):
        docs=[document('a','2026-06-12','one'),document('b','2026-06-12','two')]
        row=self.execute(docs)['rounds'][0]
        rec=row['decision_trace']['recovery']
        self.assertAlmostEqual(rec['full_required_budget'],1.9)
        self.assertAlmostEqual(rec['query_overhead'],.4)
        self.assertEqual(rec['read_reserve'],1)

    def test_unknown_policy_and_uncertainty_bypass_rejected_before_provider(self):
        for policy,cfg in [('unknown',self.config()),(POLICY,self.config(enable_uncertainty_expansion=True))]:
            calls=[]
            with self.subTest(policy=policy),self.assertRaises(ValueError):
                run(TASK,[document('old','2026-06-12')],cfg,
                    annotation_provider=lambda t,d:calls.append(d),recovery_policy=policy)
            self.assertEqual(calls,[])

    def test_on_demand_forwards_policy_and_rejects_invalid_before_model_call(self):
        class NoNetworkClient:
            def __init__(self):self.cost_ledger=CallCostLedger()
            def complete_json(self,*args,**kw):raise AssertionError('Must not call model')
        out=run_on_demand(TASK,[],self.config(),NoNetworkClient(),recovery_policy=POLICY)
        self.assertEqual(out['provenance']['recovery_policy'],POLICY)
        self.assertEqual(out['rounds'][0]['decision_trace']['recovery']['effective_policy'],POLICY)
        with self.assertRaises(ValueError):
            run_on_demand(TASK,[document('old','2026-06-12')],self.config(),NoNetworkClient(),recovery_policy='unknown')

    def test_none_preserves_complete_legacy_outputs_including_phase13_trace(self):
        # Frozen before this change: six complete engine outputs, not trace-stripped subsets.
        hashes={('fixed',False):'4bc2669f8eebbd1943848223dacf06d0acdb082e2c345a26710c119f0f31e00d',
            ('fixed',True):'b8b5d90d1e2dd6c4895bd73dedc2bc0924bec27263cd3d2cbf9caca28db46167',
            ('basic',False):'fe180602b639313259e23afce987252253342fa93473cb5964b719c2cbaff2b0',
            ('basic',True):'fc12ecec33d7971c4b4507078c24c5a00b99cad4d60140a0bd890db2711438df',
            ('enhanced',False):'6a9c6c01b27253db3080fa40e7306db4fa39d1a12ae3b0c96ea02f8e6d72b598',
            ('enhanced',True):'40734ad9c74a6a9659b8df0d715120015ceb8ae40f238f1c380ecbf7fd27bdda'}
        docs=[document('old','2026-06-12'),document('older','2026-06-07'),document('new','2026-06-18')]
        for (mode,trace),expected in hashes.items():
            with self.subTest(mode=mode,trace=trace):
                out=run(TASK,docs,self.config(mode=mode,rounds=5),annotations(docs),decision_trace=trace,recovery_policy=None)
                self.assertEqual(hashlib.sha256(json.dumps(out,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),expected)
                self.assertEqual(out,run(TASK,docs,self.config(mode=mode,rounds=5),annotations(docs),decision_trace=trace))

if __name__=='__main__':unittest.main()
