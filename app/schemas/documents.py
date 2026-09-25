from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# 数据库文档状态定义
DocumentStatus = Literal[
    "pending",
    "processing",
    "ready",
    "failed",
]


class DocumentInfo(BaseModel):
    id: str
    filename: str
    size: int
    content_type: str
    uploaded_at: datetime
    status: DocumentStatus
    ingest_error: str | None
