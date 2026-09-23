from __future__ import annotations

from .common import *
from .common import _now


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

    @staticmethod
    def _sync_state_text(
        status: str,
        account: str,
        count: int,
        endpoint: str,
        error: str,
    ) -> str:
        safe_endpoint = endpoint.split("?", 1)[0].split("#", 1)[0]
        return (
            json.dumps(
                {
                    "status": status,
                    "account": account,
                    "model_count": count,
                    "endpoint": safe_endpoint,
                    "error": error,
                    "updated_at": _now(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )

    def _record_sync(self, status: str, account: str, count: int, endpoint: str, error: str) -> None:
        self._atomic_write(
            self.paths.sync_state,
            self._sync_state_text(status, account, count, endpoint, error),
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
            "catalog_path": str(config.get("model_catalog_json", "")),
            "auth_present": bool(self._auth_api_key(self._read_text(self.paths.auth))),
        }

    def _catalog_state(
        self,
        models: list[dict[str, Any]],
        official: bool = False,
    ) -> dict[str, Any]:
        if official:
            return {
                "path": "Codex bundled catalog",
                "exists": True,
                "model_count": len(models),
                "updated_at": "",
            }
        payload = self._read_json(self.paths.catalog, {})
        return {
            "path": str(self.paths.catalog),
            "exists": self.paths.catalog.is_file(),
            "model_count": len(models),
            "updated_at": str(payload.get("updated_at", "")),
        }

    def _read_catalog_models(self) -> list[dict[str, Any]]:
        payload = self._read_json(self.paths.catalog, {})
        models = payload.get("models", [])
        if not isinstance(models, list):
            return []
        return [item for item in models if isinstance(item, dict) and item.get("slug")]

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
            body = ", ".join(f"{key} = {StorageMixin._toml_value(item)}" for key, item in value.items())
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
        lines = text.splitlines(keepends=True)
        header = f"[model_providers.{provider_id}]"
        start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
        block_lines = block.splitlines(keepends=True)
        if start is None:
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.extend(block_lines)
        else:
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
                len(lines),
            )
            lines[start:end] = block_lines + (["\n"] if end < len(lines) else [])
        result = "".join(lines)
        return result if result.endswith("\n") else result + "\n"

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
        lines = text.splitlines(keepends=True)
        header = f"[{section}]"
        start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
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
