"""Supabase adapter exposing a collection API used across the app.

Keeps services unchanged: db.collection("users").find_one({...})
Maps query operators ($lt, $gt, $or, $regex, ...) to PostgREST filters.
Tables use `_id text` primary keys to preserve existing ULID prefixes.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

# collection name → supabase table
TABLE_MAP = {
    "users": "users",
    "sessions": "auth_sessions",
    "auth_sessions": "auth_sessions",
    "chat_sessions": "chat_sessions",
    "messages": "messages",
    "retrieval_logs": "retrieval_logs",
    "reward_logs": "reward_logs",
    "indexed_documents": "indexed_documents",
    # new PG truth tables
    "documents": "documents",
    "chunks": "chunks",
    "entities": "entities",
    "chunk_entities": "chunk_entities",
    "relationships": "relationships",
}


def _to_iso(v: Any) -> Any:
    if isinstance(v, datetime):
        # Supabase expects ISO8601; ensure UTC
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return v


def _from_iso(v: Any) -> Any:
    if isinstance(v, str):
        try:
            # try parse timestamptz
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt
        except Exception:
            return v
    return v


def _deserialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert supabase row (with _id, timestamps as strings) back to app dict."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        # parse timestamps
        if k in ("created_at", "updated_at", "expires_at", "token_invalid_before"):
            v = _from_iso(v)
        out[k] = v
    return copy.deepcopy(out)


def _serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert app dict to supabase row."""
    out: dict[str, Any] = {}
    for k, v in doc.items():
        if k in ("created_at", "updated_at", "expires_at", "token_invalid_before"):
            v = _to_iso(v)
        # PG integer columns reject float; coerce known integer fields
        if k in ("latency_ms", "chunk_count") and isinstance(v, float):
            v = int(v)
        # Handle nested latency inside token_usage not needed
        out[k] = v
    return out


class SupabaseCursor:
    def __init__(self, client, table: str, query: dict[str, Any]):
        self.client = client
        self.table = table
        self.query = query or {}
        self._sort_key: str | None = None
        self._sort_dir: int = 1
        self._limit: int | None = None

    def sort(self, key: str, direction: int):
        self._sort_key = key
        self._sort_dir = direction
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def _build(self):
        q = self.client.table(self.table).select("*")
        q = _apply_query_filters(q, self.query)
        if self._sort_key:
            desc = self._sort_dir < 0
            # supabase-py order: .order(column, desc=bool)
            q = q.order(self._sort_key, desc=desc)
        if self._limit is not None:
            q = q.limit(self._limit)
        return q

    async def to_list(self, length: int | None = None):
        # length overrides limit if provided
        effective_limit = length if length is not None else self._limit
        if effective_limit is not None:
            self._limit = effective_limit
        # $or support for find: PostgREST builder can't express OR via chained
        # filters, so union per-branch queries in Python (branches are few).
        # Rest-keys (non-$or) are ANDed with every branch.
        if "$or" in (self.query or {}):
            rest = {k: v for k, v in (self.query or {}).items() if k != "$or"}
            seen: dict[str, dict[str, Any]] = {}
            for branch in self.query.get("$or", []) or []:
                merged = {**rest, **dict(branch)}
                sub = SupabaseCursor(self.client, self.table, merged)
                sub._sort_key = self._sort_key
                sub._sort_dir = self._sort_dir
                # Don't apply sub-limit per branch; slice at the end
                rows = await sub.to_list(length=None)
                for r in rows:
                    key = str(r.get("_id") or r.get("id") or id(r))
                    seen[key] = r
            rows = list(seen.values())
            # Apply sort in Python for $or union
            if self._sort_key:
                try:
                    rows.sort(key=lambda r: (r.get(self._sort_key) is None, r.get(self._sort_key)), reverse=(self._sort_dir < 0))
                except Exception:
                    pass
            if effective_limit is not None:
                rows = rows[:effective_limit]
            if length is not None:
                rows = rows[:length]
            return rows
        q = self._build()
        try:
            res = q.execute()
            rows = res.data or []
            # length slicing (PostgREST already limited, but do Python slice as fallback)
            if length is not None:
                rows = rows[:length]
            return [_deserialize_row(r) for r in rows]
        except Exception as exc:
            logger.exception("Supabase find failed on %s %s: %s", self.table, self.query, exc)
            return []


