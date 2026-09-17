"""语义检索：把查询文本向量化，在 chunks 表里找余弦距离最近的块。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.schemas.search import SearchResult
from app.services.bm25 import get_bm25_index
from app.services.embedding import Embedder


# 执行数据库检索
def search_chunks(
    db: Session,
    query_vector: list[float],
    top_k: int,
) -> list[SearchResult]:
    """按余弦距离升序返回最相似的 top_k 个块（含来源文件名和相似度）。"""
    # pgvector 提供的操作，对应 SQL 中的 <=> 运算符。
    distance = Chunk.embedding.cosine_distance(query_vector)
    # 构建并执行查询
    rows = db.execute(
        select(Chunk, Document.filename, distance)
        # 把 chunks 表和 documents 表连接起来，连接条件是 chunk.document_id = document.id。
        .join(Document, Chunk.document_id == Document.id)
        # 余弦距离升序排列，距离最小的（最相似的）排在最前面。
        .order_by(distance)
        # 只取前 top_k 条
        .limit(top_k)
        # b.execute(...).all()
        # 执行查询，返回所有结果行。每一行是一个元组：(chunk, filename, distance_value)。
    ).all()
    # 组装返回结果
    return [
        SearchResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            # round是四舍五入
            score=round(1.0 - float(distance_value), 4),
        )
        # 序列解包
        for chunk, filename, distance_value in rows
    ]


# 对外接口
def search(
    # 数据库会话
    db: Session,
    # 一个负责把文本转成向量的服务对象
    embedder: Embedder,
    query: str,
    top_k: int,
) -> list[SearchResult]:
    """把查询向量化后检索。"""
    query_vector = embedder.embed_texts([query])[0]
    return search_chunks(db, query_vector, top_k)


# 分发函数
def search_with_mode(
    db: Session,
    embedder: Embedder,
    query: str,
    top_k: int,
    mode: str = "vector",
) -> list[SearchResult]:
    """按 mode 选择检索器（阶段 4 后续会再加 hybrid / hybrid_rerank）。"""
    if mode == "bm25":
        return get_bm25_index().search(db, query, top_k)
    return search(db, embedder, query, top_k)
