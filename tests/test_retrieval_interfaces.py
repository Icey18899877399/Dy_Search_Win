import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from dynamic_retrieval import cli
from dynamic_retrieval.models import Config
from dynamic_retrieval.web_jobs import validated_execution
from test_feasible_retrieval import GRID,POLICY
from test_engine import TASK

class RetrievalInterfaceTests(unittest.TestCase):
    def test_cli_and_on_demand_forward_explicit_policy(self):
        args=cli.parser().parse_args(['run','--market','x','--cutoff',TASK['cutoff'],'--output','unused',
            '--budget-policy','patent_budget_v1','--retrieval-policy',POLICY,'--mode','fixed'])
        self.assertEqual(cli.execution_options(args,'fixed')['retrieval_policy'],POLICY)
        from dynamic_retrieval.on_demand import run_on_demand
        from dynamic_retrieval.call_cost import CallCostLedger
        with patch('dynamic_retrieval.on_demand.run',return_value={'diagnostics':{}}) as runner:
            run_on_demand(TASK,[],Config(mode='fixed'),SimpleNamespace(cost_ledger=CallCostLedger()),
                budget_policy='patent_budget_v1',retrieval_policy=POLICY)
            self.assertEqual(runner.call_args.kwargs['retrieval_policy'],POLICY)
    def test_web_preserves_policy_and_validates_before_queue(self):
        options=dict(budget_policy='patent_budget_v1',grid_policy=GRID,retrieval_policy=POLICY)
        result=validated_execution(options,Config())
        self.assertEqual(result['retrieval_policy'],POLICY)
        inherited=validated_execution(None,Config(),{'provenance':options})
        self.assertEqual(inherited['retrieval_policy'],POLICY)
        with self.assertRaisesRegex(ValueError,'fresh read'):
            validated_execution(dict(options,grid_policy=dict(GRID,width_fraction=.25,cap_fraction=.2)),Config())
        with self.assertRaises(ValueError):validated_execution({'retrieval_policy':POLICY},Config())
