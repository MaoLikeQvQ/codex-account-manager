import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from manager_parts.quota import read_official_quota


class QuotaTests(unittest.TestCase):
    def test_isolated_account_partial_failure_and_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            manager = Mock()
            manager.paths.app_home = Path(root)
            manager._load_store.return_value = {'accounts': {'chosen': {'official_auth': {'token': 'fake'}}}}
            manager._account_type.return_value = 'official'
            manager._codex_environment.return_value = {'OPENAI_API_KEY': 'fake', 'OPENAI_BASE_URL': 'https://example.com'}
            manager._codex_binary.return_value = 'codex'
            process = Mock()
            process.stdin = io.StringIO()
            process.stdout = io.StringIO('\n'.join(json.dumps(x) for x in [
                {'id': 1, 'result': {}},
                {'id': 2, 'result': {'rateLimits': {'primary': {'usedPercent': 25, 'windowDurationMins': 300}}}},
                {'id': 3, 'error': {'message': 'secret must not leak'}},
            ]))
            with patch('manager_parts.quota.subprocess.Popen', return_value=process) as spawn:
                result = read_official_quota(manager, 'chosen')
            self.assertEqual(result['limits']['rateLimits']['primary']['usedPercent'], 25)
            self.assertIsNone(result['usage'])
            self.assertNotIn('secret', result['errors']['usage'])
            self.assertEqual(spawn.call_args.kwargs['env'], {})
            self.assertEqual(list(Path(root).iterdir()), [])
            manager._terminate_process.assert_called_once_with(process)

    def test_custom_account_rejected(self):
        manager = Mock()
        manager._load_store.return_value = {'accounts': {'custom': { 'api_key': 'fake'}}}
        manager._account_type.return_value = 'custom'
        with self.assertRaises(ValueError):
            read_official_quota(manager, 'custom')
