from __future__ import annotations

from maox.shared.common import *
from urllib.parse import urlencode


class ModelsMixin:
    @staticmethod
    def _model_request_headers(account: dict[str, Any]) -> dict[str, str]:
        provider = account.get("provider_config", {})
        token = str(account.get("api_key", ""))
        if provider.get("env_key"):
            token = os.environ.get(provider["env_key"], "")
            if not token:
                raise ValueError("渠道要求的 API Key 环境变量未设置，请检查运行环境")
        if not token:
            raise ValueError("账号缺少 API Key")
        headers = dict(provider.get("http_headers", {}))
        for key, variable in provider.get("env_http_headers", {}).items():
            if os.environ.get(variable):
                headers[key] = os.environ[variable]
        headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        return headers

    def _test_model_response(self, account: dict[str, Any], model: str) -> dict[str, Any]:
        provider = account["provider_config"]
        endpoint = str(provider["base_url"]).rstrip("/") + "/responses"
        query = urlencode(provider.get("query_params", {}))
        headers = self._model_request_headers(account)
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            endpoint + ("?" + query if query else ""),
            data=json.dumps({"model": model, "input": "hi", "stream": False, "store": False}).encode(),
            headers=headers, method="POST",
        )
        started = time.monotonic()
        # A test can consume quota; make exactly one request and never retry it.
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise RuntimeError(f"连接验证失败：HTTP {exc.code}，请检查地址、Key 和模型权限") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError("连接验证失败：连接失败或请求超时，未自动重试") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError("连接验证失败：接口未返回有效的 Responses JSON") from None
        if not isinstance(payload, dict) or payload.get("error") or payload.get("status") != "completed":
            raise RuntimeError("连接验证失败：模型响应未正常完成")
        output = payload.get("output", [])
        texts = []
        for item in output if isinstance(output, list) else []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content", [])
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        reply = "".join(texts).strip()
        if not reply:
            raise RuntimeError("连接验证失败：模型没有返回文本消息")
        return {"model": model, "reply": reply[:1000], "elapsed_ms": round((time.monotonic() - started) * 1000)}

    def _discover_models(self, account: dict[str, Any]) -> dict[str, Any]:
        provider = account.get("provider_config", {})
        endpoints = self._model_endpoint_candidates(account)
        if not endpoints:
            raise ValueError("账号缺少 Base URL")
        headers = self._model_request_headers(account)
        failures: list[str] = []
        for endpoint in endpoints:
            query = urlencode(provider.get("query_params", {}))
            request = urllib.request.Request(
                endpoint + ("?" + query if query else ""),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(request, timeout=6) as response:
                    payload = json.load(response)
                values: list[Any] = []
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    values = payload["data"]
                elif isinstance(payload, dict) and isinstance(payload.get("models"), list):
                    values = payload["models"]
                elif isinstance(payload, list):
                    values = payload
                model_ids = []
                for item in values:
                    value = (item.get("id") or item.get("slug")) if isinstance(item, dict) else item
                    if isinstance(value, str) and value.strip():
                        model_ids.append(value.strip())
                model_ids = list(dict.fromkeys(model_ids))
                if model_ids:
                    return {"model_ids": model_ids, "endpoint": endpoint}
                failures.append(f"{endpoint} 未返回模型")
            except urllib.error.HTTPError as exc:
                failures.append(f"{endpoint} HTTP {exc.code}")
            except urllib.error.URLError:
                failures.append(f"{endpoint} 连接失败")
            except TimeoutError:
                failures.append(f"{endpoint} 请求超时")
            except json.JSONDecodeError:
                failures.append(f"{endpoint} 返回无效 JSON")

        detail = "；".join(failures)
        raise RuntimeError(f"未能读取渠道模型列表：{detail}。仍可保存账号；验证连接前需填写模型。模型列表检测不验证推理能力。")

    @staticmethod
    def _model_endpoint_candidates(account: dict[str, Any]) -> list[str]:
        provider = account.get("provider_config", {})
        if provider.get("model_catalog_url"):
            return [str(provider["model_catalog_url"])]
        base_url = str(provider.get("base_url", "")).rstrip("/")
        if not base_url:
            return []
        if base_url.endswith("/models"):
            return [base_url]
        v1_models = base_url + "/models" if base_url.endswith("/v1") else base_url + "/v1/models"
        return list(dict.fromkeys([base_url, base_url + "/models", v1_models]))