class SupabaseCollection:
    def __init__(self, client, table: str):
        self.client = client
        self.table = table

    async def insert_one(self, document: dict[str, Any]):
        from app.database.memory import InsertOneResult

        payload = _serialize_doc(copy.deepcopy(document))
        try:
            res = self.client.table(self.table).insert(payload).execute()
            # Supabase returns inserted rows in res.data
            inserted_id = payload.get("_id") or payload.get("id") or (res.data[0].get("_id") if res.data else None)
            return InsertOneResult(inserted_id)
        except Exception as exc:
            # Handle duplicate key (unique violation)
            msg = str(exc)
            if "duplicate" in msg.lower() or "unique" in msg.lower() or "23505" in msg:
                raise ValueError(f"Duplicate key for {self.table}: {exc}") from exc
            logger.exception("Supabase insert_one failed %s: %s", self.table, exc)
            raise

    async def find_one(self, query: dict[str, Any]):
        try:
            # $or for find_one: try branches in order, each ANDed with
            # rest-keys, return first hit.
            if query and "$or" in query:
                rest = {k: v for k, v in query.items() if k != "$or"}
                for branch in query.get("$or", []) or []:
                    merged = {**rest, **dict(branch)}
                    got = await self.find_one(merged)
                    if got:
                        return got
                return None
            q = self.client.table(self.table).select("*")
            q = _apply_query_filters(q, query)
            q = q.limit(1)
            res = q.execute()
            if res.data:
                return _deserialize_row(res.data[0])
            return None
        except Exception as exc:
            logger.exception("Supabase find_one failed %s %s: %s", self.table, query, exc)
            return None

    def find(self, query: dict[str, Any] | None = None):
        return SupabaseCursor(self.client, self.table, query or {})

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False):
        from app.database.memory import UpdateResult

        # $or cannot be expressed as a single PostgREST AND filter: resolve to a
        # concrete row first (honoring rest-keys), then update by that row's key.
        if query and "$or" in query:
            existing = await self.find_one(query)
            if not existing:
                if upsert:
                    new_doc = {k: v for k, v in query.items() if k != "$or"}
                    set_payload: dict[str, Any] = {}
                    if "$set" in update:
                        for k, v in update["$set"].items():
                            set_payload[k.split(".")[-1] if "." in k else k] = _to_iso(v)
                    new_doc.update(set_payload)
                    await self.insert_one(new_doc)
                    return UpdateResult(0, 1)
                return UpdateResult(0, 0)
            key = {"_id": existing["_id"]} if "_id" in existing else {"id": existing["id"]} if "id" in existing else None
            if key is None:
                return UpdateResult(0, 0)
            return await self.update_one(key, update, upsert=False)

        # Build $set payload
        set_payload: dict[str, Any] = {}
        if "$set" in update:
            for k, v in update["$set"].items():
                # handle dot-notation for nested? Not needed for current schemas — flatten
                if "." in k:
                    # Supabase tables are flat; dot notation maps to top-level for now
                    # For nested like "a.b", we keep as-is (not used in current code)
                    set_payload[k.split(".")[-1]] = _to_iso(v)
                else:
                    set_payload[k] = _to_iso(v)
        # $inc not used via Supabase directly; implement via read-modify-write fallback
        if "$inc" in update:
            # fetch current doc
            existing = await self.find_one(query)
            if existing:
                for k, inc_v in update["$inc"].items():
                    current = existing.get(k, 0) or 0
                    set_payload[k] = current + inc_v
            elif upsert:
                for k, inc_v in update["$inc"].items():
                    set_payload[k] = inc_v

        if not set_payload and not upsert:
            # nothing to set; treat as matched check
            existing = await self.find_one(query)
            if existing:
                return UpdateResult(1, 0)
            return UpdateResult(0, 0)

        if not query:
            # Guard: never run an unfiltered update (would touch every row).
            logger.error("Supabase update_one refused: empty query on %s", self.table)
            raise ValueError("update_one requires a non-empty query filter")
        try:
            # Build filtered update query
            q = self.client.table(self.table).update(set_payload)
            q = _apply_query_filters(q, query)
            res = q.execute()
            matched = len(res.data) if res.data else 0
            # Supabase update returns updated rows; modified_count = matched if payload differs
            # We assume modified if matched (no cheap diff)
            if matched > 0:
                return UpdateResult(1, 1)
            if upsert:
                # create new doc from query + set
                new_doc = copy.deepcopy(query)
                new_doc.update(set_payload)
                # ensure timestamps
                await self.insert_one(new_doc)
                return UpdateResult(0, 1)
            return UpdateResult(0, 0)
        except Exception as exc:
            logger.exception("Supabase update_one failed %s %s %s: %s", self.table, query, update, exc)
            raise

    async def delete_one(self, query: dict[str, Any]):
        from app.database.memory import DeleteResult

        try:
            # $or cannot be a single PostgREST filter: resolve first, delete by key.
            if query and "$or" in query:
                existing = await self.find_one(query)
                if not existing:
                    return DeleteResult(0)
                key = {"_id": existing["_id"]} if "_id" in existing else {"id": existing["id"]} if "id" in existing else None
                if key is None:
                    return DeleteResult(0)
                return await self.delete_one(key)
            if not query:
                # Guard: never run an unfiltered delete (would wipe the table).
                logger.error("Supabase delete_one refused: empty query on %s", self.table)
                return DeleteResult(0)
            # Need to fetch first to know if exists for count, then delete
            existing = await self.find_one(query)
            if not existing:
                return DeleteResult(0)
            q = self.client.table(self.table).delete()
            q = _apply_query_filters(q, query)
            # NOTE: PostgREST delete does not support .limit(1); the filter
            # (usually on unique _id) already scopes to one row.
            res = q.execute()
            deleted = len(res.data) if res.data else (1 if existing else 0)
            return DeleteResult(deleted if deleted else 1)
        except Exception as exc:
            logger.exception("Supabase delete_one failed %s %s: %s", self.table, query, exc)
            return DeleteResult(0)

    async def delete_many(self, query: dict[str, Any]):
        from app.database.memory import DeleteResult

        if not query:
            # Guard: never run an unfiltered mass delete.
            logger.error("Supabase delete_many refused: empty query on %s", self.table)
            return DeleteResult(0)
        try:
            # Handle $or specially: delete where any subquery matches ANDed with rest.
            if "$or" in query:
                rest = {k: v for k, v in query.items() if k != "$or"}
                total = 0
                for sub in query["$or"]:
                    merged = {**rest, **sub}
                    q = self.client.table(self.table).delete()
                    q = _apply_query_filters(q, merged)
                    res = q.execute()
                    total += len(res.data) if res.data else 0
                return DeleteResult(total)
            q = self.client.table(self.table).delete()
            q = _apply_query_filters(q, query)
            res = q.execute()
            deleted = len(res.data) if res.data else 0
            return DeleteResult(deleted)
        except Exception as exc:
            logger.exception("Supabase delete_many failed %s %s: %s", self.table, query, exc)
            return DeleteResult(0)

    async def create_index(self, keys, unique: bool = False):
        # Indexes are managed via migrations; no-op at runtime
        return f"{self.table}_{keys}"


