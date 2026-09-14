"""文档入库编排：解析 → 切分 → 向量化 → 写库。"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.services import chunk_store
from app.services.chunking import split_text
from app.services.embedding import Embedder
from app.services.parsers import parse_document


class IngestError(Exception):
    """用户内容无法处理（解析失败/提取不到文本等）。"""


def ingest_document(
    db: Session,
    document_id: str,
    stored_path: str,
    embedder: Embedder,
) -> int:
    """处理文档并写入向量块，返回块数。"""
    try:
        text = parse_document(Path(stored_path))
    except Exception as exc:
        raise IngestError(f"文档解析失败：{exc}") from exc

    chunks = split_text(text)
    if not chunks:
        raise IngestError("未能从文档中提取到文本内容（可能是扫描件或空文件）")

    vectors = embedder.embed_texts(chunks)
    return chunk_store.replace_chunks(db, document_id, chunks, vectors)
