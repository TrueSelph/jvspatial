#!/usr/bin/env python3
"""
Custom Database Registry Example

Demonstrates how to create and register custom database implementations
using the new registry-based factory system in jvspatial.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add the current project to the Python path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from jvspatial.core import GraphContext, Node
from jvspatial.db import (
    Database,
    get_database,
    get_default_database_type,
    list_available_databases,
    register_database,
    set_default_database,
    unregister_database,
)


class InMemoryDatabase(Database):
    """Simple in-memory database implementation for demonstration."""

    def __init__(self, name: str = "memory_db"):
        """Initialize in-memory database.

        Args:
            name: Database instance name for identification
        """
        self.name = name
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        print(f"✅ Created InMemoryDatabase: {name}")

    async def clean(self) -> None:
        """Clean up orphaned edges with invalid node references."""
        if "edge" not in self._collections or "node" not in self._collections:
            return

        node_ids = set(self._collections["node"].keys())
        edge_collection = self._collections["edge"]

        orphaned_edges = []
        for edge_id, edge_data in edge_collection.items():
            source = edge_data.get("source") or edge_data.get("context", {}).get(
                "source"
            )
            target = edge_data.get("target") or edge_data.get("context", {}).get(
                "target"
            )

            if (source and source not in node_ids) or (
                target and target not in node_ids
            ):
                orphaned_edges.append(edge_id)

        for edge_id in orphaned_edges:
            del edge_collection[edge_id]

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save document to memory."""
        if collection not in self._collections:
            self._collections[collection] = {}

        if "id" not in data:
            raise KeyError("Document data must contain 'id' field")

        self._collections[collection][data["id"]] = data.copy()
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID from memory."""
        if collection not in self._collections:
            return None
        return self._collections[collection].get(id)

    async def delete(self, collection: str, id: str) -> None:
        """Delete document by ID from memory."""
        if collection in self._collections:
            self._collections[collection].pop(id, None)

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find documents matching query in memory."""
        if collection not in self._collections:
            return []

        results = []
        for doc in self._collections[collection].values():
            if self._matches_query(doc, query):
                results.append(doc)
        return results

    def _matches_query(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Simple query matching for demonstration."""
        if not query:  # Empty query matches all
            return True

        for key, condition in query.items():
            doc_value = doc.get(key)

            if isinstance(condition, dict):
                # Handle operators
                for op, value in condition.items():
                    if op == "$gt" and (doc_value is None or doc_value <= value):
                        return False
                    elif op == "$lt" and (doc_value is None or doc_value >= value):
                        return False
                    elif op == "$eq" and doc_value != value:
                        return False
            else:
                # Simple equality
                if doc_value != condition:
                    return False
        return True


class RedisLikeDatabase(Database):
    """Mock Redis-like database implementation for demonstration."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        """Initialize Redis-like database.

        Args:
            host: Redis host
            port: Redis port
            db: Database number
        """
        self.host = host
        self.port = port
        self.db = db
        self._data: Dict[str, Dict[str, Any]] = {}
        print(f"✅ Created RedisLikeDatabase: {host}:{port}/{db}")

    async def clean(self) -> None:
        """Clean up orphaned edges."""
        # Simplified cleanup for demo
        pass

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save to mock Redis."""
        key = f"{collection}:{data['id']}"
        self._data[key] = data.copy()
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Get from mock Redis."""
        key = f"{collection}:{id}"
        return self._data.get(key)

    async def delete(self, collection: str, id: str) -> None:
        """Delete from mock Redis."""
        key = f"{collection}:{id}"
        self._data.pop(key, None)

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find in mock Redis."""
        results = []
        prefix = f"{collection}:"
        for key, doc in self._data.items():
            if key.startswith(prefix):
                results.append(doc)
        return results


def memory_configurator(kwargs: Dict[str, Any]) -> InMemoryDatabase:
    """Configure InMemoryDatabase with custom parameters."""
    name = kwargs.get("name", "default_memory")
    return InMemoryDatabase(name)


def redis_configurator(kwargs: Dict[str, Any]) -> RedisLikeDatabase:
    """Configure RedisLikeDatabase with connection parameters."""
    host = kwargs.get("host", "localhost")
    port = kwargs.get("port", 6379)
    db = kwargs.get("db", 0)
    return RedisLikeDatabase(host, port, db)


async def demonstrate_custom_database_registry():
    """Demonstrate the custom database registry system."""

    print("🚀 Custom Database Registry Demo")
    print("=" * 50)

    # Show initial state
    print(f"\n📊 Initial State:")
    print(f"Available databases: {list(list_available_databases().keys())}")
    print(f"Default database: {get_default_database_type()}")

    # Register custom databases
    print(f"\n🔧 Registering Custom Databases:")

    register_database("memory", InMemoryDatabase, memory_configurator)
    print("✓ Registered 'memory' database")

    register_database("redis", RedisLikeDatabase, redis_configurator)
    print("✓ Registered 'redis' database")

    # Show updated state
    print(f"\n📊 After Registration:")
    print(f"Available databases: {list(list_available_databases().keys())}")
    print(f"Default database: {get_default_database_type()}")

    # Test creating different database instances
    print(f"\n🏗️  Creating Database Instances:")

    # Create in-memory database
    memory_db = get_database("memory", name="test_memory")
    print(f"✓ Created memory database: {memory_db.name}")

    # Create Redis-like database with custom config
    redis_db = get_database("redis", host="redis.example.com", port=6380, db=1)
    print(f"✓ Created Redis database: {redis_db.host}:{redis_db.port}/{redis_db.db}")

    # Create default (JSON) database
    json_db = get_database()
    print(f"✓ Created default database: {json_db.__class__.__name__}")

    # Test using custom database with GraphContext
    print(f"\n🧪 Testing Custom Database with GraphContext:")

    # Use in-memory database
    ctx = GraphContext(database=memory_db)

    class TestCity(Node):
        name: str = "Unknown"
        population: int = 0

    # Create some nodes
    city1 = await ctx.create(TestCity, name="New York", population=8000000)
    city2 = await ctx.create(TestCity, name="Los Angeles", population=4000000)

    print(f"✓ Created cities in memory database")

    # Connect them
    await city1.connect(city2)
    print(f"✓ Connected cities with edge")

    # Retrieve and verify
    retrieved = await ctx.get(TestCity, city1.id)
    print(f"✓ Retrieved city: {retrieved.name} ({retrieved.population:,})")

    # Test changing default database
    print(f"\n⚙️  Changing Default Database:")

    set_default_database("memory")
    print(f"✓ Set 'memory' as default database")
    print(f"New default: {get_default_database_type()}")

    # Create database with new default
    default_db = get_database()
    print(f"✓ Default database is now: {default_db.__class__.__name__}")

    # Test unregistering a database
    print(f"\n🗑️  Unregistering Database:")

    unregister_database("redis")
    print("✓ Unregistered 'redis' database")
    print(f"Available databases: {list(list_available_databases().keys())}")

    # Try to create unregistered database (should fail)
    try:
        get_database("redis")
        print("❌ ERROR: Should have failed!")
    except ValueError as e:
        print(f"✅ Expected error: {e}")

    # Test environment variable override
    print(f"\n🌍 Environment Variable Override:")
    import os

    # Temporarily set environment variable
    os.environ["JVSPATIAL_DB_TYPE"] = "memory"

    env_db = get_database()  # Should use environment variable
    print(f"✓ Environment override works: {env_db.__class__.__name__}")

    # Clean up environment
    del os.environ["JVSPATIAL_DB_TYPE"]

    # Demonstrate configurator flexibility
    print(f"\n🎛️  Configurator Flexibility:")

    # Create multiple memory databases with different names
    db1 = get_database("memory", name="database_one")
    db2 = get_database("memory", name="database_two")

    print(f"✓ Created {db1.name}")
    print(f"✓ Created {db2.name}")

    print(f"\n✅ Demo completed successfully!")
    print(f"\nThe registry system provides:")
    print(f"  • Easy registration of custom database implementations")
    print(f"  • Flexible configuration through custom configurators")
    print(f"  • Default database management")
    print(f"  • Environment variable overrides")
    print(f"  • Runtime registration and unregistration")


if __name__ == "__main__":
    asyncio.run(demonstrate_custom_database_registry())
