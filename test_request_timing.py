"""Observed OTLP events join only an unambiguous local response."""
import json
import tempfile
import unittest
from pathlib import Path
from manager_parts.request_timing import TimingStore


def event(name, seconds, **attrs):
    attrs = {'event.name': name, 'conversation.id': 'session-1', 'model': 'gpt-6.1-sol',
             'event.timestamp': f'2026-10-27T08:00:{seconds:06.3f}Z', **attrs}
    return {'attributes': [{'key': k, 'value': {'stringValue': str(v)}} for k, v in attrs.items()]}


def batch(*events):
    return {'resourceLogs': [{'scopeLogs': [{'logRecords': list(events)}]}]}


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'timing.sqlite'
        self.store = TimingStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def feed(self, session='session-1'):
        events = [event('codex.api_request', 2, duration_ms=2000, **{'http.response.status_code': 200}),
                  event('codex.sse_event', 3, **{'event.kind': 'response.created', 'duration_ms': 1000}),
                  event('codex.sse_event', 5, **{'event.kind': 'response.output_text.delta', 'duration_ms': 2000}),
                  event('codex.sse_event', 10, **{'event.kind': 'response.completed', 'duration_ms': 5000}),
                  event('codex.sse_event', 10, **{'event.kind': 'response.completed', 'input_token_count': 100,
                                               'output_token_count': 200, 'prompt': 'SECRET', 'error.message': ''})]
        for e in events:
            for a in e['attributes']:
                if a['key'] == 'conversation.id': a['value']['stringValue'] = session
        self.store.ingest(batch(*events))

    def row(self, **updates):
        return {'id': 'resp-1', 'session_id': 'session-1', 'timestamp': '2026-10-27T08:00:10.010Z',
                'model': 'gpt-6.1-sol', 'input_tokens': 100, 'output_tokens': 200, **updates}

    def test_non_request_events_are_not_reported_as_request_activity(self):
        count = self.store.ingest(batch(event('codex.tool_result', 10, duration_ms=100)))
        self.assertEqual(count, 0)
        self.assertEqual(self.store.ingest(batch(event('codex.api_request', 12, duration_ms=100,
                                                       **{'http.response.status_code': 200}))), 1)

    def test_observed_request_start_first_text_and_end_survive_restart(self):
        self.feed()
        row = TimingStore(self.path).enrich([self.row()])[0]
        self.assertEqual(row['timing_source'], 'request_events')
        self.assertEqual(row['duration_seconds'], 10)
        self.assertEqual(row['first_token_seconds'], 5)
        self.assertEqual(row['first_response_seconds'], 2)
        self.assertEqual(row['tps'], 20)
        self.assertEqual(row['request_started_at'], '2026-10-27T08:00:00+00:00')
        self.assertNotIn(b'SECRET', self.path.read_bytes())

    def test_legacy_timings_do_not_substitute_first_text_for_connection_response(self):
        import sqlite3
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE timings (session TEXT, model TEXT, started REAL, first_text REAL, '
                       'ended REAL, input INTEGER, output INTEGER, PRIMARY KEY(session, started, ended))')
            from datetime import datetime
            start = datetime.fromisoformat('2026-10-27T08:00:00+00:00').timestamp()
            db.execute('INSERT INTO timings VALUES (?,?,?,?,?,?,?)',
                       ('session-1', 'gpt-6.1-sol', start, start + 5, start + 10, 100, 200))
        row = self.store.enrich([self.row()])[0]
        self.assertEqual(row['first_token_seconds'], 5)
        self.assertIsNone(row['first_response_seconds'])
        self.assertEqual(row['tps'], 20)

    def test_multiple_requests_and_sessions_do_not_mix(self):
        self.feed()
        self.feed('session-2')
        rows = self.store.enrich([self.row(), self.row(id='resp-2', session_id='session-2')])
        self.assertEqual([r['tps'] for r in rows], [20, 20])
        self.assertNotIn('tps', self.store.enrich([self.row(output_tokens=201)])[0])

    def test_ambiguous_matching_and_failed_requests_do_not_invent_timing(self):
        self.feed()
        self.assertNotIn('tps', self.store.enrich([self.row(), self.row(id='resp-2')])[0])
        self.store.ingest(batch(event('codex.api_request', 20, duration_ms=1000,
                                     **{'http.response.status_code': 500})))
        self.store.ingest(batch(event('codex.sse_event', 22, **{'event.kind': 'response.completed',
                                                           'input_token_count': 101, 'output_token_count': 201})))
        self.assertNotIn('tps', self.store.enrich([self.row(input_tokens=101, output_tokens=201, timestamp='2026-10-27T08:00:22Z')])[0])

    def test_first_protocol_event_is_not_first_text_and_missing_deltas_stay_null(self):
        self.store.ingest(batch(event('codex.api_request', 2, duration_ms=2000, **{'http.response.status_code': 200}),
                                event('codex.sse_event', 3, **{'event.kind': 'response.created'}),
                                event('codex.sse_event', 10, **{'event.kind': 'response.completed',
                                                             'input_token_count': 100, 'output_token_count': 200})))
        self.assertIsNone(self.store.enrich([self.row()])[0]['first_token_seconds'])

    def test_delayed_previous_request_export_cannot_replace_current_start(self):
        self.feed()
        self.store.ingest(batch(event('codex.api_request', 12, duration_ms=2000,
                                     **{'http.response.status_code': 200})))
        self.store.ingest(batch(event('codex.api_request', 2, duration_ms=2000,
                                     **{'http.response.status_code': 200})))
        self.store.ingest(batch(event('codex.sse_event', 15, **{'event.kind': 'response.output_text.delta'}),
                                event('codex.sse_event', 20, **{'event.kind': 'response.completed',
                                                             'input_token_count': 101, 'output_token_count': 201})))
        row = self.store.enrich([self.row(input_tokens=101, output_tokens=201,
                                         timestamp='2026-10-27T08:00:20Z')])[0]
        self.assertEqual(row['duration_seconds'], 10)
        self.assertEqual(row['first_token_seconds'], 5)
        self.assertEqual(row['first_response_seconds'], 2)

    def test_request_start_survives_manager_restart_between_batches(self):
        self.store.ingest(batch(event('codex.api_request', 2, duration_ms=2000, **{'http.response.status_code': 200})))
        self.store = TimingStore(self.path)
        self.store.ingest(batch(event('codex.sse_event', 5, **{'event.kind': 'response.output_text.delta'}),
                                event('codex.sse_event', 10, **{'event.kind': 'response.completed',
                                                             'input_token_count': 100, 'output_token_count': 200})))
        self.assertEqual(self.store.enrich([self.row()])[0]['tps'], 20)

    def test_completion_batch_before_start_is_reconciled_when_start_arrives(self):
        self.store.ingest(batch(event('codex.sse_event', 10, **{'event.kind': 'response.completed',
                                                             'input_token_count': 100, 'output_token_count': 200})))
        self.store.ingest(batch(event('codex.api_request', 2, duration_ms=2000, **{'http.response.status_code': 200}),
                                event('codex.sse_event', 5, **{'event.kind': 'response.output_text.delta'})))
        row = self.store.enrich([self.row()])[0]
        self.assertEqual(row['tps'], 20)
        self.assertEqual(row['first_token_seconds'], 5)
        self.assertEqual(row['first_response_seconds'], 2)

    def test_split_batches_and_duplicate_exports_are_idempotent(self):
        self.feed()
        self.feed()
        self.assertEqual(self.store.enrich([self.row()])[0]['tps'], 20)

