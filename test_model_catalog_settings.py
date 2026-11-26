"""Account catalog settings must survive apply, switching, migration and launch."""
from test_support import AccountManagerTestBase, json, patch, tomllib


class ModelCatalogSettingsTests(AccountManagerTestBase):
    def config(self):
        return tomllib.loads(self.paths.config.read_text())

    def test_remote_catalog_applies_without_changing_selected_model(self):
        catalog = self.base_url + "/models"
        self.save_account("CPA", model_catalog_url=catalog, api_key_model_discovery=True)
        self.paths.config.write_text('model = "gpt-6.2-sol"\n[features]\nother = true\n')
        self.manager.activate_account("CPA")
        config = self.config()
        self.assertEqual(config["model"], "gpt-6.2-sol")
        self.assertEqual(config["model_providers"]["MaoLocal"]["model_catalog_url"], catalog)
        self.assertTrue(config["features"]["api_key_model_discovery"])
        self.assertTrue(config["features"]["other"])
        self.save_account("Builtin")
        self.manager.activate_account("Builtin")
        self.assertNotIn("model_catalog_url", self.config()["model_providers"]["MaoLocal"])
        self.assertFalse(self.config()["features"]["api_key_model_discovery"])
        self.manager.activate_account("CPA")
        self.assertEqual(self.config()["model_providers"]["MaoLocal"]["model_catalog_url"], catalog)
        self.assertTrue(self.config()["features"]["api_key_model_discovery"])

    def test_disabled_discovery_retains_profile_url_but_never_applies_it(self):
        catalog = self.base_url + "/models"
        self.save_account("CPA", model_catalog_url=catalog, api_key_model_discovery=False)
        self.manager.activate_account("CPA")
        self.assertNotIn("model_catalog_url", self.config()["model_providers"]["MaoLocal"])
        profile = json.loads(self.paths.accounts.read_text())["accounts"]["CPA"]
        self.assertEqual(profile["provider_config"]["model_catalog_url"], catalog)
        self.save_account("CPA", original_name="CPA", api_key_model_discovery=True)
        self.manager.activate_account("CPA")
        self.assertEqual(self.config()["model_providers"]["MaoLocal"]["model_catalog_url"], catalog)
        self.assertTrue(self.config()["features"]["api_key_model_discovery"])

    def test_catalog_url_defaults_discovery_on_when_not_explicitly_disabled(self):
        self.save_account("CPA", model_catalog_url=self.base_url + "/models")
        self.manager.activate_account("CPA")
        self.assertTrue(self.config()["features"]["api_key_model_discovery"])
        self.assertIn("model_catalog_url", self.config()["model_providers"]["MaoLocal"])

    def test_legacy_cleanup_preserves_remote_catalog_and_features(self):
        original = f'''model_catalog_json = "{self.paths.bundled_model_catalog}"
model_provider = "MaoLocal"
[features]
api_key_model_discovery = true
other = true
[model_providers.MaoLocal]
model_catalog_url = "{self.base_url}/models"
'''
        self.paths.config.write_text(original)
        self.manager._clear_managed_catalog()
        self.assertEqual(self.paths.config.read_text(), "\n".join(original.splitlines()[1:]) + "\n")

    def test_official_switch_restores_original_discovery_setting(self):
        for feature_line in ("", "api_key_model_discovery = true\n", "api_key_model_discovery = false\n"):
            with self.subTest(original=feature_line):
                self.paths.config.write_text('[features]\nother = true\n' + feature_line)
                self.save_account("CPA" + str(len(feature_line)), model_catalog_url=self.base_url + "/models")
                self.manager.activate_account("CPA" + str(len(feature_line)))
                store = json.loads(self.paths.accounts.read_text())
                store["accounts"]["Official"] = {
                    "account_type": "official", "provider_id": "openai",
                    "official_auth": {"tokens": {"access_token": "fake"}},
                }
                self.paths.accounts.write_text(json.dumps(store))
                with patch.object(self.manager, "_validate_official_auth"):
                    self.manager.activate_account("Official")
                features = self.config()["features"]
                self.assertEqual(features.get("api_key_model_discovery"),
                                 None if not feature_line else "= true" in feature_line)
                self.assertTrue(features["other"])

    def test_seed_infers_discovery_from_url_and_respects_explicit_false(self):
        for setting in ("", "[features]\napi_key_model_discovery = false\n"):
            with self.subTest(setting=setting):
                self.paths.config.write_text(f'''model_provider = "MaoLocal"
[model_providers.MaoLocal]
base_url = "{self.base_url}"
model_catalog_url = "{self.base_url}/models"
{setting}''')
                store = self.manager._seed_from_codex()
                account = store["accounts"]["MaoLocal"]
                self.assertEqual(account["api_key_model_discovery"], not bool(setting))
                self.assertEqual(account["provider_config"]["model_catalog_url"], self.base_url + "/models")

    def test_launch_preserves_remote_catalog_configuration(self):
        self.save_account("CPA", model_catalog_url=self.base_url + "/models")
        self.manager.activate_account("CPA")
        self.assertTrue(self.config()["features"]["api_key_model_discovery"])
        before = self.paths.config.read_bytes()
        with patch.object(self.manager, "codex_running", return_value=False), \
             patch("codex_manager.os.uname") as uname, patch("codex_manager.subprocess.run"):
            uname.return_value.sysname = "Darwin"
            self.manager.launch_codex(restart=False)
        self.assertEqual(self.paths.config.read_bytes(), before)
