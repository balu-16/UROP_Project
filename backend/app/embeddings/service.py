import asyncio
import hashlib
import json

import numpy as np

from app.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.cache_path = settings.resolved_storage_dir / "embedding_cache.json"
        self.cache: dict[str, list[float]] = {}

    async def startup(self) -> None:
        self.settings.resolved_storage_dir.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupted embedding cache, starting fresh")
                self.cache = {}
        if not self.settings.disable_local_models:
            try:
                from sentence_transformers import SentenceTransformer

                device = "cuda"
                try:
                    import torch

                    if not torch.cuda.is_available():
                        device = "cpu"
                except Exception:
                    device = "cpu"
                self.model = SentenceTransformer(
                    self.settings.embedding_model_name, device=device
                )
                self.settings.embedding_dimension = int(
                    self.model.get_sentence_embedding_dimension()
                )
                logger.info(
                    "Loaded embedding model %s on %s",
                    self.settings.embedding_model_name,
                    device,
                )
            except Exception as exc:
                logger.warning("Falling back to deterministic hash embeddings: %s", exc)
                self.model = None

    async def shutdown(self) -> None:
        try:
            self.cache_path.write_text(json.dumps(self.cache))
        except OSError as exc:
            logger.warning("Failed to save embedding cache: %s", exc)

    def _cache_key(self, text: str) -> str:
        model = self.settings.embedding_model_name
        dim = self.settings.embedding_dimension
        return hashlib.sha256(f"{model}:{dim}:{text}".encode("utf-8")).hexdigest()

    def _hash_embedding(self, text: str) -> np.ndarray:
        dim = self.settings.embedding_dimension
        vector = np.zeros(dim, dtype="float32")
        tokens = text.lower().split()
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        vectors: list[np.ndarray | None] = []
        missing: list[tuple[int, str, str]] = []
        for index, text in enumerate(texts):
            key = self._cache_key(text)
            cached = self.cache.get(key)
            if cached is not None:
                vectors.append(np.array(cached, dtype="float32"))
            else:
                vectors.append(None)
                missing.append((index, key, text))
        if missing:
            missing_texts = [item[2] for item in missing]
            if self.model is None:
                generated = [self._hash_embedding(text) for text in missing_texts]
            else:
                generated = await asyncio.to_thread(
                    self.model.encode,
                    missing_texts,
                    batch_size=self.settings.embedding_batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            for (index, key, _), vector in zip(missing, generated):
                arr = np.asarray(vector, dtype="float32")
                norm = np.linalg.norm(arr)
                arr = arr / norm if norm > 0 else arr
                vectors[index] = arr
                self.cache[key] = arr.tolist()
        return np.vstack([vector for vector in vectors if vector is not None]).astype(
            "float32"
        )

    async def embed_query(self, text: str) -> np.ndarray:
        return (await self.embed_texts([text]))[0]

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)
