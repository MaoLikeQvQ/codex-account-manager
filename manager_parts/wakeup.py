"""Daily official-account greetings, isolated from the active Codex profile."""
import copy
import json
import re
import threading
from datetime import datetime, timedelta
from .wakeup_http import send_greeting


def local_now():
    return datetime.now().astimezone()


def scheduled_slots(data, now):
    """Return today's unclaimed original slots and their shifted times."""
    day = now.date()
    schedule = data.get('schedule', {})
    delay = schedule.get('delay_minutes', 0) if schedule.get('date') == day.isoformat() else 0
    start = schedule.get('start', '') if schedule.get('date') == day.isoformat() else ''
    slots = []
    for value in data['times']:
        original = datetime.combine(day, datetime.strptime(value, '%H:%M').time()).astimezone()
        key = original.strftime('%Y-%m-%d %H:%M')
        shifted = original + timedelta(minutes=delay)
        if key not in data['slots'] and (not start or key >= start) and shifted.date() == day:
            slots.append((key, shifted))
    return slots


class WakeupError(RuntimeError):
    pass


class WakeupService:
    def __init__(self, manager, mutation_lock):
        self.manager = manager
        self.mutation_lock = mutation_lock
        self.path = manager.paths.app_home / 'official-wakeup.json'
        self.lock = threading.RLock()
        self.run_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.worker = None

    def _load(self):
        if not self.path.exists():
            return {'enabled': False, 'times': [], 'model': '', 'slots': [], 'results': []}
        return json.loads(self.path.read_text(encoding='utf-8'))

    def _save(self, data):
        self.manager._write_private_json(self.path, data)

    def state(self):
        with self.lock:
            data = self._load()
            if not self.run_lock.locked():
                for result in data['results']:
                    if result['status'] in {'pending', 'running'}:
                        result.update(status='failed', message='上次运行已中断，未自动补发')
            now = local_now()
            candidates = []
            schedule = data.get('schedule', {})
            delay = schedule.get('delay_minutes', 0) if schedule.get('date') == now.date().isoformat() else 0
            if data['enabled'] and data['times']:
                slots = scheduled_slots(data, now)
                if slots:
                    candidates.append(max(now, slots[0][1]))
                else:
                    day = now.date() + timedelta(days=1)
                    candidates.append(datetime.combine(day, datetime.strptime(data['times'][0], '%H:%M').time()).astimezone())
            return {**{key: data[key] for key in ('enabled', 'times', 'model', 'results')},
                    'running': self.run_lock.locked(), 'timezone': str(now.tzinfo),
                    'next_run': min(candidates).isoformat() if candidates else None,
                    'delay_minutes': delay,
                    'error': data.get('error', '')}

    def configure(self, body):
        enabled, times, model = body.get('enabled'), body.get('times'), body.get('model')
        if not isinstance(enabled, bool) or not isinstance(times, list) or len(times) > 48:
            raise ValueError('请设置开关和每天最多 48 个时间点')
        if any(not isinstance(t, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', t) for t in times):
            raise ValueError('时间格式必须为 HH:MM（00:00 至 23:59）')
        if not isinstance(model, str) or len(model) > 120 or (model and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*', model)):
            raise ValueError('请输入有效的请求模型名称')
        if enabled and (not times or not model):
            raise ValueError('启用时至少设置一个时间点和请求模型')
        with self.lock:
            data = self._load()
            new_times = sorted(set(times))
            if enabled and (not data['enabled'] or new_times != data['times']):
                now = local_now()
                data['schedule'] = {'date': now.date().isoformat(), 'delay_minutes': 0,
                                    'start': now.strftime('%Y-%m-%d %H:%M')}
            data.update(enabled=enabled, times=new_times, model=model)
            self._save(data)
        return self.state()

    def tick(self, now=None):
        now = now or local_now()
        with self.lock:
            data = self._load()
            if not data['enabled']:
                return
            slots = scheduled_slots(data, now)
            if not slots or slots[0][1] > now:
                return
            slot, planned = slots[0]
            if self.run_lock.locked():
                return
            schedule = data.get('schedule', {})
            previous_delay = schedule.get('delay_minutes', 0) if schedule.get('date') == now.date().isoformat() else 0
            delay = max(0, int((now.replace(second=0, microsecond=0) - planned).total_seconds() // 60))
            data['schedule'] = {'date': now.date().isoformat(), 'delay_minutes': previous_delay + delay,
                                'start': schedule.get('start', '') if schedule.get('date') == now.date().isoformat() else ''}
            # Claim the original slot before sending to avoid duplicate requests after restart.
            data['slots'] = [*data['slots'], slot][-4320:]
            self._save(data)
            self._start(data['model'])

    def run_now(self):
        with self.lock:
            data = self._load()
            if not data['model']:
                raise ValueError('请先保存请求模型')
            self._start(data['model'])
        return self.state()

    def _start(self, model):
        if not self.run_lock.acquire(blocking=False):
            raise ValueError('已有唤醒任务正在进行，请等待完成')
        try:
            with self.mutation_lock:
                names = [name for name, account in self.manager._load_store().get('accounts', {}).items()
                         if self.manager._account_type(account) == 'official']
            data = self._load()
            data['results'] = [{'account': name, 'status': 'pending', 'message': '等待发送', 'at': ''} for name in names]
            data['error'] = '' if names else '没有可唤醒的官方账号'
            self._save(data)
            self.worker = threading.Thread(target=self._run, args=(names, model), daemon=True)
            self.worker.start()
        except Exception:
            self.run_lock.release()
            raise

    def _run(self, names, model):
        try:
            for index, name in enumerate(names):
                if self.stop_event.is_set():
                    for remaining in range(index, len(names)):
                        self._update(remaining, 'failed', '应用已退出，未发送')
                    break
                try:
                    self._update(index, 'running', '正在发送 hi')
                    self._send(name, model)
                    self._update(index, 'success', 'hi 已完成响应')
                except Exception as error:
                    # Never expose response bodies or credentials.
                    message = str(error) if isinstance(error, WakeupError) else '执行失败，请检查网络和本地账号档案'
                    self._update(index, 'failed', message)
        finally:
            self.run_lock.release()

    def _update(self, index, status, message):
        with self.lock:
            data = self._load()
            data['results'][index].update(status=status, message=message, at=local_now().isoformat(timespec='seconds'))
            self._save(data)

    def _send(self, name, model):
        manager = self.manager
        with self.mutation_lock:
            store = manager._load_store()
            account = store.get('accounts', {}).get(name)
            if not account or manager._account_type(account) != 'official':
                raise WakeupError('账号已移除或类型已变化，已跳过')
            auth = copy.deepcopy(account.get('official_auth'))
            active_auth = manager._read_json(manager.paths.auth, {}) if store.get('active_account') == name else {}
            if (active_auth.get('tokens', {}).get('account_id') and
                    active_auth.get('tokens', {}).get('account_id') == (auth or {}).get('tokens', {}).get('account_id')):
                auth = active_auth
        tokens = (auth or {}).get('tokens', {})
        if not tokens.get('access_token') or not tokens.get('account_id'):
            raise WakeupError('缺少官方授权，请重新登录')
        try:
            send_greeting(tokens, model, self.stop_event)
        except RuntimeError as error:
            raise WakeupError(str(error)) from None

    def start(self):
        if self.thread is not None:
            return
        def loop():
            while not self.stop_event.is_set():
                try:
                    self.tick()
                except Exception:
                    with self.lock:
                        try:
                            data = self._load()
                            data['error'] = '定时任务执行失败，请检查本地配置文件'
                            self._save(data)
                        except (OSError, ValueError):
                            print('[wakeup] 无法读取或保存定时任务状态', flush=True)
                self.stop_event.wait(5)
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=5)
        if self.thread:
            self.thread.join(timeout=2)
