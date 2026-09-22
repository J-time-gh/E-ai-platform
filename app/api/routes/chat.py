"""RAG 对话接口：检索 → 拼提示词 → 大模型带引用回答。"""

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies.auth import CurrentUserDep
from app.core.config import settings
from app.db.session import DbSession
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.services import chat_session_store, rag, retrieval
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
    history = request.history

    if request.session_id:
        persisted_messages = chat_session_store.list_messages(
            db,
            request.session_id,
            current_user.id,
        )

        if persisted_messages is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )

        history = [
            ChatMessage(
                role=message.role,
                content=message.content,
            )
            for message in persisted_messages
        ]

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
        response = ChatResponse(
            reply=rag.NO_CONTEXT_REPLY,
            model="none",
            sources=[],
        )

        if request.session_id:
            chat_session_store.add_turn(
                db,
                session_id=request.session_id,
                user_id=current_user.id,
                user_content=request.message,
                assistant_content=response.reply,
            )

        return response

    messages = rag.build_messages(request.message, results)
    if history:
        messages[1:1] = [message.model_dump() for message in history]

    try:
        reply = await llm.chat(messages, model=request.model)
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    response = ChatResponse(
        reply=reply,
        model=request.model or settings.llm_model,
        sources=results,
    )

    if request.session_id:
        chat_session_store.add_turn(
            db,
            session_id=request.session_id,
            user_id=current_user.id,
            user_content=request.message,
            assistant_content=response.reply,
        )

    return response
