from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class VectorStoreInterface(ABC):
    """Abstraction for vector retrieval — ChromaDB is the implementation."""

    @abstractmethod
    def startup(self) -> None: ...

    @abstractmethod
    def add(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None: ...

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int, user_id: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete(self, chunk_ids: list[str] | None = None, user_id: str | None = None) -> None: ...

    @abstractmethod
    def rebuild(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None: ...

    @abstractmethod
    def size(self) -> int: ...

    @abstractmethod
    def shutdown(self) -> None: ...
