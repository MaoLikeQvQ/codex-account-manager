from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")
PRICE_SOURCE = "https://developers.openai.com/api/docs/pricing"
CREDIT_SOURCE = "https://learn.chatgpt.com/docs/pricing#token-rates"

# Standard-rate prices per million tokens: input, cached input, cache write, output.
API_PRICES = {
    "gpt-6-astra": ((10, 1, 12.5, 50), (20, 2, 25, 75)),
    "gpt-6-sol": ((2, .2, 2.5, 10), (4, .4, 5, 15)),
    "gpt-6-luna": ((.1, .01, .125, .5), (.2, .02, .25, .75)),
    "gpt-5.6-sol": ((4, .4, 5, 20), (8, .8, 10, 30)),
    "gpt-5.6-terra": ((2, .2, 2.5, 12), (4, .4, 5, 18)),
    "gpt-5.6-luna": ((.2, .02, .25, 1.2), (.4, .04, .5, 1.8)),
    "gpt-5.5": ((5, .5, None, 30), (10, 1, None, 45)),
    "gpt-5.4": ((2.5, .25, None, 15), (5, .5, None, 22.5)),
    "gpt-5.4-mini": ((.75, .075, None, 4.5), None),
}
CREDIT_PRICES = {
    "gpt-6-astra": (250, 25, 1250),
    "gpt-6-sol": (50, 5, 250),
    "gpt-6-luna": (2.5, .25, 12.5),
    "gpt-5.6-sol": (100, 10, 500),
    "gpt-5.6-terra": (50, 5, 300),
    "gpt-5.6-luna": (5, .5, 30),
    "gpt-5.5": (125, 12.5, 750),
    "gpt-5.4": (62.5, 6.25, 375),
    "gpt-5.4-mini": (18.75, 1.875, 113),
}


def _usage_values(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    values = {key: value.get(key, 0) for key in TOKEN_FIELDS}
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in values.values()):
        return None
    if values["cached_input_tokens"] + values["cache_write_input_tokens"] > values["input_tokens"]:
        return None
    return values


def _event_delta(total: Any, last: Any, previous: dict[str, int] | None) -> tuple[dict[str, int] | None, dict[str, int] | None]:
    current = _usage_values(total)
    if current is None:
        return None, previous
    if previous is None or any(current[key] < previous[key] for key in TOKEN_FIELDS):
        return _usage_values(last), current
    return {key: current[key] - previous[key] for key in TOKEN_FIELDS}, current


def _cost(model: str, usage: dict[str, int], official: bool) -> float | None:
    # Reasoning is already included in output_tokens; never bill it a second time.
    if official:
        rates = CREDIT_PRICES.get(model)
        if rates is None:
            return None
        input_rate, cached_rate, output_rate = rates
        return (
            (usage["input_tokens"] - usage["cached_input_tokens"]) * input_rate
            + usage["cached_input_tokens"] * cached_rate
            + usage["output_tokens"] * output_rate
        ) / 1_000_000
    pair = API_PRICES.get(model)
    if pair is None:
        return None
    rates = pair[1] if usage["input_tokens"] > 272_000 else pair[0]
    if rates is None or (rates[2] is None and usage["cache_write_input_tokens"]):
        return None
    return (
        (usage["input_tokens"] - usage["cached_input_tokens"] - usage["cache_write_input_tokens"]) * rates[0]
        + usage["cached_input_tokens"] * rates[1]
        + usage["cache_write_input_tokens"] * (rates[2] or 0)
        + usage["output_tokens"] * rates[3]
    ) / 1_000_000


def summarize_today(codex_home: Path, provider_id: str, official: bool, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return summarize_range(codex_home, provider_id, official, start, start + timedelta(days=1))


def summarize_range(
    codex_home: Path, provider_id: str, official: bool, start: datetime, end: datetime
) -> dict[str, Any]:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("用量统计时间范围无效")
    rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {**{key: 0 for key in TOKEN_FIELDS}, "estimated_cost": 0.0, "unpriced_tokens": 0}
    )
    files = 0
    skipped_files = 0
    for directory in (codex_home / "sessions", codex_home / "archived_sessions"):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.jsonl"):
            try:
                if not path.is_file() or datetime.fromtimestamp(path.stat().st_mtime, start.tzinfo) < start:
                    continue
                files += 1
                with path.open(encoding="utf-8") as handle:
                    first = json.loads(handle.readline())
                    payload = first.get("payload", {}) if isinstance(first, dict) else {}
                    if first.get("type") != "session_meta" or payload.get("model_provider") != provider_id:
                        continue
                    model = ""
                    previous = None
                    for line in handle:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        payload = event.get("payload", {}) if isinstance(event, dict) else {}
                        if event.get("type") == "turn_context":
                            model = str(payload.get("model", ""))
                            continue
                        if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                            continue
                        info = payload.get("info") or {}
                        delta, previous = _event_delta(
                            info.get("total_token_usage"), info.get("last_token_usage"), previous
                        )
                        if delta is None or not any(delta.values()):
                            continue
                        timestamp = datetime.fromisoformat(str(event.get("timestamp", "")).replace("Z", "+00:00"))
                        if not start <= timestamp.astimezone(start.tzinfo) < end:
                            continue
                        row = rows[model or "未知模型"]
                        for key in TOKEN_FIELDS:
                            row[key] += delta[key]
                        cost = _cost(model, delta, official)
                        if cost is None:
                            row["unpriced_tokens"] += delta["input_tokens"] + delta["output_tokens"]
                        else:
                            row["estimated_cost"] += cost
            except (OSError, ValueError, TypeError, AttributeError):
                skipped_files += 1
    models = [{"model": model, **values} for model, values in sorted(rows.items())]
    totals = {
        key: sum(row[key] for row in models)
        for key in (*TOKEN_FIELDS, "estimated_cost", "unpriced_tokens")
    }
    return {
        "date": start.date().isoformat(),
        "end_date": (end - timedelta(microseconds=1)).date().isoformat(),
        "provider_id": provider_id,
        "unit": "credits" if official else "USD",
        "price_source": CREDIT_SOURCE if official else PRICE_SOURCE,
        "models": models,
        "totals": totals,
        "scanned_files": files,
        "skipped_files": skipped_files,
    }
