"""Stage 2 tests: cross-encoder reranking after hops + cap + fallback + telemetry.

Covers plan.md §5-8, §12 (reranker), §17-18 (ordering). The live MiniLM model
is never downloaded here: CrossEncoderReranker is exercised with an injected
fake model, and load-failure paths are simulated by monkeypatching.
"""

import numpy as np
import pytest

from app.config.settings import Settings
from app.retrieval.adaptive import AdaptiveRetrievalService
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from tests.fakes import FakeKeywordRetriever
from app.retrieval.policy import ThresholdRetrievalPolicy
from app.retrieval.reranking import (
    CrossEncoderReranker,
    NullReranker,
    build_reranker,
)
from app.services.context import ContextBuilder


def _settings(**overrides) -> Settings:
    base = {
        "high_threshold": 0.75,
        "chunk_min_tokens": 1,
        "top_k": 6,
        "vector_top_k": 50,
        "keyword_top_k": 50,
        "rrf_k": 60,
        "reranker_enabled": True,
        "rerank_candidate_cap": 100,
        "rerank_top_k": 5,
    }
    base.update(overrides)
    return Settings(**base)


def _text(cid: str) -> str:
    return f"Content of chunk {cid} with plenty of words for token counting purposes."


def _vec(chunk_id: str, score: float) -> dict:
    return {
        "chunk_id": chunk_id, "document_id": "doc1", "text": _text(chunk_id),
        "metadata": {"source": "t.md"}, "score": score,
    }


class FakeEmbeddings:
    async def embed_query(self, text: str):
        return np.zeros(384, dtype=np.float32)


class FakeVectorStore:
    def __init__(self, results, metadata=None):
        self._results = results
        self.metadata = metadata or []
        self.collection = None

    def search(self, query_vector, top_k: int, user_id=None, session_id=None):
        return [dict(r) for r in self._results[: max(0, int(top_k))]]


class FakeGraph:
    def __init__(self, chunk_ids, log=None):
        self._chunk_ids = chunk_ids
        self.log = log if log is not None else []
        self.expand_calls: list[dict] = []

    async def expand_chunks(self, seed_ids, hops: int = 1, **kwargs):
        self.expand_calls.append({"seeds": list(seed_ids), "hops": hops})
        self.log.append(("expand", hops))
        return {"chunk_ids": list(self._chunk_ids), "expanded_entities": ["e1"]}


def _graph_meta(chunk_id: str) -> dict:
    return {
        "chunk_id": chunk_id, "text": _text(chunk_id),
        "metadata": {"source": "g.md"}, "user_id": "u", "session_id": "s",
    }


class RecordingReranker:
    """Test double proving WHEN rerank runs and WHAT it receives.

    With ``assign_scores``, behaves like the real CrossEncoderReranker:
    reordered items carry fresh logits in ``score``, which is what survives
    ContextBuilder's score sort into the final context.
    """

    applied = True
    model_name = "test-recorder"

    def __init__(self, log, reverse=False, assign_scores=False):
        self.log = log
        self.reverse = reverse
        self.assign_scores = assign_scores
        self.seen: list[dict] = []

    async def rerank(self, query, candidates):
        self.seen = list(candidates)
        self.log.append(("rerank", len(candidates)))
        out = list(reversed(candidates)) if self.reverse else list(candidates)
        if self.assign_scores:
            rescored = []
            for i, c in enumerate(out):
                d = dict(c)
                d["rerank_score"] = float(len(out) - i)
                d["score"] = float(len(out) - i)
                rescored.append(d)
            return rescored
        return out


class ExplodingReranker:
    applied = True
    model_name = "test-boom"

    async def rerank(self, query, candidates):
        raise RuntimeError("reranker down")


class FakeModel:
    """Stands in for CrossEncoder.predict without downloading weights."""

    def __init__(self, scores):
        self._scores = list(scores)
        self.calls: list = []

    def predict(self, pairs):
        self.calls.append(list(pairs))
        return list(self._scores[: len(pairs)])


def _service(vector, keyword, graph_ids, reranker, log, **overrides):
    settings = _settings(**overrides)
    graph = FakeGraph(graph_ids, log=log)
    svc = AdaptiveRetrievalService(
        settings, FakeEmbeddings(),
        FakeVectorStore(vector, metadata=[_graph_meta(c) for c in graph_ids]),
        graph, RetrievalConfidenceEvaluator(), ThresholdRetrievalPolicy(settings),
        ContextBuilder(settings), keyword_retriever=FakeKeywordRetriever(keyword),
        reranker=reranker,
    )
    return svc, graph


# ── Reranker units ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_null_reranker_passes_through_untouched():
    items = [_vec("a", 0.9), _vec("b", 0.1)]
    out = await NullReranker("unit").rerank("q", items)
    assert out == items
    assert NullReranker().applied is False


@pytest.mark.asyncio
async def test_cross_encoder_scores_sorts_and_rewrites_score():
    r = CrossEncoderReranker(_settings(), model=FakeModel([1.5, 8.0, -2.0]))
    items = [_vec("a", 0.9), _vec("b", 0.2), _vec("c", 0.5)]
    out = await r.rerank("q", items)
    assert [c["chunk_id"] for c in out] == ["b", "a", "c"]
    assert [c["rerank_score"] for c in out] == [8.0, 1.5, -2.0]
    assert all(c["score"] == c["rerank_score"] for c in out)
    assert r.applied is True


