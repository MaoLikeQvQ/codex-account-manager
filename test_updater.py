import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import updater


class UpdateTests(unittest.TestCase):
    def manifest(self, content=b'installer'):
        return dict(version='2.11.9', architecture='arm64',
                    url=f'{updater.BASE}/download/v2.11.9/test.dmg',
                    sha256=hashlib.sha256(content).hexdigest(), size=len(content), available=True)

    def test_numeric_versions(self):
        self.assertGreater(updater.version_tuple('2.11.10'), updater.version_tuple('2.11.9'))
        for value in ['2.11', '2.11.1-beta', None]:
            with self.assertRaises(ValueError):
                updater.version_tuple(value)

    def test_manifest_rejects_untrusted_or_invalid_values(self):
        self.assertEqual(updater.validate_manifest(self.manifest())['version'], '2.11.9')
        for field, value in [('url', 'https://evil.example/test.dmg'), ('size', True), ('size', updater.MAX_SIZE+1), ('sha256', 'bad'), ('architecture', 'x86_64')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                updater.validate_manifest({**self.manifest(), field: value})

    def test_download_opens_only_verified_file(self):
        for content, valid in [(b'installer', True), (b'corrupted', False)]:
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / 'download'
                target.mkdir()
                with patch.object(updater, 'INSTALL_PENDING', False), patch.object(updater, 'check_update', return_value=self.manifest()), patch.object(updater.tempfile, 'mkdtemp', return_value=str(target)), patch.object(updater, 'urlopen', return_value=io.BytesIO(content)), patch.object(updater, 'installed_bundle', return_value=Path('/Applications/Test.app')), patch.object(updater, 'prepare_install') as opened, patch.object(updater.threading, 'Timer'):
                    if valid:
                        updater.download_update()
                        opened.assert_called_once()
                    else:
                        with self.assertRaises(ValueError):
                            updater.download_update()
                        opened.assert_not_called()
                        self.assertFalse(target.exists())
