import inspect,unittest
from copy import deepcopy
from dynamic_retrieval.engine import run
from dynamic_retrieval.demo import demo_inputs
from dynamic_retrieval.models import Config

class ObserverTests(unittest.TestCase):
    def test_observer_reports_each_completed_round_without_changing_prediction(self):
        self.assertIn('observer',inspect.signature(run).parameters,'Need non-mutating round observer')
        task,docs,annotations=demo_inputs()
        config=Config(rounds=5)
        expected=run(task,docs,config,annotations)
        seen=[]
        actual=run(task,docs,config,annotations,observer=lambda row:seen.append(row))
        self.assertEqual(actual,expected)
        self.assertEqual(seen,actual['rounds'])
    def test_observer_cannot_mutate_engine_result(self):
        self.assertIn('observer',inspect.signature(run).parameters)
        task,docs,annotations=demo_inputs()
        config=Config(rounds=3)
        expected=run(task,docs,config,annotations)
        def observer(row):
            row['probabilities'][0]=999
            row['source_states'].clear()
        actual=run(task,docs,config,annotations,observer=observer)
        self.assertEqual(actual,expected)
if __name__=='__main__':unittest.main()
