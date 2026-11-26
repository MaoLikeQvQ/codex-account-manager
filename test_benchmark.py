from unittest.mock import patch

from test_support import AccountManagerTestBase, BaseHTTPRequestHandler, json
from manager_parts.benchmark import run_pelican_test, PROMPT
from manager_parts.benchmark_svg import safe_svg_preview

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><circle cx="50" cy="70" r="20"/><path d="M50 70L100 30L150 70Z"/></svg>'


def completed(reply=SVG):
    return {'status': 'completed', 'model': 'reported-model', 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'message', 'content': [{'type': 'output_text', 'text': reply}]},
    ]}


class BenchmarkHandler(BaseHTTPRequestHandler):
    body = b''
    content_type = 'application/json'
    status = 200
    requests = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append((self.path, dict(self.headers), body))
        self.send_response(self.status)
        self.send_header('Content-Type', self.content_type)
        self.send_header('Content-Length', str(len(self.body)))
        if self.status == 302:
            self.send_header('Location', self.server.redirect_url)
        self.end_headers()
        self.wfile.write(self.body)


class BenchmarkTests(AccountManagerTestBase):
    def setUp(self):
        super().setUp()
        self.server.RequestHandlerClass = BenchmarkHandler
        BenchmarkHandler.requests = []
        BenchmarkHandler.status = 200
        BenchmarkHandler.content_type = 'application/json'
        BenchmarkHandler.body = json.dumps(completed()).encode()
        self.save_account('Current', api_key='test-key', default_model='saved-default', reasoning_effort='high')
        self.paths.config.write_text('model = "saved-default"\n')
        with patch.object(self.manager, 'codex_running', return_value=False):
            self.manager.activate_account('Current')
        self.expected = {'account': 'Current', 'model': 'saved-default'}

    def run_test(self):
        return run_pelican_test(self.manager, self.expected)

    def test_current_default_model_is_used_once_without_config_or_account_changes(self):
        paths = [self.paths.config, self.paths.auth, self.paths.accounts]
        before = [path.read_bytes() for path in paths]
        result = self.run_test()
        self.assertEqual(result['model'], 'saved-default')
        self.assertEqual(result['reported_model'], 'reported-model')
        self.assertEqual(result['reply'], SVG)
        self.assertIn('<circle', result['preview_svg'])
        self.assertEqual(result['warning'], '')
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertEqual(len(BenchmarkHandler.requests), 1)
        endpoint, headers, body = BenchmarkHandler.requests[0]
        self.assertEqual(endpoint, '/v1/responses')
        self.assertEqual(headers['Authorization'], 'Bearer test-key')
        self.assertEqual(body['model'], 'saved-default')
        self.assertEqual(body['reasoning'], {'effort': 'high'})
        self.assertEqual(body['input'][0]['content'][0]['text'], PROMPT)
        self.assertTrue(body['stream'])
        self.assertFalse(body['store'])
        self.assertNotIn('test-key', json.dumps(result))

    def test_stream_completion_and_multiline_data_are_supported(self):
        BenchmarkHandler.content_type = 'text/event-stream'
        event = json.dumps({'type': 'response.completed', 'response': completed()}, indent=2)
        BenchmarkHandler.body = (': keepalive\n\n' + '\n'.join('data: ' + line for line in event.splitlines()) + '\n\n').encode()
        self.assertEqual(self.run_test()['reply'], SVG)
        self.assertEqual(len(BenchmarkHandler.requests), 1)

    def test_request_uses_configured_model_instead_of_account_profile(self):
        config = self.paths.config.read_text().replace('model = "saved-default"', 'model = "current-model"')
        self.paths.config.write_text(config)
        try:
            result = run_pelican_test(self.manager, {'account': 'Current', 'model': 'current-model'})
        except ValueError as error:
            self.fail(f'the configured model must be accepted: {error}')
        self.assertEqual(result['model'], 'current-model')
        self.assertEqual(BenchmarkHandler.requests[0][2]['model'], 'current-model')

    def test_changed_account_model_and_pending_changes_do_not_send_requests(self):
        with self.assertRaisesRegex(ValueError, '账号已变化'):
            run_pelican_test(self.manager, {**self.expected, 'account': 'Other'})
        with self.assertRaisesRegex(ValueError, '模型'):
            run_pelican_test(self.manager, {**self.expected, 'model': 'different'})
        self.save_account('Current', original_name='Current', default_model='edited')
        with self.assertRaisesRegex(ValueError, '待应用'):
            self.run_test()
        self.assertEqual(BenchmarkHandler.requests, [])

    def test_http_errors_and_redirects_are_not_retried_or_exposed(self):
        for status in [401, 429, 500, 302]:
            with self.subTest(status=status):
                BenchmarkHandler.requests = []
                BenchmarkHandler.status = status
                self.server.redirect_url = self.base_url + '/redirected'
                BenchmarkHandler.body = b'secret-provider-error-test-key'
                with self.assertRaisesRegex(RuntimeError, f'HTTP {status}') as caught:
                    self.run_test()
                self.assertEqual(len(BenchmarkHandler.requests), 1)
                self.assertNotIn('test-key', str(caught.exception))

    def test_incomplete_json_and_streams_do_not_claim_success(self):
        for payload in [completed(''), {'status': 'incomplete'}, {'error': 'secret'}, []]:
            with self.subTest(payload=payload):
                BenchmarkHandler.body = json.dumps(payload).encode()
                with self.assertRaises(RuntimeError):
                    self.run_test()
        BenchmarkHandler.content_type = 'text/event-stream'
        for body in [b'data: [DONE]\n\n', b'data: {"type":"response.failed"}\n\n', b'data: invalid\n\n']:
            BenchmarkHandler.body = body
            with self.assertRaises(RuntimeError):
                self.run_test()

    def test_response_size_is_bounded_and_not_retried(self):
        with patch('manager_parts.benchmark.MAX_RESPONSE_BYTES', 32):
            with self.assertRaisesRegex(RuntimeError, '响应过大'):
                self.run_test()
        self.assertEqual(len(BenchmarkHandler.requests), 1)

    def test_non_svg_output_remains_available_for_inspection(self):
        BenchmarkHandler.body = json.dumps(completed('I cannot draw this.')).encode()
        result = self.run_test()
        self.assertEqual(result['reply'], 'I cannot draw this.')
        self.assertEqual(result['preview_svg'], '')
        self.assertIn('未返回完整 SVG', result['warning'])

    def test_official_route_uses_current_refreshed_token_and_fixed_codex_endpoint(self):
        account = {'account_type': 'official', 'default_model': 'official-default', 'reasoning_effort': 'xhigh',
                   'official_auth': {'tokens': {'access_token': 'old', 'account_id': 'account-one'}}}
        store = {'active_account': 'Official', 'accounts': {'Official': account}}
        self.paths.auth.write_text(json.dumps({'tokens': {'access_token': 'refreshed', 'account_id': 'account-one'}}))
        with patch.object(self.manager, '_load_store', return_value=store), \
             patch.object(self.manager, '_read_toml', return_value={'model_provider': 'openai', 'model': 'official-default'}), \
             patch('manager_parts.benchmark.OFFICIAL_RESPONSES_URL', self.base_url + '/official'):
            result = run_pelican_test(self.manager, {'account': 'Official', 'model': 'official-default'})
        endpoint, headers, body = BenchmarkHandler.requests[0]
        self.assertEqual(endpoint, '/v1/official')
        self.assertEqual(headers['Authorization'], 'Bearer refreshed')
        self.assertEqual(headers['Chatgpt-Account-Id'], 'account-one')
        self.assertEqual(body['reasoning'], {'effort': 'xhigh'})
        self.assertNotIn('refreshed', json.dumps(result))

    def test_official_mismatched_account_is_rejected_before_request(self):
        account = {'account_type': 'official', 'default_model': 'official-default',
                   'official_auth': {'tokens': {'account_id': 'account-one'}}}
        store = {'active_account': 'Official', 'accounts': {'Official': account}}
        self.paths.auth.write_text(json.dumps({'tokens': {'access_token': 'token', 'account_id': 'different'}}))
        with patch.object(self.manager, '_load_store', return_value=store), \
             patch.object(self.manager, '_read_toml', return_value={'model_provider': 'openai', 'model': 'official-default'}):
            with self.assertRaisesRegex(ValueError, '不一致'):
                run_pelican_test(self.manager, {'account': 'Official', 'model': 'official-default'})
        self.assertEqual(BenchmarkHandler.requests, [])

    def test_preview_removes_active_content_without_altering_raw_answer(self):
        source = '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script><foreignObject/><image href="https://example.com/leak"/><use href="https://example.com/a.svg#x"/><style>@import "https://example.com";</style><circle r="4" style="fill:url(https://example.com/a)"/></svg>'
        BenchmarkHandler.body = json.dumps(completed(source)).encode()
        result = self.run_test()
        self.assertEqual(result['reply'], source)
        for unsafe in ['script', 'onload', 'foreignObject', 'image', 'https://', '@import']:
            self.assertNotIn(unsafe, result['preview_svg'])
        self.assertIn('<circle', result['preview_svg'])
        self.assertTrue(result['warning'])
        preview, warning = safe_svg_preview('```svg\n' + SVG + '\n```')
        self.assertTrue(preview)
        self.assertFalse(warning)
