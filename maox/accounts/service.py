from __future__ import annotations

from maox.shared.common import *
from maox.shared.common import _now
from maox.accounts.config_import import connection_url, validate_provider_config
from maox.accounts.provider_switch import replace_provider, validate_file_credentials


class AccountsMixin:
    @staticmethod
    def _normalize_account_fields(payload: dict[str, Any]) -> dict[str, str]:
        name = str(payload.get("name", "")).strip()
        original_name = str(payload.get("original_name", "")).strip()
        provider_id = CUSTOM_PROVIDER_ID
        base_url = str(payload.get("base_url", "")).strip().rstrip("/")
        wire_api = str(payload.get("wire_api", "responses")).strip()
        default_model = str(payload.get("default_model", "")).strip()
        reasoning_effort = str(payload.get("reasoning_effort", "high")).strip()
        api_key = str(payload.get("api_key", "")).strip()
        connection_type = str(payload.get("connection_type", "openai_compatible")).strip()
        auth_mode = str(payload.get("auth_mode", "legacy")).strip()
        transport = str(payload.get("transport", "http_sse")).strip()

        if not name:
            raise ValueError("账号名称不能为空")
        base_url = connection_url(base_url, "Base URL")
        if wire_api != "responses":
            raise ValueError("当前只支持 Codex Responses 协议")
        if reasoning_effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
            raise ValueError("推理强度无效")
        if connection_type not in {"openai_compatible", "sub2api"}:
            raise ValueError("连接类型无效")
        if auth_mode not in {"legacy", "api_key"}:
            raise ValueError("Codex 鉴权模式无效")
        if transport not in {"http_sse", "websocket"}:
            raise ValueError("传输模式无效")
        if connection_type != "sub2api" and (auth_mode != "legacy" or transport != "http_sse"):
            raise ValueError("鉴权与传输模式仅适用于 Sub2API 连接")
        return {
            "name": name,
            "original_name": original_name,
            "provider_id": provider_id,
            "base_url": base_url,
            "wire_api": wire_api,
            "default_model": default_model,
            "reasoning_effort": reasoning_effort,
            "api_key": api_key,
            "connection_type": connection_type,
            "auth_mode": auth_mode,
            "transport": transport,
        }

    @staticmethod
    def _provider_config_for_fields(
        fields: dict[str, str],
        existing: dict[str, Any] | None = None,
        *,
        was_sub2api: bool = False,
    ) -> dict[str, Any]:
        provider = dict(existing or {})
        provider.update(
            {
                "name": CUSTOM_PROVIDER_ID,
                "base_url": fields["base_url"],
                "wire_api": fields["wire_api"],
            }
        )
        provider.pop("experimental_bearer_token", None)
        provider.pop("supports_websockets", None)
        if fields["connection_type"] == "sub2api":
            provider["requires_openai_auth"] = fields["auth_mode"] == "legacy"
        else:
            provider.setdefault("requires_openai_auth", True)
        if fields["connection_type"] != "sub2api":
            if was_sub2api:
                headers = provider.get("http_headers", {})
                headers = dict(headers) if isinstance(headers, dict) else {}
                headers.pop("x-openai-actor-authorization", None)
                if headers:
                    provider["http_headers"] = headers
                else:
                    provider.pop("http_headers", None)
            return provider

        headers = provider.get("http_headers", {})
        headers = dict(headers) if isinstance(headers, dict) else {}
        actor_header = "x-openai-actor-authorization"
        if fields["auth_mode"] == "api_key":
            headers[actor_header] = "local-image-extension"
        else:
            headers.pop(actor_header, None)
        if headers:
            provider["http_headers"] = headers
        else:
            provider.pop("http_headers", None)
        return provider

    def _account_connection(self, payload, fields, existing):
        # A pasted configuration replaces the connection, a normal edit preserves hidden fields.
        source = (validate_provider_config(payload["provider_config"])
                  if "provider_config" in payload else dict(existing.get("provider_config", {})))
        if "model_catalog_url" in payload:
            catalog = payload["model_catalog_url"]
            if catalog:
                source["model_catalog_url"] = connection_url(catalog, "模型目录地址")
            else:
                source.pop("model_catalog_url", None)
        if "requires_openai_auth" in payload:
            if not isinstance(payload["requires_openai_auth"], bool):
                raise ValueError("鉴权设置必须为 true 或 false")
            source["requires_openai_auth"] = payload["requires_openai_auth"]
        discovery = payload.get("api_key_model_discovery", existing.get("api_key_model_discovery", bool(source.get("model_catalog_url"))))
        if not isinstance(discovery, bool):
            raise ValueError("自动发现模型必须为 true 或 false")
        return self._provider_config_for_fields(
            fields, source,
            was_sub2api=self._connection_type(existing) == "sub2api",
        ), discovery

    def save_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields = self._normalize_account_fields(payload)
        name = fields["name"]
        original_name = fields["original_name"]
        provider_id = fields["provider_id"]
        default_model = fields["default_model"]
        reasoning_effort = fields["reasoning_effort"]
        api_key = fields["api_key"]
        connection_type = fields["connection_type"]
        auth_mode = fields["auth_mode"]
        transport = fields["transport"]

        store = self._load_store()
        accounts = store["accounts"]
        if not original_name and name in accounts:
            raise ValueError(f"账号已存在：{name}，请编辑现有账号或更换名称")
        if original_name and original_name not in accounts:
            raise ValueError("原账号不存在，请刷新后重试")
        existing = accounts.get(original_name, {})
        if existing and self._account_type(existing) == "official":
            raise ValueError("官方账号请使用官方授权入口")
        provider_id = str(existing.get("provider_id") or provider_id)
        provider_config, discovery = self._account_connection(payload, fields, existing)
        if not api_key:
            api_key = str(existing.get("api_key", ""))
        if not api_key:
            raise ValueError("API Key 不能为空")
        if original_name and original_name != name:
            if name in accounts:
                raise ValueError(f"账号已存在：{name}")
            del accounts[original_name]
            if store.get("active_account") == original_name:
                store["active_account"] = name
                pending = store.get("pending_history_claim")
                if isinstance(pending, dict) and pending.get("account") == original_name:
                    pending["account"] = name

        created_at = str(existing.get("created_at", "")) or _now()
        accounts[name] = {
            "account_type": "custom",
            "connection_type": connection_type,
            "auth_mode": auth_mode,
            "transport": transport,
            "provider_id": provider_id,
            "provider_config": provider_config,
            "api_key": api_key,
            "default_model": default_model,
            "reasoning_effort": reasoning_effort,
            "api_key_model_discovery": discovery,
            "created_at": created_at,
            "updated_at": _now(),
        }
        if store.get("active_account") == name:
            accounts[name]["applied_account"] = copy.deepcopy(existing.get("applied_account", existing))
            accounts[name]["pending_apply"] = True
        self._save_store(store)
        return self._public_account(name, accounts[name], store.get("active_account") == name)

    def _verification_account(self, payload: dict[str, Any]):
        fields = self._normalize_account_fields(payload)
        original_name = fields["original_name"]
        api_key = fields["api_key"]
        existing = {}
        if original_name:
            store = self._load_store()
            existing = store["accounts"].get(original_name, {})
            if not api_key:
                api_key = str(existing.get("api_key", "")).strip() if isinstance(existing, dict) else ""
        if not api_key:
            raise ValueError("API Key 不能为空")

        provider_config, _discovery = self._account_connection(payload, fields, existing)
        account = {
            "provider_id": fields["provider_id"],
            "provider_config": provider_config,
            "api_key": api_key,
        }
        return fields, account

    def verify_connection(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields, account = self._verification_account(payload)
        if not fields["default_model"]:
            raise ValueError("请先填写用于验证连接的模型")
        return self._test_model_response(account, fields["default_model"])

    def verify_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """读取模型列表，不保存或切换账号。"""
        fields, account = self._verification_account(payload)
        discovered = self._discover_models(account)
        model_ids = discovered["model_ids"]
        return {
            "account": fields["name"],
            "models": len(model_ids),
            "model_ids": model_ids,
            "endpoint": discovered["endpoint"],
            "connection_type": fields["connection_type"],
            "auth_mode": fields["auth_mode"],
            "transport": fields["transport"],
        }

    def delete_account(self, name: str) -> None:
        store = self._load_store()
        name = name.strip()
        if name not in store["accounts"]:
            raise KeyError(f"账号不存在：{name}")
        if store.get("active_account") == name:
            store["active_account"] = ""
            store["unmanaged_current_account"] = True
            store.pop("pending_history_claim", None)
        del store["accounts"][name]
        self._save_store(store)

    def activate_account(self, name: str) -> dict[str, Any]:
        store = self._load_store()
        self._capture_active_official_auth(store)
        account = store["accounts"].get(name)
        if not isinstance(account, dict):
            raise KeyError(f"账号不存在：{name}")

        store["pending_history_claim"] = {"account": name, "status": "pending"}
        if self._account_type(account) == "official":
            result = self._activate_official_account(
                store, name, account,
            )
            result["history"] = self._apply_pending_history_claim()
            return result

        config_text = self._read_text(self.paths.config)
        config = tomllib.loads(config_text)
        selected_model = str(config.get("model", "")).strip()
        selected_provider = str(config.get("model_provider", ""))
        custom_selected = bool(selected_provider and selected_provider != OFFICIAL_PROVIDER_ID)
        provider_id = selected_provider if custom_selected else CUSTOM_PROVIDER_ID
        providers = config.get("model_providers", {})
        existing_provider = providers.get(provider_id) if isinstance(providers, dict) else None
        preserve_provider = custom_selected and isinstance(existing_provider, dict)
        discovery = account.get("api_key_model_discovery", bool(account["provider_config"].get("model_catalog_url")))
        if preserve_provider:
            applied_provider = copy.deepcopy(existing_provider)
            # Only the two endpoint values come from the selected account.
            applied_provider["base_url"] = account["provider_config"]["base_url"]
            if discovery and account["provider_config"].get("model_catalog_url"):
                applied_provider["model_catalog_url"] = account["provider_config"]["model_catalog_url"]
            else:
                applied_provider.pop("model_catalog_url", None)
            new_config = config_text
        else:
            # Official/empty configuration needs a separate compatible entry.
            applied_provider = dict(account["provider_config"])
            applied_provider["name"] = provider_id
            if not discovery:
                applied_provider.pop("model_catalog_url", None)
            new_config = self._rewrite_top_level(config_text, {
                "model_provider": provider_id,
                "cli_auth_credentials_store": "file",
            })
        new_config = self._without_managed_catalog(new_config)
        validate_file_credentials(tomllib.loads(new_config), applied_provider)
        new_config = replace_provider(new_config, provider_id, applied_provider, self._toml_value)
        features = {"api_key_model_discovery": discovery}
        if not preserve_provider:
            features["responses_websockets_v2"] = self._connection_type(account) == "sub2api" and account.get("transport") == "websocket"
        new_config = self._apply_account_features(new_config, store, features)
        account["provider_id"] = provider_id
        tomllib.loads(new_config)
        auth_text = json.dumps({"OPENAI_API_KEY": account["api_key"]}, ensure_ascii=False, indent=2)

        store["active_account"] = name
        store.pop("unmanaged_current_account", None)
        account.pop("pending_apply", None)
        account.pop("applied_account", None)
        self._mark_restart_required(store)
        account["updated_at"] = _now()
        self._backup_many(self.paths.config, self.paths.auth)
        self._commit_account_switch(
            store,
            [
                (self.paths.config, new_config),
                (self.paths.auth, auth_text + "\n"),
            ],
        )
        return {
            "account": name,
            "model": selected_model,
            "history": self._apply_pending_history_claim(),
        }

    def _load_store(self) -> dict[str, Any]:
        if not self.paths.accounts.exists():
            store = self._seed_from_codex()
            self._save_store(store)
            return store
        raw = self._read_json(self.paths.accounts, {})
        if raw.get("version") == STORE_VERSION and isinstance(raw.get("accounts"), dict):
            raw.setdefault("active_account", "")
            reconciled = self._reconcile_active_account(raw)
            changed = self._remove_legacy_provider_fields(raw)
            if reconciled or changed:
                self._save_store(raw)
            return raw
        self._backup_many(self.paths.accounts)
        migrated = self._migrate_store(raw)
        self._save_store(migrated)
        return migrated

    @staticmethod
    def _remove_legacy_provider_fields(store: dict[str, Any]) -> bool:
        changed = False
        accounts = store.get("accounts", {})
        if not isinstance(accounts, dict):
            return False
        for account in accounts.values():
            if not isinstance(account, dict):
                continue
            provider = account.get("provider_config")
            if isinstance(provider, dict) and "supports_websockets" in provider:
                provider.pop("supports_websockets", None)
                changed = True
        return changed

    def _reconcile_active_account(self, store: dict[str, Any]) -> bool:
        """以 Codex 当前配置为真值，修复管理器账号库里的活动标记漂移。"""
        if store.get("unmanaged_current_account"):
            return False
        config = self._read_toml(self.paths.config)
        provider_id = str(config.get("model_provider", ""))
        if provider_id == OFFICIAL_PROVIDER_ID:
            active = store["accounts"].get(str(store.get("active_account", "")))
            if isinstance(active, dict) and self._account_type(active) == "official":
                return False
            official_names = [
                name
                for name, account in store["accounts"].items()
                if isinstance(account, dict) and self._account_type(account) == "official"
            ]
            if len(official_names) == 1:
                store["active_account"] = official_names[0]
                return True
            return False
        providers = config.get("model_providers", {})
        provider = providers.get(provider_id, {}) if isinstance(providers, dict) else {}
        if not provider_id or not isinstance(provider, dict) or not provider.get("base_url"):
            return False

        current_url = str(provider.get("base_url", "")).rstrip("/")
        current_key = self._auth_api_key(self._read_text(self.paths.auth))
        accounts = store["accounts"]
        active_name = store.get("active_account", "")
        names = ([active_name] if active_name in accounts else []) + [name for name in accounts if name != active_name]
        for name in names:
            account = accounts[name]
            if not isinstance(account, dict) or self._account_type(account) != "custom":
                continue
            applied = account.get("applied_account", account)
            saved_provider = applied.get("provider_config", {})
            saved_url = str(saved_provider.get("base_url", "")).rstrip("/")
            if (str(applied.get("provider_id", "")) == provider_id
                    and saved_url == current_url and current_key
                    and applied.get("api_key") == current_key):
                if active_name != name:
                    store["active_account"] = name
                    return True
                return False
        # External edits are visible as unmanaged configuration, not new accounts on every poll.
        if active_name:
            store["active_account"] = ""
            return True
        return False

    def _migrate_store(self, raw: dict[str, Any]) -> dict[str, Any]:
        if raw.get("version") in {6, 7} and isinstance(raw.get("accounts"), dict):
            migrated = copy.deepcopy(raw)
            migrated["version"] = STORE_VERSION
            for account in migrated["accounts"].values():
                if isinstance(account, dict):
                    account.setdefault("account_type", "custom")
                    if self._account_type(account) == "official":
                        account["connection_type"] = "official"
                    else:
                        account.setdefault("connection_type", "openai_compatible")
                        account.setdefault("auth_mode", "legacy")
                        account.setdefault("transport", "http_sse")
            self._remove_legacy_provider_fields(migrated)
            return migrated
        migrated: dict[str, Any] = {"version": STORE_VERSION, "active_account": "", "accounts": {}}
        accounts = raw.get("accounts", {})
        if not isinstance(accounts, dict):
            return migrated
        for name, legacy in accounts.items():
            if not isinstance(legacy, dict):
                continue
            try:
                top = tomllib.loads(str(legacy.get("config_top", "")))
                provider_id, provider_config = self._parse_provider_block(
                    str(legacy.get("provider_block", ""))
                )
            except Exception:
                continue
            api_key = self._auth_api_key(str(legacy.get("auth_text", "")))
            old_token = str(provider_config.pop("experimental_bearer_token", ""))
            provider_config.pop("supports_websockets", None)
            provider_config["requires_openai_auth"] = True
            if not api_key:
                api_key = old_token
            migrated["accounts"][name] = {
                "account_type": "custom",
                "connection_type": "openai_compatible",
                "auth_mode": "legacy",
                "transport": "http_sse",
                "provider_id": provider_id,
                "provider_config": provider_config,
                "api_key": api_key,
                "default_model": str(top.get("model", "")),
                "reasoning_effort": str(top.get("model_reasoning_effort", "high")),
                "created_at": str(legacy.get("updated_at", "")) or _now(),
                "updated_at": _now(),
            }
            if legacy.get("active"):
                migrated["active_account"] = name
        return migrated

    def _seed_from_codex(self) -> dict[str, Any]:
        store: dict[str, Any] = {"version": STORE_VERSION, "active_account": "", "accounts": {}}
        config_text = self._read_text(self.paths.config)
        if not config_text:
            return store
        config = self._read_toml(self.paths.config)
        provider_id = str(config.get("model_provider", ""))
        providers = config.get("model_providers", {})
        provider_config = providers.get(provider_id, {}) if isinstance(providers, dict) else {}
        if not provider_id or not isinstance(provider_config, dict) or not provider_config.get("base_url"):
            return store
        name = str(provider_config.get("name", "")) or provider_id
        store["active_account"] = name
        provider_config = dict(provider_config)
        provider_config.pop("supports_websockets", None)
        store["accounts"][name] = {
            "account_type": "custom",
            "connection_type": "openai_compatible",
            "auth_mode": "legacy",
            "transport": "http_sse",
            "provider_id": provider_id,
            "provider_config": provider_config,
            "api_key": self._auth_api_key(self._read_text(self.paths.auth)),
            "default_model": str(config.get("model", "")),
            "reasoning_effort": str(config.get("model_reasoning_effort", "high")),
            "api_key_model_discovery": bool(config.get("features", {}).get("api_key_model_discovery", bool(provider_config.get("model_catalog_url")))),
            "created_at": _now(),
            "updated_at": _now(),
        }
        return store

    @staticmethod
    def _account_type(account: dict[str, Any]) -> str:
        return "official" if account.get("account_type") == "official" else "custom"

    @classmethod
    def _connection_type(cls, account: dict[str, Any]) -> str:
        if cls._account_type(account) == "official":
            return "official"
        return "sub2api" if account.get("connection_type") == "sub2api" else "openai_compatible"
