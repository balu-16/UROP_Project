import time
from typing import Any

import numpy as np

from app.config import Settings
from app.embeddings import EmbeddingService
from app.graph import EntityGraph
from app.vectorstore import VectorStore


class RetrievalOrchestrator:
    arms = ["standard_rag", "graph_rag_1hop", "graph_rag_2hop", "hybrid"]

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
        entity_graph: EntityGraph,
    ):
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.entity_graph = entity_graph

    async def prefetch(
        self, query: str, user_id: str | None = None
    ) -> tuple[np.ndarray, list[dict[str, Any]]]:
        vector = await self.embeddings.embed_query(query)
        return vector, self.vector_store.search(
            vector, self.settings.retrieval_top_k, user_id=user_id
        )

    async def retrieve(
        self,
        arm: str,
        query_vector: np.ndarray,
        prefetch_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        start = time.perf_counter()
        if arm == "standard_rag":
            chunks = prefetch_results
            expansion = {"hops": 0, "seed_entities": [], "expanded_entities": []}
        elif arm == "graph_rag_1hop":
            chunks, expansion = self._graph_expand(prefetch_results, hops=1)
        elif arm == "graph_rag_2hop":
            chunks, expansion = self._graph_expand(prefetch_results, hops=2)
        else:
            chunks, expansion = self._hybrid(prefetch_results)
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "arm": arm,
            "chunks": chunks[: self.settings.retrieval_top_k * 2],
            "diagnostics": {
                "latency_ms": latency_ms,
                "prefetch_count": len(prefetch_results),
                "returned_count": len(chunks),
                "graph_expansion": expansion,
            },
        }

    def _graph_expand(
        self, seeds: list[dict[str, Any]], hops: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        seed_ids = [item["chunk_id"] for item in seeds]
        expansion = self.entity_graph.expand_chunks(seed_ids, hops=hops)
        by_id = {item["chunk_id"]: dict(item) for item in self.vector_store.metadata}
        scored = {item["chunk_id"]: dict(item) for item in seeds}
        for chunk_id in expansion["chunk_ids"]:
            if chunk_id in scored or chunk_id not in by_id:
                continue
            item = by_id[chunk_id]
            item["score"] = 0.55
            item["graph_boost"] = True
            scored[chunk_id] = item
        chunks = sorted(
            scored.values(), key=lambda item: item.get("score", 0), reverse=True
        )
        return chunks, expansion

    def _hybrid(
        self, seeds: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        chunks, expansion = self._graph_expand(seeds[: max(2, len(seeds) // 2)], hops=1)
        seed_scores = {item["chunk_id"]: item.get("score", 0) for item in seeds}
        for chunk in chunks:
            semantic = seed_scores.get(chunk["chunk_id"], chunk.get("score", 0.45))
            graph_boost = 0.12 if chunk.get("graph_boost") else 0.0
            chunk["score"] = min(1.0, semantic + graph_boost)
        return sorted(
            chunks, key=lambda item: item.get("score", 0), reverse=True
        ), expansion
