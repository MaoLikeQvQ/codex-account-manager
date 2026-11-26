"""Manual Codex restarts must clear only the configuration they supersede."""
from test_support import AccountManagerTestBase, patch, json


class RestartStateTests(AccountManagerTestBase):
    def activate(self):
        self.save_account('A')
        with patch.object(self.manager, 'codex_running', return_value=True), \
             patch.object(self.manager, '_codex_process', return_value={'identity': '100:first', 'started_at': 1}):
            self.manager.activate_account('A')

    def test_same_process_stays_pending_but_manual_restart_clears_flag(self):
        self.activate()
        with patch.object(self.manager, 'codex_running', return_value=True):
            with patch.object(self.manager, '_codex_process', return_value={'identity': '100:first', 'started_at': 1}):
                self.assertTrue(self.manager.state()['codex']['restart_required'])
            with patch.object(self.manager, '_codex_process', return_value={'identity': '101:second', 'started_at': 2}):
                self.assertFalse(self.manager.state()['codex']['restart_required'])
        self.assertFalse(json.loads(self.paths.accounts.read_text())['restart_required'])

    def test_unavailable_process_identity_never_fabricates_a_restart(self):
        self.activate()
        with patch.object(self.manager, 'codex_running', return_value=True), \
             patch.object(self.manager, '_codex_process', return_value=None):
            self.assertTrue(self.manager.state()['codex']['restart_required'])

    def test_legacy_pending_flag_clears_after_process_started_after_account_update(self):
        self.activate()
        store=json.loads(self.paths.accounts.read_text())
        store.pop('restart_process',None)
        store.pop('restart_requested_at',None)
        store['accounts']['A']['updated_at']='2026-10-27T08:00:00+00:00'
        self.paths.accounts.write_text(json.dumps(store))
        with patch.object(self.manager, 'codex_running', return_value=True), \
             patch.object(self.manager, '_codex_process', return_value={'identity':'new','started_at':1793088001}):
            self.assertFalse(self.manager.state()['codex']['restart_required'])

    def test_process_identity_reads_only_main_app_and_includes_start_time(self):
        from manager_parts.common import CODEX_APP
        from types import SimpleNamespace
        output = ('99 Tue Oct 27 15:00:00 2026 /usr/local/bin/codex\n'
                  f'100 Tue Oct 27 16:00:00 2026 {CODEX_APP}/Contents/MacOS/ChatGPT\n')
        with patch('manager_parts.restart.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=output)):
            process = self.manager._codex_process()
        self.assertEqual(process['identity'], '100:2026-10-27T16:00:00')
