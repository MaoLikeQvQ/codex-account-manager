from __future__ import annotations

from .common import *
from .common import _now


class AccountsMixin:
    @staticmethod
    def _normalize_account_fields(payload: dict[str, Any]) -> dict[str, str]:
        name = str(payload.get("name", "")).strip()
        original_name = str(payload.get("original_name", "")).strip()
        provider_id = str(payload.get("provider_id", "")).strip()
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
        if not re.fullmatch(r"[A-Za-z0-9_-]+", provider_id):
            raise ValueError("Provider ID 只能包含字母、数字、下划线和短横线")
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("Base URL 必须是有效的 http 或 https 地址")
        if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise ValueError("Base URL 不能包含账号密码、查询参数或片段")
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
        provider_name: str,
        existing: dict[str, Any] | None = None,
        *,
        was_sub2api: bool = False,
    ) -> dict[str, Any]:
        provider = dict(existing or {})
        provider.update(
            {
                "name": provider_name or fields["name"],
                "base_url": fields["base_url"],
                "wire_api": fields["wire_api"],
                "requires_openai_auth": (
                    fields["connection_type"] != "sub2api"
                    or fields["auth_mode"] == "legacy"
                ),
            }
        )
        provider.pop("experimental_bearer_token", None)
        provider.pop("supports_websockets", None)
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
        existing = accounts.get(original_name or name, {})
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

        provider_config = self._provider_config_for_fields(
            fields,
            str(payload.get("provider_name", "")).strip() or name,
            existing.get("provider_config", {}),
            was_sub2api=self._connection_type(existing) == "sub2api",
        )
        created_at = str(existing.get("created_at", "")) or _now()
        accounts[name] = {
            "account_type": "custom",
            "connection_type": connection_type,
            "auth_mode": auth_mode,
            "transport": transport,
            "provider_id": provider_id,
            "provider_config": provider_config,
            "api_key": api_key,
            "model_ids": self._normalized_model_ids(existing.get("model_ids", [])),
            "catalog_model_ids": self._normalized_model_ids(
                existing.get("catalog_model_ids", existing.get("model_ids", []))
            ),
            "default_model": default_model,
            "reasoning_effort": reasoning_effort,
            "created_at": created_at,
            "updated_at": _now(),
        }
        self._save_store(store)
        return self._public_account(name, accounts[name], store.get("active_account") == name)

    def verify_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """只校验当前填写信息能否访问渠道，不落库、不切换账号。"""
        fields = self._normalize_account_fields(payload)
        name = fields["name"]
        original_name = fields["original_name"]
        api_key = fields["api_key"]
        if not api_key and original_name:
            store = self._load_store()
            existing = store["accounts"].get(original_name, {})
            api_key = str(existing.get("api_key", "")).strip() if isinstance(existing, dict) else ""
        if not api_key:
            raise ValueError("API Key 不能为空")

        provider_config = self._provider_config_for_fields(
            fields,
            str(payload.get("provider_name", "")).strip() or name,
        )
        account = {
            "provider_id": fields["provider_id"],
            "provider_config": provider_config,
            "api_key": api_key,
        }
        model_ids = self._fetch_model_ids(account)
        return {
            "account": name,
            "models": len(model_ids),
            "model_ids": model_ids,
            "endpoint": self._models_endpoint(account),
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
        del store["accounts"][name]
        self._save_store(store)

    def activate_account(self, name: str) -> dict[str, Any]:
        store = self._load_store()
        self._capture_active_official_auth(store)
        account = store["accounts"].get(name)
        if not isinstance(account, dict):
            raise KeyError(f"账号不存在：{name}")

        if self._account_type(account) == "official":
            return self._activate_official_account(store, name, account)

        selected_model_ids = self._normalized_model_ids(account.get("model_ids", []))
        local_model_ids = self._normalized_model_ids(
            account.get("catalog_model_ids", selected_model_ids)
        )
        model_ids = self._merge_official_model_ids(local_model_ids)
        selected_model_ids = self._merge_official_model_ids(selected_model_ids)
        models_source = "account_cache"
        if not local_model_ids:
            existing_catalog = self._read_catalog_models()
            local_model_ids = self._normalized_model_ids(
                [item.get("slug") for item in existing_catalog]
            )
            model_ids = self._merge_official_model_ids(local_model_ids)
            selected_model_ids = self._merge_official_model_ids(
                [
                    item.get("slug")
                    for item in existing_catalog
                    if item.get("visibility", "list") != "hide"
                ]
            )
            models_source = "existing_catalog"
        if not model_ids:
            default_model = str(account.get("default_model", "")).strip()
            if not default_model:
                raise ValueError("账号没有可用模型，请先验证账号并选择默认模型")
            model_ids = [default_model]
            selected_model_ids = model_ids
            models_source = "default_model"
        selected_model_ids = self._merge_official_model_ids(selected_model_ids)
        if not account.get("catalog_model_ids"):
            account["model_ids"] = model_ids
            account["catalog_model_ids"] = model_ids
        selected_model_ids = [slug for slug in selected_model_ids if slug in model_ids]
        if not selected_model_ids:
            selected_model_ids = model_ids
            account["model_ids"] = selected_model_ids
        catalog = self._build_catalog(model_ids, selected_model_ids)
        selected_model = str(account.get("default_model", "")).strip()
        if selected_model not in selected_model_ids:
            selected_model = selected_model_ids[0]
            account["default_model"] = selected_model

        config_text = self._read_text(self.paths.config)
        provider_id = str(account["provider_id"])
        updates = {
            "model": selected_model,
            "model_provider": provider_id,
            "model_catalog_json": str(self.paths.catalog),
            "model_reasoning_effort": str(account.get("reasoning_effort", "high")),
        }
        new_config = self._rewrite_top_level(config_text, updates)
        new_config = self._replace_provider_block(
            new_config,
            provider_id,
            self._render_provider_block(provider_id, account["provider_config"]),
        )
        if self._connection_type(account) == "sub2api" and account.get("transport") == "websocket":
            new_config = self._upsert_section_value(
                new_config,
                "features",
                "responses_websockets_v2",
                True,
            )
        auth_text = json.dumps({"OPENAI_API_KEY": account["api_key"]}, ensure_ascii=False, indent=2)

        store["active_account"] = name
        store.pop("unmanaged_current_account", None)
        account["updated_at"] = _now()
        endpoint = self._models_endpoint(account)
        self._backup_many(self.paths.config, self.paths.auth, self.paths.catalog)
        self._commit_account_switch(
            store,
            [
                (self.paths.config, new_config),
                (self.paths.auth, auth_text + "\n"),
                (
                    self.paths.catalog,
                    json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
                ),
                (
                    self.paths.sync_state,
                    self._sync_state_text("ok", name, len(model_ids), endpoint, ""),
                ),
            ],
        )
        return {
            "account": name,
            "model": selected_model,
            "models": len(model_ids),
            "models_source": models_source,
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
        accounts = store["accounts"]
        for name, account in accounts.items():
            if not isinstance(account, dict):
                continue
            saved_provider = account.get("provider_config", {})
            saved_url = (
                str(saved_provider.get("base_url", "")).rstrip("/")
                if isinstance(saved_provider, dict)
                else ""
            )
            if str(account.get("provider_id", "")) == provider_id and saved_url == current_url:
                if store.get("active_account") != name:
                    store["active_account"] = name
                    return True
                return False

        base_name = str(provider.get("name", "")) or provider_id
        name = base_name
        suffix = 2
        while name in accounts:
            name = f"{base_name} {suffix}"
            suffix += 1
        accounts[name] = {
            "account_type": "custom",
            "connection_type": "openai_compatible",
            "auth_mode": "legacy",
            "transport": "http_sse",
            "provider_id": provider_id,
            "provider_config": dict(provider),
            "api_key": self._auth_api_key(self._read_text(self.paths.auth)),
            "default_model": str(config.get("model", "")),
            "reasoning_effort": str(config.get("model_reasoning_effort", "high")),
            "created_at": _now(),
            "updated_at": _now(),
        }
        store["active_account"] = name
        return True

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
