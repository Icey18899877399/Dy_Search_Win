"""Synthetic offline patent acceptance cases; no model, network or label access.

Expected behaviors come from S102/S106/S107, S301-S404, and paragraphs
[0103]-[0107], [0184], [0225] of the supplied patent. Dates describe an
already frozen archive: a later retrieval is not a later publication.
"""
import math
import unittest

from dynamic_retrieval.engine import run
from dynamic_retrieval.models import Config
from test_engine import TASK, document, annotations


class PatentAcceptanceTests(unittest.TestCase):
    def distinct_facts(self, docs):
        marked = annotations(docs)
        for doc in docs:
            marked[doc['id']]['elements']['time'] = doc['published_at']
        return marked

    def test_waiting_new_fact_resumes_regular_search_without_new_archive_data(self):
        # Every fact contributes exactly one unit. Delayed retrieval adds a new
        # fact even when its direction leaves the probabilities unchanged.
        docs = [document(str(i), f'2026-06-{19-i:02d}') for i in range(8)]
        cfg = Config(rounds=8, initial_window_days=14, min_window_days=14,
                     round_budget=6, total_budget=100, epsilon=.01,
                     stable_distance=0, band_days=3, grid_days=3)
        out = run(TASK, docs, cfg, self.distinct_facts(docs))
        resumed = [r for r in out['rounds']
                   if r['state_before'] == 'slow' and r['state'] == 'continue']
        self.assertTrue(resumed, 'A new independent fact during watch must resume search')
        first = resumed[0]
        self.assertAlmostEqual(first['delta'], 1.)
        self.assertAlmostEqual(first['distance'], 0.)
        self.assertGreater(first['budget']['watch'], 0)
        self.assertEqual(first['budget']['window'], 0)
        previous = out['rounds'][first['round'] - 2]
        self.assertAlmostEqual(first['virtual_days'] - previous['virtual_days'], 3.)
        self.assertLessEqual(first['spent'], cfg.round_budget * cfg.slow_fraction)
        source = first['source_states']['paper']
        self.assertEqual(source['silence'], 0)
        self.assertEqual(source['last_new_round'], first['round'])

    def test_retired_source_keeps_evidence_and_watch_can_reactivate_it(self):
        # Three sources, four daily facts each. Limited requests rotate sources;
        # deliberately low thresholds expose retirement and revival quickly.
        docs = [document(f'{s}-{i}', f'2026-06-{19-i:02d}', str(s))
                for s in range(3) for i in range(4)]
        marked = self.distinct_facts(docs)
        for doc in docs:
            marked[doc['id']]['support'] = ([1, -1] if
                int(doc['id'].split('-')[1]) % 2 else [-1, 1])
        cfg = Config(rounds=20, initial_window_days=14, min_window_days=14,
                     round_budget=6, total_budget=100, epsilon=0,
                     stable_distance=0, convergence=.001, source_exhaustion=.002,
                     source_confirmation_rounds=1, band_days=3, grid_days=3)
        out = run(TASK, docs, cfg, marked)
        retired = next(r for r in out['rounds'] if not r['source_states']['1']['active'])
        self.assertTrue({'1-0', '1-1'}.issubset(retired['window_ids']))
        revived = next(r for r in out['rounds'] if r['round'] > retired['round']
                       and r['source_states']['1']['active'])
        self.assertEqual(revived['state_before'], 'slow')
        self.assertIn('1-2', revived['retrieved_ids'])
        self.assertGreater(revived['budget']['watch'], 0)
        self.assertEqual(revived['budget']['window'], 0)
        state = revived['source_states']['1']
        self.assertEqual(state['confirmations'], 0)
        self.assertEqual(state['silence'], 0)
        self.assertEqual(state['phi'], 0)
        self.assertEqual(state['new_count'], 3)
        self.assertEqual(state['interval_samples'], [1., 1.])
        # Cached hits during earlier watch rounds must not reset silence.
        between = [r for r in out['rounds']
                   if retired['round'] < r['round'] < revived['round']]
        self.assertTrue(any('1-0' in r['retrieved_ids'] for r in between))
        self.assertTrue(all(r['source_states']['1']['last_new_round'] == 2 for r in between))

    def test_cross_region_rank_changes_window_support_without_counting_probe_as_support(self):
        docs = [document('old', '2026-06-12', 'old'),
                document('dup', '2026-06-18', 'new'),
                document('other', '2026-06-19', 'other')]
        marked = annotations(docs)
        marked['other']['elements']['time'] = 'different fact'
        marked['other']['support'] = [-1, 1]
        common = dict(rounds=1, initial_window_days=5, min_window_days=5,
                      band_days=5, grid_days=5, high_loss=.9, low_loss=0,
                      round_budget=30, total_budget=100)
        enhanced = run(TASK, docs, Config(**common), marked)
        row = enhanced['rounds'][0]
        self.assertEqual(row['action'], 'hold')
        self.assertEqual(set(row['window_ids']), {'dup', 'other'})
        weights = {e['id']: e['weight'] for e in enhanced['evidence']}
        self.assertEqual(weights, {'old': 1., 'dup': .5, 'other': 1.})
        self.assertEqual(row['volume'], 1.5)
        self.assertEqual(row['loss'], 1.)
        self.assertEqual(row['loss_ratio'], .4)
        # Window scores are (-1/3, +1/3); omega=2 gives sigmoid(-4/3).
        self.assertAlmostEqual(row['probabilities'][0], 1 / (1 + math.exp(4 / 3)))
        basic = run(TASK, docs, Config(mode='basic', **common), marked)
        self.assertEqual(basic['rounds'][0]['volume'], 2.)
        self.assertEqual(basic['result']['probabilities'], [.5, .5])

    def waiting_fixture(self, share):
        docs = [document('only', '2026-06-19')]
        cfg = Config(rounds=100, total_budget=50, round_budget=20,
                     initial_window_days=5, min_window_days=5,
                     band_days=5, grid_days=5, waiting_share=share, stable_distance=0)
        return cfg, run(TASK, docs, cfg, annotations(docs))

    def test_waiting_cap_is_locked_on_entry_and_does_not_claim_source_exhaustion(self):
        cfg, out = self.waiting_fixture(.04)
        entry = next(r for r in out['rounds']
                     if r['state_before'] == 'continue' and r['state'] == 'slow')
        cap = entry['remaining'] * cfg.waiting_share
        watch_rows = [r for r in out['rounds'] if r['state_before'] == 'slow']
        self.assertTrue(watch_rows)
        self.assertLessEqual(sum(r['spent'] for r in watch_rows), cap + 1e-9)
        self.assertEqual(out['result']['termination_reason'], 'waiting_budget_exhausted')
        self.assertEqual(out['result']['unresolved_sources'], ['paper'])
        self.assertGreater(out['result']['remaining_budget'], 0)
        self.assertLess(out['result']['rounds'], cfg.rounds)

    def test_fragmented_waiting_remainder_terminates_instead_of_zero_spend_rounds(self):
        # After entering slow, the cap is 48.2 * .05 = 2.41. With 2.2
        # spent, .21 remains: >= one .2 request globally, but each remaining
        # executable allocation is < .2. S107 must terminate, not spin to round_limit.
        cfg, out = self.waiting_fixture(.05)
        self.assertEqual(out['result']['termination_reason'], 'waiting_budget_exhausted')
        self.assertLess(out['result']['rounds'], cfg.rounds)
        self.assertEqual(out['result']['unresolved_sources'], ['paper'])


    def test_fragmented_regular_budget_stops_without_claiming_convergence(self):
        docs = [document('only', '2026-06-19')]
        cfg = Config(rounds=20, total_budget=.3, round_budget=.3,
                     initial_window_days=5, min_window_days=5,
                     band_days=5, grid_days=5)
        out = run(TASK, docs, cfg, annotations(docs))
        self.assertEqual(out['result']['termination_reason'], 'budget_exhausted')
        self.assertLess(out['result']['rounds'], cfg.rounds)
        self.assertEqual(out['result']['spent'], 0)
        self.assertEqual(out['result']['unresolved_sources'], ['paper'])

    def test_empty_frozen_metadata_routes_do_not_prove_source_exhaustion(self):
        docs = [document('only', '2026-06-19')]
        task = dict(TASK, scheduler_policy='grid_credit_v2')
        cfg = Config(rounds=8, initial_window_days=5, min_window_days=5,
                     band_days=5, grid_days=5)
        out = run(task, docs, cfg, annotations(docs))
        self.assertEqual(out['result']['termination_reason'], 'round_limit')
        self.assertEqual(out['result']['unresolved_sources'], ['paper'])
        self.assertTrue(all(r['source_states']['paper']['phi'] == 0
                            for r in out['rounds']))
        self.assertTrue(any(r['spent'] == 0 for r in out['rounds']))


    def test_zero_spend_round_can_wait_for_affordable_future_grid_credit(self):
        # Regular search is unaffordable, but a 1.4 (then 1.26) probe pool can
        # eventually fund the 1.2 request+read once the distant cell accrues it.
        docs = [document('current', '2026-06-19', 'new'),
                document('old', '2026-06-10', 'old')]
        task = dict(TASK, scheduler_policy='grid_credit_v2')
        cfg = Config(rounds=16, round_budget=2, total_budget=50,
                     initial_window_days=5, min_window_days=5,
                     band_days=5, grid_days=1, band_fraction=.7,
                     recovery_fraction=.25, slow_fraction=.9, low_loss=0)
        out = run(task, docs, cfg, annotations(docs))
        read_round = next(r for r in out['rounds'] if 'old' in r['retrieved_ids'])
        self.assertGreater(read_round['round'], 1)
        self.assertTrue(all(r['spent'] == 0 for r in out['rounds']
                            if r['round'] < read_round['round']))
        self.assertAlmostEqual(read_round['spent'], 1.2)
        self.assertEqual(out['result']['unresolved_sources'], ['new', 'old'])


if __name__ == '__main__':
    unittest.main()