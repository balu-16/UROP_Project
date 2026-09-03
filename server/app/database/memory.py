import copy
import re
from collections import defaultdict
from typing import Any


class InsertOneResult:
    def __init__(self, inserted_id: Any):
        self.inserted_id = inserted_id


class UpdateResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


class DeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        if key == "$or":
            # $or: list of sub-queries — at least one must match
            if not isinstance(expected, list):
                return False
            if not any(_matches(document, sub) for sub in expected):
                return False
            continue
        value = document.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
            if "$lt" in expected:
                if value is None or value >= expected["$lt"]:
                    return False
            if "$lte" in expected:
                if value is None or value > expected["$lte"]:
                    return False
            if "$gt" in expected:
                if value is None or value <= expected["$gt"]:
                    return False
            if "$gte" in expected:
                if value is None or value < expected["$gte"]:
                    return False
            if "$regex" in expected:
                flags = re.I if "i" in expected.get("$options", "") else 0
                if not re.search(expected["$regex"], str(value or ""), flags):
                    return False
        elif value != expected:
            return False
    return True


def _set_nested(document: dict[str, Any], key: str, value: Any) -> None:
    keys = key.split(".")
    current = document
    for k in keys[:-1]:
        if k not in current or not isinstance(current[k], dict):
            current[k] = {}
        current = current[k]
    current[keys[-1]] = value


def _get_nested(document: dict[str, Any], key: str, default: Any = None) -> Any:
    keys = key.split(".")
    current = document
    for k in keys:
        if not isinstance(current, dict) or k not in current:
            return default
        current = current[k]
    return current


def _apply_update(document: dict[str, Any], update: dict[str, Any]) -> None:
    if "$set" in update:
        for key, value in update["$set"].items():
            if "." in key:
                _set_nested(document, key, value)
            else:
                document[key] = value
    if "$inc" in update:
        for key, value in update["$inc"].items():
            if "." in key:
                current = _get_nested(document, key, 0)
                _set_nested(document, key, current + value)
            else:
                document[key] = document.get(key, 0) + value


class MemoryCursor:
    def __init__(self, documents: list[dict[str, Any]]):
        self.documents = [copy.deepcopy(doc) for doc in documents]

    def sort(self, key: str, direction: int):
        reverse = direction < 0
        # None always sorts last regardless of direction:
        # ascending  → (False, value) before (True, _)
        # descending → (True, _)      before (False, value)  — flip the None flag
        self.documents.sort(
            key=lambda item: (
                item.get(key) is not None if reverse else item.get(key) is None,
                item.get(key),
            ),
            reverse=reverse,
        )
        return self

    def limit(self, count: int):
        self.documents = self.documents[:count]
        return self

    async def to_list(self, length: int | None = None):
        if length is None:
            return self.documents
        return self.documents[:length]


class MemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self.documents: list[dict[str, Any]] = []
        self.indexes: list[tuple[Any, Any]] = []
        self._id_index: dict[str, dict[str, Any]] = {}

    async def insert_one(self, document: dict[str, Any]):
        stored = copy.deepcopy(document)
        for keys, unique in self.indexes:
            if not unique:
                continue
            if isinstance(keys, str):
                keys = [keys]
            query = {key: stored.get(key) for key in keys}
            if any(_matches(doc, query) for doc in self.documents):
                raise ValueError(f"Duplicate key for index on {keys}")
        self.documents.append(stored)
        if "_id" in stored:
            self._id_index[stored["_id"]] = stored
        return InsertOneResult(stored.get("_id"))

    async def find_one(self, query: dict[str, Any]):
        if set(query.keys()) == {"_id"} and query["_id"] in self._id_index:
            return copy.deepcopy(self._id_index[query["_id"]])
        for document in self.documents:
            if _matches(document, query):
                return copy.deepcopy(document)
        return None

    def find(self, query: dict[str, Any] | None = None):
        query = query or {}
        return MemoryCursor([doc for doc in self.documents if _matches(doc, query)])

    async def update_one(
        self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ):
        for document in self.documents:
            if _matches(document, query):
                # Snapshot fields that will be touched before applying the update
                touched_keys: list[str] = []
                if "$set" in update:
                    touched_keys.extend(update["$set"].keys())
                if "$inc" in update:
                    touched_keys.extend(update["$inc"].keys())
                before = {
                    key: copy.deepcopy(_get_nested(document, key))
                    for key in touched_keys
                }

                _apply_update(document, update)

                # Check whether any field actually changed
                actually_modified = False
                for key in touched_keys:
                    after = _get_nested(document, key)
                    # $inc always modifies unless increment is 0
                    if "$inc" in update and key in update["$inc"]:
                        if update["$inc"][key] != 0:
                            actually_modified = True
                            break
                    elif before[key] != after:
                        actually_modified = True
                        break

                if "_id" in document:
                    self._id_index[document["_id"]] = document
                return UpdateResult(1, 1 if actually_modified else 0)
        if upsert:
            new_document = copy.deepcopy(query)
            _apply_update(new_document, update)
            self.documents.append(new_document)
            if "_id" in new_document:
                self._id_index[new_document["_id"]] = new_document
            return UpdateResult(0, 1)
        return UpdateResult(0, 0)

    async def delete_one(self, query: dict[str, Any]):
        for index, document in enumerate(self.documents):
            if _matches(document, query):
                if "_id" in document:
                    self._id_index.pop(document["_id"], None)
                del self.documents[index]
                return DeleteResult(1)
        return DeleteResult(0)

    async def delete_many(self, query: dict[str, Any]):
        removed = [doc for doc in self.documents if _matches(doc, query)]
        self.documents = [doc for doc in self.documents if not _matches(doc, query)]
        for doc in removed:
            if "_id" in doc:
                self._id_index.pop(doc["_id"], None)
        return DeleteResult(len(removed))

    async def create_index(self, keys, unique: bool = False):
        self.indexes.append((keys, unique))
        return f"{self.name}_{len(self.indexes)}"


class MemoryDatabase:
    def __init__(self):
        self._collections: dict[str, MemoryCollection] = defaultdict(
            lambda: MemoryCollection("")
        )

    def __getitem__(self, name: str) -> MemoryCollection:
        if name not in self._collections or self._collections[name].name == "":
            self._collections[name] = MemoryCollection(name)
        return self._collections[name]
