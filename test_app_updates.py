import importlib
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch


class AppUpdateModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {'CODEX_HOME': cls.temporary.name + '/codex',
                                    'MAOLIKE_CODEX_HOME': cls.temporary.name + '/manager'}):
            cls.app = importlib.import_module('app')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_source_mode_skips_check_and_download(self):
        with patch.object(self.app.sys, 'frozen', False, create=True), \
                patch.object(self.app, 'check_update') as check, \
                patch.object(self.app, 'download_update') as download:
            with urlopen(self.url + '/') as response:
                self.assertIn(b'data-updates-enabled="false"', response.read())
            with urlopen(self.url + '/api/updates') as response:
                result = json.load(response)['result']
            self.assertFalse(result['enabled'])
            self.assertFalse(result['available'])
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.url + '/api/updates/download', data=b'{}', method='POST'))
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
            check.assert_not_called()
            download.assert_not_called()

    def test_packaged_mode_keeps_update_paths(self):
        manifest = {'available': True, 'version': '99.0.0'}
        with patch.object(self.app.sys, 'frozen', True, create=True), \
                patch.object(self.app, 'check_update', return_value=manifest) as check, \
                patch.object(self.app, 'download_update', return_value={'message': 'mock download'}) as download:
            with urlopen(self.url + '/') as response:
                self.assertIn(b'data-updates-enabled="true"', response.read())
            with urlopen(self.url + '/api/updates') as response:
                self.assertEqual(json.load(response)['result'], manifest)
            with urlopen(Request(self.url + '/api/updates/download', data=b'{}', method='POST')) as response:
                self.assertEqual(json.load(response)['result']['message'], 'mock download')
            check.assert_called_once()
            download.assert_called_once()


if __name__ == '__main__':
    unittest.main()
