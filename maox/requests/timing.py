"""Local OTLP timing metadata. Never retain event bodies, prompts, or headers."""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import math
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

from maox.requests import network_events
from maox.requests.usage import _safe, _timestamp, _SAFE_MODEL


class TimingStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.pending = {}

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=3)
        connection.execute('CREATE TABLE IF NOT EXISTS timings (session TEXT, model TEXT, '
                           'started REAL, first_text REAL, ended REAL, input INTEGER, output INTEGER, '
                           'PRIMARY KEY(session, started, ended))')
        columns = {row[1] for row in connection.execute('PRAGMA table_info(timings)')}
        if 'first_response' not in columns:
            connection.execute('ALTER TABLE timings ADD COLUMN first_response REAL')
        connection.execute('CREATE TABLE IF NOT EXISTS timing_events ('
                           'identity TEXT PRIMARY KEY, session TEXT, model TEXT, stamp REAL, metadata TEXT)')
        connection.execute('CREATE INDEX IF NOT EXISTS timing_events_session ON timing_events(session, model, stamp)')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def ingest(self, payload: dict) -> int:
        events = []
        network = []
        for resource in payload.get('resourceLogs', []):
            for scope in resource.get('scopeLogs', []):
                for record in scope.get('logRecords', []):
                    attrs = {}
                    for item in record.get('attributes', []):
                        value = item.get('value', {})
                        attrs[item.get('key')] = next((value[k] for k in ('stringValue', 'intValue', 'doubleValue', 'boolValue') if k in value), None)
                    diagnostic = network_events.sanitize(attrs)
                    if diagnostic:
                        network.append(diagnostic)
                    # Only this allowlist survives this loop. Tool bodies and user prompts are discarded.
                    name = attrs.get('event.name')
                    if name not in {'codex.api_request', 'codex.sse_event', 'codex.websocket_request', 'codex.websocket_event'}:
                        continue
                    kind = attrs.get('event.kind')
                    if name in {'codex.sse_event', 'codex.websocket_event'} and kind not in {
                            'response.output_text.delta', 'response.completed', 'response.failed', 'response.incomplete'}:
                        continue
                    stamp = _timestamp(attrs.get('event.timestamp'))
                    session = _safe(attrs.get('conversation.id'))
                    model = _safe(attrs.get('model'), _SAFE_MODEL)
                    if not stamp or not session or not model:
                        continue
                    def number(key):
                        value = attrs.get(key)
                        if value is None or isinstance(value, bool):
                            return None
                        try:
                            value = float(value)
                            return value if math.isfinite(value) and value >= 0 else None
                        except (ValueError, TypeError):
                            return None
                    events.append((stamp.timestamp(), session, model, name, attrs.get('event.kind'),
                                   number('duration_ms'), number('http.response.status_code'),
                                   bool(attrs.get('error.message')), attrs.get('success'),
                                   number('input_token_count'), number('output_token_count')))
        events.sort(key=lambda event: event[0])
        with self.lock:
            with self._connect() as db:
                network_events.record(db, network)
                touched = set()
                for record in events:
                    stamp, session, model = record[:3]
                    metadata = json.dumps(record, separators=(',', ':'))
                    identity = hashlib.sha256(metadata.encode()).hexdigest()
                    inserted = db.execute('INSERT OR IGNORE INTO timing_events VALUES (?,?,?,?,?)',
                                          (identity, session, model, stamp, metadata)).rowcount
                    if inserted:
                        touched.add((session, model))
                for session, model in touched:
                    key = (session, model)
                    latest = db.execute('SELECT max(stamp) FROM timing_events WHERE session=? AND model=?', key).fetchone()[0]
                    # Retain sanitized in-flight events across batches/restarts. Replaying only
                    # a changed conversation also repairs delayed/out-of-order OTLP exports.
                    db.execute('DELETE FROM timing_events WHERE session=? AND model=? AND stamp<?',
                               (session, model, latest - 86400))
                    records = [json.loads(row[0]) for row in db.execute(
                        'SELECT metadata FROM timing_events WHERE session=? AND model=? ORDER BY stamp, rowid', key)]
                    current = None
                    for stamp, _, _, name, kind, duration, status, error, success, inputs, outputs in records:
                        if name in {'codex.api_request', 'codex.websocket_request'}:
                            current = None
                            valid = (200 <= status < 300 if status is not None else success in ('true', True))
                            if valid and not error and duration is not None:
                                current = {'started': stamp - duration / 1000, 'first': None, 'response': stamp if name == 'codex.api_request' else None, 'last': stamp}
                            continue
                        if current is None:
                            continue
                        current['last'] = stamp
                        if error or success in ('false', False) or kind in {'response.failed', 'response.incomplete'}:
                            current = None
                            continue
                        if kind == 'response.output_text.delta':
                            if current['first'] is None:
                                current['first'] = stamp
                            else:
                                duplicate = json.dumps([stamp, session, model, name, kind, duration, status, error, success, inputs, outputs], separators=(',', ':'))
                                db.execute('DELETE FROM timing_events WHERE identity=?',
                                           (hashlib.sha256(duplicate.encode()).hexdigest(),))
                        if kind == 'response.completed' and inputs is not None and outputs is not None:
                            if (stamp > current['started'] and float(inputs).is_integer() and float(outputs).is_integer()
                                    and inputs < 2**63 and outputs < 2**63):
                                db.execute('INSERT INTO timings (session, model, started, first_text, ended, input, output, first_response) VALUES (?,?,?,?,?,?,?,?) '
                                           'ON CONFLICT(session, started, ended) DO UPDATE SET first_text=excluded.first_text, first_response=excluded.first_response',
                                           (session, model, current['started'], current['first'], stamp, int(inputs), int(outputs), current['response']))
                            current = None
                    if current:
                        self.pending[key] = current
                    else:
                        self.pending.pop(key, None)

        return len(events)

    def network_for_period(self, start, end, limit=100):
        with self.lock:
            with self._connect() as db:
                return network_events.read(db, start, end, limit)

    def enrich(self, rows: list[dict]) -> list[dict]:
        if not rows or not self.path.exists():
            return rows
        stamps = [_timestamp(row.get('timestamp')) for row in rows]
        valid = [stamp.timestamp() for stamp in stamps if stamp]
        if not valid:
            return rows
        with self.lock:
            with self._connect() as db:
                timings = db.execute('SELECT session, model, started, first_text, ended, input, output, first_response '
                                     'FROM timings WHERE ended BETWEEN ? AND ?', (min(valid) - 2, max(valid) + 2)).fetchall()
        candidates_by_usage = defaultdict(list)
        for tindex, timing in enumerate(timings):
            session, model, _, _, _, inputs, outputs, _ = timing
            candidates_by_usage[(session, model, inputs, outputs)].append(tindex)
        matches = defaultdict(list)
        reverse = defaultdict(list)
        for index, (row, stamp) in enumerate(zip(rows, stamps)):
            if not stamp:
                continue
            usage_key = (row['session_id'], row['model'], row['input_tokens'], row['output_tokens'])
            for tindex in candidates_by_usage[usage_key]:
                ended = timings[tindex][4]
                if abs(ended - stamp.timestamp()) <= 2:
                    matches[index].append(tindex)
                    reverse[tindex].append(index)
        result = [dict(row) for row in rows]
        for index, candidates in matches.items():
            if len(candidates) != 1 or len(reverse[candidates[0]]) != 1:
                continue
            _, _, started, first, ended, _, outputs, response = timings[candidates[0]]
            duration = ended - started
            result[index].update(duration_seconds=duration, first_token_seconds=first - started if first is not None else None,
                                 first_response_seconds=response - started if response is not None else None,
                                 tps=outputs / duration if outputs > 0 else None, timing_source='request_events',
                                 request_started_at=datetime.fromtimestamp(started, timezone.utc).isoformat())
        return result
