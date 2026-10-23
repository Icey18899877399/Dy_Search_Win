"""Patent budget semantics; synthetic evidence is not a quality benchmark."""
import unittest
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from test_engine import TASK, document, annotations

POLICY = "patent_budget_v1"

class PatentBudgetTests(unittest.TestCase):
    def execute(self, docs=None, **kw):
        values=dict(rounds=3,total_budget=60,round_budget=999,
            initial_window_days=5,earliest_days=30,min_window_days=2,
            band_days=5,grid_days=5,band_fraction=.3,recovery_fraction=.1,
            high_loss=.1,low_loss=0,stable_distance=1)
        values.update(kw)
        docs=docs if docs is not None else [document('old','2026-06-12')]
        return run(TASK,docs,Config(**values),annotations(docs),budget_policy=POLICY)

    def test_affordable_positive_gain_full_band_ignores_legacy_fraction(self):
        out=self.execute(cost_per_day=1.2)
        row=out['rounds'][0]; rec=row['decision_trace']['recovery']
        self.assertEqual(row['action'],'expand')
        self.assertEqual(row['recovered_ids'],['old'])
        self.assertEqual(row['volume'],1)
        self.assertGreater(row['probabilities'][0],.9)
        self.assertEqual(out['rounds'][1]['boundary_before'],row['boundary_after'])
        self.assertAlmostEqual(row['budget']['recovery'],6)
        self.assertAlmostEqual(rec['full_required_budget'],6)
        self.assertAlmostEqual(rec['candidate_span_cost'],6)
        self.assertAlmostEqual(row['net_gain'],4)
        self.assertEqual(rec['query_overhead'],0)
        self.assertEqual(rec['read_reserve'],0)

    def test_negative_gain_and_unaffordable_band_have_distinct_denials(self):
        negative=self.execute(cost_per_day=1.2,conversion_cap=1)['rounds'][0]
        poor=self.execute(cost_per_day=4)['rounds'][0]
        self.assertEqual(negative['decision_trace']['recovery']['reason'],'negative_net_gain')
        self.assertEqual(poor['decision_trace']['recovery']['reason'],'insufficient_full_band_budget')
        for row in (negative,poor):
            self.assertEqual(row['action'],'hold')
            self.assertEqual(row['budget']['recovery'],0)

    def test_slow_round_keeps_full_effective_budget_and_counts_only_watch(self):
        out=self.execute(conversion_cap=.01)
        slow=[r for r in out['rounds'] if r['state_before']=='slow']
        self.assertTrue(slow)
        expected=0
        for row in slow:
            plan=row['decision_trace']['budget_plan']
            wait=row['decision_trace']['waiting_budget']
            self.assertAlmostEqual(plan['regular_baseline'],20)
            self.assertAlmostEqual(plan['effective'],20)
            self.assertLessEqual(row['budget']['watch'],8+1e-9)
            expected+=row['budget']['watch']
            self.assertAlmostEqual(wait['cumulative_spent'],expected)
            self.assertGreater(row['spent'],row['budget']['watch'])

    def test_budget_equations_and_remaining_recurrence(self):
        out=self.execute(cost_per_day=.4,shared_quota=.12)
        remaining=60
        for row in out['rounds']:
            plan=row['decision_trace']['budget_plan']; ledger=row['budget']
            self.assertAlmostEqual(plan['remaining_at_start'],remaining)
            self.assertLessEqual(sum(plan['reserves'].values()),plan['effective']+1e-9)
            self.assertLessEqual(ledger['watch']+ledger['recovery'],.12*remaining+1e-9)
            self.assertLessEqual(row['spent'],plan['effective']+1e-9)
            if row['state_before']!='slow':self.assertEqual(ledger['watch'],0)
            remaining-=row['spent']
            self.assertAlmostEqual(row['remaining'],remaining)

    def test_recovery_reads_complete_visible_band_without_duplicate_charging(self):
        docs=[document(str(i),'2026-06-12') for i in range(15)]
        out=self.execute(docs,cost_per_day=1)
        row=out['rounds'][0]
        self.assertEqual(row['action'],'expand')
        self.assertEqual(set(row['recovered_ids']),{d['id'] for d in docs})
        self.assertAlmostEqual(row['budget']['recovery'],5)
        self.assertEqual(out['diagnostics']['body_reads'],15)
        self.assertEqual(out['diagnostics']['cost_model'],'patent_inclusive_recovery_span_budget_units')

    def test_temporal_and_policy_boundaries(self):
        docs=[document('old','2026-06-12'),document('future','2026-06-21')]
        out=self.execute(docs)
        self.assertEqual(out['diagnostics']['excluded_temporal_or_foreign'],1)
        self.assertNotIn('future',{e['id'] for e in out['evidence']})
        with self.assertRaises(ValueError):
            run(TASK,[],budget_policy='unknown')
        with self.assertRaises(ValueError):
            self.execute(enable_uncertainty_expansion=True)

    def test_reconcile_final_sources_without_stranding_unused_regular_budget(self):
        specs=[('7','19','2'),('11','11','0'),('12','17','0'),('13','14','0'),
               ('14','16','2'),('15','12','2'),('16','18','1'),('17','19','1')]
        docs=[document(i,'2026-06-'+d,source) for i,d,source in specs]
        out=self.execute(docs,rounds=6,total_budget=120,stable_distance=0,cost_per_day=1,
            source_exhaustion=.5,convergence=.1,conversion_cap=100,coverage_scale=1,
            round_interval_days=1,source_confirmation_rounds=1)
        row=out['rounds'][3]
        self.assertEqual(row['action'],'expand')
        self.assertAlmostEqual(row['budget']['recovery'],5)
        self.assertEqual(row['decision_trace']['budget_plan']['final_recovery_sources'],['0'])
        for row in out['rounds']:
            plan=row['decision_trace']['budget_plan']
            self.assertLessEqual(sum(plan['reserves'].values()),plan['effective']+1e-9)
            for phase,cost in row['budget'].items():
                self.assertLessEqual(cost,plan['reserves'][phase]+1e-9)

    def test_cli_exposes_explicit_policy(self):
        from dynamic_retrieval.cli import parser
        args=parser().parse_args(['run','--market','demo','--cutoff',TASK['cutoff'],
            '--output','artifacts/unused','--budget-policy',POLICY])
        self.assertEqual(args.budget_policy,POLICY)

    def test_small_waiting_remainder_does_not_stop_other_affordable_phases(self):
        out=self.execute(rounds=5,total_budget=100,waiting_share=.001,conversion_cap=.01)
        slow=[r for r in out['rounds'] if r['state_before']=='slow']
        self.assertTrue(slow)
        caps=[]
        for row in slow:
            wait=row['decision_trace']['waiting_budget']
            self.assertEqual(row['budget']['watch'],0)
            self.assertEqual(wait['cumulative_spent'],0)
            self.assertGreater(row['spent'],0)
            caps.append(wait['locked_cap'])
        self.assertEqual(len(set(caps)),1)
        self.assertEqual(out['result']['termination_reason'],'round_limit')

    def test_zero_net_gain_and_shared_quota_boundary(self):
        row=self.execute(cost_per_day=1.2,conversion_cap=6,shared_quota=.1)['rounds'][0]
        self.assertEqual(row['action'],'expand')
        self.assertAlmostEqual(row['net_gain'],0)
        self.assertAlmostEqual(row['budget']['recovery'],6)
        row=self.execute(cost_per_day=1.2,shared_quota=.099)['rounds'][0]
        self.assertEqual(row['action'],'hold')
        self.assertEqual(row['decision_trace']['recovery']['reason'],'insufficient_full_band_budget')

    def test_on_demand_forwards_policy_before_any_model_request(self):
        from dynamic_retrieval.on_demand import run_on_demand
        from dynamic_retrieval.call_cost import CallCostLedger
        class NoNetworkClient:
            cost_ledger=CallCostLedger()
        out=run_on_demand(TASK,[],Config(),NoNetworkClient(),budget_policy=POLICY)
        self.assertEqual(out['provenance']['budget_policy'],POLICY)
        self.assertEqual(out['diagnostics']['model_calls']['events'],[])

if __name__=='__main__':unittest.main()
