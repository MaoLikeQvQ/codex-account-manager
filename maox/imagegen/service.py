from __future__ import annotations

from maox.shared.common import *
from maox.shared.common import _now


class ImageMixin:
    @staticmethod
    def _resource_root() -> Path:
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))

    def _image_generation_state(self, config: dict[str, Any]) -> dict[str, Any]:
        image_config = self._read_json(self.paths.image_config, {})
        image_state = self._read_json(self.paths.image_state, {})
        if not isinstance(image_config, dict):
            image_config = {}
        if not isinstance(image_state, dict):
            image_state = {}
        mcp_servers = config.get("mcp_servers", {})
        if not isinstance(mcp_servers, dict):
            mcp_servers = {}
        mcp = mcp_servers.get("custom-imagegen", mcp_servers.get("maolocal-imagegen", {}))
        if not isinstance(mcp, dict):
            mcp = {}
        legacy_skill = self.paths.codex_home / "skills" / "maolocal-imagegen" / "SKILL.md"
        mcp_args = mcp.get("args", []) if isinstance(mcp, dict) else []
        mcp_env = mcp.get("env", {}) if isinstance(mcp, dict) else {}
        installed_version = self._read_text(self.paths.image_plugin_version).strip()
        installed = (
            self.paths.image_server.is_file()
            and isinstance(mcp_args, list)
            and mcp_args == [str(self.paths.image_server)]
            and isinstance(mcp_env, dict)
            and mcp_env.get("CUSTOM_IMAGEGEN_CONFIG") == str(self.paths.image_config)
        )
        enabled = bool(image_state.get("enabled", bool(mcp.get("command"))))
        migration_pending = "maolocal-imagegen" in mcp_servers or (
            enabled and legacy_skill.is_file()
        )
        credential_source = str(image_config.get("credentialSource", "separate"))
        configured = (
            bool(image_config.get("accountStorePath") and image_config.get("accountName"))
            if credential_source == "managed_account"
            else bool(image_config.get("baseUrl") and image_config.get("apiKey"))
        )
        return {
            "configured": configured,
            "enabled": enabled,
            "installed": installed,
            "installed_version": installed_version,
            "bundled_version": IMAGE_PLUGIN_VERSION,
            "update_available": bool(installed_version and installed_version != IMAGE_PLUGIN_VERSION),
            "pending_apply": enabled != installed
            or (enabled and (
                installed_version != IMAGE_PLUGIN_VERSION or not self.paths.image_skill.is_file()
            ))
            or migration_pending,
            "mode": str(image_config.get("mode", "images")),
            "source": str(image_state.get("source", credential_source)),
            "account_name": str(image_state.get("account_name", "")),
            "provider": str(image_config.get("provider", "api")),
            "base_url": str(image_config.get("baseUrl", "")),
            "image_model": str(image_config.get("imageModel", "gpt-image-2")),
            "has_api_key": bool(image_config.get("apiKey")),
            "runtime_available": shutil.which("node") is not None,
        }

    def configure_image_generation(self, payload: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(payload.get("enabled", True))
        if not enabled:
            current_state = self._read_json(self.paths.image_state, {})
            if not isinstance(current_state, dict):
                current_state = {}
            current_state["enabled"] = False
            self._backup_many(self.paths.image_state)
            self._write_private_json(self.paths.image_state, current_state)
            return self._image_generation_state(self._read_toml(self.paths.config))

        source = str(payload.get("source", "separate")).strip()
        mode = str(payload.get("mode", "images")).strip()
        image_model = str(payload.get("image_model", "gpt-image-2")).strip()
        if source == "active_account":
            source = "managed_account"
        if source not in {"managed_account", "separate"}:
            raise ValueError("图片渠道来源无效")
        if mode not in {"images", "responses"}:
            raise ValueError("图片接口模式无效")
        if not image_model:
            raise ValueError("图片模型不能为空")
        existing = self._read_json(self.paths.image_config, {})
        existing_key = str(existing.get("apiKey", "")) if isinstance(existing, dict) else ""
        account_name = ""
        provider = "api"
        if source == "managed_account":
            store = self._load_store()
            account_name = str(payload.get("account_name", "")).strip() or str(
                store.get("active_account", "")
            )
            account = store.get("accounts", {}).get(account_name)
            if not isinstance(account, dict):
                raise ValueError("请选择账号列表中的图片请求账号")
            if self._account_type(account) == "official":
                raise ValueError("OpenAI 官方 ChatGPT/Codex OAuth 凭据不能用于公开图片 API，请另行配置 OpenAI Platform API Key")
            else:
                provider_config = account.get("provider_config", {})
                base_url = str(provider_config.get("base_url", "")).strip().rstrip("/")
                api_key = str(account.get("api_key", "")).strip()
        else:
            base_url = str(payload.get("base_url", "")).strip().rstrip("/")
            api_key = str(payload.get("api_key", "")).strip() or existing_key
        # Image providers handle only image generation/editing; Codex owns the chat model.
        mode = "images"
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("图片 Base URL 必须是有效的 http 或 https 地址")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("图片 Base URL 不能包含账号密码、查询参数或片段")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("图片 Base URL 必须使用 HTTPS，本机地址除外")
        if not api_key:
            raise ValueError("图片 API Key 不能为空")

        image_config = {
            "credentialSource": source,
            "provider": provider,
            "mode": mode,
            "imageModel": image_model,
        }
        if source == "managed_account":
            image_config.update(
                {
                    "accountStorePath": str(self.paths.accounts),
                    "accountName": account_name,
                }
            )
        else:
            image_config.update({"baseUrl": base_url, "apiKey": api_key})
        self._backup_many(
            self.paths.image_config,
            self.paths.image_state,
        )
        self._commit_text_files(
            [
                (
                    self.paths.image_config,
                    json.dumps(image_config, ensure_ascii=False, indent=2) + "\n",
                ),
                (
                    self.paths.image_state,
                    json.dumps(
                        {
                            "enabled": True,
                            "source": source,
                            **({"account_name": account_name} if account_name else {}),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ) + "\n",
                ),
            ],
            "图片工具配置",
        )
        return self._image_generation_state(self._read_toml(self.paths.config))

    def apply_image_generation(self) -> dict[str, Any]:
        config = self._read_toml(self.paths.config)
        state = self._image_generation_state(config)
        config_text = self._read_text(self.paths.config)
        if not state["enabled"]:
            updated = config_text
            for name in ("custom-imagegen", "maolocal-imagegen"):
                updated = self._remove_image_mcp_section(updated, name)
            if updated != config_text:
                self._backup_many(self.paths.config)
                self._atomic_write(self.paths.config, updated)
            return {**self._image_generation_state(self._read_toml(self.paths.config)), "plugin_action": "disabled"}
        if not state["configured"]:
            raise ValueError("请先配置图片请求账号或自定义链接")

        node = shutil.which("node") or "node"
        bundled = self._image_plugin_source_root()
        if (bundled / "dist" / "server.cjs").is_file():
            source_files = {
                self.paths.image_server: bundled / "dist" / "server.cjs",
                self.paths.image_plugin_version: bundled / "VERSION",
                self.paths.image_plugin_notices: bundled / "THIRD_PARTY_NOTICES.txt",
                self.paths.image_skill: bundled / "skills" / "custom-imagegen" / "SKILL.md",
            }
        else:
            source_files = {
                self.paths.image_server: bundled / "server.cjs",
                self.paths.image_plugin_version: bundled / "VERSION",
                self.paths.image_plugin_notices: bundled / "THIRD_PARTY_NOTICES.txt",
                self.paths.image_skill: bundled / "SKILL.md",
            }
        if any(not source.is_file() for source in source_files.values()):
            raise RuntimeError("应用缺少完整图片插件资源，请重新安装管理器")
        bundled_version = (bundled / "VERSION").read_text(encoding="utf-8").strip()
        if bundled_version != IMAGE_PLUGIN_VERSION:
            raise RuntimeError("应用内图片插件版本不一致，请重新安装管理器")

        previous_version = self._read_text(self.paths.image_plugin_version).strip()
        plugin_current = previous_version == bundled_version and all(
            target.is_file() and target.read_bytes() == source.read_bytes()
            for target, source in source_files.items()
        )
        block = (
            "[mcp_servers.custom-imagegen]\n"
            f"command = {json.dumps(node, ensure_ascii=False)}\n"
            f"args = [{json.dumps(str(self.paths.image_server), ensure_ascii=False)}]\n"
            "tool_timeout_sec = 660\n"
            "env = { CUSTOM_IMAGEGEN_CONFIG = "
            f"{json.dumps(str(self.paths.image_config), ensure_ascii=False)} }}\n"
        )
        new_config = self._remove_image_mcp_section(config_text, "maolocal-imagegen")
        new_config = self._remove_image_mcp_section(new_config, "custom-imagegen")
        new_config = self._replace_toml_section(new_config, "mcp_servers.custom-imagegen", block)
        writes = [(self.paths.config, new_config)]
        if not plugin_current:
            writes = [
                (target, source.read_text(encoding="utf-8"))
                for target, source in source_files.items()
            ] + writes
        legacy_skill = self.paths.codex_home / "skills" / "maolocal-imagegen" / "SKILL.md"
        self._backup_many(self.paths.config, legacy_skill)
        self._commit_text_files(writes, "Custom ImageGen 应用")
        # Remove only the retired skill entry after the replacement is installed.
        # Keep any other files in the old directory, including user additions.
        if legacy_skill.is_file():
            legacy_skill.unlink()
            if not any(legacy_skill.parent.iterdir()):
                legacy_skill.parent.rmdir()
        action = "current" if plugin_current else ("updated" if previous_version else "installed")
        return {**self._image_generation_state(self._read_toml(self.paths.config)), "plugin_action": action}

    @staticmethod
    def _remove_image_mcp_section(config_text: str, name: str) -> str:
        # Include nested env tables and quoted service keys while preserving other MCPs.
        key = re.escape(name)
        header = re.compile(rf"^\s*\[\s*mcp_servers\.(?:{key}|\"{key}\"|'{key}')(?:\s*\]|\.)")
        kept = []
        removing = False
        for line in config_text.splitlines(keepends=True):
            if line.lstrip().startswith("["):
                removing = bool(header.match(line))
            if not removing:
                kept.append(line)
        return "".join(kept)

    @staticmethod
    def _image_plugin_source_root() -> Path:
        configured = (
            os.environ.get("CUSTOM_IMAGEGEN_PLUGIN_SOURCE", "").strip()
            or os.environ.get("MAOLOCAL_IMAGEGEN_PLUGIN_SOURCE", "").strip()
        )
        candidates = [Path(configured)] if configured else []
        candidates.append(Path(__file__).resolve().parents[3] / "custom-imagegen-plugin" / "release" / "custom-imagegen-share" / "plugins" / "custom-imagegen-plugin")
        candidates.append(ImageMixin._resource_root() / "imagegen_plugin")
        for candidate in candidates:
            if (candidate / "dist" / "server.cjs").is_file() or (candidate / "server.cjs").is_file():
                return candidate
        return candidates[-1]
