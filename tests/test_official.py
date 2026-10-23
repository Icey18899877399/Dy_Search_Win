import unittest
from unittest.mock import patch
from urllib.request import Request
from dynamic_retrieval.official import collect, get_json, NoRedirect

class OfficialTests(unittest.TestCase):
    def test_endpoint_allowlist_and_redirects_fail_closed(self):
        for url in ('https://example.com/a','http://gamma-api.polymarket.com/markets/1',
                    'https://gamma-api.polymarket.com/markets/1/../../secrets'):
            with self.assertRaises(ValueError):get_json(url)
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(Request('https://gamma-api.polymarket.com/markets/1'),None,302,'',{},'https://example.com')

    def test_failure_is_explicit_and_secret_exception_text_is_not_saved(self):
        def fail(url):raise OSError('SENSITIVE-EXCEPTION-TEXT')
        result=collect({'market_id':'1'},getter=fail)
        self.assertEqual(result['label']['status'],'fetch_failed')
        self.assertNotIn('SENSITIVE-EXCEPTION-TEXT',str(result))
