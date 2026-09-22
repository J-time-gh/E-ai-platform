import io
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.models.chunk import EMBEDDING_DIM, Chunk


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    password = "correct-horse-battery-staple"
    register_response = client.post(
        "/auth/register",
        json={
            "email": "document-user@example.com",
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": "document-user@example.com",
            "password": password,
        },
    )
    assert login_response.status_code == 200

    return {
        "Authorization": f"Bearer {login_response.json()['access_token']}",
    }


def _upload(
    client: TestClient,
    headers: dict[str, str],
    filename: str = "notes.txt",
    content: bytes = b"hello world",
) -> httpx.Response:
    return client.post(
        "/documents/upload",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


def test_documents_require_authentication(client: TestClient) -> None:
    response = client.get("/documents")

    assert response.status_code == 401


def test_upload_returns_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = _upload(client, auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "notes.txt"
    assert body["size"] == 11
    assert body["id"]
    assert body["uploaded_at"]


def test_upload_rejects_unsupported_type(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = _upload(client, auth_headers, filename="virus.exe")

    assert response.status_code == 415


def test_upload_rejects_oversized_file(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    big = b"x" * (20 * 1024 * 1024 + 1)
    response = _upload(client, auth_headers, filename="big.txt", content=big)

    assert response.status_code == 413


def test_list_documents(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    _upload(client, auth_headers, "a.txt")
    _upload(client, auth_headers, "b.md")

    response = client.get("/documents", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_document_by_id(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    doc_id = _upload(client, auth_headers).json()["id"]

    response = client.get(f"/documents/{doc_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == doc_id


def test_get_missing_document_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/documents/not-exist", headers=auth_headers)

    assert response.status_code == 404


def test_delete_document(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    doc_id = _upload(client, auth_headers).json()["id"]

    assert client.delete(f"/documents/{doc_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/documents/{doc_id}", headers=auth_headers).status_code == 404


def test_delete_missing_document_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.delete("/documents/nope", headers=auth_headers)

    assert response.status_code == 404


def test_upload_saves_file_to_disk(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    doc_id = _upload(client, auth_headers).json()["id"]

    files = list(Path(settings.upload_dir).glob(f"{doc_id}*"))

    assert len(files) == 1


def test_delete_removes_file_from_disk(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    doc_id = _upload(client, auth_headers).json()["id"]
    path = next(Path(settings.upload_dir).glob(f"{doc_id}*"))

    assert path.exists()
    assert client.delete(f"/documents/{doc_id}", headers=auth_headers).status_code == 204
    assert not path.exists()


def test_upload_ingests_chunks(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    content = ("这是用于测试切块的句子。" * 100).encode("utf-8")
    doc_id = _upload(
        client,
        auth_headers,
        filename="book.txt",
        content=content,
    ).json()["id"]

    rows = db_session.scalars(
        select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index),
    ).all()

    assert len(rows) > 1
    assert [row.chunk_index for row in rows] == list(range(len(rows)))
    assert all(len(row.embedding) == EMBEDDING_DIM for row in rows)


def test_delete_document_removes_chunks(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    doc_id = _upload(client, auth_headers).json()["id"]

    assert db_session.scalars(select(Chunk).where(Chunk.document_id == doc_id)).all()
    assert client.delete(f"/documents/{doc_id}", headers=auth_headers).status_code == 204
    assert not db_session.scalars(select(Chunk).where(Chunk.document_id == doc_id)).all()


def test_upload_empty_file_returns_422_and_cleans_up(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = _upload(
        client,
        auth_headers,
        filename="empty.txt",
        content=b"   \n",
    )

    assert response.status_code == 422
    assert "文本" in response.json()["detail"]

    documents = client.get("/documents", headers=auth_headers).json()
    assert all(document["filename"] != "empty.txt" for document in documents)
