from app.config import Settings
from app.services.chunking import count_tokens


class ContextBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build(self, chunks: list[dict]) -> dict:
        seen = set()
        selected = []
        token_count = 0
        min_tokens = self.settings.chunk_min_tokens
        for rank, chunk in enumerate(
            sorted(chunks, key=lambda item: item.get("score", 0), reverse=True)
        ):
            chunk_id = chunk["chunk_id"]
            if chunk_id in seen:
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
