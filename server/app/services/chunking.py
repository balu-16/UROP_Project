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


# Coarse → fine: paragraphs, lines, sentences, words, characters (last resort).
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_on(text: str, sep: str) -> list[str]:
    """Split on sep keeping it attached to the end of each piece (lossless)."""
    if not sep:
        return list(text)
    parts = text.split(sep)
    pieces = [part + sep for part in parts[:-1]]
    if parts[-1]:
        pieces.append(parts[-1])
    return pieces


class Chunker:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _split(self, text: str, separators: list[str]) -> list[str]:
        """Break text into units that each fit within chunk_max_tokens."""
        max_tokens = self.settings.chunk_max_tokens
        if count_tokens(text) <= max_tokens:
            return [text] if text.strip() else []
        if not separators:
            return [text] if text.strip() else []
        sep, rest = separators[0], separators[1:]
        pieces = _split_on(text, sep)
        if len(pieces) == 1:
            # separator absent — fall through to the next, finer separator
            return self._split(text, rest)
        units: list[str] = []
        for piece in pieces:
            units.extend(self._split(piece, rest))
        return units

    def chunk(
        self, document_id: str, text: str, metadata: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not text or not text.strip():
            return []
        max_tokens = self.settings.chunk_max_tokens
        overlap = min(self.settings.chunk_overlap_tokens, max(0, max_tokens - 1))

        units = self._split(text, list(SEPARATORS))
        if not units:
            return []

        groups: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        for unit in units:
            unit_tokens = count_tokens(unit)
            if current and current_tokens + unit_tokens > max_tokens:
                groups.append(current)
                tail: list[str] = []
                tail_tokens = 0
                for prev in reversed(current):
                    prev_tokens = count_tokens(prev)
                    if tail and tail_tokens + prev_tokens > overlap:
                        break
                    tail.insert(0, prev)
                    tail_tokens += prev_tokens
                # keep the tail as a seed for the next chunk only if the
                # incoming unit still fits alongside it
                if tail_tokens + unit_tokens > max_tokens:
                    tail, tail_tokens = [], 0
                current, current_tokens = tail, tail_tokens
            current.append(unit)
            current_tokens += unit_tokens
        if current:
            groups.append(current)

        chunks: list[dict[str, Any]] = []
        offset = 0
        for chunk_index, group in enumerate(groups):
            chunk_text = "".join(group).strip()
            if not chunk_text:
                continue
            group_tokens = sum(count_tokens(unit) for unit in group)
            chunks.append(
                {
                    "chunk_id": new_id("chk"),
                    "document_id": document_id,
                    "text": chunk_text,
                    "metadata": {
                        **metadata,
                        "chunk_index": chunk_index,
                        "token_start": offset,
                        "token_end": offset + group_tokens,
                    },
                    "entity_ids": [],
                }
            )
            offset += group_tokens
        return chunks
