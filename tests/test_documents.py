import io

import httpx
from fastapi.testclient import TestClient


def _upload(
    client: TestClient,
    filename: str = "notes.txt",
    content: bytes = b"hello world",
) -> httpx.Response:
    return client.post(
        "/documents/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def test_upload_returns_metadata(client: TestClient) -> None:
    response = _upload(client)
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["size"] == 11
    assert body["id"]
    assert body["uploaded_at"]


def test_upload_rejects_unsupported_type(client: TestClient) -> None:
    response = _upload(client, filename="virus.exe")
    assert response.status_code == 415


def test_upload_rejects_oversized_file(client: TestClient) -> None:
    big = b"x" * (20 * 1024 * 1024 + 1)
    response = _upload(client, filename="big.txt", content=big)
    assert response.status_code == 413


def test_list_documents(client: TestClient) -> None:
    _upload(client, "a.txt")
    _upload(client, "b.md")
    response = client.get("/documents")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_document_by_id(client: TestClient) -> None:
    doc_id = _upload(client).json()["id"]
    response = client.get(f"/documents/{doc_id}")
    assert response.status_code == 200
    assert response.json()["id"] == doc_id


def test_get_missing_document_returns_404(client: TestClient) -> None:
    response = client.get("/documents/not-exist")
    assert response.status_code == 404


def test_delete_document(client: TestClient) -> None:
    doc_id = _upload(client).json()["id"]
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 404


def test_delete_missing_document_returns_404(client: TestClient) -> None:
    assert client.delete("/documents/nope").status_code == 404
