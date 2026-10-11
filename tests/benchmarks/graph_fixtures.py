"""Shared graph seeding helpers for traversal benchmarks."""

from __future__ import annotations

from typing import Any, Protocol


class _GraphDb(Protocol):
    async def save(self, collection: str, data: dict[str, Any]) -> dict[str, Any]: ...


async def seed_chain_graph(db: _GraphDb, *, length: int = 50) -> str:
    """Linear chain n.0 -> n.1 -> ... -> n.(length-1). Returns root id."""
    for i in range(length):
        edges: list[str] = []
        if i < length - 1:
            edges = [f"e.{i}"]
        await db.save(
            "node",
            {
                "id": f"n.{i}",
                "entity": "n",
                "context": {"idx": i},
                "edges": edges,
            },
        )
    for i in range(length - 1):
        await db.save(
            "edge",
            {
                "id": f"e.{i}",
                "entity": "e",
                "context": {},
                "source": f"n.{i}",
                "target": f"n.{i + 1}",
            },
        )
    return "n.0"
