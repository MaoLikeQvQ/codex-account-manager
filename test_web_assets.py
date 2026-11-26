"""Exercise the real HTTP boundary with an isolated static directory."""
import importlib
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import Mock, patch


class WebAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {
            'CODEX_HOME': cls.home.name + '/codex',
            'MAOLIKE_CODEX_HOME': cls.home.name + '/manager',
        }):
            cls.app = importlib.import_module('app')

    @classmethod
    def tearDownClass(cls):
        cls.home.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / 'web'
        (self.root / 'assets').mkdir(parents=True)
        (self.root / 'index.html').write_text('<html><head></head><body><div id="root"></div></body></html>')
        (self.root / 'assets' / 'app-abcd.js').write_text('export const ready = true;')
        (self.root / 'assets' / 'app-abcd.css').write_text('body { margin: 0; }')
        (self.root / 'assets' / 'font.woff2').write_bytes(b'font-data')
        (self.root / 'private.txt').write_text('not a public asset')
        self.web_patch = patch.object(self.app, 'WEB_ROOT', self.root)
        self.web_patch.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.web_patch.stop()
        self.directory.cleanup()

    def get(self, path):
        with urlopen(self.url + path) as response:
            return response.headers, response.read()

    def assert_missing(self, path):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.url + path)
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_window_keeps_local_theme_preferences_between_launches(self):
        webview = Mock()
        with patch.dict('sys.modules', {'webview': webview}), patch('native_window.enable_first_mouse') as first_mouse:
            self.app._launch_window('http://127.0.0.1:8798/')
        first_mouse.assert_called_once_with()
        webview.start.assert_called_once_with(
            private_mode=False,
            storage_path=str(self.app.MANAGER.paths.app_home / 'webview'),
        )

    def test_bundled_javascript_css_and_font_have_correct_types(self):
        for path, content_type, content in [
            ('/assets/app-abcd.js?v=1', 'text/javascript', b'export const ready = true;'),
            ('/assets/app-abcd.css', 'text/css', b'body { margin: 0; }'),
            ('/assets/font.woff2', 'font/woff2', b'font-data'),
        ]:
            with self.subTest(path=path):
                headers, body = self.get(path)
                self.assertEqual(headers.get_content_type(), content_type)
                self.assertEqual(body, content)
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_index_injects_unique_matching_style_nonce_and_mode(self):
        with patch.object(self.app.sys, 'frozen', False, create=True):
            headers, first = self.get('/')
            _, second = self.get('/index.html')
        nonce = re.search(rb'<meta name="csp-nonce" content="([^"]+)">', first)
        self.assertIsNotNone(nonce)
        value = nonce.group(1).decode()
        policy = headers['Content-Security-Policy']
        self.assertIn(f"style-src-elem 'self' 'nonce-{value}'", policy)
        self.assertIn("style-src-attr 'unsafe-inline'", policy)
        self.assertIn("script-src 'self';", policy)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", policy)
        self.assertIn(b'data-updates-enabled="false"', first)
        self.assertNotIn(nonce.group(0), second)
        self.assertEqual(int(headers['Content-Length']), len(first))

    def test_missing_traversal_and_private_paths_are_not_served(self):
        for path in ['/assets/missing.js', '/assets/', '/private.txt',
                     '/assets/../private.txt', '/assets/%2e%2e/private.txt',
                     '/assets/%2e%2e%2fprivate.txt', '/assets/%00.js']:
            with self.subTest(path=path):
                self.assert_missing(path)

    def test_asset_symlink_cannot_escape_public_directory(self):
        (self.root / 'assets' / 'leak.js').symlink_to(self.root / 'private.txt')
        self.assert_missing('/assets/leak.js')


if __name__ == '__main__':
    unittest.main()
