"""Literal per-grid allocation and visible budget constraints."""
import math
import unittest
from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from test_engine import TASK, document, annotations
POLICY=dict(version='patent_grid_v1',cap_fraction=.2,width_fraction=.25)

class PatentGridTests(unittest.TestCase):
    def execute(self,docs=None,**options):
        docs=docs if docs is not None else [document('old','2026-06-12')]
        vals=dict(rounds=3,total_budget=60,initial_window_days=5,earliest_days=30,
            min_window_days=2,band_days=5,grid_days=5,high_loss=.1,low_loss=0)
        vals.update(options)
        return run(TASK,docs,Config(**vals),annotations(docs),budget_policy='patent_budget_v1',grid_policy=POLICY)

    def test_formula_and_nominal_band_fraction_are_literal(self):
        row=self.execute()['rounds'][0]
        grids=row['decision_trace']['grid_budget']['cells']
        self.assertEqual(len(grids),4)
        for i,cell in enumerate(grids):
            self.assertAlmostEqual(cell['nominal_budget'],4*math.exp(-(i+.5)/4))
            self.assertAlmostEqual(cell['end']-cell['start'],1.25)
            self.assertAlmostEqual(cell['distance'],(.5+i)*1.25)
        self.assertAlmostEqual(row['decision_trace']['budget_plan']['reserves']['probe'],sum(c['allocated_budget'] for c in grids))
        self.assertGreater(sum(c['nominal_budget'] for c in grids),5)
        self.assertEqual(row['decision_trace']['grid_budget']['cross_round_credit'],False)

    def test_costs_never_exceed_per_grid_formula_and_remaining_budget(self):
        docs=[document(str(i),'2026-06-12') for i in range(8)]
        out=self.execute(docs)
        for row in out['rounds']:
            grid=row['decision_trace']['grid_budget']
            for c in grid['cells']:
                self.assertLessEqual(c['spent'],c['allocated_budget']+1e-8)
                self.assertLessEqual(c['allocated_budget'],c['nominal_budget']+1e-8)
            self.assertAlmostEqual(sum(c['spent'] for c in grid['cells']),row['budget']['probe'])

    def test_rejects_incompatible_config_before_provider_call(self):
        called=[]
        docs=[document('old','2026-06-12')]
        with self.assertRaisesRegex(ValueError,'grid.*budget'):
            run(TASK,docs,Config(),annotation_provider=lambda *args:called.append(1),
                budget_policy='patent_budget_v1',grid_policy=dict(POLICY,cap_fraction=.4))
        self.assertEqual(called,[])
        for policy in ({'version':'unknown'},dict(POLICY,cap_fraction=True),dict(POLICY,width_fraction=.00001)):
            with self.assertRaises(ValueError):
                run(TASK,[],Config(),budget_policy='patent_budget_v1',grid_policy=policy)
        with self.assertRaises(ValueError):run(TASK,[],grid_policy=POLICY)
        with self.assertRaises(ValueError):
            run(TASK,[],Config(mode='basic'),budget_policy='patent_budget_v1',grid_policy=POLICY)

    def test_archive_horizon_does_not_redefine_nominal_width(self):
        row=self.execute(earliest_days=7)['rounds'][0]
        cells=row['decision_trace']['grid_budget']['cells']
        self.assertEqual(len(cells),4)
        self.assertAlmostEqual(cells[0]['nominal_budget'],4*math.exp(-.125))
        self.assertTrue(any(c['reason']=='outside_archive_horizon' for c in cells))
        self.assertTrue(all(c['search_start']>=row['decision_trace']['grid_budget']['earliest'] for c in cells if c['allocated_budget']))

    def test_grid_geometry_is_translation_invariant_and_no_phantom_cells(self):
        from dynamic_retrieval.grid_budget import plan_grid_budget
        for band,fraction,count in [(1,.1,10),(3,.2,5),(10,.001,1000),(5,.3,4)]:
            policy=dict(POLICY,width_fraction=fraction,cap_fraction=.0001)
            plans=[plan_grid_budget(boundary=b,earliest=b-band*2,band_days=band,
                baseline=20,decay=1,policy=policy,available=20) for b in [1,20619]]
            self.assertEqual([len(p['cells']) for p in plans],[count,count])
            self.assertEqual([c['nominal_budget'] for c in plans[0]['cells']],
                             [c['nominal_budget'] for c in plans[1]['cells']])
            self.assertTrue(all(c['end']>c['start'] for c in plans[1]['cells']))
            self.assertAlmostEqual(sum(c['end']-c['start'] for c in plans[1]['cells']),band)

    def test_pure_plan_round_shortfall_skips_without_renormalizing(self):
        from dynamic_retrieval.grid_budget import plan_grid_budget
        plan=plan_grid_budget(boundary=100,earliest=0,band_days=4,baseline=20,
            decay=1,policy=POLICY,available=4)
        funded=[c for c in plan['cells'] if c['allocated_budget']]
        self.assertEqual(len(funded),1)
        self.assertAlmostEqual(funded[0]['allocated_budget'],4*math.exp(-.125))
        self.assertTrue(all(c['allocated_budget'] in (0,c['nominal_budget']) for c in plan['cells']))
        self.assertLessEqual(plan['total_allocated'],4)

if __name__=='__main__':unittest.main()
