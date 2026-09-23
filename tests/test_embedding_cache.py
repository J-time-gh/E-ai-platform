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
