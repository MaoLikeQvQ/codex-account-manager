"""Serve production UI with real CSP, isolated homes, and no live API access."""
import os
from pathlib import Path
import sys
import tempfile
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

with tempfile.TemporaryDirectory(prefix="maox-ui-test-") as directory:
    os.environ["CODEX_HOME"] = directory + "/codex"
    os.environ["MAOLIKE_CODEX_HOME"] = directory + "/manager"
    import app

    class StaticTestHandler(app.Handler):
        def do_GET(self):
            if self.path.startswith("/api/"):
                self._send_json(501, {"ok": False, "error": "Test must stub API"})
            else:
                super().do_GET()

        def do_POST(self):
            self._send_json(501, {"ok": False, "error": "Live mutations disabled in UI tests"})

    ThreadingHTTPServer(("127.0.0.1", 8798), StaticTestHandler).serve_forever()
