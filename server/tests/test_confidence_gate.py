"""Regression tests pinning the confidence gate BEFORE hybrid retrieval lands.

The 0.75 gate must only ever see vector/cosine similarity. RRF scores live on
a ~0-0.03 scale and must never reach the gate, or every query would fall
through to 2-hop. These tests pin current behavior; Stage 1 extends them with
fused (vector_score + rrf_score) candidate shapes.
"""

from app.config.settings import Settings
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from app.retrieval.policy import ThresholdRetrievalPolicy


def _settings() -> Settings:
    return Settings()


def test_high_vector_confidence_selects_zero_hop():
    policy = ThresholdRetrievalPolicy(_settings())
    decision = policy.decide_initial(0.8)
    assert decision.depth == 0
    assert decision.strategy == "ZERO_HOP"


def test_confidence_evaluator_uses_max_score():
    evaluator = RetrievalConfidenceEvaluator()
    results = [
        {"chunk_id": "a", "score": 0.8},
        {"chunk_id": "b", "score": 0.01},  # RRF-scale value must never win
    ]
    assert evaluator.evaluate(results) == 0.8


def test_low_confidence_traverses_one_then_two_hop():
    policy = ThresholdRetrievalPolicy(_settings())
    first = policy.decide_initial(0.5)
    assert first.depth == 1
    assert first.strategy == "ONE_HOP"
    second = policy.decide_after_one_hop(0.5, 0.5)
    assert second.depth == 2
    assert second.strategy == "TWO_HOP"


def test_empty_results_yield_zero_confidence():
    assert RetrievalConfidenceEvaluator().evaluate([]) == 0.0
