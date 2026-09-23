from __future__ import annotations

from .common import *
from .common import _now


class OfficialMixin:
    def start_official_login(self) -> dict[str, Any]:
        """在隔离的 CODEX_HOME 中启动官方 ChatGPT OAuth 登录。"""
        binary = self._codex_binary()
        with self._official_login_lock:
            if any(
                session.get("status") == "pending"
                for session in self._official_login_sessions.values()
            ):
                raise ValueError("已有官方登录正在进行，请先在浏览器完成授权")
        login_home = Path(tempfile.mkdtemp(prefix="official-login-", dir=self.paths.app_home))
        os.chmod(login_home, 0o700)
        environment = self._codex_environment(login_home)
        process = subprocess.Popen(
            [binary, "app-server", "--stdio", "-c", 'cli_auth_credentials_store="file"'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=environment,
        )
        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "process": process,
            "home": login_home,
            "status": "pending",
            "error": "",
            "created_at": time.monotonic(),
        }
        with self._official_login_lock:
            self._cleanup_official_login_sessions()
            self._official_login_sessions[session_id] = session
        try:
            self._write_app_server_message(
                process,
                {
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "clientInfo": {"name": "maolike-codex-manager", "version": "2.2.0"},
                        "capabilities": {},
                    },
                },
            )
            self._write_app_server_message(process, {"method": "initialized", "params": {}})
            self._write_app_server_message(
                process,
                {
                    "method": "account/login/start",
                    "id": 2,
                    "params": {"type": "chatgptDeviceCode"},
                },
            )
            response = self._read_app_server_response(process, 2, timeout=10)
            result = response.get("result", {})
            login_id = str(result.get("loginId", "")) if isinstance(result, dict) else ""
            verification_url = (
                str(result.get("verificationUrl", "")) if isinstance(result, dict) else ""
            )
            user_code = str(result.get("userCode", "")) if isinstance(result, dict) else ""
            if not login_id or not verification_url or not user_code:
                raise RuntimeError("Codex 未返回官方设备登录信息")
            session["login_id"] = login_id
            session["verification_url"] = verification_url
            session["user_code"] = user_code
            self._open_official_auth_url(verification_url)
            threading.Thread(
                target=self._wait_for_official_login,
                args=(session_id,),
                daemon=True,
            ).start()
            return {
                "login_id": session_id,
                "status": "pending",
                "verification_url": verification_url,
                "user_code": user_code,
            }
        except Exception:
            self._discard_official_login_session(session_id)
            raise

    def official_login_status(self, login_id: str) -> dict[str, Any]:
        with self._official_login_lock:
            session = self._official_login_sessions.get(login_id)
            if not session:
                raise KeyError("官方登录会话不存在或已过期")
            return {
                "login_id": login_id,
                "status": str(session.get("status", "pending")),
                "error": str(session.get("error", "")),
                "email": str(session.get("email", "")),
                "plan_type": str(session.get("plan_type", "")),
            }

    def complete_official_login(self, login_id: str, name: str = "") -> dict[str, Any]:
        with self._official_login_lock:
            session = self._official_login_sessions.get(login_id)
            if not session:
                raise KeyError("官方登录会话不存在或已过期")
            status = str(session.get("status", "pending"))
            if status == "pending":
                raise ValueError("官方登录尚未完成")
            if status != "completed":
                raise ValueError(str(session.get("error", "官方登录失败")))
            auth_payload = session.get("auth_payload")
            email = str(session.get("email", "")).strip()
            plan_type = str(session.get("plan_type", "unknown")).strip() or "unknown"
        if not isinstance(auth_payload, dict) or not auth_payload:
            raise RuntimeError("官方登录凭据未生成")

        store = self._load_store()
        accounts = store["accounts"]
        requested_name = name.strip() or email or "OpenAI 官方账号"
        account_name = self._unique_account_name(requested_name, accounts)
        default_model = self._official_default_model()
        accounts[account_name] = {
            "account_type": "official",
            "connection_type": "official",
            "provider_id": OFFICIAL_PROVIDER_ID,
            "provider_config": {},
            "official_auth": auth_payload,
            "official_email": email,
            "official_plan_type": plan_type,
            "default_model": default_model,
            "reasoning_effort": "high",
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._save_store(store)
        public = self._public_account(account_name, accounts[account_name], False)
        self._discard_official_login_session(login_id)
        return public

    def cancel_official_login(self, login_id: str) -> None:
        with self._official_login_lock:
            session = self._official_login_sessions.get(login_id)
            if not session:
                return
            process = session.get("process")
            managed_login_id = str(session.get("login_id", ""))
        if managed_login_id and isinstance(process, subprocess.Popen) and process.poll() is None:
            try:
                self._write_app_server_message(
                    process,
                    {
                        "method": "account/login/cancel",
                        "id": 4,
                        "params": {"loginId": managed_login_id},
                    },
                )
            except (OSError, RuntimeError):
                pass
        self._discard_official_login_session(login_id)

    def _activate_official_account(
        self,
        store: dict[str, Any],
        name: str,
        account: dict[str, Any],
    ) -> dict[str, Any]:
        auth_payload = account.get("official_auth")
        if not isinstance(auth_payload, dict) or not auth_payload:
            raise ValueError("官方账号缺少登录凭据，请重新登录")
        self._validate_official_auth(auth_payload)
        models = self._official_catalog_models()
        model_ids = [str(item.get("slug", "")) for item in models if item.get("slug")]
        if not model_ids:
            raise RuntimeError("Codex 没有返回官方模型目录")
        selected_model = str(account.get("default_model", "")).strip()
        if selected_model not in model_ids:
            selected_model = model_ids[0]
            account["default_model"] = selected_model

        config_text = self._read_text(self.paths.config)
        config_text = self._rewrite_top_level(
            config_text,
            {
                "model": selected_model,
                "model_provider": OFFICIAL_PROVIDER_ID,
                "model_reasoning_effort": str(account.get("reasoning_effort", "high")),
                "cli_auth_credentials_store": "file",
            },
        )
        config_text = self._remove_top_level(config_text, {"model_catalog_json"})
        auth_text = json.dumps(auth_payload, ensure_ascii=False, indent=2) + "\n"
        store["active_account"] = name
        store.pop("unmanaged_current_account", None)
        account["updated_at"] = _now()
        self._backup_many(self.paths.config, self.paths.auth)
        self._commit_account_switch(
            store,
            [
                (self.paths.config, config_text),
                (self.paths.auth, auth_text),
                (
                    self.paths.sync_state,
                    self._sync_state_text(
                        "ok", name, len(model_ids), "official://openai", ""
                    ),
                ),
            ],
        )
        return {"account": name, "model": selected_model, "models": len(model_ids)}

    def _sync_official_account(
        self,
        store: dict[str, Any],
        name: str,
        account: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            models = self._official_catalog_models()
            model_ids = [str(item.get("slug", "")) for item in models if item.get("slug")]
            if not model_ids:
                raise RuntimeError("Codex 没有返回官方模型目录")
            current = self._read_toml(self.paths.config)
            selected_model = str(current.get("model", ""))
            if selected_model not in model_ids:
                selected_model = str(account.get("default_model", ""))
            if selected_model not in model_ids:
                selected_model = model_ids[0]
            config_text = self._rewrite_top_level(
                self._read_text(self.paths.config),
                {
                    "model": selected_model,
                    "model_provider": OFFICIAL_PROVIDER_ID,
                },
            )
            config_text = self._remove_top_level(config_text, {"model_catalog_json"})
            self._backup_many(self.paths.config)
            self._atomic_write(self.paths.config, config_text)
            account["default_model"] = selected_model
            account["updated_at"] = _now()
            self._save_store(store)
            self._record_sync("ok", name, len(model_ids), "official://openai", "")
            return {
                "account": name,
                "model": selected_model,
                "models": len(model_ids),
                "endpoint": "official://openai",
            }
        except Exception as exc:
            self._record_sync("error", name, 0, "official://openai", str(exc))
            raise

    def _capture_active_official_auth(self, store: dict[str, Any]) -> bool:
        active = store.get("accounts", {}).get(str(store.get("active_account", "")))
        if not isinstance(active, dict) or self._account_type(active) != "official":
            return False
        payload = self._read_json(self.paths.auth, {})
        if not isinstance(payload, dict) or "tokens" not in payload:
            return False
        active["official_auth"] = payload
        active["updated_at"] = _now()
        return True

    def _validate_official_auth(self, auth_payload: dict[str, Any]) -> None:
        login_home = Path(tempfile.mkdtemp(prefix="official-check-", dir=self.paths.app_home))
        os.chmod(login_home, 0o700)
        auth_path = login_home / "auth.json"
        self._atomic_write(
            auth_path,
            json.dumps(auth_payload, ensure_ascii=False, indent=2) + "\n",
        )
        environment = self._codex_environment(login_home)
        try:
            result = subprocess.run(
                [
                    self._codex_binary(),
                    "login",
                    "status",
                    "-c",
                    'cli_auth_credentials_store="file"',
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                env=environment,
            )
            if result.returncode != 0:
                raise ValueError("官方账号登录已失效，请重新登录")
        finally:
            shutil.rmtree(login_home, ignore_errors=True)

    @staticmethod
    def _unique_account_name(requested: str, accounts: dict[str, Any]) -> str:
        base = requested.strip() or "OpenAI 官方账号"
        name = base
        suffix = 2
        while name in accounts:
            name = f"{base} {suffix}"
            suffix += 1
        return name

    @staticmethod
    def _codex_binary() -> str:
        bundled = CODEX_APP / "Contents/Resources/codex"
        if bundled.is_file():
            return str(bundled)
        binary = shutil.which("codex")
        if binary:
            return binary
        raise RuntimeError("未找到 Codex CLI，无法启动官方登录")

    @staticmethod
    def _codex_environment(codex_home: Path | None = None) -> dict[str, str]:
        environment = dict(os.environ)
        environment.pop("OPENSSL_MODULES", None)
        if codex_home is not None:
            environment["CODEX_HOME"] = str(codex_home)
        return environment

    @staticmethod
    def _open_official_auth_url(auth_url: str) -> None:
        parsed = urlparse(auth_url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "auth.openai.com",
            "chatgpt.com",
            "auth0.openai.com",
        }:
            raise RuntimeError("Codex 返回了无效的官方登录地址")
        if os.uname().sysname != "Darwin":
            raise RuntimeError("官方浏览器登录目前只支持 macOS")
        try:
            subprocess.run(
                ["/usr/bin/open", auth_url],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("无法打开 OpenAI 官方登录页") from None

    @staticmethod
    def _write_app_server_message(process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise RuntimeError("Codex 登录进程不可用")
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.flush()

    @staticmethod
    def _read_app_server_response(
        process: subprocess.Popen[str],
        request_id: int,
        timeout: float,
    ) -> dict[str, Any]:
        if process.stdout is None:
            raise RuntimeError("Codex 登录进程不可用")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], min(0.5, deadline - time.monotonic()))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                if message.get("error"):
                    raise RuntimeError("Codex 官方登录服务拒绝了请求")
                return message
        raise RuntimeError("Codex 官方登录服务响应超时")

    def _wait_for_official_login(self, session_id: str) -> None:
        with self._official_login_lock:
            session = self._official_login_sessions.get(session_id)
        if not session:
            return
        process = session["process"]
        deadline = time.monotonic() + OFFICIAL_LOGIN_TIMEOUT_SECONDS
        completed = False
        error = ""
        if process.stdout is None:
            error = "Codex 登录进程不可用"
        while not error and time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 1.0)
            if not ready:
                if process.poll() is not None:
                    error = "Codex 官方登录进程已退出"
                continue
            line = process.stdout.readline()
            if not line:
                error = "Codex 官方登录进程已退出"
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("method") != "account/login/completed":
                continue
            params = message.get("params", {})
            if (
                isinstance(params, dict)
                and str(params.get("loginId", "")) == str(session.get("login_id", ""))
                and params.get("success")
            ):
                completed = True
            else:
                detail = params.get("error") if isinstance(params, dict) else ""
                error = str(detail).strip() or "Codex 官方登录失败，请重新发起"
            break
        if not completed and not error:
            error = "官方登录已超时，请重新发起"
        if not completed:
            with self._official_login_lock:
                current = self._official_login_sessions.get(session_id)
                if current:
                    current["status"] = "failed"
                    current["error"] = error
            self._terminate_process(process)
            return
        try:
            self._write_app_server_message(
                process,
                {"method": "account/read", "id": 3, "params": {"refreshToken": False}},
            )
            response = self._read_app_server_response(process, 3, timeout=10)
            result = response.get("result", {})
            account = result.get("account", {}) if isinstance(result, dict) else {}
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                raise RuntimeError("Codex 未返回有效的官方账号")
            auth_payload = self._read_json(Path(session["home"]) / "auth.json", {})
            if not isinstance(auth_payload, dict) or not auth_payload:
                raise RuntimeError("Codex 未生成官方登录凭据")
            with self._official_login_lock:
                current = self._official_login_sessions.get(session_id)
                if current:
                    current.update(
                        {
                            "status": "completed",
                            "email": str(account.get("email", "")),
                            "plan_type": str(account.get("planType", "unknown")),
                            "auth_payload": auth_payload,
                        }
                    )
        except Exception:
            with self._official_login_lock:
                current = self._official_login_sessions.get(session_id)
                if current:
                    current["status"] = "failed"
                    current["error"] = "无法读取官方账号信息，请重新发起登录"
        finally:
            self._terminate_process(process)

    def _cleanup_official_login_sessions(self) -> None:
        expired = [
            session_id
            for session_id, session in self._official_login_sessions.items()
            if time.monotonic() - float(session.get("created_at", 0))
            > OFFICIAL_LOGIN_TIMEOUT_SECONDS + 60
        ]
        for session_id in expired:
            self._discard_official_login_session(session_id, already_locked=True)

    def _discard_official_login_session(self, session_id: str, already_locked: bool = False) -> None:
        if already_locked:
            session = self._official_login_sessions.pop(session_id, None)
        else:
            with self._official_login_lock:
                session = self._official_login_sessions.pop(session_id, None)
        if not session:
            return
        self._terminate_process(session.get("process"))
        home = session.get("home")
        if isinstance(home, Path):
            shutil.rmtree(home, ignore_errors=True)

    @staticmethod
    def _terminate_process(process: Any) -> None:
        if not isinstance(process, subprocess.Popen) or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
