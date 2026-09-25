"""RAG 对话接口测试：LLM 走 FakeLLMClient，全程不发真实网络请求。"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.rag import NO_CONTEXT_REPLY


# fake_llm 故意不写类型注解：它由 conftest 提供，跨文件导入 conftest 更脆
def test_chat_returns_llm_reply_with_sources(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
    upload_ready_document,
) -> None:
    text = "机器学习是人工智能的一个分支。"
    upload_ready_document(authenticated_headers, "ml.txt", text)

    # 问句必须与入库文本完全一致：FakeEmbedder 是哈希向量，无语义
    body = client.post(
        "/chat",
        headers=authenticated_headers,
        json={"message": text},
    ).json()

    assert body["reply"] == fake_llm.reply
    assert body["model"] == settings.llm_model
    assert body["sources"][0]["filename"] == "ml.txt"
    assert body["sources"][0]["score"] > 0.99  # 同一文本 → 距离≈0
    # ChatResponse 需要保留 SearchResult 的展示高亮元数据，供前端来源抽屉使用。
    assert isinstance(body["sources"][0]["highlight_terms"], list)
    assert body["sources"][0]["highlight_terms"]


def test_chat_prompt_contains_retrieved_chunk(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
    upload_ready_document,
) -> None:
    upload_ready_document(
        authenticated_headers,
        "ml.txt",
        "机器学习是人工智能的一个分支。",
    )

    client.post(
        "/chat",
        headers=authenticated_headers,
        json={"message": "机器学习是什么？"},
    )

    messages = fake_llm.last_messages

    assert messages[0]["role"] == "system"
    assert "只能依据" in messages[0]["content"]
    assert "机器学习是人工智能的一个分支。" in messages[-1]["content"]
    assert "[1]" in messages[-1]["content"]  # 资料带编号


def test_chat_inserts_history_between_system_and_question(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
    upload_ready_document,
) -> None:
    upload_ready_document(
        authenticated_headers,
        "ml.txt",
        "机器学习是人工智能的一个分支。",
    )

    client.post(
        "/chat",
        headers=authenticated_headers,
        json={"message": "继续说说", "history": [{"role": "user", "content": "上一个问题"}]},
    )

    messages = fake_llm.last_messages

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert messages[1]["content"] == "上一个问题"


def test_chat_without_documents_skips_llm(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
) -> None:
    body = client.post(
        "/chat",
        headers=authenticated_headers,
        json={"message": "知识库里有什么？"},
    ).json()

    assert body["reply"] == NO_CONTEXT_REPLY
    assert body["sources"] == []
    assert fake_llm.call_count == 0  # 关键：没调模型


def test_chat_returns_503_when_llm_unavailable(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
    upload_ready_document,
) -> None:
    upload_ready_document(
        authenticated_headers,
        "ml.txt",
        "机器学习是人工智能的一个分支。",
    )
    fake_llm.fail = True

    response = client.post(
        "/chat",
        headers=authenticated_headers,
        json={"message": "机器学习是什么？"},
    )

    assert response.status_code == 503


def test_chat_accepts_model_override(
    client: TestClient,
    fake_llm,
    authenticated_headers: dict[str, str],
    upload_ready_document,
) -> None:
    upload_ready_document(
        authenticated_headers,
        "ml.txt",
        "机器学习是人工智能的一个分支。",
    )

    body = client.post(
        "/chat",
        headers=authenticated_headers,
        json={"message": "机器学习是什么？", "model": "qwen2.5-14b-instruct"},
    ).json()

    assert fake_llm.models[-1] == "qwen2.5-14b-instruct"
    assert body["model"] == "qwen2.5-14b-instruct"


def test_chat_rejects_empty_message(
    client: TestClient,
    authenticated_headers: dict[str, str],
) -> None:
    assert (
        client.post("/chat", headers=authenticated_headers, json={"message": ""}).status_code == 422
    )


def test_chat_rejects_invalid_role(
    client: TestClient,
    authenticated_headers: dict[str, str],
) -> None:
    payload = {"message": "hi", "history": [{"role": "boss", "content": "hello"}]}
    assert client.post("/chat", headers=authenticated_headers, json=payload).status_code == 422


def test_chat_rejects_top_k_out_of_range(
    client: TestClient,
    authenticated_headers: dict[str, str],
) -> None:
    assert (
        client.post(
            "/chat",
            headers=authenticated_headers,
            json={"message": "hi", "top_k": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/chat",
            headers=authenticated_headers,
            json={"message": "hi", "top_k": 100},
        ).status_code
        == 422
    )
