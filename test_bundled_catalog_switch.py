from test_support import AccountManagerTestBase, json, patch, tomllib


class BundledCatalogSwitchTests(AccountManagerTestBase):
    def setUp(self):
        super().setUp()
        self.save_account("Custom", default_model="old-account-model")
        store = json.loads(self.paths.accounts.read_text())
        store["accounts"]["Official"] = {
            "account_type": "official", "provider_id": "openai",
            "default_model": "another-account-model", "official_auth": {"tokens": {"access_token": "fake"}},
        }
        self.paths.accounts.write_text(json.dumps(store))

    def activate(self, name):
        with patch.object(self.manager, "codex_running", return_value=False), \
             patch.object(self.manager, "_validate_official_auth"), \
             patch.object(self.manager, "_bundled_catalog", side_effect=AssertionError("must not read bundled catalog")):
            return self.manager.activate_account(name)

    def test_both_account_types_keep_current_model_and_codex_native_catalog(self):
        self.paths.config.write_text('model = "current-model"\n[features]\nother = true\n')
        for name in ("Custom", "Official"):
            with self.subTest(name=name):
                self.activate(name)
                config = tomllib.loads(self.paths.config.read_text())
                self.assertEqual(config["model"], "current-model")
                self.assertNotIn("model_catalog_json", config)
                self.assertTrue(config["features"]["other"])
                self.assertFalse(self.paths.bundled_model_catalog.exists())
        accounts = json.loads(self.paths.accounts.read_text())["accounts"]
        self.assertEqual(accounts["Custom"]["default_model"], "old-account-model")
        self.assertEqual(accounts["Official"]["default_model"], "another-account-model")

    def test_both_account_types_clear_only_previous_manager_catalog_references(self):
        for catalog in (self.paths.codex_home / "models.json", self.paths.bundled_model_catalog):
            catalog.write_text('{"models":["leave this file alone"]}')
            for name in ("Custom", "Official"):
                with self.subTest(name=name, catalog=catalog):
                    self.paths.config.write_text(f'model = "current"\nmodel_catalog_json = "{catalog}"\n')
                    self.activate(name)
                    self.assertNotIn("model_catalog_json", tomllib.loads(self.paths.config.read_text()))
                    self.assertEqual(catalog.read_text(), '{"models":["leave this file alone"]}')

    def test_user_catalog_is_preserved_by_both_account_switches(self):
        for name in ("Custom", "Official"):
            with self.subTest(name=name):
                self.paths.config.write_text('model = "current"\nmodel_catalog_json = "/user/custom-models.json"\n')
                self.activate(name)
                self.assertEqual(tomllib.loads(self.paths.config.read_text())["model_catalog_json"], "/user/custom-models.json")

    def test_missing_model_is_not_replaced_by_account_profile(self):
        for name in ("Custom", "Official"):
            with self.subTest(name=name):
                self.paths.config.write_text('web_search = "disabled"\n')
                self.activate(name)
                config = tomllib.loads(self.paths.config.read_text())
                self.assertNotIn("model", config)
                self.assertNotIn("model_catalog_json", config)

    def test_optional_profile_model_can_be_saved_and_used_without_catalog_access(self):
        self.save_account("Optional", default_model="")
        self.paths.config.write_text('model = "current"\n')
        self.activate("Optional")
        self.assertEqual(tomllib.loads(self.paths.config.read_text())["model"], "current")

    def test_model_files_are_not_read_or_written_by_switch_or_launch(self):
        files = [self.paths.codex_home / "models.json", self.paths.codex_home / "models_cache.json", self.paths.bundled_model_catalog]
        for path in files:
            path.write_text('{"models":["unchanged"]}')
        before = {path: path.read_bytes() for path in files}
        self.paths.config.write_text('model = "current"\n')
        original_read = type(files[0]).read_text
        original_write = self.manager._atomic_write

        def read(path, *args, **kwargs):
            if path in files:
                raise AssertionError("model cache must not be read")
            return original_read(path, *args, **kwargs)

        def write(path, content):
            if path in files:
                raise AssertionError("model cache must not be written")
            return original_write(path, content)

        with patch.object(type(files[0]), "read_text", new=read), patch.object(self.manager, "_atomic_write", side_effect=write):
            self.activate("Custom")
            self.activate("Official")
            self.launch()
        self.assertEqual({path: path.read_bytes() for path in files}, before)

    def launch(self, running=False):
        with patch.object(self.manager, "codex_running", return_value=running), \
             patch.object(self.manager, "_bundled_catalog", side_effect=AssertionError("must not read bundled catalog")), \
             patch.object(self.manager, "_stop_codex") as stop, \
             patch("codex_manager.os.uname") as uname, patch("codex_manager.subprocess.run") as run:
            uname.return_value.sysname = "Darwin"
            result = self.manager.launch_codex(restart=running)
            self.assertEqual(stop.call_count, int(running))
            run.assert_called_once()
            return result

    def test_launch_cleans_manager_catalog_and_keeps_user_catalog(self):
        self.activate("Custom")
        for catalog in (self.paths.codex_home / "models.json", self.paths.bundled_model_catalog, "/user/custom-models.json"):
            with self.subTest(catalog=catalog):
                self.paths.config.write_text(f'model = "current"\nmodel_catalog_json = "{catalog}"\n')
                self.assertEqual(self.launch(), "opened")
                config = tomllib.loads(self.paths.config.read_text())
                self.assertEqual(config["model"], "current")
                if catalog == "/user/custom-models.json":
                    self.assertEqual(config["model_catalog_json"], catalog)
                else:
                    self.assertNotIn("model_catalog_json", config)

    def test_restart_does_not_require_a_bundled_catalog(self):
        self.activate("Custom")
        self.assertEqual(self.launch(running=True), "restarted")

    def test_startup_migrates_only_legacy_managed_overrides_to_native_discovery(self):
        for catalog in (self.paths.codex_home / "models.json", self.paths.bundled_model_catalog, "/user/custom-models.json"):
            with self.subTest(catalog=catalog):
                original = f'''model = "current"
model_provider = "MaoLocal"
model_catalog_json = "{catalog}"
[features]
api_key_model_discovery = true
other = true
[model_providers.MaoLocal]
base_url = "https://example.com/v1"
model_catalog_url = "https://example.com/catalog"
http_headers = {{ tag = "keep" }}
[model_providers.Unrelated]
model_catalog_url = "https://unrelated.example.com/catalog"
'''
                self.paths.config.write_text(original)
                self.manager._clear_managed_catalog()
                if catalog == "/user/custom-models.json":
                    self.assertEqual(self.paths.config.read_text(), original)
                    continue
                config = tomllib.loads(self.paths.config.read_text())
                self.assertNotIn("model_catalog_json", config)
                self.assertTrue(config["features"]["api_key_model_discovery"])
                self.assertTrue(config["features"]["other"])
                self.assertEqual(config["model_providers"]["MaoLocal"]["model_catalog_url"], "https://example.com/catalog")
                self.assertEqual(config["model_providers"]["MaoLocal"]["http_headers"], {"tag": "keep"})
                self.assertEqual(config["model_providers"]["Unrelated"]["model_catalog_url"], "https://unrelated.example.com/catalog")
