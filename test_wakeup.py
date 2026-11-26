"""Scheduling and account-specific HTTP execution; never calls an official service."""
import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from manager_parts.wakeup import WakeupError, WakeupService
from test_support import local_timezone


class WakeupTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(local_timezone('Asia/Shanghai'))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = {'active_account': 'A', 'accounts': {
            'A': self.account('one'), 'B': self.account('two'),
            'Channel': {'account_type': 'custom'},
        }}
        self.manager = Mock()
        self.manager.paths = SimpleNamespace(app_home=self.root, auth=self.root / 'active-auth.json')
        self.manager.paths.auth.write_text(json.dumps(self.store['accounts']['A']['official_auth']))
        self.manager._load_store.side_effect = lambda: json.loads(json.dumps(self.store))
        self.manager._save_store.side_effect = lambda value: self.store.update(value)
        self.manager._account_type.side_effect = lambda value: value.get('account_type', 'custom')
        self.manager._write_private_json.side_effect = lambda path, value: path.write_text(json.dumps(value))
        self.manager._read_json.side_effect = lambda path, default: json.loads(path.read_text()) if path.exists() else default
        self.manager._codex_environment.side_effect = lambda home: {'CODEX_HOME': str(home), 'OPENAI_API_KEY': 'secret'}
        self.manager._codex_binary.return_value = '/fake/codex'
        self.service = WakeupService(self.manager, threading.Lock())
        self.addCleanup(self.service.stop)

    @staticmethod
    def account(identifier):
        return {'account_type': 'official', 'official_auth': {
            'tokens': {'account_id': identifier, 'access_token': 'test-access', 'refresh_token': 'test-refresh'}}}

    def configure(self, **kwargs):
        return self.service.configure({'enabled': True, 'times': ['08:00', '13:00', '18:00'], 'model': 'test-model', **kwargs})

    def wait(self):
        self.service.worker.join(timeout=3)
        self.assertFalse(self.service.run_lock.locked())

    def test_validation_normalization_and_persistence(self):
        result = self.configure(times=['18:00', '08:00', '18:00'])
        self.assertEqual(result['times'], ['08:00', '18:00'])
        self.assertEqual(WakeupService(self.manager, threading.Lock()).state()['times'], result['times'])
        for changes in ({'times': ['25:00']}, {'times': ['8:00']}, {'times': []},
                        {'model': ''}, {'times': [True]}, {'enabled': 'true'}, {'model': '-m evil'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.configure(**changes)

    def test_missed_slots_accumulate_delay_and_reset_the_next_day(self):
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T05:00:00+08:00')):
            self.configure(times=['06:00', '11:00', '16:00'])
        with patch.object(self.service, '_start') as start:
            for value in ['05:59', '09:00', '09:00', '13:59', '16:00', '16:01', '20:59', '21:00']:
                self.service.tick(datetime.fromisoformat('2026-10-29T' + value + ':00+08:00'))
            self.assertEqual(start.call_count, 3)
        data = self.service._load()
        self.assertEqual(data['schedule']['delay_minutes'], 300)
        self.assertEqual(data['slots'], ['2026-10-29 06:00', '2026-10-29 11:00', '2026-10-29 16:00'])
        other = WakeupService(self.manager, threading.Lock())
        with patch.object(other, '_start') as start:
            other.tick(datetime.fromisoformat('2026-10-29T21:00:10+08:00'))
            start.assert_not_called()
            other.tick(datetime.fromisoformat('2026-10-30T06:00:00+08:00'))
            start.assert_called_once()

    def test_restart_preserves_delay_and_reports_shifted_next_run(self):
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T05:00:00+08:00')):
            self.configure(times=['06:00', '11:00', '16:00'])
        with patch.object(self.service, '_start'):
            self.service.tick(datetime.fromisoformat('2026-10-29T09:00:00+08:00'))
        other = WakeupService(self.manager, threading.Lock())
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T09:30:00+08:00')):
            self.assertEqual(other.state()['next_run'], '2026-10-29T14:00:00+08:00')
            self.assertEqual(other.state()['delay_minutes'], 180)
        with patch.object(other, '_start') as start:
            other.tick(datetime.fromisoformat('2026-10-29T13:59:00+08:00'))
            start.assert_not_called()
            other.tick(datetime.fromisoformat('2026-10-29T14:00:00+08:00'))
            start.assert_called_once()

    def test_legacy_enabled_config_catches_up_once_after_restart(self):
        self.service._save({'enabled': True, 'times': ['06:00', '11:00', '16:00'],
                            'model': 'test-model', 'slots': ['2026-10-28 06:00'], 'results': []})
        with patch.object(self.service, '_start') as start:
            self.service.tick(datetime.fromisoformat('2026-10-29T15:23:32+08:00'))
            self.service.tick(datetime.fromisoformat('2026-10-29T15:23:37+08:00'))
            start.assert_called_once()
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T15:24:00+08:00')):
            self.assertEqual(self.service.state()['next_run'], '2026-10-29T20:23:00+08:00')

    def test_new_or_changed_schedule_does_not_backfill_before_it_was_saved(self):
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T10:00:00+08:00')):
            self.configure(times=['06:00', '11:00', '16:00'])
        with patch.object(self.service, '_start') as start:
            self.service.tick(datetime.fromisoformat('2026-10-29T10:00:00+08:00'))
            start.assert_not_called()
            self.service.tick(datetime.fromisoformat('2026-10-29T11:10:00+08:00'))
            start.assert_called_once()
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T12:00:00+08:00')):
            self.configure(times=['06:00', '12:30', '16:00'])
        with patch.object(self.service, '_start') as start:
            self.service.tick(datetime.fromisoformat('2026-10-29T12:00:00+08:00'))
            start.assert_not_called()
            self.service.tick(datetime.fromisoformat('2026-10-29T12:30:00+08:00'))
            start.assert_called_once()

    def test_slots_shifted_past_midnight_are_skipped_and_next_day_resets(self):
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T05:00:00+08:00')):
            self.configure(times=['06:00', '11:00', '16:00'])
        with patch.object(self.service, '_start') as start:
            self.service.tick(datetime.fromisoformat('2026-10-29T22:00:00+08:00'))
            self.assertEqual(start.call_count, 1)
            self.service.tick(datetime.fromisoformat('2026-10-29T23:59:00+08:00'))
            self.assertEqual(start.call_count, 1)
            with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T22:01:00+08:00')):
                self.assertEqual(self.service.state()['next_run'], '2026-10-30T06:00:00+08:00')
            self.service.tick(datetime.fromisoformat('2026-10-30T02:00:00+08:00'))
            self.assertEqual(start.call_count, 1)
            self.service.tick(datetime.fromisoformat('2026-10-30T06:00:00+08:00'))
            self.assertEqual(start.call_count, 2)
            self.assertEqual(self.service._load()['schedule']['delay_minutes'], 0)

    def test_saving_unchanged_schedule_preserves_delay(self):
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T05:00:00+08:00')):
            self.configure(times=['06:00', '11:00', '16:00'])
        with patch.object(self.service, '_start'):
            self.service.tick(datetime.fromisoformat('2026-10-29T09:00:00+08:00'))
        with patch('manager_parts.wakeup.local_now', return_value=datetime.fromisoformat('2026-10-29T09:30:00+08:00')):
            state = self.configure(times=['06:00', '11:00', '16:00'], model='another-model')
            self.assertEqual(state['delay_minutes'], 180)
            self.assertEqual(state['next_run'], '2026-10-29T14:00:00+08:00')

    def test_all_current_official_accounts_run_and_one_failure_does_not_stop_batch(self):
        self.configure()
        self.store['accounts']['New'] = self.account('three')
        def send(name, model):
            if name == 'A':
                raise WakeupError('授权失效')
        with patch.object(self.service, '_send', side_effect=send) as runner:
            self.service.run_now()
            self.wait()
        self.assertEqual([call.args[0] for call in runner.call_args_list], ['A', 'B', 'New'])
        state = self.service.state()
        self.assertEqual([r['status'] for r in state['results']], ['failed', 'success', 'success'])
        self.assertEqual(self.store['active_account'], 'A')

    def test_busy_slot_waits_until_available_and_disabled_schedule_never_sends(self):
        self.configure()
        self.service.run_lock.acquire()
        try:
            self.service.tick(datetime.fromisoformat('2026-10-29T08:00:00+08:00'))
            self.assertNotIn('2026-10-29 08:00', self.service._load()['slots'])
            with self.assertRaises(ValueError):
                self.service.run_now()
        finally:
            self.service.run_lock.release()
        with patch.object(self.service, '_start') as start:
            self.service.tick(datetime.fromisoformat('2026-10-29T08:05:00+08:00'))
            start.assert_called_once()
        self.assertEqual(self.service._load()['schedule']['delay_minutes'], 5)
        self.configure(enabled=False)
        with patch.object(self.service, '_start') as start:
            self.service.tick(datetime.fromisoformat('2026-10-29T13:00:00+08:00'))
            start.assert_not_called()

    def test_sender_uses_target_auth_and_does_not_modify_active_profile(self):
        before = self.manager.paths.auth.read_bytes()
        with patch('manager_parts.wakeup.send_greeting') as send:
            self.service._send('B', 'test-model')
        send.assert_called_once_with(self.store['accounts']['B']['official_auth']['tokens'],
                                     'test-model', self.service.stop_event)
        self.assertEqual(self.manager.paths.auth.read_bytes(), before)
        self.manager._codex_binary.assert_not_called()
        self.manager._save_store.assert_not_called()

    def test_sender_prefers_refreshed_active_auth_only_for_matching_account(self):
        auth = self.store['accounts']['A']['official_auth']
        active = json.loads(json.dumps(auth))
        active['tokens']['access_token'] = 'new-access'
        self.manager.paths.auth.write_text(json.dumps(active))
        with patch('manager_parts.wakeup.send_greeting') as send:
            self.service._send('A', 'test-model')
        self.assertEqual(send.call_args.args[0]['access_token'], 'new-access')
        active['tokens']['account_id'] = 'different'
        self.manager.paths.auth.write_text(json.dumps(active))
        with patch('manager_parts.wakeup.send_greeting') as send:
            self.service._send('A', 'test-model')
        self.assertEqual(send.call_args.args[0]['access_token'], 'test-access')

    def test_interrupted_results_do_not_appear_running_after_restart(self):
        data = self.service._load()
        data['results'] = [{'account': 'A', 'status': 'running', 'message': 'sending', 'at': ''}]
        self.service._save(data)
        state = self.service.state()
        self.assertFalse(state['running'])
        self.assertEqual(state['results'][0]['status'], 'failed')
        self.assertIn('中断', state['results'][0]['message'])

    def test_removed_account_and_missing_auth_fail_without_http_call(self):
        with patch('manager_parts.wakeup.send_greeting') as send:
            del self.store['accounts']['B']
            with self.assertRaises(WakeupError):
                self.service._send('B', 'test-model')
            del self.store['accounts']['A']['official_auth']['tokens']['access_token']
            self.manager.paths.auth.unlink()
            with self.assertRaises(WakeupError):
                self.service._send('A', 'test-model')
        send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
