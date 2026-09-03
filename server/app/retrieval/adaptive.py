"""AdaptiveRetrievalService — §41 orchestrator.

Orchestrates: Semantic (Chroma) → Confidence → ThresholdPolicy → Graph (PG) → Context
"""
import time
from typing import Any

import numpy as np

from app.config import Settings
from app.embeddings import EmbeddingService
from app.graph_store.pg_store import PGGraphStore
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from app.retrieval.policy import ThresholdRetrievalPolicy
from app.services.context import ContextBuilder
from app.vectorstore import VectorStore
from app.utils.logging import get_logger

logger = get_logger(__name__)


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
    ):
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.confidence_evaluator = confidence_evaluator or RetrievalConfidenceEvaluator()
        self.policy = policy or ThresholdRetrievalPolicy(settings)
        self.context_builder = context_builder or ContextBuilder(settings)

    async def retrieve(
        self, query: str, user_id: str | None = None, session_id: str | None = None
    ) -> dict[str, Any]:
        """Full adaptive flow per §16:
        1. semantic search (scoped to this user + chat session)
        2. confidence
        3. if confidence >= HIGH → 0-hop
           else 1-hop → evaluate → if < HIGH then 2-hop (if max_hops>=2)
        A session only ever retrieves chunks carrying its own session_id.
        Returns: {chunks, context, retrieval{depth,confidence,strategy,scores}, diagnostics}
        """
        start = time.perf_counter()
        request_id = None
        # 1. Semantic retrieval (session-scoped)
        query_vector = await self.embeddings.embed_query(query)
        semantic_results = self.vector_store.search(
            query_vector, self.settings.top_k, user_id=user_id, session_id=session_id
        )
        initial_conf = self.confidence_evaluator.evaluate(semantic_results)
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
            context_payload = self.context_builder.build(semantic_results)
            diagnostics = {
                "latency_ms": (time.perf_counter() - start) * 1000,
                "semantic_count": len(semantic_results),
                "graph_nodes": 0,
                "confidence": initial_conf,
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
                },
                "diagnostics": diagnostics,
                "semantic_results": semantic_results,
            }

        # 1-hop (graph walk constrained to this session's chunks)
        seed_ids = [r["chunk_id"] for r in semantic_results]
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

        # Merge semantic + expanded (dedup, keep highest score)
        merged_1 = self._merge(semantic_results, expanded_chunks_1)
        conf_1 = self.confidence_evaluator.evaluate_after_expansion(merged_1, initial_conf)
        decision_1 = self.policy.decide_after_one_hop(conf_1, initial_conf)

        if decision_1.depth == 1:
            context_payload = self.context_builder.build(merged_1)
            diagnostics = {
                "latency_ms": (time.perf_counter() - start) * 1000,
                "semantic_count": len(semantic_results),
                "expanded_count": len(expanded_chunks_1),
                "merged_count": len(merged_1),
                "graph_nodes": len(expansion_1.get("expanded_entities", [])),
                "confidence": conf_1,
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
        merged_2 = self._merge(semantic_results, expanded_chunks_2)
        # Also merge with 1-hop results for completeness
        merged_2 = self._merge(merged_2, expanded_chunks_1)
        conf_2 = self.confidence_evaluator.evaluate_after_expansion(merged_2, conf_1)
        context_payload = self.context_builder.build(merged_2)
        diagnostics = {
            "latency_ms": (time.perf_counter() - start) * 1000,
            "semantic_count": len(semantic_results),
            "expanded_count": len(expanded_chunks_2),
            "merged_count": len(merged_2),
            "graph_nodes": len(expansion_2.get("expanded_entities", [])),
            "confidence": conf_2,
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
                "decision": decision_1.to_dict(),
            },
            "diagnostics": diagnostics,
            "semantic_results": semantic_results,
            "expansion": expansion_2,
        }

    async def _session_chunk_ids(
        self, user_id: str | None, session_id: str | None, seed_ids: list[str]
    ) -> set[str] | None:
        """Chunk IDs belonging to this chat session (the graph allow-list).

        Read from the Chroma index, which carries user_id + session_id on
        every point. Returns None only when no session scoping applies.
        """
        if not session_id:
            return None
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
                        if user_id and meta.get("user_id") != user_id:
                            continue
                        if session_id and meta.get("session_id") != session_id:
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
                if user_id and meta.get("user_id") != user_id:
                    continue
                if session_id and meta.get("session_id") != session_id:
                    continue
                item = dict(meta)
                item["score"] = 0.55
                item["graph_boost"] = True
                out.append(item)
        return out

    def _merge(self, a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for item in a:
            seen[item["chunk_id"]] = dict(item)
        for item in b:
            cid = item["chunk_id"]
            if cid in seen:
                # keep higher score
                if item.get("score", 0) > seen[cid].get("score", 0):
                    seen[cid] = dict(item)
            else:
                seen[cid] = dict(item)
        # Sort by score descending
        return sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)
