import hashlib
import importlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


class ExposureRegistryTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('dynamic_retrieval.exposure_registry')
        except ModuleNotFoundError:
            self.fail('Missing conservative event exposure registry')

    def write(self, root, rel, value):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding='utf-8')
        return p

    def test_prepared_rejected_and_skipped_events_are_exposed_without_results(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/prepared/cohort.json', {'selected': [{'task': {'event_id': 'a'}}], 'exclusions': [{'event_id': 'b', 'reason': 'insufficient_documents'}]})
            self.write(r, 'artifacts/bundle/bundle-plan.json', {'skipped': [{'event_id': 'c', 'reason': 'cross_cutoff_document_overlap'}]})
            x = m.build_registry(r)
            self.assertEqual(x['excluded_events'], ['a', 'b', 'c'])
            self.assertTrue(x['audit_complete'])
            self.assertEqual(x, m.build_registry(r))

    def test_variant_experiment_manifest_identifies_non_result_outputs(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            p = self.write(r, 'artifacts/phase13/runs/m/future_variant.json', {'task': {'event_id': 'variant'}, 'result': {'secret_probability': 0.9}})
            self.write(r, 'artifacts/phase13/experiment-manifest.json', {'artifact_type': 'experiment', 'files': {'runs/m/future_variant.json': hashlib.sha256(p.read_bytes()).hexdigest()}})
            x = m.build_registry(r)
            self.assertEqual(x['excluded_events'], ['variant'])
            self.assertNotIn('secret_probability', json.dumps(x))

    def test_missing_manifest_still_excludes_failed_task(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/failed/task.json', {'event_id': 'failed'})
            self.assertEqual(m.build_registry(r)['excluded_events'], ['failed'])

    def test_corrupt_known_file_makes_audit_incomplete_and_retains_other_events(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/task.json', {'event_id': 'good'})
            p = self.write(r, 'artifacts/bad/cohort.json', {})
            p.write_text('{bad', encoding='utf-8')
            x = m.build_registry(r)
            self.assertEqual(x['excluded_events'], ['good'])
            self.assertFalse(x['audit_complete'])
            self.assertEqual(x['errors'][0]['reason'], 'invalid_json')

    def test_manifest_hash_mismatch_is_not_silent(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/run/result.json', {'task': {'event_id': 'changed'}})
            self.write(r, 'artifacts/run/manifest.json', {'files': {'result.json': '0' * 64}})
            x = m.build_registry(r)
            self.assertFalse(x['audit_complete'])
            self.assertEqual(x['excluded_events'], ['changed'])
            self.assertIn('manifest_hash_mismatch', {e['reason'] for e in x['errors']})

    def test_zero_unexposed_events_and_no_labels_read(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/task.json', {'event_id': 'only'})
            db = r / 'index.sqlite'
            c = sqlite3.connect(db)
            c.execute('CREATE TABLE tasks(event_id TEXT, observed_at TEXT)')
            c.execute("INSERT INTO tasks VALUES('only','2026-08-28T13:00:00.000000Z')")
            c.commit(); c.close()
            x = m.audit_index(db, m.build_registry(r), ['2026-08-28T23:59:59Z'])
            self.assertEqual(x['status'], 'no_unexposed_events')
            self.assertFalse(x['ready_for_model'])
            self.assertEqual(x['unexposed_event_count'], 0)
            self.assertEqual(x['cutoffs'][0]['indexed_event_count'], 1)

    def test_positive_metadata_count_never_authorizes_model_or_claims_eligibility(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp); (r / 'artifacts').mkdir()
            db = r / 'index.sqlite'; c = sqlite3.connect(db)
            c.execute('CREATE TABLE tasks(event_id TEXT, observed_at TEXT)')
            c.execute("INSERT INTO tasks VALUES('new','2026-08-28T13:00:00.000000Z')")
            c.commit(); c.close()
            x = m.audit_index(db, m.build_registry(r), ['2026-08-28T23:59:59Z'])
            self.assertEqual(x['status'], 'unexposed_metadata_requires_freeze')
            self.assertEqual(x['unexposed_event_count'], 1)
            self.assertFalse(x['ready_for_model'])

    def test_malformed_selected_schema_cannot_pass_as_empty(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/cohort.json', {'selected': 'wrong'})
            self.assertFalse(m.build_registry(r)['audit_complete'])

    def test_list_cohort_and_diagnostic_rows_have_explicit_identity_schemas(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/observed/cohort.json', [{'event_id': 'observed', 'market_id': 'm'}])
            self.write(r, 'docs/example-diagnostic.json', {'tasks': 2, 'rows': [{'event_id': 'reviewed'}], 'event_results': [{'event_id': 'reviewed2'}]})
            self.write(r, 'docs/list-diagnostic.json', [{'event_id': 'reviewed3'}])
            x = m.build_registry(r)
            self.assertTrue(x['audit_complete'], x['errors'])
            self.assertEqual(x['excluded_events'], ['observed', 'reviewed', 'reviewed2', 'reviewed3'])

    def test_unknown_list_cohort_identity_is_incomplete(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/cohort.json', [{'unknown': 'not a task'}])
            self.assertFalse(m.build_registry(r)['audit_complete'])

    def test_json_null_history_cannot_be_treated_as_missing_optional_data(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/cohort.json', None)
            self.assertFalse(m.build_registry(r)['audit_complete'])

    def test_empty_cohort_object_is_unknown_schema_not_zero_exposure(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            self.write(r, 'artifacts/cohort.json', {})
            self.assertFalse(m.build_registry(r)['audit_complete'])
