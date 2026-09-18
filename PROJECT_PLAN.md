# E-ai-platform 项目计划书（交接文档）

> 更新于 2026-09-18 · 当前版本 **v0.4.0**（阶段 0–4 已完成）
>
> 本文档面向"接手这个项目的人"。读完应该能回答四个问题：
> ① 这个项目要做什么 ② 已经做到哪一步 ③ 下一步做什么 ④ 有哪些坑和约定必须遵守。

---

## 0. 速览

| 项目 | 状态 |
|---|---|
| 当前版本 | `v0.4.0`（阶段 4 完成） |
| 代码规模 | 13 个 service 模块、4 个路由、3 组 schema、2 个 Alembic 迁移 |
| 测试 | **72 passed**（9 个测试文件） |
| 静态检查 | `ruff format` + `ruff check` 全绿 |
| 检索质量 | **hit@5 100% / hit@1 93.3% / MRR 0.947 / 拒答正确率 100%** |
| 下一个里程碑 | `v0.5.0` — 阶段 5：Agent 工具调用 |

---

## 1. 这个项目是什么

**一句话**：面向企业内部的 AI Copilot 系统——上传资料建立知识库，用 RAG 做带引用的问答，用 Agent 自动调用工具，用 LLM Gateway 统一管理模型。

### 1.1 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| 配置管理 | pydantic-settings（`.env` 驱动，字段即环境变量名） |
| 数据库 | PostgreSQL 16 + pgvector（HNSW 索引） |
| 缓存 | Redis 5 |
| ORM / 迁移 | SQLAlchemy 2.0 + Alembic |
| 检索 | 向量检索（bge-m3）+ BM25（jieba + rank_bm25）+ RRF 融合 + CrossEncoder 精排 |
| 模型服务 | LM Studio / vLLM（OpenAI 兼容接口） |
| 工程化 | Docker Compose、pytest、ruff、GitHub Actions |

### 1.2 架构分层与依赖方向

```
请求
 ↓
app/api/routes/    协议层：只做参数校验与编排，不写业务逻辑
 ↓
app/schemas/       契约层：Pydantic 请求/响应模型（Literal 卡住枚举值）
 ↓
app/services/      业务层：检索 / 融合 / 精排 / 入库 / RAG 组装 / LLM 调用
 ↓
app/db/            数据层：SQLAlchemy 模型 + 会话与事务（*_store.py 是 repository）
```

**铁律：依赖只能自上而下**。`services` 不能 import `routes`；`fusion.py` 不认识数据库、不认识模型，只认 `list[SearchResult]`。

### 1.3 三个"可替换接缝"（本项目最重要的设计模式）

每个外部依赖都被抽象成 **Protocol + 真实实现 + 测试替身 + 单例工厂 + 依赖别名**：

| 能力 | 契约 | 真实实现 | 测试替身 | 依赖别名 |
|---|---|---|---|---|
| 向量化 | `Embedder` | `BgeM3Embedder` | `FakeEmbedder` | `EmbedderDep` |
| 大模型 | `LLMClient` | `LmStudioClient` | `FakeLLMClient` | `LLMClientDep` |
| 精排 | `Reranker` | `CrossEncoderReranker` | `FakeReranker` | `RerankerDep` |

**收益**：CI 不需要 GPU、不需要模型、不需要网络；72 个测试里大部分 3 秒内跑完。**新增任何外部依赖都必须照这个模式做。**

---

## 2. 已完成的部分（阶段 0–4）

### 阶段 0：项目骨架 ✅ `v0.1.0`

- FastAPI 应用 + `/health` + `/` 端点
- `pyproject.toml`（依赖分组 `dev` / `ml`）、ruff 配置、pytest 配置
- GitHub Actions CI
- `.env` / `.env.example` 配置体系

### 阶段 1：基础 API ✅

- `POST /documents/upload`、`GET /documents`、`GET /documents/{id}`、`DELETE /documents/{id}`
- 文件格式白名单（`.pdf/.docx/.doc/.txt/.md/.xlsx`）、20MB 大小限制、不支持类型返回 415
- 失败回滚：入库出错时同时清理数据库记录和落盘文件

