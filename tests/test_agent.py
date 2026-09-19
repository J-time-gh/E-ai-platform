from typing import Any

import pytest

from app.services.agent import AgentProtocolError, AgentService
from app.services.tools.base import ToolError
from app.services.tools.registry import ToolRegistry


class ScriptedLLM:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies

    async def chat(
        self,
        messages,
        model=None,
        response_format=None,
    ) -> str:
        return self.replies.pop(0)


class EchoTool:
    name = "echo"
    description = "返回输入内容"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    }

    def run(self, arguments):
        return {
            "text": arguments["text"],
        }


@pytest.mark.asyncio
async def test_agent_calls_tool_then_returns_final_answer():
    llm = ScriptedLLM(
        [
            ('{"action":"tool","tool_name":"echo","arguments":{"text":"hello"},"answer":""}'),
            ('{"action":"final","tool_name":"","arguments":{},"answer":"工具返回了 hello"}'),
        ],
    )

    registry = ToolRegistry()
    registry.register(EchoTool())

    service = AgentService(
        llm=llm,
        registry=registry,
        max_steps=4,
    )

    result = await service.run("测试工具")

    assert result["answer"] == "工具返回了 hello"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool_name"] == "echo"
    assert result["tool_calls"][0]["ok"] is True


@pytest.mark.asyncio
async def test_agent_rejects_invalid_json():
    llm = ScriptedLLM(["这不是 JSON"])

    registry = ToolRegistry()
    service = AgentService(llm=llm, registry=registry)

    with pytest.raises(AgentProtocolError, match="模型没有返回合法 JSON"):
        await service.run("测试非法输出")


@pytest.mark.asyncio
async def test_agent_rejects_unknown_tool():
    llm = ScriptedLLM(
        [
            ('{"action":"tool","tool_name":"unknown_tool","arguments":{},"answer":""}'),
            ('{"action":"final","tool_name":"","arguments":{},"answer":"工具不可用"}'),
        ],
    )

    registry = ToolRegistry()
    service = AgentService(
        llm=llm,
        registry=registry,
        max_steps=4,
    )

    result = await service.run("测试未知工具")

    assert result["tool_calls"][0]["ok"] is False
    assert "未知工具" in result["tool_calls"][0]["error"]


@pytest.mark.asyncio
async def test_agent_stops_at_max_steps():
    tool_reply = '{"action":"tool","tool_name":"echo","arguments":{"text":"again"},"answer":""}'

    llm = ScriptedLLM(
        [
            tool_reply,
            tool_reply,
        ],
    )

    registry = ToolRegistry()
    registry.register(EchoTool())

    service = AgentService(
        llm=llm,
        registry=registry,
        max_steps=2,
    )

    result = await service.run("测试最大步数")

    assert len(result["steps"]) <= 2
    assert result["answer"] == "Agent 未能在限制步数内完成任务。"


@pytest.mark.asyncio
async def test_agent_records_tool_error():
    llm = ScriptedLLM(
        [
            ('{"action":"tool","tool_name":"failing_tool","arguments":{},"answer":""}'),
            ('{"action":"final","tool_name":"","arguments":{},"answer":"工具执行失败"}'),
        ],
    )

    registry = ToolRegistry()
    registry.register(FailingTool())

    service = AgentService(
        llm=llm,
        registry=registry,
        max_steps=4,
    )

    result = await service.run("测试工具失败")

    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool_name"] == "failing_tool"
    assert result["tool_calls"][0]["ok"] is False
    assert result["tool_calls"][0]["error"] == "模拟工具失败"


class FailingTool:
    name = "failing_tool"
    description = "始终失败"
    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def run(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        raise ToolError("模拟工具失败")
