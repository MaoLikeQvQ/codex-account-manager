#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import json
import mimetypes
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app_version import APP_VERSION
from updater import check_update, download_update
from codex_manager import CodexManager
from manager_parts.config_import import parse_provider_config
from manager_parts.quota import read_official_quota
from manager_parts.quota_estimate import estimate_quota_amounts
from manager_parts.benchmark import run_pelican_test
from manager_parts.wakeup import WakeupService


APP_NAME = "MaoX 账号管理器"
DEFAULT_PORT = 8787
WEB_ROOT = Path(__file__).resolve().parent / "web"
MANAGER = CodexManager()
MUTATION_LOCK = threading.Lock()
BENCHMARK_LOCK = threading.Lock()
PRICE_SYNC_LOCK = threading.Lock()
WAKEUP = WakeupService(MANAGER, MUTATION_LOCK)


def updates_enabled() -> bool:
    return bool(getattr(sys, "frozen", False))


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
        nonce = None
        if path.name == "index.html":
            nonce = secrets.token_urlsafe(24)
            enabled = "true" if updates_enabled() else "false"
            body = body.replace(b"<body>", f'<body data-updates-enabled="{enabled}">'.encode(), 1)
            body = body.replace(b"</head>", f'<meta name="csp-nonce" content="{nonce}"></head>'.encode(), 1)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if path.name == "index.html":
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                f"style-src-elem 'self' 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'",
            )
        self.end_headers()
        self.wfile.write(body)

    def _send_bundled_asset(self, url_path: str) -> None:
        # Only the public build directory is exposed; decoded paths and symlinks
        # must remain inside it, even when a client bypasses URL normalization.
        asset_path = unquote(url_path).removeprefix("/assets/")
        if "\0" in asset_path or ".." in asset_path.split("/"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        asset_root = (WEB_ROOT / "assets").resolve()
        target = (asset_root / asset_path).resolve()
        if not target.is_relative_to(asset_root):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".js", ".mjs"}:
            content_type = "text/javascript"
        if content_type.startswith("text/"):
            content_type += "; charset=utf-8"
        self._send_asset(target, content_type)

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
        elif path.startswith("/assets/"):
            self._send_bundled_asset(path)
        elif path == "/app.css":
            self._send_asset(WEB_ROOT / "app.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send_asset(WEB_ROOT / "app.js", "text/javascript; charset=utf-8")
        elif path == "/updates.js":
            self._send_asset(WEB_ROOT / "updates.js", "text/javascript; charset=utf-8")
        elif path == "/api/updates":
            if not updates_enabled():
                self._send_json(200, {"ok": True, "result": {"enabled": False, "available": False,
                    "current_version": APP_VERSION, "message": "开发模式不检查应用更新"}})
                return
            try:
                self._send_json(200, {"ok": True, "result": check_update()})
            except Exception:
                self._send_json(502, {"ok": False, "error": "无法检查更新，请确认网络正常且 GitHub 已发布版本"})
        elif path == "/api/accounts/wakeup":
            try:
                self._send_json(200, {"ok": True, "result": WAKEUP.state()})
            except Exception:
                self._send_json(500, {"ok": False, "error": "无法读取定时唤醒配置"})
        elif path == "/api/state":
            try:
                self._send_json(200, {"ok": True, "data": MANAGER.state(include_conversations=False)})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": _safe_error(exc)})
        elif path == "/api/accounts/quota":
            try:
                name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
                with MUTATION_LOCK:
                    result = read_official_quota(MANAGER, name)
                    result['amount_estimate'] = estimate_quota_amounts(MANAGER, name, result.get('limits'))
                self._send_json(200, {"ok": True, "result": result})
            except (ValueError, RuntimeError, OSError):
                self._send_json(400, {"ok": False, "error": "无法读取官方额度，请检查网络、Codex 安装或重新授权"})
        elif path == "/api/requests":
            try:
                query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                raw_limit = query.get("limit", ["100"])[0]
                limit = int(raw_limit)
                result = MANAGER.requests_for_period(
                    query.get("period", ["today"])[0], query.get("date", [""])[0], limit,
                )
                self._send_json(200, {"ok": True, "result": result})
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": _safe_error(exc)})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": _safe_error(exc)})
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

    def _receive_timing(self) -> None:
        # OTLP is sent by the local Codex process, never from a web page.
        if self.client_address[0] != "127.0.0.1" or self.headers.get("Origin"):
            self._send_json(403, {"error": "local process only"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4 * 1024 * 1024:
                raise ValueError("invalid telemetry size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or not isinstance(payload.get("resourceLogs"), list):
                raise ValueError("invalid OTLP JSON")
            request_events = MANAGER._timing_store.ingest(payload)
            MANAGER._timing_status = "receiving_requests" if request_events else "awaiting_request_events"
            self._send_json(200, {})
        except (ValueError, TypeError, AttributeError, KeyError):
            self._send_json(400, {"error": "invalid OTLP JSON"})
        except Exception:
            self._send_json(500, {"error": "timing storage failed"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/timing/otlp":
            self._receive_timing()
            return
        try:
            body = self._read_json()
            if path == "/api/pricing/sync":
                self._sync_model_prices()
                return
            if path in {"/api/accounts/wakeup/configure", "/api/accounts/wakeup/run"}:
                result = WAKEUP.configure(body) if path.endswith("/configure") else WAKEUP.run_now()
                self._send_json(200, {"ok": True, "result": result})
                return
            if path == "/api/benchmark/pelican":
                if not BENCHMARK_LOCK.acquire(blocking=False):
                    self._send_json(409, {"ok": False, "error": "已有测试正在进行，请等待完成。"})
                    return
                try:
                    with MUTATION_LOCK:
                        result = run_pelican_test(MANAGER, body)
                    self._send_json(200, {"ok": True, "result": result})
                finally:
                    BENCHMARK_LOCK.release()
                return
            if path == "/api/updates/download":
                if not updates_enabled():
                    self._send_json(403, {"ok": False, "error": "开发模式不支持下载或安装应用更新"})
                    return
                self._send_json(200, {"ok": True, "result": download_update()})
                return
            if path == "/api/accounts/parse-config":
                self._send_json(200, {"ok": True, "result": parse_provider_config(body.get("config_text"))})
                return
            with MUTATION_LOCK:
                if path == "/api/accounts/save":
                    account = MANAGER.save_account(body)
                    response = {"message": "账号档案已保存，请点击应用修改" if account["pending_apply"] else "账号档案已保存，点击使用即可写入配置", "account": account}
                elif path == "/api/accounts/verify":
                    result = MANAGER.verify_account(body)
                    response = {
                        "message": f"已读取渠道模型列表，共 {result['models']} 个模型；尚未验证推理能力",
                        "result": result,
                    }
                elif path == "/api/accounts/verify-connection":
                    result = MANAGER.verify_connection(body)
                    response = {"message": f"连接验证通过（{result['elapsed_ms']} ms）：{result['reply']}", "result": result}
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
                    history = result.get("history", {})
                    status = history.get("status")
                    try:
                        result["launch"] = MANAGER.launch_codex(restart=True)
                    except Exception as exc:
                        result["launch"] = "failed"
                        result["launch_error"] = _safe_error(exc)
                    if status == "pending":
                        message = "账号配置已写入，但历史归属待处理，下次切换账号或启动/重启 Codex 时自动重试"
                    elif status == "partial":
                        message = f"账号配置已写入，但有 {history.get('failed', 0)} 个历史会话未能归纳，下次切换账号或启动/重启 Codex 时自动重试"
                    elif status == "error":
                        message = "账号配置已写入，但历史归纳失败，下次切换账号或启动/重启 Codex 时自动重试"
                    else:
                        message = "账号配置已写入，历史会话已归纳到当前账号"
                    if result["launch"] == "failed":
                        message += f"；Codex 自动重启失败：{result['launch_error']}"
                    else:
                        message += "；Codex 已启动或重启"
                    response = {
                        "message": message,
                        "warning": status in {"partial", "error"} or result["launch"] == "failed",
                        "result": result,
                    }
                elif path == "/api/image-generation/configure":
                    result = MANAGER.configure_image_generation(body)
                    response = {
                        "message": "Custom ImageGen 配置已保存，请点击应用使其生效",
                        "result": result,
                    }
                elif path == "/api/image-generation/apply":
                    result = MANAGER.apply_image_generation()
                    messages = {
                        "installed": "Custom ImageGen 已安装并应用配置，重启 Codex 后生效",
                        "updated": "Custom ImageGen 已更新并应用配置，重启 Codex 后生效",
                        "current": "Custom ImageGen 已是最新版本，配置已应用",
                        "disabled": "Custom ImageGen 已停用",
                    }
                    response = {
                        "message": messages.get(result.get("plugin_action"), "Custom ImageGen 已应用"),
                        "result": result,
                    }
                elif path == "/api/codex/launch":
                    launch = MANAGER.launch_codex(restart=bool(body.get("restart", True)))
                    pending_history = MANAGER.state(include_conversations=False).get("history_claim")
                    message = f"Codex 已{('重启' if launch == 'restarted' else '打开')}"
                    if pending_history:
                        message += "，但历史归属未完成；下次切换账号或启动/重启 Codex 时自动重试归纳"
                    response = {
                        "message": message,
                        "warning": bool(pending_history),
                        "result": {"launch": launch},
                    }
                elif path == "/api/history/claim-all":
                    result = MANAGER.claim_all_conversations(str(body.get("name", "")) or None)
                    message = (
                        f"已将 {result['changed_files']} 个历史会话归纳到 "
                        f"{result['account']}，共 {result['total']} 个"
                    )
                    if result["failed"]:
                        message += f"；另有 {result['failed']} 个历史会话未能归纳"
                    response = {
                        "message": message,
                        "warning": bool(result["failed"]),
                        "result": result,
                    }
                else:
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
            self._send_json(200, {"ok": True, **response, "data": MANAGER.state(include_conversations=False)})
        except KeyError as exc:
            self._send_json(404, {"ok": False, "error": str(exc).strip("'")})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "error": _safe_error(exc)})
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": _safe_error(exc)})

    def _sync_model_prices(self) -> None:
        if self.headers.get_content_type() != "application/json":
            self._send_json(415, {"ok": False, "error": "同步请求必须使用 JSON"})
            return
        if not PRICE_SYNC_LOCK.acquire(blocking=False):
            self._send_json(409, {"ok": False, "error": "模型价格正在同步，请稍候。"})
            return
        try:
            result = MANAGER.sync_model_prices()
            if result["status"] != "fresh":
                self._send_json(502, {"ok": False, "error": result["warning"]})
            elif result.get("warning"):
                self._send_json(500, {"ok": False, "error": "已下载最新价格，但本地缓存保存失败。"})
            else:
                self._send_json(200, {"ok": True, "result": result,
                    "message": f"已同步 {result['model_count']} 个模型的价格"})
        finally:
            PRICE_SYNC_LOCK.release()


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace(str(MANAGER.paths.auth), "auth.json")
    return message or type(exc).__name__


def _launch_window(url: str) -> None:
    try:
        import webview  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少 pywebview，请执行 pip install -r requirements.txt") from exc
    from native_window import enable_first_mouse
    enable_first_mouse()
    webview.create_window(
        APP_NAME,
        url,
        width=1180,
        height=820,
        min_size=(960, 640),
        resizable=True,
        background_color="#ffffff",
    )
    webview.start(private_mode=False, storage_path=str(MANAGER.paths.app_home / "webview"))


def _create_server(port: int | None) -> ThreadingHTTPServer:
    if port is not None:
        return ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # Prefer stable nearby ports so Codex can reuse its configured event endpoint
    # after normal restarts. Let the OS select a port only if these are all busy.
    candidates = [*range(DEFAULT_PORT, min(DEFAULT_PORT + 10, 65536)), 0]
    for candidate in candidates:
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
        except OSError as error:
            if error.errno != errno.EADDRINUSE or candidate == 0:
                raise
    raise RuntimeError("无法分配本机服务端口")


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=None,
                        help=f"指定服务端口（默认优先使用 {DEFAULT_PORT}，占用时自动选择）")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    MANAGER._clear_managed_catalog()

    server = _create_server(args.port)
    from manager_parts.timing_config import configure_timing
    config_text = MANAGER._read_text(MANAGER.paths.config)
    updated, timing_status = configure_timing(
        config_text, f"http://127.0.0.1:{server.server_port}/api/timing/otlp",
    )
    MANAGER._timing_endpoint = f"http://127.0.0.1:{server.server_port}/api/timing/otlp"
    MANAGER._timing_status = timing_status
    if updated != config_text:
        MANAGER._backup_many(MANAGER.paths.config)
        MANAGER._commit_text_files([(MANAGER.paths.config, updated)], "请求计时配置")
        MANAGER._timing_status = "awaiting_events"
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    WAKEUP.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"[maolocal-codex] {APP_NAME} v{APP_VERSION} · {url}", flush=True)
    try:
        if args.no_open:
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
        else:
            _launch_window(url)
    finally:
        WAKEUP.stop()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
