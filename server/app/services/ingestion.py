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

            # Legacy indexed_documents for existing metrics
            record = {
                "_id": document_id_ulid,
                "user_id": user_id,
                "session_id": session_id,
                "filename": metadata["source"],
                "metadata": metadata,
                "chunk_count": len(chunks),
                "created_at": utc_now(),
            }
            # Store PG trace inside metadata if needed (indexed_documents schema has no pg_document_id column)
            if pg_doc_uuid:
                record["metadata"] = {**metadata, "pg_document_id": pg_doc_uuid}
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
