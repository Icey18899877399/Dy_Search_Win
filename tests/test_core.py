import math
import unittest

from dynamic_retrieval.core import (relevance, independent_weights, probabilities,
    survival, exhaustion, coverage, loss_ratio, transition_cells, can_stop, total_variation)


class CoreTests(unittest.TestCase):
    def test_relevance_is_typed_target_intersection(self):
        target = dict(subject='alice', action='win', object='election', time='2026', location='x')
        self.assertAlmostEqual(relevance(dict(subject='alice', action='win', object='election'), target), .6)
        self.assertEqual(relevance({'object': 'alice'}, {'subject': 'alice'}), 0)
        with self.assertRaises(ValueError): relevance({}, {})

    def test_cross_region_duplicates_share_one_rank_and_tie_break(self):
        rows = [dict(id='c', source_id='c', published_at='2026-01-03', elements={'subject':'x'}),
                dict(id='b', source_id='b', published_at='2026-01-01', elements={'subject':'x'}),
                dict(id='a', source_id='a', published_at='2026-01-01', elements={'subject':'x'})]
        self.assertEqual(independent_weights(rows,.5), {'a':1.,'b':.5,'c':.25})

    def test_publication_rank_compares_instants_not_timezone_strings(self):
        rows=[dict(id='early',source_id='a',published_at='2026-01-02T01:00:00+14:00',elements={'subject':'x'}),
              dict(id='late',source_id='b',published_at='2026-01-01T20:00:00+00:00',elements={'subject':'x'})]
        self.assertEqual(independent_weights(rows,.5),{'early':1.,'late':.5})

    def test_support_weighting_and_no_evidence_uniform(self):
        self.assertEqual(probabilities([], {}, 2, 2), [.5,.5])
        rows=[dict(id='a',support=[1,-1]),dict(id='b',support=[-1,1])]
        got=probabilities(rows, {'a':1,'b':.5}, 2, 3)
        self.assertAlmostEqual(got[0], .8807970779778823)
        self.assertAlmostEqual(sum(got),1)
        self.assertTrue(all(math.isfinite(x) for x in probabilities(rows,{'a':1,'b':0},2,1000)))

    def test_survival_and_coverage_correct_at_zero_and_tail(self):
        self.assertEqual(survival([2,4,8],4,1),.5)
        self.assertEqual(coverage(0,2),0)
        self.assertAlmostEqual(coverage(2,2),1-math.exp(-1))
        self.assertEqual(exhaustion([],100,3),0)
        self.assertEqual(exhaustion([2,4,8],9,2),1)

    def test_sample_gap_cannot_prematurely_exhaust_source(self):
        self.assertAlmostEqual(exhaustion([10,20],1,2), .05)
        self.assertAlmostEqual(exhaustion([2,4],3,2,mode='basic'), .6)

    def test_transition_grid_covers_partial_remainder_without_gap(self):
        cells=transition_cells(10,5,2,10,1)
        self.assertEqual([(c['start'],c['end']) for c in cells],[(9,10),(7,9),(5,7)])
        self.assertGreater(cells[0]['budget'],cells[-1]['budget'])
        self.assertGreater(cells[-1]['budget'],0)
        self.assertEqual(loss_ratio(0,0),0)
        self.assertAlmostEqual(loss_ratio(2,6),.25)

    def test_minimum_source_gate_and_absolute_multiround_deltas(self):
        self.assertFalse(can_stop([.99,.1],[0,0],.9,.1))
        self.assertFalse(can_stop([.99,.99],[0,-2],.9,.1))
        self.assertTrue(can_stop([.99,.99],[0,.05],.9,.1))
        self.assertTrue(can_stop([], [0], .9,.1))
        self.assertAlmostEqual(total_variation([.8,.2],[.2,.8]),.6)


if __name__ == '__main__': unittest.main()
