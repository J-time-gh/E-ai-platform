from redis.exceptions import RedisError

from app.services.embedding import CachedEmbedder


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(index)] for index, _ in enumerate(texts)]


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def setex(
        self,
        key: str,
        _ttl: int,
        value: str,
    ) -> bool:
        self.data[key] = value
        return True

    def delete(self, key: str) -> int:
        return int(self.data.pop(key, None) is not None)


def test_cached_embedder_reuses_cached_vector() -> None:
    inner = CountingEmbedder()
    redis_client = FakeRedis()

    embedder = CachedEmbedder(
        inner,
        redis_client,
    )

    first = embedder.embed_texts(
        ["相同文本"],
    )
    second = embedder.embed_texts(
        ["相同文本"],
    )

    assert first == second
    assert inner.calls == [["相同文本"]]


def test_cached_embedder_deduplicates_batch_texts() -> None:
    inner = CountingEmbedder()
    redis_client = FakeRedis()

    embedder = CachedEmbedder(
        inner,
        redis_client,
    )

    vectors = embedder.embed_texts(
        [
            "苹果",
            "香蕉",
            "苹果",
        ],
    )

    assert inner.calls == [
        [
            "苹果",
            "香蕉",
        ],
    ]
    assert len(vectors) == 3
    assert vectors[0] == vectors[2]


class UnavailableRedis:
    def get(self, _key: str) -> str:
        raise RedisError("Redis 不可用")


def test_cached_embedder_falls_back_when_redis_is_unavailable() -> None:
    inner = CountingEmbedder()

    embedder = CachedEmbedder(
        inner,
        UnavailableRedis(),
    )

    vectors = embedder.embed_texts(
        ["Redis 故障时仍可向量化"],
    )

    assert vectors == [[0.0]]
    assert inner.calls == [
        ["Redis 故障时仍可向量化"],
    ]
