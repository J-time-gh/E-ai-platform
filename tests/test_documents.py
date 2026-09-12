import io

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import document_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store() -> None:
    document_store.clear()


def _upload(filename: str = "notes.txt", content: bytes = b"hello world") -> httpx.Response:
    return client.post(
        "/documents/upload",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def test_upload_returns_metadata() -> None:
    response = _upload()
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["size"] == 11
    assert body["id"]
    assert body["uploaded_at"]


def test_upload_rejects_unsupported_type() -> None:
    response = _upload(filename="virus.exe")
    assert response.status_code == 415


def test_upload_rejects_oversized_file() -> None:
    big = b"x" * (20 * 1024 * 1024 + 1)
    response = _upload(filename="big.txt", content=big)
    assert response.status_code == 413


def test_list_documents() -> None:
    _upload("a.txt")
    _upload("b.md")
    response = client.get("/documents")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_document_by_id() -> None:
    doc_id = _upload().json()["id"]
    response = client.get(f"/documents/{doc_id}")
    assert response.status_code == 200
    assert response.json()["id"] == doc_id


def test_get_missing_document_returns_404() -> None:
    response = client.get("/documents/not-exist")
    assert response.status_code == 404


def test_delete_document() -> None:
    doc_id = _upload().json()["id"]
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 404


def test_delete_missing_document_returns_404() -> None:
    assert client.delete("/documents/nope").status_code == 404
