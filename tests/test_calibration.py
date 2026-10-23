import copy
import importlib
import unittest


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.cal = importlib.import_module('dynamic_retrieval.calibration')

    def observations(self):
        return [dict(observation_id=str(i), source_id='a', budget=b,
                     coverage=c, budget_unit='simulation_units', explicit_cost=cost,
                     recovered_span_days=days, cost_unit='simulation_units')
                for i, (b,c,cost,days) in enumerate([
                    (2, .6321205588285577, 2, 1),
                    (4, .8646647167633873, 2, 2),
                    (6, .950212931632136, 8, 3)])]

    def test_recovers_known_coverage_scale_and_span_weighted_cost(self):
        original = self.observations()
        snapshot = copy.deepcopy(original)
        result = self.cal.calibrate_sources(original)
        self.assertAlmostEqual(result['sources']['a']['coverage_scale']['value'], 2.)
        self.assertAlmostEqual(result['sources']['a']['cost_per_day']['value'], 2.)
        estimate = result['sources']['a']['coverage_scale']
        self.assertEqual(estimate['sample_count'], 3)
        self.assertEqual(estimate['status'], 'calibrated')
        self.assertEqual(estimate['domain']['budget'], [2, 6])
        self.assertEqual(estimate['unit'], 'simulation_units')
        self.assertEqual(original, snapshot)

    def test_missing_cost_and_publication_gaps_never_become_cost_observations(self):
        rows = [dict(observation_id=str(i), source_id='a', published_at=f'2026-01-0{i+1}',
                     publication_interval_days=1) for i in range(5)]
        result = self.cal.calibrate_sources(rows)['sources']['a']
        for estimate in result.values():
            self.assertIsNone(estimate['value'])
            self.assertEqual(estimate['status'], 'uncalibrated')
            self.assertEqual(estimate['sample_count'], 0)
            self.assertTrue(estimate['reasons'])

    def test_hash_tracks_input_changes_and_repeated_observation_is_not_new_sample(self):
        rows = self.observations()
        baseline = self.cal.calibrate_sources(rows)
        self.assertEqual(baseline, self.cal.calibrate_sources(copy.deepcopy(rows)))
        duplicated = self.cal.calibrate_sources(rows + [rows[0]])
        self.assertEqual(duplicated['sources']['a']['coverage_scale']['sample_count'], 3)
        changed = copy.deepcopy(rows)
        changed[0]['explicit_cost'] = 3
        self.assertNotEqual(baseline['provenance_hash'], self.cal.calibrate_sources(changed)['provenance_hash'])
        conflicting = dict(rows[0], explicit_cost=9)
        with self.assertRaises(ValueError): self.cal.calibrate_sources(rows+[conflicting])

    def test_sources_with_insufficient_data_are_kept_separate(self):
        rows = self.observations()
        rows[2]['source_id'] = 'b'
        result = self.cal.calibrate_sources(rows)
        self.assertEqual(set(result['sources']), {'a','b'})
        self.assertIsNone(result['sources']['a']['coverage_scale']['value'])
        self.assertIsNone(result['sources']['b']['cost_per_day']['value'])

    def test_saturated_zero_coverage_and_zero_span_do_not_create_infinite_fit(self):
        rows = self.observations()
        rows[0]['coverage'] = 0
        rows[1]['coverage'] = 1
        rows[2]['recovered_span_days'] = 0
        result = self.cal.calibrate_sources(rows)['sources']['a']
        self.assertIsNone(result['coverage_scale']['value'])
        self.assertIsNone(result['cost_per_day']['value'])
        self.assertEqual(result['coverage_scale']['sample_count'], 1)
        self.assertEqual(result['cost_per_day']['sample_count'], 2)

    def test_cost_currency_and_missing_units_cannot_be_blended(self):
        rows = self.observations()
        rows[0]['cost_unit'] = 'CNY'
        estimate = self.cal.calibrate_sources(rows)['sources']['a']['cost_per_day']
        self.assertIsNone(estimate['value'])
        self.assertIn('mixed_units', estimate['reasons'])
        for row in rows: row.pop('cost_unit')
        estimate = self.cal.calibrate_sources(rows)['sources']['a']['cost_per_day']
        self.assertIsNone(estimate['value'])
        self.assertEqual(estimate['sample_count'], 0)

    def test_rejects_nonfinite_negative_and_invalid_sample_thresholds(self):
        for field, value in [('budget', -1), ('coverage', 1.1), ('coverage', float('nan')),
                             ('explicit_cost', -1), ('recovered_span_days', float('inf')),
                             ('budget', True)]:
            with self.subTest(field=field,value=value):
                rows = self.observations()
                rows[0][field] = value
                with self.assertRaises(ValueError): self.cal.calibrate_sources(rows)
        for threshold in [0, -1, 1.5, True]:
            with self.assertRaises(ValueError): self.cal.calibrate_sources([], min_samples=threshold)

    def test_noisy_coverage_uses_documented_fit_and_currency_stays_incompatible(self):
        rows=self.observations()
        for row,b,c in zip(rows,[1,2,3],[.6321205588285577,.6321205588285577,.8646647167633873]):
            row['budget']=b
            row['coverage']=c
            row['cost_unit']='CNY'
        result=self.cal.calibrate_sources(rows)['sources']['a']
        self.assertAlmostEqual(result['coverage_scale']['value'],1.5555555555555556)
        self.assertTrue(result['coverage_scale']['config_compatible'])
        self.assertAlmostEqual(result['cost_per_day']['value'],2.)
        self.assertFalse(result['cost_per_day']['config_compatible'])
        self.assertEqual(result['cost_per_day']['unit'],'CNY')
        for row in rows: row['explicit_cost']=0
        estimate=self.cal.calibrate_sources(rows)['sources']['a']['cost_per_day']
        self.assertEqual(estimate['value'],0)
        self.assertEqual(estimate['status'],'calibrated')
        self.assertFalse(estimate['config_compatible'])

    def facts(self):
        rows=[]
        for index, sources in enumerate([['a','b'],['a','b','c'],['b','c'],['d']]):
            for source in sources:
                rows.append(dict(observation_id=f'{index}-{source}', source_id=source,
                     elements=dict(subject='Alice',action='announced',object=str(index),
                                   time='2026-01-01',location='London'), support=[1,-1]))
        return rows

    def test_gamma_counts_distinct_sources_per_exact_fact_including_singletons(self):
        rows=self.facts()
        rows.append(dict(rows[0], observation_id='same-source-copy'))
        result=self.cal.calibrate_gamma(rows)
        self.assertAlmostEqual(result['value'], .5)
        self.assertEqual(result['cluster_count'], 4)
        self.assertEqual(result['duplicate_cluster_count'], 3)
        self.assertEqual(result['sample_count'], 9)
        self.assertEqual(result['status'], 'calibrated')

    def test_gamma_requires_enough_cross_source_duplicate_facts(self):
        result=self.cal.calibrate_gamma(self.facts()[:5])
        self.assertIsNone(result['value'])
        self.assertEqual(result['duplicate_cluster_count'], 2)
        self.assertTrue(result['reasons'])
        with self.assertRaises(ValueError): self.cal.calibrate_gamma([], min_duplicate_clusters=0)

    def test_gamma_never_merges_incomplete_conflicting_or_qualified_facts(self):
        rows=self.facts()[:2]
        rows[1]['support']=[-1,1]
        self.assertEqual(self.cal.calibrate_gamma(rows, min_duplicate_clusters=1)['duplicate_cluster_count'],0)
        rows=self.facts()[:2]
        rows[1]['elements']['time']='2026-01-02'
        self.assertEqual(self.cal.calibrate_gamma(rows, min_duplicate_clusters=1)['duplicate_cluster_count'],0)
        rows=self.facts()[:2]
        rows[1]['qualifiers']=['if approved']
        self.assertEqual(self.cal.calibrate_gamma(rows, min_duplicate_clusters=1)['duplicate_cluster_count'],0)
        for row in rows: row['elements'].pop('location')
        result=self.cal.calibrate_gamma(rows,min_duplicate_clusters=1)
        self.assertEqual(result['cluster_count'],0)
        self.assertEqual(result['sample_count'],0)
        self.assertIsNone(result['value'])

    def table(self):
        return [dict(urgency=u,budget=b,parameters={'gamma':g,'round_budget':r})
                for u,b,g,r in [(0,10,.2,1),(0,30,.4,3),(1,10,.4,5),(1,30,.8,9)]]

    def test_bilinear_lookup_preserves_corners_and_interior_without_claiming_calibration(self):
        table=self.table()
        result=self.cal.interpolate_policy(table,.5,20)
        self.assertAlmostEqual(result['parameters']['gamma'],.45)
        self.assertAlmostEqual(result['parameters']['round_budget'],4.5)
        self.assertEqual(result['status'],'supplied_table_interpolation')
        self.assertEqual(self.cal.interpolate_policy(table,1,30)['parameters'],table[-1]['parameters'])
        self.assertEqual(result['domain'],{'urgency':[0,1],'budget':[10,30]})
        self.assertEqual(len(result['provenance_hash']),64)

    def test_lookup_rejects_extrapolation_missing_cells_and_inconsistent_parameters(self):
        for u,b in [(-.1,20),(.5,31),(.5,float('nan'))]:
            with self.assertRaises(ValueError): self.cal.interpolate_policy(self.table(),u,b)
        for table in [self.table()[:-1],self.table()+[self.table()[0]],self.table()[:2]]:
            with self.assertRaises(ValueError): self.cal.interpolate_policy(table,.5,20)
        table=self.table()
        table[0]['parameters'].pop('gamma')
        with self.assertRaises(ValueError): self.cal.interpolate_policy(table,.5,20)
        table=self.table()
        table[0]['parameters']['gamma']=float('inf')
        with self.assertRaises(ValueError): self.cal.interpolate_policy(table,.5,20)


if __name__ == '__main__': unittest.main()


