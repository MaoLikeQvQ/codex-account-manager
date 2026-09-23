from test_support import *


class AccountManagerTests(AccountManagerTestBase):
    def test_state_never_returns_api_key(self):
        self.save_account()
        state = self.manager.state()
        self.assertNotIn("secret-key", json.dumps(state))
        self.assertTrue(state["accounts"][0]["has_api_key"])

    def test_post_switch_actions_only_run_selected_operations(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        with patch.object(self.manager, "sync_active", return_value={"models": 2}) as sync, patch.object(
            self.manager, "claim_all_conversations", return_value={"changed_files": 1}
        ) as claim, patch.object(
            self.manager, "ensure_codex_patches", return_value={"status": "current"}
        ) as patches, patch.object(self.manager, "codex_running", return_value=False):
            result = self.manager.run_post_switch_actions(
                "MaoLocal", sync_models=True, claim_history=False
            )
        self.assertEqual(
            result["actions"],
            ["sync_models", "inject_model_catalog"],
        )
        sync.assert_called_once_with()
        claim.assert_not_called()
        patches.assert_called_once_with()

    def test_post_switch_sync_injects_model_catalog_without_image_generation(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        with patch.object(self.manager, "sync_active", return_value={"models": 2}), patch.object(
            self.manager, "ensure_codex_patches", return_value={"status": "patched"}
        ) as patches, patch.object(self.manager, "codex_running", return_value=False):
            result = self.manager.run_post_switch_actions(
                "MaoLocal", sync_models=True
            )

        self.assertEqual(result["actions"], ["sync_models", "inject_model_catalog"])
        patches.assert_called_once_with()

    def test_post_switch_passes_selected_models_to_sync(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        with patch.object(self.manager, "sync_active", return_value={"models": 1}) as sync, patch.object(
            self.manager, "ensure_codex_patches", return_value={"status": "patched"}
        ), patch.object(self.manager, "codex_running", return_value=False):
            self.manager.run_post_switch_actions(
                "MaoLocal",
                sync_models=True,
                model_ids=["vendor-coder"],
            )

        sync.assert_called_once_with(["vendor-coder"])

    def test_post_switch_stops_running_codex_before_patching(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        events = []

        with patch.object(
            self.manager, "sync_active", return_value={"models": 2}
        ), patch.object(
            self.manager, "codex_running", return_value=True
        ), patch.object(
            self.manager, "_stop_codex", side_effect=lambda: events.append("stop")
        ), patch.object(
            self.manager,
            "ensure_codex_patches",
            side_effect=lambda **_kwargs: events.append("patch") or {"status": "patched"},
        ), patch.object(
            self.manager,
            "launch_codex",
            side_effect=lambda **_kwargs: events.append("launch") or "opened",
        ) as launch:
            result = self.manager.run_post_switch_actions(
                "MaoLocal", sync_models=True
            )

        self.assertEqual(events, ["stop", "patch", "launch"])
        launch.assert_called_once_with(restart=False)
        self.assertEqual(result["actions"][-1], "restart_codex")

    def test_post_switch_reopens_codex_when_patching_fails(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")

        with patch.object(
            self.manager, "sync_active", return_value={"models": 2}
        ), patch.object(
            self.manager, "codex_running", return_value=True
        ), patch.object(
            self.manager, "_stop_codex"
        ), patch.object(
            self.manager,
            "ensure_codex_patches",
            side_effect=RuntimeError("unknown version"),
        ), patch.object(
            self.manager, "launch_codex", return_value="opened"
        ) as launch:
            with self.assertRaisesRegex(RuntimeError, "unknown version"):
                self.manager.run_post_switch_actions(
                    "MaoLocal", sync_models=True
                )

        launch.assert_called_once_with(restart=False, apply_patches=False)

    def test_complete_official_login_saves_private_profile_without_exposing_tokens(self):
        token = "official-secret-token"
        login_id = "login-1"
        self.manager._official_login_sessions[login_id] = {
            "status": "completed",
            "email": "official@example.com",
            "plan_type": "plus",
            "auth_payload": {"auth_mode": "chatgpt", "tokens": {"access_token": token}},
            "created_at": 0,
        }
        with patch.object(self.manager, "_discard_official_login_session"):
            account = self.manager.complete_official_login(login_id)

        self.assertEqual(account["account_type"], "official")
        self.assertEqual(account["email"], "official@example.com")
        self.assertTrue(account["has_official_auth"])
        self.assertNotIn(token, json.dumps(account))
        self.assertNotIn(token, json.dumps(self.manager.state()))
        persisted = json.loads(self.paths.accounts.read_text())
        self.assertEqual(
            persisted["accounts"]["official@example.com"]["official_auth"]["tokens"]["access_token"],
            token,
        )

    def test_activate_official_account_switches_auth_and_openai_provider(self):
        token = "official-secret-token"
        account = {
            "account_type": "official",
            "connection_type": "official",
            "provider_id": "openai",
            "provider_config": {},
            "official_auth": {"auth_mode": "chatgpt", "tokens": {"access_token": token}},
            "official_email": "official@example.com",
            "official_plan_type": "pro",
            "default_model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "created_at": "now",
            "updated_at": "now",
        }
        self.paths.accounts.write_text(
            json.dumps({"version": 7, "active_account": "", "accounts": {"Official": account}})
        )
        self.paths.config.write_text(
            'model = "vendor-coder"\n'
            'model_provider = "custom"\n'
            f'model_catalog_json = "{self.paths.catalog}"\n'
        )
        bundled = [
            {
                "slug": "gpt-5.6-sol",
                "display_name": "GPT-5.6-Sol",
                "visibility": "list",
                "supported_in_api": True,
            }
        ]
        with patch.object(self.manager, "_validate_official_auth"), patch.object(
            self.manager, "_bundled_catalog", return_value=bundled
        ):
            result = self.manager.activate_account("Official")

        self.assertEqual(result["models"], 1)
        config = self.paths.config.read_text()
        self.assertIn('model_provider = "openai"', config)
        self.assertIn('cli_auth_credentials_store = "file"', config)
        self.assertNotIn("model_catalog_json", config)
        self.assertEqual(json.loads(self.paths.auth.read_text())["tokens"]["access_token"], token)
        self.assertEqual(self.manager.state()["active_account"], "Official")

    def test_switching_away_captures_refreshed_official_tokens(self):
        self.save_account("Custom", "custom")
        store = json.loads(self.paths.accounts.read_text())
        store["active_account"] = "Official"
        store["accounts"]["Official"] = {
            "account_type": "official",
            "provider_id": "openai",
            "provider_config": {},
            "official_auth": {"tokens": {"access_token": "old"}},
            "official_email": "official@example.com",
            "default_model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "created_at": "now",
            "updated_at": "now",
        }
        self.paths.accounts.write_text(json.dumps(store))
        self.paths.auth.write_text(json.dumps({"tokens": {"access_token": "refreshed"}}))
        self.manager.activate_account("Custom")
        persisted = json.loads(self.paths.accounts.read_text())
        self.assertEqual(
            persisted["accounts"]["Official"]["official_auth"]["tokens"]["access_token"],
            "refreshed",
        )

    def test_switching_between_official_accounts_uses_target_credentials(self):
        bundled = [
            {
                "slug": "gpt-5.6-sol",
                "display_name": "GPT-5.6-Sol",
                "visibility": "list",
                "supported_in_api": True,
            }
        ]
        accounts = {
            "Official A": {
                "account_type": "official",
                "provider_id": "openai",
                "provider_config": {},
                "official_auth": {"tokens": {"access_token": "saved-a"}},
                "official_email": "a@example.com",
                "default_model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "created_at": "now",
                "updated_at": "now",
            },
            "Official B": {
                "account_type": "official",
                "provider_id": "openai",
                "provider_config": {},
                "official_auth": {"tokens": {"access_token": "saved-b"}},
                "official_email": "b@example.com",
                "default_model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "created_at": "now",
                "updated_at": "now",
            },
        }
        self.paths.accounts.write_text(
            json.dumps({"version": 7, "active_account": "Official A", "accounts": accounts})
        )
        self.paths.config.write_text('model = "gpt-5.6-sol"\nmodel_provider = "openai"\n')
        self.paths.auth.write_text(json.dumps({"tokens": {"access_token": "refreshed-a"}}))

        with patch.object(self.manager, "_validate_official_auth"), patch.object(
            self.manager, "_bundled_catalog", return_value=bundled
        ):
            self.manager.activate_account("Official B")

        persisted = json.loads(self.paths.accounts.read_text())
        self.assertEqual(persisted["active_account"], "Official B")
        self.assertEqual(
            persisted["accounts"]["Official A"]["official_auth"]["tokens"]["access_token"],
            "refreshed-a",
        )
        self.assertEqual(
            json.loads(self.paths.auth.read_text())["tokens"]["access_token"],
            "saved-b",
        )

    def test_official_switch_write_failure_rolls_back_all_files(self):
        account = {
            "account_type": "official",
            "connection_type": "official",
            "provider_id": "openai",
            "provider_config": {},
            "official_auth": {"tokens": {"access_token": "target-token"}},
            "official_email": "target@example.com",
            "default_model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "created_at": "now",
            "updated_at": "now",
        }
        self.paths.accounts.write_text(
            json.dumps({"version": 8, "active_account": "", "accounts": {"Target": account}})
        )
        self.paths.config.write_text('model = "old-model"\nmodel_provider = "custom"\n')
        self.paths.auth.write_text(json.dumps({"OPENAI_API_KEY": "old-key"}))
        self.paths.sync_state.write_text(json.dumps({"status": "old"}))
        before = {
            path: path.read_bytes()
            for path in (
                self.paths.config,
                self.paths.auth,
                self.paths.sync_state,
                self.paths.accounts,
            )
        }
        bundled = [
            {
                "slug": "gpt-5.6-sol",
                "display_name": "GPT-5.6-Sol",
                "visibility": "list",
                "supported_in_api": True,
            }
        ]
        original_atomic_write = self.manager._atomic_write
        failed = False

        def fail_once_on_auth(path, content):
            nonlocal failed
            if path == self.paths.auth and not failed:
                failed = True
                raise OSError("simulated write failure")
            original_atomic_write(path, content)

        with patch.object(self.manager, "_validate_official_auth"), patch.object(
            self.manager, "_bundled_catalog", return_value=bundled
        ), patch.object(self.manager, "_atomic_write", side_effect=fail_once_on_auth):
            with self.assertRaisesRegex(OSError, "simulated write failure"):
                self.manager.activate_account("Target")

        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_start_official_login_opens_validated_url_without_returning_it(self):
        class FakeInput:
            def write(self, _value):
                return None

            def flush(self):
                return None

        class FakeProcess:
            stdin = FakeInput()

            def poll(self):
                return None

            def terminate(self):
                return None

            def wait(self, timeout=None):
                return 0

        login_response = {
            "id": 2,
            "result": {
                "type": "chatgpt",
                "loginId": "codex-login-id",
                "verificationUrl": "https://auth.openai.com/codex/device",
                "userCode": "ABCD-1234",
            },
        }
        with patch.dict("codex_manager.os.environ", {"OPENSSL_MODULES": "/stale/modules"}), patch(
            "codex_manager.subprocess.Popen", return_value=FakeProcess()
        ) as popen, patch.object(
            self.manager, "_read_app_server_response", return_value=login_response
        ), patch.object(self.manager, "_open_official_auth_url") as open_url, patch.object(
            threading.Thread, "start"
        ), patch.object(self.manager, "_codex_binary", return_value="/mock/codex"):
            result = self.manager.start_official_login()

        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["user_code"], "ABCD-1234")
        self.assertNotIn("auth_url", result)
        self.assertNotIn("OPENSSL_MODULES", popen.call_args.kwargs["env"])
        open_url.assert_called_once_with("https://auth.openai.com/codex/device")
        self.manager._official_login_sessions.clear()

    def test_official_catalog_command_does_not_inherit_packaged_openssl_modules(self):
        binary = self.paths.codex_home / "mock-codex"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("mock binary")
        completed = type("Completed", (), {"stdout": '{"models": []}'})()
        with patch.dict("codex_manager.os.environ", {"OPENSSL_MODULES": "/stale/modules"}), patch(
            "codex_manager.subprocess.run", return_value=completed
        ) as run, patch("codex_manager.shutil.which", return_value=str(binary)):
            self.manager._bundled_catalog()

        self.assertNotIn("OPENSSL_MODULES", run.call_args.kwargs["env"])

    def test_account_switch_preserves_conversation_files(self):
        conversation = self.paths.codex_home / "sessions" / "thread.jsonl"
        conversation.parent.mkdir(parents=True)
        conversation.write_text("conversation\n")
        before = hashlib.sha256(conversation.read_bytes()).hexdigest()
        self.save_account("A", "provider_a")
        self.manager.activate_account("A")
        self.save_account("B", "provider_b")
        self.manager.activate_account("B")
        self.assertEqual(hashlib.sha256(conversation.read_bytes()).hexdigest(), before)
        self.assertEqual(self.manager.state()["conversations"]["files"], 1)

    def test_migrates_v5_store_and_keeps_backup(self):
        legacy = {
            "version": 5,
            "accounts": {
                "legacy": {
                    "config_top": 'model = "gpt-5.6-sol"\nmodel_provider = "legacy"',
                    "provider_block": (
                        '[model_providers.legacy]\n'
                        f'base_url = "{self.base_url}"\n'
                        'wire_api = "responses"\n'
                        'requires_openai_auth = true\n'
                    ),
                    "auth_text": '{"OPENAI_API_KEY":"old-secret"}',
                    "active": True,
                }
            },
        }
        self.paths.accounts.write_text(json.dumps(legacy))
        state = self.manager.state()
        self.assertEqual(state["active_account"], "legacy")
        self.assertNotIn("old-secret", json.dumps(state))
        persisted = json.loads(self.paths.accounts.read_text())
        self.assertEqual(persisted["version"], 8)
        self.assertEqual(persisted["accounts"]["legacy"]["connection_type"], "openai_compatible")
        self.assertEqual(persisted["accounts"]["legacy"]["auth_mode"], "legacy")
        self.assertEqual(persisted["accounts"]["legacy"]["transport"], "http_sse")
        self.assertTrue(any(self.paths.backups.glob("codex_accounts.json.*.bak")))

    def test_reconciles_store_with_real_codex_provider(self):
        self.save_account("old", "old_provider")
        self.paths.config.write_text(
            'model = "gpt-5.6-sol"\n'
            'model_provider = "MaoLocal"\n'
            '[model_providers.MaoLocal]\n'
            f'base_url = "{self.base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n'
        )
        self.paths.auth.write_text('{"OPENAI_API_KEY":"current-secret"}')
        state = self.manager.state()
        self.assertEqual(state["active_account"], "MaoLocal")
        self.assertEqual({account["name"] for account in state["accounts"]}, {"old", "MaoLocal"})
        self.assertNotIn("current-secret", json.dumps(state))

    def test_files_and_backups_use_restrictive_permissions(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        self.manager.sync_active()
        self.manager.switch_model("vendor-coder")
        for path in (self.paths.accounts, self.paths.config, self.paths.auth, self.paths.catalog):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for backup in self.paths.backups.iterdir():
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_migrates_v6_custom_accounts_to_v8(self):
        self.save_account()
        legacy = json.loads(self.paths.accounts.read_text())
        legacy["version"] = 6
        legacy["accounts"]["MaoLocal"].pop("account_type")
        legacy["accounts"]["MaoLocal"].pop("connection_type")
        legacy["accounts"]["MaoLocal"].pop("auth_mode")
        legacy["accounts"]["MaoLocal"].pop("transport")
        self.paths.accounts.write_text(json.dumps(legacy))

        state = self.manager.state()
        persisted = json.loads(self.paths.accounts.read_text())
        self.assertEqual(persisted["version"], 8)
        self.assertEqual(persisted["accounts"]["MaoLocal"]["account_type"], "custom")
        self.assertEqual(
            persisted["accounts"]["MaoLocal"]["connection_type"],
            "openai_compatible",
        )
        self.assertEqual(persisted["accounts"]["MaoLocal"]["auth_mode"], "legacy")
        self.assertEqual(persisted["accounts"]["MaoLocal"]["transport"], "http_sse")
        self.assertEqual(state["accounts"][0]["account_type"], "custom")

    def test_migrates_v7_to_v8_without_changing_provider_or_model_state(self):
        self.save_account("Existing Route", "stable_provider")
        self.manager.activate_account("Existing Route")
        legacy = json.loads(self.paths.accounts.read_text())
        legacy["version"] = 7
        account = legacy["accounts"]["Existing Route"]
        account.pop("connection_type")
        account.pop("auth_mode")
        account.pop("transport")
        expected = {
            "active_account": legacy["active_account"],
            "provider_id": account["provider_id"],
            "api_key": account["api_key"],
            "model_ids": account["model_ids"],
            "catalog_model_ids": account["catalog_model_ids"],
            "provider_config": account["provider_config"],
        }
        self.paths.accounts.write_text(json.dumps(legacy))

        state = self.manager.state()
        persisted = json.loads(self.paths.accounts.read_text())
        migrated = persisted["accounts"]["Existing Route"]

        self.assertEqual(persisted["version"], 8)
        self.assertEqual(persisted["active_account"], expected["active_account"])
        for key in (
            "provider_id",
            "api_key",
            "model_ids",
            "catalog_model_ids",
            "provider_config",
        ):
            self.assertEqual(migrated[key], expected[key])
        self.assertEqual(migrated["connection_type"], "openai_compatible")
        self.assertEqual(migrated["auth_mode"], "legacy")
        self.assertEqual(migrated["transport"], "http_sse")
        self.assertEqual(state["accounts"][0]["provider_id"], "stable_provider")
        self.assertTrue(any(self.paths.backups.glob("codex_accounts.json.*.bak")))
