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
    CODEX_MODEL_FILTER_MARKER,
    CODEX_SPARKLE_RELATIVE_PATH,
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
        self.signature_compatibility = patch.object(
            self.manager,
            "_codex_update_signatures_are_compatible",
            return_value=True,
        )
        self.signature_compatibility_mock = self.signature_compatibility.start()
        self.addCleanup(self.signature_compatibility.stop)
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

    def make_fake_codex_app(
        self,
        model_filter: bytes | None = None,
        codex_binary: bytes | None = None,
    ) -> Path:
        app = Path(self.temporary.name) / "ChatGPT.app"
        resources = app / "Contents/Resources"
        macos = app / "Contents/MacOS"
        signature = app / "Contents/_CodeSignature"
        resources.mkdir(parents=True)
        macos.mkdir(parents=True)
        signature.mkdir(parents=True)
        filter_code = model_filter or (
            b"function allowed({additionalAvailableModels:e,authMethod:t,"
            b"availableModels:n,isCustomModelProvider:r,model:i,useHiddenModels:a})"
            b"{return e?.has(i.model)===!0||i.model!==`codex-auto-review`&&"
            b"(a&&!r&&t!==`amazonBedrock`?n.has(i.model):!i.hidden)};"
            b"function announcement(e,t,n,r){return "
            b"{announcementContent:n,showAnnouncement:e&&!t,dismissAnnouncement:r}};"
            b"const gates=[{gateName:`9999999999`,featureKey:`unrelated_feature`},"
            b"{gateName:`9999999999`,featureKey:`unrelated_feature`}]"
        )
        (resources / "app.asar").write_bytes(filter_code)
        (resources / "codex").write_bytes(
            b"original codex binary" if codex_binary is None else codex_binary
        )
        info = {
            "CFBundleShortVersionString": "test-version",
            "ElectronAsarIntegrity": {
                "Resources/app.asar": {"algorithm": "SHA256", "hash": "old"}
            },
        }
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
        (macos / "ChatGPT").write_bytes(b"original executable")
        (signature / "CodeResources").write_bytes(b"original code resources")
        sparkle = app / CODEX_SPARKLE_RELATIVE_PATH
        for relative in (
            "Versions/B/XPCServices/Installer.xpc/Contents/MacOS",
            "Versions/B/XPCServices/Downloader.xpc/Contents/MacOS",
            "Versions/B/Updater.app/Contents/MacOS",
        ):
            (sparkle / relative).mkdir(parents=True)
        (sparkle / "Versions/B/Autoupdate").write_bytes(b"original autoupdate")
        (sparkle / "Versions/B/Sparkle").write_bytes(b"original sparkle")
        return app
