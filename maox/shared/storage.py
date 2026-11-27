from __future__ import annotations

from maox.shared.common import *
from maox.shared.common import _now


class StorageMixin:
    def _save_store(self, store: dict[str, Any]) -> None:
        self._atomic_write(self.paths.accounts, self._store_text(store))

    @staticmethod
    def _store_text(store: dict[str, Any]) -> str:
        store["version"] = STORE_VERSION
        return json.dumps(store, ensure_ascii=False, indent=2) + "\n"

    def _commit_account_switch(
        self,
        store: dict[str, Any],
        writes: list[tuple[Path, str]],
    ) -> None:
        self._commit_text_files(
            [*writes, (self.paths.accounts, self._store_text(store))],
            "账号切换",
        )

    def _public_account(self, name: str, account: dict[str, Any], active: bool) -> dict[str, Any]:
        provider = account.get("provider_config", {})
        account_type = self._account_type(account)
        connection_type = self._connection_type(account)
        return {
            "name": name,
            "account_type": account_type,
            "connection_type": connection_type,
            "auth_mode": str(account.get("auth_mode", "legacy"))
            if account_type == "custom"
            else "",
            "transport": str(account.get("transport", "http_sse"))
            if account_type == "custom"
            else "",
            "provider_id": str(account.get("provider_id", "")),
            "provider_name": str(provider.get("name", "")),
            "base_url": str(provider.get("base_url", "")),
            "model_catalog_url": str(provider.get("model_catalog_url", "")),
            "requires_openai_auth": bool(provider.get("requires_openai_auth", True)),
            "api_key_model_discovery": account.get("api_key_model_discovery", bool(provider.get("model_catalog_url"))),
            "pending_apply": bool(account.get("pending_apply")),
            "wire_api": str(provider.get("wire_api", "responses")),
            "default_model": str(account.get("default_model", "")),
            "reasoning_effort": str(account.get("reasoning_effort", "high")),
            "has_api_key": bool(account.get("api_key")) if account_type == "custom" else False,
            "email": str(account.get("official_email", "")) if account_type == "official" else "",
            "plan_type": str(account.get("official_plan_type", "")) if account_type == "official" else "",
            "has_official_auth": bool(account.get("official_auth")) if account_type == "official" else False,
            "active": active,
            "updated_at": str(account.get("updated_at", "")),
        }

    def _current_config(self, config: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(config.get("model_provider", ""))
        providers = config.get("model_providers", {})
        provider = providers.get(provider_id, {}) if isinstance(providers, dict) else {}
        return {
            "model": str(config.get("model", "")),
            "provider_id": provider_id,
            "base_url": str(provider.get("base_url", "")) if isinstance(provider, dict) else "",
            "reasoning_effort": str(config.get("model_reasoning_effort", "")),
            "auth_present": bool(self._auth_api_key(self._read_text(self.paths.auth))),
        }

    def _without_managed_catalog(self, text: str) -> str:
        try:
            catalog = tomllib.loads(text).get("model_catalog_json") if text.strip() else None
        except tomllib.TOMLDecodeError:
            return text
        if catalog not in {str(self.paths.codex_home / "models.json"), str(self.paths.bundled_model_catalog)}:
            return text
        updated = self._remove_top_level(text, {"model_catalog_json"})
        tomllib.loads(updated)
        return updated

    def _clear_managed_catalog(self) -> None:
        text = self._read_text(self.paths.config)
        updated = self._without_managed_catalog(text)
        if updated != text:
            self._backup_many(self.paths.config)
            self._atomic_write(self.paths.config, updated)

    def _write_private_json(self, path: Path, payload: Any) -> None:
        self._atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _parse_provider_block(text: str) -> tuple[str, dict[str, Any]]:
        payload = tomllib.loads(text)
        providers = payload.get("model_providers", {})
        if not isinstance(providers, dict) or len(providers) != 1:
            raise ValueError("Provider 配置无效")
        provider_id = next(iter(providers))
        provider = providers[provider_id]
        if not isinstance(provider, dict):
            raise ValueError("Provider 配置无效")
        return provider_id, dict(provider)

    @staticmethod
    def _render_provider_block(provider_id: str, provider: dict[str, Any]) -> str:
        lines = [f"[model_providers.{provider_id}]"]
        for key, value in provider.items():
            if key == "experimental_bearer_token":
                continue
            lines.append(f"{key} = {StorageMixin._toml_value(value)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _toml_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return "[" + ", ".join(StorageMixin._toml_value(item) for item in value) + "]"
        if isinstance(value, dict):
            body = ", ".join(f"{json.dumps(str(key))} = {StorageMixin._toml_value(item)}" for key, item in value.items())
            return "{ " + body + " }"
        return json.dumps(str(value), ensure_ascii=False)

    @staticmethod
    def _rewrite_top_level(text: str, updates: dict[str, str]) -> str:
        lines = text.splitlines(keepends=True)
        if not lines:
            lines = []
        first_section = next(
            (index for index, line in enumerate(lines) if line.lstrip().startswith("[")),
            len(lines),
        )
        replaced: set[str] = set()
        for index in range(first_section):
            match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", lines[index])
            if match and match.group(1) in updates:
                key = match.group(1)
                lines[index] = f"{key} = {json.dumps(updates[key], ensure_ascii=False)}\n"
                replaced.add(key)
        additions = [
            f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
            for key, value in updates.items()
            if key not in replaced
        ]
        if additions:
            lines[first_section:first_section] = additions + (["\n"] if first_section == 0 else [])
        result = "".join(lines)
        return result if result.endswith("\n") else result + "\n"

    @staticmethod
    def _remove_top_level(text: str, keys: set[str]) -> str:
        lines = text.splitlines(keepends=True)
        first_section = next(
            (index for index, line in enumerate(lines) if line.lstrip().startswith("[")),
            len(lines),
        )
        kept = []
        for index, line in enumerate(lines):
            match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line) if index < first_section else None
            if match and match.group(1) in keys:
                continue
            kept.append(line)
        result = "".join(kept)
        return result if not result or result.endswith("\n") else result + "\n"

    @staticmethod
    def _replace_provider_block(text: str, provider_id: str, block: str) -> str:
        kept = []
        owned = False
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith("["):
                # Parse a table header so quoted keys and nested header tables are removed too.
                try:
                    section = tomllib.loads(line)
                except tomllib.TOMLDecodeError:
                    section = {}
                owned = provider_id in section.get("model_providers", {})
            if not owned:
                kept.append(line)
        return "".join(kept).rstrip() + "\n\n" + block.rstrip() + "\n"

    @staticmethod
    def _remove_section_value(text: str, section: str, key: str) -> str:
        inline = StorageMixin._update_inline_section(text, section, key, None, remove=True)
        if inline is not None:
            return inline
        inside = False
        kept = []
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith("["):
                inside = line.split("#", 1)[0].strip() == f"[{section}]"
            if inside and re.match(rf"^\s*{re.escape(key)}\s*=", line):
                continue
            kept.append(line)
        return "".join(kept)

    @staticmethod
    def _update_inline_section(text, section, key, value, *, remove=False):
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.lstrip().startswith("["):
                break
            if re.match(rf"^\s*{re.escape(section)}\s*=", line):
                table = tomllib.loads(text).get(section)
                if not isinstance(table, dict):
                    raise ValueError(f"{section} 必须为配置表")
                table = dict(table)
                if remove:
                    table.pop(key, None)
                else:
                    table[key] = value
                lines[index] = f"{section} = {StorageMixin._toml_value(table)}\n"
                return "".join(lines)
        return None

    def _apply_account_features(self, text, store, values):
        baseline = store.setdefault("account_feature_baseline", {})
        features = tomllib.loads(text).get("features", {})
        for key, value in values.items():
            baseline.setdefault(key, {"present": key in features, "value": features.get(key)})
            text = self._upsert_section_value(text, "features", key, value)
        return text

    def _restore_account_features(self, text, store):
        for key, original in store.pop("account_feature_baseline", {}).items():
            if original["present"]:
                text = self._upsert_section_value(text, "features", key, original["value"])
            else:
                text = self._remove_section_value(text, "features", key)
        return text

    @staticmethod
    def _replace_toml_section(text: str, section: str, block: str) -> str:
        lines = text.splitlines(keepends=True)
        header = f"[{section}]"
        start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
        if start is not None:
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
                len(lines),
            )
            del lines[start:end]
            while start < len(lines) and not lines[start].strip():
                del lines[start]
        if block:
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.extend(block.splitlines(keepends=True))
        result = "".join(lines).rstrip()
        return result + ("\n" if result else "")

    @staticmethod
    def _upsert_section_value(text: str, section: str, key: str, value: Any) -> str:
        inline = StorageMixin._update_inline_section(text, section, key, value)
        if inline is not None:
            return inline
        lines = text.splitlines(keepends=True)
        header = f"[{section}]"
        start = next((i for i, line in enumerate(lines) if line.split("#", 1)[0].strip() == header), None)
        rendered = f"{key} = {StorageMixin._toml_value(value)}\n"
        if start is None:
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.extend([header + "\n", rendered])
        else:
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
                len(lines),
            )
            match = next(
                (
                    i
                    for i in range(start + 1, end)
                    if re.match(rf"^\s*{re.escape(key)}\s*=", lines[i])
                ),
                None,
            )
            if match is None:
                lines.insert(end, rendered)
            else:
                lines[match] = rendered
        result = "".join(lines)
        return result if result.endswith("\n") else result + "\n"

    @staticmethod
    def _auth_api_key(text: str) -> str:
        try:
            value = json.loads(text).get("OPENAI_API_KEY", "")
            return value.strip() if isinstance(value, str) else ""
        except (json.JSONDecodeError, AttributeError):
            return ""

    @staticmethod
    def _read_toml(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        with path.open("rb") as handle:
            return tomllib.load(handle)

    @staticmethod
    def _read_json(path: Path, fallback: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return fallback

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _commit_text_files(
        self,
        writes: list[tuple[Path, str]],
        operation: str,
    ) -> None:
        snapshots: dict[Path, str | None] = {}
        for path, _content in writes:
            if path in snapshots:
                raise ValueError(f"{operation}包含重复写入目标")
            snapshots[path] = path.read_text(encoding="utf-8") if path.is_file() else None

        attempted: list[Path] = []
        try:
            for path, content in writes:
                attempted.append(path)
                self._atomic_write(path, content)
        except Exception as exc:
            rollback_failed = False
            for path in reversed(attempted):
                try:
                    previous = snapshots[path]
                    if previous is None:
                        path.unlink(missing_ok=True)
                    else:
                        self._atomic_write(path, previous)
                except Exception:
                    rollback_failed = True
            if rollback_failed:
                raise RuntimeError(
                    f"{operation}失败，且本地配置未能完整回滚，请从备份恢复"
                ) from exc
            raise

    def _backup_many(self, *paths: Path) -> None:
        existing = [path for path in paths if path.is_file()]
        if not existing:
            return
        self.paths.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.paths.backups, 0o700)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        for path in existing:
            destination = self.paths.backups / f"{path.name}.{stamp}.bak"
            shutil.copy2(path, destination)
            os.chmod(destination, 0o600)

    def _ensure_directories(self) -> None:
        for path in (self.paths.codex_home, self.paths.app_home):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path, 0o700)

    @staticmethod
    def _codex_application() -> str:
        return str(CODEX_APP)
