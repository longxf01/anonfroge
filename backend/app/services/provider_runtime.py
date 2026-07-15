from __future__ import annotations

import importlib
import inspect
import sys
from typing import Any

import httpx

from app.core.base_provider import BaseProvider
from app.schemas.provider import ProviderConfig
from app.services import provider as provider_service
from app.utils.secret_tools import decrypt_secret


class ProviderRuntimeError(provider_service.ProviderServiceError):
    """运行时加载或调度 provider 失败。"""


class OpenAICompatibleTextProvider(BaseProvider):
    """OpenAI 兼容协议的通用文本生成 Provider。"""

    provider_key = "openai_compatible"
    model_type = "text"

    def __init__(
        self,
        config: ProviderConfig,
        *,
        input_values: dict[str, str] | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.provider_key = config.key
        self.provider_config = config.model_dump(mode="json")
        self.input_values = {**config.input_values, **(input_values or {})}
        self.base_url = config.base_url
        self.timeout = timeout
        self.client = client

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        """调用 OpenAI 兼容的 chat completions 接口生成文本。"""
        resolved_model_id = (model_id or "").strip()
        if not resolved_model_id:
            raise ProviderRuntimeError("model_id 不能为空")
        messages = kwargs.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ProviderRuntimeError("messages 不能为空")

        payload: dict[str, Any] = {
            "model": resolved_model_id,
            "messages": messages,
        }
        for key in ("temperature", "top_p", "max_tokens", "response_format"):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        headers = {
            "Authorization": f"Bearer {_resolve_openai_api_key(self.config, self.input_values)}",
            "Content-Type": "application/json",
        }
        url = _build_chat_completions_url(self.base_url)
        try:
            if self.client is not None:
                response = await self.client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=_build_httpx_timeout(self.timeout)) as client:
                    response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderRuntimeError(f"文本生成请求失败: {_format_http_error(exc, url)}") from exc

        if response.status_code >= 400:
            raise ProviderRuntimeError(f"文本生成请求失败，HTTP {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderRuntimeError("文本生成响应不是合法 JSON") from exc


def create_provider(
    provider_key: str,
    model_type: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    input_values: dict[str, str] | None = None,
    timeout: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> BaseProvider:
    """按厂商 key 与模型类型创建运行时工具类实例。"""
    provider_class = get_provider_class(provider_key, model_type)
    return provider_class(
        api_key=api_key,
        base_url=base_url,
        input_values=input_values,
        timeout=timeout,
        client=client,
    )


def create_provider_for_model(
    model_id: str,
    *,
    provider_key: str | None = None,
    input_values: dict[str, str] | None = None,
    timeout: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> BaseProvider:
    """根据 model_id 查找配置中的模型能力，并创建对应 provider。"""
    model_id = model_id.strip()
    if not model_id:
        raise ProviderRuntimeError("model_id 不能为空")

    configs = (
        [provider_service.get_provider_config(provider_key)]
        if provider_key
        else provider_service.list_provider_configs()
    )
    for config in configs:
        if not config.enabled:
            continue
        for model in config.models:
            if model.model_id == model_id:
                if _should_use_openai_compatible_text_provider(config, model.model_type):
                    return OpenAICompatibleTextProvider(
                        config,
                        input_values=input_values,
                        timeout=timeout,
                        client=client,
                    )
                return create_provider(
                    config.key,
                    model.model_type,
                    input_values=input_values,
                    timeout=timeout,
                    client=client,
                )
    raise ProviderRuntimeError("未找到可用的模型配置")


def _should_use_openai_compatible_text_provider(config: ProviderConfig, model_type: str) -> bool:
    """判断文本模型是否可使用内置 OpenAI 兼容调用器。"""
    if model_type != "text":
        return False
    protocol = config.protocol.strip().lower()
    if protocol in {"openai", "openai-compatible", "openai_compatible", "qwen", "volcengine"}:
        return True
    return bool(config.base_url.strip().rstrip("/").endswith("/v1"))


def _build_chat_completions_url(base_url: str) -> str:
    """拼接 OpenAI 兼容的 chat completions 地址。"""
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ProviderRuntimeError("缺少请求地址")
    if not normalized.startswith(("http://", "https://")):
        raise ProviderRuntimeError("请求地址必须以 http:// 或 https:// 开头")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _format_http_error(exc: httpx.HTTPError, url: str) -> str:
    """格式化 httpx 异常，避免空字符串错误被直接展示给用户。"""
    message = str(exc).strip()
    error_type = type(exc).__name__
    if message:
        return f"{error_type}: {message}（{url}）"
    return f"{error_type}（{url}）"


def _build_httpx_timeout(timeout: float) -> httpx.Timeout:
    """构造模型请求超时，连接阶段保持较短，读取阶段按模型生成时间放宽。"""
    return httpx.Timeout(timeout, connect=min(15.0, timeout))


def _resolve_openai_api_key(config: ProviderConfig, values: dict[str, str]) -> str:
    """从服务配置输入值中读取并解密 API Key。"""
    candidates = [
        values.get("apiKey"),
        values.get("api_key"),
        values.get("OPENAI_API_KEY"),
        values.get("API_KEY"),
        values.get("token"),
    ]
    candidates.extend(values.get(item.key) for item in config.inputs if item.type == "password")
    candidates.extend(
        value
        for key, value in values.items()
        if key.lower().endswith(("api_key", "apikey", "token"))
    )

    for value in candidates:
        raw_value = str(value or "").strip()
        if not raw_value:
            continue
        try:
            api_key = decrypt_secret(raw_value).strip()
        except ValueError as exc:
            raise ProviderRuntimeError("API Key 解密失败") from exc
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:].strip()
        if api_key:
            return api_key
    raise ProviderRuntimeError("缺少 API Key")


async def generate(
    provider_key: str,
    model_type: str,
    *,
    model_id: str | None = None,
    input_values: dict[str, str] | None = None,
    timeout: float = 60.0,
    client: httpx.AsyncClient | None = None,
    **kwargs: Any,
) -> Any:
    """统一调度 provider 工具类执行生成任务。"""
    provider = create_provider(
        provider_key,
        model_type,
        input_values=input_values,
        timeout=timeout,
        client=client,
    )
    return await provider.generate(model_id=model_id, **kwargs)


def get_provider_class(provider_key: str, model_type: str) -> type[BaseProvider]:
    config = provider_service.get_provider_config(provider_key)
    if not config.enabled:
        raise ProviderRuntimeError("服务未启用")

    module = load_provider_module(provider_key)
    matches: list[type[BaseProvider]] = []
    for value in vars(module).values():
        if not inspect.isclass(value) or value is BaseProvider:
            continue
        if not issubclass(value, BaseProvider):
            continue
        class_key = getattr(value, "provider_key", "")
        class_model_type = getattr(value, "model_type", "")
        if class_key == provider_key and class_model_type == model_type:
            matches.append(value)

    if not matches:
        raise ProviderRuntimeError("未找到匹配的 provider 工具类")
    if len(matches) > 1:
        raise ProviderRuntimeError("找到多个匹配的 provider 工具类")
    return matches[0]


def load_provider_module(provider_key: str):
    provider_service.get_provider_config(provider_key)
    module_name = f"app.providers.{provider_key}"
    try:
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)
    except Exception as exc:
        raise ProviderRuntimeError(f"加载 provider 模块失败: {exc}") from exc
