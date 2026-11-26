"""Exercise real urllib and SSE parsing against a local HTTP server only."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from manager_parts.wakeup_http import send_greeting


class WakeupHttpTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.code = 200
        self.body = b'data: {"type":"response.completed","response":{"status":"completed"}}\n\n'
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                case.requests.append((self.headers, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(case.code)
                if case.code == 302:
                    self.send_header('Location', '/redirected')
                self.end_headers()
                self.wfile.write(case.body)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        override = patch('manager_parts.wakeup_http.RESPONSES_URL',
                         f'http://127.0.0.1:{self.server.server_port}/responses')
        override.start()
        self.addCleanup(override.stop)
        self.tokens = {'access_token': 'private-access', 'account_id': 'target-account'}
        self.stop = threading.Event()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def send(self):
        send_greeting(self.tokens, 'test-model', self.stop)

    def test_missing_content_type_sse_completes_and_posts_target_auth(self):
        self.send()
        headers, body = self.requests[0]
        self.assertEqual(headers['Authorization'], 'Bearer private-access')
        self.assertEqual(headers['ChatGPT-Account-ID'], 'target-account')
        self.assertEqual(body['model'], 'test-model')
        self.assertEqual(body['input'][0]['content'][0]['text'], 'hi')
        self.assertFalse(body['store'])
        self.assertTrue(body['stream'])

    def test_http_success_requires_completed_event(self):
        for body in [b'', b'data: [DONE]\n\n', b'data: {"type":"response.created"}\n\n',
                     b'data: {"type":"response.failed","error":"private-access"}\n\n',
                     b'data: {"type":"response.completed","response":{"status":"incomplete"}}\n\n',
                     b'data: invalid\n\n']:
            with self.subTest(body=body):
                self.body = body
                with self.assertRaises(RuntimeError) as result:
                    self.send()
                self.assertNotIn('private-access', str(result.exception))

    def test_http_errors_and_redirect_do_not_retry_or_leak_body(self):
        for code in [401, 403, 429, 500, 302]:
            with self.subTest(code=code):
                self.code, self.body = code, b'private-access'
                before = len(self.requests)
                with self.assertRaisesRegex(RuntimeError, str(code)) as result:
                    self.send()
                self.assertNotIn('private-access', str(result.exception))
                self.assertEqual(len(self.requests), before + 1)

    def test_stopped_task_never_sends(self):
        self.stop.set()
        with self.assertRaisesRegex(RuntimeError, '退出'):
            self.send()
        self.assertEqual(self.requests, [])

    def test_timeout_is_reported_without_raw_exception(self):
        with patch('manager_parts.wakeup_http.urllib.request.OpenerDirector.open',
                   side_effect=TimeoutError('private-access')):
            with self.assertRaisesRegex(RuntimeError, '发送超时'):
                self.send()
