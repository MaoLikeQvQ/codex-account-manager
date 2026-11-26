from test_support import AccountManagerTestBase, json, patch, sqlite3, subprocess


class AutomaticHistoryTests(AccountManagerTestBase):
    def rollout(self, relative, thread_id, provider):
        path = self.paths.codex_home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        body = b'{"type":"response_item","payload":{"text":"keep"}}\n'
        header = json.dumps({"type": "session_meta", "payload": {
            "id": thread_id, "model_provider": provider,
        }}).encode() + b"\n"
        path.write_bytes(header + body)
        return path, body

    def database(self):
        path = self.paths.codex_home / "state_5.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, model_provider TEXT, archived INTEGER)")
            db.executemany("INSERT INTO threads VALUES (?, ?, ?)", [
                ("active", "openai", 0), ("archived", "openai", 1),
            ])
        return path

    def provider(self, path):
        return json.loads(path.read_bytes().split(b"\n", 1)[0])["payload"]["model_provider"]

    def test_switch_assigns_active_archived_and_database_when_no_writer(self):
        self.save_account("Channel")
        active, active_body = self.rollout("sessions/a.jsonl", "active", "openai")
        archived, archived_body = self.rollout("archived_sessions/b.jsonl", "archived", "openai")
        database = self.database()
        with patch.object(self.manager, "codex_running", return_value=False), \
             patch.object(self.manager, "_history_writers_running", return_value=False, create=True):
            result = self.manager.activate_account("Channel")
        self.assertEqual(result.get("history", {}).get("status"), "completed")
        self.assertEqual([self.provider(active), self.provider(archived)], ["MaoLocal", "MaoLocal"])
        self.assertEqual(active.read_bytes().split(b"\n", 1)[1], active_body)
        self.assertEqual(archived.read_bytes().split(b"\n", 1)[1], archived_body)
        with sqlite3.connect(database) as db:
            self.assertEqual({row[0] for row in db.execute("SELECT model_provider FROM threads")}, {"MaoLocal"})
        self.assertFalse(self.manager._load_store().get("pending_history_claim"))

    def test_running_client_does_not_defer_history(self):
        self.save_account("Channel")
        path, _ = self.rollout("sessions/a.jsonl", "active", "openai")
        with patch.object(self.manager, "codex_running", return_value=True):
            result = self.manager.activate_account("Channel")
        self.assertEqual(result["history"]["status"], "completed")
        self.assertEqual(self.provider(path), "MaoLocal")

    def test_failure_keeps_account_switch_and_records_retryable_history(self):
        self.save_account("Channel")
        path, body = self.rollout("sessions/a.jsonl", "active", "openai")
        with patch.object(self.manager, "codex_running", return_value=False), \
             patch.object(self.manager, "_history_writers_running", return_value=False, create=True), \
             patch.object(self.manager, "_update_database_providers", side_effect=OSError("failure")):
            result = self.manager.activate_account("Channel")
        self.assertEqual(result.get("history", {}).get("status"), "error")
        self.assertEqual(self.manager._load_store()["active_account"], "Channel")
        self.assertEqual(self.manager._load_store()["pending_history_claim"]["status"], "error")
        self.assertEqual(self.provider(path), "openai")
        self.assertEqual(path.read_bytes().split(b"\n", 1)[1], body)

    def test_corrupt_file_reports_partial_and_preserves_pending_retry(self):
        self.save_account("Channel")
        path, _ = self.rollout("sessions/a.jsonl", "active", "openai")
        broken = self.paths.codex_home / "archived_sessions/broken.jsonl"
        broken.parent.mkdir(parents=True)
        broken.write_text("not-json\n")
        with patch.object(self.manager, "codex_running", return_value=False), \
             patch.object(self.manager, "_history_writers_running", return_value=False, create=True):
            result = self.manager.activate_account("Channel")
        self.assertEqual(result.get("history", {}).get("status"), "partial")
        self.assertEqual(result["history"]["failed"], 1)
        self.assertEqual(self.provider(path), "MaoLocal")
        self.assertEqual(broken.read_text(), "not-json\n")
        self.assertEqual(self.manager._load_store()["pending_history_claim"]["status"], "partial")

    def test_automatic_claim_closes_database_connections_before_returning(self):
        self.save_account("Channel")
        self.rollout("sessions/a.jsonl", "active", "openai")
        self.database()
        original = self.manager._sqlite_connection
        connections = []

        def track(*args, **kwargs):
            connection = original(*args, **kwargs)
            connections.append(connection)
            return connection

        with patch.object(self.manager, "codex_running", return_value=False), \
             patch.object(self.manager, "_sqlite_connection", side_effect=track):
            self.manager.activate_account("Channel")
        self.assertGreater(len(connections), 0)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_concurrent_append_is_not_overwritten_when_rewrite_rejects_changed_file(self):
        self.save_account("Channel")
        path, body = self.rollout("sessions/a.jsonl", "active", "openai")
        original = self.manager._rewrite_rollout_provider
        appended = b'{"type":"event_msg","payload":{"new":true}}\n'

        def append_before_rewrite(item, provider):
            with item.path.open("ab") as stream:
                stream.write(appended)
            return original(item, provider)

        with patch.object(self.manager, "codex_running", return_value=False), \
             patch.object(self.manager, "_rewrite_rollout_provider", side_effect=append_before_rewrite):
            result = self.manager.activate_account("Channel")
        self.assertEqual(result["history"]["status"], "error")
        self.assertEqual(self.provider(path), "openai")
        self.assertEqual(path.read_bytes().split(b"\n", 1)[1], body + appended)

    def test_rollback_preserves_an_append_to_an_already_rewritten_file(self):
        self.save_account("Channel")
        first, body = self.rollout("sessions/a.jsonl", "first", "openai")
        second, _ = self.rollout("sessions/b.jsonl", "second", "openai")
        original = self.manager._rewrite_rollout_provider
        appended = b'{"type":"event_msg","payload":{"new":true}}\n'

        def fail_on_second(item, provider):
            if item.path == second:
                with first.open("ab") as stream:
                    stream.write(appended)
                raise OSError("simulated failure")
            return original(item, provider)

        with patch.object(self.manager, "codex_running", return_value=False), \
             patch.object(self.manager, "_rewrite_rollout_provider", side_effect=fail_on_second):
            result = self.manager.activate_account("Channel")
        self.assertEqual(result["history"]["status"], "error")
        self.assertEqual(first.read_bytes().split(b"\n", 1)[1], body + appended)
        self.assertEqual(self.provider(second), "openai")

    def test_manual_retry_clears_partial_pending_status(self):
        self.save_account("Channel")
        self.rollout("sessions/a.jsonl", "active", "openai")
        broken = self.paths.codex_home / "archived_sessions/broken.jsonl"
        broken.parent.mkdir(parents=True)
        broken.write_text("not-json\n")
        with patch.object(self.manager, "codex_running", return_value=False):
            self.assertEqual(self.manager.activate_account("Channel")["history"]["status"], "partial")
            broken.write_text(json.dumps({"type": "session_meta", "payload": {
                "id": "fixed", "model_provider": "openai",
            }}) + "\n")
            result = self.manager.claim_all_conversations("Channel")
        self.assertEqual(result["failed"], 0)
        self.assertEqual(self.provider(broken), "MaoLocal")
        self.assertFalse(self.manager._load_store().get("pending_history_claim"))
