"""Keyword retrieval over Postgres full-text search (migration 002).

Provides the lexical half of hybrid retrieval: exact words, document names,
IDs, version numbers, technical terms. Runs through the ``match_chunks_fts``
RPC (``websearch_to_tsquery`` + ``ts_rank`` + GIN index) — never raw table
scans, never cross-session.

Session isolation mirrors the vector path: results are restricted to chunks
carrying this chat's ``session_id`` (see migration 002), the same guarantee
``AdaptiveRetrievalService._session_chunk_ids`` enforces for Chroma.
"""
from typing import Any, Callable, Protocol

from app.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# RPC deployed by supabase/migrations/002_fts_keyword.sql
MATCH_CHUNKS_RPC = "match_chunks_fts"


class KeywordRetriever(Protocol):
    """Lexical search contract. Implementations must never leak other sessions."""

    async def search(
        self,
        query: str,
        user_id: str | None,
        session_id: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Return [{chunk_id, document_id, text, metadata, keyword_score}]."""
        ...


RpcCaller = Callable[[str, dict[str, Any]], Any]


class PostgresKeywordRetriever:
    """Postgres FTS keyword retriever via the ``match_chunks_fts`` RPC.

    ``rpc`` dependency-injects the call so unit tests can pass a fake and the
    live path passes a thin wrapper over the Supabase client. When no client
    is available (memory-DB tests, offline mode) every search degrades to an
    empty list — retrieval continues vector-only, never crashes.
    """

    def __init__(self, settings: Settings, rpc: RpcCaller | None = None):
        self.settings = settings
        self._rpc = rpc
        self._warned_no_client = False

    async def search(
        self,
        query: str,
        user_id: str | None,
        session_id: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []
        if self._rpc is None:
            if not self._warned_no_client:
                self._warned_no_client = True
                logger.warning("keyword search unavailable (no PG client) — vector-only")
            return []
        try:
            rows = self._rpc(
                MATCH_CHUNKS_RPC,
                {
                    "p_query": query,
                    "p_session_id": session_id,
                    "p_user_id": user_id,
                    "p_limit": max(1, int(top_k)),
                },
            )
        except Exception as exc:
            logger.warning("keyword search failed, continuing vector-only: %s", exc)
            return []
        results: list[dict[str, Any]] = []
        for row in rows or []:
            chunk_id = row.get("chunk_id")
            if not chunk_id:
                continue
            results.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": str(row.get("document_id") or ""),
                    "text": row.get("content") or "",
                    "metadata": row.get("metadata") or {},
                    "keyword_score": float(row.get("rank") or 0.0),
                }
            )
        return results


def supa_rpc_caller(supa_client: Any) -> RpcCaller:
    """Adapt a supabase-py client to the ``RpcCaller`` contract."""

    def call(fn: str, params: dict[str, Any]) -> Any:
        response = supa_client.rpc(fn, params).execute()
        return response.data

    return call


def extract_supa_client(db: Any) -> Any | None:
    """Best-effort Supabase client extraction (same duck-typing as ingestion).

    Returns None for memory-DB / offline environments — callers degrade.
    """
    try:
        inner = getattr(db, "db", None)
        client = getattr(inner, "client", None)
        return client
    except Exception:
        return None



