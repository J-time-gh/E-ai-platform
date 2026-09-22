import io

from fastapi.testclient import TestClient


def _auth_headers(
    client: TestClient,
    email: str,
) -> dict[str, str]:
    """注册并登录独立测试用户，返回该用户的 JWT Header。"""
    password = "correct-horse-battery-staple"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
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
    filename: str,
    content: str,
) -> None:
    """用指定用户上传一份文本资料。"""
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


def _create_session(
    client: TestClient,
    headers: dict[str, str],
    title: str = "测试会话",
) -> dict:
    """创建会话并返回会话信息。"""
    response = client.post(
        "/chat/sessions",
        headers=headers,
        json={
            "title": title,
        },
    )
    assert response.status_code == 201

    return response.json()


def test_chat_session_requires_authentication(
    client: TestClient,
) -> None:
    """未登录用户不能创建会话。"""
    response = client.post(
        "/chat/sessions",
        json={
            "title": "未登录会话",
        },
    )

    assert response.status_code == 401


def test_user_can_create_and_list_own_chat_sessions(
    client: TestClient,
) -> None:
    """用户能创建会话，也只能在列表中看到自己的会话。"""
    headers = _auth_headers(
        client,
        "session-owner@example.com",
    )

    created = _create_session(
        client,
        headers,
        title="机器学习讨论",
    )

    assert created["title"] == "机器学习讨论"
    assert created["id"]
    assert created["created_at"]
    assert created["updated_at"]

    response = client.get(
        "/chat/sessions",
        headers=headers,
    )
    assert response.status_code == 200

    sessions = response.json()

    assert len(sessions) == 1
    assert sessions[0]["id"] == created["id"]
    assert sessions[0]["title"] == "机器学习讨论"


def test_chat_persists_user_and_assistant_messages(
    client: TestClient,
    fake_llm,
) -> None:
    """一次成功 Chat 应保存一条 user 消息和一条 assistant 消息。"""
    headers = _auth_headers(
        client,
        "session-chat@example.com",
    )
    session = _create_session(
        client,
        headers,
        title="机器学习问答",
    )

    text = "机器学习是人工智能的一个分支。"
    _upload(
        client,
        headers,
        "ml.txt",
        text,
    )

    chat_response = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": session["id"],
            "message": text,
        },
    )
    assert chat_response.status_code == 200, chat_response.text

    body = chat_response.json()
    assert body["reply"] == fake_llm.reply

    history_response = client.get(
        f"/chat/sessions/{session['id']}/messages",
        headers=headers,
    )
    assert history_response.status_code == 200

    messages = history_response.json()

    assert len(messages) == 2

    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == text

    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == fake_llm.reply


def test_user_cannot_access_another_users_chat_session(
    client: TestClient,
    fake_llm,
) -> None:
    """用户 B 不能读取、删除或使用用户 A 的会话。"""
    user_a_headers = _auth_headers(
        client,
        "session-user-a@example.com",
    )
    user_b_headers = _auth_headers(
        client,
        "session-user-b@example.com",
    )

    session = _create_session(
        client,
        user_a_headers,
        title="用户 A 私有会话",
    )
    session_id = session["id"]

    read_response = client.get(
        f"/chat/sessions/{session_id}/messages",
        headers=user_b_headers,
    )
    assert read_response.status_code == 404

    chat_response = client.post(
        "/chat",
        headers=user_b_headers,
        json={
            "session_id": session_id,
            "message": "尝试读取用户 A 的会话",
        },
    )
    assert chat_response.status_code == 404
    assert fake_llm.call_count == 0

    delete_response = client.delete(
        f"/chat/sessions/{session_id}",
        headers=user_b_headers,
    )
    assert delete_response.status_code == 404


def test_chat_rejects_history_when_session_id_is_provided(
    client: TestClient,
) -> None:
    """会话模式必须使用数据库历史，不能混入前端传入的 history。"""
    headers = _auth_headers(
        client,
        "session-history@example.com",
    )
    session = _create_session(
        client,
        headers,
    )

    response = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": session["id"],
            "message": "你好",
            "history": [
                {
                    "role": "user",
                    "content": "伪造的旧消息",
                },
            ],
        },
    )

    assert response.status_code == 422


def test_user_can_delete_own_session_and_messages(
    client: TestClient,
    fake_llm,
) -> None:
    """删除会话后，关联消息应因数据库 CASCADE 一并删除。"""
    headers = _auth_headers(
        client,
        "session-delete@example.com",
    )
    session = _create_session(
        client,
        headers,
    )

    text = "删除会话前的测试资料"
    _upload(
        client,
        headers,
        "delete.txt",
        text,
    )

    chat_response = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": session["id"],
            "message": text,
        },
    )
    assert chat_response.status_code == 200

    delete_response = client.delete(
        f"/chat/sessions/{session['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    history_response = client.get(
        f"/chat/sessions/{session['id']}/messages",
        headers=headers,
    )
    assert history_response.status_code == 404
