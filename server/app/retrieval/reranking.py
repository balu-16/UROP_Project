"""Cross-encoder reranking (Stage 2). Runs AFTER 0/1/2-hop, never before.

The reranker re-grades the final retrieved candidate set (fused seeds +
graph expansion, capped) with a pretrained cross-encoder and returns the
top-K for the context builder. Scores are raw relevance logits for sorting
only — never calibrated probabilities, never displayed as percentages.

Failure contract: the reranker must never crash a request. Load failures
degrade to :class:`NullReranker` at boot; runtime failures fall back to the
pre-rerank order inside ``AdaptiveRetrievalService._apply_rerank``.
"""
import asyncio
import time
from typing import Any, Protocol

from app.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Locked model (see thinking.md §3): L6 matches L12 quality at ~2x speed.
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker(Protocol):
    """Relevance re-grading contract."""

    applied: bool
    """True when this reranker actually re-scores; False for passthrough."""

    async def rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return candidates sorted by relevance (desc).

        Implementations must not raise: on any model/predict failure return
        the input order unchanged so a reranker never crashes a chat turn.
        """
        ...


class NullReranker:
    """Passthrough used when reranking is disabled, unavailable, or failed.

    New (Stage 2) — there was no pre-existing NullReranker. Returns inputs
    untouched so every caller path stays identical with or without a model.
    """

    applied = False

    def __init__(self, reason: str = "disabled"):
        self.reason = reason
        self.model_name: str | None = None

    async def rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return list(candidates or [])


class CrossEncoderReranker:
    """Pretrained cross-encoder reranker (MiniLM-L6 default).

    ``model`` injects a preloaded stand-in (unit tests) to skip the download.
    Scores are raw logits; each returned item gains ``rerank_score`` and takes
    it as ``score`` (documented post-rerank scale — see thinking.md §4).
    """

    applied = True

    def __init__(
        self,
        settings: Settings,
        model_name: str | None = None,
        model: Any | None = None,
    ):
        self.settings = settings
        self.model_name = model_name or settings.reranker_model or DEFAULT_RERANKER_MODEL
        self._model = model

    def load(self) -> None:
        """Load the model now (raises on failure — factory converts to Null)."""
        if self._model is not None:
            return
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self.model_name)

    async def rerank(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        pool = list(candidates or [])
        if not pool:
            return []
        try:
            if self._model is None:
                self.load()
            pairs = [[query, str(c.get("text", "") or "")] for c in pool]
            logits = await asyncio.to_thread(self._model.predict, pairs)
        except Exception as exc:
            logger.warning("cross-encoder rerank failed (%s) — keeping pre-rerank order", exc)
            return pool
        logit_list = list(logits) if logits is not None else []
        # Length mismatch: pad short with 0.0, truncate long — no candidate
        # is ever silently dropped or duplicated.
        if len(logit_list) < len(pool):
            logit_list = list(logit_list) + [0.0] * (len(pool) - len(logit_list))
        else:
            logit_list = list(logit_list[: len(pool)])
        scored: list[dict[str, Any]] = []
        for item, logit in zip(pool, logit_list):
            out = dict(item)
            try:
                value = float(logit)
            except (TypeError, ValueError):
                value = 0.0
            out["rerank_score"] = value
            out["score"] = value
            scored.append(out)
        # Stable sort: ties keep pre-rerank (fused/expansion) order.
        scored.sort(key=lambda c: float(c.get("rerank_score", 0.0)), reverse=True)
        return scored


def build_reranker(settings: Settings) -> Reranker:
    """Select the reranker. Never raises — worst case is NullReranker."""
    if not settings.reranker_enabled:
        return NullReranker("reranker_disabled")
    if settings.disable_local_models:
        return NullReranker("local_models_disabled")
    try:
        reranker = CrossEncoderReranker(settings)
        reranker.load()
        logger.info("reranker loaded: %s", reranker.model_name)
        return reranker
    except Exception as exc:
        logger.warning("reranker unavailable (%s) — continuing without reranking", exc)
        return NullReranker(f"load_failed: {exc}")


async def timed_rerank(
    reranker: Reranker, query: str, candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], float]:
    """Run rerank and report latency in ms (telemetry helper)."""
    start = time.perf_counter()
    ranked = await reranker.rerank(query, candidates)
    return ranked, (time.perf_counter() - start) * 1000.0
