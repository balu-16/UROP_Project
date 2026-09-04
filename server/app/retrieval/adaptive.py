"""AdaptiveRetrievalService — §41 orchestrator.

Orchestrates: Hybrid (Chroma vector + PG keyword → RRF) → Confidence
(vector cosine only) → ThresholdPolicy → Graph (PG) → [Stage 2: Rerank] → Context
"""
import time
from typing import Any

import numpy as np

from app.config import Settings
from app.embeddings import EmbeddingService
from app.graph_store.pg_store import PGGraphStore
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.policy import RetrievalDecision, ThresholdRetrievalPolicy
from app.retrieval.reranking import NullReranker, Reranker, timed_rerank
from app.services.context import ContextBuilder
from app.vectorstore import VectorStore
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _dedup_preserve_order(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by chunk_id keeping first-seen order (no re-sorting).

    Preserves fused RRF order for seeds followed by graph-expansion order —
    the final pre-rerank ordering. RRF and cosine scales are never compared.
    """
    seen: dict[str, dict[str, Any]] = {}
    for items in lists:
        for item in items:
            cid = item.get("chunk_id")
            if not cid or cid in seen:
                continue
            seen[cid] = item
    return list(seen.values())


class AdaptiveRetrievalService:
    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
        graph_store: PGGraphStore,
        confidence_evaluator: RetrievalConfidenceEvaluator | None = None,
        policy: ThresholdRetrievalPolicy | None = None,
        context_builder: ContextBuilder | None = None,
        keyword_retriever: KeywordRetriever | None = None,
        reranker: Reranker | None = None,
    ):
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.confidence_evaluator = confidence_evaluator or RetrievalConfidenceEvaluator()
        self.policy = policy or ThresholdRetrievalPolicy(settings)
        self.context_builder = context_builder or ContextBuilder(settings)
        self.keyword_retriever = keyword_retriever
        self.reranker = reranker or NullReranker("not_configured")

    async def retrieve(
        self, query: str, user_id: str | None = None, session_id: str | None = None
    ) -> dict[str, Any]:
        """Full adaptive flow per §16 + hybrid RRF (Stage 1):
        1. vector search (VECTOR_TOP_K) + keyword search (KEYWORD_TOP_K),
           both session-scoped
        2. RRF fusion → candidate pool (ordering only)
        3. confidence on fused pool reads vector cosine (gate unchanged);
           if confidence >= HIGH → 0-hop
            else 1-hop → evaluate → if < HIGH then 2-hop (if max_hops>=2)
        4. expansion seeds = top-`top_k` fused chunk_ids (breadth unchanged)
        A session only ever retrieves chunks carrying its own session_id.
        Returns: {chunks, context, retrieval{depth,confidence,strategy,scores}, diagnostics}
        """
        start = time.perf_counter()
        request_id = None
        # Fail-closed: chat retrieval requires a session. Without one the
        # allow-list would be None (unfiltered), so return an empty pool
        # instead of leaking cross-session chunks. The SSE layer still
        # reports this as a 200 error event (streaming contract preserved).
        if not session_id:
            logger.warning("retrieval without session_id — returning empty (fail-closed)")
            empty_diagnostics: dict[str, Any] = {
                "reranker_enabled": False,
                "reranker_model": None,
                "reranker_reason": "no_session",
                "rerank_candidate_count": 0,
                "reranked_count": 0,
                "rerank_latency_ms": 0.0,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "semantic_count": 0,
                "keyword_count": 0,
                "fused_count": 0,
                "expanded_count": 0,
                "merged_count": 0,
                "graph_nodes": 0,
                "confidence": 0.0,
                "depth": 0,
                "strategy": "ZERO_HOP",
                "fail_closed": True,
            }
            return {
                "chunks": [],
                "context": "",
                "token_count": 0,
                "retrieval": {
                    "depth": 0,
                    "confidence": 0.0,
                    "initial_confidence": 0.0,
                    "strategy": "ZERO_HOP",
                    "decision": {
                        "depth": 0,
                        "reason": "missing_session_id",
                        "threshold": self.policy.high,
                        "confidence": 0.0,
                        "strategy": "ZERO_HOP",
                    },
                    "retrieval_mode": "hybrid",
                    "candidate_count": 0,
                    "reranked_count": 0,
                    "reranker_model": None,
                },
                "diagnostics": empty_diagnostics,
                "semantic_results": [],
            }
        # 1. Hybrid retrieval (both branches session-scoped)
        query_vector = await self.embeddings.embed_query(query)
        semantic_results = self.vector_store.search(
            query_vector, self.settings.vector_top_k, user_id=user_id, session_id=session_id
        )
        keyword_results = await self._keyword_search(query, user_id, session_id)
        fused = reciprocal_rank_fusion(
            semantic_results, keyword_results, k=self.settings.rrf_k
        )
        initial_conf = self.confidence_evaluator.evaluate(fused)
        decision = self.policy.decide_initial(initial_conf)

        logger.info(
            "retrieval query_id=%s initial_score=%.3f depth=%s strategy=%s",
            request_id,
            initial_conf,
            decision.depth,
            decision.strategy,
        )

        # 0-hop
        if decision.depth == 0:
            reranked, rerank_info = await self._apply_rerank(query, fused)
            # Preserve RRF order when the reranker did not run: fused RRF
            # scores (~0-0.03) must not be score-sorted against graph defaults.
            context_payload = self.context_builder.build(
                reranked, preserve_order=not rerank_info.get("reranker_enabled", False)
            )
            diagnostics = {
                **rerank_info,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "semantic_count": len(semantic_results),
                "keyword_count": len(keyword_results),
                "fused_count": len(fused),
                "expanded_count": 0,
                "merged_count": len(fused),
                "graph_nodes": 0,
                "confidence": initial_conf,
                "depth": 0,
                "strategy": "ZERO_HOP",
                "retrieval_mode": "hybrid",
                "candidate_count": len(fused),
            }
            return {
                "chunks": context_payload["chunks"],
                "context": context_payload["context"],
                "token_count": context_payload["token_count"],
                "retrieval": {
                    "depth": 0,
                    "confidence": initial_conf,
                    "initial_confidence": initial_conf,
                    "strategy": "ZERO_HOP",
                    "decision": decision.to_dict(),
                    "retrieval_mode": "hybrid",
                    "candidate_count": len(fused),
                    "reranked_count": rerank_info["reranked_count"],
                    "reranker_model": rerank_info["reranker_model"],
                },
                "diagnostics": diagnostics,
                "semantic_results": semantic_results,
            }

        # 1-hop (graph walk constrained to this session's chunks).
        # Seeds are the top fused candidates (RRF order mixes vector + keyword
        # evidence); breadth matches the old top_k semantic seeds.
        seed_ids = [r["chunk_id"] for r in fused[: self.settings.top_k] if r.get("chunk_id")]
        allowed_ids = await self._session_chunk_ids(user_id, session_id, seed_ids)
        expansion_1 = await self.graph_store.expand_chunks(
            seed_ids,
            hops=1,
            max_entities=self.settings.max_graph_nodes,
            max_chunks=200,
            allowed_chunk_ids=allowed_ids,
        )
        # Need to fetch expanded chunk metadata for scoring.
        # Use the vector store's underlying collection to get docs by ids.
        expanded_chunks_1 = await self._resolve_chunks(
            expansion_1["chunk_ids"], user_id, session_id, semantic_results
        )

        # Merge fused seeds + expanded (order-preserving: RRF order first,
        # then expansion order — scales are never compared or re-sorted).
        merged_1 = _dedup_preserve_order(fused, expanded_chunks_1)
        conf_1 = self.confidence_evaluator.evaluate_after_expansion(merged_1, initial_conf)
        decision_1 = self.policy.decide_after_one_hop(conf_1, initial_conf)

        if decision_1.depth == 1:
            reranked_1, rerank_info_1 = await self._apply_rerank(query, merged_1)
            context_payload = self.context_builder.build(
                reranked_1, preserve_order=not rerank_info_1.get("reranker_enabled", False)
            )
            diagnostics = {
                **rerank_info_1,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "semantic_count": len(semantic_results),
                "keyword_count": len(keyword_results),
                "fused_count": len(fused),
                "expanded_count": len(expanded_chunks_1),
                "merged_count": len(merged_1),
                "graph_nodes": len(expansion_1.get("expanded_entities", [])),
                "confidence": conf_1,
                "depth": 1,
                "strategy": "ONE_HOP",
                "retrieval_mode": "hybrid",
                "candidate_count": len(merged_1),
            }
            return {
                "chunks": context_payload["chunks"],
                "context": context_payload["context"],
                "token_count": context_payload["token_count"],
                "retrieval": {
                    "depth": 1,
                    "confidence": conf_1,
                    "initial_confidence": initial_conf,
                    "strategy": "ONE_HOP",
                    "decision": decision_1.to_dict(),
                    "retrieval_mode": "hybrid",
                    "candidate_count": len(merged_1),
                    "reranked_count": rerank_info_1["reranked_count"],
                    "reranker_model": rerank_info_1["reranker_model"],
                },
                "diagnostics": diagnostics,
                "semantic_results": semantic_results,
                "expansion": expansion_1,
            }

        # 2-hop (same session constraint)
        expansion_2 = await self.graph_store.expand_chunks(
            seed_ids,
            hops=2,
            max_entities=self.settings.max_graph_nodes,
            max_chunks=200,
            allowed_chunk_ids=allowed_ids,
        )
        expanded_chunks_2 = await self._resolve_chunks(
            expansion_2["chunk_ids"], user_id, session_id, semantic_results
        )
        merged_2 = _dedup_preserve_order(fused, expanded_chunks_2)
        # Also merge with 1-hop results for completeness
        merged_2 = _dedup_preserve_order(merged_2, expanded_chunks_1)
        conf_2 = self.confidence_evaluator.evaluate_after_expansion(merged_2, conf_1)
        # Final decision for the 2-hop branch: same reason as the 1-hop
        # insufficiency that forced expansion, but with final confidence.
        # (Previously decision_1 was reused verbatim, reporting stale confidence.)
        decision_2 = RetrievalDecision(
            depth=2,
            reason=decision_1.reason,
            threshold=decision_1.threshold,
            confidence=conf_2,
            strategy="TWO_HOP",
        )
        reranked_2, rerank_info_2 = await self._apply_rerank(query, merged_2)
        context_payload = self.context_builder.build(
            reranked_2, preserve_order=not rerank_info_2.get("reranker_enabled", False)
        )
        # expanded_count covers both hop outputs (merged_2 includes 1-hop + 2-hop).
        all_expanded = _dedup_preserve_order(expanded_chunks_1, expanded_chunks_2)
        diagnostics = {
            **rerank_info_2,
            "latency_ms": (time.perf_counter() - start) * 1000,
            "semantic_count": len(semantic_results),
            "keyword_count": len(keyword_results),
            "fused_count": len(fused),
            "expanded_count": len(all_expanded),
            "merged_count": len(merged_2),
            "graph_nodes": len(expansion_2.get("expanded_entities", [])),
            "confidence": conf_2,
            "depth": 2,
            "strategy": "TWO_HOP",
            "retrieval_mode": "hybrid",
            "candidate_count": len(merged_2),
        }
        return {
            "chunks": context_payload["chunks"],
            "context": context_payload["context"],
            "token_count": context_payload["token_count"],
            "retrieval": {
                "depth": 2,
                "confidence": conf_2,
                "initial_confidence": initial_conf,
                "strategy": "TWO_HOP",
                "decision": decision_2.to_dict(),
                "retrieval_mode": "hybrid",
                "candidate_count": len(merged_2),
                "reranked_count": rerank_info_2["reranked_count"],
                "reranker_model": rerank_info_2["reranker_model"],
            },
            "diagnostics": diagnostics,
            "semantic_results": semantic_results,
            "expansion": expansion_2,
        }

    async def _apply_rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Cap → rerank → top-K slice, with graceful fallback.

        Ordering guarantee (pinned by tests): the reranker only ever sees the
        post-hop candidate pool, so it can never execute before graph
        expansion. On any failure the pre-rerank order is used and the request
        continues — a reranker must never crash a chat turn.
        """
        pool = list(candidates or [])
        cap = max(1, int(self.settings.rerank_candidate_cap))
        top_k = max(1, int(self.settings.rerank_top_k))
        shortlist = pool[:cap]
        reranker = self.reranker or NullReranker("not_configured")
        info: dict[str, Any] = {
            "reranker_enabled": bool(getattr(reranker, "applied", False)),
            "reranker_model": getattr(reranker, "model_name", None),
            "reranker_reason": getattr(reranker, "reason", None),
            "rerank_candidate_count": len(shortlist),
            "reranked_count": 0,
            "rerank_latency_ms": 0.0,
        }
        try:
            ranked, latency_ms = await timed_rerank(reranker, query, shortlist)
            info["rerank_latency_ms"] = latency_ms
        except Exception:
            logger.exception("rerank failed, falling back to pre-rerank order")
            ranked = shortlist
            info["reranker_enabled"] = False
            info["reranker_reason"] = "runtime_error"
        if not isinstance(ranked, list):
            logger.warning("reranker returned non-list; falling back to pre-rerank order")
            ranked = shortlist
            info["reranker_enabled"] = False
            info["reranker_reason"] = "runtime_error"
        final = list(ranked[:top_k])
        info["reranked_count"] = len(final)
        return final, info

    async def _keyword_search(
        self, query: str, user_id: str | None, session_id: str | None
    ) -> list[dict[str, Any]]:
        """Lexical branch of hybrid retrieval. Never raises: degradation is
        an empty list (vector-only continuation), never a failed request."""
        retriever = self.keyword_retriever
        if retriever is None:
            return []
        try:
            results = await retriever.search(
                query, user_id, session_id, self.settings.keyword_top_k
            )
            return list(results or [])
        except Exception:
            logger.exception("keyword search failed, continuing vector-only")
            return []

    async def _session_chunk_ids(
        self, user_id: str | None, session_id: str | None, seed_ids: list[str]
    ) -> set[str]:
        """Chunk IDs belonging to this chat session (the graph allow-list).

        Read from the Chroma index, which carries user_id + session_id on
        every point. Fail-closed: without a session_id returns an empty set
        so graph expansion yields seeds only (never unfiltered).
        """
        if not session_id:
            return set()
        try:
            vs = self.vector_store
            if hasattr(vs, "collection") and vs.collection is not None:
                clauses: list[dict[str, Any]] = [{"session_id": session_id}]
                if user_id is not None:
                    clauses.append({"user_id": user_id})
                where = {"$and": clauses} if len(clauses) > 1 else clauses[0]
                res = vs.collection.get(where=where, limit=100000)
                ids = set(res.get("ids", []) if res else [])
                return ids | set(seed_ids)
        except Exception:
            pass
        return set(seed_ids)

    async def _resolve_chunks(
        self,
        chunk_ids: list[str],
        user_id: str | None,
        session_id: str | None,
        semantic_seed: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Resolve chunk_ids to chunk dicts (with text, metadata, score).
        Uses vector_store's collection.get for Chroma, fallback to semantic_seed map.
        Drops any chunk outside this user + chat session.
        """
        # Build map from semantic results for fast lookup (they already have scores)
        seed_map = {c["chunk_id"]: c for c in semantic_seed}
        out: list[dict[str, Any]] = []
        # Try Chroma get
        try:
            vs = self.vector_store
            if hasattr(vs, "collection") and vs.collection is not None:
                # Chroma get by ids
                res = vs.collection.get(ids=chunk_ids, include=["metadatas", "documents"])
                if res and res.get("ids"):
                    for cid, meta, doc in zip(res["ids"], res["metadatas"], res["documents"]):
                        if cid in seed_map:
                            continue
                        # Session + user isolation: get() ignores where-clauses,
                        # so verify every expanded chunk belongs to this chat.
                        # Explicit `is not None` — empty-string IDs still filter.
                        if user_id is not None and meta.get("user_id") != user_id:
                            continue
                        if session_id is not None and meta.get("session_id") != session_id:
                            continue
                        inner = {k: v for k, v in meta.items() if k not in ("user_id", "session_id", "document_id", "chunk_id", "entity_ids")}
                        entity_ids = [e for e in meta.get("entity_ids", "").split(",") if e]
                        out.append(
                            {
                                "chunk_id": cid,
                                "document_id": meta.get("document_id", ""),
                                "text": doc,
                                "metadata": inner,
                                "entity_ids": entity_ids,
                                "score": 0.55,  # graph boost default
                                "user_id": meta.get("user_id", ""),
                                "session_id": meta.get("session_id", ""),
                                "graph_boost": True,
                            }
                        )
                    return out
        except Exception:
            pass
        # Fallback: a vector store exposing a metadata list can resolve ids here;
        # ChromaVectorStore has no such list, so this usually stays empty.
        if hasattr(self.vector_store, "metadata") and isinstance(self.vector_store.metadata, list):
            by_id = {m.get("chunk_id"): m for m in self.vector_store.metadata}
            for cid in chunk_ids:
                if cid in seed_map:
                    continue
                meta = by_id.get(cid)
                if not meta:
                    continue
                if user_id is not None and meta.get("user_id") != user_id:
                    continue
                if session_id is not None and meta.get("session_id") != session_id:
                    continue
                item = dict(meta)
                item["score"] = 0.55
                item["graph_boost"] = True
                out.append(item)
        return out


