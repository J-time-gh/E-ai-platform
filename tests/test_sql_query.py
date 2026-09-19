import pytest

from app.services.tools.base import ToolError
from app.services.tools.sql_query import SqlQueryTool


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append(
            {
                "sql": sql,
                "params": params,
            },
        )

        if "SET LOCAL statement_timeout" in sql:
            return FakeResult([])

        return FakeResult(self.rows)


def test_document_count():
    db = FakeSession([{"count": 5}])
    tool = SqlQueryTool(db)

    result = tool.run(
        {
            "query_name": "document_count",
        },
    )

    assert result == {
        "rows": [{"count": 5}],
        "count": 1,
    }

    assert any("SELECT count(*)" in call["sql"] for call in db.calls)


def test_chunks_for_document_requires_document_id():
    db = FakeSession([])
    tool = SqlQueryTool(db)

    with pytest.raises(ToolError, match="document_id"):
        tool.run(
            {
                "query_name": "chunks_for_document",
            },
        )


def test_invalid_query_name_is_rejected():
    db = FakeSession([])
    tool = SqlQueryTool(db)

    with pytest.raises(ToolError, match="参数错误"):
        tool.run(
            {
                "query_name": "delete_all",
            },
        )


def test_chunks_for_document_passes_parameters():
    db = FakeSession(
        [
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "chunk_index": 0,
                "content": "测试内容",
            },
        ],
    )

    tool = SqlQueryTool(db)

    result = tool.run(
        {
            "query_name": "chunks_for_document",
            "document_id": "doc-1",
            "limit": 10,
        },
    )

    assert result["count"] == 1
    assert result["rows"][0]["document_id"] == "doc-1"

    query_call = [
        call
        for call in db.calls
        if "SELECT count(*)" not in call["sql"] and "SET LOCAL" not in call["sql"]
    ][0]

    assert query_call["params"] == {
        "document_id": "doc-1",
        "limit": 10,
    }
