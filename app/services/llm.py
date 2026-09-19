"""LLM 客户端：OpenAI 兼容接口（LM Studio / vLLM / 云端 API）。"""

from functools import lru_cache
from typing import Annotated, Protocol

import httpx
from fastapi import Depends

from app.core.config import settings


class LLMUnavailable(Exception):
    """模型服务不可用：连接失败、超时、模型不存在等。"""


class LLMClient(Protocol):
    """LLM 客户端接口。"""

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str: ...


class LmStudioClient:
    """OpenAI 兼容客户端：支持 LM Studio、vLLM 和云端 API。"""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
            },
            timeout=settings.llm_timeout,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
        payload = {
            "model": model or settings.llm_model,
            "messages": messages,
            "temperature": settings.llm_temperature,
        }

        if response_format is not None:
            payload["response_format"] = response_format

        try:
            response = await self._client.post(
                "/chat/completions",
                json=payload,
            )
            response.raise_for_status()

        except httpx.HTTPStatusError as exc:
            raise LLMUnavailable(
                f"模型服务返回 HTTP {exc.response.status_code}："
                f"请检查 LLM_MODEL={payload['model']} 是否正确",
            ) from exc

        except httpx.HTTPError as exc:
            raise LLMUnavailable(
                f"无法连接模型服务 {settings.llm_base_url}：{exc}",
            ) from exc

        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable(
                "模型返回格式不符合 OpenAI Chat Completions 格式",
            ) from exc

    async def aclose(self) -> None:
        """关闭 HTTP 连接池。"""
        await self._client.aclose()


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """FastAPI 依赖：进程内单例。"""
    return LmStudioClient()


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
