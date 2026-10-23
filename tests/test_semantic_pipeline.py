import importlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from dynamic_retrieval.data.store import Store, build_index

CUTOFF = '2026-05-03T00:00:00Z'


class FakeClient:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.lock = threading.Lock()
        self.active = self.peak = 0

    def complete_json(self, messages, max_tokens=1800):
        payload = json.loads(messages[1]['content'])
        with self.lock:
            self.calls.append(payload)
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(.01)
        with self.lock:
            self.active -= 1
        if self.fail and 'Evidence 0.' in payload['evidence']['excerpt']:
            raise RuntimeError('DO-NOT-PERSIST-SECRET')
        task = payload['task']
        return dict(data=dict(elements=task['target_elements'],
            support=[1 if x.lower() == 'yes' else -1 for x in task['outcomes']],
            quote='Alice Smith announced her candidacy for the Republican presidential nomination.',
            rationale='The supplied passage reports candidacy, a directional feature only.',
            factual_status='reported', time_scope='target_compatible'),
            metadata=dict(model='deepseek-actual-test', requested_model='deepseek-flash',
                          usage=dict(prompt_tokens=20, completion_tokens=10, total_tokens=30),
                          cache_hit=False, cache_key='test-cache', request_id='test-request'))


class SemanticPipelineTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('dynamic_retrieval.semantic_pipeline')
        except ModuleNotFoundError:
            self.fail('Missing bounded semantic pipeline')

    def fixture(self, root, count=1, docs=4, outcomes=None):
        data = root / 'data'
        data.mkdir()
        events = []
        for event in range(count):
            market = dict(market_id=f'm{event}',
                question='Will Alice Smith win the 2028 Republican presidential nomination?',
                description='Resolves Yes for winning the Republican nomination.',
                outcomes=outcomes or ['Yes','No'], active=True, closed=False,
                end_date='2028-11-07T00:00:00Z', resolved_outcome='No', outcome_prices=['.1','.9'])
            articles = [dict(title='Alice Smith campaign',
                full_text=f'Alice Smith announced her candidacy for the Republican presidential nomination. Evidence {i}.',
                source='Paper', url=f'https://example.test/{event}/{i}',
                published_at='2026-05-01T00:00:00Z', scrape_status='success') for i in range(docs)]
            events.append(dict(event_id=f'e{event}', markets=[market], articles=articles))
        (data / 'batch.json').write_text(json.dumps(dict(collected_at='2026-05-02T00:00:00Z',
            scraped_at='2026-05-02T00:00:00Z', events=events)), encoding='utf-8')
        db = root / 'index.sqlite'
        build_index(data, db)
        return data, db

    def execute(self, root, data, db, **kwargs):
        with Store(db) as store:
            return self.module().run_semantic_pipeline(store, data, CUTOFF, root / 'out',
                min_documents=1, cache=root / 'cache', **kwargs)

    def test_nonzero_shared_frozen_inputs_returned_model_and_reversed_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, db = self.fixture(root, outcomes=['No','Yes'])
            raw_before = {p.name: p.read_bytes() for p in data.iterdir()}
            client = FakeClient()
            result = self.execute(root, data, db, count=1, max_documents=3, client=client)
            self.assertEqual(result['status'], 'completed_semantic_experiment')
            self.assertEqual(result['available_documents'], 4)
            self.assertEqual(result['sampled_documents'], 3)
            self.assertEqual(result['llm_preprocessing']['total_tokens'], 90)
            self.assertEqual(result['llm_preprocessing']['returned_models'], ['deepseek-actual-test'])
            self.assertEqual(len(client.calls), 3)
            self.assertLessEqual(client.peak, 3)
            hashes = []
            for mode in ('fixed','basic','enhanced'):
                record = json.loads((root / f'out/runs/m0/{mode}/result.json').read_text(encoding='utf-8'))
                self.assertGreater(record['result']['probabilities'][1], .5)
                self.assertFalse(record['diagnostics']['human_reviewed'])
                self.assertFalse(record['diagnostics']['label_access'])
                self.assertEqual(record['diagnostics']['visible_documents'], 3)
                self.assertNotIn('positive_patterns', record['task'])
                self.assertEqual(len(record['provenance']['annotations']), 3)
                hashes.append((record['provenance']['input_sha256'], record['provenance']['annotation_sha256']))
            self.assertEqual(len(set(hashes)), 1)
            page = (root / 'out/index.html').read_text(encoding='utf-8')
            self.assertIn('Yes / No', page)
            self.assertIn('未来知识', page)
            manifest = json.loads((root / 'out/manifest.json').read_text())
            self.assertEqual(manifest['artifact_type'], 'semantic_pipeline')
            self.assertIn('run_deepseek.py', manifest['code_sha256'])
            self.assertEqual(raw_before, {p.name: p.read_bytes() for p in data.iterdir()})

    def test_partial_failures_exclude_unprocessed_documents_and_do_not_leak_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, db = self.fixture(root)
            summary = self.execute(root, data, db, count=1, max_documents=4, client=FakeClient(fail=True))
            self.assertEqual(summary['status'], 'partial_model_failures')
            self.assertEqual(summary['llm_preprocessing']['failed_documents'], 1)
            self.assertEqual(summary['validated_documents'], 3)
            for mode in ('fixed','basic','enhanced'):
                record = json.loads((root / f'out/runs/m0/{mode}/result.json').read_text(encoding='utf-8'))
                self.assertEqual(record['diagnostics']['visible_documents'], 3)
            for file in (root / 'out').rglob('*'):
                if file.is_file():
                    self.assertNotIn('DO-NOT-PERSIST-SECRET', file.read_text(encoding='utf-8'))

    def test_default_five_distinct_events_bounded_calls_labels_only_after_all_forecasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, db = self.fixture(root, count=6, docs=12)
            original = Store.labels
            def labels(store, market):
                self.assertEqual(len(list((root / 'out/runs').glob('*/*/result.json'))), 15)
                return original(store, market)
            with patch.object(Store, 'labels', labels):
                summary = self.execute(root, data, db, client=FakeClient())
            self.assertEqual(summary['completed_tasks'], 5)
            self.assertEqual(summary['sampled_documents'], 50)
            self.assertEqual(summary['available_documents'], 60)
            self.assertEqual(len({row['event_id'] for row in summary['tasks']}), 5)

    def test_output_cache_and_parameter_guards_precede_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, db = self.fixture(root)
            client = FakeClient()
            with Store(db) as store:
                for output, cache in ((data / 'out', root / 'cache'),
                                      (root / 'out', data / 'cache'),
                                      (root / 'out', root / 'out/cache')):
                    with self.assertRaises(ValueError):
                        self.module().run_semantic_pipeline(store, data, CUTOFF, output,
                            cache=cache, client=client)
                for kwargs in ({'count':0}, {'max_documents':0}, {'workers':0}, {'max_chars':0}):
                    with self.assertRaises(ValueError):
                        self.module().run_semantic_pipeline(store, data, CUTOFF, root / 'out',
                            cache=root / 'cache', client=client, **kwargs)
                (root / 'out').mkdir(); (root / 'out/existing.txt').write_text('keep')
                with self.assertRaises(ValueError):
                    self.module().run_semantic_pipeline(store, data, CUTOFF, root / 'out',
                        cache=root / 'cache', client=client)
            self.assertEqual(client.calls, [])

    def test_document_selection_is_deterministic_and_rejects_both_future_clocks(self):
        module = self.module()
        task = dict(question='Will Alice Smith win?', cutoff=CUTOFF,
                    target_elements={'subject':'Alice Smith'})
        base = dict(event_id='e', published_at='2026-05-01T00:00:00Z',
                    observed_at='2026-05-02T00:00:00Z', text='Text')
        docs = [dict(base, id='a', title='Alice Smith wins'), dict(base, id='b', title='Unrelated'),
                dict(base, id='c', title='Alice Smith', published_at='2026-05-04T00:00:00Z'),
                dict(base, id='d', title='Alice Smith', observed_at='2026-05-04T00:00:00Z')]
        self.assertEqual([d['id'] for d in module.select_documents(task, docs, 1)], ['a'])
        self.assertEqual(module.select_documents(task, docs, 10), module.select_documents(task, docs[::-1], 10))
        self.assertEqual(len(module.select_documents(task, docs, 10)), 2)

    def test_all_failed_validations_produce_no_forecasts_but_retain_usage(self):
        class InvalidClient(FakeClient):
            def complete_json(self, messages, max_tokens=1800):
                response = super().complete_json(messages, max_tokens)
                response['data']['quote'] = 'Not present in any supplied evidence.'
                return response
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, db = self.fixture(root, docs=2)
            with patch.object(Store, 'labels', side_effect=AssertionError('No forecasts: no evaluation')):
                summary = self.execute(root, data, db, count=1, client=InvalidClient())
            self.assertEqual(summary['status'], 'partial_model_failures')
            self.assertEqual(summary['completed_tasks'], 0)
            self.assertEqual(summary['completed_runs'], 0)
            self.assertEqual(summary['llm_preprocessing']['failed_documents'], 2)
            self.assertEqual(summary['llm_preprocessing']['uncached_total_tokens'], 60)
            self.assertEqual(list((root / 'out/runs').glob('*/*/result.json')), [])

    def test_cached_usage_is_reported_separately_from_current_uncached_usage(self):
        class CachedClient(FakeClient):
            def complete_json(self, messages, max_tokens=1800):
                response = super().complete_json(messages, max_tokens)
                response['metadata']['cache_hit'] = True
                return response
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data, db = self.fixture(root, docs=2)
            summary = self.execute(root, data, db, count=1, client=CachedClient())
            self.assertEqual(summary['llm_preprocessing']['cached_calls'], 2)
            self.assertEqual(summary['llm_preprocessing']['total_tokens'], 60)
            self.assertEqual(summary['llm_preprocessing']['uncached_total_tokens'], 0)


if __name__ == '__main__':
    unittest.main()
