"""One explicit, non-retrying pelican SVG request using the active account."""
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

from .benchmark_svg import safe_svg_preview

PROMPT = 'Draw an SVG of a pelican riding a bicycle. Return only a complete, self-contained SVG, without Markdown fences, scripts, external images, or external resources.'
TIMEOUT_SECONDS = 180
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
OFFICIAL_RESPONSES_URL = 'https://chatgpt.com/backend-api/codex/responses'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _text(payload):
    if not isinstance(payload, dict) or payload.get('error') or payload.get('status') != 'completed':
        raise RuntimeError('模型响应未完成或被拒绝；未自动重试。')
    parts = []
    for item in payload.get('output', []):
        if isinstance(item, dict) and item.get('type') == 'message':
            for part in item.get('content', []):
                if isinstance(part, dict) and part.get('type') == 'output_text' and isinstance(part.get('text'), str):
                    parts.append(part['text'])
    reply = ''.join(parts).strip()
    if not reply:
        raise RuntimeError('模型没有返回文本；未自动重试。')
    return reply


def _read_response(response, started):
    if 'text/event-stream' not in response.headers.get('Content-Type', '').lower():
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise RuntimeError('测试响应过大，已停止读取；未自动重试。')
        return json.loads(body)
    total = 0
    data = []
    completed = None

    def consume():
        nonlocal completed
        value = '\n'.join(data)
        data.clear()
        if not value or value == '[DONE]':
            return
        event = json.loads(value)
        if event.get('type') in {'error', 'response.failed', 'response.incomplete'}:
            raise RuntimeError('模型响应未完成或被拒绝；未自动重试。')
        if event.get('type') == 'response.completed':
            completed = event.get('response')

    while True:
        if time.monotonic() - started > TIMEOUT_SECONDS:
            raise TimeoutError()
        line = response.readline(MAX_RESPONSE_BYTES + 1)
        total += len(line)
        if total > MAX_RESPONSE_BYTES:
            raise RuntimeError('测试响应过大，已停止读取；未自动重试。')
        if not line:
            consume()
            break
        text = line.decode('utf-8').rstrip('\r\n')
        if not text:
            consume()
            if completed is not None:
                break
        elif text.startswith('data:'):
            data.append(text[5:].lstrip(' '))
    if completed is None:
        raise RuntimeError('模型响应流提前结束，结果不完整；未自动重试。')
    return completed


def run_pelican_test(manager, expected):
    store = manager._load_store()
    name = store.get('active_account', '')
    account = store.get('accounts', {}).get(name)
    if not isinstance(account, dict) or not name:
        raise ValueError('请先启用一个账号。')
    if name != expected.get('account'):
        raise ValueError('当前账号已变化，请重新打开测试。')
    if account.get('pending_apply'):
        raise ValueError('当前账号有待应用修改，请先应用后再测试。')
    config = manager._read_toml(manager.paths.config)
    model = str(config.get('model') or '').strip()
    if not model or model != expected.get('model'):
        raise ValueError('默认模型为空或已变化，请刷新后再测试。')
    effort = str(account.get('reasoning_effort') or config.get('model_reasoning_effort') or 'high')
    if manager._account_type(account) == 'official':
        auth = manager._read_json(manager.paths.auth, {})
        tokens = auth.get('tokens', {})
        # Use the active credentials, which Codex may have refreshed since account activation.
        if not tokens.get('access_token') or not tokens.get('account_id'):
            raise ValueError('官方授权不完整，请重新登录并使用该账号。')
        saved_id = account.get('official_auth', {}).get('tokens', {}).get('account_id')
        if config.get('model_provider') != 'openai' or (saved_id and saved_id != tokens['account_id']):
            raise ValueError('当前官方授权与账号档案不一致，请重新使用该账号。')
        endpoint = OFFICIAL_RESPONSES_URL
        headers = {'Authorization': 'Bearer ' + tokens['access_token'], 'ChatGPT-Account-ID': tokens['account_id']}
    else:
        provider = account.get('provider_config', {})
        base = str(provider.get('base_url', '')).rstrip('/')
        if not base:
            raise ValueError('当前账号缺少服务地址。')
        query = urlencode(provider.get('query_params', {}))
        endpoint = base + '/responses' + ('?' + query if query else '')
        headers = manager._model_request_headers(account)
    headers.update({'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
    body = {'model': model, 'instructions': 'You are a helpful assistant.',
            'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': PROMPT}]}],
            'reasoning': {'effort': effort}, 'stream': True, 'store': False}
    request = urllib.request.Request(endpoint, data=json.dumps(body).encode(), headers=headers, method='POST')
    started = time.monotonic()
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT_SECONDS) as response:
            payload = _read_response(response, started)
        reply = _text(payload)
    except urllib.error.HTTPError as error:
        error.close()
        raise RuntimeError(f'测试请求失败：HTTP {error.code}，请检查授权、模型权限或额度；未自动重试。') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('测试连接失败或超时；未自动重试。') from None
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, AttributeError):
        raise RuntimeError('测试接口未返回有效的 Responses 数据；未自动重试。') from None
    preview, warning = safe_svg_preview(reply)
    return {'account': name, 'model': model, 'reported_model': str(payload.get('model', '')),
            'reasoning_effort': effort, 'prompt': PROMPT, 'reply': reply, 'preview_svg': preview,
            'warning': warning, 'elapsed_ms': round((time.monotonic() - started) * 1000)}
