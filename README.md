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
| 检索 | 向量检索 + BM25 + RRF 融合 + CrossEncoder 精排（阶段 4） |
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
├── core/                # 核心配置（settings）
├── api/routes/          # 协议层：health / chat / documents / search
├── schemas/             # 契约层：Pydantic 请求与响应模型
├── services/            # 业务层：检索 / 融合 / 精排 / 入库 / RAG 组装
└── db/                  # 数据层：SQLAlchemy 模型、会话与事务
tests/                   # pytest 自动化测试（72 个）
evals/                   # RAG 检索评测：题库、评测脚本、四种模式对比报告
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

## 开发路线图

- [x] 阶段 0：项目骨架（FastAPI + /health + 测试 + CI）
- [x] 阶段 1：基础 API（/chat、/documents）
- [x] 阶段 2：PostgreSQL + pgvector + Redis（Docker Compose）
- [x] 阶段 3：Production RAG（解析 → Chunk → Embedding → 检索 → 带引用回答）
- [x] 阶段 4：Hybrid Retrieval（BM25 + RRF + CrossEncoder 精排）+ 检索评测
- [ ] 阶段 5：Agent（LangGraph + RAG/SQL/Python 工具）
- [ ] 阶段 6：工程化（JWT、缓存、异步任务、压测）
- [ ] 阶段 7：vLLM 本地推理与性能测试
- [ ] 阶段 8：LLM Gateway（多模型路由/重试/限流/成本统计）
- [ ] 阶段 9：Evaluation & Monitoring（Langfuse/Prometheus + Grafana）

## License

MIT
