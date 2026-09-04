"""Stage 1 tests: hybrid vector+keyword RRF + gate-preserving integration.

Covers plan.md §2-4, §12 (hybrid), §16-18 (gate regression + ordering).
All retrieval tests run on fakes (MEMORY:// can't execute PG full-text SQL);
the live-RPC integration test is PG-gated and skipped by default.
"""

import os

import numpy as np
import pytest

from app.config.settings import Settings
from app.retrieval.adaptive import AdaptiveRetrievalService
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keyword import PostgresKeywordRetriever

from tests.fakes import FakeKeywordRetriever
from app.retrieval.policy import ThresholdRetrievalPolicy
from app.services.context import ContextBuilder


def _settings(**overrides) -> Settings:
    base = {
        "high_threshold": 0.75,
        "chunk_min_tokens": 1,
        "top_k": 6,
        "vector_top_k": 50,
        "keyword_top_k": 50,
        "rrf_k": 60,
    }
    base.update(overrides)
    return Settings(**base)


def _vec(chunk_id: str, score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc1",
        "text": f"Content of chunk {chunk_id} with plenty of words for token counting purposes.",
        "metadata": {"source": "test.md"},
        "score": score,
    }


def _kw(chunk_id: str, rank_score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc1",
        "text": f"Content of chunk {chunk_id} with plenty of words for token counting purposes.",
        "metadata": {"source": "test.md"},
        "keyword_score": rank_score,
    }


class FakeEmbeddings:
    async def embed_query(self, text: str):
        return np.zeros(384, dtype=np.float32)


class FakeVectorStore:
    def __init__(self, results: list[dict], metadata: list[dict] | None = None):
        self._results = results
        self.metadata = metadata or []
        self.collection = None
        self.search_calls: list[dict] = []

    def search(self, query_vector, top_k: int, user_id=None, session_id=None):
        self.search_calls.append({"top_k": top_k, "user_id": user_id, "session_id": session_id})
        return [dict(r) for r in self._results[: max(0, int(top_k))]]


class FakeGraph:
    def __init__(self, chunk_ids: list[str]):
        self._chunk_ids = chunk_ids
        self.expand_calls: list[dict] = []

    async def expand_chunks(self, seed_ids, hops: int = 1, **kwargs):
        self.expand_calls.append({"seeds": list(seed_ids), "hops": hops})
        return {"chunk_ids": list(self._chunk_ids), "expanded_entities": ["e1"]}


def _graph_meta(chunk_id: str) -> dict:
    # Fallback resolution enforces session isolation: metadata must carry the
    # same user_id/session_id the query runs under (here "u"/"s").
    return {
        "chunk_id": chunk_id,
        "text": f"Graph expanded chunk {chunk_id} with plenty of words for token counting.",
        "metadata": {"source": "graph.md"},
        "user_id": "u",
        "session_id": "s",
    }


def _service(vector, keyword, graph_ids, **settings_overrides):
    settings = _settings(**settings_overrides)
    return AdaptiveRetrievalService(
        settings,
        FakeEmbeddings(),
        FakeVectorStore(vector, metadata=[_graph_meta(c) for c in graph_ids]),
        FakeGraph(graph_ids),
        RetrievalConfidenceEvaluator(),
        ThresholdRetrievalPolicy(settings),
        ContextBuilder(settings),
        keyword_retriever=FakeKeywordRetriever(keyword),
    )


# ── Fusion unit tests ────────────────────────────────────────────────────

def test_fusion_combines_ranks_dedups_and_marks_provenance():
    fused = reciprocal_rank_fusion([_vec("A", 0.9), _vec("B", 0.8)], [_kw("B", 0.05), _kw("C", 0.04)])
    assert [c["chunk_id"] for c in fused] == ["B", "A", "C"]
    by_id = {c["chunk_id"]: c for c in fused}
    assert by_id["B"]["retrieval_sources"] == ["vector", "keyword"]
    assert by_id["A"]["retrieval_sources"] == ["vector"]
    assert by_id["C"]["retrieval_sources"] == ["keyword"]
    # Cosine preserved for the gate; fused score is the RRF ordering key.
    assert by_id["A"]["vector_score"] == 0.9
    assert by_id["C"]["vector_score"] is None
    assert by_id["B"]["score"] == pytest.approx(1 / 62 + 1 / 61)
    assert by_id["A"]["score"] == pytest.approx(1 / 61)  # vector rank 1
    assert by_id["C"]["score"] == pytest.approx(1 / 62)  # keyword rank 2


def test_fusion_handles_empty_sides():
    only_vector = reciprocal_rank_fusion([_vec("A", 0.7)], [])
    assert [c["chunk_id"] for c in only_vector] == ["A"]
    assert reciprocal_rank_fusion([], []) == []
    assert reciprocal_rank_fusion(None, None) == []


def test_fusion_skips_items_without_chunk_id():
    fused = reciprocal_rank_fusion([{"score": 1.0}], [_kw("A", 0.1)])
    assert [c["chunk_id"] for c in fused] == ["A"]


# ── Gate regression: RRF must never reach the 0.75 gate ──────────────────

def test_gate_reads_vector_score_not_rrf():
    evaluator = RetrievalConfidenceEvaluator()
    fused = reciprocal_rank_fusion([_vec("A", 0.8)], [_kw("B", 0.05)])
    assert evaluator.evaluate(fused) == 0.8
    policy = ThresholdRetrievalPolicy(_settings())
    assert policy.decide_initial(evaluator.evaluate(fused)).depth == 0


