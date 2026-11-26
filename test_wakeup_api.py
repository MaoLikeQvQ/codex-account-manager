"""Exercise the real HTTP boundary using an isolated wakeup service."""
import importlib
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from codex_manager import CodexManager, Paths
from pathlib import Path
from manager_parts.wakeup import WakeupService


class WakeupApiTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        root = Path(self.home.name)
        with patch.dict(os.environ, {'CODEX_HOME': str(root / 'codex'), 'MAOLIKE_CODEX_HOME': str(root / 'manager')}):
            self.app = importlib.import_module('app')
        self.manager = CodexManager(Paths(root / 'isolated-codex', root / 'isolated-manager'))
        self.service = WakeupService(self.manager, threading.Lock())
        self.override = patch.object(self.app, 'WAKEUP', self.service)
        self.override.start()
        self.addCleanup(self.override.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/accounts/wakeup'

    def close(self):
        self.service.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, suffix='', body=None):
        request = Request(self.url + suffix, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_settings_roundtrip_and_input_failure(self):
        self.assertFalse(self.request()[1]['result']['enabled'])
        body = {'enabled': True, 'times': ['18:00', '08:00'], 'model': 'test-model'}
        self.assertEqual(self.request('/configure', body)[0], 200)
        self.assertEqual(self.request()[1]['result']['times'], ['08:00', '18:00'])
        self.assertEqual(self.request('/configure', {**body, 'times': ['29:00']})[0], 400)
        self.assertEqual(self.request()[1]['result']['times'], ['08:00', '18:00'])

    def test_explicit_run_reports_busy_without_second_run(self):
        self.service.configure({'enabled': False, 'times': [], 'model': 'test-model'})
        self.service.run_lock.acquire()
        try:
            code, payload = self.request('/run', {})
            self.assertEqual(code, 400)
            self.assertIn('正在进行', payload['error'])
        finally:
            self.service.run_lock.release()
        with patch.object(self.service, '_start') as start:
            self.assertEqual(self.request('/run', {})[0], 200)
            start.assert_called_once_with('test-model')


if __name__ == '__main__':
    unittest.main()
