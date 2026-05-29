import json
import time
from typing import Any

import numpy as np

from app.config import Settings

try:
    import faiss
except Exception:
    faiss = None


class VectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.index_path = settings.resolved_storage_dir / "faiss.index"
        self.meta_path = settings.resolved_storage_dir / "faiss_metadata.json"
        self.dimension = settings.embedding_dimension
        self.index = None
        self.metadata: list[dict[str, Any]] = []
        self.vectors: np.ndarray | None = None
        self._dirty = False
        self._last_save = 0.0
        self._save_interval = 30.0  # save at most once per 30 seconds

    def startup(self) -> None:
        self.settings.resolved_storage_dir.mkdir(parents=True, exist_ok=True)
        if self.meta_path.exists():
            self.metadata = json.loads(self.meta_path.read_text())
        if faiss is not None and self.index_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            self.dimension = int(self.index.d)
        elif self.meta_path.with_suffix(".npy").exists():
            vectors = np.load(self.meta_path.with_suffix(".npy")).astype("float32")
            self.vectors = vectors
            self.dimension = (
                int(vectors.shape[1]) if len(vectors.shape) == 2 else self.dimension
            )
        else:
            self._init_index()

    def _init_index(self) -> None:
        if faiss is not None:
            self.index = faiss.IndexFlatIP(self.dimension)
        else:
            self.vectors = np.empty((0, self.dimension), dtype="float32")

    def save(self) -> None:
        self.meta_path.write_text(json.dumps(self.metadata, default=str))
        if faiss is not None and self.index is not None:
            faiss.write_index(self.index, str(self.index_path))
        elif self.vectors is not None:
            np.save(self.meta_path.with_suffix(".npy"), self.vectors)
        self._dirty = False
        self._last_save = time.monotonic()

    def add(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None:
        if len(vectors) == 0:
            return
        vectors = np.asarray(vectors, dtype="float32")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = np.divide(vectors, np.maximum(norms, 1e-12))
        if self.index is None and self.vectors is None:
            self.dimension = int(vectors.shape[1])
            self._init_index()
        if faiss is not None and self.index is not None:
            if self.index.d != vectors.shape[1]:
                self.dimension = int(vectors.shape[1])
                self.index = faiss.IndexFlatIP(self.dimension)
                self.metadata = []
            self.index.add(vectors)
        else:
            if self.vectors is None or self.vectors.shape[1] != vectors.shape[1]:
                self.dimension = int(vectors.shape[1])
                self.vectors = np.empty((0, self.dimension), dtype="float32")
                self.metadata = []
            self.vectors = np.vstack([self.vectors, vectors])
        self.metadata.extend(metadata)
        self._dirty = True
        now = time.monotonic()
        if now - self._last_save >= self._save_interval:
            self.save()

    def search(
        self, query_vector: np.ndarray, top_k: int, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        if len(self.metadata) == 0:
            return []
        # Pre-filter indices by user_id if specified
        allowed_indices: set[int] | None = None
        if user_id is not None:
            allowed_indices = {
                i for i, m in enumerate(self.metadata) if m.get("user_id") == user_id
            }
            if not allowed_indices:
                return []
        query = np.asarray(query_vector, dtype="float32").reshape(1, -1)
        query = query / np.maximum(np.linalg.norm(query, axis=1, keepdims=True), 1e-12)
        # Search a wider pool when filtering so we still get enough results
        search_k = (
            min(top_k * 4, len(self.metadata))
            if allowed_indices is not None
            else min(top_k, len(self.metadata))
        )
        if faiss is not None and self.index is not None:
            scores, indices = self.index.search(query, search_k)
            pairs = zip(indices[0].tolist(), scores[0].tolist())
        else:
            sims = (
                (self.vectors @ query[0]).tolist() if self.vectors is not None else []
            )
            order = np.argsort(sims)[::-1][:search_k]
            pairs = [(int(index), float(sims[index])) for index in order]
        results = []
        for index, score in pairs:
            if index < 0 or index >= len(self.metadata):
                continue
            if allowed_indices is not None and index not in allowed_indices:
                continue
            item = dict(self.metadata[index])
            item["score"] = float(score)
            results.append(item)
            if len(results) >= top_k:
                break
        return results

    def shutdown(self) -> None:
        if self._dirty:
            self.save()

    def size(self) -> int:
        return len(self.metadata)
