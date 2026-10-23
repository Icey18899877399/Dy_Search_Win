import importlib
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dynamic_retrieval.data.store import Store, build_index


CUTOFF = '2026-01-10T00:00:00Z'


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / 'archive'
        self.archive.mkdir()
        self.db = self.root / 'index.sqlite'

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, **kwargs):
        try:
            module = importlib.import_module('dynamic_retrieval.preparation')
        except ModuleNotFoundError:
            self.fail('Missing bounded experiment preparation')
        with Store(self.db) as store, patch.object(Store, 'labels', side_effect=AssertionError('labels accessed')):
            return module.prepare_cohort(store, self.archive, CUTOFF, **kwargs)

    def write(self, market='m1', event='e1', when='2026-01-09T00:00:00Z', docs=5, **fields):
        record = dict(market_id=market, question='Will A win by February 10, 2026?',
                      description='Resolves Yes if A wins.', outcomes=['Yes', 'No'],
                      active=True, closed=False, end_date='2026-02-11T00:00:00Z',
                      outcome_prices=['0.9', '0.1'], resolved_outcome='No')
        record.update(fields)
        articles = [dict(url=f'https://example.org/{event}/{i}', title='A wins',
                         full_text=f'A announced a win. Evidence {i}.', published_at=when)
                    for i in range(docs)]
        data = dict(collected_at=when, scraped_at=when,
                    events=[dict(event_id=event, markets=[record], articles=articles)])
        path = self.archive / (market + '.json')
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def test_pending_drafts_have_full_documents_and_no_price_or_label_fields(self):
        self.write()
        build_index(self.archive, self.db)
        result = self.prepare(count=1)
        self.assertEqual(result['completed'], 1)
        row = result['selected'][0]
        self.assertEqual(row['eligibility']['semantic_deadline_review'], 'pending')
        self.assertEqual(row['task']['cutoff'], '2026-01-10T00:00:00.000000Z')
        self.assertEqual(len(row['documents']), 5)
        self.assertTrue(all(doc['text'] for doc in row['documents']))
        for annotation in row['annotations'].values():
            self.assertIs(annotation['reviewed'], False)
            self.assertEqual(annotation['support'], [0, 0])
            self.assertEqual(annotation['review_status'], 'pending_human_review')
        serialized = json.dumps(result)
        for key in ('outcome_prices', 'resolved_outcome', 'final_prices'):
            self.assertNotIn(key, serialized)

    def test_ineligible_metadata_and_expired_question_dates_are_excluded(self):
        cases = [('closed', dict(closed=True)), ('inactive', dict(active=False)),
                 ('string', dict(active='true')), ('expired', dict(end_date=CUTOFF)),
                 ('futurestart', dict(start_date='2026-01-11T00:00:00Z')),
                 ('invalidstart', dict(start_date='yesterday')),
                 ('old', dict(when='2025-12-01T00:00:00Z')),
                 ('question', dict(question='Will A win by January 1, 2026?')),
                 ('isoquestion', dict(question='Will A win by 2026-01-01?')),
                 ('future', dict(when='2026-01-11T00:00:00Z'))]
        for name, fields in cases:
            self.write(market=name, event=name, **fields)
        self.write(market='valid', event='valid', end_date='2026-01-10T09:00:00+08:00')
        build_index(self.archive, self.db)
        result = self.prepare(count=5)
        self.assertEqual([row['task']['market_id'] for row in result['selected']], ['valid'])
        self.assertEqual(result['requested'], 5)
        self.assertEqual(result['completed'], 1)
        self.assertEqual(len(result['exclusions']), 9)

    def test_unique_events_determinism_and_document_minimum(self):
        self.write(market='m1', event='same')
        self.write(market='m2', event='same')
        self.write(market='m3', event='other')
        self.write(market='short', event='short', docs=4)
        build_index(self.archive, self.db)
        first = self.prepare(count=5)
        second = self.prepare(count=5)
        self.assertEqual(first, second)
        self.assertEqual(first['completed'], 2)
        self.assertEqual(len({x['task']['event_id'] for x in first['selected']}), 2)

    def test_changed_source_rejected(self):
        source = self.write()
        build_index(self.archive, self.db)
        source.write_text(source.read_text() + ' ', encoding='utf-8')
        result = self.prepare(count=1)
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['exclusions'][0]['reason'], 'source_hash_mismatch')

    def test_source_record_ambiguity_and_missing_status_fail_closed(self):
        path = self.write()
        data = json.loads(path.read_text())
        data['events'][0]['markets'].append(data['events'][0]['markets'][0].copy())
        path.write_text(json.dumps(data), encoding='utf-8')
        other = self.write(market='missing', event='missing')
        data = json.loads(other.read_text())
        del data['events'][0]['markets'][0]['active']
        other.write_text(json.dumps(data), encoding='utf-8')
        build_index(self.archive, self.db)
        self.assertEqual(self.prepare()['completed'], 0)

    def test_bounded_document_reads_stop_when_requested_cohort_is_complete(self):
        for i in range(8):
            self.write(market=f'm{i}', event=f'e{i}')
        build_index(self.archive, self.db)
        original = Store.documents
        calls = []
        def documents(store, event, cutoff):
            calls.append(event)
            return original(store, event, cutoff)
        with patch.object(Store, 'documents', documents):
            result = self.prepare(count=1)
        self.assertEqual(result['completed'], 1)
        self.assertEqual(len(calls), 1)

    def test_snapshot_question_and_observation_mismatches_are_rejected(self):
        self.write()
        build_index(self.archive, self.db)
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE tasks SET question='Will B win?'")
        connection.close()
        self.assertEqual(self.prepare()['exclusions'][0]['reason'], 'source_snapshot_mismatch')
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE tasks SET observed_at='2026-01-08T00:00:00.000000Z'")
        connection.close()
        self.assertEqual(self.prepare()['exclusions'][0]['reason'], 'source_observation_mismatch')

    def test_unsafe_source_is_rejected_and_future_documents_do_not_count(self):
        path = self.write(docs=5)
        data = json.loads(path.read_text())
        data['events'][0]['articles'][0]['published_at'] = '2026-01-11T00:00:00Z'
        path.write_text(json.dumps(data), encoding='utf-8')
        build_index(self.archive, self.db)
        self.assertEqual(self.prepare()['exclusions'][0]['reason'], 'insufficient_documents')
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE tasks SET source_file='../outside.json'")
        connection.close()
        self.assertEqual(self.prepare()['exclusions'][0]['reason'], 'unsafe_source_path')

    def test_timezone_required_and_wrong_source_root_rejected(self):
        self.write()
        build_index(self.archive, self.db)
        from dynamic_retrieval.preparation import prepare_cohort
        with Store(self.db) as store:
            with self.assertRaises(ValueError):
                prepare_cohort(store, self.archive, '2026-01-10T00:00:00')
            with self.assertRaises(ValueError):
                prepare_cohort(store, self.root, CUTOFF)


if __name__ == '__main__':
    unittest.main()
