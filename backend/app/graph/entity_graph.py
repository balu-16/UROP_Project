import json
from collections import defaultdict
from typing import Any

import networkx as nx

from app.config import Settings


class EntityGraph:
    def __init__(self, settings: Settings):
        self.path = settings.resolved_storage_dir / "entity_graph.json"
        self.graph = nx.Graph()
        self.entity_to_chunks: dict[str, set[str]] = defaultdict(set)
        self.chunk_to_entities: dict[str, set[str]] = defaultdict(set)

    def startup(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text())
        self.graph = nx.node_link_graph(payload.get("graph", {}))
        self.entity_to_chunks = defaultdict(
            set, {k: set(v) for k, v in payload.get("entity_to_chunks", {}).items()}
        )
        self.chunk_to_entities = defaultdict(
            set, {k: set(v) for k, v in payload.get("chunk_to_entities", {}).items()}
        )

    def save(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "graph": nx.node_link_data(self.graph),
                    "entity_to_chunks": {
                        k: list(v) for k, v in self.entity_to_chunks.items()
                    },
                    "chunk_to_entities": {
                        k: list(v) for k, v in self.chunk_to_entities.items()
                    },
                },
                default=str,
            )
        )

    @staticmethod
    def normalize_entity(entity: str) -> str:
        return " ".join(entity.lower().strip().split())

    def add_chunk(self, chunk_id: str, entities: list[dict[str, Any]]) -> None:
        normalized = [
            self.normalize_entity(item["text"]) for item in entities if item.get("text")
        ]
        normalized = [item for item in normalized if item]
        for entity in normalized:
            self.graph.add_node(entity, kind="entity")
            self.entity_to_chunks[entity].add(chunk_id)
            self.chunk_to_entities[chunk_id].add(entity)
        for left_index, left in enumerate(normalized):
            for right in normalized[left_index + 1 :]:
                if left == right:
                    continue
                if self.graph.has_edge(left, right):
                    self.graph[left][right]["weight"] = (
                        self.graph[left][right].get("weight", 1) + 1
                    )
                else:
                    self.graph.add_edge(
                        left, right, relation="mentioned_with", weight=1
                    )

    def expand_chunks(
        self,
        seed_chunk_ids: list[str],
        hops: int,
        max_entities: int = 40,
        max_chunks: int = 200,
    ) -> dict[str, Any]:
        seed_entities: set[str] = set()
        for chunk_id in seed_chunk_ids:
            seed_entities.update(self.chunk_to_entities.get(chunk_id, set()))
        visited_entities = set(seed_entities)
        frontier = set(seed_entities)
        for _ in range(hops):
            next_frontier: set[str] = set()
            for entity in list(frontier)[:max_entities]:
                if entity not in self.graph:
                    continue
                next_frontier.update(
                    str(neighbor) for neighbor in self.graph.neighbors(entity)
                )
            next_frontier -= visited_entities
            visited_entities.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        chunk_ids: set[str] = set(seed_chunk_ids)
        for entity in visited_entities:
            chunk_ids.update(self.entity_to_chunks.get(entity, set()))
            if len(chunk_ids) >= max_chunks:
                break
        return {
            "chunk_ids": list(chunk_ids),
            "seed_entities": list(seed_entities),
            "expanded_entities": list(visited_entities),
            "hops": hops,
        }

    def stats(self) -> dict[str, int]:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }
