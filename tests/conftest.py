import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  导入以注册所有模型
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.embedding import FakeEmbedder, get_embedder
from app.services.llm import LLMUnavailable, get_llm_client

# 测试的文件落盘目录（与生产目录隔离）
TEST_UPLOAD_DIR = Path("data/test_uploads")
settings.upload_dir = str(TEST_UPLOAD_DIR)


class FakeLLMClient:
    """LLM 测试替身：不联网，记录收到的 messages，返回固定回答。"""

    def __init__(self, reply: str = "这是模拟回答，依据资料 [1]。", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.call_count = 0
        self.last_messages: list[dict[str, str]] = []
        self.models: list[str | None] = []

    async def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        self.call_count += 1
        self.last_messages = messages
        self.models.append(model)
        if self.fail:
            raise LLMUnavailable("模拟模型服务不可用")
        return self.reply


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    """测试里同时要 client 和 fake_llm 时，拿到的是同一个实例（见下面的依赖注入）。"""
    return FakeLLMClient()


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    test_engine = create_engine(settings.test_database_url)
    with test_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# 第 71 行，client fixture 签名带上 fake_llm，并加一行 override：
@pytest.fixture
def client(db_session: Session, fake_llm: FakeLLMClient) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_llm_client] = lambda: fake_llm  # ← 补这行

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session", autouse=True)
def _clean_test_uploads() -> Generator[None, None, None]:
    shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
    yield
    shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
