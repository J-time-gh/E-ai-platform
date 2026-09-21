# Enterprise AI Platform

> 企业级 AI 应用后端：RAG 知识库问答 · Agent 工具调用
>
> A backend-first enterprise AI platform featuring RAG and tool-using Agents.

[![CI](https://github.com/J-time-gh/E-ai-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/J-time-gh/E-ai-platform/actions/workflows/ci.yml)

## 项目简介

面向企业内部的 AI Copilot 系统：

- 上传 PDF / Word / Excel / Markdown / TXT 等资料建立知识库，基于 RAG 进行带引用的问答
- Agent 根据问题调用 RAG、受限只读 SQL 或安全数学表达式计算工具
- 模型服务兼容 LM Studio / vLLM 提供的 OpenAI 兼容接口
- 工程化基础：Docker Compose、pytest、Ruff、GitHub Actions 和检索/Agent 评测

> 当前没有正式前端、JWT 认证、用户隔离、会话持久化、真实 Redis 缓存、异步入库、结构化日志、压测、监控或 LLM Gateway。

## 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| 配置管理 | pydantic-settings |
| 数据库 | PostgreSQL + pgvector（阶段 2） |
| 缓存 | Redis 依赖与配置（尚未接入实际缓存） |
| 检索 | 向量检索 + BM25 + RRF 融合 + CrossEncoder 精排（阶段 4） |
| 模型服务 | LM Studio / vLLM（OpenAI 兼容接口） |
| Agent | LangGraph；RAG、受限 SQL 与安全数学表达式工具（阶段 5） |
| 前端 | 暂无正式前端 |
| 工程化 | Docker Compose、pytest、Ruff、GitHub Actions |

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
├── core/                # 核心配置（settings）
├── api/routes/          # 协议层：health / chat / documents / search / agent
├── schemas/             # 契约层：Pydantic 请求与响应模型
├── services/            # 业务层：检索 / 融合 / 精排 / 入库 / RAG / Agent
└── db/                  # 数据层：SQLAlchemy 模型、会话与事务
tests/                   # pytest 自动化测试（以实际测试输出为准）
evals/                   # RAG 与 Agent 评测题库、脚本及结果（结果可能含敏感内容）
.github/workflows/       # GitHub Actions CI
```

## 检索策略对比（阶段 4：BM25 → RRF → Reranker）

同一语料（3 篇 / 53 chunk）、同一题库（20 条：15 可答 + 5 库外）、同一生成模型（ornith-1.0-9b）：

| 检索策略 | hit@5 | hit@1 | MRR | 拒答正确率 | 平均延迟 |
|---|---|---|---|---|---|
| 纯向量（基线） | 86.7% | 60.0% | 0.722 | 100% | 31.32s\* |
| BM25 | 93.3% | 80.0% | 0.867 | 80% | 28.72s\* |
| RRF 混合（hybrid） | 93.3% | 80.0% | 0.850 | 60% | 33.26s\* |
| **CrossEncoder 精排（hybrid_rerank）** | **100.0%** | **93.3%** | **0.947** | **100.0%** | 21.25s |

\* 前三行为并发测量（多个评测进程共用同一个 LLM 服务，延迟被排队抬高），
hybrid_rerank 为串行测量，延迟不可直接跨行比较。

**四个数字背后的三段故事**：

1. **BM25 补上了向量检索的字面匹配短板**（hit@1 60% → 80%）：向量漏掉的「科学实验」「拜物教」被关键词精确命中。同时引入检索层门控，库外请求延迟从 3~6s 降到 0.04s（不再调用大模型）。

2. **RRF 融合没有赢，但给出了关键诊断**：hybrid 每一项都 ≤ 单路 BM25。机制是 RRF 的"双票必胜"——`k=60`、每路召回 20 条时，双票的最低分 `1/80 + 1/80 = 0.025` 恒大于单票的最高分 `1/61 = 0.0164`，于是"只被一路命中"的正确答案会被挤出前 5。同时实测出 **两路 top-20 的并集召回 = 15/15 = 100%**：**召回已经满分，瓶颈在排序**。这个结论直接决定了下一步该用 Reranker，而不是继续调 RRF 参数。

3. **CrossEncoder 精排同时解决了排序与门控**：它把「问题 ↔ 候选块」拼在一起逐条精算相关性，把向量独有命中的题目救回前 5（hit@5 100%）；它输出的**统一量纲分数**又给整条管线提供了第一把"可比较的门控尺子"，拒答正确率从 60% 回到 100%。

**已知边界（如实记录）**：

- 「《实践论》批判了哪两种错误倾向？」两轮评测都排第 5 —— 它的向量分数天然挤在一起（前 5 名差距 < 0.005），属于该语料的真实检索难度边界。
- 生成层存在采样噪声：同一道题在两轮中可能一次答出、一次拒答（`temperature=0.2` 仍有随机性）。**多轮评测中检索层指标（hit@5 / hit@1 / MRR）完全可复现，波动只出现在引用率与覆盖率。**

### 复现评测

```powershell
# 前置：Docker 起着（PostgreSQL）、uvicorn 跑着、LM Studio 已加载模型
.venv\Scripts\python.exe evals\run_eval.py --mode hybrid_rerank   # 单轮约 8 分钟
```

四种模式分别产出 `evals/report-{mode}.md`（`vector` / `bm25` / `hybrid` / `hybrid_rerank`）。
**评测必须串行执行**——多个评测进程共用同一个 LLM 服务会让延迟指标失真。

### Agent 工具调用（阶段 5）

`POST /agent` 使用 LangGraph 驱动规划与工具执行循环；默认最多调用 4 次工具。模型仅决定调用哪个已注册工具、传递什么参数或直接回答，流程节点跳转由 LangGraph 控制。

可用工具及边界：

- `rag_search`：检索企业知识库，涉及企业资料、制度、流程、产品文档或上传文件时必须先调用。无结果时必须说明资料不足，不得编造事实。
- `sql_query`：仅支持 `document_count` 和 `chunks_for_document` 两个只读模板，使用参数绑定、结果上限和超时控制；不是任意 SQL 执行器。
- `python_sandbox`：仅计算经过 AST 白名单校验的数学表达式，例如 `sqrt(16)` 或 `pi * 2`；不支持导入、文件、网络、系统命令、`eval`、`exec` 或任意 Python。

Agent 应直接拒绝文件读取、网络请求、系统命令和其他危险操作；闲聊、常识问题及已有工具结果的总结不应调用工具。

#### 当前评测状态

最近一次运行时题库共 20 题，结果为 **19/20（95%）**。唯一未通过的是 `multi-step-rag-then-python`：当时知识库中没有「单日交通报销上限」资料，`rag_search` 正确返回空结果，Agent 因而安全停止、没有继续编造金额或计算。

**方案 A：暂不补充固定多步评测语料。** 因此该项不阻塞当前 Agent 核心能力，但多步端到端能力仍**未验收**，不得将 19/20 表述为多步能力已达标。接手后须重新运行以下检查，并以实际输出更新结论：

```powershell
.venv\Scripts\python.exe -m pytest -q tests\test_agent.py tests\test_agent_api.py --tb=line
.venv\Scripts\python.exe -m ruff format --check app tests scripts
.venv\Scripts\python.exe -m ruff check app tests scripts --no-cache
.venv\Scripts\python.exe -m pytest -q --tb=line

# 需要 PostgreSQL、后端与 LM Studio 正常运行
.venv\Scripts\python.exe scripts\evaluate_agent.py
```

## 开发路线图

- [x] 阶段 0：项目骨架（FastAPI + /health + 测试 + CI）
- [x] 阶段 1：基础 API（/chat、/documents）
- [x] 阶段 2：PostgreSQL + pgvector + Redis（Docker Compose）
- [x] 阶段 3：Production RAG（解析 → Chunk → Embedding → 检索 → 带引用回答）
- [x] 阶段 4：Hybrid Retrieval（BM25 + RRF + CrossEncoder 精排）+ 检索评测
- [x] 阶段 5：Agent 核心能力（LangGraph + RAG / 受限 SQL / 安全数学表达式工具；多步端到端验收暂缓）
- [ ] 阶段 6：安全与工程化（JWT、用户隔离、缓存、异步任务、压测）
- [ ] 阶段 7：vLLM 本地推理与性能测试
- [ ] 阶段 8：LLM Gateway（多模型路由/重试/限流/成本统计）
- [ ] 阶段 9：Evaluation & Monitoring（Langfuse/Prometheus + Grafana）

## License

MIT
