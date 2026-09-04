"""Stage 3 tests: document delete / un-upload.

Covers plan.md §9-11 (delete). Uses memory DB + fake vector store (PG-gated
live-DB coverage is unnecessary here: every query uses portable equality/$in
filters supported by both backends).
"""

import pytest

from app.config.settings import Settings
from app.database import AppDatabase
from app.services.ingestion import IngestionService


def _settings() -> Settings:
    return Settings(database_url="memory://delete-tests")


class FakeVectorStore:
    def __init__(self):
        self.deleted: list[list[str]] = []

    def delete(self, chunk_ids=None, user_id=None, session_id=None):
        self.deleted.append(list(chunk_ids or []))

    def size(self):
        return 0


async def _db() -> AppDatabase:
    db = AppDatabase(_settings())
    await db.connect()
    return db


async def _seed_two_doc_graph(db: AppDatabase):
    """Doc A (deleted later) shares eShared with surviving doc B."""
    async def put(coll: str, doc: dict):
        await db.collection(coll).insert_one(doc)

    # Survivor doc B
    await put("indexed_documents", {
        "_id": "docB", "user_id": "u", "session_id": "s",
        "filename": "b.pdf", "metadata": {"pg_document_id": "pgB", "source": "b.pdf"},
        "chunk_count": 1,
    })
    await put("documents", {"id": "pgB", "user_id": "u", "title": "b.pdf", "content": "b"})
    await put("chunks", {"id": "cuB", "document_id": "pgB", "chunk_index": 0,
                         "content": "bravo", "chunk_id": "chk_B", "metadata": {}})
    await put("chunk_entities", {"chunk_id": "cuB", "entity_id": "eShared"})
    await put("entities", {"id": "eShared", "name": "shared"})
    await put("entities", {"id": "eOther", "name": "other"})
    await put("relationships", {"source_entity_id": "eShared", "target_entity_id": "eOther",
                                "relation_type": "mentioned_with"})
    # Doomed doc A
    await put("indexed_documents", {
        "_id": "docA", "user_id": "u", "session_id": "s",
        "filename": "a.pdf", "metadata": {"pg_document_id": "pgA", "source": "a.pdf"},
        "chunk_count": 2,
    })
    await put("documents", {"id": "pgA", "user_id": "u", "title": "a.pdf", "content": "a"})
    for cuid, chk in (("cu1", "chk_1"), ("cu2", "chk_2")):
        await put("chunks", {"id": cuid, "document_id": "pgA", "chunk_index": 0,
                             "content": "alpha", "chunk_id": chk, "metadata": {}})
    await put("chunk_entities", {"chunk_id": "cu1", "entity_id": "eX"})
    await put("chunk_entities", {"chunk_id": "cu1", "entity_id": "eP1"})
    await put("chunk_entities", {"chunk_id": "cu2", "entity_id": "eShared"})
    await put("chunk_entities", {"chunk_id": "cu2", "entity_id": "eP2"})
    await put("entities", {"id": "eX", "name": "x"})
    await put("entities", {"id": "eP1", "name": "p1"})
    await put("entities", {"id": "eP2", "name": "p2"})
    # Closure pair: used only by A, edged to each other → both pruned + edge gone.
    await put("relationships", {"source_entity_id": "eP1", "target_entity_id": "eP2",
                                "relation_type": "mentioned_with"})


def _svc(db: AppDatabase, vs: FakeVectorStore) -> IngestionService:
    return IngestionService(_settings(), db, None, vs, None, None)


@pytest.mark.asyncio
async def test_delete_removes_all_artifacts_but_keeps_shared_entities():
    db = await _db()
    await _seed_two_doc_graph(db)
    vs = FakeVectorStore()
    report = await _svc(db, vs).delete_document("u", "s", "docA")

    assert report is not None
    assert report["documents"] == 1
    assert report["chunks"] == 2
    assert report["indexed_documents"] == 1
    assert sorted(vs.deleted[0]) == ["chk_1", "chk_2"]
    # eX + closure pair pruned; shared + other survive.
    remaining_entities = {e["id"] for e in await db.collection("entities").find().to_list(100)}
    assert remaining_entities == {"eShared", "eOther"}
    assert report["entities_pruned"] == 3
    # Closure edge gone; shared edge intact.
    remaining_edges = {
        (r["source_entity_id"], r["target_entity_id"])
        for r in await db.collection("relationships").find().to_list(100)
    }
    assert remaining_edges == {("eShared", "eOther")}
    # Survivor doc B fully intact (row, chunks, vectors untouched).
    assert await db.collection("indexed_documents").find_one({"_id": "docB"}) is not None
    assert await db.collection("documents").find_one({"id": "pgB"}) is not None
    assert [c["id"] for c in await db.collection("chunks").find().to_list(100)] == ["cuB"]
    assert all("chk_B" not in batch for batch in vs.deleted)


