import io
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.models.chunk import EMBEDDING_DIM, Chunk


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


def test_upload_saves_file_to_disk(client: TestClient) -> None:
    doc_id = _upload(client).json()["id"]
    files = list(Path(settings.upload_dir).glob(f"{doc_id}*"))
    assert len(files) == 1


def test_delete_removes_file_from_disk(client: TestClient) -> None:
    doc_id = _upload(client).json()["id"]
    path = next(Path(settings.upload_dir).glob(f"{doc_id}*"))
    assert path.exists()
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert not path.exists()


def test_upload_ingests_chunks(client: TestClient, db_session) -> None:
    content = ("这是用于测试切块的句子。" * 100).encode("utf-8")
    doc_id = _upload(client, filename="book.txt", content=content).json()["id"]

    rows = db_session.scalars(
        select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index)
    ).all()
    assert len(rows) > 1
    assert [r.chunk_index for r in rows] == list(range(len(rows)))
    assert all(len(r.embedding) == EMBEDDING_DIM for r in rows)


def test_delete_document_removes_chunks(client: TestClient, db_session) -> None:
    doc_id = _upload(client).json()["id"]
    assert db_session.scalars(select(Chunk).where(Chunk.document_id == doc_id)).all()

    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert not db_session.scalars(select(Chunk).where(Chunk.document_id == doc_id)).all()


def test_upload_empty_file_returns_422_and_cleans_up(client: TestClient) -> None:
    response = _upload(client, filename="empty.txt", content=b"   \n")
    assert response.status_code == 422
    assert "文本" in response.json()["detail"]
    assert all(doc["filename"] != "empty.txt" for doc in client.get("/documents").json())
