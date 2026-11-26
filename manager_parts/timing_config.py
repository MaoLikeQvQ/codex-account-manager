"""Configure the local request timing exporter without changing model traffic."""

from datetime import date, datetime, time
import json
import tomllib
from urllib.parse import urlsplit


_COLLECTOR_PATH = "/api/timing/otlp"


def _local_collector(endpoint: object) -> bool:
    if not isinstance(endpoint, str):
        return False
    try:
        url = urlsplit(endpoint)
        return (url.scheme == "http" and url.hostname == "127.0.0.1"
                and url.port is not None and 0 < url.port <= 65535
                and not url.username and not url.password
                and url.path == _COLLECTOR_PATH and not url.query and not url.fragment)
    except ValueError:
        return False


def _value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(key)} = {_value(item)}" for key, item in value.items()) + " }"
    return json.dumps(value, ensure_ascii=False)


def _without_otel(text: str) -> str:
    # Decode complete statements so header-looking text inside multiline
    # strings/arrays cannot remove unrelated configuration.
    kept: list[str] = []
    pending = ""
    in_otel = False
    in_table = False
    for line in text.splitlines(keepends=True):
        pending += line
        try:
            statement = tomllib.loads(pending)
        except tomllib.TOMLDecodeError:
            continue
        significant = pending.lstrip()
        if significant.startswith("["):
            in_otel = "otel" in statement
            in_table = True
        if not in_otel and not (not in_table and "otel" in statement):
            kept.append(pending)
        pending = ""
    if pending:
        raise ValueError("无法安全修改计时配置")
    return "".join(kept)


def configure_timing(config_text: str, endpoint: str) -> tuple[str, str]:
    """Return updated TOML and ``configured`` or ``external_exporter``.

    External exporters are preserved byte for byte. Only this manager's exact
    loopback collector path is considered managed; traces and metrics retain
    their independent exporters. No file is read or written here.
    """
    if not _local_collector(endpoint):
        raise ValueError("计时接收地址必须是本管理器的本机 HTTP 地址")
    config = tomllib.loads(config_text)
    otel = config.get("otel", {})
    if not isinstance(otel, dict):
        raise ValueError("otel 必须是 TOML 配置表")
    exporter = otel.get("exporter", "none")
    if exporter != "none":
        http = exporter.get("otlp-http") if isinstance(exporter, dict) else None
        if not (isinstance(http, dict) and set(exporter) == {"otlp-http"}
                and _local_collector(http.get("endpoint"))):
            return config_text, "external_exporter"
    updates = {**otel, "exporter": {"otlp-http": {"endpoint": endpoint, "protocol": "json"}},
               "log_user_prompt": False}
    if updates == otel:
        return config_text, "configured"
    remaining = _without_otel(config_text)
    if remaining and not remaining.endswith("\n"):
        remaining += "\n"
    if remaining and not remaining.endswith("\n\n"):
        remaining += "\n"
    result = remaining + "[otel]\n" + "".join(f"{json.dumps(key)} = {_value(value)}\n" for key, value in updates.items())
    expected = {**config, "otel": updates}
    if tomllib.loads(result) != expected:
        raise ValueError("计时配置修改影响了其他配置，已取消")
    return result, "configured"
