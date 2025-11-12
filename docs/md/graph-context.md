# GraphContext: Database Management & Dependency Injection

GraphContext is jvspatial's centralized database management system that provides clean dependency injection for all database operations. It uses a unified, testable, and maintainable approach to database management.

## Overview

GraphContext serves as the single source of truth for database operations in your jvspatial application. It manages database connections, handles entity lifecycle, and provides both automatic and explicit usage patterns.

### Key Benefits

- **Clean Architecture**: No scattered database connections across entity classes
- **Dependency Injection**: Database instances are injected rather than globally managed
- **Testing Isolation**: Easy to create isolated test environments with different databases
- **Configuration Flexibility**: Switch database backends without changing entity code
- **Convenient API**: Simple methods like `Node.create()`, `Edge.create()` for common operations
- **Explicit Control**: When needed, full programmatic control over database operations

## Usage Patterns

### 1. Automatic GraphContext (Recommended)

For most applications, jvspatial automatically manages GraphContext with sensible defaults:

```python
import asyncio
from jvspatial.core.entities import Node, Walker, on_visit

class Person(Node):
    name: str
    age: int = 0

class PersonWalker(Walker):
    @on_visit(Person)
    async def visit_person(self, here):
        print(f"Visiting {here.name} (age {here.age})")

async def main():
    # Uses default JSON database automatically
    person = await Person.create(name="Alice", age=30)

    walker = PersonWalker()
    result = await walker.spawn(person)

if __name__ == "__main__":
    asyncio.run(main())
```

**Default Configuration:**
- Database: JSON file-based storage (default)
- Location: `./jv_data/` directory
- Auto-creation: Enabled
- Alternative backends: set `JVSPATIAL_DB_TYPE` to `sqlite` (requires `aiosqlite`) or `mongodb` to switch backends. For SQLite, configure the database file with `JVSPATIAL_SQLITE_PATH` (defaults to `jvdb/sqlite/jvspatial.db`).

### 2. Explicit GraphContext Configuration

For applications requiring specific database configuration:

```python
import asyncio
from jvspatial.core.entities import Node, Edge
from jvspatial.core.context import GraphContext
from jvspatial.db import create_database

class Company(Node):
    name: str
    industry: str = ""

class Partnership(Edge):
    contract_date: str = ""
    value: float = 0.0

async def main():
    # Create custom database
    db = create_database(
        db_type="sqlite",
        db_path="./business_data/app.db"
    )

    # Create GraphContext
    ctx = GraphContext(database=db)

    # Create entities through context
    apple = await ctx.create_node(Company, name="Apple", industry="Technology")
    microsoft = await ctx.create_node(Company, name="Microsoft", industry="Technology")

    # Create relationship
    partnership = await ctx.create_edge(
        Partnership,
        source=apple,
        target=microsoft,
        contract_date="2023-01-15",
        value=1000000.0
    )

    # Standard API methods
    retrieved = await Company.get(apple.id)
    print(f"Company: {retrieved.name}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Multiple GraphContext Instances

For applications managing multiple databases or environments:

```python
import asyncio
from jvspatial.core.context import GraphContext
from jvspatial.db import create_database

async def main():
    # Production database
    prod_db = create_database(db_type="json", base_path="./prod_data")
    prod_ctx = GraphContext(database=prod_db)

    # Development database
    dev_db = create_database(db_type="json", base_path="./dev_data")
    dev_ctx = GraphContext(database=dev_db)

    # Create entities in different contexts
    prod_user = await prod_ctx.create_node(User, name="Production User")
    dev_user = await dev_ctx.create_node(User, name="Development User")

    # Each context manages its own entities
    print(f"Prod user: {prod_user.name}")
    print(f"Dev user: {dev_user.name}")

if __name__ == "__main__":
    asyncio.run(main())
