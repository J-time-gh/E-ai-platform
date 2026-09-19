from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.tools.base import ToolError


class SqlQueryArguments(BaseModel):
    """SQL 工具参数。"""

    query_name: Literal[
        "document_count",
        "chunks_for_document",
    ]
    document_id: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SqlQueryTool:
    """执行预定义的只读数据库查询。"""

    name = "sql_query"
    description = "执行预定义的只读数据库查询。"

    parameters = {
        "type": "object",
        "properties": {
            "query_name": {
                "type": "string",
                "enum": [
                    "document_count",
                    "chunks_for_document",
                ],
            },
            "document_id": {
                "type": "string",
                "description": "文档 ID。查询 chunks 时必填。",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 20,
            },
        },
        "required": ["query_name"],
        "additionalProperties": False,
    }

    def __init__(self, db: Session) -> None:
        self._db = db

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            args = SqlQueryArguments.model_validate(arguments)
        except ValidationError as exc:
            raise ToolError(f"sql_query 参数错误：{exc}") from exc

        # 使用配置中的最大行数，防止模型请求过多数据。
        limit = min(args.limit, settings.sql_max_rows)

        if args.query_name == "document_count":
            statement = text(
                """
                SELECT count(*) AS count
                FROM documents
                """,
            )
            params: dict[str, Any] = {}

        elif args.query_name == "chunks_for_document":
            if not args.document_id:
                raise ToolError(
                    "chunks_for_document 必须提供 document_id",
                )

            statement = text(
                """
                SELECT
                    id,
                    document_id,
                    chunk_index,
                    content
                FROM chunks
                WHERE document_id = :document_id
                ORDER BY chunk_index
                LIMIT :limit
                """,
            )
            params = {
                "document_id": args.document_id,
                "limit": limit,
            }

        else:
            raise ToolError(
                f"不允许的查询类型：{args.query_name}",
            )

        # 设置当前事务的 SQL 超时时间。
        self._db.execute(
            text(
                f"SET LOCAL statement_timeout = {settings.sql_timeout_ms}",
            ),
        )
        # 获取查询结果
        rows = (
            self._db.execute(
                statement,
                params,
            )
            # .mappings()会把每一行转换为类似字典的对象
            .mappings()
            .all()
        )

        return {
            "rows": [dict(row) for row in rows],
            "count": len(rows),
        }
