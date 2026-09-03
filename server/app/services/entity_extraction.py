import asyncio
import re
from typing import Any

from app.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EntityExtractor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.nlp = None

    def startup(self) -> None:
        if self.settings.disable_local_models:
            return
        try:
            import spacy

            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                self.nlp = spacy.blank("en")
            logger.info("spaCy entity extractor initialized")
        except Exception as exc:
            logger.warning("Using regex entity extractor: %s", exc)

    async def extract(self, text: str) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        if self.nlp is not None and self.nlp.pipe_names:
            doc = await asyncio.to_thread(self.nlp, text[:100000])
            labels = {"ORG", "PERSON", "GPE", "EVENT", "PRODUCT", "NORP", "WORK_OF_ART"}
            entities.extend(
                {"text": ent.text.strip(), "label": ent.label_}
                for ent in doc.ents
                if ent.label_ in labels and ent.text.strip()
            )
        if not entities:
            # Title Case phrases (ASCII)
            for match in re.finditer(
                r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,3})\b", text
            ):
                value = match.group(0).strip()
                if len(value) > 2:
                    entities.append({"text": value, "label": "CONCEPT"})
            # All-caps acronyms
            for match in re.finditer(r"\b[A-Z]{2,}\b", text):
                value = match.group(0).strip()
                if len(value) > 1:
                    entities.append({"text": value, "label": "ACRONYM"})
            # Mixed case (e.g., iPhone, GitHub)
            for match in re.finditer(r"\b[a-z]+[A-Z][a-z]*\b", text):
                value = match.group(0).strip()
                if len(value) > 2:
                    entities.append({"text": value, "label": "CONCEPT"})
            # Unicode names: words starting with an uppercase unicode letter
            # followed by lowercase unicode chars (e.g., München, Café, François)
            for match in re.finditer(
                r"\b[\u00C0-\u024F][\u0061-\u024F\u00C0-\u024F]{1,}(?:\s+[\u00C0-\u024F][\u0061-\u024F\u00C0-\u024F]{1,}){0,2}\b",
                text,
            ):
                value = match.group(0).strip()
                # Avoid re-matching ASCII Title Case already captured above
                if len(value) > 2 and not value.isascii():
                    entities.append({"text": value, "label": "CONCEPT"})
        seen = set()
        unique = []
        for entity in entities:
            key = entity["text"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(entity)
        return unique[:80]
