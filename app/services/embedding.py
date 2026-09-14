"""文本向量化：真实实现（bge-m3 + GPU）与测试替身（FakeEmbedder）。"""

import hashlib
import os
from functools import lru_cache
from typing import Annotated, Protocol

from fastapi import Depends

from app.core.config import settings
from app.db.models.chunk import EMBEDDING_DIM


class Embedder(Protocol):
    """向量化接口：把一批文本转成向量列表。"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class BgeM3Embedder:
    """bge-m3 实现：懒加载模型，跑在 GPU 上。"""

    def __init__(self) -> None:
        os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
        os.environ.setdefault("HF_HOME", settings.hf_home)

        from sentence_transformers import (
            SentenceTransformer,  # 懒导入：CI 不装 torch 也能 import 本模块
        )

        self._model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=settings.embedding_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]


class FakeEmbedder:
    """测试替身：由文本哈希生成确定性向量，无需模型/GPU。"""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 - 0.5 for i in range(self._dim)]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """FastAPI 依赖：进程内单例（首次请求时才加载模型）。"""
    return BgeM3Embedder()


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
