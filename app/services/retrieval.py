"""语义检索：把查询文本向量化，在 chunks 表里找余弦距离最近的块。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.schemas.search import SearchResult
from app.services.embedding import Embedder


def search_chunks(
    db: Session,
    query_vector: list[float],
    top_k: int,
) -> list[SearchResult]:
    """按余弦距离升序返回最相似的 top_k 个块（含来源文件名和相似度）。"""
    distance = Chunk.embedding.cosine_distance(query_vector)
    rows = db.execute(
        select(Chunk, Document.filename, distance)
        .join(Document, Chunk.document_id == Document.id)
        .order_by(distance)
        .limit(top_k)
    ).all()
    return [
        SearchResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            score=round(1.0 - float(distance_value), 4),
        )
        for chunk, filename, distance_value in rows
    ]


def search(
    db: Session,
    embedder: Embedder,
    query: str,
    top_k: int,
) -> list[SearchResult]:
    """把查询向量化后检索。"""
    query_vector = embedder.embed_texts([query])[0]
    return search_chunks(db, query_vector, top_k)
