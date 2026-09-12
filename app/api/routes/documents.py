from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.schemas.documents import DocumentInfo
from app.services import document_store

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("/upload", response_model=DocumentInfo, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile) -> DocumentInfo:
    """上传文档（当前仅保存元数据，阶段 3 加入解析与向量化）。"""
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
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件超过 20MB 限制",
        )

    document = DocumentInfo(
        id=str(uuid4()),
        filename=filename,
        size=len(content),
        content_type=file.content_type or "application/octet-stream",
        uploaded_at=datetime.now(UTC),
    )
    return document_store.add(document)


@router.get("", response_model=list[DocumentInfo])
async def list_documents() -> list[DocumentInfo]:
    return document_store.list_all()


@router.get("/{doc_id}", response_model=DocumentInfo)
async def get_document(doc_id: str) -> DocumentInfo:
    document = document_store.get(doc_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return document


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str) -> None:
    if not document_store.delete(doc_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
