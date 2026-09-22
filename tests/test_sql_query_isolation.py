import io

from fastapi.testclient import TestClient


def _auth_headers(
    client: TestClient,
    email: str,
) -> dict[str, str]:
    """注册并登录一个独立测试用户，返回该用户的 JWT Header。"""
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
    """以指定用户身份上传文档，返回新文档的 document_id。"""
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


def test_agent_sql_query_cannot_read_another_users_chunks(
    client: TestClient,
    fake_llm,
) -> None:
    user_a_headers = _auth_headers(client, "sql-user-a@example.com")
    user_b_headers = _auth_headers(client, "sql-user-b@example.com")

    document_id = _upload(
        client,
        user_a_headers,
        "private.txt",
        "用户A的SQL私有资料",
    )

    fake_llm.replies = [
        (
            '{"action":"tool","tool_name":"sql_query",'
            '"arguments":{'
            '"query_name":"chunks_for_document",'
            f'"document_id":"{document_id}",'
            '"limit":20'
            '},"answer":""}'
        ),
        ('{"action":"final","tool_name":"","arguments":{},"answer":"没有权限读取该文档"}'),
    ]

    response = client.post(
        "/agent",
        headers=user_b_headers,
        json={
            "message": "读取这份文档的文本块",
        },
    )

    assert response.status_code == 200

    body = response.json()
    output = body["tool_calls"][0]["output"]

    assert body["tool_calls"][0]["tool_name"] == "sql_query"
    assert body["tool_calls"][0]["ok"] is True
    assert output["rows"] == []
    assert output["count"] == 0
