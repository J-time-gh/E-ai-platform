from fastapi import APIRouter

from app.db.session import DbSession
from app.schemas.search import SearchRequest, SearchResult
from app.services import retrieval
from app.services.embedding import EmbedderDep
from app.services.reranker import RerankerDep

router = APIRouter(tags=["search"])


@router.post("/search", response_model=list[SearchResult])
async def search(
    request: SearchRequest,
    db: DbSession,
    embedder: EmbedderDep,
    reranker: RerankerDep,
) -> list[SearchResult]:
    """语义检索：返回与查询最相关的知识块。

    刻意**不传** min_score / min_rerank_score：/search 是"纯检索"接口，
    不门控，方便评测脚本量出真实的检索质量。
    """
    return retrieval.search_with_mode(
        db,
        embedder,
        request.query,
        request.top_k,
        request.mode,
        reranker=reranker,
    )
