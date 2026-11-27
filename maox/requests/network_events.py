"""Allowlisted request diagnostics from Codex telemetry, never raw event bodies."""
import hashlib
import json
import math
import re
from datetime import timezone
from urllib.parse import urlsplit

from maox.requests.usage import _safe, _SAFE_MODEL, _timestamp

EVENTS = {'codex.api_request', 'codex.websocket_request', 'codex.sse_event', 'codex.websocket_event'}
TERMINAL = {'response.completed', 'response.failed', 'response.incomplete'}
ROUTES = {'/responses', '/v1/responses', '/backend-api/codex/responses', '/chat/completions', '/v1/chat/completions'}


def endpoint(value):
    """Keep only an origin and known model route; never credentials/query/custom paths."""
    if not isinstance(value, str):
        return ''
    try:
        url = urlsplit(value)
        if not url.scheme and not url.netloc and url.path in ROUTES:
            return url.path
        if url.scheme not in {'http', 'https', 'ws', 'wss'} or not url.hostname:
            return ''
        host = url.hostname
        if not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}', host):
            return ''
        if ':' in host:
            host = '[' + host + ']'
        origin = url.scheme + '://' + host + (':' + str(url.port) if url.port else '')
        route = url.path if url.path in ROUTES else '/…'
        return origin + route
    except ValueError:
        return ''


def error_category(message):
    # Only fixed category names survive; exceptions may contain tokens or prompts.
    text = str(message or '').lower()
    for category, words in (
        ('timeout', ('timeout', 'timed out', 'deadline')),
        ('dns', ('dns', 'name resolution', 'resolve host')),
        ('tls', ('tls', 'certificate', 'ssl')),
        ('connection', ('connect', 'network', 'reset', 'broken pipe')),
        ('authorization', ('unauthorized', 'forbidden', '401', '403', 'token_expired')),
        ('rate_limit', ('429', 'rate limit', 'quota')),
    ):
        if any(word in text for word in words):
            return category
    return 'request_error' if text else ''


def sanitize(attrs):
    name = attrs.get('event.name')
    kind = attrs.get('event.kind')
    if name not in EVENTS or (name in {'codex.sse_event', 'codex.websocket_event'} and kind not in TERMINAL):
        return None
    stamp = _timestamp(attrs.get('event.timestamp'))
    if stamp is None:
        return None
    def number(key):
        try:
            value = attrs.get(key)
            if value is None or isinstance(value, bool):
                return None
            value = float(value)
            return value if math.isfinite(value) and value >= 0 else None
        except (TypeError, ValueError):
            return None
    code = number('http.response.status_code')
    code = int(code) if code is not None and code.is_integer() and 100 <= code <= 599 else None
    error = error_category(attrs.get('error.message'))
    success = attrs.get('success')
    failed = bool(error) or success in (False, 'false') or (code is not None and code >= 400) or kind in {'response.failed', 'response.incomplete'}
    status = ('failed' if failed else 'completed' if kind == 'response.completed' else
              'response_received' if (code is not None and 200 <= code < 300) or success in (True, 'true') else 'unknown')
    return {
        'timestamp': stamp.astimezone(timezone.utc).isoformat(),
        'session_id': _safe(attrs.get('conversation.id')),
        'model': _safe(attrs.get('model'), _SAFE_MODEL),
        'event': name,
        'kind': kind if kind in TERMINAL else '',
        'transport': 'WebSocket' if 'websocket' in name else 'HTTP/SSE',
        'endpoint': endpoint(attrs.get('endpoint') or attrs.get('url.full') or attrs.get('url') or attrs.get('http.url')),
        'http_status': code,
        'duration_ms': number('duration_ms'),
        'status': status,
        'error_category': error,
        'attempt': number('attempt'),
    }


def create_table(db):
    db.execute('CREATE TABLE IF NOT EXISTS network_events (id TEXT PRIMARY KEY, stamp REAL, metadata TEXT)')
    db.execute('CREATE INDEX IF NOT EXISTS network_events_stamp ON network_events(stamp)')


def record(db, events):
    create_table(db)
    for value in events:
        metadata = json.dumps(value, sort_keys=True, separators=(',', ':'))
        identity = hashlib.sha256(metadata.encode()).hexdigest()
        stamp = _timestamp(value['timestamp']).timestamp()
        db.execute('INSERT OR IGNORE INTO network_events VALUES (?,?,?)', (identity, stamp, metadata))


def read(db, start, end, limit=100):
    create_table(db)
    total = db.execute('SELECT count(*) FROM network_events WHERE stamp>=? AND stamp<?',
                       (start.timestamp(), end.timestamp())).fetchone()[0]
    rows = db.execute('SELECT id, metadata FROM network_events WHERE stamp>=? AND stamp<? ORDER BY stamp DESC, id LIMIT ?',
                      (start.timestamp(), end.timestamp(), max(1, min(500, limit)))).fetchall()
    return {'scope': 'all_providers', 'total': total, 'events': [{'id': identity, **json.loads(metadata)} for identity, metadata in rows]}
