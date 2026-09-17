"""M8 评测：给 RAG 系统做体检（检索质量 / 回答质量 / 延迟）。

前置（三个都要开着）：
    1. docker compose up -d                                # PostgreSQL
    2. .venv\\Scripts\\python.exe -m uvicorn app.main:app    # 后端服务
    3. LM Studio 启动本地服务器并加载模型                     # 大模型

运行（在项目根目录）：
    .venv\\Scripts\\python.exe evals\\run_eval.py

输出：控制台打印 markdown 表格，同时写入 evals/report.md
"""

import argparse
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
TOP_K = 5
QUESTIONS_PATH = Path(__file__).parent / "questions.jsonl"
REPORT_PATH = Path(__file__).parent / "report.md"

CITATION_RE = re.compile(r"\[\d+\]")  # 匹配 [1] [2] 这类引用标记
NO_ANSWER = "根据现有资料无法回答。"  # 与 app/services/rag.py 的 NO_CONTEXT_REPLY 保持一致


@dataclass
class Question:
    """题库里的一条。"""

    question: str
    must_hit: list[str]  # 命中判定关键词（任一出现即算命中）；不可答的题写 []
    answerable: bool = True  # False = 知识库里本来就没有答案（用来测拒答）


@dataclass
class Sample:
    """一条问题的评测结果。"""

    question: str
    answerable: bool
    rank: int | None  # 第一个命中的排名（从 1 开始）；None = 没命中
    citation: bool  # 回答里有没有 [n]
    covered: bool  # 回答里有没有出现 must_hit 关键词
    refused: bool  # 回答是不是"根据现有资料无法回答。"
    latency: float  # /chat 耗时（秒）


def _mark(flag: bool) -> str:
    """把布尔值渲染成表里的勾叉。"""
    return "✅" if flag else "❌"


def load_questions(path: Path = QUESTIONS_PATH) -> list[Question]:
    """读取 JSONL 题库（跳过空行和 # 开头的注释行）。"""
    items: list[Question] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        items.append(Question(**json.loads(stripped)))
    return items


def first_hit_rank(texts: list[str], keywords: list[str]) -> int | None:
    """返回第一个包含任一关键词的排名（从 1 开始）；都没命中返回 None。"""
    for rank, text in enumerate(texts, start=1):
        if any(keyword in text for keyword in keywords):
            return rank
    return None


