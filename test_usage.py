import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from codex_manager import CodexManager, Paths
from manager_parts.usage import summarize_range, summarize_today


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.temporary.cleanup()

    def write_rollout(self, name, provider, events):
        path = self.home / "sessions" / "2026" / "09" / "23" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [{"type": "session_meta", "payload": {"model_provider": provider}}] + events
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        return path

    def token_event(self, timestamp, total, last):
        def usage(values):
            return {
                "input_tokens": values[0],
                "cached_input_tokens": values[1],
                "cache_write_input_tokens": values[2],
                "output_tokens": values[3],
                **({"reasoning_output_tokens": values[4]} if len(values) > 4 else {}),
            }
        return {
            "timestamp": timestamp,
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {"total_token_usage": usage(total), "last_token_usage": usage(last)},
            },
        }

    def test_today_usage_deduplicates_cumulative_events_and_prices_api(self):
        self.write_rollout("a.jsonl", "vendor", [
            {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
            self.token_event("2026-09-22T23:00:00Z", (100, 20, 0, 10), (100, 20, 0, 10)),
            self.token_event("2026-09-23T08:00:00Z", (200, 70, 0, 20), (100, 50, 0, 10)),
            self.token_event("2026-09-23T08:00:01Z", (200, 70, 0, 20), (100, 50, 0, 10)),
            self.token_event("2026-09-23T09:00:00Z", (300, 100, 10, 30), (100, 30, 10, 10)),
        ])
        self.write_rollout("other.jsonl", "other", [
            self.token_event("2026-09-23T09:00:00Z", (900, 0, 0, 0), (900, 0, 0, 0)),
        ])

        result = summarize_today(self.home, "vendor", False, self.now)

        self.assertEqual(result["totals"]["input_tokens"], 200)
        self.assertEqual(result["totals"]["cached_input_tokens"], 80)
        self.assertEqual(result["totals"]["cache_write_input_tokens"], 10)
        self.assertEqual(result["totals"]["output_tokens"], 20)
        self.assertAlmostEqual(result["totals"]["estimated_cost"], .000461)
        self.assertEqual(result["totals"]["unpriced_tokens"], 0)
        self.assertEqual(result["unit"], "USD")

    def test_official_credits_and_unknown_model_are_kept_separate(self):
        self.write_rollout("a.jsonl", "openai", [
            {"type": "turn_context", "payload": {"model": "gpt-6-luna"}},
            self.token_event("2026-09-23T08:00:00Z", (1000, 500, 0, 100), (1000, 500, 0, 100)),
            {"type": "turn_context", "payload": {"model": "vendor-model"}},
            self.token_event("2026-09-23T09:00:00Z", (1100, 500, 0, 110), (100, 0, 0, 10)),
        ])

        result = summarize_today(self.home, "openai", True, self.now)

        self.assertEqual(result["unit"], "credits")
        self.assertAlmostEqual(result["totals"]["estimated_cost"], .002625)
        self.assertEqual(result["totals"]["unpriced_tokens"], 110)
        self.assertEqual([row["model"] for row in result["models"]], ["gpt-6-luna", "vendor-model"])

    def test_long_context_uses_long_rate_and_missing_rate_is_unpriced(self):
        self.write_rollout("a.jsonl", "vendor", [
            {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
            self.token_event("2026-09-23T08:00:00Z", (300000, 100000, 0, 1000), (300000, 100000, 0, 1000)),
            {"type": "turn_context", "payload": {"model": "gpt-5.4-mini"}},
            self.token_event("2026-09-23T09:00:00Z", (600000, 200000, 0, 2000), (300000, 100000, 0, 1000)),
        ])

        result = summarize_today(self.home, "vendor", False, self.now)

        self.assertAlmostEqual(result["totals"]["estimated_cost"], .855)
        self.assertEqual(result["totals"]["unpriced_tokens"], 301000)

    def test_range_includes_selected_days_without_double_counting(self):
        self.write_rollout("range.jsonl", "vendor", [
            {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
            self.token_event("2026-09-21T20:00:00Z", (100, 0, 0, 5), (100, 0, 0, 5)),
            self.token_event("2026-09-22T20:00:00Z", (200, 0, 0, 10), (100, 0, 0, 5)),
            self.token_event("2026-09-23T20:00:00Z", (300, 0, 0, 15), (100, 0, 0, 5)),
        ])
        start = self.now.replace(day=22, hour=0)
        end = start + timedelta(days=2)

        result = summarize_range(self.home, "vendor", False, start, end)

        self.assertEqual(result["date"], "2026-09-22")
        self.assertEqual(result["end_date"], "2026-09-23")
        self.assertEqual(result["totals"]["input_tokens"], 200)
        self.assertEqual(result["totals"]["output_tokens"], 10)

    def test_reasoning_is_deduplicated_and_included_in_output_price(self):
        self.write_rollout("reasoning.jsonl", "vendor", [
            {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
            self.token_event("2026-09-22T23:00:00Z", (100, 0, 0, 40, 30), (100, 0, 0, 40, 30)),
            self.token_event("2026-09-23T08:00:00Z", (200, 0, 0, 100, 80), (100, 0, 0, 60, 50)),
            self.token_event("2026-09-23T08:00:01Z", (200, 0, 0, 100, 80), (100, 0, 0, 60, 50)),
            # A reset starts a fresh cumulative counter.
            self.token_event("2026-09-23T09:00:00Z", (50, 0, 0, 20, 10), (50, 0, 0, 20, 10)),
        ])
        result = summarize_today(self.home, "vendor", False, self.now)
        self.assertEqual(result["totals"]["reasoning_output_tokens"], 60)
        self.assertEqual(result["models"][0]["reasoning_output_tokens"], 60)
        self.assertEqual(result["totals"]["output_tokens"], 80)
        self.assertEqual(result["totals"]["input_tokens"], 150)
        self.assertAlmostEqual(result["totals"]["estimated_cost"], .0011)
        credits = summarize_today(self.home, "vendor", True, self.now)
        self.assertAlmostEqual(credits["totals"]["estimated_cost"], .0275)

    def test_legacy_usage_without_reasoning_remains_valid(self):
        self.write_rollout("legacy.jsonl", "vendor", [
            {"type": "turn_context", "payload": {"model": "gpt-6-sol"}},
            self.token_event("2026-09-23T08:00:00Z", (100, 0, 0, 20), (100, 0, 0, 20)),
        ])
        result = summarize_today(self.home, "vendor", False, self.now)
        self.assertEqual(result["totals"]["reasoning_output_tokens"], 0)
        self.assertEqual(result["totals"]["output_tokens"], 20)
        self.assertAlmostEqual(result["totals"]["estimated_cost"], .0004)

    def test_manager_period_selection_validates_dates(self):
        manager = CodexManager(Paths(self.home, self.home / "manager"))
        store = {"active_account": "current", "accounts": {"current": {"account_type": "custom", "provider_id": "vendor"}}}
        with patch.object(manager, "_load_store", return_value=store), patch(
            "codex_manager.summarize_range", return_value={"ok": True}
        ) as summarize:
            self.assertEqual(manager.usage_for_period("date", "2026-09-22"), {"ok": True})
            start, end = summarize.call_args.args[-2:]
            self.assertEqual(start.date().isoformat(), "2026-09-22")
            self.assertEqual(end - start, timedelta(days=1))
            with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                manager.usage_for_period("date", "09/22/2026")
            with self.assertRaisesRegex(ValueError, "未来"):
                manager.usage_for_period("date", "2999-01-01")
            with self.assertRaisesRegex(ValueError, "不支持"):
                manager.usage_for_period("all")


if __name__ == "__main__":
    unittest.main()
