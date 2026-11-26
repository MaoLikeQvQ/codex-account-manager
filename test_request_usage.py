"""Per-response metadata parsing, timing, and incremental file boundaries."""
import json
from io import BytesIO
import os
from pathlib import Path
import tempfile
import threading
import importlib
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from codex_manager import CodexManager, Paths
from manager_parts.pricing import MODELS_DEV
from manager_parts.request_usage import RequestUsageReader
from manager_parts.usage import API_PRICES


class RequestUsageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        (self.home / 'sessions').mkdir()
        self.start = datetime(2026, 10, 26, tzinfo=timezone(timedelta(hours=8)))
        self.end = self.start + timedelta(days=1)
        self.reader = RequestUsageReader()
        self.base = self.start.timestamp() + 3600

    def tearDown(self):
        self.temporary.cleanup()

    def timestamp(self, seconds):
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()

    def write(self, name, events, provider='MaoLocal', session='safe-session'):
        path = self.home / 'sessions' / name
        metadata = {'type': 'session_meta', 'payload': {'id': session, 'model_provider': provider, 'cwd': '/secret/path'}}
        context = {'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol', 'effort': 'high', 'cwd': '/private', 'instructions': 'private prompt'}}
        path.write_text('\n'.join(json.dumps(item) for item in [metadata, context, *events]) + '\n')
        return path

    def record(self, response='response-1', offset=10, output=100, **extra):
        return {'type': 'token_usage_record', 'timestamp': self.timestamp(self.base + offset), 'payload': {
            'response_id': response, 'turn_id': 'turn-1', 'thread_id': 'safe-session',
            'usage': {'input_tokens': 1000, 'cached_input_tokens': 800, 'cache_write_input_tokens': 0,
                      'output_tokens': output, 'reasoning_output_tokens': 40, 'total_tokens': 1000 + output}, **extra}}

    def item(self, start, end, kind='AgentMessage', turn='turn-1'):
        return {'type': 'event_msg', 'payload': {'type': 'item_completed', 'turn_id': turn,
            'started_at_ms': (self.base + start) * 1000, 'completed_at_ms': (self.base + end) * 1000,
            'item': {'type': kind, 'text': 'PRIVATE RESPONSE', 'encrypted_content': 'SECRET', 'arguments': 'token=secret'}}}

    def legacy(self, offset, total=100, last=100):
        return {'type': 'event_msg', 'timestamp': self.timestamp(self.base + offset), 'payload': {'type': 'token_count', 'info': {
            'total_token_usage': {'input_tokens': total * 10, 'output_tokens': total},
            'last_token_usage': {'input_tokens': last * 10, 'output_tokens': last}}}}

    def query(self, provider='MaoLocal', **kwargs):
        return self.reader.summarize(self.home, provider, self.start, self.end, **kwargs)

    def test_timing_coverage_distinguishes_desktop_requests_from_cli_validation(self):
        desktop = self.write('desktop.jsonl', [self.record('desktop')], session='desktop')
        cli = self.write('cli.jsonl', [self.record('cli')], session='cli')
        for path, source in [(desktop, 'vscode'), (cli, 'exec')]:
            lines = path.read_text().splitlines()
            metadata = json.loads(lines[0])
            metadata['payload']['source'] = source
            lines[0] = json.dumps(metadata)
            path.write_text('\n'.join(lines) + '\n')
        def enrich(rows):
            return [{**row, 'timing_source': 'request_events'} if row['id'] == 'cli' else row for row in rows]
        result = self.query(timing_enricher=enrich)
        self.assertEqual(result['timing_coverage'], {
            'total': 2, 'timed': 1, 'desktop_total': 1, 'desktop_timed': 0, 'cli_timed': 1,
        })
        self.assertEqual({row['id']: row['client_source'] for row in result['requests']},
                         {'desktop': 'desktop', 'cli': 'cli'})

    def test_item_timestamps_do_not_prove_per_response_generation_time(self):
        self.write('a.jsonl', [self.item(0, 10, 'Reasoning'), self.record(),
            self.item(10, 110, 'LocalShellCall'), self.item(110, 115, 'Reasoning'),
            self.item(115, 120), self.record('response-2', 120, 200),
            {'type': 'event_msg', 'payload': {'type': 'task_complete', 'duration_ms': 120000}}])
        result = self.query()
        self.assertEqual(result['total_requests'], 2)
        latest, first = result['requests']
        self.assertEqual(latest['output_tokens'], 200)
        self.assertIsNone(latest['duration_seconds'])
        self.assertIsNone(latest['tps'])
        self.assertIsNone(first['tps'])
        self.assertEqual(latest['reasoning_effort'], 'high')
        self.assertNotIn('PRIVATE RESPONSE', repr(self.reader._files))
        self.assertNotIn('/secret/path', repr(self.reader._files))
        self.assertEqual(latest['timing_source'], 'unavailable')
        self.assertAlmostEqual(first['estimated_cost'], .00148)
        serialized = json.dumps(result)
        for secret in ['PRIVATE RESPONSE', 'SECRET', '/secret', '/private', 'instructions', 'arguments', 'encrypted_content']:
            self.assertNotIn(secret, serialized)

    def test_single_response_turn_duration_is_not_request_timing(self):
        started = {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn-1'}}
        path = self.write('single.jsonl', [started, self.item(9.9, 9.9, 'Reasoning'),
                                         self.record('single', 10, 200)])
        self.assertIsNone(self.query()['requests'][0]['tps'])
        self.assertIsNone(self.query()['requests'][0]['first_token_seconds'])
        completed = {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'turn-1',
                     'duration_ms': 20000, 'time_to_first_token_ms': 8000}}
        with path.open('a') as stream:
            stream.write(json.dumps(completed) + '\n')
        row = self.query()['requests'][0]
        self.assertIsNone(row['duration_seconds'])
        self.assertIsNone(row['first_token_seconds'])
        self.assertIsNone(row['tps'])
        self.assertEqual(row['timing_source'], 'unavailable')

    def test_turn_first_token_fields_are_not_per_request_timing(self):
        started = {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn-1'}}
        for index, (first_ms, expected) in enumerate([
            (None, None), (-1, None), (True, None), (20001, None), (0, 0), (1250, 1.25),
        ]):
            with self.subTest(first_ms=first_ms):
                name = f'first-{index}'
                completed = {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'turn-1',
                             'duration_ms': 20000, 'time_to_first_token_ms': first_ms}}
                self.write(f'{name}.jsonl', [started, self.record(name, 10, 200), completed], session=name)
                row = next(item for item in self.query()['requests'] if item['id'] == name)
                self.assertIsNone(row['first_token_seconds'])
                self.assertIsNone(row['duration_seconds'])
                self.assertIsNone(row['tps'])

    def test_no_output_turn_does_not_infer_request_timing(self):
        started = {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn-1'}}
        record = self.record('no-output', 10, 0)
        record['payload']['usage']['reasoning_output_tokens'] = 0
        completed = {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'turn-1',
                     'duration_ms': 12000, 'time_to_first_token_ms': 3000}}
        self.write('no-output.jsonl', [started, record, completed])
        row = self.query()['requests'][0]
        self.assertIsNone(row['first_token_seconds'])
        self.assertIsNone(row['duration_seconds'])
        self.assertIsNone(row['tps'])
        self.assertEqual(row['timing_source'], 'unavailable')

    def test_ambiguous_or_invalid_turns_do_not_calculate_tps(self):
        started = {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn-1'}}
        completed = {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'turn-1',
                     'duration_ms': 20000}}
        tool_call = {'type': 'response_item', 'payload': {'type': 'custom_tool_call'}}
        tool_item = self.item(1, 5, 'CommandExecution')
        scenarios = {
            'tool_call': [started, self.record('tool_call'), tool_call, completed],
            'tool_item': [started, tool_item, self.record('tool_item'), completed],
            'other_turn_item': [started, self.item(1, 5, turn='other'), self.record('other_turn_item'), completed],
            'multiple': [started, self.record('multiple'), self.record('multiple-2', 12), completed],
            'no_start': [self.record('no_start'), completed],
            'wrong_turn': [started, self.record('wrong_turn'),
                           {'type': 'event_msg', 'payload': {**completed['payload'], 'turn_id': 'other'}}],
            'invalid_duration': [started, self.record('invalid_duration'),
                                 {'type': 'event_msg', 'payload': {**completed['payload'], 'duration_ms': 0}}],
            'boolean_duration': [started, self.record('boolean_duration'),
                                 {'type': 'event_msg', 'payload': {**completed['payload'], 'duration_ms': True}}],
            'failed': [started, self.record('failed'),
                       {'type': 'event_msg', 'payload': {**completed['payload'], 'error': {'message': 'failed'}}}],
        }
        for name, events in scenarios.items():
            with self.subTest(name=name):
                self.write(f'{name}.jsonl', events, session=name)
                row = next(item for item in self.query()['requests'] if item['id'] == name)
                self.assertIsNone(row['duration_seconds'])
                self.assertIsNone(row['first_token_seconds'])
                self.assertIsNone(row['tps'])
                self.assertEqual(row['timing_source'], 'unavailable')

    def test_authoritative_records_deduplicate_and_replace_legacy_even_when_appended(self):
        path = self.write('a.jsonl', [self.legacy(10), self.legacy(11)])
        self.assertEqual(self.query()['total_requests'], 1)
        record = self.record()
        with path.open('a') as stream:
            stream.write(json.dumps(record) + '\n' + json.dumps(record) + '\n')
        result = self.query()
        self.assertEqual(result['total_requests'], 1)
        self.assertEqual(result['requests'][0]['output_tokens'], 100)
        self.assertIsNone(result['requests'][0]['tps'])
        self.assertEqual(result['requests'][0]['timing_source'], 'unavailable')

    def test_invalid_authoritative_record_keeps_legacy_until_valid_record_arrives(self):
        invalid_usage = self.record('invalid-usage')
        invalid_usage['payload']['usage']['input_tokens'] = -1
        invalid_timestamp = self.record('invalid-timestamp')
        invalid_timestamp['timestamp'] = 'not-a-timestamp'
        empty_usage = self.record('empty-usage')
        empty_usage['payload']['usage'] = {}
        path = self.write('a.jsonl', [self.legacy(10), invalid_usage, invalid_timestamp, empty_usage])
        result = self.query()
        self.assertEqual(result['total_requests'], 1)
        self.assertEqual(result['requests'][0]['output_tokens'], 100)
        with path.open('a') as stream:
            stream.write(json.dumps(self.record('valid-record', 20, 200)) + '\n')
        result = self.query()
        self.assertEqual(result['total_requests'], 1)
        self.assertEqual(result['requests'][0]['id'], 'valid-record')
        self.assertEqual(result['requests'][0]['output_tokens'], 200)

    def test_no_timing_invalid_timing_and_other_turns_do_not_fabricate_tps(self):
        self.write('a.jsonl', [self.item(0, 8, turn='other-turn'), self.record(),
            self.item(30, 40), self.record('response-2', 20),
            self.item(20, 20), self.record('response-3', 20)])
        for row in self.query()['requests']:
            self.assertIsNone(row['duration_seconds'])
            self.assertIsNone(row['tps'])
            self.assertEqual(row['timing_source'], 'unavailable')

    def test_legacy_events_are_per_response_without_duplicate_or_task_duration(self):
        self.write('a.jsonl', [self.legacy(10), self.legacy(11), self.legacy(20, 150, 50)])
        result = self.query()
        self.assertEqual(result['total_requests'], 2)
        self.assertEqual([row['output_tokens'] for row in result['requests']], [50, 100])
        self.assertTrue(all(row['tps'] is None for row in result['requests']))

    def test_date_provider_filters_unknown_price_and_safe_identifiers(self):
        self.write('a.jsonl', [self.record(offset=-3601), self.record('in-date', 0), self.record('next-day', 86400)], session='../../auth.json')
        self.write('other.jsonl', [self.record('other-provider')], provider='openai')
        path = self.write('unknown.jsonl', [self.record('unknown')])
        path.write_text(path.read_text().replace('gpt-6.1-sol', 'unknown-model'))
        result = self.query()
        self.assertEqual(result['total_requests'], 2)
        unknown = next(row for row in result['requests'] if row['model'] == 'unknown-model')
        self.assertIsNone(unknown['estimated_cost'])
        self.assertEqual(next(row for row in result['requests'] if row['id'] == 'in-date')['session_id'], '')
        self.assertEqual(result['date'], '2026-10-26')

    def test_partial_append_only_parses_new_complete_lines_and_unchanged_file_is_not_reopened(self):
        path = self.write('a.jsonl', [self.record()])
        self.assertEqual(self.query()['total_requests'], 1)
        with patch.object(Path, 'open', side_effect=AssertionError('unchanged content was reopened')):
            self.assertEqual(self.query()['total_requests'], 1)
        encoded = json.dumps(self.record('response-2', 20)) + '\n'
        with path.open('a') as stream:
            stream.write(encoded[:30])
        self.assertEqual(self.query()['total_requests'], 1)
        with path.open('a') as stream:
            stream.write(encoded[30:])
        with patch('manager_parts.request_usage.json.loads', wraps=json.loads) as parse:
            self.assertEqual(self.query()['total_requests'], 2)
            self.assertEqual(parse.call_count, 1, 'only the newly completed line is parsed')
        path.write_text(path.read_text().replace('MaoLocal', 'different'))
        self.assertEqual(self.query()['total_requests'], 0)
        self.write('a.jsonl', [self.record('replacement')])
        self.assertEqual(self.query()['requests'][0]['id'], 'replacement')

    def test_copies_across_archive_are_deduplicated_and_limit_is_validated(self):
        path = self.write('a.jsonl', [self.record(), self.record('response-2', 20)])
        archive = self.home / 'archived_sessions'
        archive.mkdir()
        (archive / 'copy.jsonl').write_text(path.read_text())
        result = self.query(limit=1)
        self.assertEqual(result['total_requests'], 2)
        self.assertEqual(len(result['requests']), 1)
        self.assertEqual(result['requests'][0]['id'], 'response-2')
        for limit in [0, 201, True, 1.5, 'x']:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.query(limit=limit)

    def test_manager_uses_applied_identity_and_price_failure_is_throttled(self):
        self.write('official.jsonl', [self.record()], provider='openai')
        manager = CodexManager(Paths(self.home, self.home / 'manager'))
        saved = {'account_type': 'custom', 'provider_id': 'MaoLocal', 'applied_account': {'account_type': 'official'}}
        store = {'active_account': 'active', 'accounts': {'active': saved}}
        with patch.object(manager, '_load_store', return_value=store), patch('codex_manager.get_api_prices', return_value=(API_PRICES, {'status': 'bundled'})) as prices:
            for _ in range(2):
                result = manager.requests_for_period('date', '2026-10-26')
                self.assertEqual(result['provider_id'], 'openai')
                self.assertEqual(result['total_requests'], 1)
            self.assertEqual(prices.call_count, 1)
            for period, date in [('invalid', ''), ('date', 'garbage'), ('date', '2999-01-01')]:
                with self.assertRaises(ValueError):
                    manager.requests_for_period(period, date)

    def test_old_files_are_not_opened_and_other_provider_only_reads_header(self):
        old = self.write('old.jsonl', [self.record('old')])
        os.utime(old, (self.start.timestamp() - 1, self.start.timestamp() - 1))
        other = self.write('other.jsonl', [self.record('official')], provider='openai')
        with patch.object(Path, 'open', autospec=True, side_effect=Path.open) as opened:
            self.assertEqual(self.query()['total_requests'], 0)
            self.assertNotIn(old, [call.args[0] for call in opened.call_args_list])
        self.assertEqual(self.reader._files[other].offset, len(other.read_bytes().splitlines(keepends=True)[0]))
        self.assertEqual(self.query('openai')['requests'][0]['id'], 'official')

    def test_new_turn_without_ids_clears_old_generation_candidates(self):
        next_context = {'type': 'turn_context', 'payload': {'model': 'gpt-6.1-sol', 'effort': 'high'}}
        started = {'type': 'event_msg', 'payload': {'type': 'task_started'}}
        self.write('a.jsonl', [self.item(0, 10), next_context, self.record('context', 100),
            self.item(110, 120), started, self.record('task', 200)])
        for row in self.query()['requests']:
            self.assertIsNone(row['tps'])

    def test_thread_safe_concurrent_queries_reuse_the_same_response_index(self):
        self.write('a.jsonl', [self.item(0, 10), self.record()])
        results = []
        failures = []
        def query():
            try:
                results.append(self.query())
            except Exception as error:
                failures.append(error)
        threads = [threading.Thread(target=query) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 8)
        self.assertTrue(all(result['total_requests'] == 1 for result in results))

    def test_http_route_preserves_result_shape_and_rejects_bad_query(self):
        self.write('a.jsonl', [self.record()])
        manager = CodexManager(Paths(self.home, self.home / 'manager'))
        store = {'active_account': 'active', 'accounts': {'active': {'account_type': 'custom', 'provider_id': 'MaoLocal'}}}
        with patch.dict(os.environ, {'CODEX_HOME': str(self.home), 'MAOLIKE_CODEX_HOME': str(self.home / 'manager')}):
            app = importlib.import_module('app')
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.object(app, 'MANAGER', manager), patch.object(manager, '_load_store', return_value=store), patch(
                'codex_manager.get_api_prices', return_value=(API_PRICES, {'status': 'bundled'}),
            ):
                with urlopen(url + '/api/requests?period=date&date=2026-10-26&limit=1') as response:
                    payload = json.load(response)
                self.assertTrue(payload['ok'])
                self.assertEqual(payload['result']['total_requests'], 1)
                self.assertEqual(payload['result']['requests'][0]['id'], 'response-1')
                for query in ['limit=0', 'limit=201', 'limit=1.5', 'limit=x', 'period=date&date=bad']:
                    with self.subTest(query=query), self.assertRaises(HTTPError) as caught:
                        urlopen(url + '/api/requests?' + query)
                    self.assertEqual(caught.exception.code, 400)
                    caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_price_sync_reprices_both_views_and_preserves_cache_on_failure(self):
        self.write('a.jsonl', [self.legacy(18 * 3600), self.record(offset=18 * 3600 + 1)])
        manager = CodexManager(Paths(self.home, self.home / 'manager'))
        store = {'active_account': 'active', 'accounts': {'active': {'account_type': 'custom', 'provider_id': 'MaoLocal'}}}

        def price_feed(output):
            data = {'openai': {'models': {'gpt-6.1-sol': {'cost': {
                'input': 2, 'cache_read': .1, 'output': output,
            }}}}}
            return BytesIO(json.dumps(data).encode())

        with patch.dict(os.environ, {'CODEX_HOME': str(self.home), 'MAOLIKE_CODEX_HOME': str(self.home / 'manager')}):
            app = importlib.import_module('app')
        with ThreadingHTTPServer(('127.0.0.1', 0), app.Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}'
            sync = Request(url + '/api/pricing/sync', data=b'{}', headers={'Content-Type': 'application/json'})
            query = '?period=date&date=2026-10-26'

            def read(path):
                with urlopen(url + path + query, timeout=3) as response:
                    return json.load(response)['result']

            online = [price_feed(10), price_feed(20)] + [OSError('offline')] * 3
            try:
                with patch.object(app, 'MANAGER', manager), patch.object(manager, '_load_store', return_value=store), patch(
                    'manager_parts.pricing.urlopen', side_effect=online,
                ) as upstream:
                    self.assertAlmostEqual(read('/api/requests')['requests'][0]['estimated_cost'], .00148)
                    with urlopen(sync, timeout=3) as response:
                        result = json.load(response)['result']
                    self.assertEqual(result['model_count'], 1)
                    self.assertEqual(result['source'], MODELS_DEV)
                    self.assertAlmostEqual(read('/api/requests')['requests'][0]['estimated_cost'], .00248)
                    self.assertAlmostEqual(read('/api/usage')['totals']['estimated_cost'], .004)

                    with self.assertRaises(HTTPError) as caught:
                        urlopen(sync, timeout=3)
                    with caught.exception as error:
                        self.assertEqual(error.code, 502)
                        self.assertIn('使用上次缓存价格', json.load(error)['error'])
                    self.assertAlmostEqual(read('/api/usage')['totals']['estimated_cost'], .004)
                    self.assertEqual(upstream.call_count, 5)
            finally:
                server.shutdown()
                thread.join()

    def test_malformed_complete_line_counts_file_without_returning_private_payload(self):
        path = self.write('a.jsonl', [self.record()])
        with path.open('a') as stream:
            stream.write('{private invalid JSON}\n')
        result = self.query()
        self.assertEqual(result['total_requests'], 1)
        self.assertEqual(result['skipped_files'], 1)


if __name__ == '__main__':
    unittest.main()
