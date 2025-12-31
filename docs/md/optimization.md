# Performance Optimization Guide

## Overview

This guide covers performance optimization techniques for jvspatial applications, including database strategies, caching, and walker optimizations.

## Database Performance

### Implementation Comparison

| Feature              | JSONDB Implementation      | MongoDB Implementation     |
|---------------------|----------------------------|----------------------------|
| Version Storage     | `_version` field in docs   | Atomic `findOneAndUpdate` |
| Conflict Detection  | Pre-update version check   | Built-in atomic operations|
| Performance (10k ops)| 2.1s ±0.3s               | 1.4s ±0.2s                |
| Best For           | Single-node deployments    | Distributed systems       |
| Migration Strategy | Batch version field adds   | Schema versioning         |

### Query Optimization

#### Use `count()` Instead of `len(find())`

For counting records, always use the `count()` method which performs database-level counting without loading records into memory:

```python
# Bad: Loads all records into memory just to count them
active_users = await User.find({"context.active": True})
count = len(active_users)  # Inefficient - loads all data

# Good: Database-level counting
count = await User.count({"context.active": True})  # Efficient - no data loading
```

#### Use `find_one()` Instead of `find(...)[0]`

When you only need a single record, use `find_one()` which is optimized for single-record retrieval:

```python
# Bad: Fetches all matching records, then takes first
users = await User.find({"context.email": "alice@example.com"})
user = users[0] if users else None  # Inefficient

# Good: Database-optimized single record retrieval
user = await User.find_one({"context.email": "alice@example.com"})  # Efficient
```

#### Use `node()` Instead of `nodes()[0]`

For graph traversal when you expect a single connected node, use `node()` which directly returns a single node:

```python
# Bad: Fetches all connected nodes, then takes first
connected_nodes = await current_node.nodes(node=User, direction="out")
user = connected_nodes[0] if connected_nodes else None  # Inefficient

# Good: Direct single-node retrieval
user = await current_node.node(node=User, direction="out")  # Efficient
```

#### Bulk Query Optimization

```python
# Bad: Multiple separate queries
for user_id in user_ids:
    user = await User.get(user_id)  # N queries

# Good: Single bulk query
users = await User.get_many(user_ids)  # 1 query
```

### Batch Processing

```python
# Efficient batch updates
class BatchProcessor(Walker):
    batch_size = 100
    current_batch = []

    async def process_batch(self):
        if len(self.current_batch) >= self.batch_size:
            await self.db.bulk_save(self.current_batch)
            self.current_batch = []

    @on_visit(Node)
    async def process_node(self, here: Node):
        self.current_batch.append(here)
        await self.process_batch()
```

## Caching Strategies

### Multi-Layer Caching

```python
from jvspatial.cache import Cache

# Configure multi-layer cache
cache = Cache([
    MemoryCache(max_size=1000),  # Fast, in-memory
    RedisCache(url="redis://localhost:6379")  # Distributed
])

class CachedWalker(Walker):
    async def visit_node(self, node):
        cache_key = f"analysis:{node.id}"

        # Check cache first
        if result := await cache.get(cache_key):
            return result

        # Perform analysis
        result = await self.analyze(node)

        # Cache result
        await cache.set(
            cache_key,
            result,
            expire_in=3600
        )

        return result
```

### Query Result Caching

```python
from jvspatial.cache import cached_query

class CachedRepository:
    @cached_query(ttl=300)  # Cache for 5 minutes
    async def get_active_users(self):
        return await User.find({"active": True})
```

## Walker Optimization

### Parallel Processing

```python
from jvspatial.walkers import ParallelWalker

class FastWalker(ParallelWalker):
    max_workers = 4

    async def process_node(self, node):
        # Nodes processed in parallel
        result = await self.heavy_computation(node)
        await self.store_result(result)
```

### Memory Management

```python
class MemoryEfficientWalker(Walker):
    max_results = 1000

    async def visit_node(self, node):
        # Process in chunks to manage memory
        chunk = await self.get_chunk(node)

        for item in chunk:
            # Process each item
            result = await self.process_item(item)

            # Emit results immediately
            await self.emit_result(result)

            # Clear processed data
            del item
```

## Advanced Optimizations

### Declarative Database Indexing

jvspatial supports declarative indexing using field annotations. Indexes are automatically created on first use:

#### Single-Field Indexes

```python
from jvspatial.core.annotations import attribute
from jvspatial.core.entities import Object

class User(Object):
    # Indexed field - automatically creates database index
    user_id: str = attribute(indexed=True, description="User identifier")

    # Unique indexed field
    email: str = attribute(indexed=True, index_unique=True, description="Email address")

    # Indexed nested field (stored in context)
    status: str = attribute(indexed=True, default="active")
```

#### Compound Indexes

```python
from jvspatial.core.annotations import attribute, compound_index

@compound_index([("user_id", 1), ("status", 1)])
class User(Object):
    user_id: str = attribute(indexed=True)
    status: str = attribute(indexed=True)
    email: str = ""
```

#### How It Works

1. **Automatic Creation**: Indexes are created automatically when entities are first saved
2. **Database-Specific**: Each database backend implements indexing optimally:
   - **MongoDB**: Uses native `create_index()` with proper options
   - **SQLite**: Creates JSON path indexes using `json_extract()`
   - **DynamoDB**: Creates Global Secondary Indexes (GSI) transparently
   - **JSON**: No-op (indexing not applicable for file-based storage)
3. **Query Optimization**: Queries on indexed fields automatically use indexes for better performance

#### Index Usage Examples

```python
# These queries will use indexes automatically
active_users = await User.find({"context.user_id": "123"})  # Uses user_id index
user = await User.find_one({"context.email": "alice@example.com"})  # Uses email index
filtered = await User.find({"context.user_id": "123", "context.status": "active"})  # Uses compound index
```

### Transparent DynamoDB Indexing

DynamoDB implementation automatically:
- Extracts indexed fields from JSON data
- Stores them as top-level attributes for GSI support
- Creates Global Secondary Indexes (GSI) when `create_index()` is called
- Optimizes queries to use GSIs instead of table scans

This is completely transparent - no code changes needed, just use `indexed=True` annotations.

### Selective Field Loading

```python
# Load only needed fields
users = await User.find(
    {"active": True},
    projection=["id", "name", "email"]
)

# Efficient counting without loading records
active_count = await User.count({"active": True})  # Much faster than len(await User.find(...))
```

### Connection Pooling

```python
from jvspatial.db import configure_pool

# Configure database connection pool
configure_pool(
    min_size=5,
    max_size=20,
    max_idle_time=30
)
```

## Best Practices

1. **Use `count()` instead of `len(find())`** - Database-level counting is much more efficient
2. **Use `find_one()` instead of `find(...)[0]`** - Optimized for single-record retrieval
3. **Use `node()` instead of `nodes()[0]`** - Direct single-node graph traversal
4. Use appropriate batch sizes for your data
5. Implement caching for frequently accessed data
6. Choose the right database implementation
7. **Index frequently queried fields** - Use `indexed=True` on fields used in queries
8. Monitor and optimize database queries
9. Use parallel processing when appropriate
10. Manage memory usage in large operations
11. Use connection pooling
12. Profile your application regularly
13. Implement monitoring and alerting

## See Also

- [Database Configuration](configuration.md)
- [Caching System](caching.md)
- [Walker Patterns](walker-patterns.md)
- [Monitoring Guide](monitoring.md)