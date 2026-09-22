from fastapi.testclient import TestClient


def test_agent_calls_python_then_returns_final(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
) -> None:
    fake_llm.replies = [
        (
            '{"action":"tool","tool_name":"python_sandbox",'
            '"arguments":{"expression":"(12 + 8) / 2"},"answer":""}'
        ),
        ('{"action":"final","tool_name":"","arguments":{},"answer":"计算结果是 10"}'),
    ]

    response = client.post(
        "/agent",
        headers=authenticated_headers,
        json={"message": "请计算 (12 + 8) / 2"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["answer"] == "计算结果是 10"
    assert fake_llm.call_count == 2
    assert body["tool_calls"][0]["tool_name"] == "python_sandbox"
    assert body["tool_calls"][0]["arguments"] == {
        "expression": "(12 + 8) / 2",
    }
    assert body["tool_calls"][0]["ok"] is True
    assert body["tool_calls"][0]["output"]["value"] == 10.0


def test_agent_rejects_empty_message(
    client: TestClient,
    authenticated_headers: dict[str, str],
) -> None:
    response = client.post(
        "/agent",
        headers=authenticated_headers,
        json={"message": ""},
    )

    assert response.status_code == 422


def test_agent_rejects_too_long_message(
    client: TestClient,
    authenticated_headers: dict[str, str],
) -> None:
    response = client.post(
        "/agent",
        headers=authenticated_headers,
        json={"message": "a" * 2001},
    )

    assert response.status_code == 422


def test_agent_returns_503_when_llm_unavailable(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
) -> None:
    fake_llm.fail = True

    response = client.post(
        "/agent", headers=authenticated_headers, json={"message": "测试模型不可用"}
    )

    assert response.status_code == 503
    assert "模拟模型服务不可用" in response.json()["detail"]


def test_agent_returns_502_for_invalid_llm_json(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
) -> None:
    fake_llm.reply = "这不是合法 JSON"

    response = client.post(
        "/agent",
        headers=authenticated_headers,
        json={"message": "测试模型协议错误"},
    )

    assert response.status_code == 502
    assert "模型返回格式错误" in response.json()["detail"]
