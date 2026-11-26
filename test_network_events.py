"""Request failures persist without a rollout; diagnostics never persist raw content."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from manager_parts.network_events import endpoint
from manager_parts.request_timing import TimingStore
from test_request_timing import event, batch


class NetworkEventTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.path = Path(self.home.name) / 'events.sqlite'
        self.store = TimingStore(self.path)
        self.start = datetime.fromisoformat('2026-10-27T00:00:00+00:00')
        self.end = datetime.fromisoformat('2026-10-28T00:00:00+00:00')

    def read(self, limit=100):
        return self.store.network_for_period(self.start, self.end, limit)

    def test_failed_attempt_without_rollout_is_visible_and_export_is_idempotent(self):
        payload = batch(event('codex.api_request', 3, duration_ms=3000, attempt=1,
                              **{'http.response.status_code': 429, 'error.message': 'quota exceeded SECRET',
                                 'endpoint': 'https://user:SECRET@example.com/v1/responses?key=SECRET',
                                 'prompt': 'PRIVATE_PROMPT', 'authorization': 'Bearer SECRET'}))
        self.store.ingest(payload)
        self.store.ingest(payload)
        result = self.read()
        self.assertEqual(result['total'], 1)
        row = result['events'][0]
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['http_status'], 429)
        self.assertEqual(row['error_category'], 'rate_limit')
        self.assertEqual(row['endpoint'], 'https://example.com/v1/responses')
        self.assertEqual(row['duration_ms'], 3000)
        self.assertNotIn(b'SECRET', self.path.read_bytes())
        self.assertNotIn(b'PRIVATE_PROMPT', self.path.read_bytes())
        self.assertEqual(TimingStore(self.path).network_for_period(self.start, self.end)['total'], 1)

    def test_headers_are_not_confused_with_completed_response(self):
        self.store.ingest(batch(
            event('codex.api_request', 1, **{'http.response.status_code': 200}),
            event('codex.sse_event', 2, **{'event.kind': 'response.output_text.delta', 'text': 'SECRET'}),
            event('codex.sse_event', 3, **{'event.kind': 'response.failed'}),
            event('codex.websocket_request', 4, success='true'),
            event('codex.websocket_event', 5, **{'event.kind': 'response.completed'})))
        result = self.read()
        self.assertEqual(result['total'], 4)
        self.assertEqual([row['status'] for row in result['events']],
                         ['completed', 'response_received', 'failed', 'response_received'])
        self.assertEqual(result['events'][0]['transport'], 'WebSocket')

    def test_missing_metadata_stays_unknown_and_failures_are_classified_without_details(self):
        self.store.ingest(batch(event('codex.api_request', 2, **{
            'conversation.id': '', 'model': '', 'error.message': 'TLS certificate SECRET'})))
        row = self.read()['events'][0]
        self.assertEqual(row['error_category'], 'tls')
        self.assertEqual(row['session_id'], '')
        self.assertEqual(row['endpoint'], '')
        self.assertNotIn('SECRET', json.dumps(row))

    def test_custom_paths_and_queries_are_redacted_and_invalid_urls_are_discarded(self):
        self.assertEqual(endpoint('/responses?key=SECRET'), '/responses')
        self.assertEqual(endpoint('https://example.com/private/SECRET?auth=SECRET#SECRET'), 'https://example.com/…')
        for value in ('file:///private/SECRET', 'https://example.com:bad/responses', 'invalid', None):
            self.assertEqual(endpoint(value), '')

    def test_date_limit_and_malformed_numbers(self):
        self.store.ingest(batch(event('codex.api_request', 1, duration_ms='nan', **{'http.response.status_code': 200.5}),
                                event('codex.api_request', 2, duration_ms=-1)))
        data = self.read(1)
        self.assertEqual(data['total'], 2)
        self.assertEqual(len(data['events']), 1)
        self.assertIsNone(data['events'][0]['duration_ms'])
        future = datetime.fromisoformat('2026-10-29T00:00:00+00:00')
        self.assertEqual(self.store.network_for_period(self.end, future)['total'], 0)
        self.assertIsNone(self.read()['events'][1]['http_status'])


if __name__ == '__main__':
    unittest.main()
