import importlib
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen


class HistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {"CODEX_HOME": self.home.name + "/codex",
                                     "MAOLIKE_CODEX_HOME": self.home.name + "/manager"}):
            self.app = importlib.import_module("app")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.home.cleanup()

    def post(self, path):
        url = f"http://127.0.0.1:{self.server.server_port}{path}"
        request = Request(url, data=b'{"name":"Channel","restart":true}',
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_activate_reports_partial_history_without_misrepresenting_switch(self):
        manager = Mock()
        manager.launch_codex.return_value = "restarted"
        manager.activate_account.return_value = {"account": "Channel", "history": {"status": "partial", "failed": 1}}
        manager.state.return_value = {"history_claim": {"account": "Channel", "status": "partial", "failed": 1}}
        with patch.object(self.app, "MANAGER", manager):
            payload = self.post("/api/accounts/activate")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload.get("warning"))
        self.assertIn("1", payload["message"])
        self.assertIn("未能归纳", payload["message"])
        self.assertNotIn("工具页", payload["message"])
        self.assertIn("自动重试", payload["message"])
        manager.launch_codex.assert_called_once_with(restart=True)

    def test_activate_reports_deferred_history(self):
        manager = Mock()
        manager.launch_codex.return_value = "restarted"
        manager.activate_account.return_value = {"account": "Channel", "history": {"status": "pending"}}
        manager.state.return_value = {"history_claim": {"account": "Channel", "status": "pending"}}
        with patch.object(self.app, "MANAGER", manager):
            payload = self.post("/api/accounts/activate")
        self.assertTrue(payload["ok"])
        self.assertIn("历史", payload["message"])
        self.assertIn("重启", payload["message"])

    def test_launch_reports_when_other_clients_still_block_history(self):
        manager = Mock()
        manager.launch_codex.return_value = "restarted"
        manager.state.return_value = {"history_claim": {"account": "Channel", "status": "pending"}}
        with patch.object(self.app, "MANAGER", manager):
            payload = self.post("/api/codex/launch")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload.get("warning"))
        self.assertIn("历史", payload["message"])
        self.assertIn("未完成", payload["message"])
        self.assertNotIn("工具页", payload["message"])
        self.assertIn("自动重试", payload["message"])

    def test_manual_claim_reports_partial_failure(self):
        manager = Mock()
        manager.claim_all_conversations.return_value = {
            "account": "Channel", "changed_files": 1, "total": 1, "failed": 1,
        }
        manager.state.return_value = {}
        with patch.object(self.app, "MANAGER", manager):
            payload = self.post("/api/history/claim-all")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload.get("warning"))
        self.assertIn("未能归纳", payload["message"])
