"""documents 表的数据访问层。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.schemas.documents import DocumentInfo


def _to_info(row: Document) -> DocumentInfo:
    """ORM 对象转换为接口返回模型。"""
    return DocumentInfo(
        id=row.id,
        filename=row.filename,
        size=row.size,
        content_type=row.content_type,
        uploaded_at=row.uploaded_at,
        status=row.status,
        ingest_error=row.ingest_error,
    )


def add(
    db: Session,
    document: DocumentInfo,
    *,
    user_id: str,
    stored_path: str | None = None,
    status: str = "pending",
) -> DocumentInfo:
    """创建属于指定用户的文档记录。"""
    row = Document(
        id=document.id,
        user_id=user_id,
        filename=document.filename,
        size=document.size,
        content_type=document.content_type,
        uploaded_at=document.uploaded_at,
        stored_path=stored_path,
        status=status,
        ingest_error=None,
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return _to_info(row)


def list_all(db: Session, user_id: str) -> list[DocumentInfo]:
    """列出指定用户的全部文档。"""
    rows = db.scalars(
        select(Document).where(Document.user_id == user_id).order_by(Document.uploaded_at),
    ).all()

    return [_to_info(row) for row in rows]


def _get_row(
    db: Session,
    doc_id: str,
    user_id: str,
) -> Document | None:
    """按文档 ID 和所属用户查询记录。"""
    return db.scalar(
        select(Document).where(
            Document.id == doc_id,
            Document.user_id == user_id,
        ),
    )


def get(
    db: Session,
    doc_id: str,
    user_id: str,
) -> DocumentInfo | None:
    """获取指定用户拥有的文档。"""
    row = _get_row(db, doc_id, user_id)

    return _to_info(row) if row is not None else None


def get_stored_path(
    db: Session,
    doc_id: str,
    user_id: str,
) -> str | None:
    """获取指定用户拥有的文档存储路径。"""
    row = _get_row(db, doc_id, user_id)

    return row.stored_path if row is not None else None


def delete(
    db: Session,
    doc_id: str,
    user_id: str,
) -> bool:
    """删除指定用户拥有的文档。"""
    row = _get_row(db, doc_id, user_id)

    if row is None:
        return False

    db.delete(row)
    db.commit()

    return True


# 加 Worker 专用状态方法
def claim_for_ingest(
    db: Session,
    document_id: str,
) -> Document | None:
    """原子认领一个 pending 文档，避免重复 Worker 同时处理。"""
    row = db.scalar(
        select(Document).where(Document.id == document_id).with_for_update(),
    )

    if row is None or row.status != "pending":
        return None

    row.status = "processing"
    row.ingest_error = None
    db.commit()
    db.refresh(row)

    return row


def mark_ready(
    db: Session,
    document_id: str,
) -> str | None:
    """将 processing 文档标记 ready，返回所属 user_id。"""
    row = db.get(Document, document_id)

    if row is None:
        return None

    row.status = "ready"
    row.ingest_error = None
    db.commit()

    return row.user_id


def mark_failed(
    db: Session,
    document_id: str,
    error_message: str,
) -> str | None:
    """将文档标记 failed，错误信息只保存可安全展示给用户的内容。"""
    row = db.get(Document, document_id)

    if row is None:
        return None

    row.status = "failed"
    row.ingest_error = error_message[:1000]
    db.commit()

    return row.user_id
