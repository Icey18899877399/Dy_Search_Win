import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from dynamic_retrieval import semantic

MESSAGES = [{'role': 'user', 'content': 'private request text'}]
USAGE = {'prompt_tokens': 11, 'completion_tokens': 7, 'total_tokens': 18}


def completion(content='{"ok":true}', usage=USAGE, finish='stop'):
    return {'model': 'deepseek-flash', 'id': 'request-id', 'usage': usage,
            'choices': [{'finish_reason': finish, 'message': {'content': content}}]}


class Response:
    def __init__(self, body, read_error=None):
        self.body = body
        self.read_error = read_error
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def geturl(self):
        return semantic.ENDPOINT
    def read(self):
        if self.read_error:
            raise self.read_error
        return self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()


class Opener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
    def open(self, request, timeout):
        self.requests.append(json.loads(request.data))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class CallCostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / 'cache'

    def client(self, responses, ledger=None, **kwargs):
        client = semantic.DeepSeekClient(self.cache, api_key='secret-value', cost_ledger=ledger, **kwargs)
        client._opener = Opener(responses)
        return client

    def ledger(self, **kwargs):
        from dynamic_retrieval.call_cost import CallCostLedger
        return CallCostLedger(**kwargs)

    def test_optional_telemetry_preserves_payload_cache_and_result(self):
        self.assertIn('cost_ledger', __import__('inspect').signature(semantic.DeepSeekClient).parameters)
        ledger = self.ledger()
        client = self.client([Response(completion())], ledger)
        result = client.complete_json(MESSAGES)
        cached = self.client([], ledger).complete_json(MESSAGES)
        self.assertEqual(result['data'], {'ok': True})
        self.assertTrue(cached['metadata']['cache_hit'])
        self.assertEqual(cached['metadata']['cache_key'], result['metadata']['cache_key'])
        self.assertEqual(client._opener.requests, [{'model': 'deepseek-flash', 'messages': MESSAGES,
            'max_tokens': 1800, 'temperature': 0, 'thinking': {'type': 'disabled'},
            'response_format': {'type': 'json_object'}}])
        summary = ledger.snapshot()
        self.assertEqual(summary['network_attempts'], 1)
        self.assertEqual(summary['cache_hits'], 1)
        self.assertEqual(summary['actual_usage']['total_tokens'], 18)
        self.assertEqual(summary['historical_cache_usage']['total_tokens'], 18)
        self.assertTrue(all(e['elapsed_seconds'] >= 0 for e in summary['events']))
        self.assertNotIn('secret-value', json.dumps(summary))
        self.assertNotIn('private request text', json.dumps(summary))

    def test_retry_accounts_for_unknown_failed_attempt(self):
        ledger = self.ledger()
        client = self.client([TimeoutError('secret-value'), Response(completion())], ledger)
        with patch.object(semantic.time, 'sleep'):
            client.complete_json(MESSAGES)
        summary = ledger.snapshot()
        self.assertEqual(summary['network_attempts'], 2)
        self.assertEqual(summary['failed_network_attempts'], 1)
        self.assertEqual(summary['unknown_usage_attempts'], 1)
        self.assertIsNone(summary['actual_usage']['total_tokens'])
        self.assertEqual(summary['observed_usage']['total_tokens'], 18)
        self.assertEqual([e['attempt'] for e in summary['events']], [1, 2])
        self.assertNotIn('secret-value', json.dumps(summary))

    def test_invalid_completion_preserves_observed_usage(self):
        for raw in (completion('bad json'), completion('{}', finish='length'),
                    {'model': 'deepseek-flash', 'usage': USAGE, 'choices': []}):
            with self.subTest(raw=raw):
                ledger = self.ledger()
                with self.assertRaises(semantic.DeepSeekError):
                    self.client([Response(raw)], ledger).complete_json(MESSAGES)
                summary = ledger.snapshot()
                self.assertEqual(summary['network_attempts'], 1)
                self.assertEqual(summary['failed_network_attempts'], 1)
                self.assertEqual(summary['actual_usage']['total_tokens'], 18)
                self.assertEqual(summary['events'][0]['error_category'], 'completion')

    def test_transport_and_decode_failures_are_counted_without_secrets(self):
        failures = [HTTPError(semantic.ENDPOINT, 401, 'secret-value', {}, None),
                    OSError('secret-value'), Response(b'not json'),
                    Response(None, OSError('secret-value'))]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                ledger = self.ledger()
                with self.assertRaises(semantic.DeepSeekError):
                    self.client([failure], ledger, max_attempts=1).complete_json(MESSAGES)
                summary = ledger.snapshot()
                self.assertEqual(summary['network_attempts'], 1)
                self.assertEqual(summary['failed_network_attempts'], 1)
                self.assertIsNone(summary['actual_usage']['total_tokens'])
                self.assertNotIn('secret-value', json.dumps(summary))

    def test_cache_write_failure_retains_billed_usage(self):
        ledger = self.ledger()
        with patch.object(semantic.os, 'replace', side_effect=OSError('secret-value')):
            with self.assertRaises(semantic.DeepSeekError):
                self.client([Response(completion())], ledger).complete_json(MESSAGES)
        summary = ledger.snapshot()
        self.assertEqual(summary['actual_usage']['total_tokens'], 18)
        self.assertEqual(summary['events'][0]['error_category'], 'cache_write')

    def test_cache_cleanup_failure_cannot_trigger_another_network_attempt(self):
        ledger = self.ledger()
        client = self.client([Response(completion())], ledger)
        with patch.object(semantic.os, 'replace', side_effect=OSError('secret-value')):
            with patch.object(semantic.Path, 'unlink', side_effect=TimeoutError('secret-value')):
                with patch.object(semantic.time, 'sleep'):
                    with self.assertRaises(semantic.DeepSeekError):
                        client.complete_json(MESSAGES)
        self.assertEqual(ledger.snapshot()['network_attempts'], 1)
        self.assertEqual(ledger.snapshot()['actual_usage']['total_tokens'], 18)
        self.assertEqual(ledger.snapshot()['events'][0]['error_category'], 'cache_write')

    def test_cache_only_has_zero_actual_usage_and_bad_cache_records_failure(self):
        self.client([Response(completion())]).complete_json(MESSAGES)
        ledger = self.ledger()
        self.client([], ledger).complete_json(MESSAGES)
        self.assertEqual(ledger.snapshot()['actual_usage']['total_tokens'], 0)
        self.assertEqual(ledger.snapshot()['network_attempts'], 0)
        next(self.cache.glob('*.json')).write_text('bad json', encoding='utf-8')
        with self.assertRaises(semantic.DeepSeekError):
            self.client([], ledger).complete_json(MESSAGES)
        self.assertEqual(ledger.snapshot()['cache_reads'], 2)
        self.assertEqual(ledger.snapshot()['cache_hits'], 1)

    def test_unknown_and_partial_usage_never_synthesizes_zero(self):
        for usage in (None, {}, {'total_tokens': True}, {'prompt_tokens': 4}):
            with self.subTest(usage=usage):
                ledger = self.ledger()
                client = self.client([Response(completion(usage=usage))], ledger)
                try:
                    client.complete_json(MESSAGES)
                except semantic.DeepSeekError:
                    pass
                self.assertIsNone(ledger.snapshot()['actual_usage']['total_tokens'])
                for path in self.cache.glob('*.json'):
                    path.unlink()

    def test_thread_safe_durable_events_and_snapshot_isolation(self):
        path = Path(self.temp.name) / 'ledger.jsonl'
        ledger = self.ledger(jsonl_path=path)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: ledger.record('network_attempt', elapsed_seconds=0.1,
                          outcome='success', usage=USAGE, attempt=1), range(80)))
        summary = ledger.snapshot()
        self.assertEqual(summary['network_attempts'], 80)
        self.assertEqual(summary['actual_usage']['total_tokens'], 1440)
        self.assertEqual(len(path.read_text(encoding='utf-8').splitlines()), 80)
        summary['events'][0]['usage']['total_tokens'] = 999
        self.assertEqual(ledger.snapshot()['events'][0]['usage']['total_tokens'], 18)

    def test_post_response_persistence_failure_retains_observation(self):
        from dynamic_retrieval.call_cost import CallCostError
        path = Path(self.temp.name) / 'ledger.jsonl'
        ledger = self.ledger(jsonl_path=path)
        class BlockLedger(Response):
            def read(inner):
                path.unlink()
                path.mkdir()
                return super().read()
        client = self.client([BlockLedger(completion())], ledger)
        with self.assertRaises(CallCostError):
            client.complete_json(MESSAGES)
        self.assertEqual(len(client._opener.requests), 1)
        self.assertEqual(ledger.snapshot()['actual_usage']['total_tokens'], 18)

    def test_retriable_http_failures_each_have_their_own_event(self):
        ledger = self.ledger()
        failures = [HTTPError(semantic.ENDPOINT, status, 'secret-value', {}, None)
                    for status in (429, 503)]
        with patch.object(semantic.time, 'sleep'):
            with self.assertRaises(semantic.DeepSeekError):
                self.client(failures, ledger, max_attempts=2).complete_json(MESSAGES)
        summary = ledger.snapshot()
        self.assertEqual(summary['network_attempts'], 2)
        self.assertEqual(summary['failed_network_attempts'], 2)
        self.assertEqual([e['http_status'] for e in summary['events']], [429, 503])
        self.assertIsNone(summary['actual_usage']['total_tokens'])

    def test_usage_survives_response_exit_failure(self):
        ledger = self.ledger()
        class ExitFailure(Response):
            def __exit__(self, *args):
                raise OSError('secret-value')
        with self.assertRaises(semantic.DeepSeekError):
            self.client([ExitFailure(completion())], ledger).complete_json(MESSAGES)
        self.assertEqual(ledger.snapshot()['actual_usage']['total_tokens'], 18)
        self.assertEqual(ledger.snapshot()['failed_network_attempts'], 1)

    def test_missing_credentials_never_count_as_network_attempt(self):
        ledger = self.ledger()
        client = self.client([], ledger)
        client._api_key = None
        with self.assertRaises(semantic.DeepSeekError):
            client.complete_json(MESSAGES)
        self.assertEqual(ledger.snapshot()['network_attempts'], 0)

    def test_unknown_historical_cache_usage_stays_unknown(self):
        self.client([Response(completion(usage={}))]).complete_json(MESSAGES)
        ledger = self.ledger()
        self.client([], ledger).complete_json(MESSAGES)
        summary = ledger.snapshot()
        self.assertIsNone(summary['historical_cache_usage']['total_tokens'])
        self.assertEqual(summary['actual_usage']['total_tokens'], 0)
        self.assertEqual(summary['historical_unknown_usage_reads'], 1)

    def test_ledger_failure_is_explicit_and_does_not_retry_request(self):
        from dynamic_retrieval.call_cost import CallCostError
        path = Path(self.temp.name) / 'directory'
        path.mkdir()
        ledger = self.ledger(jsonl_path=path)
        client = self.client([Response(completion())], ledger)
        with self.assertRaises(CallCostError) as raised:
            client.complete_json(MESSAGES)
        self.assertNotIn('secret-value', str(raised.exception))
        self.assertEqual(len(client._opener.requests), 0)
        self.assertEqual(ledger.snapshot()['network_attempts'], 0)


if __name__ == '__main__':
    unittest.main()
