"""PG-backed graph store. Uses Supabase tables:

  documents, chunks, entities, chunk_entities, relationships

PG is truth, Chroma is index.
Provides getOneHop / getTwoHop via batched SQL.
"""
from typing import Any
import uuid

from app.config import Settings
from app.database import AppDatabase
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_entity(text: str) -> str:
    return " ".join(text.lower().strip().split())


class PGGraphStore:
    def __init__(self, settings: Settings, db: AppDatabase):
        self.settings = settings
        self.db = db
        # In-memory caches to avoid repeated PG roundtrips in ephemeral fallback
        # When Supabase is unavailable, we still keep graph in PG, but for tests/memory we use local dicts
        self._use_memory = db.db.__class__.__name__ == "MemoryDatabase" if hasattr(db, "db") and db.db else True
        # Fallback local structures when PG not available (tests)
        self._entity_to_chunks: dict[str, set[str]] = {}
        self._chunk_to_entities: dict[str, set[str]] = {}
        self._graph_edges: dict[str, set[str]] = {}  # entity -> neighbors

    def startup(self) -> None:
        # No file to load; PG tables are source of truth.
        # For memory DB, no-op.
        logger.info("PGGraphStore startup (use_memory=%s)", self._use_memory)

    def _ensure_supabase_tables(self):
        # Tables are created via migration; assume exist.
        pass

    async def add_chunk(self, chunk_id: str, entities: list[dict[str, Any]]) -> None:
        """Upsert entities, link chunk_entities, create relationships (mentioned_with)."""
        normalized = []
        for item in entities:
            txt = item.get("text") or item.get("name") or ""
            if not txt:
                continue
            norm = _normalize_entity(str(txt))
            if norm:
                normalized.append((norm, item))
        # Deduplicate by normalized name
        seen: dict[str, dict[str, Any]] = {}
        for norm, item in normalized:
            if norm not in seen:
                seen[norm] = item
        if not seen:
            return

        if self._use_memory:
            # Memory fallback — same edge logic over in-memory dicts
            for norm in seen:
                self._entity_to_chunks.setdefault(norm, set()).add(chunk_id)
                self._chunk_to_entities.setdefault(chunk_id, set()).add(norm)
                self._graph_edges.setdefault(norm, set())
            # Create edges among entities in same chunk
            norms = list(seen.keys())
            for i, left in enumerate(norms):
                for right in norms[i + 1 :]:
                    if left == right:
                        continue
                    self._graph_edges.setdefault(left, set()).add(right)
                    self._graph_edges.setdefault(right, set()).add(left)
            return

        # Supabase PG path
        try:
            supa = self.db.db.client if hasattr(self.db.db, "client") else None
            if supa is None:
                # No supabase client, fallback to memory
                return await self.add_chunk_memory_fallback(chunk_id, list(seen.keys()))

            # Upsert entities: try insert, on conflict do select
            entity_ids: dict[str, str] = {}  # norm -> uuid
            for norm, item in seen.items():
                # Check existing
                res = supa.table("entities").select("id").eq("name", norm).limit(1).execute()
                if res.data:
                    entity_ids[norm] = res.data[0]["id"]
                else:
                    # Insert
                    ins = supa.table("entities").insert({"name": norm, "type": item.get("label") or item.get("type") or "UNKNOWN", "metadata": {}}).execute()
                    if ins.data:
                        entity_ids[norm] = ins.data[0]["id"]
                    else:
                        # fetch again
                        res2 = supa.table("entities").select("id").eq("name", norm).limit(1).execute()
                        if res2.data:
                            entity_ids[norm] = res2.data[0]["id"]

            # Need chunk uuid: chunks table uses uuid id, but chunk_id is ULID string for Chroma.
            # We stored chunk_id in chunks.chunk_id column, need to resolve chunk uuid.
            # If chunk not yet inserted (ingestion order), we skip linking until chunk exists.
            # Try to find chunk uuid by chunk_id
            chunk_uuid: str | None = None
            try:
                cres = supa.table("chunks").select("id").eq("chunk_id", chunk_id).limit(1).execute()
                if cres.data:
                    chunk_uuid = cres.data[0]["id"]
            except Exception:
                pass

            if chunk_uuid:
                for norm, eid in entity_ids.items():
                    try:
                        supa.table("chunk_entities").insert({"chunk_id": chunk_uuid, "entity_id": eid}).execute()
                    except Exception:
                        # duplicate, ignore
                        pass

            # Create relationships (undirected: insert both directions or single with relation_type)
            norms = list(seen.keys())
            for i, left in enumerate(norms):
                for right in norms[i + 1 :]:
                    if left == right:
                        continue
                    lid = entity_ids.get(left)
                    rid = entity_ids.get(right)
                    if not lid or not rid:
                        continue
                    # Check existing relationship
                    try:
                        existing = supa.table("relationships").select("id").eq("source_entity_id", lid).eq("target_entity_id", rid).limit(1).execute()
                        if not existing.data:
                            existing2 = supa.table("relationships").select("id").eq("source_entity_id", rid).eq("target_entity_id", lid).limit(1).execute()
                            if not existing2.data:
                                supa.table("relationships").insert(
                                    {"source_entity_id": lid, "target_entity_id": rid, "relation_type": "mentioned_with", "metadata": {}}
                                ).execute()
                    except Exception as e:
                        logger.debug("PG relationship insert skip: %s", e)

        except Exception as exc:
            logger.exception("PGGraphStore add_chunk failed, fallback to memory: %s", exc)
            # fallback to memory structures so graph still works even if PG write fails
            for norm in seen:
                self._entity_to_chunks.setdefault(norm, set()).add(chunk_id)
                self._chunk_to_entities.setdefault(chunk_id, set()).add(norm)
                self._graph_edges.setdefault(norm, set())
            norms = list(seen.keys())
            for i, left in enumerate(norms):
                for right in norms[i + 1 :]:
                    self._graph_edges.setdefault(left, set()).add(right)
                    self._graph_edges.setdefault(right, set()).add(left)

    async def add_chunk_memory_fallback(self, chunk_id: str, norms: list[str]):
        for norm in norms:
            self._entity_to_chunks.setdefault(norm, set()).add(chunk_id)
            self._chunk_to_entities.setdefault(chunk_id, set()).add(norm)
            self._graph_edges.setdefault(norm, set())
        for i, left in enumerate(norms):
            for right in norms[i + 1 :]:
                self._graph_edges.setdefault(left, set()).add(right)
                self._graph_edges.setdefault(right, set()).add(left)

    def remove_chunks(self, chunk_ids: list[str]) -> dict[str, int]:
        """Prune in-memory graph structures for deleted chunks.

        PG mode needs no action here (collections + cascades own truth);
        memory mode stores edges only in these dicts, so explicit cleanup is
        required or deletes leak across docs/users. Best-effort, never raises.
        Returns counts for telemetry.
        """
        removed_links = 0
        pruned_entities = 0
        pruned_edges = 0
        try:
            targets = set(chunk_ids or [])
            if not targets:
                return {"links": 0, "entities": 0, "edges": 0}
            # Detach chunks from entities
            for cid in list(targets):
                ents = self._chunk_to_entities.pop(cid, set())
                for ent in ents:
                    s = self._entity_to_chunks.get(ent)
                    if s is not None:
                        s.discard(cid)
                        removed_links += 1
            # Prune entities with no chunk refs left (shared entities survive)
            for ent in list(self._entity_to_chunks.keys()):
                if not self._entity_to_chunks.get(ent):
                    # Remove incident edges
                    neighbors = self._graph_edges.pop(ent, set())
                    pruned_edges += len(neighbors)
                    for other in neighbors:
                        adj = self._graph_edges.get(other)
                        if adj is not None:
                            adj.discard(ent)
                    del self._entity_to_chunks[ent]
                    pruned_entities += 1
        except Exception:
            pass
        return {"links": removed_links, "entities": pruned_entities, "edges": pruned_edges}

    async def expand_chunks(
        self,
        seed_chunk_ids: list[str],
        hops: int,
        max_entities: int = 40,
        max_chunks: int = 200,
        allowed_chunk_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Batched graph expansion. Deduplicates, prevents cycles, respects MAX_GRAPH_NODES / MAX_HOPS.

        When allowed_chunk_ids is given (one chat's chunks), the walk may pass
        through shared entities but only chunks in the set are returned — so a
        chat never receives another chat's documents via the graph.
        """
        if not seed_chunk_ids:
            return {"chunk_ids": [], "seed_entities": [], "expanded_entities": [], "hops": hops}

        if self._use_memory or not hasattr(self.db.db, "client") or self.db.db.client is None:
            return self._expand_memory(seed_chunk_ids, hops, max_entities, max_chunks, allowed_chunk_ids)

        # PG path
        try:
            supa = self.db.db.client
            # Step 1: seed entities via chunk_entities + chunks join
            # Need to map chunk_id (ULID string) -> chunk uuid -> entity_ids
            # Do batched query: select chunk uuids for seed chunk_ids
            chunk_uuids: list[str] = []
            uuid_by_chunk_id: dict[str, str] = {}
            # Supabase in filter: .in_("chunk_id", seed_chunk_ids)
            try:
                cres = supa.table("chunks").select("id,chunk_id").in_("chunk_id", seed_chunk_ids).execute()
                for row in cres.data or []:
                    chunk_uuids.append(row["id"])
                    uuid_by_chunk_id[row["chunk_id"]] = row["id"]
            except Exception:
                # Fallback: individual queries
                for cid in seed_chunk_ids:
                    try:
                        r = supa.table("chunks").select("id").eq("chunk_id", cid).limit(1).execute()
                        if r.data:
                            chunk_uuids.append(r.data[0]["id"])
                            uuid_by_chunk_id[cid] = r.data[0]["id"]
                    except Exception:
                        continue

            if not chunk_uuids:
                # No PG chunks yet (maybe ingestion hasn't committed), fallback to memory
                return self._expand_memory(seed_chunk_ids, hops, max_entities, max_chunks, allowed_chunk_ids)

            # Get seed entity ids
            seed_entity_ids: set[str] = set()
            try:
                eres = supa.table("chunk_entities").select("entity_id").in_("chunk_id", chunk_uuids).execute()
                for row in eres.data or []:
                    seed_entity_ids.add(row["entity_id"])
            except Exception as exc:
                logger.debug("PG seed entities fetch failed: %s", exc)
                return self._expand_memory(seed_chunk_ids, hops, max_entities, max_chunks, allowed_chunk_ids)

            if not seed_entity_ids:
                return {"chunk_ids": list(seed_chunk_ids), "seed_entities": [], "expanded_entities": [], "hops": hops}

            # Check max_entities limit
            # Resolve entity names for return value (optional)
            seed_entity_names = set()
            try:
                nres = supa.table("entities").select("id,name").in_("id", sorted(seed_entity_ids)[:max_entities]).execute()
                for row in nres.data or []:
                    seed_entity_names.add(row["name"])
            except Exception:
                pass

            visited = set(seed_entity_ids)
            frontier = set(seed_entity_ids)
            for _ in range(hops):
                if not frontier:
                    break
                # Batch fetch relationships where source in frontier
                frontier_list = sorted(frontier)[:max_entities]
                next_frontier: set[str] = set()
                try:
                    # Query both directions: source in frontier OR target in frontier (undirected)
                    # For simplicity, query source in frontier, then target in frontier separately and union
                    r1 = supa.table("relationships").select("source_entity_id,target_entity_id").in_("source_entity_id", frontier_list).execute()
                    for row in r1.data or []:
                        next_frontier.add(row["target_entity_id"])
                    r2 = supa.table("relationships").select("source_entity_id,target_entity_id").in_("target_entity_id", frontier_list).execute()
                    for row in r2.data or []:
                        next_frontier.add(row["source_entity_id"])
                except Exception as exc:
                    logger.debug("PG hop fetch failed: %s", exc)
                    break
                next_frontier -= visited
                if not next_frontier:
                    break
                # Respect max_entities overall
                if len(visited) + len(next_frontier) > max_entities:
                    # trim
                    next_frontier = set(sorted(next_frontier)[: max_entities - len(visited)])
                visited.update(next_frontier)
                frontier = next_frontier
                if len(visited) >= max_entities:
                    break

            # Collect chunks for visited entities
            chunk_ids: set[str] = set(seed_chunk_ids)
            if visited:
                try:
                    # Get chunk uuids for visited entities
                    c2 = supa.table("chunk_entities").select("chunk_id").in_("entity_id", sorted(visited)).execute()
                    chunk_uuid_set = {row["chunk_id"] for row in c2.data or []}
                    if chunk_uuid_set:
                        # Need to map back to chunk_id strings (ULIDs)
                        # Already have uuid -> chunk_id mapping limited; fetch all
                        cres2 = supa.table("chunks").select("chunk_id").in_("id", sorted(chunk_uuid_set)[:max_chunks]).execute()
                        for row in cres2.data or []:
                            chunk_ids.add(row["chunk_id"])
                            if len(chunk_ids) >= max_chunks:
                                break
                except Exception as exc:
                    logger.debug("PG chunk expansion fetch failed: %s", exc)
                    # fallback to memory for chunks
                    for eid in visited:
                        # memory fallback lookup would need entity name; skip
                        pass

            # Limit (session allow-list applied: only this chat's chunks leave the graph).
            # Sorted for deterministic output across runs (set order is hash-randomized).
            chunk_list = sorted(chunk_ids)[:max_chunks]
            if allowed_chunk_ids is not None:
                seeds = set(seed_chunk_ids)
                chunk_list = [cid for cid in chunk_list if cid in allowed_chunk_ids or cid in seeds][:max_chunks]
            # For return, also include expanded entity names
            expanded_names = set(seed_entity_names)
            try:
                nres2 = supa.table("entities").select("name").in_("id", list(visited)).execute()
                for row in nres2.data or []:
                    expanded_names.add(row["name"])
            except Exception:
                pass

            return {
                "chunk_ids": chunk_list,
                "seed_entities": list(seed_entity_names),
                "expanded_entities": list(expanded_names),
                "hops": hops,
            }
        except Exception as exc:
            logger.exception("PGGraphStore expand_chunks PG failed, fallback to memory: %s", exc)
            return self._expand_memory(seed_chunk_ids, hops, max_entities, max_chunks, allowed_chunk_ids)

    def _expand_memory(self, seed_chunk_ids: list[str], hops: int, max_entities: int, max_chunks: int, allowed_chunk_ids: set[str] | None = None) -> dict[str, Any]:
        seed_entities: set[str] = set()
        for cid in seed_chunk_ids:
            seed_entities.update(self._chunk_to_entities.get(cid, set()))
        visited = set(seed_entities)
        frontier = set(seed_entities)
        for _ in range(hops):
            next_frontier: set[str] = set()
            for ent in sorted(frontier)[:max_entities]:
                next_frontier.update(self._graph_edges.get(ent, set()))
            next_frontier -= visited
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        chunk_ids: set[str] = set(seed_chunk_ids)
        for ent in sorted(visited):
            chunk_ids.update(self._entity_to_chunks.get(ent, set()))
            if len(chunk_ids) >= max_chunks:
                break
        if allowed_chunk_ids is not None:
            seeds = set(seed_chunk_ids)
            chunk_ids = {cid for cid in chunk_ids if cid in allowed_chunk_ids or cid in seeds}
        return {
            "chunk_ids": sorted(chunk_ids)[:max_chunks],
            "seed_entities": sorted(seed_entities),
            "expanded_entities": sorted(visited),
            "hops": hops,
        }

    def stats(self) -> dict[str, int]:
        if self._use_memory or not hasattr(self.db.db, "client") or self.db.db.client is None:
            # memory stats
            edges = sum(len(v) for v in self._graph_edges.values()) // 2
            return {"nodes": len(self._entity_to_chunks), "edges": edges}
        # PG stats: count entities and relationships
        try:
            supa = self.db.db.client
            # Use head count via select with count
            ecount = supa.table("entities").select("id", count="exact").limit(1).execute()
            rcount = supa.table("relationships").select("id", count="exact").limit(1).execute()
            return {"nodes": ecount.count or 0, "edges": rcount.count or 0}
        except Exception:
            edges = sum(len(v) for v in self._graph_edges.values()) // 2
            return {"nodes": len(self._entity_to_chunks), "edges": edges}

    def save(self) -> None:
        # PG is already persisted; no file save
        pass

    def shutdown(self) -> None:
        pass
