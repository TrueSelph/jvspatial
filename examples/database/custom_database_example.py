"""
Example of extending jvspatial with a custom database implementation.

This demonstrates how developers can create their own database adapters
that integrate seamlessly with the jvspatial framework, including:
1. Implementing the Database abstract class
2. Registering custom database types with the factory system
3. Using custom databases with create_database() and multi-database management

For comprehensive documentation, see: docs/md/custom-database-guide.md
"""

import asyncio
from typing import Any, Dict, List, Optional

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Node
from jvspatial.db import (
    Database,
    create_database,
    list_database_types,
    register_database_type,
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


def create_memory_db(**kwargs: Any) -> MemoryDatabase:
    """Factory function for creating MemoryDatabase instances.

    This factory function is used when registering the database type
    with jvspatial's factory system.
    """
    return MemoryDatabase(**kwargs)


async def main():
    """Demonstrate custom database usage with registry integration."""

    print("=" * 60)
    print("Custom Database Example")
    print("=" * 60)

    # Method 1: Direct instantiation (works but not integrated with factory)
    print("\n1. Direct instantiation...")
    memory_db = MemoryDatabase()
    context = GraphContext(database=memory_db)
    set_default_context(context)

    city1 = await City.create(name="New York", population=8000000)
    city2 = await City.create(name="Los Angeles", population=4000000)
    print(f"   ✅ Created cities: {city1.name}, {city2.name}")

    retrieved_city = await City.get(city1.id)
    if retrieved_city:
        print(
            f"   ✅ Retrieved city: {retrieved_city.name} (pop: {retrieved_city.population})"
        )

    all_nodes = await memory_db.find("node", {})
    print(f"   ✅ Total nodes in custom database: {len(all_nodes)}")

    # Method 2: Register and use with factory system (recommended)
    print("\n2. Registering custom database type...")
    register_database_type("memory", create_memory_db)
    print("   ✅ Registered 'memory' database type")

    # List available database types
    print("\n3. Available database types:")
    types = list_database_types()
    for db_type, description in types.items():
        print(f"   - {db_type}: {description}")

    # Method 3: Use with create_database() (seamless integration)
    print("\n4. Using registered database with create_database()...")
    memory_db2 = create_database("memory")
    context2 = GraphContext(database=memory_db2)
    set_default_context(context2)

    city3 = await City.create(name="Chicago", population=2700000)
    print(f"   ✅ Created city using factory: {city3.name}")

    # Method 4: Use with multi-database management
    print("\n5. Using with multi-database management...")
    from jvspatial.db import get_database_manager

    manager = get_database_manager()
    memory_db3 = create_database("memory", register=True, name="memory_app")
    manager.set_current_database("memory_app")

    city4 = await City.create(name="Houston", population=2300000)
    print(f"   ✅ Created city in registered database: {city4.name}")

    # Verify isolation
    current_db = manager.get_current_database()
    all_cities = await current_db.find("node", {})
    print(f"   ✅ Cities in registered database: {len(all_cities)}")

    print("\n" + "=" * 60)
    print("✅ Custom database implementation working correctly!")
    print("=" * 60)
    print("\nFor comprehensive documentation, see: docs/md/custom-database-guide.md")


if __name__ == "__main__":
    asyncio.run(main())
