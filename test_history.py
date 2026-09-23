from test_support import *


class AccountManagerTests(AccountManagerTestBase):
    def write_rollout(self, relative, thread_id, provider, body=b'{"type":"response_item","payload":{"text":"unchanged"}}\n'):
        path = self.paths.codex_home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = json.dumps(
            {"type": "session_meta", "payload": {"id": thread_id, "model_provider": provider}},
            separators=(",", ":"),
        ).encode() + b"\n"
        path.write_bytes(meta + body)
        return path, body

    def create_state_db(self, relative="state_5.sqlite"):
        path = self.paths.codex_home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE threads (id TEXT PRIMARY KEY, model_provider TEXT NOT NULL, archived INTEGER NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO threads VALUES (?, ?, ?)",
            [("thread-a", "old-a", 0), ("thread-b", "old-b", 1)],
        )
        connection.commit()
        connection.close()
        return path

    def test_claim_all_scans_active_archived_without_persistent_backup(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        active, active_body = self.write_rollout(
            "sessions/2026/08/13/a.jsonl", "thread-a", "old-a"
        )
        archived, archived_body = self.write_rollout(
            "archived_sessions/b.jsonl", "thread-b", "old-b"
        )
        database = self.create_state_db()

        state = self.manager.state()["conversations"]
        self.assertEqual((state["threads"], state["active"], state["archived"]), (2, 1, 1))
        self.assertEqual(state["unassigned"], 2)
        result = self.manager.claim_all_conversations("MaoLocal")

        self.assertEqual(result["changed_files"], 2)
        self.assertEqual(result["sqlite_rows_updated"], 2)
        for path, body in ((active, active_body), (archived, archived_body)):
            first, remainder = path.read_bytes().split(b"\n", 1)
            self.assertEqual(json.loads(first)["payload"]["model_provider"], "MaoLocal")
            self.assertEqual(remainder, body)
        with sqlite3.connect(database) as connection:
            providers = {row[0] for row in connection.execute("SELECT model_provider FROM threads")}
        self.assertEqual(providers, {"MaoLocal"})
        self.assertNotIn("backup_dir", result)
        self.assertFalse(any(self.paths.app_home.glob("history-rollback-*")))

    def test_sub2api_claim_history_uses_stable_provider_id_for_jsonl_and_sqlite(self):
        self.save_account(
            "Sub Pool Display Name",
            "stable_sub2api_provider",
            connection_type="sub2api",
            auth_mode="legacy",
            transport="http_sse",
        )
        self.manager.activate_account("Sub Pool Display Name")
        active, _ = self.write_rollout(
            "sessions/sub2api.jsonl",
            "thread-a",
            "old-provider",
        )
        database = self.create_state_db()

        self.manager.claim_all_conversations("Sub Pool Display Name")

        first = json.loads(active.read_text().splitlines()[0])
        self.assertEqual(
            first["payload"]["model_provider"],
            "stable_sub2api_provider",
        )
        with sqlite3.connect(database) as connection:
            providers = {row[0] for row in connection.execute("SELECT model_provider FROM threads")}
        self.assertEqual(providers, {"stable_sub2api_provider"})

    def test_claim_all_rewrites_every_session_meta_and_preserves_other_lines(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        path = self.paths.codex_home / "sessions/multiple.jsonl"
        path.parent.mkdir(parents=True)
        lines = [
            json.dumps({"type": "session_meta", "payload": {"id": "thread-a", "model_provider": "old-a"}}, separators=(",", ":")),
            json.dumps({"type": "response_item", "payload": {"text": "unchanged"}}, separators=(",", ":")),
            json.dumps({"type": "session_meta", "payload": {"id": "thread-a", "model_provider": "old-b"}}, separators=(",", ":")),
            json.dumps({"type": "event_msg", "payload": {"value": 1}}, separators=(",", ":")),
        ]
        path.write_text("\n".join(lines) + "\n")
        untouched = [lines[1].encode(), lines[3].encode()]

        result = self.manager.claim_all_conversations("MaoLocal")
        records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(result["changed_files"], 1)
        self.assertEqual(result["session_meta_rows_updated"], 2)
        self.assertTrue(
            all(
                record["payload"]["model_provider"] == "MaoLocal"
                for record in records
                if record["type"] == "session_meta"
            )
        )
        raw_lines = path.read_bytes().splitlines()
        self.assertEqual([raw_lines[1], raw_lines[3]], untouched)

    def test_claim_all_is_idempotent_and_history_state_is_private(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        self.write_rollout("sessions/a.jsonl", "thread-a", "MaoLocal")
        database = self.create_state_db()
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE threads SET model_provider = 'MaoLocal'")
            connection.commit()

        result = self.manager.claim_all_conversations("MaoLocal")
        self.assertEqual(result["changed_files"], 0)
        self.assertEqual(result["sqlite_rows_updated"], 0)
        self.assertEqual(self.paths.history_state.stat().st_mode & 0o777, 0o600)

    def test_idempotent_verification_records_latest_result_without_backup(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        self.write_rollout("sessions/a.jsonl", "thread-a", "old")
        first = self.manager.claim_all_conversations("MaoLocal")
        second = self.manager.claim_all_conversations("MaoLocal")
        persisted = json.loads(self.paths.history_state.read_text())
        self.assertEqual(first["changed_files"], 1)
        self.assertEqual(second["changed_files"], 0)
        self.assertEqual(persisted["changed_files"], 0)
        self.assertNotIn("backup_dir", first)
        self.assertNotIn("backup_dir", persisted)

    def test_claim_all_rejects_non_active_account(self):
        self.save_account("MaoLocal", "MaoLocal")
        self.manager.activate_account("MaoLocal")
        self.save_account("Other", "Other")
        with self.assertRaisesRegex(ValueError, "当前已启用账号"):
            self.manager.claim_all_conversations("Other")

    def test_claim_all_skips_corrupt_rollout_without_blocking_valid_files(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        valid, body = self.write_rollout("sessions/a.jsonl", "thread-a", "old")
        broken = self.paths.codex_home / "archived_sessions/broken.jsonl"
        broken.parent.mkdir(parents=True)
        broken.write_text("not-json\n")
        before = broken.read_bytes()

        result = self.manager.claim_all_conversations("MaoLocal")
        self.assertEqual(result["changed_files"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(broken.read_bytes(), before)
        self.assertEqual(valid.read_bytes().split(b"\n", 1)[1], body)

    def test_claim_all_rolls_back_first_database_when_second_database_fails(self):
        self.save_account()
        self.manager.activate_account("MaoLocal")
        rollout, body = self.write_rollout("sessions/a.jsonl", "thread-a", "old")
        first = self.create_state_db("state_5.sqlite")
        second = self.create_state_db("sqlite/state_5.sqlite")
        original_update = self.manager._update_database_providers

        def fail_on_second(targets, provider_id, backup_dir):
            broken_targets = [targets[0], (second, ("missing_table",))]
            return original_update(broken_targets, provider_id, backup_dir)

        with patch.object(self.manager, "_update_database_providers", side_effect=fail_on_second):
            with self.assertRaises(sqlite3.OperationalError):
                self.manager.claim_all_conversations("MaoLocal")

        self.assertEqual(json.loads(rollout.read_bytes().split(b"\n", 1)[0])["payload"]["model_provider"], "old")
        self.assertEqual(rollout.read_bytes().split(b"\n", 1)[1], body)
        with sqlite3.connect(first) as connection:
            providers = {row[0] for row in connection.execute("SELECT model_provider FROM threads")}
        self.assertEqual(providers, {"old-a", "old-b"})
