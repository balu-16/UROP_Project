"""ThresholdRetrievalPolicy.

Deterministic threshold controller. No LLM, no DB access.
Receives confidence, returns RetrievalDecision.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from app.config import Settings


class RetrievalDepth(IntEnum):
    ZERO_HOP = 0
    ONE_HOP = 1
    TWO_HOP = 2


@dataclass
class RetrievalDecision:
    depth: int
    reason: str
    threshold: float
    confidence: float
    strategy: str  # ONE_HOP, ZERO_HOP etc for API

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "reason": self.reason,
            "threshold": self.threshold,
            "confidence": self.confidence,
            "strategy": self.strategy,
        }


class ThresholdRetrievalPolicy:
    """Deterministic policy per §16:

    Step 1: semantic retrieval
    Step 2: confidence = top score
    Step 3: if confidence >= HIGH_THRESHOLD → 0-hop else 1-hop
    Step 4: evaluate after 1-hop; if confidence >= HIGH_THRESHOLD → stay 1-hop else 2-hop (if allowed)
    Max hops = MAX_HOPS (default 2)
    """

    def __init__(self, settings: Settings):
        self.high = float(settings.high_threshold)
        self.low = float(settings.low_threshold)
        self.max_hops = int(settings.max_hops)

    def decide_initial(self, confidence: float) -> RetrievalDecision:
        if confidence >= self.high:
            return RetrievalDecision(
                depth=RetrievalDepth.ZERO_HOP,
                reason="semantic_confidence_above_high_threshold",
                threshold=self.high,
                confidence=confidence,
                strategy="ZERO_HOP",
            )
        # below high → need graph expansion
        return RetrievalDecision(
            depth=RetrievalDepth.ONE_HOP,
            reason="semantic_confidence_below_threshold",
            threshold=self.high,
            confidence=confidence,
            strategy="ONE_HOP",
        )

    def decide_after_one_hop(self, confidence: float, previous_confidence: float) -> RetrievalDecision:
        if confidence >= self.high:
            return RetrievalDecision(
                depth=RetrievalDepth.ONE_HOP,
                reason="one_hop_confidence_sufficient",
                threshold=self.high,
                confidence=confidence,
                strategy="ONE_HOP",
            )
        if self.max_hops >= 2:
            return RetrievalDecision(
                depth=RetrievalDepth.TWO_HOP,
                reason="one_hop_confidence_insufficient",
                threshold=self.high,
                confidence=confidence,
                strategy="TWO_HOP",
            )
        return RetrievalDecision(
            depth=RetrievalDepth.ONE_HOP,
            reason="max_hops_reached",
            threshold=self.high,
            confidence=confidence,
            strategy="ONE_HOP",
        )
