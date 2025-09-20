# Database Architecture

This document describes the database architecture of jvspatial, which provides a flexible and extensible system for asynchronous graph-based persistence.

## Overview

The jvspatial database layer is designed with the following principles:

- **Generic Interface**: Abstract base class ensures all implementations follow the same contract
- **Extensibility**: Easy registration of custom database implementations
- **Async First**: All operations are asynchronous for high performance
- **Graph Optimized**: Specifically designed for efficient node and edge persistence
- **Error Resilient**: Comprehensive error handling and graceful degradation

## Architecture Components

### 1. Database Abstract Base Class (`database.py`)

The `Database` class defines the contract all database implementations must follow:

```python
class Database(ABC):
    @abstractmethod
    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database."""

    @abstractmethod
    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""

    @abstractmethod
    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""

    @abstractmethod
    async def find(self, collection: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find records matching a query."""

    @abstractmethod
    async def cleanup_orphans(self) -> None:
        """Clean up orphaned edges with invalid node references."""
```

### 2. Database Factory (`factory.py`)

The factory provides:

- **Automatic Discovery**: Detects available database implementations
- **Dynamic Registration**: Runtime registration of custom databases
- **Configuration Management**: Environment-based and parameter-based configuration
- **Error Handling**: Clear error messages for missing dependencies or invalid configurations

```python
# Get a database instance
db = get_database("json", base_path="./my_data")

# Register custom implementation
register_database("redis", RedisDatabase)

# List available types
available = list_available_databases()
```

### 3. Built-in Implementations

#### JsonDB (`jsondb.py`)

File-based JSON storage with:
- **Thread Safety**: AsyncIO locks for concurrent access
- **Robust Error Handling**: Graceful handling of file system errors
- **Query Support**: Basic query operations with dot notation
- **Orphan Cleanup**: Automatic cleanup of invalid edge references
- **Validation**: Input validation for collection names and document IDs

#### MongoDB (`mongodb.py`)

MongoDB integration featuring:
- **Connection Pooling**: Efficient connection management
- **Versioning Support**: Optimistic concurrency control
- **Index Management**: Automatic index creation for performance
- **Performance Monitoring**: Integration with performance tracking
- **Error Recovery**: Robust error handling with automatic retries

## Integration with Graph Context

The database layer integrates seamlessly with the `GraphContext`:

```python
# Create context with specific database
db = get_database("mongodb", uri="mongodb://localhost:27017")
context = GraphContext(database=db)

# All operations use the configured database
node = await context.create_node(City, name="New York")
retrieved = await context.get_node(City, node.id)
```

## Extending with Custom Databases

Creating a custom database implementation is straightforward:

### 1. Implement the Database Interface

```python
class RedisDatabase(Database):
    def __init__(self, redis_url: str = "redis://localhost:6379", **kwargs):
        self.redis_url = redis_url
        # Initialize Redis connection

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        # Implement Redis save logic
        pass

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        # Implement Redis get logic
        pass

    # ... implement other required methods
```

### 2. Register the Implementation

```python
from jvspatial.db import register_database

# Register for use with factory
register_database("redis", RedisDatabase)

# Now available through factory
db = get_database("redis", redis_url="redis://localhost:6379")
```

### 3. Use with GraphContext

```python
context = GraphContext(database=db)
# All graph operations now use Redis for persistence
```

## Data Model

### Collections

The database layer organizes data into collections:
- `node`: Graph nodes (cities, locations, entities)
- `edge`: Graph edges (connections between nodes)
- `walker`: Walker/traverser state
- `object`: Generic objects

### Document Structure

All documents follow a consistent structure:

```json
{
  "id": "unique_identifier",
  "name": "ClassName",
  "context": {
    "field1": "value1",
    "field2": "value2",
    "_data": {
      "custom_data": "goes_here"
    }
  },
  "_version": 1
}
```

For edges, additional fields are included:

```json
{
  "id": "edge_id",
  "name": "EdgeClassName",
  "source": "source_node_id",
  "target": "target_node_id",
  "direction": "both|in|out",
  "context": { ... }
}
```

## Performance Considerations

### JsonDB
- **File System**: Performance depends on underlying file system
- **Concurrency**: Single asyncio lock may limit high-concurrency scenarios
- **Memory Usage**: Entire documents loaded into memory
- **Best For**: Development, testing, small to medium datasets

### MongoDB
- **Indexing**: Automatic indexes on `id` fields for fast lookups
- **Connection Pooling**: Efficient connection reuse
- **Sharding**: Supports MongoDB's horizontal scaling features
- **Best For**: Production environments, large datasets, high concurrency

## Error Handling

The database layer implements comprehensive error handling:

### JsonDB Errors
- `RuntimeError`: File system access issues
- `ValueError`: Invalid collection names or document IDs
- `KeyError`: Missing required document fields

### MongoDB Errors
- `VersionConflictError`: Optimistic concurrency conflicts
- `RuntimeError`: Connection or operation failures
- `ValueError`: Invalid collection names

### Recovery Strategies
- **Graceful Degradation**: Operations return None/empty lists on errors
- **Automatic Retry**: Built into connection management
- **Orphan Cleanup**: Automatic cleanup of invalid references

## Configuration

### Environment Variables

- `JVSPATIAL_DB_TYPE`: Default database type ("json" or "mongodb")
- `JVSPATIAL_JSONDB_PATH`: Default path for JSON database files
- `JVSPATIAL_MONGODB_URI`: MongoDB connection string
- `JVSPATIAL_MONGODB_DB_NAME`: MongoDB database name

### Programmatic Configuration

```python
# Configure via factory
json_db = get_database(
    db_type="json",
    base_path="/custom/path"
)

mongo_db = get_database(
    db_type="mongodb",
    uri="mongodb://localhost:27017",
    db_name="custom_db",
    maxPoolSize=20
)
```

## Testing and Development

### Mock Database
For testing, use the provided memory database:

```python
from jvspatial.db import register_database, get_database

# Register memory database for tests
register_database("memory", MemoryDatabase)
db = get_database("memory")
```

### Test Utilities
The integration tests provide examples of:
- Database operation testing
- Error condition simulation
- Performance benchmarking
- Migration testing

## Best Practices

1. **Always use the factory**: Don't instantiate database classes directly
2. **Handle exceptions**: Wrap database operations in try/catch blocks
3. **Use contexts**: Leverage GraphContext for consistent database access
4. **Monitor performance**: Enable performance monitoring in production
5. **Regular cleanup**: Run `cleanup_orphans()` periodically
6. **Validate data**: Ensure all documents have required fields
7. **Environment configuration**: Use environment variables for deployment flexibility

## Migration and Versioning

When upgrading database schemas:

1. **Backup data**: Always backup before schema changes
2. **Version compatibility**: Handle both old and new document formats
3. **Gradual migration**: Migrate data incrementally
4. **Test thoroughly**: Test with real data before production deployment

This architecture provides a solid foundation for scalable, maintainable graph data persistence while remaining flexible enough to adapt to changing requirements.