### 阶段 2：数据与基础设施 ✅ `v0.2.0`

- Docker Compose 拉起 PostgreSQL（pgvector 镜像）+ Redis
- `documents` / `chunks` 两张表 + 2 个 Alembic 迁移
- `chunks.embedding` 为 `vector(1024)`（绑定 bge-m3 维度）+ HNSW 索引 `vector_cosine_ops`
- 生产库与测试库分离（`e_ai_database` / `e_ai_database_test`）

### 阶段 3：Production RAG ✅ `v0.3.0`

完整链路：**解析 → 切块 → 向量化 → 入库 → 检索 → 带引用回答**

- 文档解析器（PDF / DOCX / DOC / XLSX / Markdown / TXT），`app/services/parsers/`
- 切块：按句子边界切分 + 块间重叠
- 检索：pgvector 余弦距离 `<=>`，`score = 1 - distance`
- RAG 组装：`rag.build_messages()` 把检索结果编号成【资料】+ system 约束"只能依据资料回答"
- `POST /chat`：检索 → 组装提示词 → 模型带引用回答；`LLMUnavailable` → 503
- **评测体系建立**：`evals/questions.jsonl`（20 题：15 可答 + 5 库外）+ `evals/run_eval.py`

### 阶段 4：混合检索 + 精排 ✅ `v0.4.0`

这一阶段拆成三小节，**中间有一次失败的实验，是整个项目最有价值的记录**。

#### 4.1 BM25 关键词检索 + 检索层门控

交付：`app/services/bm25.py`（jieba 分词 + rank_bm25 + 进程内索引）、`mode` 参数化、`min_vector_score` 门控。

| 指标 | 向量（基线） | BM25 |
|---|---|---|
| hit@1 | 60.0% | **86.7%** |
| 拒答 | 100% | 60% |

- **门控收益**：库外问题延迟从 3~6s 降到 **0.04s**（不再调用大模型），拒答率 40% → 100%
- 关键修复：不能用 `score > 0` 过滤（rank_bm25 的 IDF 在极端情况下会算出 0 或负数），改用**分词交集**判断

#### 4.2 RRF 融合（hybrid）—— ❌ 失败的实验

交付：`app/services/fusion.py`（`rrf_fuse`，`k=60`）、`hybrid` 模式、BM25 停用词表。

**结果：hybrid 每一项都 ≤ 单路 BM25（MRR 0.850 < 0.867，拒答 60% < 80%）。**

但这一轮产出了两个**决定后续方向**的诊断：

1. **RRF 的"双票必胜"**：`k=60`、每路召 20 条时，双票最低分 `1/80+1/80 = 0.025` 恒大于单票最高分 `1/61 = 0.0164`。于是"只被一路命中"的正确答案会被挤出前 5（实测 Q4 从第 3 名出局）。**加权和调 k 都救不了。**
2. **RRF 的"或"短路**：门控只作用于向量腿，`if not results` 只在两路都空时才拒答 → BM25 腿的泛词假命中直接绕过门控 → 拒答率崩到 60%。

**最关键的一条实测数据**：两路 top-20 的**并集召回 = 15/15 = 100%**。

> **结论：召回已经满分，瓶颈在"从 40 条里挑 5 条"，也就是排序。**
> 这个结论直接决定了 4.3 该用 Reranker，而不是继续调 RRF 参数。

#### 4.3 CrossEncoder 精排（hybrid_rerank）✅

交付：`app/services/reranker.py`（懒加载 CrossEncoder，`BAAI/bge-reranker-base`）、`hybrid_rerank` 模式、`fusion.merge_candidates`、`min_rerank_score` 统一门控。

