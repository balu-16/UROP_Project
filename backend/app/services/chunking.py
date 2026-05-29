import re
from typing import Any

from app.config import Settings
from app.utils.ids import new_id


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base encoding used by GPT-4/others)."""
    try:
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")
        return len(encoder.encode(text))
    except Exception:
        # Fallback to word-piece heuristic if tiktoken unavailable
        words = len(re.findall(r"\S+", text))
        return max(1, int(words * 1.3)) if words else 0


class Chunker:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chunk(
        self, document_id: str, text: str, metadata: dict[str, Any]
    ) -> list[dict[str, Any]]:
        tokens = re.findall(r"\S+", text)
        if not tokens:
            return []
        max_tokens = self.settings.chunk_max_tokens
        overlap = self.settings.chunk_overlap_tokens
        if overlap >= max_tokens:
            overlap = max(0, max_tokens - 1)  # prevent infinite loop
        chunks = []
        start = 0
        chunk_index = 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunks.append(
                {
                    "chunk_id": new_id("chk"),
                    "document_id": document_id,
                    "text": " ".join(chunk_tokens),
                    "metadata": {
                        **metadata,
                        "chunk_index": chunk_index,
                        "token_start": start,
                        "token_end": end,
                    },
                    "entity_ids": [],
                }
            )
            if end >= len(tokens):
                break
            start = max(0, end - overlap)
            chunk_index += 1
        return chunks
