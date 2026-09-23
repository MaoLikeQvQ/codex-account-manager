import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_install


class InstallTests(unittest.TestCase):
    def test_source_mode_rejected(self):
        with patch.object(update_install.sys, 'frozen', False, create=True):
            with self.assertRaises(ValueError):
                update_install.installed_bundle()

    def test_helper_replaces_and_rolls_back_on_open_failure(self):
        for success in [True, False]:
            with self.subTest(success=success), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                current = root / 'App with spaces.app'
                work = root / 'work'
                work.mkdir()
                staged = work / 'new.app'
                current.mkdir()
                staged.mkdir()
                (current / 'version').write_text('old')
                (staged / 'version').write_text('new')
                script = root / 'helper.sh'
                script.write_text(update_install.INSTALL_SCRIPT.replace('/usr/bin/open', '/usr/bin/true' if success else '/usr/bin/false'))
                result = subprocess.run(['/bin/bash', str(script), '99999999', str(current), str(staged), str(work / 'previous.app'), str(work)], capture_output=True)
                self.assertEqual((current / 'version').read_text(), 'new' if success else 'old')
                self.assertEqual(result.returncode == 0, success)
