"""BM25 关键词检索测试：纯 CPU、无需 GPU，CI 可直接跑。"""

import io

from fastapi.testclient import TestClient

from app.services.bm25 import tokenize


def _upload(client: TestClient, filename: str, content: str) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), "text/plain")},
    )
    assert response.status_code == 201


def _search(client: TestClient, query: str, mode: str = "bm25", top_k: int = 5) -> list[dict]:
    response = client.post("/search", json={"query": query, "top_k": top_k, "mode": mode})
    assert response.status_code == 200
    return response.json()


def test_tokenize_splits_chinese_into_words() -> None:
    text = "科学实验在认识过程中的作用"
    tokens = tokenize(text)
    assert tokens
    assert len(tokens) < len(text)  # 按词切了，不是按字


def test_bm25_finds_chunk_by_keyword(client: TestClient) -> None:
    _upload(client, "a.txt", "科学实验是认识过程中的重要环节。")
    _upload(client, "b.txt", "商品的价值量由社会必要劳动时间决定。")
    _upload(client, "c.txt", "资本的有机构成随着积累而提高。")  # ★ 新增：第三篇无关文档
    results = _search(client, "科学实验")
    assert results
    assert results[0]["filename"] == "a.txt"


def test_bm25_returns_empty_for_unrelated_query(client: TestClient) -> None:
    _upload(client, "a.txt", "科学实验是认识过程中的重要环节。")
    assert _search(client, "zzzqqq") == []


def test_bm25_index_rebuilds_after_upload(client: TestClient) -> None:
    _upload(client, "a.txt", "科学实验是认识过程中的重要环节。")
    _upload(client, "b.txt", "商品的价值量由社会必要劳动时间决定。")
    assert _search(client, "唯物论") == []  # 先建一次索引（2 块）
    _upload(client, "c.txt", "唯物论和唯心论的根本分歧。")  # ★ 第 3 块
    results = _search(client, "唯物论")  # 索引应已自动重建
    assert results
    assert results[0]["filename"] == "c.txt"


def test_vector_mode_remains_default(client: TestClient) -> None:
    _upload(client, "a.txt", "苹果是一种水果。")
    body = client.post("/search", json={"query": "苹果是一种水果。"}).json()
    assert body
    assert body[0]["filename"] == "a.txt"


def test_search_rejects_unknown_mode(client: TestClient) -> None:
    assert client.post("/search", json={"query": "x", "mode": "bm42"}).status_code == 422
