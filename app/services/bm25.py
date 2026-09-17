"""BM25 关键词检索：jieba 分词 + rank_bm25，补齐向量检索的字面匹配短板。

注意：不同 mode 下 SearchResult.score 的量纲不同——
向量模式是余弦相似度（0~1），BM25 模式是词频分数（任意正数）。
两者不可直接比较，也**不能相加**（融合用 RRF，只看排名）。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.schemas.search import SearchResult

jieba.setLogLevel(logging.WARNING)  # 关掉 "Building prefix dict" 之类的噪音日志


def tokenize(text: str) -> list[str]:
    """中文分词：BM25 比的是"词"，必须先分词（按字切会失去意义）。"""
    return [token for token in jieba.lcut(text) if token.strip()]


@dataclass
class IndexedChunk:
    """索引里保存的一行——检索时不需要再回数据库。"""

    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    content: str
    tokens: set[str]  # 预分词结果，用于判断"是否真的含查询词"


class Bm25Index:
    """进程内的 BM25 索引；数据库内容变化时自动重建。"""

    def __init__(self) -> None:
        self._version: tuple[int, datetime | None] | None = None
        self._rows: list[IndexedChunk] = []
        self._bm25: BM25Okapi | None = None

    def _read_version(self, db: Session) -> tuple[int, datetime | None]:
        """用 (块数量, 最新创建时间) 判断索引是否过期。"""
        total, latest = db.execute(select(func.count(Chunk.id), func.max(Chunk.created_at))).one()
        return int(total), latest

    def _rebuild(self, db: Session) -> None:
        rows = db.execute(
            select(Chunk, Document.filename).join(Document, Chunk.document_id == Document.id)
        ).all()
        self._rows = []
        corpus: list[list[str]] = []
        for chunk, filename in rows:
            tokens = tokenize(chunk.content)
            corpus.append(tokens)
            self._rows.append(
                IndexedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    filename=filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    tokens=set(tokens),
                )
            )
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._version = self._read_version(db)

    def search(self, db: Session, query: str, top_k: int) -> list[SearchResult]:
        """按 BM25 分数降序返回 top_k；与查询词无交集的块会被过滤掉。

        刻意不用 "score > 0" 过滤：rank_bm25 的 IDF 在"某词出现在恰好一半文档里"时
        会算出 0，在"某词很常见"时 eps 还可能为负——两种情况都会把真正含查询词的块
        误过滤掉。所以改用分词交集判断，分数只负责排序。
        """
        if self._read_version(db) != self._version:
            self._rebuild(db)
        if self._bm25 is None:
            return []

        query_tokens = tokenize(query)
        query_token_set = set(query_tokens)
        scores = self._bm25.get_scores(query_tokens)
        candidates = [
            (row, float(score))
            for row, score in zip(self._rows, scores, strict=True)
            if row.tokens & query_token_set
        ]
        candidates.sort(key=lambda pair: pair[1], reverse=True)
        return [
            SearchResult(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                filename=row.filename,
                chunk_index=row.chunk_index,
                content=row.content,
                score=round(score, 4),
            )
            for row, score in candidates[:top_k]
        ]


@lru_cache(maxsize=1)
def get_bm25_index() -> Bm25Index:
    """进程内单例：只保留一份索引。"""
    return Bm25Index()
