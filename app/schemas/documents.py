from datetime import datetime

from pydantic import BaseModel


class DocumentInfo(BaseModel):
    id: str
    filename: str
    size: int
    content_type: str
    uploaded_at: datetime
