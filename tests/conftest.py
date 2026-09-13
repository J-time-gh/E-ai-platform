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

# 测试的文件落盘目录（与生产目录隔离）
TEST_UPLOAD_DIR = Path("data/test_uploads")
settings.upload_dir = str(TEST_UPLOAD_DIR)


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


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session", autouse=True)
def _clean_test_uploads() -> Generator[None, None, None]:
    shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
    yield
    shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
