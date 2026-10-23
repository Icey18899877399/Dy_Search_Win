import hashlib
import unittest
from dynamic_retrieval.source_history import historical_body_candidate

CUT = '2026-05-31T23:59:59Z'
TASK = {'event_id': 'e', 'cutoff': CUT, 'observed_at': '2026-05-01T00:00:00Z'}
BODY = 'The Knesset voted unanimously on Wednesday in favor of a dissolution bill. This was a preliminary reading; three further readings remain.'
WRAPPER = 'The Wayback Machine - https://web.archive.org/web/20260521070528/https://example.test/news'

def document(id, body, observed='2026-05-20T00:00:00Z', **kwargs):
    row = dict(id=id, text=body, event_id='e', canonical_url='https://example.test/news', observed_at=observed,
               published_at='2026-05-19T00:00:00Z', content_hash=hashlib.sha256(body.encode()).hexdigest(), scrape_status='success')
    row.update(kwargs)
    return row

class SourceHistoryTests(unittest.TestCase):
    def test_recovers_own_provenance_without_mutating_inputs(self):
        old = document('old', BODY)
        new = document('new', WRAPPER, '2026-05-30T00:00:00Z')
        out = historical_body_candidate(TASK, [old, new])
        self.assertEqual(out['status'], 'historical_body_candidate')
        self.assertEqual(out['document'], old)
        self.assertEqual(out['latest_visible_id'], 'new')
        self.assertEqual(out['skipped'][0]['reason'], 'archive_wrapper_only')
        self.assertEqual(new['text'], WRAPPER)
        self.assertFalse(out['prediction_input_replaced'])
    def test_substantive_correction_is_never_replaced_even_with_failure_status(self):
        for status in ('success', 'error'):
            correction = document('new', 'Correction: the reported dissolution vote never occurred.', '2026-05-30T00:00:00Z', scrape_status=status)
            out = historical_body_candidate(TASK, [document('old', BODY), correction])
            self.assertEqual(out['document']['id'], 'new')
            self.assertEqual(out['status'], 'latest_substantive_body')
    def test_both_clocks_and_task_visibility_are_required(self):
        for field in ('published_at', 'observed_at'):
            bad = document('late', BODY, **{field: '2026-06-01T00:00:00Z'}) if field=='published_at' else document('late', BODY, '2026-06-01T00:00:00Z')
            out = historical_body_candidate(TASK, [bad, document('wrapper', WRAPPER)])
            self.assertIsNone(out['document'])
            self.assertIn(field+'_after_cutoff', out['excluded'][0]['reasons'])
        with self.assertRaises(ValueError):
            historical_body_candidate(dict(TASK, observed_at='2026-06-01T00:00:00Z'), [])
    def test_missing_timezone_and_body_hash_mismatch_rejected(self):
        out = historical_body_candidate(TASK, [document('bad', BODY, '2026-05-20')])
        self.assertIsNone(out['document'])
        with self.assertRaisesRegex(ValueError, 'hash'):
            historical_body_candidate(TASK, [document('bad', BODY, content_hash='bad')])
    def test_mixed_urls_or_events_raise(self):
        for kw in ({'event_id':'other'}, {'canonical_url':'https://example.test/other'}):
            with self.assertRaises(ValueError):
                historical_body_candidate(TASK, [document('a', BODY), document('b', WRAPPER, **kw)])
    def test_latest_substantive_body_retained_regardless_of_length_or_direction(self):
        for body in ('No.', 'Correction: '+('unrelated text '*20000)):
            out = historical_body_candidate(TASK, [document('old', BODY), document('new', body, '2026-05-30T00:00:00Z')])
            self.assertEqual(out['document']['id'], 'new')
    def test_empty_and_access_pages_can_be_skipped_but_full_articles_mentioning_them_cannot(self):
        for body in ('', 'Access denied', 'Just a moment'):
            out = historical_body_candidate(TASK, [document('old', BODY), document('new', body, '2026-05-30T00:00:00Z')])
            self.assertEqual(out['document']['id'], 'old')
        body = 'Access denied to reporters, the official said. '+BODY
        out = historical_body_candidate(TASK, [document('old', BODY), document('new', body, '2026-05-30T00:00:00Z')])
        self.assertEqual(out['document']['id'], 'new')
    def test_ties_are_deterministic_and_empty_input_is_explicit(self):
        a, b = document('a', BODY), document('b', WRAPPER)
        self.assertEqual(historical_body_candidate(TASK,[b,a])['document']['id'], 'a')
        self.assertEqual(historical_body_candidate(TASK,[])['status'], 'no_visible_substantive_body')

if __name__ == '__main__': unittest.main()
