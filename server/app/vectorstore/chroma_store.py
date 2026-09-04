import time
from typing import Any

import numpy as np

from app.config import Settings
from app.vectorstore.interface import VectorStoreInterface
from app.utils.logging import get_logger

logger = get_logger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
except Exception:
    chromadb = None  # type: ignore
    ChromaSettings = None  # type: ignore


class ChromaVectorStore(VectorStoreInterface):
    """ChromaDB PersistentClient VectorStore implementation.

    Storage: local PersistentClient at ``settings.resolved_chroma_path``
    (repo-root ``.chromadb/`` in dev, ``/app/.chromadb`` in Docker,
    ``storage_test/.chromadb`` in tests). Rebuildable from PG chunks.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        self.collection = None
        self._path = str(settings.resolved_chroma_path)
        self._collection_name = settings.chroma_collection

    def startup(self) -> None:
        if chromadb is None:
            raise RuntimeError("chromadb not installed — pip install chromadb")
        from pathlib import Path
        import shutil

        Path(self._path).mkdir(parents=True, exist_ok=True)
        # Try to create client/collection, with recovery for corrupted DB (e.g., after storage_test deletion)
        for attempt in range(2):
            try:
                self.client = chromadb.PersistentClient(path=self._path)
                self.collection = self.client.get_or_create_collection(
                    name=self._collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                # Validate collection is usable
                try:
                    count = self.collection.count()
                except Exception as count_exc:
                    # Corrupted DB (e.g., 'no such table: embeddings' after rm -rf)
                    if "no such table" in str(count_exc).lower() and attempt == 0:
                        logger.warning("ChromaDB corrupted at %s (%s), resetting", self._path, count_exc)
                        # Try to reset or delete directory
                        try:
                            # Try Chroma reset
                            if hasattr(self.client, "reset"):
                                self.client.reset()
                        except Exception:
                            pass
                        try:
                            shutil.rmtree(self._path, ignore_errors=True)
                            Path(self._path).mkdir(parents=True, exist_ok=True)
                        except Exception:
                            pass
                        continue
                    raise
                logger.info("ChromaDB collection '%s' at %s (count=%s)", self._collection_name, self._path, count)
                return
            except Exception as exc:
                if attempt == 0 and "no such table" in str(exc).lower():
                    logger.warning("Chroma startup corrupted, retrying after reset: %s", exc)
                    try:
                        shutil.rmtree(self._path, ignore_errors=True)
                        Path(self._path).mkdir(parents=True, exist_ok=True)
                    except Exception:
                        pass
                    continue
                logger.exception("Chroma startup failed: %s", exc)
                raise
        raise RuntimeError("Chroma startup failed after retry")

    def _prepare_metadatas(self, metadata: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
        ids: list[str] = []
        metadatas: list[dict[str, Any]] = []
        documents: list[str] = []
        # vectors handled outside
        for m in metadata:
            chunk_id = m.get("chunk_id") or m.get("id") or m.get("_id") or f"chk_{len(ids)}"
            ids.append(str(chunk_id))
            # Chroma metadata must be flat primitives
            meta: dict[str, Any] = {}
            meta["user_id"] = str(m.get("user_id", ""))
            meta["session_id"] = str(m.get("session_id", ""))
            meta["document_id"] = str(m.get("document_id", m.get("documentId", "")))
            meta["chunk_id"] = str(chunk_id)
            inner = m.get("metadata", {})
            if isinstance(inner, dict):
                for k, v in inner.items():
                    if isinstance(v, (str, int, float, bool)):
                        # Chroma rejects None; skip
                        if v is not None:
                            meta[str(k)] = v
                    elif v is not None:
                        meta[str(k)] = str(v)
            # entity_ids as comma-separated
            eids = m.get("entity_ids", [])
            if isinstance(eids, list):
                meta["entity_ids"] = ",".join(str(x) for x in eids)
            elif isinstance(eids, str):
                meta["entity_ids"] = eids
            else:
                meta["entity_ids"] = ""
            # preserve chunk_index for debugging
            if "chunk_index" in m:
                meta["chunk_index"] = int(m["chunk_index"])
            metadatas.append(meta)
            documents.append(str(m.get("text", m.get("content", ""))))
        return ids, metadatas, documents  # type: ignore

    def add(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None:
        if len(vectors) == 0 or not metadata:
            return
        if self.collection is None:
            logger.warning("ChromaVectorStore not started — skipping add of %d vectors", len(metadata))
            return
        vectors = np.asarray(vectors, dtype="float32")
        # Normalize already done by EmbeddingService, but ensure
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = np.divide(vectors, np.maximum(norms, 1e-12))
        ids, metadatas, documents = self._prepare_metadatas(metadata)  # type: ignore
        # Prepare embeddings as list
        embeddings = vectors.tolist()
        # Use upsert to allow re-adding same chunk_id (re-ingest)
        try:
            # chromadb==0.5.23 always provides upsert; add() is the fallback
            if hasattr(self.collection, "upsert"):
                self.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
            else:
                self.collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
        except Exception as exc:
            # If duplicate, try update
            logger.warning("Chroma add upsert fallback: %s", exc)
            try:
                self.collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
            except Exception as e2:
                logger.exception("Chroma add failed: %s", e2)
                raise

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search scoped to one user and one chat session.

        A chat can only ever see vectors carrying its own session_id, so
        documents uploaded in another chat are invisible here.
        """
        if self.collection is None:
            return []
        if self.collection.count() == 0:
            return []
        query = np.asarray(query_vector, dtype="float32").reshape(1, -1)
        query = query / np.maximum(np.linalg.norm(query, axis=1, keepdims=True), 1e-12)
        clauses: list[dict[str, Any]] = []
        if user_id is not None:
            clauses.append({"user_id": user_id})
        if session_id is not None:
            clauses.append({"session_id": session_id})
        if len(clauses) > 1:
            where: dict[str, Any] | None = {"$and": clauses}
        elif clauses:
            where = clauses[0]
        else:
            where = None
        try:
            # Chroma where filtering requires exact match; handle empty where
            kwargs: dict[str, Any] = {
                "query_embeddings": query.tolist(),
                "n_results": min(top_k, max(1, self.collection.count())),
                "include": ["metadatas", "documents", "distances"],
            }
            if where:
                kwargs["where"] = where
            results = self.collection.query(**kwargs)
        except Exception as exc:
            logger.exception("Chroma query failed: %s", exc)
            return []
        if not results or not results.get("ids") or not results["ids"][0]:
            return []
        ids = results["ids"][0]
        metadatas = results["metadatas"][0]
        documents = results["documents"][0] if results.get("documents") else [""] * len(ids)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)
        out: list[dict[str, Any]] = []
        for idx, (cid, meta, doc, dist) in enumerate(zip(ids, metadatas, documents, distances)):
            # distance is cosine distance (1 - similarity) when hnsw:space=cosine
            score = 1.0 - float(dist) if dist is not None else 0.0
            # Clamp
            score = max(-1.0, min(1.0, score))
            # Reconstruct metadata inner
            inner_meta = {k: v for k, v in meta.items() if k not in ("user_id", "session_id", "document_id", "chunk_id", "entity_ids")}
            entity_ids = [e for e in meta.get("entity_ids", "").split(",") if e]
            item = {
                "chunk_id": cid,
                "document_id": meta.get("document_id", ""),
                "text": doc,
                "metadata": inner_meta,
                "entity_ids": entity_ids,
                "score": float(score),
                "user_id": meta.get("user_id", ""),
                "session_id": meta.get("session_id", ""),
                # keep raw for compatibility
                "distance": float(dist) if dist is not None else 0.0,
            }
            out.append(item)
        # Already sorted by distance ascending (score descending)
        return out[:top_k]

    def delete(
        self,
        chunk_ids: list[str] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        if self.collection is None:
            return
        try:
            if chunk_ids:
                self.collection.delete(ids=chunk_ids)
            elif user_id is not None and session_id is not None:
                self.collection.delete(where={"$and": [{"user_id": user_id}, {"session_id": session_id}]})
            elif user_id:
                self.collection.delete(where={"user_id": user_id})
            elif session_id:
                self.collection.delete(where={"session_id": session_id})
            else:
                # delete all? not used
                pass
        except Exception as exc:
            logger.exception("Chroma delete failed: %s", exc)

    def rebuild(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None:
        """Clear collection and re-add. Used when PG truth must rebuild the Chroma index."""
        if self.collection is None:
            return
        try:
            # delete all ids
            existing = self.collection.get(limit=100000)
            if existing and existing.get("ids"):
                self.collection.delete(ids=existing["ids"])
        except Exception:
            pass
        if len(vectors) > 0:
            self.add(vectors, metadata)

    def size(self) -> int:
        if self.collection is None:
            return 0
        try:
            return int(self.collection.count())
        except Exception:
            return 0

    def shutdown(self) -> None:
        try:
            if self.client is not None and hasattr(self.client, "persist"):
                self.client.persist()
        except Exception:
            pass
        # Release Chroma resources so next test/process can delete/recreate directory.
        # PersistentClient holds an open SQLite connection + Rust HNSW handles;
        # without _system.stop() the next test's rmtree + recreate hits
        # "sqlite3.OperationalError: attempt to write a readonly database".
        try:
            if self.collection is not None:
                self.collection = None
            if self.client is not None:
                try:
                    if hasattr(self.client, "_system") and hasattr(self.client._system, "stop"):
                        self.client._system.stop()
                except Exception:
                    pass
                try:
                    if hasattr(self.client, "clear_system_cache") and callable(getattr(self.client, "clear_system_cache")):
                        self.client.clear_system_cache()
                except Exception:
                    pass
                self.client = None
            import gc
            import time

            gc.collect()
            # Give OS/Chroma threads a moment to release file handles before
            # the next test deletes the directory.
            try:
                time.sleep(0.2)
            except Exception:
                pass
            gc.collect()
        except Exception:
            pass

VectorStore = ChromaVectorStore
