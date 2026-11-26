from test_support import *


class ResponseHandler(BaseHTTPRequestHandler):
    status = 200
    payload = None
    requests = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.requests.append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length))))
        body = json.dumps(self.payload).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ConnectionValidationTests(AccountManagerTestBase):
    def setUp(self):
        super().setUp()
        self.server.RequestHandlerClass = ResponseHandler
        ResponseHandler.status = 200
        ResponseHandler.requests = []
        ResponseHandler.payload = {"status": "completed", "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": "Hello!"}]},
        ]}
        self.payload = {"name": "Test", "base_url": self.base_url, "api_key": "test-key", "default_model": "vendor-model"}

    def test_hi_response_is_verified_without_saving_or_switching(self):
        result = self.manager.verify_connection(self.payload)
        self.assertEqual(result["reply"], "Hello!")
        self.assertEqual(result["model"], "vendor-model")
        self.assertEqual(ResponseHandler.requests, [("/v1/responses", "Bearer test-key", {
            "model": "vendor-model", "input": "hi", "stream": False, "store": False,
        })])
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.auth.exists())
        self.assertFalse(self.paths.accounts.exists())

    def test_edit_uses_saved_key_and_does_not_change_files(self):
        self.save_account("Test", api_key="saved-key")
        before = self.paths.accounts.read_bytes()
        self.manager.verify_connection({**self.payload, "original_name": "Test", "api_key": ""})
        self.assertEqual(ResponseHandler.requests[0][1], "Bearer saved-key")
        self.assertEqual(self.paths.accounts.read_bytes(), before)

    def test_http_error_is_not_retried_or_exposed(self):
        ResponseHandler.status = 401
        ResponseHandler.payload = {"error": "test-key"}
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as error:
            self.manager.verify_connection(self.payload)
        self.assertNotIn("test-key", str(error.exception))
        self.assertEqual(len(ResponseHandler.requests), 1)

    def test_empty_failed_and_incomplete_responses_do_not_pass(self):
        for payload in ({"status": "completed", "output": []}, {"status": "failed"},
                        {"status": "incomplete"}, {"error": "failed"}, []):
            with self.subTest(payload=payload):
                ResponseHandler.payload = payload
                with self.assertRaises(RuntimeError):
                    self.manager.verify_connection(self.payload)

    def test_model_is_required_before_request(self):
        with self.assertRaisesRegex(ValueError, "验证连接的模型"):
            self.manager.verify_connection({**self.payload, "default_model": ""})
        self.assertEqual(ResponseHandler.requests, [])

    def test_environment_headers_and_query_are_used(self):
        provider = {"base_url": self.base_url, "wire_api": "responses", "env_key": "VALIDATION_TEST_KEY",
                    "query_params": {"access": "query-key"}}
        with patch.dict(os.environ, {"VALIDATION_TEST_KEY": "env-key"}):
            result = self.manager.verify_connection({**self.payload, "provider_config": provider})
        self.assertEqual(ResponseHandler.requests[0][:2], ("/v1/responses?access=query-key", "Bearer env-key"))
        self.assertNotIn("query-key", json.dumps(result))
