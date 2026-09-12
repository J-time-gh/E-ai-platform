# Enterprise AI Platform

> 企业级大模型 AI 应用平台：RAG 知识库问答 · Agent 工具调用 · LLM Gateway 多模型接入
>
> An enterprise-grade LLM application platform featuring RAG, Agents and an LLM gateway.

[![CI](https://github.com/J-time-gh/E-ai-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/J-time-gh/E-ai-platform/actions/workflows/ci.yml)

## 项目简介

面向企业内部的 AI Copilot 系统：

- 上传 PDF / Word / Excel 等资料建立知识库，基于 RAG 进行带引用的问答
- Agent 自动调用 RAG / SQL / Python 等工具完成复杂任务
- LLM Gateway 统一接入 Qwen / DeepSeek 等模型（本地 LM Studio / vLLM / 云端 API）
- 工程化：Docker Compose、pytest、CI、监控与评测

## 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| 配置管理 | pydantic-settings |
| 数据库 | PostgreSQL + pgvector（阶段 2） |
| 缓存 | Redis（阶段 2） |
| 检索 | BM25 + 向量检索 + Reranker（阶段 3-4） |
| 模型服务 | LM Studio / vLLM（OpenAI 兼容接口） |
| Agent | LangGraph（阶段 5） |
| 前端 | Streamlit（阶段 3） |
| 工程化 | Docker、pytest、ruff、GitHub Actions |

## 快速开始

```bash
# 1. 创建虚拟环境
py -3.11 -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖（含开发依赖）
pip install -e ".[dev]"

# 3. 启动开发服务器
uvicorn app.main:app --reload

# 4. 打开接口文档
# http://127.0.0.1:8000/docs
```

## 项目结构

```
app/
├── main.py              # FastAPI 应用入口
├── core/                # 核心配置（settings、日志、安全）
└── api/routes/          # API 路由（health、chat、documents...）
tests/                   # pytest 自动化测试
.github/workflows/       # GitHub Actions CI
```

## 开发路线图

- [x] 阶段 0：项目骨架（FastAPI + /health + 测试 + CI）
- [x] 阶段 1：基础 API（/chat、/documents）
- [ ] 阶段 2：PostgreSQL + pgvector + Redis（Docker Compose）
- [ ] 阶段 3：Production RAG（解析 → Chunk → Embedding → 检索 → 带引用回答）
- [ ] 阶段 4：Hybrid Retrieval（BM25 + 向量 + RRF）+ Reranker + 评测
- [ ] 阶段 5：Agent（LangGraph + RAG/SQL/Python 工具）
- [ ] 阶段 6：工程化（JWT、缓存、异步任务、压测）
- [ ] 阶段 7：vLLM 本地推理与性能测试
- [ ] 阶段 8：LLM Gateway（多模型路由/重试/限流/成本统计）
- [ ] 阶段 9：Evaluation & Monitoring（Langfuse/Prometheus + Grafana）

## License

MIT
