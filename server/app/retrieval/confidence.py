"""RetrievalConfidenceEvaluator — §17.

Isolates confidence logic behind an abstraction so it can evolve
without changing the rest of the retrieval pipeline.
V1: confidence = topResultSimilarity (max score of semantic results).
Future: top-k avg, score distribution, margin, coverage, reranker.
"""
from typing import Any


class RetrievalConfidenceEvaluator:
    def evaluate(self, semantic_results: list[dict[str, Any]]) -> float:
        """Return confidence in [0,1]. Higher = more confident."""
        if not semantic_results:
            return 0.0
        scores = [float(r.get("score", 0.0)) for r in semantic_results]
        # V1: top similarity
        confidence = max(scores) if scores else 0.0
        # Clamp
        return float(max(0.0, min(1.0, confidence)))

    def evaluate_after_expansion(
        self, expanded_chunks: list[dict[str, Any]], previous_confidence: float
    ) -> float:
        """Confidence after graph expansion. V1: max of expanded scores."""
        if not expanded_chunks:
            return previous_confidence
        scores = [float(c.get("score", 0.0)) for c in expanded_chunks]
        new_conf = max(scores) if scores else previous_confidence
        # Slight boost if expansion added chunks, but cap at 1.0
        return float(max(previous_confidence, min(1.0, new_conf)))
