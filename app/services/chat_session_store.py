from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.chat import ChatMessage, ChatSession
from app.schemas.chat_session import (
    ChatSessionResponse,
    PersistedChatMessageResponse,
)


def _to_session_response(
    row: ChatSession,
) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=row.id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_message_response(
    row: ChatMessage,
) -> PersistedChatMessageResponse:
    return PersistedChatMessageResponse(
        id=row.id,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
    )


def _get_session_row(
    db: Session,
    session_id: str,
    user_id: str,
) -> ChatSession | None:
    """只查询当前用户拥有的会话。"""
    return db.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ),
    )


def create(
    db: Session,
    *,
    user_id: str,
    title: str | None,
) -> ChatSessionResponse:
    now = datetime.now(UTC)

    row = ChatSession(
        id=str(uuid4()),
        user_id=user_id,
        title=title,
        created_at=now,
        updated_at=now,
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return _to_session_response(row)


def list_all(
    db: Session,
    user_id: str,
) -> list[ChatSessionResponse]:
    rows = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc()),
    ).all()

    return [_to_session_response(row) for row in rows]


def get(
    db: Session,
    session_id: str,
    user_id: str,
) -> ChatSessionResponse | None:
    row = _get_session_row(
        db,
        session_id,
        user_id,
    )

    return _to_session_response(row) if row else None


def list_messages(
    db: Session,
    session_id: str,
    user_id: str,
) -> list[PersistedChatMessageResponse] | None:
    """返回 None 表示会话不属于当前用户或不存在。"""
    session = _get_session_row(
        db,
        session_id,
        user_id,
    )
    if session is None:
        return None

    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at),
    ).all()

    return [_to_message_response(row) for row in rows]


def add_turn(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    user_content: str,
    assistant_content: str,
) -> bool:
    """一次写入用户消息和助手消息，确保它们属于同一会话。"""
    session = _get_session_row(
        db,
        session_id,
        user_id,
    )
    if session is None:
        return False

    now = datetime.now(UTC)

    db.add_all(
        [
            ChatMessage(
                id=str(uuid4()),
                session_id=session.id,
                role="user",
                content=user_content,
                created_at=now,
            ),
            ChatMessage(
                id=str(uuid4()),
                session_id=session.id,
                role="assistant",
                content=assistant_content,
                created_at=now,
            ),
        ],
    )

    session.updated_at = now

    db.commit()

    return True


def delete(
    db: Session,
    session_id: str,
    user_id: str,
) -> bool:
    row = _get_session_row(
        db,
        session_id,
        user_id,
    )
    if row is None:
        return False

    db.delete(row)
    db.commit()

    return True
