"""Behavioral checks for explicitly supplied runtime policy tables."""
import copy
import importlib
import importlib.util
import math
import unittest
from dataclasses import asdict

from dynamic_retrieval.models import Config


def profile():
    return dict(evidence_span_days=2., evidence_span_provenance='synthetic scenario median; not measured',
                task_duration_days=8., budget_unit='simulation_units', table=[
        dict(urgency=0., budget=0., parameters=dict(slow_multiplier=5., waiting_share=.8, shared_quota=.9)),
        dict(urgency=0., budget=100., parameters=dict(slow_multiplier=3., waiting_share=.6, shared_quota=.7)),
        dict(urgency=1., budget=0., parameters=dict(slow_multiplier=3., waiting_share=.4, shared_quota=.5)),
        dict(urgency=1., budget=100., parameters=dict(slow_multiplier=2., waiting_share=.2, shared_quota=.3)),
    ])


class RuntimePolicyTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('dynamic_retrieval.runtime_policy'),
                             'runtime policy implementation must exist')
        return importlib.import_module('dynamic_retrieval.runtime_policy')

    def test_bilinear_interpolation_uses_remaining_task_time_and_absolute_budget(self):
        params, trace = self.api().runtime_parameters(profile(), 4., 50., Config())
        self.assertAlmostEqual(params['slow_multiplier'], 3.25)
        self.assertAlmostEqual(params['waiting_share'], .5)
        self.assertAlmostEqual(params['shared_quota'], .6)
        self.assertEqual(trace['task_remaining_days'], 4.)
        self.assertEqual(trace['urgency'], .5)
        self.assertEqual(trace['interpolation_coordinates'], dict(urgency=.5, budget=50.))
        self.assertEqual(trace['clamped_axes'], [])
        self.assertFalse(trace['independently_validated'])
        self.assertEqual(trace['calibration_status'], 'supplied_unvalidated')

    def test_first_round_is_elapsed_zero_and_table_endpoints_are_exact(self):
        api = self.api()
        _, trace = api.runtime_parameters(profile(), 0., 100., Config())
        self.assertEqual(trace['urgency'], .25)
        params, _ = api.runtime_parameters(profile(), 6., 100., Config())
        self.assertEqual(params, dict(slow_multiplier=2., waiting_share=.2, shared_quota=.3))

    def test_deadline_returns_no_parameters_without_division_or_extrapolation(self):
        for elapsed in (8., 9.):
            with self.subTest(elapsed=elapsed):
                params, trace = self.api().runtime_parameters(profile(), elapsed, 50., Config())
                self.assertEqual(params, {})
                self.assertEqual(trace['status'], 'deadline_reached')
                self.assertIsNone(trace['urgency'])
                self.assertEqual(trace['parameters'], {})

    def test_default_domain_error_and_explicit_clamp_are_audited(self):
        api = self.api()
        with self.assertRaises(ValueError):
            api.runtime_parameters(profile(), 7., 150., Config())
        p = profile()
        p['out_of_domain'] = 'clamp'
        params, trace = api.runtime_parameters(p, 7., 150., Config())
        self.assertEqual(params, dict(slow_multiplier=2., waiting_share=.2, shared_quota=.3))
        self.assertEqual(trace['urgency'], 2.)
        self.assertEqual(trace['remaining_budget'], 150.)
        self.assertEqual(trace['interpolation_coordinates'], dict(urgency=1., budget=100.))
        self.assertEqual(trace['clamped_axes'], ['urgency', 'budget'])

    def test_units_provenance_and_explicit_span_are_required(self):
        api = self.api()
        bad = [('budget_unit', 'USD'), ('budget_unit', 'fraction'),
               ('evidence_span_provenance', ''), ('evidence_span_provenance', '   '),
               ('out_of_domain', 'extrapolate'), ('calibration_status', 'measured')]
        for key, value in bad:
            p = profile()
            p[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                api.validate_runtime_policy(p, Config())
        for missing in ('evidence_span_days', 'evidence_span_provenance', 'task_duration_days', 'budget_unit'):
            p = profile()
            p.pop(missing)
            p['publication_interval_days'] = 2.
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                api.validate_runtime_policy(p, Config())

    def test_numbers_are_finite_nonboolean_and_physical_inputs_nonnegative(self):
        api = self.api()
        for key in ('evidence_span_days', 'task_duration_days'):
            for value in (0., -1., math.nan, math.inf, True, '2'):
                p = profile()
                p[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    api.validate_runtime_policy(p, Config())
        for elapsed, budget in ((-1., 50.), (math.nan, 50.), (True, 50.), (0., -1.), (0., math.inf)):
            with self.subTest(elapsed=elapsed, budget=budget), self.assertRaises(ValueError):
                api.runtime_parameters(profile(), elapsed, budget, Config())

    def test_complete_unique_rectangle_with_at_least_two_axis_points_required(self):
        api = self.api()
        for rows in (profile()['table'][:-1], profile()['table']+[profile()['table'][0]],
                     profile()['table'][:2], []):
            p = profile()
            p['table'] = rows
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                api.validate_runtime_policy(p, Config())

    def test_each_parameter_decreases_with_urgency(self):
        for parameter in ('slow_multiplier', 'waiting_share', 'shared_quota'):
            p = profile()
            p['table'][2]['parameters'][parameter] = p['table'][0]['parameters'][parameter]+.05
            with self.subTest(parameter=parameter), self.assertRaises(ValueError):
                self.api().validate_runtime_policy(p, Config())

    def test_multiplier_must_not_increase_with_budget_but_shares_may(self):
        api = self.api()
        p = profile()
        p['table'][1]['parameters']['slow_multiplier'] = 6.
        with self.assertRaises(ValueError):
            api.validate_runtime_policy(p, Config())
        p = profile()
        p['table'][1]['parameters']['waiting_share'] = .85
        p['table'][1]['parameters']['shared_quota'] = .95
        api.validate_runtime_policy(p, Config())

    def test_parameter_bounds_and_fixed_slow_fraction(self):
        api = self.api()
        for parameter, value in (('slow_multiplier', 1.), ('waiting_share', 0.),
                                 ('shared_quota', 1.), ('slow_multiplier', math.inf),
                                 ('waiting_share', True), ('slow_fraction', .7)):
            p = profile()
            p['table'][0]['parameters'][parameter] = value
            with self.subTest(parameter=parameter, value=value), self.assertRaises(ValueError):
                api.validate_runtime_policy(p, Config())
        cfg = Config(slow_fraction=.37)
        original = asdict(cfg)
        params, trace = api.runtime_parameters(profile(), 4., 50., cfg)
        self.assertNotIn('slow_fraction', params)
        self.assertEqual(trace['slow_fraction'], .37)
        self.assertEqual(asdict(cfg), original)
        self.assertEqual(Config.from_dict(dict(original, **params)).slow_fraction, .37)
        cfg.slow_fraction = 0.
        with self.assertRaises(ValueError):
            api.runtime_parameters(profile(), 4., 50., cfg)

    def test_profile_and_trace_are_detached_and_hashes_track_source_and_table(self):
        api = self.api()
        p = profile()
        before = copy.deepcopy(p)
        validated = api.validate_runtime_policy(p, Config())
        self.assertEqual(p, before)
        self.assertEqual(validated['calibration_status'], 'supplied_unvalidated')
        self.assertEqual(validated['provenance_hash'], api.validate_runtime_policy(validated, Config())['provenance_hash'])
        validated['table'][0]['parameters']['slow_multiplier'] = 99.
        self.assertEqual(p, before)
        params, trace = api.runtime_parameters(p, 4., 50., Config())
        params['slow_multiplier'] = 99.
        self.assertEqual(trace['parameters']['slow_multiplier'], 3.25)
        q = copy.deepcopy(p)
        q['evidence_span_provenance'] = 'different supplied scenario'
        _, other = api.runtime_parameters(q, 4., 50., Config())
        self.assertNotEqual(trace['provenance_hash'], other['provenance_hash'])
        self.assertEqual(trace['table_hash'], other['table_hash'])
        q['table'][0]['parameters']['slow_multiplier'] = 6.
        _, other = api.runtime_parameters(q, 4., 50., Config())
        self.assertNotEqual(trace['table_hash'], other['table_hash'])


if __name__ == '__main__':
    unittest.main()
