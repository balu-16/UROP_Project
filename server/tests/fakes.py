"""Shared test doubles (never imported by production code)."""

from typing import Any


class FakeKeywordRetriever:
    """In-memory keyword retriever for unit tests (MEMORY:// can't run SQL)."""

    def __init__(self, results: list[dict[str, Any]] | None = None):
        self._results = results or []
        self.calls: list[dict[str, Any]] = []

    async def search(
        self,
        query: str,
        user_id: str | None,
        session_id: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {"query": query, "user_id": user_id, "session_id": session_id, "top_k": top_k}
        )
        return [dict(r) for r in self._results[: max(0, int(top_k))]]
