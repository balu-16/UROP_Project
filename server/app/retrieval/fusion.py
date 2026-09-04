"""Reciprocal Rank Fusion (RRF) for hybrid retrieval.

Combines the vector (Chroma/cosine) and keyword (Postgres/ts_rank) ranked
lists using rank positions — raw scores are never added because cosine and
ts_rank live on incompatible scales.

Output contract per candidate::

    {
        "chunk_id": ...,
        "document_id": ...,
        "text": ...,
        "metadata": ...,
        "vector_score": float | None,    # cosine where available (THE gate input)
        "keyword_score": float | None,   # ts_rank where available
        "rrf_score": float,              # ordering key only — NEVER feed the 0.75 gate
        "retrieval_sources": ["vector"] | ["keyword"] | ["vector", "keyword"],
        "score": float,                  # = rrf_score (keeps ContextBuilder ordering correct)
    }

Pure function, no I/O — fully unit-testable.
"""
from typing import Any


def reciprocal_rank_fusion(
    vector_results: list[dict[str, Any]] | None,
    keyword_results: list[dict[str, Any]] | None,
    k: int = 60,
) -> list[dict[str, Any]]:
    """Fuse two ranked lists into one deduplicated, RRF-ordered candidate pool."""
    fused: dict[str, dict[str, Any]] = {}

    def _add(item: dict[str, Any], rank: int, source: str) -> None:
        chunk_id = item.get("chunk_id")
        if not chunk_id:
            return
        rrf = 1.0 / (float(k) + float(rank))
        existing = fused.get(chunk_id)
        if existing is None:
            merged = dict(item)
            merged["vector_score"] = item.get("score") if source == "vector" else None
            if source == "vector":
                merged["keyword_score"] = None
            else:
                merged["keyword_score"] = item.get("keyword_score", item.get("score"))
                if "text" not in merged and "content" in item:
                    merged["text"] = item.get("content")
            merged["rrf_score"] = rrf
            merged["score"] = rrf
            merged["retrieval_sources"] = [source]
            fused[chunk_id] = merged
            return
        existing["rrf_score"] = float(existing.get("rrf_score", 0.0)) + rrf
        existing["score"] = existing["rrf_score"]
        if source == "vector":
            if existing.get("vector_score") is None:
                existing["vector_score"] = item.get("score")
        else:
            if existing.get("keyword_score") is None:
                existing["keyword_score"] = item.get("keyword_score", item.get("score"))
        sources = existing.get("retrieval_sources") or []
        if source not in sources:
            sources = [*sources, source]
        existing["retrieval_sources"] = sources

    for rank, item in enumerate(vector_results or [], start=1):
        _add(item, rank, "vector")
    for rank, item in enumerate(keyword_results or [], start=1):
        _add(item, rank, "keyword")

    return sorted(fused.values(), key=lambda c: float(c.get("rrf_score", 0.0)), reverse=True)
