from fastapi import UploadFile

from app.config import Settings
from app.database import AppDatabase
from app.embeddings import EmbeddingService
from app.services.chunking import Chunker
from app.services.document_parser import DocumentParser
from app.services.entity_extraction import EntityExtractor
from app.utils.ids import new_id
from app.utils.time import utc_now
from app.vectorstore import VectorStore
from app.utils.logging import get_logger

logger = get_logger(__name__)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        db: AppDatabase,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
        graph_store,  # PGGraphStore (avoid circular import)
        extractor: EntityExtractor,
    ):
        self.settings = settings
        self.db = db
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.extractor = extractor
        self.parser = DocumentParser()
        self.chunker = Chunker(settings)

    async def index_uploads(self, user_id: str, session_id: str, files: list[UploadFile]) -> dict:
        """Index uploads scoped to one chat session.

        Every stored artifact (PG documents/chunks, Chroma points,
        indexed_documents) carries both user_id and session_id so retrieval
        in another session can never see this chat's documents.
        """
        documents = []
        total_chunks = 0
        total_entities = 0
        total_bytes = 0
        total_cap = int(getattr(self.settings, "total_upload_max_mb", 100)) * 1024 * 1024
        # For PG inserts, collect supabase client if available
        supa = None
        use_pg = False
        try:
            if hasattr(self.db, "db") and hasattr(self.db.db, "client") and self.db.db.client:
                supa = self.db.db.client
                use_pg = True
        except Exception:
            supa = None
            use_pg = False

        for file in files:
            text, metadata = await self.parser.parse_upload(
                file, self.settings.upload_max_mb
            )
            total_bytes += int(metadata.get("size_bytes", 0) or 0)
            if total_bytes > total_cap:
                raise ValueError(
                    "Combined upload size exceeds the per-request limit "
                    f"({self.settings.total_upload_max_mb}MB total)."
                )
            if not text.strip():
                logger.warning("Skipping empty/unparseable file: %s", getattr(file, "filename", "?"))
                continue
            document_id_ulid = new_id("doc")  # for Chroma / indexed_documents
            pg_doc_uuid: str | None = None

            # Insert into PG documents table if Supabase available (for truth)
            if use_pg and supa:
                try:
                    # documents table has uuid id, we insert with user_id, title/source/content
                    pg_payload = {
                        "user_id": user_id,
                        "title": metadata.get("source", "Untitled"),
                        "source": metadata.get("source", ""),
                        "content": text[:50000],  # limit for PG
                        "metadata": {**metadata, "session_id": session_id},
                    }
                    res = supa.table("documents").insert(pg_payload).execute()
                    if res.data:
                        pg_doc_uuid = res.data[0].get("id")
                except Exception as exc:
                    logger.warning("PG documents insert failed (fallback to legacy): %s", exc)
                    pg_doc_uuid = None

            chunks = self.chunker.chunk(document_id_ulid, text, metadata)
            chunk_metadata = []
            pg_chunks_to_insert: list[dict] = []
            chunk_entities_list: list[list[dict]] = []
            for chunk in chunks:
                entities = await self.extractor.extract(chunk["text"])
                # Normalize entity names
                entity_ids = []
                for ent in entities:
                    t = ent.get("text") or ent.get("name") or ""
                    if t:
                        # Use graph_store normalize
                        from app.graph_store.pg_store import _normalize_entity
                        entity_ids.append(_normalize_entity(str(t)))
                entity_ids = [e for e in entity_ids if e]
                chunk["entity_ids"] = entity_ids
                chunk_entities_list.append(entities)

                chunk_metadata.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "document_id": document_id_ulid,
                        "text": chunk["text"],
                        "metadata": chunk["metadata"],
                        "entity_ids": entity_ids,
                        "user_id": user_id,
                        "session_id": session_id,
                    }
                )
                total_entities += len(entity_ids)

                # Prepare PG chunks insert if we have pg_doc_uuid
                if pg_doc_uuid:
                    pg_chunks_to_insert.append(
                        {
                            "document_id": pg_doc_uuid,
                            "chunk_index": chunk["metadata"].get("chunk_index", 0),
                            "content": chunk["text"],
                            "chunk_id": chunk["chunk_id"],
                            "metadata": {**chunk["metadata"], "session_id": session_id},
                        }
                    )

            if chunks:
                try:
                    vectors = await self.embeddings.embed_texts(
                        [chunk["text"] for chunk in chunks]
                    )
                    self.vector_store.add(vectors, chunk_metadata)
                except Exception as exc:
                    logger.exception("vector_store add failed: %s", exc)
                    raise

            # Bulk insert PG chunks BEFORE graph linking so chunk_uuid lookup succeeds
            if pg_doc_uuid and pg_chunks_to_insert:
                try:
                    # Supabase insert bulk
                    supa.table("chunks").insert(pg_chunks_to_insert).execute()
                except Exception as exc:
                    logger.warning("PG chunks bulk insert failed: %s", exc)

            # Link graph AFTER PG chunks exist (fixes chunk_uuid miss → skipped chunk_entities)
            for chunk, entities in zip(chunks, chunk_entities_list):
                try:
                    res = self.graph_store.add_chunk(chunk["chunk_id"], entities)
                    if hasattr(res, "__await__"):
                        await res
                except TypeError:
                    # fallback if add_chunk is sync
                    try:
                        self.graph_store.add_chunk(chunk["chunk_id"], entities)
                    except Exception as exc2:
                        logger.warning("graph add_chunk failed: %s", exc2)
                except Exception as exc:
                    logger.warning("graph add_chunk failed: %s", exc)

            # Legacy indexed_documents for existing metrics.
            # Chunk ULIDs live inside metadata JSON (indexed_documents has no
            # top-level chunk_ids column in migration 001) so un-upload can
            # clean vectors/graph even for legacy/memory rows without a PG link.
            meta_out = {**metadata, "chunk_ids": [c["chunk_id"] for c in chunks]}
            record = {
                "_id": document_id_ulid,
                "user_id": user_id,
                "session_id": session_id,
                "filename": metadata["source"],
                "metadata": meta_out,
                "chunk_count": len(chunks),
                "created_at": utc_now(),
            }
            # Store PG trace inside metadata (indexed_documents schema has no pg_document_id column)
            if pg_doc_uuid:
                record["metadata"] = {**meta_out, "pg_document_id": pg_doc_uuid}
            await self.db.collection("indexed_documents").insert_one(record)
            documents.append(record)
            total_chunks += len(chunks)

        # Save graph if it has save (PG no-op, memory persists)
        try:
            if hasattr(self.graph_store, "save"):
                res = self.graph_store.save()
                if hasattr(res, "__await__"):
                    await res
        except Exception:
            pass

        # Graph stats
        try:
            gstats = self.graph_store.stats()
        except Exception:
            gstats = {"nodes": 0, "edges": 0}

        return {
            "documents": documents,
            "chunk_count": total_chunks,
            "entity_count": total_entities,
            "vector_index_size": self.vector_store.size(),
            "graph": gstats,
        }

    async def delete_document(self, user_id: str, session_id: str, document_ulid: str) -> dict | None:
        """Delete an uploaded document and all its artifacts (un-upload).

        Removes, in order: Chroma vectors (by chunk ULIDs) → PG documents row
        (SQL cascades chunks + chunk_entities) → explicit chunk/chunk_entities
        cleanup (memory DB has no cascades; no-op on PG) → orphan-entity prune
        (shared entities survive) → indexed_documents row.

        Returns a deletion report, or None when the document doesn't belong to
        this user/chat (callers map that to 404; repeats are therefore
        idempotent). Steps are best-effort and individually logged: a partial
        failure still removes the indexed row so retries return not-found
        instead of looping on the same artifact.
        """
        record = await self.db.collection("indexed_documents").find_one(
            {"_id": document_ulid, "user_id": user_id, "session_id": session_id}
        )
        if not record:
            return None
        metadata = record.get("metadata") or {}
        pg_doc_id = metadata.get("pg_document_id")
        deleted = {
            "vectors": 0,
            "chunks": 0,
            "documents": 0,
            "entities_pruned": 0,
            "relationships_removed": 0,
            "indexed_documents": 0,
        }

        # 1. Resolve PG chunk rows first (yields Chroma ULIDs + entity links).
        # Legacy/memory rows have no PG link: fall back to stored chunk_ids,
        # then to a session-scoped Chroma listing by document_id.
        pg_chunks: list[dict] = []
        if pg_doc_id:
            try:
                pg_chunks = await self.db.collection("chunks").find(
                    {"document_id": pg_doc_id}
                ).to_list(100000)
            except Exception as exc:
                logger.warning("delete: chunks lookup failed for %s: %s", document_ulid, exc)
        chunk_ulids = [r.get("chunk_id") for r in pg_chunks if r.get("chunk_id")]
        chunk_uuids = [r.get("id") for r in pg_chunks if r.get("id")]
        if not chunk_ulids:
            # Chunk ULIDs are stored in metadata JSON (see index_uploads);
            # also accept a legacy top-level key for old memory rows.
            stored = record.get("chunk_ids") or (metadata.get("chunk_ids") or [])
            chunk_ulids = [c for c in stored if c]
        if not chunk_ulids:
            # Last resort for old legacy rows: list Chroma points for this doc.
            try:
                vs = self.vector_store
                coll = getattr(vs, "collection", None)
                if coll is not None:
                    where = {
                        "$and": [
                            {"document_id": document_ulid},
                            {"session_id": session_id},
                            {"user_id": user_id},
                        ]
                    }
                    res = coll.get(where=where, limit=100000)
                    ids = (res.get("ids", []) if res else []) or []
                    chunk_ulids = list(ids)
            except Exception as exc:
                logger.warning("delete: chroma listing failed for %s: %s", document_ulid, exc)
        entity_ids: set[str] = set()
        if chunk_uuids:
            try:
                links = await self.db.collection("chunk_entities").find(
                    {"chunk_id": {"$in": chunk_uuids}}
                ).to_list(100000)
                entity_ids = {l.get("entity_id") for l in links if l.get("entity_id")}
            except Exception as exc:
                logger.warning("delete: entity-link lookup failed for %s: %s", document_ulid, exc)

        # 2. Chroma vectors by ULID (best-effort; the index rebuilds from PG).
        if chunk_ulids:
            try:
                self.vector_store.delete(chunk_ids=chunk_ulids)
                deleted["vectors"] = len(chunk_ulids)
            except Exception as exc:
                logger.warning("delete: vector removal failed for %s: %s", document_ulid, exc)

        # 3. PG documents row (SQL cascades chunks + chunk_entities).
        if pg_doc_id:
            try:
                res = await self.db.collection("documents").delete_many(
                    {"id": pg_doc_id, "user_id": user_id}
                )
                deleted["documents"] = res.deleted_count
            except Exception as exc:
                logger.warning("delete: documents row removal failed for %s: %s", document_ulid, exc)
            # Explicit cleanup for backends without cascades (memory DB).
            # No-ops on PG where the cascade already removed these rows.
            try:
                cres = await self.db.collection("chunks").delete_many({"document_id": pg_doc_id})
                deleted["chunks"] = cres.deleted_count
            except Exception as exc:
                logger.warning("delete: chunks cleanup failed for %s: %s", document_ulid, exc)
            if chunk_uuids:
                try:
                    await self.db.collection("chunk_entities").delete_many(
                        {"chunk_id": {"$in": chunk_uuids}}
                    )
                except Exception as exc:
                    logger.warning("delete: chunk_entities cleanup failed for %s: %s", document_ulid, exc)

        # 4. Prune entities orphaned by this delete. Shared entities (still
        # referenced by another document's chunks or any relationship reaching
        # a live entity) survive. Two-phase closure: an entity is prunable
        # when it has no chunk references left AND every incident edge touches
        # only chunkless entities (otherwise the edge is shared knowledge and
        # both it and the entity stay). Relationships have no document link,
        # so edges between two pruned entities are removed with them; every
        # other edge is kept. Errs toward keeping.
        async def _has_chunk_refs(eid: str) -> bool:
            try:
                return bool(await self.db.collection("chunk_entities").find_one({"entity_id": eid}))
            except Exception as exc:
                logger.warning("delete: chunk-ref check failed for %s: %s", eid, exc)
                return True  # fail closed: keep the entity

        async def _incident_edges(eid: str) -> list[dict]:
            rows: list[dict] = []
            for key in ("source_entity_id", "target_entity_id"):
                try:
                    rows.extend(
                        await self.db.collection("relationships").find({key: eid}).to_list(10000)
                    )
                except Exception as exc:
                    logger.warning("delete: edge lookup failed for %s: %s", eid, exc)
            return rows

        chunkless = {eid for eid in entity_ids if not await _has_chunk_refs(eid)}
        prune_set: set[str] = set()
        for eid in sorted(chunkless):
            try:
                shared = False
                for row in await _incident_edges(eid):
                    other = row.get("target_entity_id" if row.get("source_entity_id") == eid else "source_entity_id")
                    if not other:
                        continue
                    if other not in chunkless and await _has_chunk_refs(other):
                        shared = True  # edge reaches live, chunk-backed knowledge
                        break
                    if other not in entity_ids:
                        # Edge reaches an entity outside this delete entirely:
                        # shared knowledge — keep both the edge and eid.
                        shared = True
                        break
                if not shared:
                    prune_set.add(eid)
            except Exception as exc:
                logger.warning("delete: prune evaluation failed for %s: %s", eid, exc)
        for eid in sorted(prune_set):
            try:
                # Remove every incident edge (PG cascades these automatically on
                # entity delete; explicit here for backends without cascades —
                # by construction no kept entity depends on them, see above).
                for key in ("source_entity_id", "target_entity_id"):
                    try:
                        rres = await self.db.collection("relationships").delete_many({key: eid})
                        deleted["relationships_removed"] += rres.deleted_count
                    except Exception as exc:
                        logger.warning("delete: relationship cleanup failed for %s: %s", eid, exc)
                eres = await self.db.collection("entities").delete_many({"id": eid})
                deleted["entities_pruned"] += eres.deleted_count
            except Exception as exc:
                logger.warning("delete: entity prune failed for %s: %s", eid, exc)

        # 4b. In-memory graph structures (memory DB stores edges only in dicts,
        # never in chunk_entities/relationships collections).
        if chunk_ulids:
            try:
                remover = getattr(self.graph_store, "remove_chunks", None)
                if callable(remover):
                    stats = remover(chunk_ulids)
                    if isinstance(stats, dict):
                        deleted["entities_pruned"] += int(stats.get("entities", 0) or 0)
                        deleted["relationships_removed"] += int(stats.get("edges", 0) or 0)
            except Exception as exc:
                logger.warning("delete: memory graph prune failed for %s: %s", document_ulid, exc)

        # 5. Indexed row last: afterwards repeats cleanly return not-found.
        try:
            ires = await self.db.collection("indexed_documents").delete_many(
                {"_id": document_ulid, "user_id": user_id, "session_id": session_id}
            )
            deleted["indexed_documents"] = ires.deleted_count
        except Exception as exc:
            logger.warning("delete: indexed row removal failed for %s: %s", document_ulid, exc)

        return {
            "document_id": document_ulid,
            "filename": record.get("filename"),
            **deleted,
        }
