"""Update a selected provider without replacing its connection settings."""
from __future__ import annotations

import copy
import json
import re
import tomllib
from typing import Any, Callable


def validate_file_credentials(config: dict[str, Any], provider: dict[str, Any]) -> None:
    if config.get("cli_auth_credentials_store", "file") != "file":
        raise ValueError("当前 Provider 未使用文件凭据；请先将 cli_auth_credentials_store 设为 file 后再切换账号")
    if provider.get("env_key") or provider.get("experimental_bearer_token"):
        raise ValueError("当前 Provider 使用独立凭据来源，无法只更新 auth.json 中的 API Key；请先改用文件凭据")
    for field in ("http_headers", "env_http_headers"):
        headers = provider.get(field, {})
        if isinstance(headers, dict) and any(str(key).lower() == "authorization" for key in headers):
            raise ValueError("当前 Provider 自带 Authorization 请求头，无法只更新 API Key；请先移除该认证覆盖")


def replace_provider(text: str, provider_id: str, provider: dict[str, Any],
                     render_value: Callable[[Any], str]) -> str:
    """Preserve other providers, including inline and quoted TOML representations."""
    lines = text.splitlines(keepends=True)
    kept = []
    section = {}
    index = 0
    inline_replaced = False
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("["):
            try:
                section = tomllib.loads(line)
            except tomllib.TOMLDecodeError:
                # Multiline arrays/strings are consumed together below, never as headers.
                section = {}
            if provider_id not in section.get("model_providers", {}):
                kept.append(line)
            index += 1
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            if provider_id not in section.get("model_providers", {}):
                kept.append(line)
            index += 1
            continue
        # A single assignment may contain a multiline value. Parse it as a unit
        # so embedded TOML-looking text cannot be mistaken for another table.
        chunk = line
        end = index + 1
        while True:
            try:
                assignment = tomllib.loads(chunk)
                break
            except tomllib.TOMLDecodeError:
                if end >= len(lines):
                    raise ValueError("无法安全更新当前 Provider 配置") from None
                chunk += lines[end]
                end += 1
        providers = assignment.get("model_providers") if not section else None
        parent = section.get("model_providers")
        if provider_id in section.get("model_providers", {}):
            pass
        elif isinstance(providers, dict):
            # Root inline model_providers is a sealed table: update it in place.
            if re.match(r'^\s*(?:model_providers|"model_providers"|\'model_providers\')\s*=', chunk):
                providers = copy.deepcopy(providers)
                providers[provider_id] = provider
                kept.append(f"model_providers = {render_value(providers)}\n")
                inline_replaced = True
            elif provider_id not in providers:
                kept.append(chunk)
        elif parent == {} and provider_id in assignment:
            # Remove inline/dotted entries under [model_providers]; the selected
            # provider is rendered once below so multiple dotted fields stay valid.
            pass
        else:
            kept.append(chunk)
        index = end
    if not inline_replaced:
        key = provider_id if re.fullmatch(r"[A-Za-z0-9_-]+", provider_id) else json.dumps(provider_id, ensure_ascii=False)
        block = [f"[model_providers.{key}]"]
        block.extend(f"{json.dumps(key, ensure_ascii=False)} = {render_value(value)}" for key, value in provider.items())
        kept.append("\n" + "\n".join(block) + "\n")
    result = "".join(kept)
    # Verify the resulting tree before any config, credentials or store writes.
    parsed = tomllib.loads(result)
    expected = tomllib.loads(text) if text.strip() else {}
    expected.setdefault("model_providers", {})[provider_id] = provider
    if parsed != expected:
        raise ValueError("无法安全更新当前 Provider 配置")
    return result
