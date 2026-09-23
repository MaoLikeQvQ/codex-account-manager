from test_support import *


class AccountManagerTests(AccountManagerTestBase):
    def test_image_config_drops_chat_model_and_uses_image_endpoints(self):
        original = 'model = "codex-selected-model"\nmodel_provider = "existing"\n'
        self.paths.config.write_text(original)
        self.paths.image_config.write_text(json.dumps({
            "mode": "responses", "mainModel": "stale-model", "apiKey": "image-secret"
        }))
        self.manager.configure_image_generation({
            "source": "separate", "base_url": "https://images.example/v1",
            "mode": "responses", "main_model": "ignored-model",
            "image_model": "gpt-image-2-2k",
        })
        config = json.loads(self.paths.image_config.read_text())
        self.assertEqual(config["mode"], "images")
        self.assertEqual(config["imageModel"], "gpt-image-2-2k")
        self.assertEqual(config["apiKey"], "image-secret")
        self.assertNotIn("mainModel", config)
        self.assertEqual(self.paths.config.read_text(), original)

    def test_configure_then_apply_image_generation_installs_versioned_plugin(self):
        self.paths.config.write_text('[features]\ngoals = true\n')

        result = self.manager.configure_image_generation(
            {
                "enabled": True,
                "source": "separate",
                "base_url": "https://api.openai.com/v1",
                "api_key": "image-secret",
                "mode": "images",
                "image_model": "gpt-image-2",
            }
        )

        self.assertFalse(result["installed"])
        self.assertTrue(result["pending_apply"])
        image_config = json.loads(self.paths.image_config.read_text())
        self.assertEqual(image_config["apiKey"], "image-secret")
        self.assertEqual(self.paths.image_config.stat().st_mode & 0o777, 0o600)
        config_text = self.paths.config.read_text()
        self.assertNotIn("image-secret", config_text)
        self.assertTrue(tomllib.loads(config_text)["features"]["goals"])
        self.assertNotIn("maolocal-imagegen", tomllib.loads(config_text).get("mcp_servers", {}))

        applied = self.manager.apply_image_generation()

        self.assertTrue(applied["installed"])
        self.assertFalse(applied["pending_apply"])
        self.assertEqual(applied["plugin_action"], "installed")
        self.assertEqual(applied["installed_version"], applied["bundled_version"])
        config = tomllib.loads(self.paths.config.read_text())
        self.assertEqual(
            config["mcp_servers"]["maolocal-imagegen"]["env"]["CUSTOM_IMAGEGEN_CONFIG"],
            str(self.paths.image_config),
        )
        self.assertEqual(
            config["mcp_servers"]["maolocal-imagegen"]["args"],
            [str(self.paths.image_server)],
        )
        self.assertTrue(self.paths.image_server.is_file())
        self.assertTrue(self.paths.image_skill.is_file())
        self.assertNotIn("image-secret", json.dumps(self.manager.state()))

        current = self.manager.apply_image_generation()
        self.assertEqual(current["plugin_action"], "current")

        self.paths.image_plugin_version.write_text("0.1.0\n")
        updated = self.manager.apply_image_generation()
        self.assertEqual(updated["plugin_action"], "updated")
        self.assertEqual(updated["installed_version"], updated["bundled_version"])

    def test_official_account_can_be_selected_without_copying_oauth_to_image_config(self):
        store = {
            "version": 8,
            "active_account": "Official",
            "accounts": {
                "Official": {
                    "account_type": "official",
                    "connection_type": "official",
                    "provider_id": "openai",
                    "official_auth": {"auth_mode": "chatgpt", "tokens": {"access_token": "token"}},
                    "default_model": "gpt-5.6-sol",
                }
            },
        }
        self.paths.accounts.write_text(json.dumps(store))

        store["accounts"]["Official"]["official_auth"]["tokens"]["account_id"] = "account-1"
        self.paths.accounts.write_text(json.dumps(store))

        with self.assertRaisesRegex(ValueError, "不能用于公开图片 API"):
            self.manager.configure_image_generation(
                {
                    "enabled": True,
                    "source": "managed_account",
                    "account_name": "Official",
                    "mode": "responses",
                    "image_model": "gpt-image-2",
                }
            )

    def test_managed_custom_account_is_fixed_by_name(self):
        self.save_account("Image Pool", "image_pool")

        result = self.manager.configure_image_generation(
            {
                "enabled": True,
                "source": "managed_account",
                "account_name": "Image Pool",
                "mode": "images",
                "image_model": "gpt-image-2",
            }
        )

        self.assertEqual(result["account_name"], "Image Pool")
        image_config = json.loads(self.paths.image_config.read_text())
        self.assertEqual(image_config["accountName"], "Image Pool")
        self.assertNotIn("apiKey", image_config)
        self.assertNotIn("secret-key", self.paths.image_config.read_text())

    def test_image_mcp_resolves_managed_official_account_without_network_request(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable")
        token = "e30.eyJleHAiOjQxMDI0NDQ4MDB9.signature"
        store = {
            "version": 8,
            "accounts": {
                "Official": {
                    "account_type": "official",
                    "default_model": "gpt-5.6-sol",
                    "official_auth": {
                        "tokens": {"access_token": token, "account_id": "account-1"}
                    },
                }
            },
        }
        self.paths.accounts.write_text(json.dumps(store))
        self.paths.image_config.write_text(
            json.dumps(
                {
                    "credentialSource": "managed_account",
                    "provider": "official",
                    "accountStorePath": str(self.paths.accounts),
                    "accountName": "Official",
                    "mode": "responses",
                    "imageModel": "gpt-image-2",
                    "mainModel": "gpt-5.6-sol",
                }
            )
        )
        requests = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    }
                ),
                json.dumps(
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "imagegen_status", "arguments": {}},
                    }
                ),
            ]
        ) + "\n"
        server = Path(__file__).resolve().parent / "imagegen_plugin" / "server.cjs"

        completed = subprocess.run(
            [node, str(server)],
            input=requests,
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "CUSTOM_IMAGEGEN_CONFIG": str(self.paths.image_config)},
            check=True,
        )

        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        result = next(item["result"] for item in responses if item.get("id") == 2)
        detail = json.loads(result["content"][0]["text"])
        self.assertEqual(detail["provider"], "official")
        self.assertEqual(detail["accountName"], "Official")
        self.assertNotIn(token, completed.stdout)

    def test_image_mcp_sends_official_responses_request_and_parses_sse(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable")
        token = "e30.eyJleHAiOjQxMDI0NDQ4MDB9.signature"
        store = {
            "version": 8,
            "accounts": {
                "Official": {
                    "account_type": "official",
                    "default_model": "gpt-5.6-sol",
                    "official_auth": {
                        "tokens": {"access_token": token, "account_id": "account-1"}
                    },
                }
            },
        }
        self.paths.accounts.write_text(json.dumps(store))
        output_dir = self.paths.image_config.parent / "generated-images"
        self.paths.image_config.write_text(
            json.dumps(
                {
                    "credentialSource": "managed_account",
                    "provider": "official",
                    "accountStorePath": str(self.paths.accounts),
                    "accountName": "Official",
                    "mode": "responses",
                    "imageModel": "gpt-image-2",
                    "mainModel": "gpt-5.6-sol",
                    "outputDir": str(output_dir),
                }
            )
        )
        image_server = ThreadingHTTPServer(("127.0.0.1", 0), ImageSseHandler)
        image_thread = threading.Thread(target=image_server.serve_forever, daemon=True)
        image_thread.start()
        self.addCleanup(image_thread.join, 2)
        self.addCleanup(image_server.server_close)
        self.addCleanup(image_server.shutdown)
        requests = "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"},
                        },
                    }
                ),
                json.dumps(
                    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "generate_image",
                            "arguments": {"prompt": "a red square"},
                        },
                    }
                ),
            ]
        ) + "\n"
        server = Path(__file__).resolve().parent / "imagegen_plugin" / "server.cjs"
        endpoint = f"http://127.0.0.1:{image_server.server_address[1]}"

        completed = subprocess.run(
            [node, str(server)],
            input=requests,
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **os.environ,
                "CUSTOM_IMAGEGEN_CONFIG": str(self.paths.image_config),
                "NODE_ENV": "test",
                "IMAGE_OFFICIAL_BASE_URL": endpoint,
            },
            check=True,
        )

        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        result = next(item["result"] for item in responses if item.get("id") == 2)
        self.assertFalse(result.get("isError", False), result)
        detail = json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))
        self.assertTrue(Path(detail["savedPath"]).is_file())
        self.assertEqual(ImageSseHandler.authorization, f"Bearer {token}")
        self.assertEqual(ImageSseHandler.account_id, "account-1")
        self.assertEqual(ImageSseHandler.request_body["model"], "gpt-5.6-sol")
        self.assertTrue(ImageSseHandler.request_body["stream"])
        self.assertEqual(ImageSseHandler.request_body["tool_choice"], "required")
        self.assertEqual(ImageSseHandler.request_body["tools"][0]["type"], "image_generation")
