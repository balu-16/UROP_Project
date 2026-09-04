from app.config import Settings
from app.services.chunking import count_tokens


class ContextBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build(self, chunks: list[dict], preserve_order: bool = False) -> dict:
        """Assemble LLM context from ranked chunks.

        When ``preserve_order`` is True the input order (RRF fusion /
        pre-rerank order) is kept as-is; otherwise chunks are sorted by
        ``score`` desc. ``preserve_order`` must be True whenever the
        reranker did NOT run (NullReranker passthrough): fused ``score`` is
        an RRF value (~0-0.03) while graph chunks carry ``0.55``, so sorting
        would destroy RRF order and always float graph chunks on top.
        Post-rerank ``score`` is a cross-encoder logit and sorting is correct.
        """
        seen = set()
        selected = []
        token_count = 0
        min_tokens = self.settings.chunk_min_tokens
        if preserve_order:
            ordered = list(chunks or [])
        else:
            ordered = sorted(chunks or [], key=lambda item: item.get("score", 0), reverse=True)
        for rank, chunk in enumerate(ordered):
            chunk_id = chunk.get("chunk_id")
            if not chunk_id or chunk_id in seen:
                continue
            text = chunk.get("text", "")
            tokens = count_tokens(text)
            # skip very short / low-quality chunks, but always keep the top
            # hit so a confident retrieval never yields an empty context
            if tokens < min_tokens and rank > 0:
                continue
            if token_count + tokens > self.settings.max_context_tokens:
                break
            seen.add(chunk_id)
            selected.append(chunk)
            token_count += tokens
        context = "\n\n".join(
            f"[{index + 1}] source={chunk.get('metadata', {}).get('source', 'unknown')}\n{chunk.get('text', '')}"
            for index, chunk in enumerate(selected)
        )
        return {"context": context, "chunks": selected, "token_count": token_count}
