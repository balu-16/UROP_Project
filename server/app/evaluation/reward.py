from app.embeddings import EmbeddingService
from app.services.chunking import count_tokens

STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "shall",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "each",
        "every",
        "all",
        "any",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
        "just",
        "because",
        "if",
        "when",
        "where",
        "how",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "it",
        "its",
        "they",
        "them",
        "their",
    }
)


class RewardEvaluator:
    def __init__(self, embeddings: EmbeddingService):
        self.embeddings = embeddings

    async def evaluate(
        self,
        query: str,
        answer: str,
        chunks: list[dict],
        latency_ms: float,
        usage: dict | None,
    ) -> dict:
        if answer.strip():
            vectors = await self.embeddings.embed_texts([query, answer])
            quality = max(0.0, min(1.0, self.embeddings.cosine(vectors[0], vectors[1])))
        else:
            quality = 0.0

        def _get_terms(text: str) -> set[str]:
            return {
                w for w in text.lower().split() if w not in STOP_WORDS and len(w) > 2
            }

        def _get_bigrams(text: str) -> set[str]:
            words = text.lower().split()
            return {f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)}

        answer_terms = _get_terms(answer)
        context_terms: set[str] = set()
        for chunk in chunks:
            context_terms.update(_get_terms(chunk.get("text", "")))

        answer_bigrams = _get_bigrams(answer)
        context_bigrams: set[str] = set()
        for chunk in chunks:
            context_bigrams.update(_get_bigrams(chunk.get("text", "")))

        term_overlap = len(answer_terms & context_terms) / max(1, len(answer_terms))
        bigram_overlap = len(answer_bigrams & context_bigrams) / max(
            1, len(answer_bigrams)
        )
        lexical_faithfulness = max(
            0.0, min(1.0, 0.4 * term_overlap + 0.6 * bigram_overlap)
        )

        # Semantic faithfulness: cosine similarity between answer and context embeddings
        context_text = " ".join(chunk.get("text", "") for chunk in chunks)
        if answer.strip() and context_text.strip():
            vecs = await self.embeddings.embed_texts([answer, context_text])
            semantic_faith = max(
                0.0, min(1.0, self.embeddings.cosine(vecs[0], vecs[1]))
            )
        else:
            semantic_faith = 0.0

        faithfulness = max(
            0.0, min(1.0, 0.3 * lexical_faithfulness + 0.7 * semantic_faith)
        )
        _usage = usage or {}
        prompt_tokens = _usage.get("prompt_tokens")
        if prompt_tokens is None:
            prompt_tokens = sum(
                count_tokens(chunk.get("text", "")) for chunk in chunks
            )
        completion_tokens = _usage.get("completion_tokens")
        if completion_tokens is None:
            completion_tokens = count_tokens(answer)
        cost = min(
            1.0, (prompt_tokens + completion_tokens) / 12000.0 + latency_ms / 120000.0
        )
        reward = 0.6 * quality + 0.3 * faithfulness - 0.1 * cost
        return {
            "reward": max(-1.0, min(1.0, reward)),
            "quality": quality,
            "faithfulness": faithfulness,
            "cost": cost,
            "latency_ms": latency_ms,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        }
