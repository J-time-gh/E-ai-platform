"""ORM 模型集合（导入即注册到 Base.metadata）。"""

from app.db.models.chunk import Chunk
from app.db.models.document import Document

__all__ = ["Chunk", "Document"]
