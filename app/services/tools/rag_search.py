from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import retrieval
from app.services.embedding import Embedder
from app.services.reranker import Reranker
from app.services.tools.base import ToolError


# 参数校验
class RagSearchArguments(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class RagSearchTool:
    name = "rag_search"
    description = "检索企业知识库。适用于询问项目文档、规章制度、上传资料等知识库内容。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要检索的问题",
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 5,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    # 依赖注入
    def __init__(
        self,
        db: Session,
        embedder: Embedder,
        reranker: Reranker,
    ) -> None:
        self._db = db
        self._embedder = embedder
        self._reranker = reranker

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            args = RagSearchArguments.model_validate(arguments)
        except ValidationError as exc:
            raise ToolError(f"rag_search 参数错误：{exc}") from exc

        results = retrieval.search_with_mode(
            db=self._db,
            embedder=self._embedder,
            query=args.query,
            top_k=args.top_k,
            mode="hybrid_rerank",
            min_score=settings.min_vector_score,
            reranker=self._reranker,
            min_rerank_score=settings.min_rerank_score,
        )

        return {
            "results": [result.model_dump() for result in results],
            "count": len(results),
        }
