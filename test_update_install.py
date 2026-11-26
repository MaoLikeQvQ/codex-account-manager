import json
import shlex
import subprocess
import sys
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
            for restart_args in [[], ['--env', 'CODEX_HOME=/isolated/home with spaces', '--args', '--port', '8793', '']]:
                with self.subTest(success=success, restart_args=restart_args), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    current = root / 'App with spaces.app'
                    work = root / 'work'
                    work.mkdir()
                    staged = work / 'new.app'
                    current.mkdir()
                    staged.mkdir()
                    (current / 'version').write_text('old')
                    (staged / 'version').write_text('new')
                    calls = root / 'launches.jsonl'
                    opener = root / 'open stub.py'
                    opener.write_text(
                        'import json, sys\nfrom pathlib import Path\n'
                        f'with Path({str(calls)!r}).open("a") as stream:\n'
                        '    stream.write(json.dumps({"args": sys.argv[1:], '
                        '"version": (Path(sys.argv[1]) / "version").read_text()}) + "\\n")\n'
                        f'sys.exit({0 if success else 1})\n'
                    )
                    script = root / 'helper.sh'
                    script.write_text(update_install.INSTALL_SCRIPT.replace('/usr/bin/open', shlex.join([sys.executable, str(opener)])))
                    result = subprocess.run(['/bin/bash', str(script), '99999999', str(current), str(staged), str(work / 'previous.app'), str(work), *restart_args], capture_output=True, text=True)
                    self.assertEqual((current / 'version').read_text(), 'new' if success else 'old', result.stderr)
                    self.assertEqual(result.returncode == 0, success, result.stderr)
                    launches = [json.loads(line) for line in calls.read_text().splitlines()]
                    expected = [{'args': [str(current), *restart_args], 'version': 'new'}]
                    if not success:
                        expected.append({'args': [str(current), *restart_args], 'version': 'old'})
                    self.assertEqual(launches, expected)
                    self.assertEqual(work.exists(), not success)
