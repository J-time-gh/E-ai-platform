from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.schemas.documents import DocumentInfo


def _to_info(row: Document) -> DocumentInfo:
    """ORM 对象 → Pydantic 模型（数据库层与接口层的转换）"""
    return DocumentInfo(
        id=row.id,
        filename=row.filename,
        size=row.size,
        content_type=row.content_type,
        uploaded_at=row.uploaded_at,
    )


def add(db: Session, document: DocumentInfo, stored_path: str | None = None) -> DocumentInfo:
    row = Document(
        id=document.id,
        filename=document.filename,
        size=document.size,
        content_type=document.content_type,
        uploaded_at=document.uploaded_at,
        stored_path=stored_path,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_info(row)


def list_all(db: Session) -> list[DocumentInfo]:
    rows = db.scalars(select(Document).order_by(Document.uploaded_at)).all()
    return [_to_info(row) for row in rows]


def get(db: Session, doc_id: str) -> DocumentInfo | None:
    row = db.get(Document, doc_id)
    return _to_info(row) if row is not None else None


def delete(db: Session, doc_id: str) -> bool:
    row = db.get(Document, doc_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def get_stored_path(db: Session, doc_id: str) -> str | None:
    row = db.get(Document, doc_id)
    return row.stored_path if row is not None else None
