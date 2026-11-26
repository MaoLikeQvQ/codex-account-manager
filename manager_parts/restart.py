"""Track the desktop process generation rather than missing brief manual exits."""
from datetime import datetime
import os
import subprocess
import time

from .common import CODEX_APP


class RestartMixin:
    @staticmethod
    def _codex_process():
        try:
            result = subprocess.run(
                ['/bin/ps', '-axo', 'pid=,lstart=,comm='], check=False,
                capture_output=True, text=True, timeout=5,
                env={**os.environ, 'LC_ALL': 'C'},
            )
            if result.returncode or not isinstance(result.stdout, str):
                return None
            roots = {str(CODEX_APP), str(CODEX_APP.with_name('Codex.app'))}
            for line in result.stdout.splitlines():
                fields = line.split(None, 6)
                if len(fields) != 7 or not fields[0].isdigit():
                    continue
                if not any(fields[6].startswith(root + '/Contents/MacOS/') for root in roots):
                    continue
                started = datetime.strptime(' '.join(fields[1:6]), '%a %b %d %H:%M:%S %Y')
                return {'identity': fields[0] + ':' + started.isoformat(), 'started_at': started.timestamp()}
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return None

    def _mark_restart_required(self, store):
        store['restart_required'] = self.codex_running()
        store.pop('restart_process', None)
        store.pop('restart_requested_at', None)
        if store['restart_required']:
            store['restart_requested_at'] = time.time()
            process = self._codex_process()
            if process:
                store['restart_process'] = process['identity']

    def _refresh_restart_requirement(self, store, running):
        if not store.get('restart_required'):
            return
        completed = not running
        if running:
            process = self._codex_process()
            previous = store.get('restart_process')
            if process and previous:
                completed = process['identity'] != previous
            elif process:
                requested = store.get('restart_requested_at')
                if not isinstance(requested, (int, float)):
                    account = store.get('accounts', {}).get(store.get('active_account'), {})
                    try:
                        requested = datetime.fromisoformat(account.get('updated_at', '')).timestamp()
                    except (ValueError, TypeError):
                        requested = None
                completed = requested is not None and process['started_at'] > requested
        if completed:
            store['restart_required'] = False
            store.pop('restart_process', None)
            store.pop('restart_requested_at', None)
            self._save_store(store)
