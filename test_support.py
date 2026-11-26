from __future__ import annotations

import hashlib
import json
import plistlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import tomllib
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from codex_manager import (
    CodexManager,
    Paths,
)

class ModelHandler(BaseHTTPRequestHandler):
    models = ["gpt-5.6-sol", "vendor-coder"]
    authorization = ""
    response_shape = "data"
    successful_path = None
    request_paths = []

    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        type(self).request_paths.append(self.path)
        type(self).authorization = self.headers.get("Authorization", "")
        if type(self).successful_path and self.path != type(self).successful_path:
            self.send_response(404)
            self.end_headers()
            return
        payload = (
            {"models": [{"slug": model} for model in type(self).models]}
            if type(self).response_shape == "models_slug"
            else {"data": [{"id": model} for model in type(self).models]}
        )
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ImageSseHandler(BaseHTTPRequestHandler):
    authorization = ""
    account_id = ""
    request_body = {}
    image_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        "/x8AAusB9WlA7x8AAAAASUVORK5CYII="
    )

    def log_message(self, _format, *_args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        type(self).authorization = self.headers.get("Authorization", "")
        type(self).account_id = self.headers.get("ChatGPT-Account-ID", "")
        type(self).request_body = json.loads(self.rfile.read(length))
        event = {
            "type": "response.output_item.done",
            "item": {
                "type": "image_generation_call",
                "status": "completed",
                "result": type(self).image_base64,
            },
        }
        body = f"event: response.output_item.done\ndata: {json.dumps(event)}\n\ndata: [DONE]\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AccountManagerTestBase(unittest.TestCase):
    def setUp(self):
        ModelHandler.models = ["gpt-5.6-sol", "vendor-coder"]
        ModelHandler.authorization = ""
        ModelHandler.response_shape = "data"
        ModelHandler.successful_path = None
        ModelHandler.request_paths = []
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = Paths(root / "codex", root / "manager")
        self.manager = CodexManager(self.paths)
        catalog = patch.object(self.manager, "_bundled_catalog", return_value=[
            {"slug": "gpt-5.6-sol", "visibility": "list", "priority": 1},
        ])
        catalog.start()
        self.addCleanup(catalog.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def save_account(self, name="MaoLocal", provider="MaoLocal", **overrides):
        payload = {
            "name": name,
            "provider_id": provider,
            "provider_name": name,
            "base_url": self.base_url,
            "wire_api": "responses",
            "api_key": "secret-key",
            "default_model": "gpt-5.6-sol",
            "reasoning_effort": "high",
        }
        payload.update(overrides)
        return self.manager.save_account(payload)
