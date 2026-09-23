from datetime import datetime
from typing import Literal

from pydantic import BaseModel

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
