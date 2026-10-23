"""Behavioral tests for explicit, provenance-bearing calibration observations."""
import copy
import importlib.util
import unittest


class ObservationTransformsTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dynamic_retrieval.calibration_observations'),
                             'explicit observation transforms must be implemented')
        from dynamic_retrieval import calibration_observations
        return calibration_observations

    def sources(self):
        return [dict(source_id='a', observation_id='a1', response_latency_seconds=2,
                     rate_limit_quota=20, returned_items=3, observation_window='2026-01-01/2026-01-02',
                     quota_unit='requests/minute'),
                dict(source_id='b', observation_id='b1', response_latency_seconds=6,
                     rate_limit_quota=80, returned_items=7, observation_window='2026-01-01/2026-01-02',
                     quota_unit='requests/minute')]

    def costs(self, rows=None, **overrides):
        options = dict(weights=dict(response_latency_seconds=.2, rate_limit_quota=.3, returned_items=.5),
                       base_cost=100, budget_unit='simulation_units', base_time_unit='day')
        options.update(overrides)
        return self.module().normalize_source_costs(self.sources() if rows is None else rows, **options)

    def events(self):
        return [dict(event_id=str(i), event_type='decision',
                     first_relevant_evidence_at=f'2026-01-{10-span:02d}T00:00:00+00:00',
                     event_occurred_at='2026-01-10T00:00:00+00:00',
                     timestamp_kind='observed_event_times',
                     evidence_time_provenance=f'evidence-record:{i}', event_time_provenance=f'event-record:{i}')
                for i, span in enumerate((1, 3, 5, 7))]

    def band(self, rows=None, **overrides):
        options = dict(event_type='decision', calibration_cutoff='2026-02-01T00:00:00Z',
                       quantile=.75, min_samples=3)
        options.update(overrides)
        return self.module().estimate_incubation_band(self.events() if rows is None else rows, **options)

    def test_source_ratios_follow_literal_quota_and_sum_to_explicit_base(self):
        result = self.costs()
        a, b = result['sources']['a'], result['sources']['b']
        self.assertAlmostEqual(a['cost_per_day'], 26)
        self.assertAlmostEqual(b['cost_per_day'], 74)
        self.assertEqual(a['normalized_components'], dict(response_latency_seconds=.25, rate_limit_quota=.2, returned_items=.3))
        self.assertFalse(result['empirical_calibration'])
        self.assertFalse(result['applied'])
        self.assertEqual(result['unit'], 'simulation_units/day')
        self.assertEqual(len(a['provenance_hash']), 64)

    def test_time_unit_conversion_and_zero_individual_cost_are_explicit(self):
        result = self.costs(base_time_unit='hour')
        self.assertAlmostEqual(result['sources']['a']['cost_per_day'], 624)
        rows = self.sources()
        for key in ('response_latency_seconds', 'rate_limit_quota', 'returned_items'):
            rows[0][key] = 0
        self.assertEqual(self.costs(rows)['sources']['a']['cost_per_day'], 0)
        self.assertFalse(self.costs(rows)['sources']['a']['config_compatible'])

    def test_source_invalid_numbers_denominators_duplicates_and_units_rejected(self):
        for key in ('response_latency_seconds', 'rate_limit_quota', 'returned_items'):
            for invalid in (-1, float('nan'), float('inf'), True, '2', None):
                rows = self.sources(); rows[0][key] = invalid
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    self.costs(rows)
            rows = self.sources()
            for row in rows:
                row[key] = 0
            with self.assertRaises(ValueError):
                self.costs(rows)
        for rows in ([], self.sources() + [self.sources()[0]]):
            with self.assertRaises(ValueError):
                self.costs(rows)
        for field in ('observation_window', 'quota_unit'):
            rows = self.sources(); rows[0][field] = 'different'
            with self.assertRaises(ValueError):
                self.costs(rows)
        for changes in (dict(base_cost=0), dict(base_cost=float('inf')), dict(budget_unit=''),
                        dict(base_time_unit='month'), dict(weights={'returned_items': 1}),
                        dict(weights=dict(response_latency_seconds=.5, rate_limit_quota=.5, returned_items=.5)),
                        dict(weights=dict(response_latency_seconds=-.5, rate_limit_quota=.5, returned_items=1))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.costs(**changes)

    def test_source_provenance_is_required_and_configuration_changes_hash(self):
        rows = self.sources(); rows[0].pop('observation_id')
        with self.assertRaises(ValueError):
            self.costs(rows)
        rows[0]['provenance'] = {'record': 'source-a-measurement'}
        self.assertEqual(self.costs(rows)['sources']['a']['cost_per_day'], 26)
        self.assertNotEqual(self.costs()['provenance_hash'], self.costs(base_cost=10)['provenance_hash'])
        rows = self.sources(); rows[1]['observation_id'] = 'a1'
        with self.assertRaises(ValueError):
            self.costs(rows)

    def test_incubation_uses_linear_high_quantile_and_median_of_observed_event_spans(self):
        result = self.band()
        self.assertEqual(result['band_days'], 5.5)
        self.assertEqual(result['value'], 5.5)
        self.assertEqual(result['median_span_days'], 4)
        self.assertEqual(result['sample_count'], 4)
        self.assertEqual(result['unit'], 'days')
        self.assertFalse(result['empirical_calibration'])
        self.assertEqual(result['status'], 'estimated_from_supplied_observations')
        self.assertEqual(len(result['provenance_hash']), 64)

    def test_future_and_other_type_are_excluded_and_threshold_does_not_impute(self):
        rows = self.events()
        rows[0]['event_type'] = 'different'
        rows[1]['event_occurred_at'] = '2026-03-01T00:00:00Z'
        result = self.band(rows)
        self.assertIsNone(result['band_days'])
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['status'], 'underidentified')
        self.assertEqual({r['reason'] for r in result['excluded_observations']},
                         {'different_event_type', 'event_after_calibration_cutoff'})
        self.assertIn('insufficient_samples', result['reasons'])

    def test_dates_use_actual_timezones_and_cutoff_is_inclusive(self):
        row = self.events()[0]
        row['first_relevant_evidence_at'] = '2026-01-01T12:00:00+08:00'
        row['event_occurred_at'] = '2026-01-02T12:00:00+00:00'
        result = self.band([row], calibration_cutoff=row['event_occurred_at'], min_samples=1)
        self.assertAlmostEqual(result['band_days'], 4 / 3)

    def test_malformed_dates_reversed_spans_duplicates_and_publication_proxies_rejected(self):
        for field in ('first_relevant_evidence_at', 'event_occurred_at'):
            for invalid in ('2026-01-01', '2026-01-01T00:00:00', 1760000000, '2026-02-31T00:00:00Z', '2026-01-01T00:00:00+00:60', None):
                rows = self.events(); rows[0][field] = invalid
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    self.band(rows)
        rows = self.events(); rows[0]['first_relevant_evidence_at'] = '2026-01-20T00:00:00Z'
        with self.assertRaises(ValueError):
            self.band(rows)
        with self.assertRaises(ValueError):
            self.band(self.events() + [self.events()[0]])
        for field in ('evidence_time_provenance', 'event_time_provenance', 'timestamp_kind'):
            rows = self.events(); rows[0].pop(field)
            with self.assertRaises(ValueError):
                self.band(rows)
        rows = self.events(); rows[0]['timestamp_kind'] = 'publication_timestamps'
        with self.assertRaises(ValueError):
            self.band(rows)
        for changes in (dict(quantile=0), dict(quantile=1), dict(quantile=.4), dict(quantile=float('nan')),
                        dict(min_samples=0), dict(min_samples=True), dict(event_type=''),
                        dict(calibration_cutoff='2026-02-01')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.band(**changes)

    def test_empty_history_is_underidentified_and_inputs_are_unchanged(self):
        result = self.band([])
        self.assertEqual(result['sample_count'], 0)
        self.assertIsNone(result['median_span_days'])
        self.assertIsNone(result['band_days'])
        rows = self.events(); before = copy.deepcopy(rows)
        self.band(rows)
        self.assertEqual(rows, before)
        self.assertNotEqual(self.band()['provenance_hash'], self.band(quantile=.5)['provenance_hash'])


if __name__ == '__main__':
    unittest.main()

