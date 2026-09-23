#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app_version import APP_VERSION
from updater import check_update, download_update
from codex_manager import CodexManager
from manager_parts.config_import import parse_provider_config
from manager_parts.quota import read_official_quota


APP_NAME = "MaoLocal Codex 管理器"
DEFAULT_PORT = 8787
WEB_ROOT = Path(__file__).resolve().parent / "web"
MANAGER = CodexManager()
MUTATION_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "MaoLocalCodexManager/" + APP_VERSION

    def log_message(self, _format: str, *_args) -> None:
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_asset(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if path.name == "index.html":
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'",
            )
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 64 * 1024:
            raise ValueError("请求内容过大")
        if length <= 0:
            return {}
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("请求必须是 JSON 对象")
        return payload

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_asset(WEB_ROOT / "index.html", "text/html; charset=utf-8")
        elif path == "/app.css":
            self._send_asset(WEB_ROOT / "app.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send_asset(WEB_ROOT / "app.js", "text/javascript; charset=utf-8")
        elif path == "/updates.js":
            self._send_asset(WEB_ROOT / "updates.js", "text/javascript; charset=utf-8")
        elif path == "/api/updates":
            try:
                self._send_json(200, {"ok": True, "result": check_update()})
            except Exception:
                self._send_json(502, {"ok": False, "error": "无法检查更新，请确认网络正常且 GitHub 已发布版本"})
        elif path == "/api/state":
            try:
                self._send_json(200, {"ok": True, "data": MANAGER.state()})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": _safe_error(exc)})
        elif path == "/api/accounts/quota":
            try:
                name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
                with MUTATION_LOCK:
                    result = read_official_quota(MANAGER, name)
                self._send_json(200, {"ok": True, "result": result})
            except (ValueError, RuntimeError, OSError):
                self._send_json(400, {"ok": False, "error": "无法读取官方额度，请检查网络、Codex 安装或重新授权"})
        elif path == "/api/usage":
            try:
                query = parse_qs(urlparse(self.path).query)
                period = query.get("period", ["today"])[0]
                selected_date = query.get("date", [""])[0]
                self._send_json(200, {"ok": True, "result": MANAGER.usage_for_period(period, selected_date)})
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": _safe_error(exc)})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": _safe_error(exc)})
        elif path == "/api/accounts/official-login/status":
            try:
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                login_id = str(query.get("login_id", [""])[0]).strip()
                if not login_id:
                    raise ValueError("缺少官方登录会话 ID")
                result = MANAGER.official_login_status(login_id)
                self._send_json(200, {"ok": True, "result": result})
            except KeyError as exc:
                self._send_json(404, {"ok": False, "error": str(exc).strip("'")})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": _safe_error(exc)})
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/updates/download":
                self._send_json(200, {"ok": True, "result": download_update()})
                return
            if path == "/api/accounts/parse-config":
                self._send_json(200, {"ok": True, "result": parse_provider_config(body.get("config_text"))})
                return
            with MUTATION_LOCK:
                if path == "/api/accounts/save":
                    account = MANAGER.save_account(body)
                    response = {"message": "账号已保存", "account": account}
                elif path == "/api/accounts/verify":
                    result = MANAGER.verify_account(body)
                    response = {
                        "message": f"验证通过，渠道可用，共 {result['models']} 个模型",
                        "result": result,
                    }
                elif path == "/api/accounts/official-login/start":
                    result = MANAGER.start_official_login()
                    response = {"message": "已打开 OpenAI 官方登录页", "result": result}
                elif path == "/api/accounts/official-login/complete":
                    account = MANAGER.complete_official_login(
                        str(body.get("login_id", "")),
                        str(body.get("name", "")),
                    )
                    response = {"message": "官方账号已添加", "account": account}
                elif path == "/api/accounts/official-login/cancel":
                    MANAGER.cancel_official_login(str(body.get("login_id", "")))
                    response = {"message": "已取消官方登录"}
                elif path == "/api/accounts/delete":
                    MANAGER.delete_account(str(body.get("name", "")))
                    response = {"message": "账号已从管理器移除"}
                elif path == "/api/accounts/activate":
                    result = MANAGER.activate_account(str(body.get("name", "")))
                    response = {
                        "message": f"已切换账号并载入 {result['models']} 个模型",
                        "result": result,
                    }
                elif path == "/api/accounts/post-switch":
                    result = MANAGER.run_post_switch_actions(
                        str(body.get("name", "")) or None,
                        sync_models=bool(body.get("sync_models", False)),
                        model_ids=body.get("model_ids"),
                        claim_history=bool(body.get("claim_history", False)),
                    )
                    response = {"message": "切换后处理已完成", "result": result}
                elif path == "/api/models/sync":
                    result = MANAGER.sync_active(body.get("model_ids"))
                    response = {"message": f"已同步 {result['models']} 个模型", "result": result}
                elif path == "/api/models/preview":
                    result = MANAGER.preview_active_models()
                    response = {
                        "message": f"已获取 {result['models']} 个可用模型",
                        "result": result,
                    }
                elif path == "/api/models/select":
                    model = str(body.get("model", ""))
                    MANAGER.switch_model(model)
                    response = {"message": f"默认模型已切换为 {model}"}
                elif path == "/api/models/restore-official":
                    result = MANAGER.restore_official_model_catalog()
                    response = {
                        "message": f"已恢复官方模型目录，共 {result['models']} 个模型",
                        "result": result,
                    }
                elif path == "/api/image-generation/configure":
                    result = MANAGER.configure_image_generation(body)
                    response = {
                        "message": "图片配置已保存，请点击应用使其生效",
                        "result": result,
                    }
                elif path == "/api/image-generation/apply":
                    result = MANAGER.apply_image_generation()
                    messages = {
                        "installed": "图片插件已安装并应用配置，重启 Codex 后生效",
                        "updated": "图片插件已更新并应用配置，重启 Codex 后生效",
                        "current": "图片插件已是最新版本，配置已应用",
                        "disabled": "图片工具已停用",
                    }
                    response = {
                        "message": messages.get(result.get("plugin_action"), "图片工具已应用"),
                        "result": result,
                    }
                elif path == "/api/codex/launch":
                    launch = MANAGER.launch_codex(restart=bool(body.get("restart", True)))
                    response = {
                        "message": f"Codex 已{('重启' if launch == 'restarted' else '打开')}",
                        "result": {"launch": launch},
                    }
                elif path == "/api/history/claim-all":
                    result = MANAGER.claim_all_conversations(str(body.get("name", "")) or None)
                    response = {
                        "message": (
                            f"已将 {result['changed_files']} 个历史会话归纳到 "
                            f"{result['account']}，共 {result['total']} 个"
                        ),
                        "result": result,
                    }
                else:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
            self._send_json(200, {"ok": True, **response, "data": MANAGER.state()})
        except KeyError as exc:
            self._send_json(404, {"ok": False, "error": str(exc).strip("'")})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "error": _safe_error(exc)})
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": _safe_error(exc)})


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace(str(MANAGER.paths.auth), "auth.json")
    return message or type(exc).__name__


def _launch_window(url: str) -> None:
    try:
        import webview  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少 pywebview，请执行 pip install -r requirements.txt") from exc
    webview.create_window(
        APP_NAME,
        url,
        width=960,
        height=640,
        min_size=(960, 640),
        resizable=False,
        background_color="#ffffff",
    )
    webview.start()


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"[maolocal-codex] {APP_NAME} v{APP_VERSION} · {url}", flush=True)
    if args.no_open:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    else:
        _launch_window(url)
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    main()
