"""Verify the real benchmark HTTP boundary without provider or credential access."""
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


class BenchmarkApiTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {'CODEX_HOME': self.home.name + '/codex',
                                     'MAOLIKE_CODEX_HOME': self.home.name + '/manager'}):
            self.app = importlib.import_module('app')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/benchmark/pelican'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.home.cleanup()

    def post(self):
        request = Request(self.url, data=b'{"account":"Current","model":"default"}',
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_explicit_post_returns_result_without_state_or_credentials(self):
        result = {'account': 'Current', 'model': 'default', 'reply': '<svg/>', 'preview_svg': '', 'elapsed_ms': 25}
        manager = Mock()
        with patch.object(self.app, 'MANAGER', manager), patch.object(self.app, 'run_pelican_test', return_value=result) as run:
            code, payload = self.post()
        self.assertEqual(code, 200)
        self.assertEqual(payload, {'ok': True, 'result': result})
        run.assert_called_once_with(manager, {'account': 'Current', 'model': 'default'})
        manager.state.assert_not_called()

    def test_running_test_is_rejected_without_second_provider_call(self):
        self.app.BENCHMARK_LOCK.acquire()
        try:
            with patch.object(self.app, 'run_pelican_test') as run:
                code, payload = self.post()
            self.assertEqual(code, 409)
            self.assertIn('已有测试', payload['error'])
            run.assert_not_called()
        finally:
            self.app.BENCHMARK_LOCK.release()

    def test_failure_is_visible_and_releases_lock(self):
        with patch.object(self.app, 'run_pelican_test', side_effect=RuntimeError('未自动重试')) as run:
            code, payload = self.post()
        self.assertEqual(code, 500)
        self.assertEqual(payload['error'], '未自动重试')
        self.assertFalse(self.app.BENCHMARK_LOCK.locked())
        self.assertEqual(run.call_count, 1)