```

## API Reference

### GraphContext Class

#### Constructor

```python
def __init__(self, database: Database) -> None
```

**Parameters:**
- `database`: Database instance from `jvspatial.db.create_database()`

#### Node Operations

##### `create_node`
```python
async def create_node(
    self,
    node_class: type[T],
    **kwargs
) -> T
```

Creates a new node instance and persists it to the database.

**Parameters:**
- `node_class`: The Node subclass to create
- `**kwargs`: Node attributes

**Returns:** The created node instance

**Example:**
```python
user = await ctx.create_node(User, name="Alice", email="alice@example.com")
```

##### `get_node`
```python
async def get_node(
    self,
    node_class: type[T],
    node_id: str
) -> T | None
```

Retrieves a node by ID and class.

**Parameters:**
- `node_class`: The Node subclass to retrieve
- `node_id`: The node's unique identifier

**Returns:** The node instance or None if not found

**Example:**
```python
user = await ctx.get_node(User, "user_123")
```

##### `save_node`
```python
async def save_node(self, node: Object) -> Object
```

Saves changes to an existing node.

**Parameters:**
- `node`: The node instance to save

**Returns:** The updated node instance

**Example:**
```python
user.name = "Updated Name"
await ctx.save_node(user)
```

##### `delete_node`
```python
async def delete_node(self, node: Object) -> bool
```

Deletes a node from the database.

**Parameters:**
- `node`: The node instance to delete

**Returns:** True if deletion was successful

**Example:**
```python
success = await ctx.delete_node(user)
```

#### Edge Operations

##### `create_edge`
```python
async def create_edge(
    self,
    edge_class: type[T],
    source: Object,
    target: Object,
    **kwargs
) -> T
```

Creates a new edge between two nodes.

**Parameters:**
- `edge_class`: The Edge subclass to create
- `source`: Source node for the edge
- `target`: Target node for the edge
- `**kwargs`: Edge attributes

**Returns:** The created edge instance

**Example:**
```python
friendship = await ctx.create_edge(
    Friendship,
    source=alice,
    target=bob,
    strength=0.9,
    since="2020-01"
)
```

##### `get_edge`
```python
async def get_edge(
    self,
    edge_class: type[T],
    edge_id: str
) -> T | None
```

Retrieves an edge by ID and class.

##### `save_edge`
```python
async def save_edge(self, edge: Object) -> Object
```

Saves changes to an existing edge.

##### `delete_edge`
```python
async def delete_edge(self, edge: Object) -> bool
```

Deletes an edge from the database.

### Graph Visualization

Export your graph structure in renderable formats:

```python
# Export as DOT format (Graphviz)
dot_graph = await context.export_graph(
    format="dot",
    output_file="graph.dot",
    rankdir="LR",
    node_shape="box"
)

# Export as Mermaid format
mermaid_graph = await context.export_graph(
    format="mermaid",
    output_file="graph.mermaid",
    direction="LR"
)
```

For detailed information, see [Graph Visualization](graph-visualization.md).

### Entity Integration

All jvspatial entities automatically integrate with GraphContext:

#### Node Methods

```python
# These methods work with both automatic and explicit GraphContext
await Node.create(**kwargs)           # Uses default or current context
await Node.get(node_id)               # Uses default or current context
await node.save()                     # Uses node's context
await node.destroy()                  # Uses node's context
```

#### Edge Methods

```python
# Edge methods similarly integrate with GraphContext
await Edge.create(source, target, **kwargs)
await Edge.get(edge_id)
await edge.save()
await edge.destroy()
```

## Database Configuration

### Supported Databases

#### JSON Database (Default)
```python
from jvspatial.db import create_database

