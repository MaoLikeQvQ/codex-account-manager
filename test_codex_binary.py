import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_manager import CodexManager, Paths


class CodexBinaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / "ChatGPT.app"
        app_patch = patch("manager_parts.official.CODEX_APP", self.app)
        app_patch.start()
        self.addCleanup(app_patch.stop)
        path_patch = patch("manager_parts.official.shutil.which", return_value=None)
        self.which = path_patch.start()
        self.addCleanup(path_patch.stop)

    def binary(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
        return path

    def test_current_bundle_works_without_path_and_supplies_catalog(self):
        binary = self.binary(
            "ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
        )
        self.assertEqual(CodexManager._codex_binary(), str(binary))
        manager = CodexManager(Paths(self.root / "home", self.root / "manager"))
        result = subprocess.CompletedProcess([], 0, '{"models": [{"slug": "test"}]}')
        with patch("codex_manager.subprocess.run", return_value=result) as run:
            self.assertEqual(manager._bundled_catalog(), [{"slug": "test"}])
        self.assertEqual(run.call_args.args[0][0], str(binary))

    def test_legacy_bundles_work_without_path(self):
        for app in ("ChatGPT.app", "Codex.app"):
            with self.subTest(app=app):
                binary = self.binary(f"{app}/Contents/Resources/codex")
                self.assertEqual(CodexManager._codex_binary(), str(binary))
                binary.unlink()

    def test_path_fallback_skips_nonexecutable_bundle(self):
        bundled = self.binary("ChatGPT.app/Contents/Resources/codex")
        bundled.chmod(0o644)
        binary = self.binary("bin/codex")
        self.which.return_value = str(binary)
        self.assertEqual(CodexManager._codex_binary(), str(binary))

    def test_missing_cli_reports_error(self):
        with self.assertRaisesRegex(RuntimeError, "未找到 Codex CLI"):
            CodexManager._codex_binary()