@pytest.mark.asyncio
async def test_cross_encoder_empty_pool_short_circuits_without_model_call():
    r = CrossEncoderReranker(_settings(), model=FakeModel([1.0]))
    assert await r.rerank("q", []) == []


def test_build_reranker_respects_flags_and_failures(monkeypatch):
    assert isinstance(build_reranker(_settings(reranker_enabled=False)), NullReranker)
    assert isinstance(
        build_reranker(_settings(disable_local_models=True)), NullReranker
    )

    def boom(self):
        raise RuntimeError("no network")

    monkeypatch.setattr(CrossEncoderReranker, "load", boom)
    # Explicit False: run_all.py exports DISABLE_LOCAL_MODELS=true, which would
    # otherwise short-circuit to NullReranker before load() is ever reached.
    fallback = build_reranker(_settings(disable_local_models=False))
    assert isinstance(fallback, NullReranker)
    assert "load_failed" in fallback.reason


# ── Ordering: rerank strictly after hops ─────────────────────────────────

@pytest.mark.asyncio
async def test_rerank_runs_after_expansion_and_sees_graph_chunks():
    log: list = []
    rec = RecordingReranker(log)
    svc, _ = _service([_vec("A", 0.5)], [], ["g1"], rec, log)
    out = await svc.retrieve("query", user_id="u", session_id="s")
    expand_idx = next(i for i, e in enumerate(log) if e[0] == "expand")
    rerank_idx = next(i for i, e in enumerate(log) if e[0] == "rerank")
    assert expand_idx < rerank_idx, f"rerank ran before expansion: {log}"
    assert "g1" in [c["chunk_id"] for c in rec.seen], "reranker missed hop evidence"
    assert out["retrieval"]["depth"] == 2


@pytest.mark.asyncio
async def test_rerank_also_runs_on_zero_hop():
    log: list = []
    rec = RecordingReranker(log)
    svc, _ = _service([_vec("A", 0.9)], [], [], rec, log)
    out = await svc.retrieve("query", user_id="u", session_id="s")
    assert out["retrieval"]["strategy"] == "ZERO_HOP"
    assert ("rerank", 1) in log


@pytest.mark.asyncio
async def test_rerank_order_determines_final_context():
    log: list = []
    rec = RecordingReranker(log, reverse=True, assign_scores=True)
    svc, _ = _service(
        [_vec(f"c{i}", 0.9 - i * 0.01) for i in range(8)], [], [], rec, log
    )
    out = await svc.retrieve("query", user_id="u", session_id="s")
    # 8 fused → top 5 after reverse → context holds reversed slice.
    assert [c["chunk_id"] for c in out["chunks"]] == [f"c{i}" for i in (7, 6, 5, 4, 3)]
    assert out["retrieval"]["reranked_count"] == 5


# ── Cap, slice, fallback, telemetry ──────────────────────────────────────

@pytest.mark.asyncio
async def test_candidate_cap_bounds_reranker_input():
    log: list = []
    rec = RecordingReranker(log)
    vector = [_vec(f"v{i}", 0.9 - i * 0.001) for i in range(50)]
    svc, _ = _service(vector, [], [f"g{i}" for i in range(60)], rec, log,
                       rerank_candidate_cap=100)
    out = await svc.retrieve("query", user_id="u", session_id="s")
    assert rec.seen and len(rec.seen) <= 100
    assert out["diagnostics"]["rerank_candidate_count"] <= 100
    assert out["retrieval"]["reranked_count"] <= 5


@pytest.mark.asyncio
async def test_reranker_failure_falls_back_to_pre_rerank_order():
    log: list = []
    svc, _ = _service(
        [_vec("A", 0.9), _vec("B", 0.8)], [], [], ExplodingReranker(), log
    )
    out = await svc.retrieve("query", user_id="u", session_id="s")
    assert [c["chunk_id"] for c in out["chunks"]] == ["A", "B"]
    assert out["retrieval"]["strategy"] == "ZERO_HOP"
    assert out["diagnostics"]["reranker_enabled"] is False
    assert out["diagnostics"]["reranker_reason"] == "runtime_error"


@pytest.mark.asyncio
async def test_telemetry_reports_model_counts_and_latency():
    log: list = []
    rec = RecordingReranker(log)
    svc, _ = _service([_vec("A", 0.9), _vec("B", 0.8)], [], [], rec, log)
    out = await svc.retrieve("query", user_id="u", session_id="s")
    diag = out["diagnostics"]
    assert diag["reranker_enabled"] is True
    assert diag["reranker_model"] == "test-recorder"
    assert diag["rerank_candidate_count"] == 2
    assert diag["reranked_count"] == 2
    assert diag["rerank_latency_ms"] >= 0.0
    assert out["retrieval"]["retrieval_mode"] == "hybrid"
    assert out["retrieval"]["candidate_count"] == 2
    assert out["retrieval"]["strategy"] == "ZERO_HOP", "strategy enum untouched"