@pytest.mark.asyncio
async def test_delete_is_idempotent_and_session_isolated():
    db = await _db()
    await _seed_two_doc_graph(db)
    svc = _svc(db, FakeVectorStore())

    assert await svc.delete_document("u", "s", "docA") is not None
    assert await svc.delete_document("u", "s", "docA") is None  # repeat → not-found
    assert await svc.delete_document("u", "WRONG", "docB") is None  # other chat
    assert await svc.delete_document("intruder", "s", "docB") is None  # other user
    assert await svc.delete_document("u", "s", "nope") is None
    # Failed lookups delete nothing.
    assert await db.collection("indexed_documents").find_one({"_id": "docB"}) is not None


@pytest.mark.asyncio
async def test_delete_legacy_row_without_pg_link_removes_indexed_row():
    db = await _db()
    await db.collection("indexed_documents").insert_one({
        "_id": "legacy", "user_id": "u", "session_id": "s",
        "filename": "old.pdf", "metadata": {"source": "old.pdf"}, "chunk_count": 3,
    })
    vs = FakeVectorStore()
    report = await _svc(db, vs).delete_document("u", "s", "legacy")
    assert report is not None
    assert report["documents"] == 0  # nothing linkable in PG
    assert report["indexed_documents"] == 1
    # No stored chunk_ids and no Chroma collection: nothing addressable.
    assert vs.deleted == []
    assert await db.collection("indexed_documents").find_one({"_id": "legacy"}) is None


@pytest.mark.asyncio
async def test_delete_memory_row_with_stored_chunk_ids_cleans_vectors_and_graph():
    from app.graph_store.pg_store import PGGraphStore

    db = await _db()
    await db.collection("indexed_documents").insert_one({
        "_id": "mem1", "user_id": "u", "session_id": "s",
        "filename": "m.pdf", "metadata": {"source": "m.pdf"},
        "chunk_count": 2, "chunk_ids": ["chk_1", "chk_2"],
    })
    vs = FakeVectorStore()
    settings = _settings()
    graph = PGGraphStore(settings, db)
    await graph.add_chunk("chk_1", [{"text": "Alpha"}])
    await graph.add_chunk("chk_2", [{"text": "Beta"}])
    svc = IngestionService(settings, db, None, vs, graph, None)
    report = await svc.delete_document("u", "s", "mem1")
    assert report is not None
    # Stored ULIDs drive Chroma delete even without PG link.
    assert vs.deleted == [["chk_1", "chk_2"]]
    assert report["vectors"] == 2
    # Memory graph dicts pruned.
    assert graph._chunk_to_entities.get("chk_1") is None
    assert graph._chunk_to_entities.get("chk_2") is None


def test_delete_routes_registered_with_dual_prefix():
    from app.main import create_app

    paths = {
        (r.path, method)
        for r in create_app().routes
        for method in getattr(r, "methods", []) or []
    }
    assert ("/documents/{document_id}", "DELETE") in paths
    assert ("/api/documents/{document_id}", "DELETE") in paths
    assert ("/documents", "GET") in paths
    assert ("/api/documents", "GET") in paths


@pytest.mark.asyncio
async def test_list_impl_returns_session_scoped_documents():
    from app.api.ingestion import _list_impl

    class _State:
        class _Metrics:
            def record_request(self, _name: str):
                pass

        metrics = _Metrics()

    db = await _db()
    await db.collection("indexed_documents").insert_one({
        "_id": "d1", "user_id": "u", "session_id": "s",
        "filename": "a.pdf", "chunk_count": 2, "created_at": "2026-01-01T00:00:00+00:00",
    })
    await db.collection("indexed_documents").insert_one({
        "_id": "d2", "user_id": "u", "session_id": "other",
        "filename": "b.pdf", "chunk_count": 1, "created_at": "2026-01-01T00:00:00+00:00",
    })
    out = await _list_impl("s", {"_id": "u"}, db, _State())
    assert [d["_id"] for d in out["documents"]] == ["d1"]
    out_other_user = await _list_impl("s", {"_id": "intruder"}, db, _State())
    assert out_other_user["documents"] == []
