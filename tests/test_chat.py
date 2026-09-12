from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_chat_returns_reply() -> None:
    response = client.post("/chat", json={"message": "你好"})
    # 请求体
    assert response.status_code == 200
    body = response.json()
    assert "你好" in body["reply"]
    assert body["model"] == "placeholder"


# 空消息被拒绝
def test_chat_rejects_empty_message() -> None:
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_accepts_history() -> None:
    response = client.post(
        "/chat",
        json={
            "message": "继续",
            "history": [{"role": "user", "content": "你好"}],
        },
    )
    assert response.status_code == 200


def test_chat_rejects_invalid_role() -> None:
    response = client.post(
        "/chat",
        json={"message": "hi", "history": [{"role": "boss", "content": "hello"}]},
    )
    assert response.status_code == 422
