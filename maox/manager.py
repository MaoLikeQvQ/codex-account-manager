from __future__ import annotations

from datetime import timedelta

from maox.shared.common import *
from maox.shared.common import _now
from maox.accounts.service import AccountsMixin
from maox.accounts.official import OfficialMixin
from maox.imagegen.service import ImageMixin
from maox.accounts.models import ModelsMixin
from maox.history.service import HistoryMixin
from maox.shared.storage import StorageMixin
from maox.codex.restart import RestartMixin
from maox.usage.summary import summarize_range
from maox.usage.pricing import get_api_prices
from maox.requests.usage import RequestUsageReader
from maox.requests.timing import TimingStore


class CodexManager(AccountsMixin, OfficialMixin, ImageMixin, ModelsMixin, HistoryMixin, StorageMixin, RestartMixin):
    def _usage_context_for_period(self, period: str, selected_date: str):
        store = self._load_store()
        account = store.get("accounts", {}).get(store.get("active_account", ""))
        if not isinstance(account, dict):
            raise ValueError("没有已启用的账号")
        account = account.get("applied_account", account)
        official = self._account_type(account) == "official"
        provider_id = OFFICIAL_PROVIDER_ID if official else str(account.get("provider_id", ""))
        now = datetime.now().astimezone()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "today":
            start = today
        elif period == "yesterday":
            start = today - timedelta(days=1)
        elif period == "7d":
            start = today - timedelta(days=6)
        elif period == "month":
            start = today.replace(day=1, tzinfo=None).astimezone()
        elif period == "all":
            # A fixed lower bound covers all Codex history without scanning it
            # once just to discover its earliest date before the real query.
            start = datetime(1970, 1, 1).astimezone()
        elif period == "date":
            try:
                start = datetime.strptime(selected_date, "%Y-%m-%d").replace(tzinfo=now.tzinfo)
            except ValueError as exc:
                raise ValueError("日期必须是 YYYY-MM-DD") from exc
            if start > today:
                raise ValueError("不能查询未来日期")
        else:
            raise ValueError("不支持的用量时间范围")
        end = today + timedelta(days=1) if period in {"7d", "month", "all"} else start + timedelta(days=1)
        return provider_id, start, end

    def usage_for_period(self, period: str = "today", selected_date: str = "") -> dict[str, Any]:
        provider_id, start, end = self._usage_context_for_period(period, selected_date)
        prices, pricing = get_api_prices(self.paths.app_home)
        result = summarize_range(self.paths.codex_home, provider_id, False, start, end, api_prices=prices)
        result['pricing'] = pricing
        result['price_source'] = pricing.get('source', result['price_source'])
        return result

    def sync_model_prices(self) -> dict[str, Any]:
        prices, pricing = get_api_prices(self.paths.app_home, force_refresh=True)
        if pricing['status'] == 'fresh' and not pricing.get('warning'):
            self._request_usage_reader.update_prices(prices)
        return {**pricing, 'model_count': len(prices)}

    def requests_for_period(self, period: str = "today", selected_date: str = "", limit: int = 100) -> dict[str, Any]:
        provider_id, start, end = self._usage_context_for_period(period, selected_date)
        result = self._request_usage_reader.summarize(
            self.paths.codex_home, provider_id, start, end, limit,
            timing_enricher=self._timing_store.enrich,
            price_loader=lambda: get_api_prices(self.paths.app_home)[0],
        )

        status = getattr(self, '_timing_status', 'not_started')
        result['network'] = self._timing_store.network_for_period(start, end, limit)
        result['timing_status'] = ('collecting' if result['timing_coverage']['timed'] and status != 'external_exporter' else status)
        return result

    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or Paths.from_environment()
        self._request_usage_reader = RequestUsageReader()
        self._timing_store = TimingStore(self.paths.app_home / "request-timing.sqlite")
        self._rollout_cache: dict[Path, tuple[tuple[int, int, int, bool], RolloutRecord]] = {}
        self._rollout_error_cache: dict[
            Path,
            tuple[tuple[int, int, int, bool], dict[str, Any]],
        ] = {}
        self._official_login_lock = threading.Lock()
        self._official_login_sessions: dict[str, dict[str, Any]] = {}
        self._bundled_catalog_cache: list[dict[str, Any]] | None = None
        self._bundled_catalog_cache_key: tuple[str, int, int] | None = None
        self._ensure_directories()

    def state(self, *, include_conversations: bool = True) -> dict[str, Any]:
        store = self._load_store()
        running = self.codex_running()
        self._refresh_restart_requirement(store, running)
        config = self._read_toml(self.paths.config)
        active_name = str(store.get("active_account", ""))
        accounts = store.get("accounts", {})
        pending_history = store.get("pending_history_claim")
        result = {
            "codex_home": str(self.paths.codex_home),
            "active_account": active_name,
            "accounts": [
                self._public_account(name, account, name == active_name)
                for name, account in accounts.items()
                if isinstance(account, dict)
            ],
            "current": self._current_config(config),
            "codex": {
                "running": running,
                "restart_required": bool(store.get("restart_required")),
                "application": self._codex_application(),
            },
            "image_generation": self._image_generation_state(config),
            "history_claim": {
                "account": str(pending_history.get("account", "")),
                "status": str(pending_history.get("status", "pending")),
                "failed": int(pending_history.get("failed", 0)),
            } if isinstance(pending_history, dict) else None,
        }
        if include_conversations:
            result["conversations"] = self._conversation_state()
        return result

    def launch_codex(self, restart: bool = True) -> str:
        if os.uname().sysname != "Darwin":
            raise RuntimeError("启动 Codex 目前只支持 macOS")
        running = self.codex_running()
        if running and not restart:
            raise RuntimeError("Codex 正在运行")
        self._clear_managed_catalog()
        if running:
            self._stop_codex()
        self._apply_pending_history_claim()
        subprocess.run(
            ["/usr/bin/open", "-b", "com.openai.codex"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        store = self._load_store()
        store["restart_required"] = False
        self._save_store(store)
        return "restarted" if running and restart else "opened"

    def _stop_codex(self) -> None:
        subprocess.run(
            ["/usr/bin/osascript", "-e", 'tell application id "com.openai.codex" to quit'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        for _ in range(40):
            if not self.codex_running():
                return
            time.sleep(0.25)
        raise RuntimeError("Codex 未能完全退出，尚未修改应用，请关闭后重试")

    @staticmethod
    def codex_running() -> bool:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", 'application id "com.openai.codex" is running'],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "true"

    def _bundled_catalog(self) -> list[dict[str, Any]]:
        for binary in self._codex_binary_candidates():
            if not binary.is_file():
                continue
            stat = binary.stat()
            cache_key = (str(binary), stat.st_size, stat.st_mtime_ns)
            if self._bundled_catalog_cache_key == cache_key and self._bundled_catalog_cache is not None:
                return copy.deepcopy(self._bundled_catalog_cache)
            try:
                result = subprocess.run(
                    [str(binary), "debug", "models", "--bundled"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env=self._codex_environment(),
                )
                payload = json.loads(result.stdout)
                models = payload.get("models", [])
                if isinstance(models, list) and models:
                    self._bundled_catalog_cache = [
                        item for item in models if isinstance(item, dict)
                    ]
                    self._bundled_catalog_cache_key = cache_key
                    return copy.deepcopy(self._bundled_catalog_cache)
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                continue
        return []

    def _official_catalog_models(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in self._bundled_catalog()
            if str(item.get("visibility", "")) == "list" and item.get("slug")
        ]