class TimingApiTests(unittest.TestCase):
    def test_local_otlp_route_persists_only_timing_and_rejects_browser_origin(self):
        import importlib
        import os
        import threading
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {'CODEX_HOME': td + '/codex', 'MAOLIKE_CODEX_HOME': td + '/app'}):
                app = importlib.import_module('app')
            store = TimingStore(Path(td) / 'timing.sqlite')
            server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                body = json.dumps(batch(event('codex.api_request', 2, duration_ms=2000,
                                               **{'http.response.status_code': 200}))).encode()
                url = f'http://127.0.0.1:{server.server_port}/api/timing/otlp'
                with patch.object(app, 'MANAGER', SimpleNamespace(_timing_store=store)):
                    with urlopen(Request(url, body, {'Content-Type': 'application/json'})) as response:
                        self.assertEqual(response.status, 200)
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request(url, body, {'Content-Type': 'application/json', 'Origin': 'https://example.com'}))
                    self.assertEqual(error.exception.code, 403)
                    error.exception.close()
                self.assertEqual(len(store.pending), 1)
                from datetime import datetime
                network = store.network_for_period(datetime.fromisoformat('2026-10-27T00:00:00+00:00'),
                                                   datetime.fromisoformat('2026-10-28T00:00:00+00:00'))
                self.assertEqual(network['total'], 1)
                self.assertEqual(network['events'][0]['http_status'], 200)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)