db = create_database(
    db_type="json",
    base_path="./my_data"      # Directory for JSON files
)
```

#### MongoDB Database
```python
db = create_database(
    db_type="mongodb",
    connection_string="mongodb://localhost:27017",
    db_name="my_app"
)
```

#### Memory Database (Testing)
```python
# For testing - data is not persisted
db = create_database(
    db_type="json",
    base_path=":memory:"
)
```

### Database Factory Function

The `create_database()` function provides a unified interface:

```python
def create_database(
    db_type: str,
    base_path: str | None = None,
    connection_string: str | None = None,
    db_name: str | None = None,
    auto_create: bool = True
) -> Database
```

**Parameters:**
- `db_type`: "json" or "mongodb"
- `base_path`: Path for JSON database files
- `connection_string`: MongoDB connection string
- `database_name`: MongoDB database name
- `auto_create`: Whether to create database/directories automatically

## Testing with GraphContext

GraphContext makes testing much easier by providing database isolation:

### Basic Test Setup

```python
import pytest
from jvspatial.core.context import GraphContext
from jvspatial.db.factory import get_database

@pytest.fixture
async def test_context():
    """Create isolated test database"""
    db = get_database(db_type="json", base_path=":memory:")
    ctx = GraphContext(database=db)
    yield ctx
    # Automatic cleanup
```

### Test Example

```python
async def test_user_operations(test_context):
    # Create user
    user = await test_context.create_node(
        User,
        name="Test User",
        email="test@example.com"
    )

    assert user.name == "Test User"
    assert user.id is not None

    # Update user
    user.email = "updated@example.com"
    updated_user = await test_context.save_node(user)
    assert updated_user.email == "updated@example.com"

    # Retrieve user
    retrieved = await test_context.get_node(User, user.id)
    assert retrieved.email == "updated@example.com"

    # Delete user
    success = await test_context.delete_node(user)
    assert success

    # Verify deletion
    deleted_user = await test_context.get_node(User, user.id)
    assert deleted_user is None
```

### Integration Testing

```python
async def test_social_network(test_context):
    # Create users
    alice = await test_context.create_node(User, name="Alice")
    bob = await test_context.create_node(User, name="Bob")
    charlie = await test_context.create_node(User, name="Charlie")

    # Create friendships
    alice_bob = await test_context.create_edge(
        Friendship,
        source=alice,
        target=bob,
        strength=0.9
    )

    bob_charlie = await test_context.create_edge(
        Friendship,
        source=bob,
        target=charlie,
        strength=0.7
    )

    # Test graph traversal
    class FriendCounter(Walker):
        def __init__(self):
            super().__init__()
            self.count = 0

        @on_visit(User)
        async def count_friends(self, here):
            self.count += 1
            # Visit connected friends
            for edge in await here.edges_out:
                if isinstance(edge, Friendship):
                    await self.visit(edge.target)

    counter = FriendCounter()
    result = await counter.spawn(alice)

    assert counter.count == 3  # Alice + Bob + Charlie
```

## Using GraphContext

GraphContext provides clean, centralized database management:

All existing entity methods continue to work:
- `await Node.create(**kwargs)`
- `await Node.get(id)`
- `await node.save()`
- `await node.destroy()`
- `await Edge.create(source, target, **kwargs)`

The main difference is that database management is now centralized and configurable through GraphContext.

## Multi-Database Support

jvspatial supports managing multiple databases with a prime database for core persistence operations (authentication, session management). See the [Multi-Database Example](../../examples/database/multi_database_example.py) for a complete demonstration.

### Key Features

- **Prime Database**: Always used for authentication and session management
- **Multiple Databases**: Register and switch between application databases
- **Easy Switching**: Use `switch_database(name)` or `DatabaseManager.set_current_database(name)`
- **Database Removal**: Use `unregister_database(name)` to remove non-prime databases

### Quick Example

```python
from jvspatial.db import create_database, get_database_manager, switch_database, unregister_database

# Prime database is automatically created
manager = get_database_manager()
prime_db = manager.get_prime_database()  # For auth/sessions

# Create and register additional database
app_db = create_database("json", base_path="./app_data", register=True, name="app")

# Switch between databases
switch_database("app")  # For application data
switch_database("prime")  # Back to prime

