from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """对话接口（当前为占位回答，阶段 3 接入 RAG + 大模型）。"""
    reply = f"收到你的问题：{request.message}（当前为占位回答）"
    return ChatResponse(reply=reply, model="placeholder")
