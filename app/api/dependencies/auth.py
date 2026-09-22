"""FastAPI 当前登录用户认证依赖。"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import (
    InvalidAccessTokenError,
    get_user_id_from_access_token,
)
from app.db.models.user import User
from app.db.session import DbSession
from app.services import user_store

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _credentials_error() -> HTTPException:
    """统一返回认证失败响应。"""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或已过期的访问令牌",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    """验证 Bearer Token，并返回当前启用状态的用户。"""
    try:
        user_id = get_user_id_from_access_token(token)
    except InvalidAccessTokenError as exc:
        raise _credentials_error() from exc

    user = user_store.get_by_id(db, user_id)

    if user is None or not user.is_active:
        raise _credentials_error()

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