# Remove a database
unregister_database("app")
```

## Best Practices

### 1. Choose the Right Pattern

- **Automatic GraphContext**: For simple applications with single database
- **Explicit GraphContext**: For applications needing database control
- **Multiple Contexts**: For multi-tenant or multi-environment applications
- **Multi-Database**: For applications needing separate databases for different data domains

### 2. Testing

```python
# Always use isolated test contexts
@pytest.fixture
async def test_context():
    db = get_database(db_type="json", base_path=":memory:")
    return GraphContext(database=db)
```

### 3. Configuration Management

```python
# Use configuration for database settings
import os
from jvspatial.core.context import GraphContext
from jvspatial.db import create_database

def get_app_context() -> GraphContext:
    db_type = os.getenv("JVSPATIAL_DB_TYPE", "json")
    base_path = os.getenv("JVSPATIAL_JSONDB_PATH", "./jvdb")

    db = create_database(db_type=db_type, base_path=base_path)
    return GraphContext(database=db)
```

### 4. Context Lifecycle

```python
# For web applications, consider context per request
from fastapi import Depends

async def get_graph_context() -> GraphContext:
    db = create_database("json", base_path="./api_data")
    return GraphContext(database=db)

@app.post("/users")
async def create_user(
    user_data: UserData,
    ctx: GraphContext = Depends(get_graph_context)
):
    user = await ctx.create_node(User, **user_data.dict())
    return user
```

### 5. Error Handling

```python
async def safe_create_user(ctx: GraphContext, **kwargs):
    try:
        user = await ctx.create_node(User, **kwargs)
        return user
    except DatabaseError as e:
        logger.error(f"Failed to create user: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Invalid user data: {e}")
        raise
```

## Troubleshooting

### Common Issues

#### 1. "No database configured" Error
```python
# Solution: Ensure GraphContext is properly configured
ctx = GraphContext(database=create_database("json", base_path="./data"))
```

#### 2. Entity Not Found
```python
# Check if entity was created with correct context
user = await ctx.get_node(User, user_id)
if user is None:
    # Entity doesn't exist or wrong context
```

#### 3. Test Database Pollution
```python
# Use isolated test contexts
@pytest.fixture
async def clean_context():
    db = create_database("json", base_path=":memory:")
    return GraphContext(database=db)
```

### Debug Mode

Enable debug logging to trace GraphContext operations:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("jvspatial.core.context")

# GraphContext operations will now be logged
```

## Performance Considerations

### Database Connection Pooling

GraphContext manages database connections efficiently:

```python
# Connection is reused across operations
ctx = GraphContext(database=db)

# Multiple operations use same connection
user1 = await ctx.create_node(User, name="Alice")
user2 = await ctx.create_node(User, name="Bob")
edge = await ctx.create_edge(Friendship, source=user1, target=user2)
```

### Batch Operations

For bulk operations, consider batching:

```python
async def create_users_batch(ctx: GraphContext, user_data_list):
    users = []
    for user_data in user_data_list:
        user = await ctx.create_node(User, **user_data)
        users.append(user)
    return users
```

### Caching

GraphContext supports caching at the database level:

```python
# Some databases support caching configuration
db = create_database(
    db_type="json",
    base_path="./data",
    cache_enabled=True  # If supported by database
)
```

## Summary

GraphContext provides a clean, testable, and maintainable approach to database management in jvspatial applications. It offers both automatic convenience for simple use cases and explicit control for complex scenarios.

Key takeaways:
- Use automatic GraphContext for simple applications
- Use explicit GraphContext for complex database requirements
- Always use isolated contexts for testing
- Existing entity APIs continue to work unchanged
- Database configuration is centralized and flexible

For more examples, see the [Examples Documentation](./examples.md).

## See Also

- [Entity Reference](entity-reference.md) - Complete API reference
- [Examples](examples.md) - Practical usage examples
- [Object Pagination Guide](pagination.md) - Efficient data handling
- [MongoDB-Style Query Interface](mongodb-query-interface.md) - Query capabilities
- [REST API Integration](rest-api.md) - Using GraphContext in APIs
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

---

**[← Back to README](../../README.md)** | **[Server API →](server-api.md)**
