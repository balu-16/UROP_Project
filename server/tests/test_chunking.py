"""Unit tests for the recursive Chunker."""

import pytest

from app.config.settings import Settings
from app.services.chunking import Chunker, count_tokens


@pytest.fixture()
def chunker() -> Chunker:
    # Small limits keep the tests fast and make boundaries easy to assert.
    settings = Settings(chunk_max_tokens=64, chunk_overlap_tokens=12)
    return Chunker(settings)


def _paragraph(topic: str, sentences: int = 6) -> str:
    return " ".join(
        f"Sentence {i} of {topic} expands on the idea with additional detail."
        for i in range(sentences)
    )


def test_empty_text_returns_no_chunks(chunker: Chunker):
    assert chunker.chunk("doc", "", {}) == []
    assert chunker.chunk("doc", "   \n\n  ", {}) == []


def test_short_text_is_single_chunk(chunker: Chunker):
    text = "A short paragraph. With two sentences."
    chunks = chunker.chunk("doc", text, {"source": "unit-test"})
    assert len(chunks) == 1
    assert chunks[0]["text"] == text
    assert chunks[0]["metadata"]["chunk_index"] == 0
    assert chunks[0]["metadata"]["source"] == "unit-test"


def test_output_contract(chunker: Chunker):
    chunks = chunker.chunk("doc-1", _paragraph("alpha"), {})
    assert chunks
    for chunk in chunks:
        assert set(chunk) == {"chunk_id", "document_id", "text", "metadata", "entity_ids"}
        assert chunk["document_id"] == "doc-1"
        assert chunk["chunk_id"].startswith("chk_")
        assert chunk["entity_ids"] == []
        assert chunk["metadata"]["chunk_index"] >= 0
        assert "token_start" in chunk["metadata"] and "token_end" in chunk["metadata"]


def test_chunk_indices_are_sequential(chunker: Chunker):
    text = "\n\n".join(_paragraph(f"topic-{i}") for i in range(6))
    chunks = chunker.chunk("doc", text, {})
    assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_chunks_respect_max_tokens(chunker: Chunker):
    text = "\n\n".join(_paragraph(f"topic-{i}", sentences=8) for i in range(8))
    chunks = chunker.chunk("doc", text, {})
    assert len(chunks) > 1
    for chunk in chunks:
        assert count_tokens(chunk["text"]) <= 64


def test_boundaries_fall_on_sentences(chunker: Chunker):
    text = "\n\n".join(_paragraph(f"topic-{i}") for i in range(6))
    chunks = chunker.chunk("doc", text, {})
    assert len(chunks) > 1
    for chunk in chunks:
        # every chunk must end at a sentence boundary (no mid-word cuts)
        stripped = chunk["text"].rstrip()
        assert stripped.endswith("."), f"chunk cut mid-sentence: ...{stripped[-40:]!r}"


def test_consecutive_chunks_share_overlap(chunker: Chunker):
    text = "\n\n".join(_paragraph(f"topic-{i}", sentences=10) for i in range(4))
    chunks = chunker.chunk("doc", text, {})
    assert len(chunks) > 2
    for prev, nxt in zip(chunks, chunks[1:]):
        prev_words = prev["text"].split()
        next_words = nxt["text"].split()
        shared = set(prev_words) & set(next_words)
        # the overlap seed should carry content from the previous chunk
        assert shared, "no overlap between consecutive chunks"


def test_no_separator_fallback_splits_long_text(chunker: Chunker):
    # One unbroken character run well past the token budget (tiktoken
    # compresses repeats, so go large): falls through to the char-level
    # last resort.
    text = "a" * 2000
    chunks = chunker.chunk("doc", text, {})
    assert len(chunks) > 1
    assert all(count_tokens(c["text"]) <= 64 for c in chunks)


def test_long_single_sentence_is_split(chunker: Chunker):
    sentence = (
        "The quick brown fox jumps over the lazy dog while the packed library "
        "guards its quiet corners and the rain writes patterns on the glass. "
    )
    text = sentence * 30  # one "sentence" run far beyond 64 tokens
    chunks = chunker.chunk("doc", text, {})
    assert len(chunks) > 1
    assert all(count_tokens(c["text"]) <= 64 for c in chunks)


def test_paragraph_content_preserved_across_chunks(chunker: Chunker):
    text = "\n\n".join(_paragraph(f"topic-{i}") for i in range(6))
    chunks = chunker.chunk("doc", text, {})
    joined = " ".join(c["text"] for c in chunks)
    for i in range(6):
        assert f"topic-{i}" in joined
