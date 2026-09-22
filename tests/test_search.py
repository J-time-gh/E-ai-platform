import io

import httpx
from fastapi.testclient import TestClient


def _upload(
    client: TestClient,
    headers: dict[str, str],
    filename: str,
    content: str,
) -> str:
    response = client.post(
        "/documents/upload",
        headers=headers,
        files={
            "file": (
                filename,
                io.BytesIO(content.encode()),
                "text/plain",
            ),
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _search(
    client: TestClient, headers: dict[str, str], query: str, top_k: int = 5
) -> httpx.Response:
    return client.post("/search", headers=headers, json={"query": query, "top_k": top_k})


def test_search_finds_exact_chunk(
    client: TestClient, authenticated_headers: dict[str, str]
) -> None:
    text = "机器学习是人工智能的一个分支。"
    _upload(client, authenticated_headers, "ml.txt", text)
    results = _search(client, authenticated_headers, text).json()
    assert results[0]["content"] == text
    assert results[0]["filename"] == "ml.txt"
    assert results[0]["score"] > 0.99  # 同一文本 → 距离≈0


def test_search_ranks_most_similar_first(
    client: TestClient, authenticated_headers: dict[str, str]
) -> None:
    _upload(client, authenticated_headers, "a.txt", "苹果是一种水果。")
    _upload(client, authenticated_headers, "b.txt", "汽车需要定期保养。")
    results = _search(client, authenticated_headers, "苹果是一种水果。").json()
    assert results[0]["filename"] == "a.txt"


def test_search_respects_top_k(client: TestClient, authenticated_headers: dict[str, str]) -> None:
    _upload(client, authenticated_headers, "long.txt", "这是第一段内容。" * 200)
    assert len(_search(client, authenticated_headers, "这是第一段内容。", top_k=2).json()) == 2


def test_search_no_documents_returns_empty(
    client: TestClient, authenticated_headers: dict[str, str]
) -> None:
    assert _search(client, authenticated_headers, "随便问问").json() == []


def test_search_rejects_empty_query(
    client: TestClient, authenticated_headers: dict[str, str]
) -> None:
    assert _search(client, authenticated_headers, "").status_code == 422


def test_search_rejects_top_k_out_of_range(
    client: TestClient, authenticated_headers: dict[str, str]
) -> None:
    assert _search(client, authenticated_headers, "x", top_k=0).status_code == 422
    assert _search(client, authenticated_headers, "x", top_k=100).status_code == 422
