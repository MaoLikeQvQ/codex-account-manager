import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from manager_parts.quota_estimate import estimate_quota_amounts
from manager_parts.usage import API_PRICES


class QuotaEstimateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.now = datetime.now(timezone.utc)
        self.manager = Mock()
        self.manager.paths = SimpleNamespace(codex_home=self.home, app_home=self.home / 'manager')
        pricing = patch('manager_parts.quota_estimate.get_api_prices', return_value=(API_PRICES, {'status': 'cached'}))
        pricing.start()
        self.addCleanup(pricing.stop)
        self.manager._account_type.side_effect = lambda value: value['account_type']
        self.store = {'active_account': 'official', 'accounts': {'official': {'account_type': 'official'}}}
        self.manager._load_store.return_value = self.store
        self.limits = {'rateLimitsByLimitId': {'codex': {
            'primary': self.window(300, 10), 'secondary': self.window(10080, 20)}}}

    def window(self, duration, used):
        return {'usedPercent': used, 'windowDurationMins': duration,
                'resetsAt': (self.now + timedelta(minutes=duration-60)).timestamp()}

    def write_usage(self, model='gpt-5.4', provider='openai'):
        directory = self.home / 'sessions'
        directory.mkdir(exist_ok=True)
        events = [
            {'type': 'session_meta', 'payload': {'model_provider': provider}},
            {'type': 'turn_context', 'payload': {'model': model}},
            {'type': 'event_msg', 'timestamp': (self.now-timedelta(minutes=10)).isoformat(),
             'payload': {'type': 'token_count', 'info': {'total_token_usage': {
                 'input_tokens': 100000, 'cached_input_tokens': 20000,
                 'output_tokens': 10000, 'reasoning_output_tokens': 5000}}}},
        ]
        info = events[-1]['payload']['info']
        info['last_token_usage'] = dict(info['total_token_usage'])
        (directory / 'sample.jsonl').write_text('\n'.join(map(json.dumps, events)))

    def estimate(self):
        return estimate_quota_amounts(self.manager, 'official', self.limits, self.now)

    def test_price_weighted_estimate_for_each_window(self):
        self.write_usage()
        result = self.estimate()
        # $0.20 input + $0.005 cached + $0.15 output; reasoning is included in output.
        primary = result['windows']['codex:primary']
        self.assertAlmostEqual(primary['sample_usd'], .355)
        self.assertAlmostEqual(primary['total_usd'], 3.55)
        self.assertAlmostEqual(primary['remaining_usd'], 3.195)
        self.assertAlmostEqual(result['windows']['codex:secondary']['total_usd'], 1.775)
        self.assertEqual(result['currency'], 'USD')

    def test_low_percentage_keeps_estimate_with_warning(self):
        self.write_usage()
        self.limits['rateLimitsByLimitId']['codex']['secondary']['usedPercent'] = 1
        result = self.estimate()['windows']
        self.assertAlmostEqual(result['codex:secondary']['total_usd'], 35.5)
        self.assertIn('样本较少', result['codex:secondary']['note'])
        self.assertNotIn('note', result['codex:primary'])

    def test_current_model_has_price(self):
        self.write_usage(model='gpt-6.1-sol')
        result = self.estimate()['windows']['codex:primary']
        self.assertAlmostEqual(result['sample_usd'], .262)
        self.assertAlmostEqual(result['total_usd'], 2.62)

    def test_unknown_model_cannot_produce_partial_amount(self):
        self.write_usage(model='unpriced-model')
        reason = self.estimate()['windows']['codex:primary']['reason']
        self.assertIn('缺少价格', reason)
        self.assertIn('unpriced-model', reason)

    def test_other_provider_and_expired_period_not_counted(self):
        self.write_usage(provider='MaoLocal')
        self.assertNotIn('total_usd', self.estimate()['windows']['codex:primary'])
        self.limits['rateLimitsByLimitId']['codex']['primary']['resetsAt'] = self.now.timestamp()-1
        self.assertIn('已过期', self.estimate()['windows']['codex:primary']['reason'])

    def test_account_and_bucket_isolation(self):
        self.store['accounts']['another'] = {'account_type': 'official'}
        self.assertIn('多个官方账号', self.estimate()['reason'])
        del self.store['accounts']['another']
        self.store['active_account'] = 'another'
        self.assertNotIn('total_usd', self.estimate())
        self.store['active_account'] = 'official'
        self.limits['rateLimitsByLimitId']['extra'] = {}
        self.assertIn('独立额度', self.estimate()['reason'])

    def test_invalid_values_do_not_generate_amounts(self):
        window = self.limits['rateLimitsByLimitId']['codex']['primary']
        for value in (None, 0, -1, 101, float('nan'), True):
            window['usedPercent'] = value
            self.assertNotIn('total_usd', self.estimate()['windows']['codex:primary'])
        window['usedPercent'] = 10
        window['resetsAt'] = float('inf')
        self.assertNotIn('total_usd', self.estimate()['windows']['codex:primary'])


if __name__ == '__main__':
    unittest.main()
