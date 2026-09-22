import io

from fastapi.testclient import TestClient

from app.services.rag import NO_CONTEXT_REPLY


def _auth_headers(
    client: TestClient,
    email: str,
) -> dict[str, str]:
    """注册并登录一个测试用户，返回 Bearer Token Header。"""
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
) -> str:
    """以指定用户身份上传一份文档。"""
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
    client: TestClient,
    headers: dict[str, str],
    query: str,
    mode: str = "vector",
) -> list[dict]:
    """以指定用户身份调用 Search。"""
    response = client.post(
        "/search",
        headers=headers,
        json={
            "query": query,
            "top_k": 5,
            "mode": mode,
        },
    )
    assert response.status_code == 200

    return response.json()


def test_vector_search_isolated_by_user(
    client: TestClient,
) -> None:
    """用户 B 不能通过向量检索读取用户 A 的私有资料。"""
    user_a_headers = _auth_headers(client, "vector-user-a@example.com")
    user_b_headers = _auth_headers(client, "vector-user-b@example.com")

    private_text = "用户A独有的向量检索机密关键词"
    _upload(
        client,
        user_a_headers,
        "vector-private.txt",
        private_text,
    )

    user_a_results = _search(
        client,
        user_a_headers,
        private_text,
    )
    assert user_a_results
    assert user_a_results[0]["content"] == private_text

    user_b_results = _search(
        client,
        user_b_headers,
        private_text,
    )
    assert user_b_results == []


def test_bm25_search_isolated_by_user(
    client: TestClient,
) -> None:
    """用户 B 不能通过 BM25 索引读取用户 A 的私有资料。"""
    user_a_headers = _auth_headers(client, "bm25-user-a@example.com")
    user_b_headers = _auth_headers(client, "bm25-user-b@example.com")

    private_text = "用户A独有的BM25关键词量子报销"
    _upload(
        client,
        user_a_headers,
        "bm25-private.txt",
        private_text,
    )

    user_a_results = _search(
        client,
        user_a_headers,
        "量子报销",
        mode="bm25",
    )
    assert user_a_results
    assert user_a_results[0]["content"] == private_text

    user_b_results = _search(
        client,
        user_b_headers,
        "量子报销",
        mode="bm25",
    )
    assert user_b_results == []


def test_chat_does_not_use_another_users_document(
    client: TestClient,
    fake_llm,
) -> None:
    """用户 B 的 Chat 不得将用户 A 的资料组装进 Prompt。"""
    user_a_headers = _auth_headers(client, "chat-user-a@example.com")
    user_b_headers = _auth_headers(client, "chat-user-b@example.com")

    private_text = "用户A私有的Chat机密资料"
    _upload(
        client,
        user_a_headers,
        "chat-private.txt",
        private_text,
    )

    response = client.post(
        "/chat",
        headers=user_b_headers,
        json={
            "message": private_text,
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["reply"] == NO_CONTEXT_REPLY
    assert body["sources"] == []
    assert fake_llm.call_count == 0


def test_agent_rag_search_isolated_by_user(
    client: TestClient,
    fake_llm,
) -> None:
    """用户 B 的 Agent rag_search 不得读取用户 A 的资料。"""
    user_a_headers = _auth_headers(client, "agent-user-a@example.com")
    user_b_headers = _auth_headers(client, "agent-user-b@example.com")

    private_text = "用户A私有的Agent检索资料"
    _upload(
        client,
        user_a_headers,
        "agent-private.txt",
        private_text,
    )

    fake_llm.replies = [
        (
            '{"action":"tool","tool_name":"rag_search",'
            f'"arguments":{{"query":"{private_text}","top_k":5}},'
            '"answer":""}'
        ),
        ('{"action":"final","tool_name":"","arguments":{},"answer":"没有检索到资料"}'),
    ]

    response = client.post(
        "/agent",
        headers=user_b_headers,
        json={
            "message": f"请检索：{private_text}",
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["tool_calls"][0]["tool_name"] == "rag_search"
    assert body["tool_calls"][0]["ok"] is True
    assert body["tool_calls"][0]["output"]["count"] == 0
