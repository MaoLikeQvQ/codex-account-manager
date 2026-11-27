"""Minimal official HTTP greeting; never persist replies or raw errors."""
import json
import time
import urllib.error
import urllib.request


RESPONSES_URL = 'https://chatgpt.com/backend-api/codex/responses'
TIMEOUT_SECONDS = 90
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_greeting(tokens, model, stop_event):
    if stop_event.is_set():
        raise RuntimeError('应用正在退出，已停止发送')
    body = {'model': model, 'instructions': 'Reply briefly to the greeting. Do not use tools.',
            'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'hi'}]}],
            'reasoning': {'effort': 'low'}, 'stream': True, 'store': False}
    request = urllib.request.Request(RESPONSES_URL, data=json.dumps(body).encode(), headers={
        'Authorization': 'Bearer ' + tokens['access_token'],
        'ChatGPT-Account-ID': tokens['account_id'], 'Content-Type': 'application/json',
        'Accept': 'text/event-stream', 'Accept-Encoding': 'identity'}, method='POST')
    started = time.monotonic()
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT_SECONDS) as response:
            # The official endpoint can omit Content-Type; parse the requested SSE format directly.
            data, total = [], 0

            def consume():
                raw = '\n'.join(data)
                data.clear()
                if not raw or raw == '[DONE]':
                    return False
                event = json.loads(raw)
                if event.get('type') in {'error', 'response.failed', 'response.incomplete'}:
                    raise RuntimeError('未完成响应，请检查授权、模型权限或额度')
                if event.get('type') == 'response.completed':
                    result = event.get('response', {})
                    if result.get('status') != 'completed' or result.get('error'):
                        raise RuntimeError('模型响应未完成')
                    return True
                return False

            while True:
                if stop_event.is_set():
                    raise RuntimeError('应用正在退出，已停止发送')
                if time.monotonic() - started >= TIMEOUT_SECONDS:
                    raise TimeoutError()
                line = response.readline(MAX_RESPONSE_BYTES + 1)
                total += len(line)
                if total > MAX_RESPONSE_BYTES:
                    raise RuntimeError('响应过大，已停止读取')
                if not line:
                    if consume():
                        return
                    raise RuntimeError('响应流提前结束，未完成响应')
                text = line.decode('utf-8').rstrip('\r\n')
                if not text:
                    if consume():
                        return
                elif text.startswith('data:'):
                    data.append(text[5:].lstrip(' '))
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 401:
            raise RuntimeError('官方授权已失效，请重新登录（HTTP 401）') from None
        raise RuntimeError(f'发送失败：HTTP {error.code}，请检查模型权限或额度') from None
    except (TimeoutError, urllib.error.URLError, OSError) as error:
        if isinstance(error, TimeoutError) or isinstance(getattr(error, 'reason', None), TimeoutError):
            raise RuntimeError('发送超时，本轮已结束') from None
        raise RuntimeError('网络连接失败，请检查网络或代理') from None
    except (ValueError, UnicodeDecodeError, AttributeError, TypeError):
        raise RuntimeError('接口未返回有效的流式响应') from None
