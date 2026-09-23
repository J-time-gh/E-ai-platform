from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api.dependencies.auth import CurrentUserDep
from app.db.session import DbSession
from app.schemas.documents import DocumentInfo
from app.services import document_store, file_store
from app.services.embedding import EmbedderDep
from app.services.ingest import IngestError, ingest_document
from app.services.search_cache import invalidate_search_cache

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _cleanup_failed_upload(
    db: DbSession,
    document_id: str,
    user_id: str,
    stored_path: str,
) -> None:
    """入库失败时清理数据库记录与文件。"""
    document_store.delete(db, document_id, user_id)
    file_store.delete_file(stored_path)


@router.post("/upload", response_model=DocumentInfo, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    db: DbSession,
    embedder: EmbedderDep,
    current_user: CurrentUserDep,
) -> DocumentInfo:
    """上传文档：落盘 → 写元数据 → 解析切分向量化入库（阶段 3 M1–M4）；失败回滚记录与文件。"""
    filename = file.filename or "unnamed"
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支持的文件类型：{suffix or '无扩展名'}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="文件超过 20MB 限制",
        )

    document_id = str(uuid4())
    stored_path = file_store.save_file(document_id, suffix, content)

    document = DocumentInfo(
        id=document_id,
        filename=filename,
        size=len(content),
        content_type=file.content_type or "application/octet-stream",
        uploaded_at=datetime.now(UTC),
    )
    result = document_store.add(
        db,
        document,
        user_id=current_user.id,
        stored_path=stored_path,
    )

    try:
        ingest_document(db, document_id, stored_path, embedder)
    except IngestError as exc:
        _cleanup_failed_upload(
            db,
            document_id,
            current_user.id,
            stored_path,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        _cleanup_failed_upload(
            db,
            document_id,
            current_user.id,
            stored_path,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档处理失败，请稍后重试",
        ) from exc
    # 上传文档后让当前用户缓存失效
    invalidate_search_cache(
        current_user.id,
    )
    return result


@router.get("", response_model=list[DocumentInfo])
async def list_documents(
    db: DbSession,
    current_user: CurrentUserDep,
) -> list[DocumentInfo]:
    return document_store.list_all(db, current_user.id)


@router.get("/{doc_id}", response_model=DocumentInfo)
async def get_document(
    doc_id: str,
    db: DbSession,
    current_user: CurrentUserDep,
) -> DocumentInfo:
    document = document_store.get(
        db,
        doc_id,
        current_user.id,
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    return document


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    db: DbSession,
    current_user: CurrentUserDep,
) -> None:
    stored_path = document_store.get_stored_path(
        db,
        doc_id,
        current_user.id,
    )

    if not document_store.delete(
        db,
        doc_id,
        current_user.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )
    # 删除文档后让缓存失效
    invalidate_search_cache(
        current_user.id,
    )
    if stored_path:
        file_store.delete_file(stored_path)
