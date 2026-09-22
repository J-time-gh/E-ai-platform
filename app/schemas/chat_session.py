from datetime import datetime

from pydantic import BaseModel, Field


class CreateChatSessionRequest(BaseModel):
    """创建会话的请求。"""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )


class ChatSessionResponse(BaseModel):
    """会话列表或创建会话时的返回结构。"""

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class PersistedChatMessageResponse(BaseModel):
    """数据库中已持久化的一条聊天消息。"""

    id: str
    role: str
    content: str
    created_at: datetime
