from fastapi import APIRouter

from app.db.session import DbSession
from app.schemas.search import SearchRequest, SearchResult
from app.services import retrieval
from app.services.embedding import EmbedderDep

router = APIRouter(tags=["search"])


@router.post("/search", response_model=list[SearchResult])
async def search(
    request: SearchRequest,
    db: DbSession,
    embedder: EmbedderDep,
) -> list[SearchResult]:
    """语义检索：返回与查询最相关的知识块。"""
    return retrieval.search(db, embedder, request.query, request.top_k)
