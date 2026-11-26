import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from manager_parts.pricing import CACHE_TTL, MODELS_DEV, LITELLM, OPENROUTER, get_api_prices, parse_api_prices, parse_structured_prices
from manager_parts.usage import _cost

TABLE = '''# Official API pricing
| Model | Short context input | Short context cached input | Short context cache writes | Short context output | Long context input | Long context cached input | Long context cache writes | Long context output |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-future | $2.00 | $0.10 | $2.50 | $10.00 | $4.00 | $0.20 | $5.00 | $15.00 |
| gpt-legacy (<272K context length) | $5.00 | - | - | $30.00 | - | - | - | - |

## Fast pricing
| gpt-future | $4.00 | $0.20 | $5.00 | $20.00 | $8.00 | $0.40 | $10.00 | $30.00 |
'''


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def response(self, markdown=TABLE):
        response = Mock()
        response.read.return_value = markdown.encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_parser_uses_standard_table_and_normalizes_models(self):
        rates = parse_api_prices(TABLE)
        self.assertEqual(rates['gpt-future'][0], [2, .1, 2.5, 10])
        self.assertIsNone(rates['gpt-legacy'][1])
        usage = {'input_tokens': 100000, 'cached_input_tokens': 20000,
                 'cache_write_input_tokens': 0, 'output_tokens': 10000}
        self.assertAlmostEqual(_cost('gpt-future', usage, False, rates), .262)
        usage['input_tokens'] = 300000
        self.assertAlmostEqual(_cost('gpt-future', usage, False, rates), 1.274)

    def test_models_dev_download_then_reuse_daily_cache(self):
        data = {'openai': {'models': {'gpt-future': {'cost': {
            'input': 2, 'cache_read': .1, 'cache_write': 2.5, 'output': 10,
            'tiers': [{'tier': {'type': 'context', 'size': 272000}, 'input': 4,
                       'cache_read': .2, 'cache_write': 5, 'output': 15}],
        }}}}}
        with patch('manager_parts.pricing.urlopen', return_value=self.response(json.dumps(data))) as opener:
            rates, first = get_api_prices(self.home)
            again, second = get_api_prices(self.home)
        self.assertEqual(rates, again)
        self.assertEqual(first['source'], MODELS_DEV)
        self.assertEqual(second['status'], 'cached')
        self.assertEqual(rates['gpt-future'], [[2, .1, 2.5, 10], [4, .2, 5, 15]])
        opener.assert_called_once()
        self.assertFalse(opener.call_args.args[0].has_header('Authorization'))

    def test_structured_fallback_converts_per_token_and_keeps_provider_scope(self):
        data = {'gpt-future': {'litellm_provider': 'openai', 'input_cost_per_token': .000002,
                'output_cost_per_token': .00001},
                'other/gpt-future': {'litellm_provider': 'openai', 'input_cost_per_token': 1,
                'output_cost_per_token': 1}}
        with patch('manager_parts.pricing.urlopen', side_effect=[OSError('offline'), self.response(json.dumps(data))]):
            rates, metadata = get_api_prices(self.home)
        self.assertEqual(metadata['source'], LITELLM)
        self.assertEqual(rates['gpt-future'][0], [2, None, None, 10])
        self.assertNotIn('other/gpt-future', rates)

    def test_force_refresh_bypasses_a_fresh_cache_and_keeps_it_if_offline(self):
        def data(output):
            return json.dumps({'openai': {'models': {'gpt-future': {'cost': {'input': 2, 'output': output}}}}})

        responses = [self.response(data(10)), self.response(data(12))] + [OSError('offline')] * 3
        with patch('manager_parts.pricing.urlopen', side_effect=responses):
            get_api_prices(self.home)
            updated, metadata = get_api_prices(self.home, force_refresh=True)
            offline, offline_metadata = get_api_prices(self.home, force_refresh=True)
            cached, cached_metadata = get_api_prices(self.home)

        self.assertEqual(updated['gpt-future'][0][3], 12)
        self.assertEqual(metadata['status'], 'fresh')
        self.assertEqual(offline, updated)
        self.assertEqual(offline_metadata['status'], 'stale')
        self.assertEqual(cached, updated)
        self.assertEqual(cached_metadata['status'], 'cached')

    def test_model_missing_from_online_prices_uses_bundled_short_and_long_rates(self):
        usage = {'input_tokens': 100000, 'cached_input_tokens': 20000,
                 'cache_write_input_tokens': 10000, 'output_tokens': 10000}
        self.assertAlmostEqual(_cost('gpt-6.2-astra', usage, False, {}), 1.068)
        usage['input_tokens'] = 300000
        self.assertAlmostEqual(_cost('gpt-6.2-astra', usage, False, {}), 5.136)

    def test_openrouter_is_used_when_first_two_sources_fail(self):
        data = {'data': [{'id': 'openai/gpt-future', 'pricing': {
            'prompt': '.000001', 'completion': '.000005'}}]}
        with patch('manager_parts.pricing.urlopen', side_effect=[OSError('offline'), OSError('offline'),
                                                                  self.response(json.dumps(data))]):
            rates, metadata = get_api_prices(self.home)
        self.assertEqual(metadata['source'], OPENROUTER)
        self.assertEqual(rates['gpt-future'][0], [1, None, None, 5])

    def test_openrouter_and_unsupported_context_tiers(self):
        data = {'data': [{'id': 'openai/gpt-future', 'pricing': {'prompt': '.000001',
                 'completion': '.000005', 'overrides': [{'min_prompt_tokens': 272000,
                 'prompt': '.000002', 'completion': '.0000075'}]}}]}
        rates = parse_structured_prices(data, OPENROUTER)
        self.assertEqual(rates['gpt-future'], [[1, None, None, 5], [2, None, None, 7.5]])
        data['data'][0]['pricing']['overrides'][0]['min_prompt_tokens'] = 128000
        with self.assertRaises(ValueError):
            parse_structured_prices(data, OPENROUTER)

    def test_stale_cache_retained_and_failure_visible(self):
        path = self.home / 'api-prices-cache.json'
        path.write_text(json.dumps({'markdown': TABLE, 'fetched_at': time.time()-CACHE_TTL-1}))
        with patch('manager_parts.pricing.urlopen', side_effect=OSError('offline')):
            rates, metadata = get_api_prices(self.home)
        self.assertIn('gpt-future', rates)
        self.assertEqual(metadata['status'], 'stale')
        self.assertIn('更新失败', metadata['warning'])

    def test_bad_response_does_not_overwrite_previous_cache(self):
        path = self.home / 'api-prices-cache.json'
        original = json.dumps({'markdown': TABLE, 'fetched_at': time.time()-CACHE_TTL-1})
        path.write_text(original)
        with patch('manager_parts.pricing.urlopen', return_value=self.response('unexpected page')):
            _, metadata = get_api_prices(self.home)
        self.assertEqual(metadata['status'], 'stale')
        self.assertEqual(path.read_text(), original)

    def test_missing_cache_failure_has_explicit_builtin_fallback(self):
        with patch('manager_parts.pricing.urlopen', side_effect=OSError('offline')):
            rates, metadata = get_api_prices(self.home)
        self.assertIn('gpt-6.1-sol', rates)
        self.assertEqual(metadata['status'], 'bundled')
        self.assertIn('内置价格', metadata['warning'])

    def test_incomplete_or_invalid_table_rejected(self):
        for markdown in ('', TABLE.replace('$2.00', '$nan'), TABLE.replace('$2.00', '-')):
            with self.assertRaises(ValueError):
                parse_api_prices(markdown)


if __name__ == '__main__':
    unittest.main()
