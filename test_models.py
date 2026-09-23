from test_support import *


class AccountManagerTests(AccountManagerTestBase):
    def test_launch_after_app_update_adds_official_models_without_remote_sync(self):
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("MaoLocal")
            self.manager.sync_active(["vendor-coder"])
        official = [{"slug": "new-official", "visibility": "list", "display_name": "New"}]

        with patch.object(self.manager, "_official_catalog_models", return_value=official), patch.object(
            self.manager, "_bundled_catalog", return_value=official
        ), patch.object(
            self.manager, "_fetch_model_ids", side_effect=AssertionError("unexpected sync")
        ), patch.object(self.manager, "codex_running", return_value=False), patch.object(
            self.manager, "ensure_codex_patches", return_value={"status": "patched"}
        ) as patches, patch("codex_manager.subprocess.run") as run:
            launched = self.manager.launch_codex()

        self.assertEqual(launched, "opened")
        patches.assert_called_once_with()
        run.assert_called_once()
        catalog = json.loads(self.paths.catalog.read_text())["models"]
        self.assertEqual(
            {model["slug"]: model["visibility"] for model in catalog},
            {"new-official": "list", "gpt-5.6-sol": "hide", "vendor-coder": "list"},
        )

    def test_bundled_catalog_cache_invalidates_when_app_binary_changes(self):
        app = self.make_fake_codex_app()
        binary = app / "Contents/Resources/codex"
        outputs = [
            subprocess.CompletedProcess([], 0, '{"models":[{"slug":"old"}]}', ""),
            subprocess.CompletedProcess([], 0, '{"models":[{"slug":"new"}]}', ""),
        ]
        with patch("codex_manager.CODEX_APP", app), patch(
            "codex_manager.subprocess.run", side_effect=outputs
        ) as run:
            self.assertEqual(self.manager._bundled_catalog()[0]["slug"], "old")
            self.assertEqual(self.manager._bundled_catalog()[0]["slug"], "old")
            binary.write_bytes(b"updated codex binary")
            self.assertEqual(self.manager._bundled_catalog()[0]["slug"], "new")
        self.assertEqual(run.call_count, 2)

    def test_activate_uses_saved_model_cache_without_remote_sync(self):
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("MaoLocal")
            self.manager.sync_active()
            with patch.object(
                self.manager, "_fetch_model_ids", side_effect=AssertionError("unexpected sync")
            ):
                result = self.manager.activate_account("MaoLocal")
        self.assertEqual(result["models_source"], "account_cache")
        self.assertEqual(result["models"], 2)

    def test_codex_model_filter_patch_uses_local_model_list_and_is_idempotent(self):
        app = self.make_fake_codex_app()
        with patch.object(self.manager, "_sign_locally_modified_codex"), patch.object(
            self.manager, "_verify_codex_signature"
        ):
            first = self.manager.ensure_codex_patches(
                app
            )
            first_blob = (app / "Contents/Resources/app.asar").read_bytes()
            second = self.manager.ensure_codex_patches(app)

        self.assertEqual(first["status"], "patched")
        self.assertEqual(second["status"], "current")
        self.assertIn(CODEX_MODEL_FILTER_MARKER, first_blob)
        self.assertIn(b"!1/*maolocal-models", first_blob)
        self.assertIn(b"showAnnouncement:!1   ", first_blob)
        self.assertIn(b"gateName:`9999999999`,featureKey:`unrelated_feature`", first_blob)
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        self.assertEqual(
            info["ElectronAsarIntegrity"]["Resources/app.asar"]["hash"],
            hashlib.sha256(first_blob).hexdigest(),
        )
        self.assertTrue(Path(first["backup"]).joinpath("app.asar").is_file())
        self.assertTrue(
            Path(first["backup"])
            .joinpath("Sparkle.framework/Versions/B/Autoupdate")
            .is_file()
        )

    def test_native_catalog_filter_needs_no_app_patch(self):
        native_filter = (
            b"function allowed({additionalAvailableModels:e,authMethod:t,"
            b"availableModels:n,hasConfiguredModelCatalog:r,"
            b"isCustomModelProvider:i,model:a,useHiddenModels:o})"
            b"{return e?.has(a.model)===!0||a.model!==`codex-auto-review`&&"
            b"(r&&!a.hidden||(o&&!i&&t!==`amazonBedrock`?n.has(a.model):!a.hidden))}"
        )
        app = self.make_fake_codex_app(native_filter)
        asar = app / "Contents/Resources/app.asar"
        before = asar.read_bytes()
        shutil.rmtree(app / CODEX_SPARKLE_RELATIVE_PATH)

        with patch.object(self.manager, "_sign_locally_modified_codex") as sign:
            result = self.manager.ensure_codex_patches(app)

        self.assertEqual(result["status"], "native")
        self.assertEqual(asar.read_bytes(), before)
        sign.assert_not_called()
        self.assertFalse((self.paths.backups / "codex-app-patches").exists())

    def test_codex_model_filter_patch_supports_new_custom_provider_guard(self):
        source = (
            b"function allowed({additionalAvailableModels:e,authMethod:t,"
            b"availableModels:n,isCustomModelProvider:r,model:i,useHiddenModels:a})"
            b"{return e?.has(i.model)===!0||"
            b"i.model!==`codex-auto-review`&&"
            b"(a&&!r&&t!==`amazonBedrock`?n.has(i.model):!i.hidden)}"
        )

        patched = self.manager._patch_model_availability_blob(source)

        self.assertIn(CODEX_MODEL_FILTER_MARKER, patched)
        self.assertNotIn(b"a&&!!1", patched)
        self.assertIn(b"(!1/*maolocal-models", patched)
        self.assertIn(b"!r&&e?.has(i.model) ", patched)
        self.assertNotIn(b"return e?.has(i.model)===!0", patched)
        self.assertEqual(len(patched), len(source))

    def test_codex_model_filter_patch_migrates_264_partial_patch(self):
        source = (
            b"function allowed({additionalAvailableModels:e,authMethod:t,"
            b"availableModels:n,isCustomModelProvider:r,model:i,useHiddenModels:a})"
            b"{return e?.has(i.model)===!0||"
            b"i.model!==`codex-auto-review`&&"
            b"(!1/*maolocal-models_____*/?n.has(i.model):!i.hidden)}"
        )

        patched = self.manager._patch_model_availability_blob(source)

        self.assertIn(b"!r&&e?.has(i.model) ", patched)
        self.assertNotIn(b"a&&!!1", patched)
        self.assertTrue(self.manager._model_availability_patch_is_current(patched))
        self.assertEqual(len(patched), len(source))

    def test_codex_model_filter_patch_repairs_262_inverted_guard(self):
        broken_filter = (
            b"function allowed({additionalAvailableModels:e,authMethod:t,"
            b"availableModels:n,isCustomModelProvider:r,model:i,useHiddenModels:a})"
            b"{return e?.has(i.model)===!0||"
            b"i.model!==`codex-auto-review`&&"
            b"(a&&!!1/*maolocal-models_*/?n.has(i.model):!i.hidden)}"
        )
        app = self.make_fake_codex_app(
            broken_filter
            + b";function announcement(){return {showAnnouncement:!1   }};"
            + b"const gates=[{gateName:`1935276618`,featureKey:`image_generation`}]"
        )

        with patch.object(self.manager, "_sign_locally_modified_codex"), patch.object(
            self.manager, "_verify_codex_signature"
        ):
            first = self.manager.ensure_codex_patches(app)
            second = self.manager.ensure_codex_patches(app)

        patched = (app / "Contents/Resources/app.asar").read_bytes()
        self.assertEqual(first["status"], "patched")
        self.assertEqual(second["status"], "current")
        self.assertNotIn(b"a&&!!1", patched)
        self.assertIn(b"(!1/*maolocal-models", patched)
        self.assertEqual(len(patched), len(broken_filter) + len(
            b";function announcement(){return {showAnnouncement:!1   }};"
            b"const gates=[{gateName:`1935276618`,featureKey:`image_generation`}]"
        ))

    def test_existing_patch_repairs_incompatible_updater_signatures(self):
        model_filter = self.manager._patch_model_availability_blob(
            b"function allowed({additionalAvailableModels:e,authMethod:t,"
            b"availableModels:n,isCustomModelProvider:r,model:i,useHiddenModels:a})"
            b"{return e?.has(i.model)===!0||i.model!==`codex-auto-review`&&"
            b"(a&&!r&&t!==`amazonBedrock`?n.has(i.model):!i.hidden)}"
        )
        blob = (
            model_filter
            + b";function announcement(){return {showAnnouncement:!1   }};"
            + b"const gates=[{gateName:`1935276618`,featureKey:`image_generation`}]"
        )
        app = self.make_fake_codex_app(blob)
        self.signature_compatibility_mock.return_value = False

        with patch.object(self.manager, "_sign_locally_modified_codex") as sign, patch.object(
            self.manager, "_verify_codex_signature"
        ):
            result = self.manager.ensure_codex_patches(app)

        self.assertEqual(result["status"], "patched")
        sign.assert_called_once_with(app)

    def test_codex_model_filter_patch_rejects_unknown_app_without_changes(self):
        app = self.make_fake_codex_app(b"new desktop implementation")
        asar = app / "Contents/Resources/app.asar"
        before = asar.read_bytes()

        with self.assertRaisesRegex(RuntimeError, "预期 1 处，实际 0 处"):
            self.manager.ensure_codex_patches(app)

        self.assertEqual(asar.read_bytes(), before)
        self.assertFalse((self.paths.backups / "codex-app-patches").exists())

    def test_codex_model_filter_patch_restores_original_when_signing_fails(self):
        app = self.make_fake_codex_app()
        targets = [
            app / "Contents/Resources/app.asar",
            app / "Contents/Info.plist",
            app / "Contents/MacOS/ChatGPT",
            app / "Contents/Resources/codex",
            app / "Contents/_CodeSignature/CodeResources",
            app / CODEX_SPARKLE_RELATIVE_PATH / "Versions/B/Autoupdate",
        ]
        before = {path: path.read_bytes() for path in targets}

        def fail_after_sparkle_change(target_app):
            sparkle = target_app / CODEX_SPARKLE_RELATIVE_PATH / "Versions/B/Autoupdate"
            sparkle.write_bytes(b"partially signed autoupdate")
            raise RuntimeError("sign failed")

        with patch.object(
            self.manager,
            "_sign_locally_modified_codex",
            side_effect=fail_after_sparkle_change,
        ), patch.object(self.manager, "_verify_codex_signature"):
            with self.assertRaisesRegex(RuntimeError, "已恢复原应用"):
                self.manager.ensure_codex_patches(app)

        self.assertEqual({path: path.read_bytes() for path in targets}, before)

    def test_local_signing_signs_sparkle_from_inner_targets_to_outer_app(self):
        app = self.make_fake_codex_app()
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        with patch("codex_manager.subprocess.run", return_value=completed) as run, patch.object(
            CodexManager,
            "_codex_update_signatures_are_compatible",
            return_value=True,
        ):
            self.manager._sign_locally_modified_codex(app)

        commands = [call.args[0] for call in run.call_args_list]
        targets = [Path(command[-1]) for command in commands]
        self.assertEqual(
            targets,
            [*self.manager._codex_sparkle_sign_targets(app), app],
        )
        self.assertNotIn("--deep", [argument for command in commands for argument in command])
        downloader = app / CODEX_SPARKLE_RELATIVE_PATH / "Versions/B/XPCServices/Downloader.xpc"
        downloader_command = commands[targets.index(downloader)]
        self.assertIn("--preserve-metadata=entitlements", downloader_command)
        for command, target in zip(commands[:-1], targets[:-1]):
            if target != downloader:
                self.assertNotIn("--preserve-metadata=entitlements", command)

    def test_codex_patch_adds_announcement_suppression_to_existing_model_patch(self):
        model_filter = self.manager._patch_model_availability_blob(
            b"function allowed({additionalAvailableModels:e,authMethod:t,"
            b"availableModels:n,isCustomModelProvider:r,model:i,useHiddenModels:a})"
            b"{return e?.has(i.model)===!0||i.model!==`codex-auto-review`&&"
            b"(a&&!r&&t!==`amazonBedrock`?n.has(i.model):!i.hidden)}"
        )
        app = self.make_fake_codex_app(
            model_filter
            + b";function announcement(e,t,n,r){return "
            + b"{announcementContent:n,showAnnouncement:e&&!t,dismissAnnouncement:r}};"
            + b"const gates=[{gateName:`1935276618`,featureKey:`image_generation`}]"
        )

        with patch.object(self.manager, "_sign_locally_modified_codex"), patch.object(
            self.manager, "_verify_codex_signature"
        ):
            result = self.manager.ensure_codex_patches(app)

        blob = (app / "Contents/Resources/app.asar").read_bytes()
        self.assertEqual(result["status"], "patched")
        self.assertEqual(blob.count(CODEX_MODEL_FILTER_MARKER), 1)
        self.assertIn(b"showAnnouncement:!1   ", blob)

    def test_verify_account_validates_without_saving_or_switching(self):
        result = self.manager.verify_account(
            {
                "name": "MaoLocal",
                "provider_id": "MaoLocal",
                "provider_name": "MaoLocal",
                "base_url": self.base_url,
                "wire_api": "responses",
                "api_key": "secret-key",
                "reasoning_effort": "high",
            }
        )
        self.assertEqual(result["models"], 2)
        self.assertEqual(result["model_ids"], ModelHandler.models)
        self.assertEqual(ModelHandler.authorization, "Bearer secret-key")
        state = self.manager.state()
        self.assertEqual(state["accounts"], [])
        self.assertEqual(state["active_account"], "")
        self.assertFalse(self.paths.config.exists())

    def test_verify_account_accepts_sub2api_models_slug_shape(self):
        ModelHandler.response_shape = "models_slug"

        result = self.manager.verify_account(
            {
                "name": "Sub2API",
                "provider_id": "sub2api_pool",
                "provider_name": "Sub2API",
                "base_url": self.base_url,
                "wire_api": "responses",
                "api_key": "secret-key",
                "reasoning_effort": "high",
                "connection_type": "sub2api",
                "auth_mode": "legacy",
                "transport": "http_sse",
            }
        )

        self.assertEqual(result["model_ids"], ModelHandler.models)
        self.assertEqual(result["connection_type"], "sub2api")
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.auth.exists())

    def test_model_discovery_tries_base_models_and_v1_models(self):
        ModelHandler.successful_path = "/v1/models"
        origin = self.base_url.removesuffix("/v1")
        account = {
            "provider_config": {"base_url": origin},
            "api_key": "secret-key",
        }

        model_ids = self.manager._fetch_model_ids(account)

        self.assertEqual(model_ids, ModelHandler.models)
        self.assertEqual(ModelHandler.request_paths, ["/", "/models", "/v1/models"])

    def test_model_discovery_falls_back_to_official_catalog(self):
        ModelHandler.successful_path = "/never"
        origin = self.base_url.removesuffix("/v1")
        account = {
            "provider_config": {"base_url": origin},
            "api_key": "secret-key",
        }
        official = [{"slug": "gpt-5.6-sol", "visibility": "list"}]

        with patch.object(self.manager, "_official_catalog_models", return_value=official):
            model_ids = self.manager._fetch_model_ids(account)

        self.assertEqual(model_ids, ["gpt-5.6-sol"])
        self.assertEqual(ModelHandler.request_paths, ["/", "/models", "/v1/models"])

    def test_sub2api_legacy_mode_reuses_auth_and_local_catalog_contract(self):
        account = self.save_account(
            "Sub Pool",
            "sub2api_pool",
            connection_type="sub2api",
            auth_mode="legacy",
            transport="http_sse",
        )

        self.assertEqual(account["connection_type"], "sub2api")
        self.assertEqual(account["auth_mode"], "legacy")
        self.assertEqual(account["transport"], "http_sse")
        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("Sub Pool")
            self.manager.sync_active()

        config = tomllib.loads(self.paths.config.read_text())
        provider = config["model_providers"]["sub2api_pool"]
        self.assertTrue(provider["requires_openai_auth"])
        self.assertNotIn("supports_websockets", provider)
        self.assertNotIn("http_headers", provider)
        self.assertEqual(config["model_catalog_json"], str(self.paths.catalog))
        self.assertEqual(
            json.loads(self.paths.auth.read_text()),
            {"OPENAI_API_KEY": "secret-key"},
        )
        self.assertEqual(
            [item["slug"] for item in json.loads(self.paths.catalog.read_text())["models"]],
            ModelHandler.models,
        )

    def test_sub2api_api_key_mode_keeps_key_out_of_config_and_public_state(self):
        self.save_account(
            "Sub Pool",
            "sub2api_pool",
            connection_type="sub2api",
            auth_mode="api_key",
            transport="http_sse",
        )
        self.manager.activate_account("Sub Pool")

        config_text = self.paths.config.read_text()
        config = tomllib.loads(config_text)
        provider = config["model_providers"]["sub2api_pool"]
        self.assertFalse(provider["requires_openai_auth"])
        self.assertNotIn("supports_websockets", provider)
        self.assertEqual(
            provider["http_headers"],
            {"x-openai-actor-authorization": "local-image-extension"},
        )
        self.assertNotIn("experimental_bearer_token", provider)
        self.assertNotIn("secret-key", config_text)
        self.assertNotIn("secret-key", self.paths.sync_state.read_text())
        self.assertNotIn("secret-key", json.dumps(self.manager.state()))
        self.assertEqual(
            json.loads(self.paths.auth.read_text()),
            {"OPENAI_API_KEY": "secret-key"},
        )

    def test_sub2api_websocket_enables_feature_without_overwriting_other_sections(self):
        self.save_account(
            "Sub Pool",
            "sub2api_pool",
            connection_type="sub2api",
            auth_mode="api_key",
            transport="websocket",
        )
        self.paths.config.write_text(
            'model = "old"\n'
            'model_provider = "old"\n\n'
            '[features]\n'
            'goals = true\n\n'
            '[mcp_servers.keep]\n'
            'command = "keep"\n'
        )

        self.manager.activate_account("Sub Pool")

        config = tomllib.loads(self.paths.config.read_text())
        self.assertNotIn("supports_websockets", config["model_providers"]["sub2api_pool"])
        self.assertTrue(config["features"]["responses_websockets_v2"])
        self.assertTrue(config["features"]["goals"])
        self.assertEqual(config["mcp_servers"]["keep"]["command"], "keep")

    def test_changing_sub2api_account_to_compatible_removes_managed_ws_and_actor_fields(self):
        self.save_account(
            "Route",
            "route",
            connection_type="sub2api",
            auth_mode="api_key",
            transport="websocket",
        )

        self.save_account(
            "Route",
            "route",
            original_name="Route",
            connection_type="openai_compatible",
            auth_mode="legacy",
            transport="http_sse",
            api_key="",
        )

        persisted = json.loads(self.paths.accounts.read_text())["accounts"]["Route"]
        self.assertEqual(persisted["connection_type"], "openai_compatible")
        self.assertNotIn("supports_websockets", persisted["provider_config"])
        self.assertNotIn("http_headers", persisted["provider_config"])

    def test_existing_store_removes_legacy_supports_websockets_field(self):
        self.save_account(
            "Sub Pool",
            "sub2api_pool",
            connection_type="sub2api",
            transport="websocket",
        )
        stored = json.loads(self.paths.accounts.read_text())
        stored["accounts"]["Sub Pool"]["provider_config"]["supports_websockets"] = True
        self.paths.accounts.write_text(json.dumps(stored))

        self.manager.state()

        persisted = json.loads(self.paths.accounts.read_text())
        self.assertNotIn(
            "supports_websockets",
            persisted["accounts"]["Sub Pool"]["provider_config"],
        )

    def test_sub2api_model_injection_reuses_existing_catalog_patch_chain(self):
        self.save_account(
            "Sub Pool",
            "sub2api_pool",
            connection_type="sub2api",
            auth_mode="legacy",
            transport="http_sse",
        )
        self.manager.activate_account("Sub Pool")

        with patch.object(
            self.manager,
            "sync_active",
            return_value={"models": 2},
        ) as sync, patch.object(
            self.manager,
            "ensure_codex_patches",
            return_value={"status": "patched"},
        ) as patches, patch.object(self.manager, "codex_running", return_value=False):
            result = self.manager.run_post_switch_actions(
                "Sub Pool",
                sync_models=True,
                model_ids=["vendor-coder"],
            )

        sync.assert_called_once_with(["vendor-coder"])
        patches.assert_called_once_with()
        self.assertIn("inject_model_catalog", result["actions"])

    def test_activate_reuses_existing_catalog_without_remote_sync(self):
        self.paths.catalog.write_text(
            json.dumps(
                self.manager._build_catalog(
                    ["gpt-5.6-sol", "vendor-coder"], ["vendor-coder"]
                )
            )
        )
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]), patch.object(
            self.manager, "_fetch_model_ids", side_effect=AssertionError("unexpected sync")
        ):
            result = self.manager.activate_account("MaoLocal")
        self.assertEqual(result["models"], 2)
        self.assertEqual(result["models_source"], "existing_catalog")
        self.assertEqual(ModelHandler.authorization, "")
        config = self.paths.config.read_text()
        self.assertIn('model_provider = "MaoLocal"', config)
        self.assertIn(f'model_catalog_json = "{self.paths.catalog}"', config)
        self.assertIn("[model_providers.MaoLocal]", config)
        self.assertEqual(json.loads(self.paths.auth.read_text()), {"OPENAI_API_KEY": "secret-key"})
        catalog = json.loads(self.paths.catalog.read_text())
        self.assertEqual([model["slug"] for model in catalog["models"]], ModelHandler.models)
        self.assertEqual(
            {model["slug"]: model["visibility"] for model in catalog["models"]},
            {"gpt-5.6-sol": "hide", "vendor-coder": "list"},
        )
        self.assertTrue(all(model["supported_in_api"] for model in catalog["models"]))
        self.assertTrue(all(model["availability_nux"] is None for model in catalog["models"]))
        self.assertTrue(all(model["upgrade"] is None for model in catalog["models"]))

    def test_activate_uses_saved_default_when_no_local_catalog_exists(self):
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]), patch.object(
            self.manager, "_fetch_model_ids", side_effect=AssertionError("unexpected sync")
        ):
            result = self.manager.activate_account("MaoLocal")

        self.assertEqual(result["models_source"], "default_model")
        self.assertEqual(result["models"], 1)
        self.assertEqual(
            [model["slug"] for model in json.loads(self.paths.catalog.read_text())["models"]],
            ["gpt-5.6-sol"],
        )

    def test_frontend_initialization_does_not_refresh_models_implicitly(self):
        source = (Path(__file__).parent / "web/app.js").read_text()
        initialize = source[source.index("async function initialize()") :]

        self.assertNotIn("refreshModels(", initialize)

    def test_catalog_disables_announcements_for_official_and_custom_models(self):
        bundled = [
            {
                "slug": "official-model",
                "display_name": "Official model",
                "description": "Official description",
                "visibility": "list",
                "availability_nux": {"message": "Try the official model"},
                "upgrade": {"model": "official-next"},
            }
        ]

        with patch.object(self.manager, "_bundled_catalog", return_value=bundled):
            catalog = self.manager._build_catalog(["official-model", "custom-model"])

        self.assertEqual(
            [model["slug"] for model in catalog["models"]],
            ["official-model", "custom-model"],
        )
        self.assertTrue(all(model["availability_nux"] is None for model in catalog["models"]))
        self.assertTrue(all(model["upgrade"] is None for model in catalog["models"]))

    def test_sync_replaces_removed_models_instead_of_accumulating_stale_entries(self):
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("MaoLocal")
            ModelHandler.models = ["vendor-next"]
            self.manager.sync_active()
        catalog = json.loads(self.paths.catalog.read_text())
        self.assertEqual([model["slug"] for model in catalog["models"]], ["vendor-next"])

    def test_switching_back_to_local_merges_official_models_and_deduplicates(self):
        self.save_account()
        store = json.loads(self.paths.accounts.read_text())
        store["accounts"]["MaoLocal"]["model_ids"] = ["local-model"]
        store["accounts"]["MaoLocal"]["catalog_model_ids"] = ["shared-model", "local-model"]
        self.paths.accounts.write_text(json.dumps(store))
        bundled = [
            {"slug": "official-model", "display_name": "Official", "visibility": "list"},
            {"slug": "shared-model", "display_name": "Shared", "visibility": "list"},
        ]

        with patch.object(self.manager, "_bundled_catalog", return_value=bundled):
            result = self.manager.activate_account("MaoLocal")

        catalog = json.loads(self.paths.catalog.read_text())
        model_ids = [model["slug"] for model in catalog["models"]]
        self.assertEqual(model_ids, ["official-model", "shared-model", "local-model"])
        self.assertEqual(len(model_ids), len(set(model_ids)))
        self.assertEqual(
            {model["slug"]: model["visibility"] for model in catalog["models"]},
            {"official-model": "list", "shared-model": "list", "local-model": "list"},
        )
        self.assertEqual(result["models"], 3)

    def test_restore_official_model_catalog_replaces_local_catalog(self):
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("MaoLocal")
        expected = [
            "gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra",
            "gpt-6-astra", "gpt-6-luna", "gpt-6-sol",
        ]
        bundled = [
            {"slug": "gpt-5.5", "display_name": "GPT-5.5", "visibility": "list"},
            {"slug": "gpt-5.6-cyber", "display_name": "Cyber", "visibility": "list"},
        ]
        for current, default in [("gpt-6-astra", "gpt-6-astra"), ("gpt-5.5", "gpt-5.6-luna")]:
            with self.subTest(current=current):
                config_text = self.manager._rewrite_top_level(
                    self.paths.config.read_text(), {"model": current}
                )
                self.paths.config.write_text(config_text)
                with patch.object(self.manager, "_bundled_catalog", return_value=bundled):
                    result = self.manager.restore_official_model_catalog()
                catalog = json.loads(self.paths.catalog.read_text())["models"]
                self.assertEqual([model["slug"] for model in catalog], expected)
                self.assertTrue(all(model["visibility"] == "list" for model in catalog))
                account = json.loads(self.paths.accounts.read_text())["accounts"]["MaoLocal"]
                self.assertEqual(account["model_ids"], expected)
                self.assertEqual(account["catalog_model_ids"], expected)
                self.assertEqual(account["default_model"], default)
                self.assertEqual(tomllib.loads(self.paths.config.read_text())["model"], default)
                self.assertEqual(result["models"], 6)
                for model in catalog[-2:]:
                    self.assertEqual(model["context_window"], 1050000)
                    self.assertNotIn("ultra", [v["effort"] for v in model["supported_reasoning_levels"]])

    def test_preview_models_does_not_change_catalog(self):
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("MaoLocal")
        before = self.paths.catalog.read_bytes()
        ModelHandler.models = ["gpt-5.6-sol", "vendor-next"]

        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            result = self.manager.preview_active_models()

        self.assertEqual(result["model_ids"], ModelHandler.models)
        self.assertEqual(result["selected_model_ids"], ["gpt-5.6-sol"])
        self.assertEqual(self.paths.catalog.read_bytes(), before)
        self.assertEqual(json.loads(self.paths.sync_state.read_text())["status"], "ok")

    def test_sync_writes_all_remote_models_and_hides_unselected_models(self):
        self.save_account()
        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("MaoLocal")
            result = self.manager.sync_active(["vendor-coder"])

        catalog = json.loads(self.paths.catalog.read_text())
        self.assertEqual(result["models"], 2)
        self.assertEqual(result["visible_models"], 1)
        self.assertEqual([model["slug"] for model in catalog["models"]], ModelHandler.models)
        self.assertEqual(
            {model["slug"]: model["visibility"] for model in catalog["models"]},
            {"gpt-5.6-sol": "hide", "vendor-coder": "list"},
        )
        self.assertEqual(
            {model["slug"]: model["visibility"] for model in self.manager.state()["models"]},
            {"gpt-5.6-sol": "hide", "vendor-coder": "list"},
        )
        store = json.loads(self.paths.accounts.read_text())
        self.assertEqual(store["accounts"]["MaoLocal"]["model_ids"], ["vendor-coder"])
        self.assertEqual(
            store["accounts"]["MaoLocal"]["catalog_model_ids"],
            ModelHandler.models,
        )
        with self.assertRaisesRegex(ValueError, "不在当前账号目录"):
            self.manager.switch_model("gpt-5.6-sol")

        with patch.object(self.manager, "_bundled_catalog", return_value=[]):
            self.manager.activate_account("MaoLocal")
        catalog = json.loads(self.paths.catalog.read_text())
        self.assertEqual(
            {model["slug"]: model["visibility"] for model in catalog["models"]},
            {"gpt-5.6-sol": "hide", "vendor-coder": "list"},
        )

    def test_sync_rejects_empty_or_unknown_selection_without_changing_catalog(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        before = self.paths.catalog.read_bytes()

        with self.assertRaisesRegex(ValueError, "至少选择一个"):
            self.manager.sync_active([])
        self.assertEqual(self.paths.catalog.read_bytes(), before)

        with self.assertRaisesRegex(ValueError, "渠道当前不存在"):
            self.manager.sync_active(["missing-model"])
        self.assertEqual(self.paths.catalog.read_bytes(), before)

    def test_failed_sync_preserves_previous_catalog(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        before = self.paths.catalog.read_bytes()
        with patch.object(self.manager, "_fetch_model_ids", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                self.manager.sync_active()
        self.assertEqual(self.paths.catalog.read_bytes(), before)
        self.assertEqual(json.loads(self.paths.sync_state.read_text())["status"], "error")

    def test_switch_model_rejects_models_outside_current_catalog(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        self.manager.sync_active()
        with self.assertRaisesRegex(ValueError, "不在当前账号目录"):
            self.manager.switch_model("missing-model")
        self.manager.switch_model("vendor-coder")
        self.assertEqual(self.manager.state()["current"]["model"], "vendor-coder")
