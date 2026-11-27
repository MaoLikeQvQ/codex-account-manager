"""Read official quota in an isolated Codex home; never switch active accounts."""
import json
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime


def read_official_quota(manager, name):
    account = manager._load_store().get('accounts', {}).get(name)
    if not account or manager._account_type(account) != 'official':
        raise ValueError('请选择 OpenAI 官方账号')
    auth = account.get('official_auth')
    if not auth:
        raise ValueError('缺少官方授权，请重新登录')
    with tempfile.TemporaryDirectory(prefix='quota-', dir=manager.paths.app_home) as directory:
        home = Path(directory)
        manager._atomic_write(home / 'auth.json', json.dumps(auth))
        env = manager._codex_environment(home)
        for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID'):
            env.pop(key, None)
        process = subprocess.Popen(
            [manager._codex_binary(), 'app-server', '--stdio', '-c', 'cli_auth_credentials_store="file"'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, env=env, cwd=directory,
        )
        messages = queue.Queue()
        def read():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    continue
            messages.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        def request(identifier, method, params):
            manager._write_app_server_message(process, {'id': identifier, 'method': method, 'params': params})
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    message = messages.get(timeout=max(.01, deadline-time.monotonic()))
                except queue.Empty:
                    break
                if message is None:
                    raise RuntimeError('官方查询进程已结束，请重试')
                if message.get('id') == identifier:
                    if message.get('error'):
                        error = message['error']
                        detail = str(error.get('message', '')).lower()
                        if 'token_expired' in detail or '401' in detail or 'unauthorized' in detail:
                            raise PermissionError('官方登录已过期或失效，请点击“管理授权”重新登录')
                        if error.get('code') == -32601:
                            raise RuntimeError('当前 Codex 版本不支持此用量接口，请更新 Codex')
                        if '403' in detail:
                            raise RuntimeError('官方拒绝访问此账号的用量，请检查账号权限')
                        raise RuntimeError('官方用量接口请求失败，请检查网络后重试')
                    return message.get('result', {})
            raise RuntimeError('官方查询超时，请检查网络后重试')
        result = {'account': name, 'limits': None, 'usage': None, 'errors': {}}
        try:
            request(1, 'initialize', {'clientInfo': {'name': 'maolocal-quota', 'version': '1.0'}, 'capabilities': {'experimentalApi': True}})
            manager._write_app_server_message(process, {'method': 'initialized', 'params': {}})
            refresh_attempted = False
            for identifier, key, method in [(2, 'limits', 'account/rateLimits/read'), (3, 'usage', 'account/usage/read')]:
                try:
                    result[key] = request(identifier, method, {})
                except PermissionError as error:
                    if not refresh_attempted:
                        refresh_attempted = True
                        try:
                            request(10, 'account/read', {'refreshToken': True})
                            refreshed = json.loads((home / 'auth.json').read_text())
                            current_store = manager._load_store()
                            current = current_store.get('accounts', {}).get(name)
                            if current and current.get('official_auth') == auth:
                                current['official_auth'] = refreshed
                                manager._save_store(current_store)
                            result[key] = request(identifier + 100, method, {})
                            continue
                        except (RuntimeError, PermissionError, OSError, ValueError):
                            pass
                    result['errors'][key] = str(error)
                except RuntimeError as error:
                    result['errors'][key] = str(error)
            result['fetched_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
            return result
        finally:
            manager._terminate_process(process)
            reader.join(timeout=2)
            process.stdin.close()
            process.stdout.close()
