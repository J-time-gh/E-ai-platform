import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.services.llm import LLMClient
from app.services.tools.base import ToolError
from app.services.tools.registry import ToolRegistry


class AgentProtocolError(Exception):
    """LLM 没有返回合法的 Agent 决策。"""


# Agent 状态
class AgentState(TypedDict, total=False):
    question: str
    model: str | None
    decision: dict[str, Any]
    # 工具返回结果，供下一轮规划
    observations: list[dict[str, Any]]
    # 人类可读的执行轨迹
    steps: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    answer: str
    error: str | None


class AgentService:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        max_steps: int = 4,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._max_steps = max_steps
        self._graph = self._build_graph()

    # 构建工作流
    def _build_graph(self):
        graph = StateGraph(AgentState)

        graph.add_node("plan", self._plan)
        graph.add_node("execute", self._execute)

        graph.set_entry_point("plan")

        graph.add_conditional_edges(
            "plan",
            self._after_plan,
            {
                "execute": "execute",
                "finish": END,
            },
        )

        graph.add_conditional_edges(
            "execute",
            self._after_execute,
            {
                "plan": "plan",
                "finish": END,
            },
        )

        return graph.compile()

    async def _plan(self, state: AgentState) -> dict[str, Any]:
        # 复制已有步骤
        steps = list(state.get("steps", []))
        # 检查最大步数
        if len(steps) >= self._max_steps:
            return {
                "answer": "已达到最大工具调用步数，无法安全完成任务。",
                "decision": {
                    "action": "final",
                    "answer": "已达到最大工具调用步数，无法安全完成任务。",
                },
            }
        # 获取工具列表（工具名称、描述、参数传给模型。）
        tools = json.dumps(
            self._registry.definitions(),
            ensure_ascii=False,
        )
        # 获取过去的观察结果
        observations = json.dumps(
            state.get("observations", []),
            ensure_ascii=False,
        )

        system_prompt = (
            "你是企业 AI Agent 的工具规划器。\n"
            "你只能从给出的工具中选择。\n"
            "必须只返回一个 JSON 对象，不要返回 Markdown。\n"
            "调用工具时返回："
            '{"action":"tool","tool_name":"工具名","arguments":{...}}\n'
            "直接回答时返回："
            '{"action":"final","answer":"最终回答"}\n'
            "不要虚构工具，不要执行危险操作。\n\n"
            f"可用工具：{tools}"
        )

        user_prompt = f"用户问题：{state['question']}\n\n之前的工具观察结果：{observations}"
        # 调用 LM Studio
        raw = await self._llm.chat(
            [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            model=state.get("model"),
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_decision",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["tool", "final"],
                            },
                            "tool_name": {
                                "type": "string",
                            },
                            "arguments": {
                                "type": "object",
                            },
                            "answer": {
                                "type": "string",
                            },
                        },
                        "required": [
                            "action",
                            "tool_name",
                            "arguments",
                            "answer",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
        )
        # 解析模型决策
        decision = self._parse_decision(raw)
        # 如果模型决定直接回答
        if decision["action"] == "final":
            # 记录最终回答的步骤
            steps.append(
                {
                    "step": len(steps) + 1,
                    "action": "final",
                    "tool_name": None,
                    "summary": "生成最终回答",
                }
            )
            return {
                "decision": decision,
                "answer": decision["answer"],
                "steps": steps,
            }
        # 如果模型决定调用工具
        return {"decision": decision}

    # 执行工具
    def _execute(self, state: AgentState) -> dict[str, Any]:
        decision = state["decision"]
        tool_name = decision["tool_name"]
        arguments = decision["arguments"]

        step_number = len(state.get("steps", [])) + 1
        tool_calls = list(state.get("tool_calls", []))
        observations = list(state.get("observations", []))
        steps = list(state.get("steps", []))

        try:
            # 获取工具并执行
            tool = self._registry.get(tool_name)
            output = tool.run(arguments)
            # 保存详细数据（成功记录）
            tool_call = {
                "step": step_number,
                "tool_name": tool_name,
                "arguments": arguments,
                "ok": True,
                "output": output,
                "error": None,
            }

            observation = {
                "tool_name": tool_name,
                "ok": True,
                "output": output,
            }

            summary = f"成功调用工具：{tool_name}"

        except ToolError as exc:
            # 保存详细数据
            tool_call = {
                "step": step_number,
                "tool_name": tool_name,
                "arguments": arguments,
                "ok": False,
                "output": None,
                "error": str(exc),
            }

            observation = {
                # 保存给下一轮规划使用的结果
                "tool_name": tool_name,
                "ok": False,
                "error": str(exc),
            }

            summary = f"工具被拒绝或执行失败：{tool_name}"

        tool_calls.append(tool_call)
        observations.append(observation)
        # steps 保存给前端展示的简化轨迹
        steps.append(
            {
                "step": step_number,
                "action": "tool",
                "tool_name": tool_name,
                "summary": summary,
            }
        )

        return {
            "tool_calls": tool_calls,
            "observations": observations,
            "steps": steps,
        }

    # 路由判断
    @staticmethod
    def _after_plan(state: AgentState) -> str:
        if state.get("decision", {}).get("action") == "tool":
            return "execute"
        return "finish"

    def _after_execute(self, state: AgentState) -> str:
        if len(state.get("steps", [])) >= self._max_steps:
            return "finish"
        return "plan"

    @staticmethod
    def _parse_decision(raw: str) -> dict[str, Any]:
        text = raw.strip()

        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
            if text.startswith("json"):
                text = text[4:].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentProtocolError("模型没有返回合法 JSON") from exc

        if not isinstance(data, dict):
            raise AgentProtocolError("Agent 决策必须是 JSON 对象")

        action = data.get("action")

        if action == "final":
            answer = data.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise AgentProtocolError("最终回答不能为空")
            return {
                "action": "final",
                "answer": answer,
            }

        if action == "tool":
            tool_name = data.get("tool_name")
            arguments = data.get("arguments", {})

            if not isinstance(tool_name, str):
                raise AgentProtocolError("tool_name 必须是字符串")
            if not isinstance(arguments, dict):
                raise AgentProtocolError("arguments 必须是对象")

            return {
                "action": "tool",
                "tool_name": tool_name,
                "arguments": arguments,
            }

        raise AgentProtocolError(f"未知 action：{action}")

    # Agent 运行总入口
    async def run(
        self,
        question: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        initial_state: AgentState = {
            "question": question,
            "model": model,
            "observations": [],
            "steps": [],
            "tool_calls": [],
            "answer": "",
            "error": None,
        }
        #  启动 LangGraph
        result = await self._graph.ainvoke(initial_state)

        return {
            "answer": result.get("answer") or "Agent 未能在限制步数内完成任务。",
            "steps": result.get("steps", []),
            "tool_calls": result.get("tool_calls", []),
        }
