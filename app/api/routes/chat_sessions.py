from fastapi import APIRouter, HTTPException, status

from app.api.dependencies.auth import CurrentUserDep
from app.db.session import DbSession
from app.schemas.chat_session import (
    ChatSessionResponse,
    CreateChatSessionRequest,
    PersistedChatMessageResponse,
)
from app.services import chat_session_store

router = APIRouter(
    prefix="/chat/sessions",
    tags=["chat-sessions"],
)


@router.post(
    "",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    request: CreateChatSessionRequest,
    db: DbSession,
    current_user: CurrentUserDep,
) -> ChatSessionResponse:
    return chat_session_store.create(
        db,
        user_id=current_user.id,
        title=request.title,
    )


@router.get(
    "",
    response_model=list[ChatSessionResponse],
)
async def list_chat_sessions(
    db: DbSession,
    current_user: CurrentUserDep,
) -> list[ChatSessionResponse]:
    return chat_session_store.list_all(
        db,
        current_user.id,
    )


@router.get(
    "/{session_id}/messages",
    response_model=list[PersistedChatMessageResponse],
)
async def list_chat_messages(
    session_id: str,
    db: DbSession,
    current_user: CurrentUserDep,
) -> list[PersistedChatMessageResponse]:
    messages = chat_session_store.list_messages(
        db,
        session_id,
        current_user.id,
    )

    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    return messages


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_session(
    session_id: str,
    db: DbSession,
    current_user: CurrentUserDep,
) -> None:
    deleted = chat_session_store.delete(
        db,
        session_id,
        current_user.id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