- **精排替代 RRF 做排序**：RRF 降级为"只去重合并"（`merge_candidates`），排序交给 CrossEncoder
- **统一量纲的分数**：精排分是 0~1 的概率，对所有检索模式都可比 → 整条管线第一次有了"统一的门控尺子"
- **阈值用数据标定**：实测可答题 top1 分数 0.32~1.00、库外题 0.00~0.01，中间有 30 倍空档 → 取 `MIN_RERANK_SCORE=0.05`

#### 阶段 4 完整数据对比

| 检索策略 | hit@5 | hit@1 | MRR | 拒答正确率 | 平均延迟 |
|---|---|---|---|---|---|
| 纯向量（基线） | 86.7% | 60.0% | 0.722 | 100% | 31.32s\* |
| BM25 | 93.3% | 80.0% | 0.867 | 80% | 28.72s\* |
| RRF 混合（hybrid） | 93.3% | 80.0% | 0.850 | 60% | 33.26s\* |
| **CrossEncoder 精排** | **100.0%** | **93.3%** | **0.947** | **100.0%** | 21.25s |

\* 前三行为并发测量（多个评测进程共用同一个 LLM 服务，延迟被排队抬高），不可直接比较。

---

## 3. 当前系统的能力清单

### 3.1 API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/` | 根端点 |
| POST | `/documents/upload` | 上传文档并入库（解析 → 切块 → 向量化） |
| GET | `/documents` | 列出所有文档 |
| GET | `/documents/{id}` | 查询单个文档 |
| DELETE | `/documents/{id}` | 删除文档（级联删 chunks + 落盘文件） |
| POST | `/search` | 纯检索（**不门控**，用于评测检索质量） |
| POST | `/chat` | RAG 问答（**门控**，检索为空则直接拒答） |

### 3.2 四种检索模式（`mode` 参数）

| mode | 流程 | 用途 |
|---|---|---|
| `vector`（默认） | 向量腿 top_k | 语义检索基线 |
| `bm25` | 关键词腿 top_k | 不需要 GPU 的降级方案 |
| `hybrid` | 两路各 20 条 → RRF 融合 → top_k | 保留（作为对照与教学案例） |
| `hybrid_rerank` | 两路各 20 条 → 去重合并 → CrossEncoder 精排 → top_k | **当前最优** |

### 3.3 评测体系

- `evals/questions.jsonl`：20 题（15 可答 + 5 库外），每题带 `must_hit` 关键词或 `answerable: false`
- `evals/run_eval.py`：`--mode` / `--limit` 参数，预热排除模型加载耗时
- 8 个指标：hit@5 / hit@1 / MRR / 引用标注率 / 关键词覆盖率 / 拒答正确率 / 平均延迟 / P95
- 每轮产出 `evals/report-{mode}.md`

### 3.4 Git 历史

```
127619b  docs: record phase 4.3 reranking results          ← v0.4.0
e08ad26  feat: add cross-encoder reranking for hybrid retrieval
d43645a  docs: record phase 4.2 retrieval comparison
c28c120  feat: add RRF hybrid retrieval with pre-fusion score gating
5e0a293  docs: record phase 4.1 retrieval comparison
0ef8114  feat: add BM25 keyword retrieval and retrieval score gate
02af1f4  docs: mark phase 3 complete with evaluation baseline   ← v0.3.0
```

**提交约定**：功能一笔 `feat:`、文档/评测一笔 `docs:`，与既有历史保持一致。

---

## 4. 接下来的计划（阶段 5–9）

### 阶段 5：Agent 工具调用 → `v0.5.0` ★下一个里程碑

**目标**：让模型自己决定"这个问题该查知识库、查数据库、还是跑一段 Python"。

**要交付的模块**：

| 模块 | 说明 |
|---|---|
| `app/services/tools/` | 工具注册表：`Tool` Protocol（`name` / `description` / `run(args)`）+ 注册与查找 |
| `rag_search` 工具 | 直接复用现有 `search_with_mode(..., mode="hybrid_rerank")` |
| `sql_query` 工具 | **只读** SQL（白名单表 + 禁止 DDL/DML + 超时 + 行数上限） |
| `python_sandbox` 工具 | 受限执行（无网络、无文件写入、超时），用于计算类问题 |
| `app/services/agent.py` | LangGraph 状态机：`规划 → 调工具 → 观察 → 再规划 / 回答` |
| `POST /agent` | 新端点，返回 `{answer, steps[], tool_calls[]}` |
| `evals/agent_questions.jsonl` | ≥10 道工具调用评测题（含需要多步的） |

