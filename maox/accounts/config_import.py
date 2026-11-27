"""Validate account connection fields in pasted TOML; never apply global settings."""
import re
import tomllib
from urllib.parse import urlsplit


PROVIDER_FIELDS = {
    "base_url", "wire_api", "requires_openai_auth", "model_catalog_url", "env_key",
    "env_key_instructions", "http_headers", "env_http_headers", "query_params",
    "request_max_retries", "stream_max_retries", "stream_idle_timeout_ms",
}


def connection_url(value, field):
    try:
        parsed = urlsplit(value) if isinstance(value, str) else None
        valid = (parsed and parsed.scheme in {"http", "https"} and parsed.hostname
                 and not parsed.username and not parsed.password and not parsed.query
                 and not parsed.fragment)
        if parsed:
            parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{field} 必须是有效的 HTTP 或 HTTPS 地址，不能包含账号密码、查询参数或片段")
    return value.strip().rstrip("/")


def validate_provider_config(provider):
    if not isinstance(provider, dict):
        raise ValueError("渠道连接配置格式不正确")
    result = {}
    for key, value in provider.items():
        if key not in PROVIDER_FIELDS:
            raise ValueError("渠道连接配置包含不支持的字段，请重新识别配置")
        if key in {"base_url", "model_catalog_url"}:
            value = connection_url(value, key)
        elif key == "wire_api":
            if value != "responses":
                raise ValueError("当前仅支持 wire_api = responses 的渠道")
        elif key == "requires_openai_auth":
            if not isinstance(value, bool):
                raise ValueError("requires_openai_auth 必须为 true 或 false")
        elif key in {"http_headers", "env_http_headers", "query_params"}:
            if not isinstance(value, dict) or not all(
                isinstance(k, str) and isinstance(v, str) and not any(c in k + v for c in "\r\n")
                for k, v in value.items()
            ):
                raise ValueError("渠道请求参数必须为字符串键值对，不能含换行")
        elif key in {"request_max_retries", "stream_max_retries", "stream_idle_timeout_ms"}:
            if type(value) is not int or value < 0:
                raise ValueError("渠道重试和超时参数必须为非负整数")
        elif not isinstance(value, str):
            raise ValueError("渠道环境变量配置必须为字符串")
        result[key] = value
    return result


def parse_provider_config(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("请粘贴 config.toml 内容")
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise ValueError("config.toml 格式不正确，请复制完整配置代码") from None
    provider_id = config.get("model_provider")
    if not isinstance(provider_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", provider_id):
        raise ValueError("缺少有效的 model_provider")
    providers = config.get("model_providers", {})
    provider = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(provider, dict):
        raise ValueError("找不到 model_provider 对应的渠道配置")
    supported = validate_provider_config({k: v for k, v in provider.items() if k in PROVIDER_FIELDS})
    url = connection_url(provider.get("base_url"), "base_url")
    supported.setdefault("wire_api", "responses")
    model = config.get("model", "")
    effort = config.get("model_reasoning_effort", "high")
    if not isinstance(model, str) or not isinstance(effort, str) or effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
        raise ValueError("模型名称或推理强度格式不正确")
    features = config.get("features", {})
    discovery = features.get("api_key_model_discovery", bool(supported.get("model_catalog_url"))) if isinstance(features, dict) else False
    if not isinstance(discovery, bool):
        raise ValueError("api_key_model_discovery 必须为 true 或 false")
    ignored = sorted(set(config) - {"model_provider", "model_providers", "model", "model_reasoning_effort", "features"})
    ignored += [f"model_providers.{provider_id}.{k}" for k in provider if k not in PROVIDER_FIELDS and k != "name"]
    if isinstance(features, dict):
        ignored += [f"features.{k}" for k in features if k != "api_key_model_discovery"]
    return {"provider_id": provider_id, "name": provider_id, "base_url": url,
            "default_model": model, "reasoning_effort": effort,
            "provider_config": supported, "api_key_model_discovery": discovery,
            "ignored_fields": sorted(ignored)}
