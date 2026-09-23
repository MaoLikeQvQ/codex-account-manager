"""Parse pasted provider configuration without saving or contacting a provider."""
import re
import tomllib
from urllib.parse import urlsplit


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
    url = provider.get("base_url")
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        valid_url = parsed and parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ValueError("渠道 base_url 必须是有效的 HTTP 或 HTTPS 地址，不能包含账号密码")
    if provider.get("wire_api", "responses") != "responses":
        raise ValueError("当前仅支持 wire_api = responses 的渠道")
    model = config.get("model", "")
    effort = config.get("model_reasoning_effort", "high")
    if not isinstance(model, str) or not isinstance(effort, str) or effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
        raise ValueError("模型名称或推理强度格式不正确")
    ignored = sorted(set(config) - {"model_provider", "model_providers", "model", "model_reasoning_effort"})
    return {"provider_id": provider_id, "name": provider_id, "base_url": url,
            "default_model": model, "reasoning_effort": effort,
            "ignored_fields": ignored}
