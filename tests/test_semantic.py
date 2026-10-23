import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


TASK = {'question': 'Will Alice win the election in 2026?', 'description': '2026 election',
        'outcomes': ['Yes', 'No'], 'target_elements': {'subject': 'Alice', 'action': 'win',
        'object': 'election', 'time': '2026'}, 'cutoff': '2026-10-01T00:00:00Z'}
DOC = {'id': 'd1', 'title': 'Election report', 'text': 'Alice gained the endorsement today.'}
METADATA = {'model': 'deepseek-flash', 'excerpt': 'Election report\nAlice gained the endorsement today.'}
DATA = {'elements': {'subject': 'Alice', 'action': 'gained', 'object': 'endorsement'},
        'support': [1, -1], 'quote': 'Alice gained the endorsement today.',
        'rationale': 'The endorsement provides favorable evidence, without establishing the winner.',
        'factual_status': 'reported', 'time_scope': 'target_compatible'}


def response(content=None, finish='stop'):
    payload = {'id': 'request-1', 'model': 'deepseek-flash-resolved',
               'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30},
               'choices': [{'finish_reason': finish, 'message': {'role': 'assistant',
                    'content': json.dumps(DATA) if content is None else content,
                    'reasoning_content': 'PRIVATE INTERNAL REASONING'}}]}
    return io.BytesIO(json.dumps(payload).encode())


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('dynamic_retrieval.semantic'),
                             'Semantic adapter must exist')
        from dynamic_retrieval import semantic
        self.s = semantic

    def test_prompt_omits_labels_and_prices_and_limits_excerpt(self):
        task = dict(TASK, resolved_outcome='LEAKED', final_prices=[1, 0])
        messages = self.s.build_evidence_messages(task, DOC, max_chars=20)
        payload = json.loads(messages[1]['content'])
        self.assertNotIn('LEAKED', json.dumps(messages))
        self.assertNotIn('final_prices', json.dumps(messages))
        self.assertEqual(payload['task']['cutoff'], '2026-10-01T00:00:00Z')
        self.assertEqual(payload['evidence']['excerpt'], 'Election report\nAlic')

    def test_annotation_is_machine_unreviewed_bound_and_revalidated(self):
        annotation = self.s.validate_semantic(DATA, TASK, DOC, METADATA)
        self.assertIs(annotation['reviewed'], False)
        self.assertEqual(annotation['origin'], 'model')
        self.assertEqual(annotation['support'], [1, -1])
        self.assertEqual(self.s.validate_model_annotation(annotation, TASK, DOC), annotation)
        for altered_task, altered_doc in ((dict(TASK, question='Another task?'), DOC),
                (TASK, dict(DOC, text=DOC['text'] + ' changed')), (TASK, dict(DOC, title='Changed'))):
            with self.subTest(task=altered_task, doc=altered_doc), self.assertRaises(ValueError):
                self.s.validate_model_annotation(annotation, altered_task, altered_doc)

    def test_grounding_schema_and_temporal_gate_reject_invalid_nonzero(self):
        for change in ({'quote': 'made up'}, {'support': [True, -1]}, {'support': [2, 0]},
                       {'elements': {'unknown': 'x'}}, {'elements': {'subject': ''}},
                       {'elements': {}}, {'factual_status': 'opinion'},
                       {'time_scope': 'historical_other_cycle'}, {'time_scope': 'unknown'},
                       {'elements': {'time': '2026-11-01'}}, {'rationale': ''}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.s.validate_semantic(dict(DATA, **change), TASK, DOC, METADATA)
        with self.assertRaises(ValueError):
            self.s.validate_semantic(DATA, TASK, DOC, dict(METADATA, excerpt='Election report'))
        abstained = dict(DATA, elements={}, support=[0, 0], factual_status='irrelevant', time_scope='unknown')
        self.assertEqual(self.s.validate_semantic(abstained, TASK, DOC, METADATA)['support'], [0, 0])

    def test_annotation_marker_cannot_bypass_revalidation(self):
        annotation = self.s.validate_semantic(DATA, TASK, DOC, METADATA)
        for change in ({'support': [1, True]}, {'quote': 'invented'}, {'prompt_version': 'other'},
                       {'reviewed': True}, {'body_sha256': ''}, {'validation_status': 'unchecked'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.s.validate_model_annotation(dict(annotation, **change), TASK, DOC)

    def test_explicit_same_day_future_time_and_invalid_calendar_date_rejected(self):
        for timestamp in ('2026-10-01T01:00:00Z', '2026-02-31', '2026-13-01'):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.s.validate_semantic(dict(DATA, elements={'subject': 'Alice', 'time': timestamp}), TASK, DOC, METADATA)

    def test_creation_requires_model_and_original_prefix_excerpt(self):
        for change in ({'model': None}, {'model': ''}, {'model': '  '}, {'model': 123},
                       {'excerpt': None}, {'excerpt': ''}, {'excerpt': DOC['text']},
                       {'excerpt': METADATA['excerpt'] + ' invented suffix'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.s.validate_semantic(DATA, TASK, DOC, dict(METADATA, **change))
        for missing in ('model', 'excerpt'):
            metadata = dict(METADATA)
            del metadata[missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.s.validate_semantic(DATA, TASK, DOC, metadata)
        shortened = dict(DATA, quote='Election report')
        annotation = self.s.validate_semantic(shortened, TASK, DOC, dict(METADATA, excerpt='Election report'))
        self.assertEqual(annotation['excerpt'], 'Election report')

    def test_persisted_annotations_cannot_drop_model_or_excerpt(self):
        original = self.s.validate_semantic(DATA, TASK, DOC, METADATA)
        for field in ('model', 'excerpt'):
            for value in (None, '', '  ', 123):
                annotation = dict(original, **{field: value})
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.s.validate_model_annotation(annotation, TASK, DOC)
            annotation = dict(original)
            del annotation[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.s.validate_model_annotation(annotation, TASK, DOC)
        with self.assertRaises(ValueError):
            self.s.validate_model_annotation(dict(original, excerpt=DOC['text']), TASK, DOC)

    def test_market_odds_quote_or_rationale_cannot_provide_nonzero_support(self):
        signals = (
            'Trump’s statement boosts odds of Iranian regime falling by June 30 to 14%.',
            'Market-implied probability rose to 14%.',
            'Prediction-market prices suggest she will win.',
            'The YES 71% contract rose again.',
            'YES shares trade at 71 cents.',
            'YES contracts trade at 14 cents.',
            'Traders price a 14% chance.',
            'The prediction market gives a 14 percent chance.',
            'The betting market now favors Alice.',
            'Polymarket quotes a 71% probability.',
            'The implied probability climbed to 71%.',
            'Kalshi contracts gained 5 points.',
        )
        for signal in signals:
            for field in ('quote', 'rationale'):
                doc = dict(DOC, text=signal) if field == 'quote' else DOC
                metadata = dict(METADATA, excerpt=doc['title'] + '\n' + doc['text'])
                data = dict(DATA, **{field: signal})
                with self.subTest(signal=signal, field=field), self.assertRaisesRegex(ValueError, 'market'):
                    self.s.validate_semantic(data, TASK, doc, metadata)
        # Ordinary measured percentages and independent news remain usable.
        data = dict(DATA, rationale='Alice gained endorsements from 71% of local mayors.')
        self.assertEqual(self.s.validate_semantic(data, TASK, DOC, METADATA)['support'], [1, -1])

    def test_market_odds_can_be_recorded_only_as_abstention(self):
        data = dict(DATA, support=[0, 0], rationale='Market odds are not independent event evidence.')
        annotation = self.s.validate_semantic(data, TASK, DOC, METADATA)
        self.assertEqual(self.s.validate_model_annotation(annotation, TASK, DOC)['support'], [0, 0])
        with self.assertRaisesRegex(ValueError, 'market'):
            self.s.validate_model_annotation(dict(annotation, support=[1, -1]), TASK, DOC)

    def test_current_runtime_rejects_legacy_v1_annotations(self):
        annotation = self.s.validate_semantic(DATA, TASK, DOC, METADATA)
        with self.assertRaises(ValueError):
            self.s.validate_model_annotation(dict(annotation, prompt_version='evidence-semantics-v1'), TASK, DOC)

    def test_duplicate_json_keys_and_nonfinite_json_never_cached(self):
        for content in ('{"support": [0,0], "support": [1,-1]}', '{"value": NaN}'):
            with tempfile.TemporaryDirectory() as directory:
                client = self.s.DeepSeekClient(directory, api_key='fake')
                with patch.object(client._opener, 'open', return_value=response(content)):
                    with self.assertRaises(self.s.DeepSeekError):
                        client.complete_json([{'role': 'user', 'content': 'x'}])
                self.assertEqual(list(Path(directory).glob('*.json')), [])

    def test_cache_offline_provenance_and_no_secrets_or_reasoning(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.s.DeepSeekClient(directory, api_key='FAKE-SECRET')
            messages = self.s.build_evidence_messages(TASK, DOC)
            seen = []
            def transport(request, timeout):
                seen.append(request)
                self.assertEqual(request.full_url, 'https://api.deepseek.com/chat/completions')
                wire = json.loads(request.data)
                self.assertEqual(wire['response_format'], {'type': 'json_object'})
                self.assertEqual(wire['thinking'], {'type': 'disabled'})
                return response()
            with patch.object(client._opener, 'open', side_effect=transport):
                first = client.complete_json(messages)
            self.assertEqual(len(seen), 1)
            self.assertEqual(first['data'], DATA)
            self.assertFalse(first['metadata']['cache_hit'])
            self.assertEqual(first['metadata']['model'], 'deepseek-flash-resolved')
            self.assertEqual(first['metadata']['request_id'], 'request-1')
            with patch.dict('os.environ', {}, clear=True):
                offline = self.s.DeepSeekClient(directory)
                with patch.object(offline._opener, 'open', side_effect=AssertionError('Network forbidden')):
                    cached = offline.complete_json(messages)
                    self.assertTrue(cached['metadata']['cache_hit'])
                    for changed, tokens in ((messages, 1500), (messages + [{'role':'user','content':'Changed'}],1800)):
                        with self.assertRaises(self.s.DeepSeekError):
                            offline.complete_json(changed, max_tokens=tokens)
            stored = next(Path(directory).glob('*.json')).read_text(encoding='utf-8')
            self.assertNotIn('FAKE-SECRET', stored)
            self.assertNotIn('PRIVATE INTERNAL REASONING', stored)
            self.assertIn('Alice gained', stored)

    def test_retry_transient_errors_and_fail_auth_without_secret_error_text(self):
        for status, expected_attempts in ((401, 1), (402, 1), (429, 3), (503, 3)):
            with tempfile.TemporaryDirectory() as directory:
                client = self.s.DeepSeekClient(directory, api_key='FAKE-SECRET')
                error = HTTPError('url', status, 'FAKE-SECRET', {}, io.BytesIO(b'FAKE-SECRET'))
                with patch.object(client._opener, 'open', side_effect=error) as transport, patch.object(self.s.time, 'sleep'):
                    with self.assertRaises(self.s.DeepSeekError) as caught:
                        client.complete_json([{'role': 'user', 'content': 'hi'}])
                    self.assertEqual(transport.call_count, expected_attempts)
                    self.assertNotIn('FAKE-SECRET', str(caught.exception))
                    self.assertIsNone(caught.exception.__cause__)

    def test_timeout_can_recover_and_invalid_completion_is_never_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.s.DeepSeekClient(directory, api_key='fake')
            with patch.object(client._opener, 'open', side_effect=[TimeoutError('secret'), response()]), patch.object(self.s.time, 'sleep'):
                self.assertEqual(client.complete_json([{'role':'user','content':'x'}])['data'], DATA)
        for content, finish in (('not json', 'stop'), ('[]', 'stop'), ('{}', 'stop'), (json.dumps(DATA), 'length')):
            with tempfile.TemporaryDirectory() as directory:
                client = self.s.DeepSeekClient(directory, api_key='fake')
                with patch.object(client._opener, 'open', return_value=response(content, finish)):
                    with self.assertRaises(self.s.DeepSeekError):
                        client.complete_json([{'role':'user','content':'x'}])
                self.assertEqual(list(Path(directory).glob('*.json')), [])

    def test_redirect_handler_never_reissues_request(self):
        from urllib.request import Request
        request = Request('https://api.deepseek.com/chat/completions', headers={'Authorization':'Bearer fake'})
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code), self.assertRaises(self.s.DeepSeekError):
                self.s._NoRedirect().redirect_request(request, None, code, 'redirect', {}, 'https://thirdparty.test')


if __name__ == '__main__':
    unittest.main()
