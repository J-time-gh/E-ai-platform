"""RAG 对话接口：检索 → 拼提示词 → 大模型带引用回答。"""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies.auth import CurrentUserDep
from app.core.config import settings
from app.db.session import DbSession
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import rag, retrieval
from app.services.embedding import EmbedderDep
from app.services.llm import LLMClientDep, LLMUnavailable
from app.services.reranker import RerankerDep

# 余弦相似度低于此值视为"没检索到相关资料"（仅用于 vector 模式）
# MIN_VECTOR_SCORE = 0.45

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    *,
    db: DbSession,
    embedder: EmbedderDep,
    llm: LLMClientDep,
    reranker: RerankerDep,
    current_user: CurrentUserDep,
) -> ChatResponse:
    """知识库问答：检索 Top-K → 组装提示词 → 模型带引用回答。"""
    results = retrieval.search_with_mode(
        db,
        embedder,
        request.message,
        request.top_k,
        request.mode,
        user_id=current_user.id,
        min_score=settings.min_vector_score,  # 向量腿门控（对 hybrid 也生效）
        reranker=reranker,
        min_rerank_score=settings.min_rerank_score,  # 精排门控（所有模式统一）
    )

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
