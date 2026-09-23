from __future__ import annotations

from datetime import timedelta

from manager_parts.common import *
from manager_parts.common import _now
from manager_parts.accounts import AccountsMixin
from manager_parts.official import OfficialMixin
from manager_parts.image import ImageMixin
from manager_parts.models import ModelsMixin
from manager_parts.history import HistoryMixin
from manager_parts.storage import StorageMixin
from manager_parts.usage import summarize_range


class CodexManager(AccountsMixin, OfficialMixin, ImageMixin, ModelsMixin, HistoryMixin, StorageMixin):
    def usage_for_period(self, period: str = "today", selected_date: str = "") -> dict[str, Any]:
        store = self._load_store()
        account = store.get("accounts", {}).get(store.get("active_account", ""))
        if not isinstance(account, dict):
            raise ValueError("没有已启用的账号")
        official = self._account_type(account) == "official"
        provider_id = OFFICIAL_PROVIDER_ID if official else str(account.get("provider_id", ""))
        now = datetime.now().astimezone()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "today":
            start = today
        elif period == "yesterday":
            start = today - timedelta(days=1)
        elif period == "7d":
            start = today - timedelta(days=6)
        elif period == "date":
            try:
                start = datetime.strptime(selected_date, "%Y-%m-%d").replace(tzinfo=now.tzinfo)
            except ValueError as exc:
                raise ValueError("日期必须是 YYYY-MM-DD") from exc
            if start > today:
                raise ValueError("不能查询未来日期")
        else:
            raise ValueError("不支持的用量时间范围")
        end = today + timedelta(days=1) if period == "7d" else start + timedelta(days=1)
        return summarize_range(self.paths.codex_home, provider_id, official, start, end)

    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or Paths.from_environment()
        self._rollout_cache: dict[Path, tuple[tuple[int, int, int, bool], RolloutRecord]] = {}
        self._rollout_error_cache: dict[
            Path,
            tuple[tuple[int, int, int, bool], dict[str, Any]],
        ] = {}
        self._official_login_lock = threading.Lock()
        self._official_login_sessions: dict[str, dict[str, Any]] = {}
        self._bundled_catalog_cache: list[dict[str, Any]] | None = None
        self._bundled_catalog_cache_key: tuple[str, int, int] | None = None
        self._ensure_directories()

    def state(self) -> dict[str, Any]:
        store = self._load_store()
        config = self._read_toml(self.paths.config)
        active_name = str(store.get("active_account", ""))
        accounts = store.get("accounts", {})
        active_account = accounts.get(active_name) if isinstance(accounts, dict) else None
        official_active = (
            isinstance(active_account, dict) and self._account_type(active_account) == "official"
        )
        models = self._official_catalog_models() if official_active else self._read_catalog_models()
        sync_state = self._read_json(self.paths.sync_state, {})
        if official_active and (
            not isinstance(sync_state, dict) or sync_state.get("account") != active_name
        ):
            sync_state = {}
        return {
            "codex_home": str(self.paths.codex_home),
            "active_account": active_name,
            "accounts": [
                self._public_account(name, account, name == active_name)
                for name, account in accounts.items()
                if isinstance(account, dict)
            ],
            "current": self._current_config(config),
            "models": [
                {
                    "slug": item.get("slug", ""),
                    "display_name": item.get("display_name", "") or item.get("slug", ""),
                    "context_window": item.get("context_window"),
                    "visibility": item.get("visibility", "list"),
                }
                for item in models
            ],
            "catalog": self._catalog_state(models, official=official_active),
            "sync": sync_state,
            "codex": {
                "running": self.codex_running(),
                "application": self._codex_application(),
            },
            "conversations": self._conversation_state(),
            "image_generation": self._image_generation_state(config),
        }

    def run_post_switch_actions(
        self,
        name: str | None = None,
        *,
        sync_models: bool = False,
        model_ids: Any = None,
        claim_history: bool = False,
    ) -> dict[str, Any]:
        store = self._load_store()
        active_name = str(store.get("active_account", ""))
        target = (name or active_name).strip()
        if target != active_name:
            raise ValueError("只能对当前已启用账号执行切换后处理")
        account = store["accounts"].get(target)
        if not isinstance(account, dict):
            raise KeyError(f"账号不存在：{target}")
        result: dict[str, Any] = {"account": target, "actions": []}
        if sync_models:
            result["sync"] = (
                self.sync_active(model_ids) if model_ids is not None else self.sync_active()
            )
            result["actions"].append("sync_models")
        if claim_history:
            result["history"] = self.claim_all_conversations(target)
            result["actions"].append("claim_history")
        if sync_models:
            was_running = self.codex_running()
            if was_running:
                self._stop_codex()
            try:
                patch_result = self.ensure_codex_patches()
            except Exception:
                if was_running:
                    try:
                        self.launch_codex(restart=False, apply_patches=False)
                    except Exception:
                        pass
                raise
            result["model_catalog"] = patch_result
            result["actions"].append("inject_model_catalog")
            if was_running:
                result["launch"] = self.launch_codex(restart=False)
                result["actions"].append("restart_codex")
        return result

    def launch_codex(self, restart: bool = True, apply_patches: bool | None = None) -> str:
        if os.uname().sysname != "Darwin":
            raise RuntimeError("启动 Codex 目前只支持 macOS")
        running = self.codex_running()
        if restart and running:
            self._stop_codex()
        elif running:
            raise RuntimeError("Codex 正在运行，必须重启后才能更新本地模型列表")
        store = self._load_store()
        active = store.get("accounts", {}).get(store.get("active_account", ""))
        custom_active = isinstance(active, dict) and self._account_type(active) == "custom"
        if custom_active and apply_patches is not False:
            self._refresh_local_catalog_from_app()
        if apply_patches is True or (apply_patches is None and custom_active):
            self.ensure_codex_patches()
        subprocess.run(
            ["/usr/bin/open", "-b", "com.openai.codex"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return "restarted" if running and restart else "opened"

    def _refresh_local_catalog_from_app(self) -> None:
        official_ids = self._normalized_model_ids(
            [item.get("slug") for item in self._official_catalog_models()]
        )
        if not official_ids:
            return
        local_models = self._read_catalog_models()
        local_ids = self._normalized_model_ids([item.get("slug") for item in local_models])
        new_ids = [slug for slug in official_ids if slug not in local_ids]
        if not new_ids:
            return
        visible_ids = self._normalized_model_ids(
            [item.get("slug") for item in local_models if item.get("visibility", "list") != "hide"]
        )
        catalog = self._build_catalog(
            self._normalized_model_ids(official_ids + local_ids),
            self._normalized_model_ids(official_ids + visible_ids),
        )
        self._backup_many(self.paths.catalog)
        self._atomic_write(self.paths.catalog, json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _codex_bundle_version(app: Path) -> str:
        info_path = app / "Contents/Info.plist"
        try:
            info = plistlib.loads(info_path.read_bytes())
        except (OSError, plistlib.InvalidFileException, ValueError, TypeError) as exc:
            raise RuntimeError("无法读取当前 Codex 版本") from exc
        version = str(info.get("CFBundleShortVersionString", "")).strip()
        if not version:
            raise RuntimeError("当前 Codex 缺少版本信息")
        return version

    def _stop_codex(self) -> None:
        subprocess.run(
            ["/usr/bin/osascript", "-e", 'tell application id "com.openai.codex" to quit'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        for _ in range(40):
            if not self.codex_running():
                return
            time.sleep(0.25)
        raise RuntimeError("Codex 未能完全退出，尚未修改应用，请关闭后重试")

    def ensure_codex_patches(self, app: Path | None = None) -> dict[str, Any]:
        """确认本地模型目录支持，必要时补丁旧版 App。"""
        app = app or CODEX_APP
        asar = app / "Contents/Resources/app.asar"
        info_path = app / "Contents/Info.plist"
        executable = app / "Contents/MacOS/ChatGPT"
        codex_binary = app / "Contents/Resources/codex"
        code_resources = app / "Contents/_CodeSignature/CodeResources"
        if not asar.is_file():
            raise RuntimeError(f"Codex 应用结构不完整：{asar}")
        blob = asar.read_bytes()
        native_matches = len(list(CODEX_MODEL_NATIVE_CATALOG_PATTERN.finditer(blob)))
        if native_matches == 1:
            legacy_patterns = (
                CODEX_MODEL_FILTER_PATTERN,
                CODEX_MODEL_FILTER_BROKEN_262_PATTERN,
                CODEX_MODEL_FILTER_LEGACY_PATCHED_PATTERN,
                CODEX_MODEL_FILTER_PATCHED_PATTERN,
            )
            if any(pattern.search(blob) for pattern in legacy_patterns):
                raise RuntimeError("当前 Codex 同时包含新旧模型筛选代码，未执行补丁")
            return {"status": "native", "application": str(app)}
        required_files = (asar, info_path, executable, codex_binary, code_resources)
        required_paths = (*required_files, *self._codex_sparkle_sign_targets(app))
        missing = [
            str(path)
            for path in required_paths
            if not (path.is_file() if path in required_files else path.exists())
        ]
        if missing:
            raise RuntimeError(f"Codex 应用结构不完整：{missing[0]}")

        patched = blob
        if not self._model_availability_patch_is_current(patched):
            patched = self._patch_model_availability_blob(patched)
        if not self._model_announcement_patch_is_current(patched):
            patched = self._patch_model_announcement_blob(patched)
        codex_blob = codex_binary.read_bytes()
        patch_is_current = patched == blob
        if patch_is_current and self._codex_update_signatures_are_compatible(app):
            self._verify_codex_signature(app)
            return {"status": "current", "application": str(app)}
        info = plistlib.loads(info_path.read_bytes())
        integrity = info.get("ElectronAsarIntegrity")
        if not isinstance(integrity, dict):
            raise RuntimeError("Codex 缺少 Electron ASAR 完整性配置")
        resources = integrity.get("Resources/app.asar")
        if not isinstance(resources, dict):
            raise RuntimeError("Codex 缺少 app.asar 完整性配置")
        resources["hash"] = hashlib.sha256(patched).hexdigest()

        backup_dir = self._backup_codex_app_patch(
            app,
            blob,
            info_path.read_bytes(),
            executable.read_bytes(),
            codex_blob,
            code_resources.read_bytes(),
        )
        try:
            self._atomic_replace_bytes(asar, patched)
            self._atomic_replace_bytes(
                info_path,
                plistlib.dumps(info, fmt=plistlib.FMT_BINARY, sort_keys=False),
            )
            self._sign_locally_modified_codex(app)
            self._verify_codex_signature(app)
        except Exception as exc:
            rollback_error = self._restore_codex_app_patch(app, backup_dir)
            if rollback_error:
                raise RuntimeError(
                    f"Codex 注入失败，自动恢复也失败：{rollback_error}；"
                    f"原始文件保存在 {backup_dir}"
                ) from exc
            raise RuntimeError(f"Codex 注入失败，已恢复原应用：{exc}") from exc
        return {
            "status": "patched",
            "application": str(app),
            "backup": str(backup_dir),
        }

    @staticmethod
    def _model_availability_patch_is_current(blob: bytes) -> bool:
        source_count = len(list(CODEX_MODEL_FILTER_PATTERN.finditer(blob)))
        broken_count = len(list(CODEX_MODEL_FILTER_BROKEN_262_PATTERN.finditer(blob)))
        legacy_count = len(list(CODEX_MODEL_FILTER_LEGACY_PATCHED_PATTERN.finditer(blob)))
        patched_count = len(list(CODEX_MODEL_FILTER_PATCHED_PATTERN.finditer(blob)))
        total = source_count + broken_count + legacy_count + patched_count
        if total != 1:
            raise RuntimeError(
                "当前 Codex 版本的模型筛选代码已变化，未执行补丁；"
                f"预期 1 处，实际 {total} 处"
            )
        return patched_count == 1

    @staticmethod
    def _patch_model_availability_blob(blob: bytes) -> bytes:
        source_matches = list(CODEX_MODEL_FILTER_PATTERN.finditer(blob))
        broken_matches = list(CODEX_MODEL_FILTER_BROKEN_262_PATTERN.finditer(blob))
        legacy_matches = list(CODEX_MODEL_FILTER_LEGACY_PATCHED_PATTERN.finditer(blob))
        patched_matches = list(CODEX_MODEL_FILTER_PATCHED_PATTERN.finditer(blob))
        if (
            len(patched_matches) == 1
            and not source_matches
            and not broken_matches
            and not legacy_matches
        ):
            return blob
        matches = source_matches + broken_matches + legacy_matches
        if len(matches) != 1 or patched_matches:
            total = len(matches) + len(patched_matches)
            raise RuntimeError(
                "当前 Codex 版本的模型筛选代码已变化，未执行补丁；"
                f"预期 1 处，实际 {total} 处"
            )
        match = matches[0]
        additional_condition = (
            b"!"
            + match.group("custom")
            + b"&&"
            + match.group("additional")
            + b"?.has("
            + match.group("model")
            + b".model)"
        )
        additional_padding = len(match.group("additional_condition")) - len(
            additional_condition
        )
        if additional_padding < 0:
            raise RuntimeError("当前 Codex 版本的额外模型筛选代码长度不兼容")
        additional_condition += b" " * additional_padding
        condition = match.group("condition")
        marker = b"!1/*maolocal-models"
        padding = len(condition) - len(marker) - 2
        if padding < 0:
            raise RuntimeError("当前 Codex 版本的模型筛选代码长度不兼容")
        replacement = marker + b"_" * padding + b"*/"
        return (
            blob[: match.start("additional_condition")]
            + additional_condition
            + blob[match.end("additional_condition") : match.start("condition")]
            + replacement
            + blob[match.end("condition") :]
        )

    @staticmethod
    def _model_announcement_patch_is_current(blob: bytes) -> bool:
        source_count = len(list(CODEX_MODEL_ANNOUNCEMENT_PATTERN.finditer(blob)))
        patched_count = len(list(CODEX_MODEL_ANNOUNCEMENT_PATCHED_PATTERN.finditer(blob)))
        if source_count == 1 and patched_count == 0:
            return False
        if source_count == 0 and patched_count == 1:
            return True
        raise RuntimeError(
            "当前 Codex 版本的模型公告代码已变化，未执行补丁；"
            f"原始代码 {source_count} 处，已关闭代码 {patched_count} 处"
        )

    @staticmethod
    def _patch_model_announcement_blob(blob: bytes) -> bytes:
        matches = list(CODEX_MODEL_ANNOUNCEMENT_PATTERN.finditer(blob))
        if len(matches) != 1:
            raise RuntimeError(
                "当前 Codex 版本的模型公告代码已变化，未执行补丁；"
                f"预期 1 处，实际 {len(matches)} 处"
            )
        match = matches[0]
        condition = match.group("condition")
        replacement = b"!1" + b" " * (len(condition) - 2)
        return blob[: match.start("condition")] + replacement + blob[match.end("condition") :]

    def _backup_codex_app_patch(
        self,
        app: Path,
        asar: bytes,
        info: bytes,
        executable: bytes,
        codex_binary: bytes,
        code_resources: bytes,
    ) -> Path:
        version = "unknown"
        try:
            payload = plistlib.loads(info)
            version = str(payload.get("CFBundleShortVersionString", "unknown"))
        except (plistlib.InvalidFileException, ValueError, TypeError):
            pass
        digest = hashlib.sha256(asar + codex_binary).hexdigest()[:12]
        root = self.paths.backups / "codex-app-patches" / f"{version}-{digest}"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        for name, content in (
            ("app.asar", asar),
            ("Info.plist", info),
            ("ChatGPT", executable),
            ("codex", codex_binary),
            ("CodeResources", code_resources),
        ):
            destination = root / name
            if not destination.exists():
                self._atomic_replace_bytes(destination, content, mode=0o600)
        self._backup_directory_once(
            app / CODEX_SPARKLE_RELATIVE_PATH,
            root / "Sparkle.framework",
        )
        metadata = {
            "application": str(app),
            "version": version,
            "asar_sha256": hashlib.sha256(asar).hexdigest(),
            "sparkle_framework": True,
            "created_at": _now(),
        }
        self._atomic_replace_bytes(
            root / "metadata.json",
            (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode(),
            mode=0o600,
        )
        return root

    @staticmethod
    def _atomic_replace_bytes(path: Path, content: bytes, mode: int | None = None) -> None:
        original_mode = path.stat().st_mode & 0o777 if path.exists() else (mode or 0o600)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode or original_mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _backup_directory_once(source: Path, destination: Path) -> None:
        if destination.exists():
            return
        temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
        try:
            shutil.copytree(source, temporary, symlinks=True)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    @staticmethod
    def _replace_directory_from_backup(source: Path, target: Path) -> None:
        staging_root = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.restore-", dir=target.parent)
        )
        staged = staging_root / target.name
        displaced = target.parent / f".{target.name}.rollback-{uuid.uuid4().hex}"
        replacement_complete = False
        target_moved = False
        try:
            shutil.copytree(source, staged, symlinks=True)
            if target.exists():
                os.replace(target, displaced)
                target_moved = True
            try:
                os.replace(staged, target)
                replacement_complete = True
            except Exception:
                if target_moved and not target.exists():
                    os.replace(displaced, target)
                raise
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
            if replacement_complete and displaced.exists():
                shutil.rmtree(displaced, ignore_errors=True)

    def _restore_codex_app_patch(self, app: Path, backup_dir: Path) -> str:
        targets = (
            ("app.asar", app / "Contents/Resources/app.asar"),
            ("Info.plist", app / "Contents/Info.plist"),
            ("ChatGPT", app / "Contents/MacOS/ChatGPT"),
            ("codex", app / "Contents/Resources/codex"),
            ("CodeResources", app / "Contents/_CodeSignature/CodeResources"),
        )
        try:
            for name, target in targets:
                self._atomic_replace_bytes(target, (backup_dir / name).read_bytes())
            sparkle_backup = backup_dir / "Sparkle.framework"
            if sparkle_backup.is_dir():
                self._replace_directory_from_backup(
                    sparkle_backup,
                    app / CODEX_SPARKLE_RELATIVE_PATH,
                )
            self._verify_codex_signature(app)
            return ""
        except Exception as exc:
            return str(exc) or type(exc).__name__

    @staticmethod
    def _codex_sparkle_sign_targets(app: Path) -> tuple[Path, ...]:
        sparkle = app / CODEX_SPARKLE_RELATIVE_PATH
        return tuple(
            sparkle if relative == Path(".") else sparkle / relative
            for relative, _ in CODEX_SPARKLE_SIGN_TARGETS
        )

    @staticmethod
    def _codesign_identity(path: Path) -> tuple[bool, str] | None:
        result = subprocess.run(
            ["/usr/bin/codesign", "-dv", "--verbose=4", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        output = result.stdout + result.stderr
        team = re.search(r"^TeamIdentifier=(.+)$", output, re.MULTILINE)
        team_id = team.group(1).strip() if team else ""
        return "Signature=adhoc" in output, team_id

    @classmethod
    def _codex_update_signatures_are_compatible(cls, app: Path) -> bool:
        app_identity = cls._codesign_identity(app)
        if app_identity is None:
            return False
        app_is_adhoc, app_team = app_identity
        if not app_is_adhoc and not app_team:
            return False
        for target in cls._codex_sparkle_sign_targets(app):
            target_identity = cls._codesign_identity(target)
            if target_identity is None:
                return False
            target_is_adhoc, target_team = target_identity
            if app_is_adhoc:
                if not target_is_adhoc:
                    return False
            elif target_is_adhoc or target_team != app_team:
                return False
        return True

    @classmethod
    def _sign_locally_modified_codex(cls, app: Path) -> None:
        entitlements = {
            "com.apple.security.app-sandbox": False,
            "com.apple.security.automation.apple-events": True,
            "com.apple.security.cs.allow-jit": True,
            "com.apple.security.cs.allow-unsigned-executable-memory": True,
            "com.apple.security.cs.disable-library-validation": True,
            "com.apple.security.device.audio-input": True,
            "com.apple.security.device.camera": True,
            "com.apple.security.files.user-selected.read-write": True,
            "com.apple.security.network.client": True,
        }
        descriptor, name = tempfile.mkstemp(prefix="maolocal-codex-entitlements-", suffix=".plist")
        path = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                plistlib.dump(entitlements, handle)
            sparkle = app / CODEX_SPARKLE_RELATIVE_PATH
            for relative, preserve_entitlements in CODEX_SPARKLE_SIGN_TARGETS:
                target = sparkle if relative == Path(".") else sparkle / relative
                command = [
                    "/usr/bin/codesign",
                    "--force",
                    "--sign",
                    "-",
                    "--options",
                    "runtime",
                ]
                if preserve_entitlements:
                    command.append("--preserve-metadata=entitlements")
                command.append(str(target))
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr.strip() or f"本地代码签名失败：{target.name}"
                    )
            result = subprocess.run(
                [
                    "/usr/bin/codesign",
                    "--force",
                    "--sign",
                    "-",
                    "--options",
                    "runtime",
                    "--entitlements",
                    str(path),
                    str(app),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "本地代码签名失败：ChatGPT.app")
            if not cls._codex_update_signatures_are_compatible(app):
                raise RuntimeError("Codex 与 Sparkle 更新组件的本地签名身份不一致")
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def _verify_codex_signature(app: Path) -> None:
        result = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Codex 本地签名校验失败")

    @staticmethod
    def codex_running() -> bool:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", 'application id "com.openai.codex" is running'],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "true"

    def _bundled_catalog(self) -> list[dict[str, Any]]:
        candidates = [
            CODEX_APP / "Contents/Resources/codex",
            Path(shutil.which("codex") or ""),
        ]
        for binary in candidates:
            if not binary.is_file():
                continue
            stat = binary.stat()
            cache_key = (str(binary), stat.st_size, stat.st_mtime_ns)
            if self._bundled_catalog_cache_key == cache_key and self._bundled_catalog_cache is not None:
                return copy.deepcopy(self._bundled_catalog_cache)
            try:
                result = subprocess.run(
                    [str(binary), "debug", "models", "--bundled"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env=self._codex_environment(),
                )
                payload = json.loads(result.stdout)
                models = payload.get("models", [])
                if isinstance(models, list) and models:
                    self._bundled_catalog_cache = [
                        item for item in models if isinstance(item, dict)
                    ]
                    self._bundled_catalog_cache_key = cache_key
                    return copy.deepcopy(self._bundled_catalog_cache)
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                continue
        return []

    def _official_catalog_models(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in self._bundled_catalog()
            if str(item.get("visibility", "")) == "list" and item.get("slug")
        ]
