"""Behavioral contracts for the bounded source-cost profile adapter."""
import copy
import importlib.util
import unittest


class SourceCostProfileTests(unittest.TestCase):
    def prepare(self, profile=None, source_ids=None, cutoff='2026-01-03T00:00:00Z'):
        self.assertIsNotNone(importlib.util.find_spec('dynamic_retrieval.source_cost_profile'),
                             'source cost profile adapter is required')
        from dynamic_retrieval.source_cost_profile import prepare_source_cost_profile
        return prepare_source_cost_profile(self.profile() if profile is None else profile,
                                           ['a', 'b'] if source_ids is None else source_ids, cutoff)

    def profile(self):
        return dict(version='patent_source_cost_v1', observations=[
            dict(source_id='a', observation_id='a1', interface_id='search:a',
                 observed_at='2026-01-02T00:00:00Z', measurement_kind='retrieval_interface',
                 response_latency_seconds=2, rate_limit_quota=20, returned_items=3,
                 observation_window='2026-01-01/2026-01-02', quota_unit='requests/minute',
                 provenance={'record': ['a-supplied-record']}),
            dict(source_id='b', observation_id='b1', interface_id='search:b',
                 observed_at='2026-01-02T08:00:00+08:00', measurement_kind='retrieval_interface',
                 response_latency_seconds=6, rate_limit_quota=80, returned_items=7,
                 observation_window='2026-01-01/2026-01-02', quota_unit='requests/minute')],
            weights=dict(response_latency_seconds=.2, rate_limit_quota=.3, returned_items=.5),
            base_cost=100, budget_unit='simulation_units')

    def test_literal_costs_have_global_sum_and_subset_keeps_its_cost(self):
        result = self.prepare()
        self.assertAlmostEqual(result['source_parameters']['a']['cost_per_day'], 26)
        self.assertAlmostEqual(result['source_parameters']['b']['cost_per_day'], 74)
        self.assertAlmostEqual(sum(row['cost_per_day'] for row in result['source_parameters'].values()), 100)
        self.assertEqual(result['diagnostics']['normalization_scope'], 'all_visible_sources')
        self.assertFalse(result['diagnostics']['subset_renormalization'])
        self.assertEqual(result['diagnostics']['unit'], 'simulation_units/day')
        self.assertEqual(result['provenance']['transformation']['method'],
                         'patent_0249_literal_weighted_source_ratios')

    def test_supported_time_units_convert_to_day_without_changing_ratios(self):
        for time_unit, expected in (('day', 26), ('hour', 624), ('minute', 37440), ('second', 2246400)):
            profile = self.profile()
            profile['base_time_unit'] = time_unit
            with self.subTest(time_unit=time_unit):
                self.assertAlmostEqual(self.prepare(profile)['source_parameters']['a']['cost_per_day'], expected)

    def test_supplied_measurements_are_transformed_not_verified_empirical_calibration(self):
        result = self.prepare()
        self.assertEqual(result['diagnostics']['observation_status'], 'supplied_interface_observations')
        self.assertFalse(result['diagnostics']['empirical_calibration'])
        self.assertFalse(result['diagnostics']['provenance_verified'])
        self.assertTrue(result['diagnostics']['applied'])
        profile = self.profile()
        for row in profile['observations']:
            row['measurement_kind'] = 'synthetic'
        result = self.prepare(profile)
        self.assertEqual(result['diagnostics']['observation_status'], 'synthetic_formula_fixture')
        self.assertFalse(result['diagnostics']['empirical_calibration'])
        profile['observations'][0]['measurement_kind'] = 'retrieval_interface'
        with self.assertRaisesRegex(ValueError, 'measurement_kind'):
            self.prepare(profile)

    def test_rejects_missing_extra_duplicate_sources_without_fallback(self):
        for source_ids in (['a'], ['a', 'b', 'c'], ['a', 'a', 'b'], [], 'ab', [True, 'b']):
            with self.subTest(source_ids=source_ids), self.assertRaises(ValueError):
                self.prepare(source_ids=source_ids)
        profile = self.profile()
        profile['observations'].append(copy.deepcopy(profile['observations'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate source_id'):
            self.prepare(profile)
        profile = self.profile()
        profile['observations'][1]['source_id'] = 'c'
        with self.assertRaisesRegex(ValueError, 'source_ids'):
            self.prepare(profile)

    def test_rejects_missing_quota_interface_or_provenance_fields(self):
        for field in ('rate_limit_quota', 'interface_id', 'observed_at', 'measurement_kind',
                      'quota_unit', 'observation_window'):
            profile = self.profile()
            profile['observations'][0].pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.prepare(profile)
        profile = self.profile()
        profile['observations'][1].pop('observation_id')
        with self.assertRaises(ValueError):
            self.prepare(profile)
        profile = self.profile()
        profile['observations'][0]['interface_id'] = ' '
        with self.assertRaises(ValueError):
            self.prepare(profile)

    def test_requires_aware_full_timestamp_and_rejects_future_observations(self):
        for timestamp in ('2026-01-04T00:00:00Z', '2026-01-03T00:00:00.000001Z',
                          '2026-01-02', '2026-01-02T00:00:00', '2026-02-30T00:00:00Z', None):
            profile = self.profile()
            profile['observations'][0]['observed_at'] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(ValueError, 'observed_at'):
                self.prepare(profile)
        profile = self.profile()
        profile['observations'][0]['observed_at'] = '2026-01-03T08:00:00+08:00'
        self.prepare(profile)  # inclusive cutoff after UTC conversion
        for cutoff in ('bad', '2026-01-03T00:00:00', None):
            with self.subTest(cutoff=cutoff), self.assertRaisesRegex(ValueError, 'cutoff'):
                self.prepare(cutoff=cutoff)

    def test_rejects_wrong_units_schema_versions_and_unknown_policy_fields(self):
        for changes in (dict(version='other'), dict(budget_unit='USD'),
                        dict(base_time_unit='month'), dict(fallback=True), dict(empirical_calibration=True)):
            profile = self.profile()
            profile.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.prepare(profile)
        for key in ('version', 'weights', 'base_cost', 'budget_unit', 'observations'):
            profile = self.profile()
            profile.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare(profile)
        for profile in ([], 'profile', 1):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                self.prepare(profile)

    def test_rejects_invalid_numbers_and_non_json_metadata(self):
        for value in (True, '2', -1, float('nan'), float('inf'), None, 10**1000):
            profile = self.profile()
            profile['observations'][0]['rate_limit_quota'] = value
            with self.subTest(value=repr(value)[:40]), self.assertRaises(ValueError):
                self.prepare(profile)
        for value in ((1, 2), {1: 'nonstring-key'}, {'nested': float('nan')}, object()):
            profile = self.profile()
            profile['observations'][0]['extra'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.prepare(profile)
        for value in (True, 0, float('inf')):
            profile = self.profile()
            profile['base_cost'] = value
            with self.subTest(base_cost=value), self.assertRaises(ValueError):
                self.prepare(profile)
        profile = self.profile()
        profile['observations'] = tuple(profile['observations'])
        with self.assertRaises(ValueError):
            self.prepare(profile)

    def test_rejects_incompatible_zero_cost_and_bad_normalizer_inputs(self):
        profile = self.profile()
        for component in profile['weights']:
            profile['observations'][0][component] = 0
        with self.assertRaisesRegex(ValueError, 'positive.*cost|cost.*positive'):
            self.prepare(profile)
        for mutation in ('zero_denominator', 'weights', 'observation_id', 'window', 'quota_unit'):
            profile = self.profile()
            if mutation == 'zero_denominator':
                for row in profile['observations']:
                    row['rate_limit_quota'] = 0
            elif mutation == 'weights':
                profile['weights']['rate_limit_quota'] = .9
            elif mutation == 'observation_id':
                profile['observations'][1]['observation_id'] = 'a1'
            elif mutation == 'window':
                profile['observations'][1]['observation_window'] = 'different'
            else:
                profile['observations'][1]['quota_unit'] = 'different'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.prepare(profile)

    def test_profile_provenance_and_results_are_deeply_isolated(self):
        profile = self.profile()
        original = copy.deepcopy(profile)
        first, second = self.prepare(profile), self.prepare(profile)
        self.assertEqual(profile, original)
        self.assertEqual(first['provenance']['profile'], original)
        self.assertEqual(len(first['provenance']['profile_digest']), 64)
        profile['observations'][0]['provenance']['record'].append('later')
        self.assertEqual(first['provenance']['profile'], original)
        first['provenance']['profile']['observations'][0]['provenance']['record'].append('changed-result')
        first['source_parameters']['a']['cost_per_day'] = 999
        self.assertEqual(second['provenance']['profile'], original)
        self.assertEqual(second['source_parameters']['a']['cost_per_day'], 26)
        self.assertNotEqual(self.prepare(profile)['provenance']['profile_digest'], second['provenance']['profile_digest'])
        reordered = dict(reversed(list(original.items())))
        self.assertEqual(self.prepare(reordered)['provenance']['profile_digest'], second['provenance']['profile_digest'])


if __name__ == '__main__':
    unittest.main()