**验收标准（可量化）**：

- 工具选择准确率 ≥ **80%**
- 多步任务端到端成功率 ≥ **70%**
- 危险操作（写库 / 删除 / 执行系统命令）**100% 被拒绝**
- 单次任务平均步数 ≤ 4，且有最大步数兜底

**第一步可以这么开始**：装 `langgraph` → 定义 `Tool` Protocol + 注册表 → 把现有检索包成第一个工具 → 写最小的 `规划 → 调工具 → 回答` 循环 → 加 `/agent` 端点与测试替身。

---

### 阶段 6：工程化 → `v0.6.0`

| # | 事项 | 说明 |
|---|---|---|
| 1 | **JWT 认证 + 用户隔离** | 注册/登录、`documents` 加 `owner_id`、所有查询按用户过滤 |
| 2 | **会话历史持久化** | `chat_sessions` / `chat_messages` 表，替换现在由前端传 `history` 的做法 |
| 3 | **Redis 缓存** | embedding 缓存、检索结果缓存、限流（Redis 已在依赖里但尚未使用） |
| 4 | **异步任务** | 大文件后台入库 + 任务状态查询端点 |
| 5 | **结构化日志** | JSON 日志 + `request_id` 贯穿全链路 |
| 6 | **压测** | locust 脚本，产出 P50 / P95 / 错误率 |

**验收**：核心端点认证覆盖率 100%；缓存命中率 > 30%；压测报告（50 并发下的 P95）。

---

### 阶段 7：vLLM 本地推理

- 用 vLLM 替换 LM Studio，对比吞吐与延迟
- 精度/量化对比（fp16 vs AWQ）
- 产出：TTFT、tokens/s、并发吞吐曲线

---

### 阶段 8：LLM Gateway

**已有雏形**：`request.model` 可覆盖模型名、`LLMUnavailable` → 503。

- 多模型路由（按任务类型选模型：摘要用小模型、推理用大模型）
- 重试 / 降级 / 熔断
- 限流
- Token 计数与成本统计

---

### 阶段 9：Evaluation & Monitoring

- **Langfuse** 接入：每次 RAG / Agent 调用打 trace（检索命中了什么、用了哪个工具、花了多少 token）
- **Prometheus + Grafana**：QPS、延迟分位、错误率、模型调用量看板
- **评测进 CI**：指标低于基线就让 CI 失败，防止回归

---

## 5. 已知限制与技术债

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | 「《实践论》批判了哪两种错误倾向？」两轮评测都排第 5 | 卡在 `top_k=5` 边界上 | 已如实记录为语料的真实检索难度；如需改善可换 `bge-reranker-v2-m3`（改 `.env` 一行） |
| 2 | 生成层有采样噪声 | 同一题两轮可能一次答出、一次拒答 | 检索层指标可复现，生成层指标需多轮取平均 |
| 3 | 前三轮评测延迟为并发测量 | README 延迟对比带星号 | 串行重跑 vector / bm25 / hybrid 三轮统一口径 |
| 4 | `pyproject.toml` 的 `version` 仍是 `0.1.0` | 与 tag `v0.4.0` 不一致 | 阶段 5 顺手改成 `0.5.0` 并纳入发布流程 |
| 5 | BM25 索引是**进程内全量重建** | 语料上万块后内存与重建耗时会失控 | 大语料应换成 Elasticsearch / OpenSearch |
| 6 | `chunks.embedding` 绑定 `vector(1024)` | 换 embedding 模型必须迁移整表 | 已知约束，已在文档说明 |
| 7 | `evals/report.md` 是阶段 3 的旧数据 | 容易看错 | 删除或改名 `report-phase3-baseline.md` |
| 8 | `probe_rerank` 探针脚本未入库 | 换精排模型时要重新手写标定脚本 | 建议补进 `evals/` |

