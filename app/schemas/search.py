from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """检索请求。"""

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    """单条检索结果。"""

    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    content: str
    score: float  # 相似度（1 - 余弦距离），越接近 1 越相关
