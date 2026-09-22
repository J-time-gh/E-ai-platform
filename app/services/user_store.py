"""users 表的数据访问层。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User


def normalize_email(email: str) -> str:
    """统一邮箱格式，避免大小写或空格导致重复账户。"""
    return email.strip().lower()


def get_by_id(db: Session, user_id: str) -> User | None:
    """根据用户 ID 查询用户。"""
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    """根据邮箱查询用户。"""
    normalized_email = normalize_email(email)

    return db.scalar(
        select(User).where(User.email == normalized_email),
    )


def create(
    db: Session,
    *,
    email: str,
    password_hash: str,
) -> User:
    """创建用户并保存密码哈希。"""
    user = User(
        id=str(uuid4()),
        email=normalize_email(email),
        password_hash=password_hash,
        is_active=True,
        created_at=datetime.now(UTC),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user
