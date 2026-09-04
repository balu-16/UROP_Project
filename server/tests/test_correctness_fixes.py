"""Correctness-batch regression tests.

Covers: NullReranker order preservation (RRF vs 0.55 graph scale),
2-hop final decision object, unified diagnostics keys.
"""

import numpy as np
import pytest

from app.config.settings import Settings
from app.retrieval.adaptive import AdaptiveRetrievalService
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from tests.fakes import FakeKeywordRetriever
from app.retrieval.policy import ThresholdRetrievalPolicy
from app.retrieval.reranking import NullReranker
from app.services.context import ContextBuilder


def _settings(**overrides) -> Settings:
    base = {
        "high_threshold": 0.75,
        "chunk_min_tokens": 1,
        "top_k": 6,
        "vector_top_k": 50,
        "keyword_top_k": 50,
        "rrf_k": 60,
        "rerank_candidate_cap": 100,
        "rerank_top_k": 5,
    }
    base.update(overrides)
    return Settings(**base)


def _text(cid: str) -> str:
    return f"Content of chunk {cid} with plenty of words for token counting purposes."


def _fused(chunk_id: str, vector_score: float, rrf: float) -> dict:
    # Vector-store input shape: score IS the cosine. Fusion derives
    # vector_score from score; rrf/score here are ignored pre-fusion.
    return {
        "chunk_id": chunk_id,
        "document_id": "doc1",
        "text": _text(chunk_id),
        "metadata": {"source": "t.md"},
        "score": vector_score,
    }


class FakeEmbeddings:
    async def embed_query(self, text: str):
        return np.zeros(384, dtype=np.float32)


class FakeVectorStore:
    def __init__(self, results):
        self._results = results
        self.metadata: list[dict] = []
        self.collection = None

    def search(self, query_vector, top_k: int, user_id=None, session_id=None):
        return [dict(r) for r in self._results[: max(0, int(top_k))]]


class FakeGraphWithChunks:
    """Graph that resolves to caller-supplied chunk dicts via metadata fallback."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def expand_chunks(self, seed_ids, hops: int = 1, **kwargs):
        return {"chunk_ids": [c["chunk_id"] for c in self._chunks], "expanded_entities": ["e1"]}


@pytest.mark.asyncio
async def test_null_reranker_preserves_rrf_order_over_graph_default():
    """Fused RRF order must survive ContextBuilder when reranker is Null.

    RRF scores (~0.01) vs graph default 0.55: a score-sort would float the
    graph chunk on top. preserve_order=True must keep RRF first.
    """
    settings = _settings()
    vector = [_fused("b", 0.5, 0.02), _fused("a", 0.4, 0.015)]
    graph_chunks = [
        {
            "chunk_id": "g1",
            "document_id": "doc1",
            "text": _text("g1"),
            "metadata": {"source": "t.md"},
            "user_id": "u",
            "session_id": "s",
            "score": 0.55,
            "graph_boost": True,
        }
    ]
    svc = AdaptiveRetrievalService(
        settings,
        FakeEmbeddings(),
        FakeVectorStore(vector),
        FakeGraphWithChunks(graph_chunks),
        RetrievalConfidenceEvaluator(),
        ThresholdRetrievalPolicy(settings),
        ContextBuilder(settings),
        keyword_retriever=FakeKeywordRetriever([]),
        reranker=NullReranker("unit"),
    )
    # Force the metadata fallback path: FakeVectorStore exposes .metadata list.
    svc.vector_store.metadata = [
        {**c, "chunk_id": c["chunk_id"]} for c in graph_chunks
    ]
    out = await svc.retrieve("q", user_id="u", session_id="s")
    # Low confidence (0.5) forces 1-hop then 2-hop; final context must keep
    # fused RRF order (b, a) before graph (g1).
    ids = [c["chunk_id"] for c in out["chunks"]]
    assert ids[:2] == ["b", "a"], f"RRF order lost: {ids}"
    assert "g1" in ids
    assert out["diagnostics"]["reranker_enabled"] is False


@pytest.mark.asyncio
async def test_two_hop_reports_final_decision_and_unified_diagnostics():
    settings = _settings()
    vector = [_fused("a", 0.5, 0.02)]
    svc = AdaptiveRetrievalService(
        settings,
        FakeEmbeddings(),
        FakeVectorStore(vector),
        FakeGraphWithChunks([]),
        RetrievalConfidenceEvaluator(),
        ThresholdRetrievalPolicy(settings),
        ContextBuilder(settings),
        keyword_retriever=FakeKeywordRetriever([]),
        reranker=NullReranker("unit"),
    )
    out = await svc.retrieve("q", user_id="u", session_id="s")
    assert out["retrieval"]["depth"] == 2
    decision = out["retrieval"]["decision"]
    assert decision["depth"] == 2
    assert decision["strategy"] == "TWO_HOP"
    assert decision["confidence"] == out["retrieval"]["confidence"]
    diag = out["diagnostics"]
    for key in (
        "semantic_count",
        "keyword_count",
        "fused_count",
        "expanded_count",
        "merged_count",
        "graph_nodes",
        "confidence",
        "depth",
        "strategy",
        "reranker_enabled",
        "rerank_candidate_count",
        "reranked_count",
        "rerank_latency_ms",
    ):
        assert key in diag, f"missing diagnostics key: {key}"


@pytest.mark.asyncio
async def test_zero_hop_diagnostics_unified():
    settings = _settings()
    vector = [_fused("a", 0.9, 0.03)]
    svc = AdaptiveRetrievalService(
        settings,
        FakeEmbeddings(),
        FakeVectorStore(vector),
        FakeGraphWithChunks([]),
        RetrievalConfidenceEvaluator(),
        ThresholdRetrievalPolicy(settings),
        ContextBuilder(settings),
        keyword_retriever=FakeKeywordRetriever([]),
        reranker=NullReranker("unit"),
    )
    out = await svc.retrieve("q")
    assert out["retrieval"]["strategy"] == "ZERO_HOP"
    diag = out["diagnostics"]
    assert diag["expanded_count"] == 0
    assert diag["merged_count"] == diag["fused_count"]
    assert diag["depth"] == 0
    assert diag["strategy"] == "ZERO_HOP"
