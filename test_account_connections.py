from test_support import *
from manager_parts.config_import import parse_provider_config


class AccountConnectionTests(AccountManagerTestBase):
    def imported(self, **provider):
        return {"base_url": self.base_url, "wire_api": "responses", **provider}

    def config(self):
        return tomllib.loads(self.paths.config.read_text())

    def test_import_roundtrip_and_switch_replace_connection_without_changing_global_settings(self):
        catalog = self.base_url + "/catalog"
        parsed = parse_provider_config(f'''model = "codex-auto-review"
model_provider = "krill"
web_search = "live"
suppress_unstable_features_warning = true
[features]
api_key_model_discovery = true
[model_providers.krill]
name = "OpenAI"
base_url = "{self.base_url}"
model_catalog_url = "{catalog}"
requires_openai_auth = false
wire_api = "responses"
http_headers = {{ "x.channel.tag" = "private-header" }}
''')
        self.manager.save_account({**parsed, "api_key": "key-a", "name": "Channel A"})
        self.save_account("Channel B", "different", api_key="key-b")
        self.paths.config.write_text('web_search = "disabled"\nsuppress_unstable_features_warning = false\n[mcp_servers.demo]\ncommand = "demo"\n[model_providers.MaoLocal.http_headers]\nold = "stale"\n')
        self.manager.activate_account("Channel A")
        config = self.config()
        provider = config["model_providers"]["MaoLocal"]
        self.assertEqual(config["model_provider"], "MaoLocal")
        self.assertEqual(provider["name"], "MaoLocal")
        self.assertEqual(provider["model_catalog_url"], catalog)
        self.assertFalse(provider["requires_openai_auth"])
        self.assertEqual(provider["http_headers"], {"x.channel.tag": "private-header"})
        self.assertTrue(config["features"]["api_key_model_discovery"])
        self.assertNotIn("model", config)
        self.assertEqual(config["web_search"], "disabled")
        self.assertFalse(config["suppress_unstable_features_warning"])
        self.assertEqual(config["mcp_servers"]["demo"]["command"], "demo")
        self.assertNotIn("private-header", json.dumps(self.manager.state()))
        self.manager.activate_account("Channel B")
        provider = self.config()["model_providers"]["MaoLocal"]
        self.assertNotIn("model_catalog_url", provider)
        self.assertNotIn("http_headers", provider)
        self.assertFalse(self.config()["features"]["api_key_model_discovery"])
        self.assertEqual(self.manager.state()["active_account"], "Channel B")
        self.assertEqual(json.loads(self.paths.auth.read_text())["OPENAI_API_KEY"], "key-b")

    def test_same_address_different_keys_and_external_changes_match_correct_account(self):
        self.save_account("A", api_key="key-a")
        self.save_account("B", api_key="key-b")
        self.manager.activate_account("B")
        self.assertEqual(self.manager.state()["active_account"], "B")
        self.paths.auth.write_text('{"OPENAI_API_KEY":"key-a"}')
        self.assertEqual(self.manager.state()["active_account"], "A")
        self.paths.auth.write_text('{"OPENAI_API_KEY":"external"}')
        for _ in range(2):
            state = self.manager.state()
            self.assertEqual(state["active_account"], "")
            self.assertEqual(len(state["accounts"]), 2)

    def test_edit_active_preserves_current_config_until_explicit_apply(self):
        self.save_account("A", api_key="key-a", provider_config=self.imported(model_catalog_url=self.base_url + "/catalog"))
        self.manager.activate_account("A")
        before = self.paths.config.read_bytes()
        self.save_account("Renamed A", original_name="A", api_key="key-b", base_url="http://127.0.0.1:12345/v1")
        state = self.manager.state()
        self.assertEqual(state["active_account"], "Renamed A")
        self.assertTrue(state["accounts"][0]["pending_apply"])
        self.assertEqual(self.paths.config.read_bytes(), before)
        self.assertEqual(json.loads(self.paths.auth.read_text())["OPENAI_API_KEY"], "key-a")
        self.manager.activate_account("Renamed A")
        self.assertFalse(self.manager.state()["accounts"][0]["pending_apply"])
        self.assertEqual(self.config()["model_providers"]["MaoLocal"]["base_url"], "http://127.0.0.1:12345/v1")
        self.assertEqual(json.loads(self.paths.auth.read_text())["OPENAI_API_KEY"], "key-b")

    def test_duplicate_add_does_not_overwrite_and_import_edit_replaces_hidden_fields(self):
        self.save_account("A", provider_config=self.imported(http_headers={"x-old": "old"}, model_catalog_url=self.base_url + "/catalog"))
        before = self.paths.accounts.read_bytes()
        with self.assertRaisesRegex(ValueError, "账号已存在"):
            self.save_account("A", api_key="replacement")
        self.assertEqual(self.paths.accounts.read_bytes(), before)
        self.save_account("A", original_name="A", api_key="", provider_config=self.imported(), api_key_model_discovery=False)
        account = json.loads(self.paths.accounts.read_text())["accounts"]["A"]
        self.assertNotIn("model_catalog_url", account["provider_config"])
        self.assertNotIn("http_headers", account["provider_config"])
        self.assertEqual(account["api_key"], "secret-key")

    def test_catalog_detection_uses_actual_endpoint_and_keeps_original_key_when_editing(self):
        catalog = self.base_url + "/catalog"
        self.save_account("A", provider_config=self.imported(model_catalog_url=catalog))
        ModelHandler.successful_path = "/v1/catalog"
        ModelHandler.response_shape = "models_slug"
        result = self.manager.verify_account({"name": "A", "original_name": "A", "base_url": self.base_url})
        self.assertEqual(result["endpoint"], catalog)
        self.assertEqual(result["model_ids"], ModelHandler.models)
        self.assertEqual(ModelHandler.request_paths, ["/v1/catalog"])
        self.assertEqual(ModelHandler.authorization, "Bearer secret-key")
        self.assertFalse(self.paths.config.exists())

    def test_switch_applies_catalog_profile_and_keeps_explicit_verification(self):
        catalog = self.base_url + "/catalog"
        self.save_account("A", provider_config=self.imported(model_catalog_url=catalog), api_key_model_discovery=True)
        self.manager.activate_account("A")
        active_provider = self.config()["model_providers"]["MaoLocal"]
        self.assertEqual(active_provider["model_catalog_url"], catalog)
        self.assertTrue(self.config()["features"]["api_key_model_discovery"])
        saved = json.loads(self.paths.accounts.read_text())["accounts"]["A"]
        self.assertEqual(saved["provider_config"]["model_catalog_url"], catalog)
        self.assertTrue(saved["api_key_model_discovery"])
        self.assertEqual(self.manager.state()["active_account"], "A")
        ModelHandler.successful_path = "/v1/catalog"
        ModelHandler.response_shape = "models_slug"
        result = self.manager.verify_account({"name": "A", "original_name": "A", "base_url": self.base_url})
        self.assertEqual(result["endpoint"], catalog)
        self.assertEqual(result["model_ids"], ModelHandler.models)
        self.assertEqual(ModelHandler.request_paths, ["/v1/catalog"])

    def test_failed_detection_never_falls_back_to_official_models(self):
        ModelHandler.successful_path = "/unreachable"
        with patch.object(self.manager, "_official_catalog_models", return_value=[{"slug": "fake-success"}]) as bundled:
            with self.assertRaisesRegex(RuntimeError, "未能读取渠道模型列表"):
                self.manager.verify_account({"name": "A", "base_url": self.base_url, "api_key": "secret-key"})
            bundled.assert_not_called()
        self.assertFalse(self.paths.accounts.exists())

    def test_custom_switch_failure_rolls_back_config_auth_and_store(self):
        self.save_account("A", api_key="key-a")
        self.save_account("B", api_key="key-b", api_key_model_discovery=True)
        self.manager.activate_account("A")
        files = [self.paths.config, self.paths.auth, self.paths.accounts]
        before = {path: path.read_bytes() for path in files}
        original = self.manager._atomic_write
        failed = False
        def write(path, content):
            nonlocal failed
            if path == self.paths.auth and not failed:
                failed = True
                raise OSError("simulated")
            original(path, content)
        with patch.object(self.manager, "_atomic_write", side_effect=write):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.manager.activate_account("B")
        for path in files:
            self.assertEqual(path.read_bytes(), before[path])

    def test_official_switch_restores_feature_baseline(self):
        self.paths.config.write_text('[features]\napi_key_model_discovery = true\nresponses_websockets_v2 = true\nother = true\n')
        self.save_account("Custom", api_key_model_discovery=True)
        self.manager.activate_account("Custom")
        store = json.loads(self.paths.accounts.read_text())
        store["accounts"]["Official"] = {
            "account_type": "official", "provider_id": "openai", "default_model": "gpt-test",
            "official_auth": {"tokens": {"access_token": "token"}},
        }
        self.paths.accounts.write_text(json.dumps(store))
        with patch.object(self.manager, "_validate_official_auth"), patch.object(self.manager, "_official_catalog_models", return_value=[{"slug": "gpt-test"}]):
            self.manager.activate_account("Official")
        self.assertEqual(self.config()["features"], {"api_key_model_discovery": True, "responses_websockets_v2": True, "other": True})

    def test_restart_pending_is_reported_only_when_running(self):
        self.save_account("A")
        with patch.object(self.manager, "codex_running", return_value=True):
            self.manager.activate_account("A")
            self.assertTrue(self.manager.state()["codex"]["restart_required"])
        with patch.object(self.manager, "codex_running", return_value=False):
            self.assertFalse(self.manager.state()["codex"]["restart_required"])

    def test_inline_and_commented_features_preserve_unrelated_settings(self):
        self.save_account("A", api_key_model_discovery=True)
        for text in ['features = { other = true, api_key_model_discovery = false }\n',
                     '[features] # keep these settings\nother = true\napi_key_model_discovery = false\n']:
            with self.subTest(text=text):
                self.paths.config.write_text(text)
                self.manager.activate_account("A")
                features = self.config()['features']
                self.assertTrue(features['other'])
                self.assertTrue(features['api_key_model_discovery'])
                self.assertFalse(features['responses_websockets_v2'])

    def test_pending_edit_blocks_history_until_apply_and_hides_previous_key(self):
        self.save_account("A", api_key="old-key")
        self.manager.activate_account("A")
        self.save_account("A", original_name="A", api_key="new-key")
        with self.assertRaisesRegex(ValueError, "待应用"):
            self.manager.claim_all_conversations("A")
        state = json.dumps(self.manager.state())
        self.assertNotIn("old-key", state)
        self.assertNotIn("new-key", state)

    def test_model_detection_uses_environment_and_query_without_exposing_query_secrets(self):
        provider = self.imported(env_key="ACCOUNT_TEST_KEY", query_params={"access": "query-secret"})
        with patch.dict(os.environ, {"ACCOUNT_TEST_KEY": "env-secret"}):
            result = self.manager.verify_account({"name": "A", "base_url": self.base_url,
                "api_key": "saved-key", "provider_config": provider})
        self.assertEqual(ModelHandler.authorization, "Bearer env-secret")
        self.assertEqual(ModelHandler.request_paths, ["/v1?access=query-secret"])
        self.assertNotIn("query-secret", json.dumps(result))

    def test_window_state_skips_history_but_explicit_history_state_is_available(self):
        self.save_account("A")
        with patch.object(self.manager, "_conversation_state", return_value={"files": 123}) as history:
            light = self.manager.state(include_conversations=False)
            history.assert_not_called()
            self.assertNotIn("conversations", light)
            self.assertEqual(light["accounts"][0]["name"], "A")
            full = self.manager.state()
            history.assert_called_once_with()
            self.assertEqual(full["conversations"], {"files": 123})
