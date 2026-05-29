from fastapi import UploadFile

from app.config import Settings
from app.database import AppDatabase
from app.embeddings import EmbeddingService
from app.graph import EntityGraph
from app.services.chunking import Chunker
from app.services.document_parser import DocumentParser
from app.services.entity_extraction import EntityExtractor
from app.utils.ids import new_id
from app.utils.time import utc_now
from app.vectorstore import VectorStore


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        db: AppDatabase,
        embeddings: EmbeddingService,
        vector_store: VectorStore,
        entity_graph: EntityGraph,
        extractor: EntityExtractor,
    ):
        self.settings = settings
        self.db = db
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.entity_graph = entity_graph
        self.extractor = extractor
        self.parser = DocumentParser()
        self.chunker = Chunker(settings)

    async def index_uploads(self, user_id: str, files: list[UploadFile]) -> dict:
        documents = []
        total_chunks = 0
        total_entities = 0
        for file in files:
            text, metadata = await self.parser.parse_upload(
                file, self.settings.upload_max_mb
            )
            if not text.strip():
                continue  # skip empty files
            document_id = new_id("doc")
            chunks = self.chunker.chunk(document_id, text, metadata)
            chunk_metadata = []
            for chunk in chunks:
                entities = await self.extractor.extract(chunk["text"])
                entity_ids = [
                    EntityGraph.normalize_entity(entity["text"]) for entity in entities
                ]
                chunk["entity_ids"] = entity_ids
                self.entity_graph.add_chunk(chunk["chunk_id"], entities)
                chunk_metadata.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "document_id": document_id,
                        "text": chunk["text"],
                        "metadata": chunk["metadata"],
                        "entity_ids": entity_ids,
                        "user_id": user_id,
                    }
                )
                total_entities += len(entity_ids)
            if chunks:
                vectors = await self.embeddings.embed_texts(
                    [chunk["text"] for chunk in chunks]
                )
                self.vector_store.add(vectors, chunk_metadata)
            record = {
                "_id": document_id,
                "user_id": user_id,
                "filename": metadata["source"],
                "metadata": metadata,
                "chunk_count": len(chunks),
                "created_at": utc_now(),
            }
            await self.db.collection("indexed_documents").insert_one(record)
            documents.append(record)
            total_chunks += len(chunks)
        self.entity_graph.save()
        return {
            "documents": documents,
            "chunk_count": total_chunks,
            "entity_count": total_entities,
            "vector_index_size": self.vector_store.size(),
            "graph": self.entity_graph.stats(),
        }
