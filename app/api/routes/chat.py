"""RAG 对话接口：检索 → 拼提示词 → 大模型带引用回答。"""

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.db.session import DbSession
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import rag, retrieval
from app.services.embedding import EmbedderDep
from app.services.llm import LLMClientDep, LLMUnavailable

MIN_VECTOR_SCORE = 0.45  # 余弦相似度低于此值视为"没检索到相关资料"（仅用于 vector 模式）

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: DbSession,
    embedder: EmbedderDep,
    llm: LLMClientDep,
) -> ChatResponse:
    """知识库问答：向量检索 Top-K → 组装提示词 → 模型带引用回答。"""
    results = retrieval.search_with_mode(db, embedder, request.message, request.top_k, request.mode)

    if request.mode == "vector":
        # 向量模式：过滤低分块。BM25 模式不用阈值——它已经在检索层用
        # "分词交集"过滤过一次了，不相关的块根本不会返回。
        results = [result for result in results if result.score >= settings.min_vector_score]

    if not results:
        # 知识库没有相关资料：不调模型，直接拒答（快 + 稳定 + 不烧 token）
        return ChatResponse(reply=rag.NO_CONTEXT_REPLY, model="none", sources=[])

    messages = rag.build_messages(request.message, results)
    if request.history:
        messages[1:1] = [message.model_dump() for message in request.history]

    try:
        reply = await llm.chat(messages, model=request.model)
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatResponse(
        reply=reply,
        model=request.model or settings.llm_model,
        sources=results,
    )
