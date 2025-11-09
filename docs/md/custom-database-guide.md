# Custom Database Implementation Guide

This guide explains how to implement your own database backend for jvspatial using the abstract `Database` class. The architecture is designed for seamless extension, allowing you to integrate any database system while maintaining full compatibility with jvspatial's graph operations, multi-database management, and entity persistence.

---

## Table of Contents

1. [Overview](#overview)
2. [Database Interface](#database-interface)
3. [Implementation Steps](#implementation-steps)
4. [Registering Custom Databases](#registering-custom-databases)
5. [Complete Example](#complete-example)
6. [Best Practices](#best-practices)
7. [Advanced Topics](#advanced-topics)

---

## Overview

jvspatial uses an abstract `Database` class that defines a simple, collection-based interface for CRUD operations. This design allows you to:

- **Implement any database backend** (SQL databases, NoSQL databases, cloud storage, etc.)
- **Seamlessly integrate** with jvspatial's factory system
- **Use multi-database management** features with your custom database
- **Maintain compatibility** with all jvspatial features (GraphContext, Object persistence, etc.)

The architecture is **database-agnostic** - as long as you implement the four core methods (`save`, `get`, `delete`, `find`), your database will work with all jvspatial features.

---

## Database Interface

The `Database` abstract base class defines the following interface:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class Database(ABC):
    @abstractmethod
    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Args:
            collection: Collection name (e.g., 'node', 'edge', 'object')
            data: Record data dictionary (must include 'id' field)

        Returns:
            Saved record with any database-generated fields
        """
        pass

    @abstractmethod
    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data or None if not found
        """
        pass

    @abstractmethod
    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID.

        Args:
            collection: Collection name
            id: Record ID
        """
        pass

    @abstractmethod
    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

        Returns:
            List of matching records
        """
        pass

    # Optional convenience methods (have default implementations)
    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records matching a query."""
        results = await self.find(collection, query or {})
        return len(results)

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find the first record matching a query."""
        results = await self.find(collection, query)
        return results[0] if results else None
```

### Key Requirements

1. **All methods must be async** - jvspatial uses async/await throughout
2. **Collection-based organization** - Data is organized by collection names (`node`, `edge`, `object`, `walker`)
3. **ID-based operations** - Records must have an `id` field (string)
4. **Dictionary-based data** - All data is passed as dictionaries
5. **Query matching** - The `find()` method should support simple dictionary-based queries

---

## Implementation Steps

### Step 1: Create Your Database Class

Subclass `Database` and implement the four abstract methods:

```python
from typing import Any, Dict, List, Optional
from jvspatial.db import Database

class MyCustomDatabase(Database):
    """Custom database implementation."""

    def __init__(self, connection_string: str, **kwargs):
        """Initialize your database connection."""
        self.connection_string = connection_string
        # Initialize your database client here
        # self._client = YourDatabaseClient(connection_string)

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record."""
        # Ensure record has an ID
        if "id" not in data:
            raise ValueError("Record must have an 'id' field")

        # Save to your database
        # await self._client.save(collection, data)

        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        # return await self._client.get(collection, id)
        return None  # Placeholder

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        # await self._client.delete(collection, id)
        pass

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query."""
        # return await self._client.find(collection, query)
        return []
```

### Step 2: Implement Query Matching

The `find()` method should support simple dictionary-based queries. For example:

```python
async def find(
    self, collection: str, query: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Find records matching a query."""
    all_records = await self._get_all_records(collection)

    if not query:  # Empty query returns all records
        return all_records

    # Simple matching: all query fields must match
    results = []
    for record in all_records:
        if self._matches_query(record, query):
            results.append(record)

    return results

def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
    """Check if a record matches a query."""
    for key, expected_value in query.items():
        # Support dot notation for nested fields (e.g., "context.email")
        actual_value = self._get_nested_value(record, key)
        if actual_value != expected_value:
            return False
    return True

def _get_nested_value(self, data: Dict[str, Any], key: str) -> Any:
    """Get a nested value using dot notation."""
    keys = key.split(".")
    current = data
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return current
```

### Step 3: Handle Collection Organization

jvspatial uses the following collection names:
- `node` - Graph nodes
- `edge` - Graph edges
- `object` - Generic Object entities
- `walker` - Walker instances

Your database should organize data by these collection names. For SQL databases, you might use tables; for NoSQL, you might use collections or namespaces.

---

## Registering Custom Databases

Once you've implemented your database, register it with jvspatial's factory system to use it seamlessly with `create_database()`:

### Step 1: Create a Factory Function

```python
def create_my_custom_db(**kwargs) -> MyCustomDatabase:
    """Factory function for creating MyCustomDatabase instances."""
    connection_string = kwargs.get("connection_string", "default://")
    return MyCustomDatabase(connection_string=connection_string, **kwargs)
```

### Step 2: Register the Database Type

```python
from jvspatial.db import register_database_type

# Register your custom database
register_database_type("my_custom", create_my_custom_db)
```

### Step 3: Use It Like Built-in Types

```python
from jvspatial.db import create_database

# Create your custom database
db = create_database(
    "my_custom",
    connection_string="custom://example",
    register=True,
    name="custom_db"
)

# Use with GraphContext
from jvspatial.core.context import GraphContext
ctx = GraphContext(database=db)

# Use with multi-database management
from jvspatial.db import get_database_manager
manager = get_database_manager()
manager.register_database("app", db)
```

### Listing Available Database Types

```python
from jvspatial.db import list_database_types

types = list_database_types()
# Returns: {
#     "json": "JSON file-based database (built-in)",
#     "mongodb": "MongoDB database (built-in)",
#     "my_custom": "Custom database: create_my_custom_db"
# }
```

---

## Complete Example

Here's a complete example implementing a Redis-based database:

```python
import asyncio
import json
from typing import Any, Dict, List, Optional

from jvspatial.db import Database, register_database_type, create_database
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial import Object

# Assume redis is installed: pip install redis
try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class RedisDatabase(Database):
    """Redis-based database implementation."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        """Initialize Redis database.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
        """
        if redis is None:
            raise ImportError("redis package is required. Install with: pip install redis")

        self.host = host
        self.port = port
        self.db = db
        self._client: Optional[redis.Redis] = None

    async def _ensure_connected(self):
        """Ensure Redis connection is established."""
        if self._client is None:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True
            )

    def _get_key(self, collection: str, id: str) -> str:
        """Get Redis key for a record."""
        return f"jvspatial:{collection}:{id}"

    def _get_collection_key(self, collection: str) -> str:
        """Get Redis key for collection index."""
        return f"jvspatial:{collection}:index"

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to Redis."""
        await self._ensure_connected()

        if "id" not in data:
            raise ValueError("Record must have an 'id' field")

        # Store record as JSON
        key = self._get_key(collection, data["id"])
        await self._client.set(key, json.dumps(data))

        # Add to collection index
        index_key = self._get_collection_key(collection)
        await self._client.sadd(index_key, data["id"])

        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        await self._ensure_connected()

        key = self._get_key(collection, id)
        data = await self._client.get(key)

        if data is None:
            return None

        return json.loads(data)

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        await self._ensure_connected()

        key = self._get_key(collection, id)
        await self._client.delete(key)

        # Remove from collection index
        index_key = self._get_collection_key(collection)
        await self._client.srem(index_key, id)

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query."""
        await self._ensure_connected()

        # Get all IDs in collection
        index_key = self._get_collection_key(collection)
        ids = await self._client.smembers(index_key)

        if not query:  # Empty query returns all
            results = []
            for id_str in ids:
                record = await self.get(collection, id_str)
                if record:
                    results.append(record)
            return results

        # Filter by query
        results = []
        for id_str in ids:
            record = await self.get(collection, id_str)
            if record and self._matches_query(record, query):
                results.append(record)

        return results

    def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a record matches a query."""
        for key, expected_value in query.items():
            actual_value = self._get_nested_value(record, key)
            if actual_value != expected_value:
                return False
        return True

    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Any:
        """Get a nested value using dot notation."""
        keys = key.split(".")
        current = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()


# Factory function
def create_redis_db(**kwargs) -> RedisDatabase:
    """Factory function for creating RedisDatabase instances."""
    host = kwargs.get("host", "localhost")
    port = kwargs.get("port", 6379)
    db = kwargs.get("db", 0)
    return RedisDatabase(host=host, port=port, db=db)


# Register the database type
register_database_type("redis", create_redis_db)


# Example usage
class User(Object):
    email: str = ""
    name: str = ""


async def main():
    """Demonstrate custom Redis database usage."""

    # Create Redis database using factory
    redis_db = create_database(
        "redis",
        host="localhost",
        port=6379,
        db=0
    )

    # Use with GraphContext
    ctx = GraphContext(database=redis_db)
    set_default_context(ctx)

    # Create and save entities
    user = await User.create(email="test@example.com", name="Test User")
    print(f"Created user: {user.email}")

    # Retrieve entity
    retrieved = await User.get(user.id)
    if retrieved:
        print(f"Retrieved user: {retrieved.email}")

    # Use with multi-database management
    from jvspatial.db import get_database_manager
    manager = get_database_manager()
    manager.register_database("redis_app", redis_db)

    print("✅ Custom Redis database working correctly!")

    # Cleanup
    if hasattr(redis_db, "close"):
        await redis_db.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Best Practices

### 1. **Error Handling**

Always raise `DatabaseError` (or its subclasses) for database-related errors:

```python
from jvspatial.db import DatabaseError

async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # Your database operation
        pass
    except YourDatabaseException as e:
        raise DatabaseError(f"Database save error: {e}") from e
```

### 2. **ID Management**

Ensure records always have an `id` field. If your database generates IDs, map them to the `id` field:

```python
async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if "id" not in data:
        # Generate ID or let database generate it
        data["id"] = str(uuid.uuid4())

    # If your database uses a different ID field (e.g., _id), map it
    if "_id" in data and "id" not in data:
        data["id"] = data["_id"]

    # Save to database
    # ...

    return data
```

### 3. **Connection Management**

Handle connection lifecycle properly:

```python
class MyDatabase(Database):
    def __init__(self, **kwargs):
        self._client = None
        self._connected = False

    async def _ensure_connected(self):
        """Lazy connection initialization."""
        if not self._connected:
            # Initialize connection
            self._client = YourClient(...)
            self._connected = True

    async def close(self):
        """Clean up connections."""
        if self._client:
            await self._client.close()
            self._connected = False
```

### 4. **Query Implementation**

Implement efficient querying. For simple cases, in-memory filtering is fine, but for large datasets, use database-native queries:

```python
async def find(self, collection: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
    # For simple queries, use database-native filtering
    if len(query) == 1 and "id" in query:
        # Optimize single ID lookup
        record = await self.get(collection, query["id"])
        return [record] if record else []

    # For complex queries, use database query language
    # results = await self._client.query(collection, query)

    # Fallback to in-memory filtering
    all_records = await self._get_all(collection)
    return [r for r in all_records if self._matches_query(r, query)]
```

### 5. **Thread Safety**

Ensure your implementation is thread-safe if used in multi-threaded environments:

```python
import asyncio

class MyDatabase(Database):
    def __init__(self):
        self._lock = asyncio.Lock()

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            # Thread-safe operation
            pass
```

---

## Advanced Topics

### Custom Database with Multi-Database Support

Your custom database works seamlessly with jvspatial's multi-database management:

```python
from jvspatial.db import (
    create_database,
    get_database_manager,
    register_database_type
)

# Register custom database
register_database_type("my_custom", create_my_custom_db)

# Create and register multiple instances
db1 = create_database("my_custom", config="config1", register=True, name="db1")
db2 = create_database("my_custom", config="config2", register=True, name="db2")

# Switch between them
manager = get_database_manager()
manager.set_current_database("db1")
# ... use db1 ...
manager.set_current_database("db2")
# ... use db2 ...
```

### Integration with Server

Your custom database can be used as the prime database for Server:

```python
from jvspatial import Server
from jvspatial.db import create_database, register_database_type

# Register custom database
register_database_type("my_custom", create_my_custom_db)

# Create server with custom database
# Note: Server uses environment variables or direct database instance
custom_db = create_database("my_custom", connection_string="...")

# Set as prime database
from jvspatial.db import get_database_manager
manager = get_database_manager()
manager._prime_database = custom_db
manager._databases["prime"] = custom_db

# Create server (will use prime database)
server = Server()
```

### Testing Custom Databases

Test your custom database implementation:

```python
import pytest
from jvspatial.db import Database
from jvspatial.core.context import GraphContext
from jvspatial import Object

class TestObject(Object):
    name: str = ""

async def test_custom_database():
    """Test custom database implementation."""
    db = MyCustomDatabase(...)
    ctx = GraphContext(database=db)

    # Test save
    obj = TestObject(name="test")
    await ctx.save(obj)

    # Test get
    retrieved = await ctx.get(TestObject, obj.id)
    assert retrieved is not None
    assert retrieved.name == "test"

    # Test find
    results = await TestObject.find({"name": "test"})
    assert len(results) == 1

    # Test delete
    await ctx.delete(TestObject, obj.id)
    retrieved = await ctx.get(TestObject, obj.id)
    assert retrieved is None
```

---

## Summary

Implementing a custom database for jvspatial is straightforward:

1. **Subclass `Database`** and implement four abstract methods
2. **Handle collections** (`node`, `edge`, `object`, `walker`)
3. **Support simple queries** (dictionary-based matching)
4. **Register your database** with `register_database_type()`
5. **Use it seamlessly** with `create_database()` and all jvspatial features

The architecture is designed for **seamless extension** - your custom database will work with:
- GraphContext and entity operations
- Multi-database management
- Server integration
- All jvspatial features

For more examples, see `examples/database/custom_database_example.py`.