def _apply_query_filters(query_builder, query: dict[str, Any]):
    """Apply a query dict to the PostgREST builder via supabase-py filters."""
    for key, expected in query.items():
        if key == "$or":
            # Handled at delete_many level; for find we do client-side fallback
            # For find, we cannot easily express OR via PostgREST builder without raw `or` param.
            # Fallback: ignore $or for builder and filter in Python after fetch (inefficient but rare)
            # Startup purge is the only $or user; handled in delete_many.
            continue
        if isinstance(expected, dict):
            # operator query
            if "$in" in expected:
                # supabase .in_(col, list)
                try:
                    query_builder = query_builder.in_(key, expected["$in"])
                except Exception:
                    # fallback to eq via or
                    pass
                continue
            if "$ne" in expected:
                query_builder = query_builder.neq(key, _to_iso(expected["$ne"]))
                continue
            if "$lt" in expected:
                query_builder = query_builder.lt(key, _to_iso(expected["$lt"]))
                continue
            if "$lte" in expected:
                query_builder = query_builder.lte(key, _to_iso(expected["$lte"]))
                continue
            if "$gt" in expected:
                query_builder = query_builder.gt(key, _to_iso(expected["$gt"]))
                continue
            if "$gte" in expected:
                query_builder = query_builder.gte(key, _to_iso(expected["$gte"]))
                continue
            if "$regex" in expected:
                pattern = expected["$regex"]
                options = expected.get("$options", "")
                # strip regex special chars for ilike fallback; use ilike %pattern%
                # Real regex via PostgREST: `key=regex`. Supabase-py doesn't expose, so use ilike
                clean = pattern.strip("^$.*+?[](){}|\\")
                if not clean:
                    clean = pattern
                if "i" in options:
                    query_builder = query_builder.ilike(key, f"%{clean}%")
                else:
                    query_builder = query_builder.like(key, f"%{clean}%")
                continue
            # unknown dict — fallback to eq
            query_builder = query_builder.eq(key, _to_iso(expected))
        else:
            query_builder = query_builder.eq(key, _to_iso(expected))
    return query_builder


class SupabaseDatabase:
    """Wraps supabase-py client to provide MemoryDatabase-compatible interface."""

    def __init__(self, supabase_client):
        self.client = supabase_client
        self._collections: dict[str, SupabaseCollection] = {}

    def __getitem__(self, name: str) -> SupabaseCollection:
        table = TABLE_MAP.get(name, name)
        if table not in self._collections:
            self._collections[table] = SupabaseCollection(self.client, table)
        # also cache by original name for quick lookup
        if name not in self._collections:
            self._collections[name] = self._collections[table]
        return self._collections[name]

    def collection(self, name: str) -> SupabaseCollection:
        return self.__getitem__(name)