def percentile(values: list[float], ratio: float) -> float:
    """线性插值百分位，ratio=0.95 即 P95。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def warm_up(client: httpx.Client) -> None:
    """预热：把 bge-m3 首次加载（约 18 秒）排除在延迟统计之外。"""
    print("预热中（首次请求要加载 bge-m3，约 18 秒）...")
    started = time.perf_counter()
    client.post(f"{BASE_URL}/search", json={"query": "预热", "top_k": 1})
    print(f"预热完成：{time.perf_counter() - started:.1f}s\n")


def run_one(client: httpx.Client, item: Question, mode: str) -> tuple[Sample, str]:
    """跑一条题：先检索（看命中排名），再问答（看引用 / 覆盖 / 延迟）。"""
    search_response = client.post(
        f"{BASE_URL}/search",
        json={"query": item.question, "top_k": TOP_K, "mode": mode},
    )
    search_response.raise_for_status()
    contents = [row["content"] for row in search_response.json()]
    rank = first_hit_rank(contents, item.must_hit) if item.must_hit else None

    started = time.perf_counter()
    chat_response = client.post(
        f"{BASE_URL}/chat",
        json={"message": item.question, "top_k": TOP_K, "mode": mode},
    )
    latency = time.perf_counter() - started
    chat_response.raise_for_status()
    body = chat_response.json()
    reply = body["reply"]

    sample = Sample(
        question=item.question,
        answerable=item.answerable,
        rank=rank,
        citation=bool(CITATION_RE.search(reply)),
        covered=any(keyword in reply for keyword in item.must_hit),
        refused=reply.strip() == NO_ANSWER,
        latency=latency,
    )
    return sample, body["model"]


def build_report(samples: list[Sample], model: str, mode: str) -> str:
    """计算指标并生成 markdown 报告。"""
    retrieval = [s for s in samples if s.answerable]  # 检索/回答指标只看"可答"题
    refusals = [s for s in samples if not s.answerable]  # 拒答指标只看"不可答"题
    total = len(retrieval)

    hit_at_1 = sum(1 for s in retrieval if s.rank == 1) / total
    hit_at_k = sum(1 for s in retrieval if s.rank is not None) / total
    mrr = sum(1.0 / s.rank for s in retrieval if s.rank is not None) / total
    citation_rate = sum(1 for s in retrieval if s.citation) / total
    coverage_rate = sum(1 for s in retrieval if s.covered) / total
    refuse_rate = sum(1 for s in refusals if s.refused) / len(refusals) if refusals else 0.0
    latencies = [s.latency for s in retrieval]

    lines = [
        "# RAG 评测报告",
        "",
        f"- 评测时间：{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}",
        f"- 生成模型：{model}",
        f"- 检索模式：{mode}",
        f"- 检索 top_k：{TOP_K}",
        f"- 题库：{len(samples)} 条（可答 {total} / 不可答 {len(refusals)}）",
        "- 延迟统计已排除预热（首次模型加载）",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 | 口径 |",
        "|---|---|---|",
        f"| hit@{TOP_K} | {hit_at_k:.1%} | 前 {TOP_K} 条里有任一条含关键词 |",
        f"| hit@1 | {hit_at_1:.1%} | 第 1 条就命中 |",
        f"| MRR | {mrr:.3f} | 首个命中排名倒数的平均值 |",
        f"| 引用标注率 | {citation_rate:.1%} | 回答里出现 [n] |",
        f"| 关键词覆盖率 | {coverage_rate:.1%} | 回答里出现 must_hit |",
        f"| 拒答正确率 | {refuse_rate:.1%} | 库外问题被正确拒答 |",
        f"| 平均延迟 | {sum(latencies) / len(latencies):.2f}s | /chat 平均耗时 |",
        f"| P95 延迟 | {percentile(latencies, 0.95):.2f}s | /chat P95 耗时 |",
        "",
        "## 逐题明细",
        "",
        "| # | 问题 | 首个命中 | 引用 | 覆盖 | 拒答 | 延迟(s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for index, sample in enumerate(samples, start=1):
        rank = "-" if sample.rank is None else str(sample.rank)
        lines.append(
            f"| {index} | {sample.question[:24]} | {rank} | "
            f"{_mark(sample.citation)} | {_mark(sample.covered)} | "
            f"{_mark(sample.refused)} | {sample.latency:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 评测")
    parser.add_argument(
        "--mode",
        default="vector",
        # hybrid / hybrid_rerank 要等 4.2 / 4.3 实现后才能用
        choices=["vector", "bm25", "hybrid", "hybrid_rerank"],
    )
    args = parser.parse_args()
    report_path = REPORT_PATH.with_name(f"report-{args.mode}.md")

    questions = load_questions()
    print(f"载入题库 {len(questions)} 条，检索模式：{args.mode}\n")

    samples: list[Sample] = []
    model = "unknown"
    with httpx.Client(timeout=300.0) as client:
        warm_up(client)
        for index, item in enumerate(questions, start=1):
            sample, served_model = run_one(client, item, args.mode)
            samples.append(sample)
            if model == "unknown" and served_model != "none":
                model = served_model
            rank_text = "-" if sample.rank is None else str(sample.rank)
            print(
                f"[{index}/{len(questions)}] {item.question[:26]:<26} "
                f"命中={rank_text:<2} 延迟={sample.latency:5.2f}s"
            )

    report = build_report(samples, model, args.mode)
    print("\n" + report)
    report_path.write_text(report, encoding="utf-8")
    print(f"报告已写入：{report_path}")


if __name__ == "__main__":
    main()