---

## 6. 工程纪律（每天都要遵守）

### 6.1 环境

1. **所有命令显式走 `.venv\Scripts\python.exe -m ...`**，不要用裸 `pip` / `python` / `pytest` / `uvicorn`
2. 看中文输出前先 `chcp 65001`；Python 脚本再加 `$PYTHONIOENCODING='utf-8'`
3. 跑测试前先确认 **Docker 起着**（PostgreSQL 5432）。数据库没起的典型症状是 `ERROR at setup of ...` + `psycopg.errors.ConnectionTimeout`

### 6.2 提交前必跑

```powershell
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q --tb=line      # 期望 72 passed
```

### 6.3 改代码时的几条硬规矩

1. **粘完大段代码先核对行数，再跑最小的那个测试**（`pytest tests/test_chat.py` 只需 3 秒）
2. **改完函数签名先用 `--limit 3` 跑通全流程**，别等 20 题跑完才发现最后一行的 bug
3. **每个文件末尾必须有换行符**（VS Code 开 `files.insertFinalNewline`）；ruff 报的列号 = 行长 + 1 就是缺换行
4. **阈值和开关一律做成配置项**（`settings.xxx`），不要硬编码——测试环境会被线上参数绑架
5. **评测必须串行跑**，一轮结束再开下一轮
6. **新增外部依赖必须走 Protocol + 替身 + 依赖注入**那套模式

### 6.4 读报错的方法

**先分清三类来源**，再动手：

| 关键词 | 大概率是 | 去哪查 |
|---|---|---|
| `PermissionError`、`No usable temporary directory`、`ConnectionTimeout` | **环境问题** | Docker / 权限 / 环境变量 |
| `ERROR at setup of`（不是 FAILED） | 死在 fixture，**测试函数根本没跑** | 外部依赖 |
| `assert A == B` | **代码逻辑** | 看 A（实际）和 B（期望） |
| `AttributeError` / `TypeError` / `NameError` | **代码** | 堆栈里你自己的那一行 |

长 traceback 只看三处：**标题行 → `E` 开头的最后几行 → 堆栈里 `app\` 或 `tests\` 开头的那一行**。日常加 `--tb=line` 让 pytest 只说一行。

---

## 7. 参考文档索引

| 文档 | 位置 | 内容 |
|---|---|---|
| 项目说明 | `README.md` | 项目简介、技术栈、快速开始、**四种检索策略对比** |
| 踩坑记录 | `D:\Tool\Code\Trouble history\troubleshooting.md` | 24 条问题（编号 1–39），含根因、解决方案、复发记录 |
| 评测报告 | `evals/report-{vector,bm25,hybrid,hybrid_rerank}.md` | 四份逐题明细 |
| 题库 | `evals/questions.jsonl` | 20 题（15 可答 + 5 库外） |
| 评测脚本 | `evals/run_eval.py` | `--mode` / `--limit` |

---

## 8. 附：本项目最值得讲的三段故事

1. **"我做了 hybrid，数据说它没赢"** —— 阶段 4.2 的 hybrid 每一项都 ≤ 单路 BM25。没有粉饰，而是定位到两个数学/架构层面的机制（RRF 双票必胜、门控被"或"短路），并据此测出"召回已满分、瓶颈在排序"。
2. **"阈值不是拍脑袋定的"** —— 4.2 里硬编码 `0.45` 误杀了一道可答题；4.3 改成先用探针跑出 20 题的真实分数分布（可答题 0.32~1.00 vs 库外题 0.00~0.01，30 倍空档），再划线。
3. **"同一套评测跑两轮，排序指标一位不差"** —— hit@5 / hit@1 / MRR 两轮完全一致，证明**检索层是确定性的**，波动只出现在 LLM 生成层。这是评测体系可信度的直接证据。
