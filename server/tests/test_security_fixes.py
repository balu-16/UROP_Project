"""Regression tests for isolation / validation / DoS fixes.

Covers: retrieval fail-closed on missing session, Supabase $or+rest merge,
rate-limit proxy/per-route behavior, upload caps/codes, greeting threshold.
"""

import numpy as np
import pytest

from app.config.settings import Settings
from app.retrieval.adaptive import AdaptiveRetrievalService
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from app.retrieval.policy import ThresholdRetrievalPolicy
from app.retrieval.reranking import NullReranker
from app.services.context import ContextBuilder
from tests.fakes import FakeKeywordRetriever


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


class FakeEmbeddings:
    async def embed_query(self, text: str):
        return np.zeros(384, dtype=np.float32)


class FakeVectorStore:
    def __init__(self, results=None):
        self._results = results or []
        self.metadata: list[dict] = []
        self.collection = None

    def search(self, query_vector, top_k: int, user_id=None, session_id=None):
        return [dict(r) for r in self._results[: max(0, int(top_k))]]


class FakeGraph:
    async def expand_chunks(self, seed_ids, hops: int = 1, **kwargs):
        raise AssertionError("graph must not run when session is missing")


def _svc(**overrides):
    settings = _settings(**overrides)
    return AdaptiveRetrievalService(
        settings,
        FakeEmbeddings(),
        FakeVectorStore([{
            "chunk_id": "a", "document_id": "d", "text": "x " * 50,
            "metadata": {"source": "t.md"}, "score": 0.9,
        }]),
        FakeGraph(),
        RetrievalConfidenceEvaluator(),
        ThresholdRetrievalPolicy(settings),
        ContextBuilder(settings),
        keyword_retriever=FakeKeywordRetriever([]),
        reranker=NullReranker("unit"),
    )


@pytest.mark.asyncio
async def test_retrieve_without_session_is_fail_closed():
    svc = _svc()
    out = await svc.retrieve("q", user_id="u", session_id=None)
    assert out["chunks"] == []
    assert out["context"] == ""
    assert out["diagnostics"].get("fail_closed") is True
    assert out["retrieval"]["candidate_count"] == 0


@pytest.mark.asyncio
async def test_session_chunk_ids_without_session_returns_empty_set():
    svc = _svc()
    assert await svc._session_chunk_ids("u", None, ["a"]) == set()
    assert await svc._session_chunk_ids("u", "", ["a"]) == set()


@pytest.mark.asyncio
async def test_resolve_chunks_filters_empty_string_ids_strictly():
    svc = _svc()

    class Coll:
        def get(self, ids=None, include=None):
            return {
                "ids": ["g1"],
                "metadatas": [{"user_id": "other", "session_id": "",
                               "document_id": "d", "entity_ids": ""}],
                "documents": ["text " * 50],
            }

    svc.vector_store.collection = Coll()
    out = await svc._resolve_chunks(["g1"], user_id="", session_id="", semantic_seed=[])
    # Empty-string IDs are real scoping values: mismatched user drops the chunk.
    assert out == []


def test_rate_limiter_trusted_proxy_and_per_route():
    from app.utils.rate_limit import InMemoryRateLimiter

    lim = InMemoryRateLimiter(90, per_route_limits={"/auth": 2, "/chat": 1000})
    # Per-route budgets are independent.
    assert lim.limit_for("/auth/login") == 2
    assert lim.limit_for("/chat") == 1000
    assert lim.limit_for("/sessions") == 90
    assert lim.check_key("k", "/auth") is True
    assert lim.check_key("k", "/auth") is True
    assert lim.check_key("k", "/auth") is False
    # Same raw key on another route still has budget.
    assert lim.check_key("k", "/chat") is True


