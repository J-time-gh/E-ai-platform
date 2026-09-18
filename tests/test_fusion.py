"""RRF 融合测试：纯函数，不需要数据库、不需要模型。"""

from app.schemas.search import SearchResult
from app.services.fusion import rrf_fuse


def _result(chunk_id: str, score: float = 1.0) -> SearchResult:
    """造一条假的检索结果，只关心 chunk_id 和 score。"""
    return SearchResult(
        chunk_id=chunk_id,
        document_id="doc-1",
        filename="fake.txt",
        chunk_index=0,
        content=f"内容 {chunk_id}",
        score=score,
    )


def test_rrf_prefers_chunks_found_by_both_lists() -> None:
    vector = [_result("a"), _result("b")]
    bm25 = [_result("b"), _result("c")]
    fused = rrf_fuse([vector, bm25], top_k=3)
    # b 在向量里第 2、BM25 里第 1 → 两路都投票 → 应该排第一
    assert fused[0].chunk_id == "b"


def test_rrf_keeps_results_from_single_list() -> None:
    vector = [_result("a")]
    bm25 = [_result("b")]
    fused = rrf_fuse([vector, bm25], top_k=5)
    assert {item.chunk_id for item in fused} == {"a", "b"}


def test_rrf_deduplicates_same_chunk() -> None:
    fused = rrf_fuse([[_result("a"), _result("a")]], top_k=5)
    assert len(fused) == 1


def test_rrf_respects_top_k() -> None:
    vector = [_result(f"c{index}") for index in range(10)]
    assert len(rrf_fuse([vector], top_k=3)) == 3


def test_rrf_handles_empty_input() -> None:
    assert rrf_fuse([[], []], top_k=5) == []


def test_rrf_replaces_score_with_fusion_score() -> None:
    fused = rrf_fuse([[_result("a", score=0.99)]], top_k=1)
    # 原来的 0.99 会被 RRF 分（1/61 ≈ 0.016）替换掉
    assert fused[0].score < 0.1
