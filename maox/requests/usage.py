"""Read response metadata from append-only rollouts without retaining their content.

Timing comes only from correlated request events, never whole-turn duration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable

from maox.usage.summary import API_PRICES, _cost, _event_delta, _usage_values

_SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z')
_SAFE_PROVIDER = re.compile(r"[^\x00-\x1f\x7f]{1,160}\Z")
_SAFE_MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z')
_PRICE_TTL_SECONDS = 300


def _safe(value: Any, pattern=_SAFE_ID) -> str:
    return value if isinstance(value, str) and pattern.fullmatch(value) else ''


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except ValueError:
        return None


@dataclass
class _Rollout:
    signature: tuple[int, int, int, int] | None = None
    offset: int = 0
    prefix_hash: bytes = b''
    tail_hash: bytes = b''
    fingerprint_size: int = 0
    provider: str = ''
    session_id: str = ''
    client_source: str = 'unknown'
    model: str = ''
    effort: str = ''
    previous: dict[str, int] | None = None
    authoritative: bool = False
    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    legacy: dict[str, dict[str, Any]] = field(default_factory=dict)
    malformed: bool = False
    complete: bool = False
    def consume(self, event: Any, position: int) -> None:
        if not isinstance(event, dict):
            return
        kind = event.get('type')
        payload = event.get('payload')
        if not isinstance(payload, dict):
            return
        if kind == 'session_meta':
            self.provider = _safe(payload.get('model_provider'), _SAFE_PROVIDER)
            self.session_id = _safe(payload.get('id') or payload.get('session_id'))
            source = payload.get('source')
            self.client_source = ('desktop' if source == 'vscode' else
                                  'cli' if source in ('exec', 'cli') else
                                  'subagent' if isinstance(source, dict) and 'subagent' in source else 'unknown')
            return
        if kind == 'turn_context':
            self.model = _safe(payload.get('model'), _SAFE_MODEL)
            self.effort = _safe(payload.get('effort') or payload.get('reasoning_effort'))
            return
        if kind == 'token_usage_record':
            raw_usage = payload.get('usage')
            usage = _usage_values(raw_usage) if isinstance(raw_usage, dict) and {'input_tokens', 'output_tokens'} <= raw_usage.keys() else None
            timestamp = _timestamp(event.get('timestamp'))
            if usage is None or timestamp is None:
                return
            self.authoritative = True
            row = self.row(timestamp, usage, position, _safe(payload.get('response_id')))
            self.records.setdefault(row['id'], row)
            return
        if kind == 'event_msg' and payload.get('type') == 'token_count':
            info = payload.get('info')
            if not isinstance(info, dict):
                return
            usage, self.previous = _event_delta(info.get('total_token_usage'), info.get('last_token_usage'), self.previous)
            timestamp = _timestamp(event.get('timestamp'))
            if usage is not None and any(usage.values()) and timestamp is not None:
                row = self.row(timestamp, usage, position)
                self.legacy.setdefault(row['id'], row)

    def row(self, timestamp: datetime, usage: dict[str, int], position: int, response_id='') -> dict[str, Any]:
        # The fallback is stable across archive copies and never contains a path.
        identity = f'{self.session_id}:{timestamp.isoformat()}:{position}:{self.model}:{usage}'
        return {
            'id': response_id or hashlib.sha256(identity.encode()).hexdigest()[:24],
            'session_id': self.session_id, 'timestamp': timestamp.isoformat(),
            'client_source': self.client_source,
            'model': self.model or '未知模型', 'reasoning_effort': self.effort,
            **usage, 'first_token_seconds': None, 'first_response_seconds': None, 'duration_seconds': None,
            'tps': None, 'timing_source': 'unavailable',
        }


class RequestUsageReader:
    """Cache sanitized rows; unchanged files are stat'ed, never reopened.

    Changed files resume at the last complete newline. Replacement/truncation,
    same-size rewrites, and changes to the session header or read boundary reset
    their cache. Neither raw lines nor private response fields survive parsing.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._files: dict[Path, _Rollout] = {}
        self._prices: Any = None
        self._prices_checked = 0.0

    def update_prices(self, prices) -> None:
        with self._lock:
            self._prices = prices
            self._prices_checked = time.monotonic()

    def _read(self, path: Path, provider_id: str, stat) -> _Rollout:
        signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        previous = self._files.get(path)
        if previous is not None and previous.signature == signature and (previous.complete or previous.provider != provider_id):
            return previous
        with path.open('rb') as stream:
            append = previous is not None and previous.signature is not None and signature[:2] == previous.signature[:2] and (stat.st_size > previous.signature[2] or (signature == previous.signature and not previous.complete))
            if append and previous.offset:
                stream.seek(0)
                prefix = hashlib.sha256(stream.read(previous.fingerprint_size)).digest()
                stream.seek(previous.offset - previous.fingerprint_size)
                tail = hashlib.sha256(stream.read(previous.fingerprint_size)).digest()
                append = prefix == previous.prefix_hash and tail == previous.tail_hash
            state = previous if append else _Rollout()
            stream.seek(state.offset)
            state.complete = True
            while not state.provider or state.provider == provider_id:
                position = stream.tell()
                line = stream.readline()
                if not line or not line.endswith(b'\n'):
                    break
                state.offset = stream.tell()
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    state.malformed = True
                    continue
                state.consume(event, position)
                if state.provider and state.provider != provider_id:
                    state.complete = False
                    break
            if state.provider != provider_id:
                state.complete = False
            stream.seek(0)
            state.fingerprint_size = min(256, state.offset)
            state.prefix_hash = hashlib.sha256(stream.read(state.fingerprint_size)).digest()
            stream.seek(state.offset - state.fingerprint_size)
            state.tail_hash = hashlib.sha256(stream.read(state.fingerprint_size)).digest()
        state.signature = signature
        self._files[path] = state
        return state

    def summarize(self, codex_home: Path, provider_id: str, start: datetime, end: datetime,
                  limit: int = 100, *, price_loader: Callable[[], Any] | None = None,
                  timing_enricher: Callable[[list[dict]], list[dict]] | None = None) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError('请求列表 limit 必须是 1 到 200 的整数')
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError('请求统计时间范围无效')
        with self._lock:
            rates = API_PRICES
            if price_loader is not None:
                # Also throttle the bundled/stale fallback, which otherwise can
                # cause a failed public price-table request on every live poll.
                if self._prices is None or time.monotonic() - self._prices_checked >= _PRICE_TTL_SECONDS:
                    self._prices = price_loader()
                    self._prices_checked = time.monotonic()
                rates = self._prices
            paths = set()
            rows: dict[str, dict[str, Any]] = {}
            skipped = 0
            for directory in (codex_home / 'sessions', codex_home / 'archived_sessions'):
                if not directory.is_dir():
                    continue
                for path in directory.rglob('*.jsonl'):
                    paths.add(path)
                    try:
                        stat = path.stat()
                        if stat.st_mtime < start.timestamp():
                            continue
                        state = self._read(path, provider_id, stat)
                    except (OSError, ValueError):
                        skipped += 1
                        continue
                    skipped += int(state.malformed)
                    if state.provider != provider_id:
                        continue
                    source = state.records if state.authoritative else state.legacy
                    for row in source.values():
                        timestamp = _timestamp(row['timestamp'])
                        if timestamp is not None and start <= timestamp < end:
                            rows.setdefault(row['id'], row)
            for stale in self._files.keys() - paths:
                del self._files[stale]
            requests = sorted(rows.values(), key=lambda row: (row['timestamp'], row['id']), reverse=True)
            # Datetimes may use different UTC offsets; compare instants, not text.
            requests.sort(key=lambda row: _timestamp(row['timestamp']).timestamp(), reverse=True)
            if timing_enricher is not None:
                requests = timing_enricher(requests)
            coverage = {
                'total': len(requests),
                'timed': sum(row['timing_source'] == 'request_events' for row in requests),
                'desktop_total': sum(row['client_source'] == 'desktop' for row in requests),
                'desktop_timed': sum(row['client_source'] == 'desktop' and row['timing_source'] == 'request_events' for row in requests),
                'cli_timed': sum(row['client_source'] == 'cli' and row['timing_source'] == 'request_events' for row in requests),
            }
            output = [{**row, 'estimated_cost': _cost(row['model'], row, False, rates)} for row in requests[:limit]]
            return {
                'provider_id': provider_id, 'date': start.date().isoformat(),
                'end_date': (end - timedelta(microseconds=1)).date().isoformat(),
                'requests': output, 'total_requests': len(requests), 'skipped_files': skipped,
                'timing_coverage': coverage,
                'updated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            }