@pytest.mark.asyncio
async def test_rate_limiter_spoofed_xff_ignored_without_proxy():
    from app.utils.rate_limit import InMemoryRateLimiter, RateLimitMiddleware

    hits: list[bool] = []

    async def app(scope, receive, send):
        hits.append(True)

    mw = RateLimitMiddleware(app, InMemoryRateLimiter(1), exempt_paths=set())

    async def noop_receive():
        return {}

    statuses: list[int] = []

    async def send(msg):
        if "status" in msg:
            statuses.append(msg["status"])

    async def call(client, headers):
        await mw(
            {"type": "http", "path": "/chat", "client": client, "headers": headers},
            noop_receive,
            send,
        )

    # Occupy the direct-IP bucket, then try to bypass with a spoofed XFF
    # from a non-proxy peer: must still be 429 (XFF ignored).
    await call(("9.9.9.9", 1234), [])
    await call(("9.9.9.9", 1234), [(b"x-forwarded-for", b"1.2.3.4")])
    assert statuses == [429]
    assert hits == [True]


@pytest.mark.asyncio
async def test_rate_limiter_honors_xff_from_trusted_proxy():
    from app.utils.rate_limit import RateLimitMiddleware, InMemoryRateLimiter

    hits: list[bool] = []

    async def app(scope, receive, send):
        hits.append(True)

    mw = RateLimitMiddleware(app, InMemoryRateLimiter(1), exempt_paths=set())

    async def noop_receive():
        return {}

    statuses: list[int] = []

    async def send(msg):
        if "status" in msg:
            statuses.append(msg["status"])

    async def call(xff: bytes):
        await mw(
            {
                "type": "http",
                "path": "/chat",
                "client": ("127.0.0.1", 8000),
                "headers": [(b"x-forwarded-for", xff)],
            },
            noop_receive,
            send,
        )

    # Same proxy peer, distinct client IPs via XFF → distinct buckets, both pass.
    await call(b"203.0.113.7, 127.0.0.1")
    await call(b"203.0.113.8, 127.0.0.1")
    assert hits == [True, True]
    assert statuses == []


@pytest.mark.asyncio
async def test_document_parser_codes():
    from fastapi import UploadFile
    from fastapi import status as http_status

    from app.services.document_parser import DocumentParser

    parser = DocumentParser()

    class FakeUpload:
        filename = "evil.exe"
        size = 10

        async def read(self, *a, **k):
            return b"x" * 10

    try:
        await parser.parse_upload(FakeUpload(), 25)  # type: ignore[arg-type]
        raise AssertionError("expected 415")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    class BigUpload:
        filename = "big.txt"
        size = 999 * 1024 * 1024

        async def read(self, *a, **k):
            return b"x" * 10

    try:
        await parser.parse_upload(BigUpload(), 25)  # type: ignore[arg-type]
        raise AssertionError("expected 413 on declared size")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


def test_supabase_or_merges_rest_keys():
    from app.database import supabase as supa_mod

    captured: list[dict] = []

    class FakeQ:
        def __init__(self):
            self.filters: dict = {}

        def delete(self):
            return self

        def select(self, *a, **k):
            return self

        def table(self, name):
            return self

        def eq(self, k, v):
            self.filters[k] = v
            return self

        def limit(self, n):
            return self

        def execute(self):
            captured.append(dict(self.filters))
            return type("R", (), {"data": [{"_id": "x"}]})()

    # _apply_query_filters with merged dict must carry both rest + branch keys.
    q = FakeQ()
    supa_mod._apply_query_filters(q, {"session_id": "s", "a": 1})
    assert q.filters == {"session_id": "s", "a": 1}
    # $or itself is skipped by design (handled at delete_many level).
    q2 = FakeQ()
    supa_mod._apply_query_filters(q2, {"$or": [{"a": 1}], "session_id": "s"})
    assert q2.filters == {"session_id": "s"}


def test_greeting_threshold_lives_in_settings():
    assert float(_settings().greeting_confidence_threshold) == 0.45
    assert int(_settings().total_upload_max_mb) >= 100
    assert int(_settings().rate_limit_auth_per_minute) == 10
