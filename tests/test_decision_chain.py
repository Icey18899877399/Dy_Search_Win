"""Loss observation, recovery explanation and opt-in runtime policy regressions."""
import copy
import unittest
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from test_engine import TASK, document, annotations


def profile():
    return dict(evidence_span_days=3.,evidence_span_provenance='synthetic test spans',
        task_duration_days=20.,budget_unit='simulation_units',out_of_domain='clamp',
        table=[dict(urgency=u,budget=b,parameters=dict(slow_multiplier=4-u-b/200,
            waiting_share=.4-.05*u,shared_quota=.7-.1*u))
            for u in (0.,1.) for b in (0.,200.)])

class DecisionChainTests(unittest.TestCase):
    def config(self,**overrides):
        values=dict(rounds=3,total_budget=100,round_budget=20,initial_window_days=5,
            earliest_days=30,min_window_days=2,band_days=5,grid_days=5,
            high_loss=.1,low_loss=0,band_fraction=.3,recovery_fraction=.4,stable_distance=0)
        values.update(overrides);return Config(**values)

    def test_trace_separates_pre_observation_from_post_recovery(self):
        docs=[document('old','2026-06-12')]
        out=run(TASK,docs,self.config(),annotations(docs),decision_trace=True)
        row=next(r for r in out['rounds'] if r['action']=='expand')
        trace=row['decision_trace'];loss=trace['loss_observation']
        self.assertEqual(loss['window_volume'],0.)
        self.assertEqual(loss['loss'],1.)
        self.assertEqual(sum(e['contribution'] for e in loss['band_evidence']),loss['loss'])
        self.assertEqual(row['volume'],1.)
        self.assertEqual(trace['recovery']['reason'],'approved')
        self.assertIn('old',trace['boundary_adjustment']['entered_ids'])
        self.assertEqual(trace['recovery']['sources'][0]['source_id'],'paper')

    def test_budget_denial_explains_overhead_and_preserves_probability(self):
        docs=[document('old','2026-06-12')]
        out=run(TASK,docs,self.config(rounds=1,round_budget=4,recovery_fraction=.1,
            band_fraction=.5),annotations(docs),decision_trace=True)
        rec=out['rounds'][0]['decision_trace']['recovery']
        self.assertEqual(rec['reason'],'insufficient_recovery_budget')
        self.assertEqual(rec['candidate_width_days'],0.)
        self.assertLess(rec['available_budget'],rec['query_overhead']+rec['read_reserve'])
        self.assertEqual(out['result']['probabilities'],[.5,.5])

    def test_trace_mode_cannot_change_default_scheduling(self):
        docs=[document('old','2026-06-12'),document('new','2026-06-18')]
        expected=run(TASK,docs,self.config(),annotations(docs))
        actual=run(TASK,docs,self.config(),annotations(docs),decision_trace=True)
        self.assertEqual(expected['result'],actual['result'])
        self.assertEqual(expected['evidence'],actual['evidence'])
        for before,after in zip(expected['rounds'],actual['rounds']):
            self.assertEqual(before,{k:v for k,v in after.items() if k!='decision_trace'})

    def test_contraction_identifies_discarded_known_evidence(self):
        docs=[document('old','2026-06-12')]
        out=run(TASK,docs,self.config(mode='basic',rounds=5),annotations(docs),decision_trace=True)
        removed=[r['decision_trace']['boundary_adjustment']['removed_ids'] for r in out['rounds']]
        self.assertTrue(any('old' in ids for ids in removed))

    def test_runtime_parameters_are_applied_and_waiting_cap_stays_locked(self):
        p=profile();before=copy.deepcopy(p)
        out=run(TASK,[],self.config(rounds=5),runtime_policy=p)
        self.assertEqual(p,before)
        first,second=out['rounds'][:2]
        t1=first['decision_trace']['runtime_parameters'];t2=second['decision_trace']['runtime_parameters']
        self.assertAlmostEqual(t1['urgency'],3/20)
        self.assertAlmostEqual(t2['urgency'],3/19)
        self.assertAlmostEqual(second['virtual_days']-first['virtual_days'],t2['parameters']['slow_multiplier'])
        cap=first['decision_trace']['waiting_budget']['locked_cap']
        self.assertAlmostEqual(cap,first['remaining']*t1['parameters']['waiting_share'])
        self.assertTrue(all(r['decision_trace']['waiting_budget']['locked_cap']==cap for r in out['rounds']))
        self.assertEqual(out['provenance']['runtime_policy']['calibration_status'],'supplied_unvalidated')

    def test_task_deadline_stops_clock_without_opening_new_evidence_dates(self):
        p=profile();p['task_duration_days']=2.
        out=run(TASK,[],self.config(rounds=20),runtime_policy=p)
        self.assertEqual(out['result']['termination_reason'],'task_deadline_reached')
        self.assertEqual(out['rounds'][-1]['virtual_days'],2.)
        self.assertEqual(out['task']['cutoff'],TASK['cutoff'])
        self.assertEqual(out['rounds'][-1]['state'],'stop')

    def test_invalid_runtime_policy_rejected_before_extraction(self):
        p=profile();p['evidence_span_provenance']=''
        calls=[]
        with self.assertRaises(ValueError):
            run(TASK,[document('a','2026-06-18')],self.config(),runtime_policy=p,
                annotation_provider=lambda t,d:calls.append(d))
        self.assertEqual(calls,[])

    def test_low_loss_hold_explains_incomplete_transition_probing(self):
        task=dict(TASK,scheduler_policy='grid_credit_v2')
        docs=[document('old','2026-06-12')]
        out=run(task,docs,self.config(rounds=1,round_budget=4,grid_days=1,
            band_fraction=.25,recovery_fraction=.25),annotations(docs),decision_trace=True)
        row=out['rounds'][0];trace=row['decision_trace']['contraction']
        self.assertEqual(row['action'],'hold')
        self.assertTrue(trace['low_loss_passed'])
        self.assertEqual(trace['reason'],'pending_transition_probes')
        self.assertEqual(trace['pending_probe_count'],1)
        self.assertFalse(trace['probe_complete'])
        self.assertFalse(trace['executed'])

    def test_contraction_records_candidate_step_and_boundary_limit(self):
        out=run(TASK,[],self.config(rounds=5),decision_trace=True)
        selected=out['rounds'][0]['decision_trace']['contraction']
        self.assertEqual(selected['reason'],'approved')
        self.assertTrue(selected['executed'])
        self.assertEqual(selected['candidate_step_days'],1.25)
        final=out['rounds'][-1]['decision_trace']['contraction']
        self.assertEqual(final['reason'],'boundary_limit_reached')
        self.assertEqual(final['candidate_step_days'],0.)
        self.assertEqual(final['upper_boundary'],'2026-06-18T00:00:00+00:00')
        self.assertIsNone(final['return_ceiling'])

    def test_basic_full_band_gain_basis_is_distinct_from_candidate_span(self):
        docs=[document('old','2026-06-11')]
        out=run(TASK,docs,self.config(mode='basic',rounds=1,cost_per_day=2),
            annotations(docs),decision_trace=True)
        row=out['rounds'][0];rec=row['decision_trace']['recovery']
        self.assertEqual(row['action'],'expand')
        self.assertEqual(rec['loss_basis'],'full_band_basic_comparator')
        self.assertEqual(rec['candidate_span_observed_loss'],0.)
        self.assertEqual(rec['candidate_covered_loss'],1.)
        self.assertFalse(rec['net_gain_required'])

class OnDemandChainTests(unittest.TestCase):
    def test_runtime_policy_reaches_on_demand_scheduler_without_calls(self):
        from dynamic_retrieval.call_cost import CallCostLedger
        from dynamic_retrieval.on_demand import run_on_demand
        class NoNetworkClient:
            def __init__(self): self.cost_ledger=CallCostLedger()
            def complete_json(self,*args,**kwargs): raise AssertionError('No documents')
        client=NoNetworkClient()
        out=run_on_demand(TASK,[],Config(rounds=3),client,runtime_policy=profile())
        self.assertEqual(out['rounds'][0]['decision_trace']['runtime_parameters']['status'],'supplied_table_interpolation')
        self.assertEqual(out['diagnostics']['model_calls']['network_attempts'],0)
        plain=run_on_demand(TASK,[],Config(rounds=1),NoNetworkClient(),decision_trace=True)
        self.assertIn('decision_trace',plain['rounds'][0])
