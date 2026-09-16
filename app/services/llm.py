"""LLM 客户端：OpenAI 兼容接口（LM Studio / vLLM / 云端 API）。"""

from functools import lru_cache
from typing import Annotated, Protocol

import httpx
from fastapi import Depends

from app.core.config import settings


class LLMUnavailable(Exception):
    """模型服务不可用：连不上、超时、模型名不存在等。"""


class LLMClient(Protocol):
    """LLM 接口：把一组 messages 交给模型，返回回答文本。"""

    async def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str: ...


class LmStudioClient:  # OpenAI 兼容，LM Studio / vLLM / 云端都能用
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout,
        )

    async def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        payload = {
            "model": model or settings.llm_model,
            "messages": messages,
            "temperature": settings.llm_temperature,
        }
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailable(
                f"模型服务返回 {exc.response.status_code}："
                f"请检查 LLM_MODEL={payload['model']} 是否与 {settings.llm_base_url}/models 一致",
            ) from exc
        except httpx.HTTPError as exc:  # 连接被拒 / 超时
            raise LLMUnavailable(f"无法连接模型服务 {settings.llm_base_url}（{exc}）") from exc
        return response.json()["choices"][0]["message"]["content"]

    async def aclose(self) -> None:
        """释放连接池。"""
        await self._client.aclose()


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """FastAPI 依赖：进程内单例（首次请求时才建连接池）。"""
    return LmStudioClient()


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