def test_low_vector_confidence_still_traverses_to_two_hop():
    policy = ThresholdRetrievalPolicy(_settings())
    assert policy.decide_initial(0.5).depth == 1
    assert policy.decide_after_one_hop(0.4, 0.5).depth == 2


# ── Adaptive integration (ordering + scoping) ────────────────────────────

@pytest.mark.asyncio
async def test_high_confidence_skips_expansion_and_uses_fused_pool():
    svc = _service([_vec("A", 0.9)], [], [])
    out = await svc.retrieve("query", user_id="u", session_id="s")
    assert out["retrieval"]["strategy"] == "ZERO_HOP"
    assert out["retrieval"]["depth"] == 0
    assert svc.graph_store.expand_calls == []
    assert out["diagnostics"]["keyword_count"] == 0
    assert out["diagnostics"]["fused_count"] == 1
    assert out["chunks"], "confident retrieval must still build context"


@pytest.mark.asyncio
async def test_low_confidence_expands_from_fused_seeds_in_rrf_order():
    # Vector prefers A; keyword ranks B first → RRF puts B first → B seeds expansion.
    svc = _service([_vec("A", 0.5), _vec("B", 0.49)], [_kw("B", 0.05), _kw("C", 0.04)], ["g1"])
    out = await svc.retrieve("query", user_id="u", session_id="s")
    assert svc.graph_store.expand_calls, "expansion must run below threshold"
    first_seeds = svc.graph_store.expand_calls[0]["seeds"]
    assert first_seeds[0] == "B", f"RRF order not respected in seeds: {first_seeds}"
    assert out["retrieval"]["depth"] == 2  # existing traversal preserved
    chunk_ids = [c["chunk_id"] for c in out["chunks"]]
    assert "g1" in chunk_ids, "graph evidence must survive into context"
    assert len(chunk_ids) == len(set(chunk_ids)), "duplicates leaked into context"


@pytest.mark.asyncio
async def test_expansion_seeds_are_bounded_by_top_k():
    vector = [_vec(f"v{i}", 0.5 - i * 0.01) for i in range(10)]
    keyword = [_kw(f"k{i}", 0.05) for i in range(10)]
    svc = _service(vector, keyword, [])
    await svc.retrieve("query", user_id="u", session_id="s")
    assert svc.graph_store.expand_calls
    assert len(svc.graph_store.expand_calls[0]["seeds"]) <= 6


@pytest.mark.asyncio
async def test_keyword_branch_uses_configured_top_k_and_scoping():
    kw = FakeKeywordRetriever([_kw("B", 0.05)])
    settings = _settings()
    svc = AdaptiveRetrievalService(
        settings, FakeEmbeddings(), FakeVectorStore([_vec("A", 0.9)]),
        FakeGraph([]), RetrievalConfidenceEvaluator(),
        ThresholdRetrievalPolicy(settings), ContextBuilder(settings),
        keyword_retriever=kw,
    )
    await svc.retrieve("exact words query", user_id="u1", session_id="s1")
    assert kw.calls and kw.calls[0]["top_k"] == 50
    assert kw.calls[0]["user_id"] == "u1"
    assert kw.calls[0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_keyword_failure_degrades_to_vector_only():
    class ExplodingRetriever:
        async def search(self, *args, **kwargs):
            raise RuntimeError("pg down")

    settings = _settings()
    svc = AdaptiveRetrievalService(
        settings, FakeEmbeddings(), FakeVectorStore([_vec("A", 0.9)]),
        FakeGraph([]), RetrievalConfidenceEvaluator(),
        ThresholdRetrievalPolicy(settings), ContextBuilder(settings),
        keyword_retriever=ExplodingRetriever(),
    )
    out = await svc.retrieve("query", user_id="u", session_id="s")
    assert out["retrieval"]["strategy"] == "ZERO_HOP"
    assert out["diagnostics"]["keyword_count"] == 0
    assert out["chunks"], "vector-only degradation must still build context"


# ── PostgresKeywordRetriever mapping (no live PG needed) ─────────────────

@pytest.mark.asyncio
async def test_postgres_retriever_maps_rows_and_degrades():
    from app.retrieval.keyword import PostgresKeywordRetriever

    rows = [
        {"chunk_id": "chk_1", "document_id": "d1", "content": "hello world",
         "metadata": {"source": "a.pdf"}, "rank": 0.7},
        {"nope": True},
    ]
    seen: dict = {}

    def fake_rpc(fn, params):
        seen["fn"] = fn
        seen["params"] = params
        return rows

    mapped = await PostgresKeywordRetriever(
        _settings(), rpc=fake_rpc
    ).search("hello", "u", "s", 50)
    assert seen["fn"] == "match_chunks_fts"
    assert seen["params"] == {
        "p_query": "hello", "p_session_id": "s", "p_user_id": "u", "p_limit": 50,
    }
    assert len(mapped) == 1
    assert mapped[0]["chunk_id"] == "chk_1"
    assert mapped[0]["text"] == "hello world"
    assert mapped[0]["keyword_score"] == 0.7

    assert await PostgresKeywordRetriever(_settings(), rpc=None).search("q", "u", "s", 5) == []

    def boom(fn, params):
        raise RuntimeError("db gone")

    assert await PostgresKeywordRetriever(_settings(), rpc=boom).search("q", "u", "s", 5) == []


@pytest.mark.skipif(
    os.environ.get("RAG_TEST_PG") != "1",
    reason="Needs live Postgres with migration 002: RAG_TEST_PG=1 supa-url supa-key",
)
@pytest.mark.asyncio
async def test_live_rpc_shape():
    """PG-gated integration: run manually against staging Supabase."""
    raise AssertionError("Manual test: call match_chunks_fts and assert rank desc + session isolation")
