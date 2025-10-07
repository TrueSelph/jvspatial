"""
Example of extending jvspatial with a custom database implementation.

This demonstrates how developers can create their own database adapters
that integrate seamlessly with the jvspatial framework.
"""

import asyncio
from typing import Any, Dict, List, Optional

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node
from jvspatial.db import (
    Database,
    get_database,
    list_available_databases,
    register_database,
)


class MemoryDatabase(Database):
    """In-memory database implementation for testing/demo purposes.

    This is a simple example showing how to implement the Database interface.
    In production, you might implement adapters for Redis, SQLite, PostgreSQL, etc.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize memory database."""
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}

    async def clean(self) -> None:
        """Clean up orphaned edges with invalid node references."""
        if "node" not in self._collections or "edge" not in self._collections:
            return

        # Get all valid node IDs
        valid_node_ids = set(self._collections["node"].keys())

        # Find orphaned edges
        orphaned_edge_ids = []
        for edge_id, edge_data in self._collections["edge"].items():
            source = edge_data.get("source") or edge_data.get("context", {}).get(
                "source"
            )
            target = edge_data.get("target") or edge_data.get("context", {}).get(
                "target"
            )

            if (source and source not in valid_node_ids) or (
                target and target not in valid_node_ids
            ):
                orphaned_edge_ids.append(edge_id)

        # Remove orphaned edges
        for edge_id in orphaned_edge_ids:
            del self._collections["edge"][edge_id]

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save document to memory."""
        if "id" not in data:
            raise KeyError("Document data must contain 'id' field")

        if collection not in self._collections:
            self._collections[collection] = {}

        doc_id = data["id"]
        self._collections[collection][doc_id] = data.copy()
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        if collection not in self._collections:
            return None
        return self._collections[collection].get(id)

    async def delete(self, collection: str, id: str) -> None:
        """Delete document by ID."""
        if collection in self._collections:
            self._collections[collection].pop(id, None)

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find documents matching query."""
        if collection not in self._collections:
            return []

        results = []
        for doc in self._collections[collection].values():
            if self._matches_simple_query(doc, query):
                results.append(doc.copy())
        return results

    def _matches_simple_query(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Simple query matching (for demo purposes)."""
        if not query:  # Empty query matches all
            return True

        for key, value in query.items():
            if key not in doc or doc[key] != value:
                return False
        return True


class City(Node):
    """Example city node."""

    name: str = ""
    population: int = 0


async def main():
    """Demonstrate custom database usage."""

    # Register our custom database implementation
    register_database("memory", MemoryDatabase)

    print("Available database types:", list(list_available_databases().keys()))

    # Create a custom database instance
    memory_db = get_database(db_type="memory")

    # Create a graph context using our custom database
    context = GraphContext(database=memory_db)

    # Create some nodes using the custom database
    city1 = await context.create_node(City, name="New York", population=8000000)
    city2 = await context.create_node(City, name="Los Angeles", population=4000000)

    print(f"Created cities: {city1.name}, {city2.name}")

    # Retrieve nodes from the custom database
    retrieved_city = await context.get_node(City, city1.id)
    print(f"Retrieved city: {retrieved_city.name} (pop: {retrieved_city.population})")

    # Demonstrate that the custom database stores data correctly
    all_nodes = await memory_db.find("node", {})
    print(f"Total nodes in custom database: {len(all_nodes)}")

    print("✅ Custom database implementation working correctly!")


if __name__ == "__main__":
    asyncio.run(main())
