"""Exercise startup with real loopback sockets and isolated application state."""
import errno
import importlib
import io
import os
import socket
import tempfile
import unittest
from contextlib import redirect_stdout
from urllib.parse import urlparse
from urllib.request import urlopen
from unittest.mock import Mock, patch


class AppStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {
            "CODEX_HOME": cls.directory.name + "/codex",
            "MAOLIKE_CODEX_HOME": cls.directory.name + "/manager",
        }):
            cls.app = importlib.import_module("app")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_startup(self, arguments):
        manager = Mock()
        manager._read_text.return_value = ""
        wakeup = Mock()
        opened = []
        output = io.StringIO()

        def visit_window(url):
            # The launched address must serve this application's production UI.
            with urlopen(url, timeout=2) as response:
                self.assertIn(b'id="root"', response.read())
            opened.append(url)
            self.assertEqual(manager._timing_endpoint, url + "api/timing/otlp")

        with patch.object(self.app, "MANAGER", manager), \
                patch.object(self.app, "WAKEUP", wakeup), \
                patch.object(self.app, "_launch_window", side_effect=visit_window), \
                patch.object(self.app.sys, "argv", ["app.py", *arguments]), \
                redirect_stdout(output):
            self.app.main()
        self.assertEqual(len(opened), 1)
        wakeup.start.assert_called_once_with()
        wakeup.stop.assert_called_once_with()
        self.assertIn(opened[0], output.getvalue())
        return opened[0]

    def test_system_assigned_port_opens_actual_server_address(self):
        url = self.run_startup(["--port", "0"])
        self.assertGreater(urlparse(url).port, 0)

    def test_busy_default_port_selects_another_loopback_port(self):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            occupied = blocker.getsockname()[1]
            with patch.object(self.app, "DEFAULT_PORT", occupied):
                url = self.run_startup([])
            self.assertEqual(urlparse(url).hostname, "127.0.0.1")
            self.assertNotEqual(urlparse(url).port, occupied)

    def test_explicit_busy_port_does_not_silently_choose_another(self):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            occupied = blocker.getsockname()[1]
            with patch.object(self.app, "MANAGER", Mock()), \
                    patch.object(self.app, "_launch_window") as window, \
                    patch.object(self.app.sys, "argv", ["app.py", "--port", str(occupied)]):
                with self.assertRaises(OSError):
                    self.app.main()
            window.assert_not_called()

    def test_available_default_port_is_used(self):
        server = self.app._create_server(0)
        free_port = server.server_port
        server.server_close()
        with patch.object(self.app, "DEFAULT_PORT", free_port):
            url = self.run_startup([])
        self.assertEqual(urlparse(url).port, free_port)

    def test_unrelated_bind_error_is_not_hidden_by_fallback(self):
        denied = OSError(errno.EACCES, "Permission denied")
        with patch.object(self.app, "ThreadingHTTPServer", side_effect=denied) as create:
            with self.assertRaises(OSError) as caught:
                self.app._create_server(None)
        self.assertIs(caught.exception, denied)
        create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
