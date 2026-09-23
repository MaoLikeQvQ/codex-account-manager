from __future__ import annotations

from .common import *
from .common import _now


class HistoryMixin:
    def claim_all_conversations(self, account_name: str | None = None) -> dict[str, Any]:
        """把 Codex 原生会话 Provider 元数据统一到指定账号。"""
        store = self._load_store()
        name = (account_name or str(store.get("active_account", ""))).strip()
        account = store["accounts"].get(name)
        if not isinstance(account, dict):
            raise KeyError(f"账号不存在：{name}")
        if name != str(store.get("active_account", "")):
            raise ValueError("只能归纳到当前已启用账号")
        provider_id = str(account.get("provider_id", "")).strip()
        if not provider_id:
            raise ValueError("当前账号缺少 Provider ID")

        rollouts, errors = self._scan_rollouts(
            detect_encrypted_content=True,
            force_refresh=True,
        )
        counts = self._rollout_counts(rollouts, provider_id)
        changes = [
            item for item in rollouts if any(provider != provider_id for provider in item.provider_ids)
        ]
        database_targets = self._provider_database_targets()
        database_rows_pending = sum(
            self._count_database_provider_updates(path, tables, provider_id)
            for path, tables in database_targets
        )
        encrypted_content_files = sum(
            item.has_encrypted_content
            and any(provider != provider_id for provider in item.provider_ids)
            for item in rollouts
        )
        if not changes and database_rows_pending == 0:
            verified_at = _now()
            result = {
                "account": name,
                "provider_id": provider_id,
                "total": counts["threads"],
                "active": counts["active"],
                "archived": counts["archived"],
                "already_assigned": counts["assigned"],
                "changed_files": 0,
                "session_meta_rows_updated": 0,
                "sqlite_rows_updated": 0,
                "failed": len(errors),
                "encrypted_content_files": encrypted_content_files,
                "updated_at": verified_at,
            }
            self._record_history_state("ok" if not errors else "partial", result)
            return result

        backup_dir = self._create_history_rollback(changes, database_targets, provider_id)
        applied: list[RolloutRecord] = []
        session_meta_rows_updated = 0
        try:
            for item in changes:
                applied.append(item)
                session_meta_rows_updated += self._rewrite_rollout_provider(item, provider_id)
            sqlite_rows = self._update_database_providers(
                database_targets,
                provider_id,
                backup_dir,
            )
        except Exception:
            for item in reversed(applied):
                try:
                    self._restore_rollout_from_backup(item, backup_dir)
                except Exception:
                    pass
            self._record_history_state(
                "error",
                {
                    "account": name,
                    "provider_id": provider_id,
                    "total": counts["threads"],
                    "changed_files": len(applied),
                    "session_meta_rows_updated": session_meta_rows_updated,
                    "failed": 1,
                    "updated_at": _now(),
                },
            )
            raise
        finally:
            shutil.rmtree(backup_dir, ignore_errors=True)

        result = {
            "account": name,
            "provider_id": provider_id,
            "total": counts["threads"],
            "active": counts["active"],
            "archived": counts["archived"],
            "already_assigned": counts["assigned"],
            "changed_files": len(changes),
            "session_meta_rows_updated": session_meta_rows_updated,
            "sqlite_rows_updated": sqlite_rows,
            "failed": len(errors),
            "encrypted_content_files": encrypted_content_files,
            "updated_at": _now(),
        }
        self._record_history_state("ok" if not errors else "partial", result)
        return result

    def _conversation_state(self) -> dict[str, Any]:
        rollouts, errors = self._scan_rollouts()
        providers = Counter(
            provider if provider is not None else "<missing>"
            for item in rollouts
            for provider in item.provider_ids
        )
        active_provider = str(self._read_toml(self.paths.config).get("model_provider", ""))
        counts = self._rollout_counts(rollouts, active_provider)
        history_state = self._read_json(self.paths.history_state, {})
        latest_ns = max(
            [item.mtime_ns for item in rollouts]
            + [int(item.get("mtime_ns", 0)) for item in errors],
            default=0,
        )
        return {
            "files": len(rollouts) + len(errors),
            "threads": counts["threads"],
            "active": counts["active"],
            "archived": counts["archived"],
            "bytes": sum(item.size for item in rollouts)
            + sum(int(item.get("size", 0)) for item in errors),
            "assigned_to_active_account": counts["assigned"],
            "unassigned": counts["threads"] - counts["assigned"],
            "providers": dict(sorted(providers.items())),
            "failed": len(errors),
            "encrypted_content_files": int(history_state.get("encrypted_content_files", 0))
            if isinstance(history_state, dict)
            else 0,
            "latest_at": datetime.fromtimestamp(latest_ns / 1_000_000_000)
            .astimezone()
            .isoformat(timespec="minutes")
            if latest_ns
            else "",
            "last_claim": history_state if isinstance(history_state, dict) else {},
        }

    @staticmethod
    def _rollout_counts(records: list[RolloutRecord], provider_id: str) -> dict[str, int]:
        by_thread: dict[str, list[RolloutRecord]] = {}
        for item in records:
            by_thread.setdefault(item.thread_id, []).append(item)
        active = sum(any(not item.archived for item in items) for items in by_thread.values())
        assigned = sum(
            all(
                provider == provider_id
                for item in items
                for provider in item.provider_ids
            )
            for items in by_thread.values()
        )
        return {
            "threads": len(by_thread),
            "active": active,
            "archived": len(by_thread) - active,
            "assigned": assigned,
        }

    def _scan_rollouts(
        self,
        detect_encrypted_content: bool = False,
        force_refresh: bool = False,
    ) -> tuple[list[RolloutRecord], list[dict[str, Any]]]:
        records: list[RolloutRecord] = []
        errors: list[dict[str, Any]] = []
        current_paths: set[Path] = set()
        for dirname, archived in (("sessions", False), ("archived_sessions", True)):
            root = self.paths.codex_home / dirname
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.jsonl")):
                current_paths.add(path)
                try:
                    stat_before = path.stat()
                    signature = (
                        stat_before.st_ino,
                        stat_before.st_size,
                        stat_before.st_mtime_ns,
                        archived,
                    )
                    cached = self._rollout_cache.get(path)
                    if (
                        not force_refresh
                        and not detect_encrypted_content
                        and cached is not None
                        and cached[0] == signature
                    ):
                        records.append(cached[1])
                        continue
                    cached_error = self._rollout_error_cache.get(path)
                    if (
                        not force_refresh
                        and not detect_encrypted_content
                        and cached_error is not None
                        and cached_error[0] == signature
                    ):
                        errors.append(dict(cached_error[1]))
                        continue
                    line = self._read_session_meta_line(path)
                    item = json.loads(line)
                    payload = item.get("payload") if isinstance(item, dict) else None
                    if not isinstance(item, dict) or item.get("type") != "session_meta" or not isinstance(payload, dict):
                        raise ValueError("首条记录不是 session_meta")
                    thread_id = payload.get("id")
                    if not isinstance(thread_id, str) or not thread_id.strip():
                        raise ValueError("session_meta 缺少 thread id")
                    provider = payload.get("model_provider", payload.get("modelProvider"))
                    if provider is not None and not isinstance(provider, str):
                        raise ValueError("session_meta Provider 类型无效")
                    provider_ids: list[str | None] = []
                    with path.open("rb") as handle:
                        for raw_line in handle:
                            if b'"session_meta"' not in raw_line:
                                continue
                            candidate = json.loads(raw_line)
                            if not isinstance(candidate, dict) or candidate.get("type") != "session_meta":
                                continue
                            candidate_payload = candidate.get("payload")
                            if not isinstance(candidate_payload, dict):
                                raise ValueError("session_meta payload 类型无效")
                            candidate_provider = candidate_payload.get(
                                "model_provider",
                                candidate_payload.get("modelProvider"),
                            )
                            if candidate_provider is not None and not isinstance(candidate_provider, str):
                                raise ValueError("session_meta Provider 类型无效")
                            provider_ids.append(candidate_provider)
                    if not provider_ids:
                        raise ValueError("会话文件没有 session_meta")
                    stat_after = path.stat()
                    if (
                        stat_after.st_ino,
                        stat_after.st_size,
                        stat_after.st_mtime_ns,
                    ) != signature[:3]:
                        raise RuntimeError("会话在扫描过程中发生变化")
                    record = RolloutRecord(
                        path=path,
                        archived=archived,
                        thread_id=thread_id,
                            provider_id=provider,
                            provider_ids=tuple(provider_ids),
                            size=stat_after.st_size,
                        inode=stat_after.st_ino,
                        mode=stat_after.st_mode & 0o777,
                        atime_ns=stat_after.st_atime_ns,
                        mtime_ns=stat_after.st_mtime_ns,
                        has_encrypted_content=detect_encrypted_content
                        and self._file_contains(path, b'"encrypted_content"', start=len(line)),
                    )
                    records.append(record)
                    self._rollout_cache[path] = (signature, record)
                    self._rollout_error_cache.pop(path, None)
                except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                    try:
                        stat = path.stat()
                        size, mtime_ns = stat.st_size, stat.st_mtime_ns
                        signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns, archived)
                    except OSError:
                        size, mtime_ns = 0, 0
                        signature = (0, 0, 0, archived)
                    error = {
                        "path": str(path),
                        "error": str(exc),
                        "size": size,
                        "mtime_ns": mtime_ns,
                    }
                    errors.append(error)
                    self._rollout_error_cache[path] = (signature, error)
                    self._rollout_cache.pop(path, None)
        for cache in (self._rollout_cache, self._rollout_error_cache):
            for path in set(cache) - current_paths:
                del cache[path]
        return records, errors

    @staticmethod
    def _read_session_meta_line(path: Path) -> bytes:
        with path.open("rb") as handle:
            line = handle.readline(MAX_SESSION_META_BYTES + 1)
        if not line:
            raise ValueError("会话文件为空")
        if len(line) > MAX_SESSION_META_BYTES:
            raise ValueError("session_meta 超过大小限制")
        return line

    @staticmethod
    def _file_contains(path: Path, marker: bytes, start: int = 0) -> bool:
        overlap = b""
        with path.open("rb") as handle:
            handle.seek(start)
            while chunk := handle.read(1024 * 1024):
                data = overlap + chunk
                if marker in data:
                    return True
                overlap = data[-max(len(marker) - 1, 0) :]
        return False

    def _rewrite_rollout_provider(self, item: RolloutRecord, provider_id: str) -> int:
        stat = item.path.stat()
        if stat.st_ino != item.inode or stat.st_size != item.size or stat.st_mtime_ns != item.mtime_ns:
            raise RuntimeError(f"会话在扫描后发生变化：{item.path.name}")
        updated = 0
        fd, temporary = tempfile.mkstemp(prefix=f".{item.path.name}.", dir=item.path.parent)
        try:
            with os.fdopen(fd, "wb") as destination, item.path.open("rb") as source:
                for raw_line in source:
                    next_line = raw_line
                    if b'"session_meta"' in raw_line:
                        candidate = json.loads(raw_line)
                        if isinstance(candidate, dict) and candidate.get("type") == "session_meta":
                            payload = candidate.get("payload")
                            if not isinstance(payload, dict):
                                raise ValueError("session_meta payload 类型无效")
                            current = payload.get("model_provider", payload.get("modelProvider"))
                            if current != provider_id or "modelProvider" in payload:
                                newline = (
                                    b"\r\n"
                                    if raw_line.endswith(b"\r\n")
                                    else b"\n"
                                    if raw_line.endswith(b"\n")
                                    else b""
                                )
                                payload["model_provider"] = provider_id
                                payload.pop("modelProvider", None)
                                next_line = (
                                    json.dumps(
                                        candidate,
                                        ensure_ascii=False,
                                        separators=(",", ":"),
                                    ).encode("utf-8")
                                    + newline
                                )
                                updated += 1
                    destination.write(next_line)
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary, item.mode)
            os.replace(temporary, item.path)
            os.utime(item.path, ns=(item.atime_ns, item.mtime_ns))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return updated

    def _restore_rollout_from_backup(self, item: RolloutRecord, backup_dir: Path) -> None:
        source = backup_dir / "sessions" / item.path.relative_to(self.paths.codex_home)
        fd, temporary = tempfile.mkstemp(prefix=f".{item.path.name}.", dir=item.path.parent)
        try:
            with source.open("rb") as backup, os.fdopen(fd, "wb") as destination:
                shutil.copyfileobj(backup, destination, 1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(temporary, item.mode)
            os.replace(temporary, item.path)
            os.utime(item.path, ns=(item.atime_ns, item.mtime_ns))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _provider_database_targets(self) -> list[tuple[Path, tuple[str, ...]]]:
        candidates: list[Path] = []
        for root in (self.paths.codex_home, self.paths.codex_home / "sqlite"):
            if root.is_dir():
                candidates.extend(
                    path
                    for path in root.iterdir()
                    if path.is_file() and path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}
                )
        targets: list[tuple[Path, tuple[str, ...]]] = []
        for path in sorted(set(candidates)):
            if not path.is_file():
                continue
            with self._sqlite_connection(path, readonly=True) as connection:
                tables = tuple(
                    table
                    for table in ("threads", "local_thread_catalog")
                    if "model_provider" in self._table_columns(connection, table)
                )
            if tables:
                targets.append((path, tables))
        return targets

    @staticmethod
    def _sqlite_connection(path: Path, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15)
        else:
            connection = sqlite3.connect(path, timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
        existing = connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if not existing:
            return set()
        return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}

    def _count_database_provider_updates(
        self,
        path: Path,
        tables: tuple[str, ...],
        provider_id: str,
    ) -> int:
        with self._sqlite_connection(path, readonly=True) as connection:
            return sum(
                int(
                    connection.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE COALESCE(model_provider, \'\') <> ?',
                        (provider_id,),
                    ).fetchone()[0]
                )
                for table in tables
            )

    def _create_history_rollback(
        self,
        changes: list[RolloutRecord],
        database_targets: list[tuple[Path, tuple[str, ...]]],
        provider_id: str,
    ) -> Path:
        backup_dir = Path(
            tempfile.mkdtemp(prefix="history-rollback-", dir=self.paths.app_home)
        )
        os.chmod(backup_dir, 0o700)
        session_manifest = [
            {
                "path": str(item.path),
                "thread_id": item.thread_id,
                "provider_id": item.provider_id,
                "session_meta": self._read_session_meta_line(item.path).decode("utf-8"),
                "size": item.size,
                "mode": item.mode,
                "mtime_ns": item.mtime_ns,
            }
            for item in changes
        ]
        self._write_private_json(backup_dir / "session-meta.json", session_manifest)
        for item in changes:
            relative = item.path.relative_to(self.paths.codex_home)
            destination = backup_dir / "sessions" / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            clone = subprocess.run(
                ["/bin/cp", "-c", str(item.path), str(destination)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if clone.returncode != 0:
                shutil.copy2(item.path, destination)
            os.chmod(destination, 0o600)
        database_manifest: list[dict[str, Any]] = []
        for index, (path, tables) in enumerate(database_targets):
            destination = backup_dir / "sqlite" / f"{index}-{path.name}"
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._sqlite_connection(path, readonly=True) as source:
                source.execute("PRAGMA query_only = ON")
                destination_connection = sqlite3.connect(destination)
                try:
                    source.backup(destination_connection)
                finally:
                    destination_connection.close()
            os.chmod(destination, 0o600)
            database_manifest.append(
                {"path": str(path), "backup": str(destination.relative_to(backup_dir)), "tables": tables}
            )
        self._write_private_json(
            backup_dir / "manifest.json",
            {
                "version": 1,
                "target_provider": provider_id,
                "created_at": _now(),
                "changed_session_files": len(changes),
                "databases": database_manifest,
                "managed_by": "MaoLocal Codex Manager",
            },
        )
        return backup_dir

    def _update_database_providers(
        self,
        targets: list[tuple[Path, tuple[str, ...]]],
        provider_id: str,
        backup_dir: Path,
    ) -> int:
        updated = 0
        completed: list[tuple[Path, Path]] = []
        manifest = self._read_json(backup_dir / "manifest.json", {})
        backup_by_path = {
            str(item["path"]): backup_dir / str(item["backup"])
            for item in manifest.get("databases", [])
            if isinstance(item, dict) and item.get("path") and item.get("backup")
        }
        try:
            for path, tables in targets:
                with self._sqlite_connection(path) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        for table in tables:
                            cursor = connection.execute(
                                f'UPDATE "{table}" SET model_provider = ? '
                                "WHERE COALESCE(model_provider, '') <> ?",
                                (provider_id, provider_id),
                            )
                            updated += cursor.rowcount
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
                completed.append((path, backup_by_path[str(path)]))
        except Exception:
            for path, backup in reversed(completed):
                with self._sqlite_connection(backup, readonly=True) as source:
                    destination = self._sqlite_connection(path)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
            raise
        return updated

    def _record_history_state(self, status: str, result: dict[str, Any]) -> None:
        payload = {"status": status, **result}
        self._write_private_json(self.paths.history_state, payload)
