from __future__ import annotations

from .common import *
from .common import _now


class ModelsMixin:
    def preview_active_models(self) -> dict[str, Any]:
        store = self._load_store()
        name = str(store.get("active_account", ""))
        account = store["accounts"].get(name)
        if not isinstance(account, dict):
            raise ValueError("没有已启用的账号")
        if self._account_type(account) == "official":
            model_ids = self._normalized_model_ids([
                str(item.get("slug", ""))
                for item in self._official_catalog_models()
                if item.get("slug")
            ])
            endpoint = "official://openai"
        else:
            model_ids = self._merge_official_model_ids(self._fetch_model_ids(account))
            endpoint = self._models_endpoint(account)
        selected_model_ids = self._normalized_model_ids(account.get("model_ids", []))
        if self._account_type(account) != "official":
            selected_model_ids = self._merge_official_model_ids(selected_model_ids)
        return {
            "account": name,
            "models": len(model_ids),
            "model_ids": model_ids,
            "selected_model_ids": selected_model_ids,
            "endpoint": endpoint,
        }

    def sync_active(self, selected_model_ids: Any = None) -> dict[str, Any]:
        store = self._load_store()
        name = str(store.get("active_account", ""))
        account = store["accounts"].get(name)
        if not isinstance(account, dict):
            raise ValueError("没有已启用的账号")
        if self._account_type(account) == "official":
            return self._sync_official_account(store, name, account)
        try:
            remote_model_ids = self._merge_official_model_ids(self._fetch_model_ids(account))
            visible_model_ids = remote_model_ids
            if selected_model_ids is not None:
                selected = self._normalized_model_ids(selected_model_ids)
                if not selected:
                    raise ValueError("请至少选择一个需要注入的模型")
                unknown = sorted(set(selected) - set(remote_model_ids))
                if unknown:
                    raise ValueError(f"选择中包含渠道当前不存在的模型：{unknown[0]}")
                selected_set = set(selected)
                visible_model_ids = [
                    model_id for model_id in remote_model_ids if model_id in selected_set
                ]
            catalog = self._build_catalog(remote_model_ids, visible_model_ids)
            config = self._read_toml(self.paths.config)
            current_model = str(config.get("model", ""))
            selected_model = (
                current_model if current_model in visible_model_ids else visible_model_ids[0]
            )
            config_text = self._read_text(self.paths.config)
            config_text = self._rewrite_top_level(
                config_text,
                {
                    "model": selected_model,
                    "model_catalog_json": str(self.paths.catalog),
                },
            )
            self._backup_many(self.paths.config, self.paths.catalog)
            self._atomic_write(self.paths.config, config_text)
            self._atomic_write(
                self.paths.catalog,
                json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            )
            account["default_model"] = selected_model
            account["model_ids"] = visible_model_ids
            account["catalog_model_ids"] = remote_model_ids
            account["updated_at"] = _now()
            self._save_store(store)
            endpoint = self._models_endpoint(account)
            self._record_sync("ok", name, len(remote_model_ids), endpoint, "")
            return {
                "account": name,
                "model": selected_model,
                "models": len(remote_model_ids),
                "visible_models": len(visible_model_ids),
                "endpoint": endpoint,
            }
        except Exception as exc:
            self._record_sync("error", name, 0, self._models_endpoint(account), str(exc))
            raise

    def switch_model(self, slug: str) -> None:
        slug = slug.strip()
        store = self._load_store()
        active = store["accounts"].get(store.get("active_account", ""))
        catalog = (
            self._official_catalog_models()
            if isinstance(active, dict) and self._account_type(active) == "official"
            else self._read_catalog_models()
        )
        available = {
            str(item.get("slug", ""))
            for item in catalog
            if str(item.get("visibility", "list")) == "list"
        }
        if slug not in available:
            raise ValueError(f"模型不在当前账号目录中：{slug}")
        if isinstance(active, dict):
            active["default_model"] = slug
            active["updated_at"] = _now()
            self._save_store(store)
        text = self._read_text(self.paths.config)
        self._backup_many(self.paths.config)
        self._atomic_write(self.paths.config, self._rewrite_top_level(text, {"model": slug}))

    def restore_official_model_catalog(self) -> dict[str, Any]:
        store = self._load_store()
        name = str(store.get("active_account", ""))
        account = store["accounts"].get(name)
        if not isinstance(account, dict):
            raise ValueError("没有已启用的账号")
        if self._account_type(account) == "official":
            raise ValueError("官方账号已经使用默认模型目录")

        model_ids = list(RESTORED_OFFICIAL_MODEL_IDS)
        current_model = str(self._read_toml(self.paths.config).get("model", ""))
        selected_model = current_model if current_model in model_ids else model_ids[0]
        catalog = self._build_catalog(model_ids, model_ids)
        # These public models may be absent from the installed Codex catalog.
        for entry in catalog["models"]:
            if entry["slug"] in {"gpt-6-luna", "gpt-6-sol"}:
                entry["display_name"] = "GPT-6 " + entry["slug"].rsplit("-", 1)[1].title()
                entry["description"] = "OpenAI 官方公开模型；当前渠道可用性尚未验证"
                entry["context_window"] = 1050000
                entry["max_context_window"] = 1050000
                entry["default_reasoning_level"] = "medium"
                entry["supported_reasoning_levels"] = [
                    {"effort": effort, "description": effort}
                    for effort in ("none", "low", "medium", "high", "xhigh", "max")
                ]
        config_text = self._rewrite_top_level(
            self._read_text(self.paths.config),
            {"model": selected_model, "model_catalog_json": str(self.paths.catalog)},
        )
        account["default_model"] = selected_model
        account["model_ids"] = model_ids
        account["catalog_model_ids"] = model_ids
        account["updated_at"] = _now()
        self._backup_many(self.paths.config, self.paths.catalog)
        self._commit_account_switch(
            store,
            [
                (self.paths.config, config_text),
                (self.paths.catalog, json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"),
                (
                    self.paths.sync_state,
                    self._sync_state_text("ok", name, len(model_ids), "official://preset", ""),
                ),
            ],
        )
        return {"account": name, "model": selected_model, "models": len(model_ids)}

    def sync_and_launch(self, restart: bool = True) -> dict[str, Any]:
        result = self.sync_active()
        result["launch"] = self.launch_codex(restart=restart, apply_patches=True)
        result["model_filter"] = "local_catalog"
        return result

    def _fetch_model_ids(self, account: dict[str, Any]) -> list[str]:
        token = str(account.get("api_key", ""))
        endpoints = self._model_endpoint_candidates(account)
        if not endpoints or not token:
            raise ValueError("账号缺少 Base URL 或 API Key")
        failures: list[str] = []
        for endpoint in endpoints:
            request = urllib.request.Request(
                endpoint,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=6) as response:
                    payload = json.load(response)
                values: list[Any] = []
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    values = payload["data"]
                elif isinstance(payload, dict) and isinstance(payload.get("models"), list):
                    values = payload["models"]
                elif isinstance(payload, list):
                    values = payload
                model_ids = []
                for item in values:
                    value = (item.get("id") or item.get("slug")) if isinstance(item, dict) else item
                    if isinstance(value, str) and value.strip():
                        model_ids.append(value.strip())
                model_ids = list(dict.fromkeys(model_ids))
                if model_ids:
                    return model_ids
                failures.append(f"{endpoint} 未返回模型")
            except urllib.error.HTTPError as exc:
                failures.append(f"{endpoint} HTTP {exc.code}")
            except urllib.error.URLError as exc:
                failures.append(f"{endpoint} {getattr(exc, 'reason', '连接失败')}")
            except TimeoutError:
                failures.append(f"{endpoint} 请求超时")
            except json.JSONDecodeError:
                failures.append(f"{endpoint} 返回无效 JSON")

        official_ids = self._normalized_model_ids(
            [item.get("slug") for item in self._official_catalog_models()]
        )
        if official_ids:
            return official_ids
        detail = "；".join(failures)
        raise RuntimeError(f"渠道模型接口均不可用，且无法读取官方模型目录：{detail}")

    @staticmethod
    def _normalized_model_ids(values: Any) -> list[str]:
        if not isinstance(values, (list, tuple)):
            return []
        return list(
            dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip())
        )

    def _merge_official_model_ids(self, local_model_ids: Any) -> list[str]:
        official_model_ids = [
            str(item.get("slug", ""))
            for item in self._official_catalog_models()
            if item.get("slug")
        ]
        return self._normalized_model_ids(official_model_ids + self._normalized_model_ids(local_model_ids))

    def _build_catalog(
        self, model_ids: list[str], visible_model_ids: list[str] | None = None
    ) -> dict[str, Any]:
        bundled = self._bundled_catalog()
        known = {
            str(item.get("slug", "")): item
            for item in bundled
            if isinstance(item, dict) and item.get("slug")
        }
        template = bundled[0] if bundled else self._fallback_model_template()
        visible = set(model_ids if visible_model_ids is None else visible_model_ids)
        models = []
        for index, slug in enumerate(model_ids):
            entry = copy.deepcopy(known.get(slug, template))
            exact = slug in known
            entry["slug"] = slug
            entry["display_name"] = entry.get("display_name") if exact else slug
            entry["description"] = entry.get("description") if exact else f"由当前渠道提供的模型：{slug}"
            entry["visibility"] = "list" if slug in visible else "hide"
            entry["supported_in_api"] = True
            entry["priority"] = 1000 + index
            entry["availability_nux"] = None
            entry["upgrade"] = None
            entry.setdefault("context_window", 272000)
            entry.setdefault("max_context_window", entry["context_window"])
            entry.setdefault("effective_context_window_percent", 95)
            models.append(entry)
        return {
            "version": 1,
            "updated_at": _now(),
            "generated_by": "MaoLocal Codex Manager",
            "models": models,
        }

    def _official_default_model(self) -> str:
        models = self._official_catalog_models()
        return str(models[0].get("slug", "")) if models else ""

    @staticmethod
    def _fallback_model_template() -> dict[str, Any]:
        return {
            "slug": "template",
            "display_name": "Template",
            "description": "Provider model",
            "default_reasoning_level": "medium",
            "supported_reasoning_levels": [
                {"effort": "low", "description": "Fast responses"},
                {"effort": "medium", "description": "Balanced reasoning"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra high reasoning"},
            ],
            "shell_type": "shell_command",
            "visibility": "list",
            "supported_in_api": True,
            "context_window": 272000,
            "max_context_window": 272000,
            "effective_context_window_percent": 95,
            "supports_parallel_tool_calls": True,
            "input_modalities": ["text", "image"],
        }

    @staticmethod
    def _model_endpoint_candidates(account: dict[str, Any]) -> list[str]:
        provider = account.get("provider_config", {})
        base_url = str(provider.get("base_url", "")).rstrip("/")
        if not base_url:
            return []
        if base_url.endswith("/models"):
            return [base_url]
        v1_models = base_url + "/models" if base_url.endswith("/v1") else base_url + "/v1/models"
        return list(dict.fromkeys([base_url, base_url + "/models", v1_models]))

    def _models_endpoint(self, account: dict[str, Any]) -> str:
        candidates = self._model_endpoint_candidates(account)
        return candidates[1] if len(candidates) > 1 else (candidates[0] if candidates else "")
