import copy
import unittest
from unittest.mock import patch
from dynamic_retrieval import cli
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from test_engine import TASK, document, annotations
import test_source_cost_profile as profiles
from test_patent_grid import POLICY

class ExecutionInterfaceTests(unittest.TestCase):
    def test_cli_loads_profiles_and_only_enhanced_uses_grid(self):
        args=cli.parser().parse_args(['compare','--market','x','--cutoff',TASK['cutoff'],
            '--output','unused','--budget-policy','patent_budget_v1',
            '--grid-policy','grid.json','--source-cost-profile','cost.json'])
        with patch.object(cli,'read_json',side_effect=lambda p: POLICY if str(p)=='grid.json' else {'profile':'supplied'}):
            for mode in ['fixed','basic','enhanced']:
                opts=cli.execution_options(args,mode)
                self.assertEqual(opts['budget_policy'],'patent_budget_v1')
                self.assertEqual(opts['grid_policy'],POLICY if mode=='enhanced' else None)
                self.assertEqual(opts['source_cost_profile'],{'profile':'supplied'})
    def test_engine_profile_applies_global_costs_and_does_not_mutate_input(self):
        profile=profiles.SourceCostProfileTests().profile();profile['base_cost']=.1
        for row in profile['observations']:row['measurement_kind']='synthetic'
        before=copy.deepcopy(profile)
        docs=[document('a1','2026-06-12','a'),document('b1','2026-06-12','b')]
        result=run(TASK,docs,Config(rounds=2,total_budget=40,initial_source_limit=1),annotations(docs),
            budget_policy='patent_budget_v1',grid_policy=POLICY,source_cost_profile=profile)
        self.assertEqual(profile,before)
        costs=result['provenance']['source_parameters']
        self.assertAlmostEqual(costs['a']['cost_per_day'],.026)
        self.assertAlmostEqual(costs['b']['cost_per_day'],.074)
        self.assertAlmostEqual(result['diagnostics']['budget_feasibility']['source_cost_sum_per_day'],.026)
        self.assertFalse(result['diagnostics']['source_cost_profile']['empirical_calibration'])
    def test_invalid_profile_never_reaches_extraction_provider(self):
        profile=profiles.SourceCostProfileTests().profile();calls=[]
        with self.assertRaises(ValueError):
            run(TASK,[document('a1','2026-06-12','a')],Config(),
                annotation_provider=lambda *a:calls.append(a),budget_policy='patent_budget_v1',source_cost_profile=profile)
        self.assertEqual(calls,[])
    def test_on_demand_forwards_policy_without_external_call(self):
        from dynamic_retrieval.on_demand import run_on_demand
        from dynamic_retrieval.call_cost import CallCostLedger
        from types import SimpleNamespace
        client=SimpleNamespace(cost_ledger=CallCostLedger())
        with patch('dynamic_retrieval.on_demand.run',return_value={'diagnostics':{}}) as runner:
            run_on_demand(TASK,[],Config(),client,budget_policy='patent_budget_v1',grid_policy=POLICY,
                source_cost_profile={'profile':'supplied'})
            self.assertEqual(runner.call_args.kwargs['grid_policy'],POLICY)
            self.assertEqual(runner.call_args.kwargs['source_cost_profile'],{'profile':'supplied'})
