import re
from statistics import variance

from app.services.entity_extraction import EntityExtractor


class FeatureExtractor:
    causal_terms = {"why", "cause", "caused", "because", "impact", "effect", "reason"}
    factual_terms = {"what", "when", "where", "who", "which", "define", "list"}

    def __init__(self, extractor: EntityExtractor):
        self.extractor = extractor

    async def extract(self, query: str, prefetch_results: list[dict]) -> dict:
        tokens = re.findall(r"\S+", query)
        entities = await self.extractor.extract(query)
        lower_tokens = {token.lower().strip("?.!,") for token in tokens}
        scores = [float(item.get("score", 0)) for item in prefetch_results]
        confidence = max(scores) if scores else 0.0
        score_variance = variance(scores) if len(scores) > 1 else 0.0
        short_penalty = 0.1 if len(tokens) < 3 and confidence < 0.5 else 0.0
        ambiguity = min(
            1.0,
            query.count(" or ") * 0.2
            + short_penalty
            + (0.3 if confidence < 0.35 else 0.0),
        )
        question_type = (
            1.0
            if lower_tokens & self.causal_terms
            else 0.5
            if lower_tokens & self.factual_terms
            else 0.0
        )
        vector = [
            min(len(tokens) / 64.0, 1.0),
            min(len(entities) / 8.0, 1.0),
            question_type,
            1.0 if lower_tokens & self.causal_terms else 0.0,
            confidence,
            min(score_variance, 1.0),
            ambiguity,
        ]
        return {
            "query_length": len(tokens),
            "entity_count": len(entities),
            "question_type": question_type,
            "causal": bool(lower_tokens & self.causal_terms),
            "retrieval_confidence": confidence,
            "top_k_variance": score_variance,
            "ambiguity_score": ambiguity,
            "vector": vector,
            "entities": entities,
        }
