from test_support import *


class ImageMigrationTests(AccountManagerTestBase):
    def install_legacy_image_plugin(self):
        self.manager.configure_image_generation({
            "source": "separate",
            "base_url": "https://images.example/v1",
            "api_key": "image-secret",
        })
        self.manager.apply_image_generation()
        self.paths.config.write_text(self.paths.config.read_text().replace(
            "[mcp_servers.custom-imagegen]", "[mcp_servers.maolocal-imagegen]"
        ))
        legacy_skill = self.paths.codex_home / "skills" / "maolocal-imagegen" / "SKILL.md"
        legacy_skill.parent.mkdir(parents=True)
        self.paths.image_skill.rename(legacy_skill)
        return legacy_skill

    def test_apply_migrates_legacy_service_and_skill_without_changing_credentials(self):
        legacy_skill = self.install_legacy_image_plugin()
        legacy_skill.write_text("previous skill contents\n")
        extra_file = legacy_skill.parent / "user-notes.md"
        extra_file.write_text("keep me")
        self.paths.config.write_text(self.paths.config.read_text() + (
            '\n[mcp_servers.other]\ncommand = "other-server"\n'
            '[features]\ngoals = true\n'
        ))
        credentials = self.paths.image_config.read_bytes()

        state = self.manager._image_generation_state(self.manager._read_toml(self.paths.config))
        self.assertTrue(state["installed"])
        self.assertTrue(state["enabled"])
        self.assertTrue(state["pending_apply"])
        result = self.manager.apply_image_generation()

        self.assertTrue(result["installed"])
        self.assertFalse(result["pending_apply"])
        config = tomllib.loads(self.paths.config.read_text())
        self.assertNotIn("maolocal-imagegen", config["mcp_servers"])
        self.assertIn("custom-imagegen", config["mcp_servers"])
        self.assertEqual(config["mcp_servers"]["other"]["command"], "other-server")
        self.assertTrue(config["features"]["goals"])
        self.assertEqual(self.paths.image_config.read_bytes(), credentials)
        self.assertTrue(self.paths.image_skill.is_file())
        self.assertFalse(legacy_skill.exists())
        self.assertEqual(extra_file.read_text(), "keep me")
        backups = list(self.paths.backups.glob("SKILL.md.*.bak"))
        self.assertTrue(any(item.read_text() == "previous skill contents\n" for item in backups))

    def test_disable_removes_new_and_legacy_services_and_nested_environment(self):
        self.install_legacy_image_plugin()
        self.paths.config.write_text(
            '[mcp_servers."maolocal-imagegen"]\ncommand = "node"\n'
            '[mcp_servers."maolocal-imagegen".env]\nOLD = "old"\n'
            '[mcp_servers.custom-imagegen]\ncommand = "node"\n'
            '[mcp_servers.custom-imagegen.env]\nNEW = "new"\n'
            '[mcp_servers.other]\ncommand = "keep"\n'
        )
        self.manager.configure_image_generation({"enabled": False})
        result = self.manager.apply_image_generation()

        self.assertFalse(result["enabled"])
        self.assertFalse(result["installed"])
        self.assertFalse(result["pending_apply"])
        self.assertEqual(result["plugin_action"], "disabled")
        self.assertEqual(tomllib.loads(self.paths.config.read_text())["mcp_servers"], {
            "other": {"command": "keep"},
        })

    def test_apply_removes_nested_legacy_service_without_leaving_duplicate(self):
        legacy_skill = self.install_legacy_image_plugin()
        self.paths.config.write_text(
            '[mcp_servers.maolocal-imagegen]\ncommand = "node"\n'
            '[mcp_servers.maolocal-imagegen.env]\nOLD = "old"\n'
            '[mcp_servers.other]\ncommand = "keep"\n'
        )
        result = self.manager.apply_image_generation()
        self.assertFalse(result["pending_apply"])
        self.assertFalse(legacy_skill.parent.exists())
        config = tomllib.loads(self.paths.config.read_text())
        self.assertEqual(set(config["mcp_servers"]), {"custom-imagegen", "other"})
        self.assertEqual(config["mcp_servers"]["custom-imagegen"]["env"], {
            "CUSTOM_IMAGEGEN_CONFIG": str(self.paths.image_config),
        })

    def test_failed_install_keeps_legacy_skill_and_config(self):
        legacy_skill = self.install_legacy_image_plugin()
        previous_config = self.paths.config.read_text()
        previous_skill = legacy_skill.read_text()
        original_write = self.manager._atomic_write

        def fail_skill_write(path, content):
            if path == self.paths.image_skill:
                raise OSError("simulated skill installation failure")
            return original_write(path, content)

        with patch.object(self.manager, "_atomic_write", side_effect=fail_skill_write):
            with self.assertRaisesRegex(OSError, "simulated skill"):
                self.manager.apply_image_generation()

        self.assertEqual(self.paths.config.read_text(), previous_config)
        self.assertEqual(legacy_skill.read_text(), previous_skill)
        self.assertFalse(self.paths.image_skill.exists())
