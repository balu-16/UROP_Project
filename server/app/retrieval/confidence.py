"""RetrievalConfidenceEvaluator — §17.

Isolates confidence logic behind an abstraction so it can evolve
without changing the rest of the retrieval pipeline.
V1: confidence = topResultSimilarity (max score of semantic results).

HYBRID CONTRACT (Stage 1): the gate reads ``vector_score`` (cosine) when
present and falls back to ``score`` for legacy inputs. RRF scores (~0-0.03)
must never reach the 0.75 gate or every query would fall through to 2-hop —
see tests/test_confidence_gate.py + test_hybrid_retrieval.py.
Future: top-k avg, score distribution, margin, coverage, reranker.
"""
from typing import Any


def _gate_score(item: dict[str, Any]) -> float:
    value = item.get("vector_score", item.get("score", 0.0))
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


class RetrievalConfidenceEvaluator:
    def evaluate(self, semantic_results: list[dict[str, Any]]) -> float:
        """Return confidence in [0,1]. Higher = more confident."""
        if not semantic_results:
            return 0.0
        scores = [_gate_score(r) for r in semantic_results]
        # V1: top similarity
        confidence = max(scores) if scores else 0.0
        # Clamp
        return float(max(0.0, min(1.0, confidence)))

    def evaluate_after_expansion(
        self, expanded_chunks: list[dict[str, Any]], previous_confidence: float
    ) -> float:
        """Confidence after graph expansion. V1: max of expanded scores.

        QUIRK (preserved): graph chunks carry score 0.55 and fused seeds that
        reached expansion are <0.75 by construction, so with HIGH=0.75 this
        can never reach the gate — every expansion currently proceeds to
        2-hop. Preserved as-is; recalibrate after telemetry.
        """
        if not expanded_chunks:
            return previous_confidence
        scores = [_gate_score(c) for c in expanded_chunks]
        new_conf = max(scores) if scores else previous_confidence
        # Slight boost if expansion added chunks, but cap at 1.0
        return float(max(previous_confidence, min(1.0, new_conf)))
