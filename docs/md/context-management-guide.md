# Context Management Guide

This guide covers context management in jvspatial, focusing on `GraphContext` for database management and dependency injection.

**Note**: For comprehensive documentation on GraphContext, see [Graph Context](graph-context.md).

## Quick Reference

`GraphContext` is jvspatial's centralized database management system. It provides:

- **Clean Architecture**: No scattered database connections
- **Dependency Injection**: Database instances are injected
- **Testing Isolation**: Easy isolated test environments
- **Configuration Flexibility**: Switch backends without changing entity code

## Usage Patterns

### Automatic GraphContext (Recommended)

For most applications, jvspatial automatically manages GraphContext:

```python
from jvspatial.core.entities import Node

class Person(Node):
    name: str

# Uses default JSON database automatically
person = await Person.create(name="Alice")
```

### Explicit GraphContext Configuration

For applications requiring specific database configuration:

```python
from jvspatial.core.context import GraphContext
from jvspatial.db import create_database

# Create custom database
db = create_database(
    db_type="json",
    base_path="./my_data"
)

# Create GraphContext
ctx = GraphContext(database=db)

# Create entities through context
person = await ctx.create_node(Person, name="Alice")
```

## Key Concepts

- **Default Context**: Automatically created when using entity methods like `Node.create()`
- **Explicit Context**: Created explicitly for fine-grained control
- **Context Isolation**: Each context manages its own database connection

## Integration with Server

When using the `Server` class, GraphContext is automatically configured:

```python
from jvspatial.api import Server

server = Server(
    title="My API",
    db_type="json",
    db_path="./jvdb"
)

# GraphContext is automatically available to all entities
# No explicit context setup needed
```

## Multi-Database Support

jvspatial supports managing multiple databases with a prime database for core persistence operations. See the [Multi-Database Example](../../examples/database/multi_database_example.py) for a complete demonstration.

```python
from jvspatial.db import create_database, switch_database, unregister_database

# Create and register additional database
app_db = create_database("json", base_path="./app_data", register=True, name="app")

# Switch between databases
switch_database("app")  # For application data
switch_database("prime")  # Back to prime (for auth/sessions)

# Remove a database
unregister_database("app")
```

## See Also

- [Graph Context](graph-context.md) - Complete GraphContext documentation including multi-database support
- [Multi-Database Example](../../examples/database/multi_database_example.py) - Complete multi-database demonstration
- [Entity Reference](entity-reference.md) - Entity API reference
- [Server API](server-api.md) - Server configuration

