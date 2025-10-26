# Context Management Guide

**Date**: 2025-10-20
**Version**: 0.2.0

This guide explains the context management system in JVspatial, including the hierarchy, usage patterns, and best practices.

---

## 📋 **Context Hierarchy Overview**

| Context | Location | Purpose | Scope | Thread Safety |
|---------|----------|---------|-------|---------------|
| **GraphContext** | `core/context.py` | Graph operations & database | Per operation | ✅ Yes |
| **ServerContext** | `api/context.py` | Server management | Per thread/task | ✅ Yes |
| **GlobalContext** | `common/context.py` | Generic utilities | Global | ❌ No |

---

## 🌐 **GraphContext** - Core Graph Operations

**Location**: `jvspatial.core.context`
**Purpose**: Manage database dependencies for graph operations
**Thread Safety**: ✅ Yes (async context managers)

### Features

- **Database Management**: Automatic database connection handling
- **Performance Monitoring**: Track database operations and hook executions
- **Error Handling**: Comprehensive error tracking and reporting
- **Resource Cleanup**: Automatic cleanup of database connections

### Usage Examples

#### Basic Graph Operations
```python
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node, Walker

# Automatic context management
async with GraphContext() as ctx:
    # Create and save nodes
    node = Node(name="test_node")
    await node.save()

    # Context automatically handles database connections
    found_node = await Node.get("test_node")
    print(f"Found: {found_node}")

# Context automatically cleans up resources
```

#### Performance Monitoring
```python
from jvspatial.core.context import GraphContext

async with GraphContext() as ctx:
    # Perform operations
    node = Node(name="monitored_node")
    await node.save()

    # Access performance data
    monitor = ctx.performance_monitor
    print(f"DB operations: {len(monitor.db_operations)}")
    print(f"Hook executions: {len(monitor.hook_executions)}")
```

#### Error Handling
```python
from jvspatial.core.context import GraphContext

async with GraphContext() as ctx:
    try:
        # Operations that might fail
        node = Node(name="error_test")
        await node.save()
    except Exception as e:
        # Context tracks errors
        print(f"Errors: {len(ctx.performance_monitor.db_errors)}")
        raise
```

### Advanced Usage

#### Custom Database Configuration
```python
from jvspatial.core.context import GraphContext
from jvspatial.db.factory import get_database

# Use specific database
custom_db = get_database("mongodb://localhost:27017/custom")

async with GraphContext(database=custom_db) as ctx:
    # Operations use custom database
    node = Node(name="custom_db_node")
    await node.save()
```

#### Context Nesting
```python
from jvspatial.core.context import GraphContext

async with GraphContext() as outer_ctx:
    # Outer context
    node1 = Node(name="outer_node")
    await node1.save()

    async with GraphContext() as inner_ctx:
        # Inner context (nested)
        node2 = Node(name="inner_node")
        await node2.save()

    # Back to outer context
    node3 = Node(name="back_to_outer")
    await node3.save()
```

---

## 🚀 **ServerContext** - API Server Management

**Location**: `jvspatial.api.context`
**Purpose**: Thread-safe server instance management
**Thread Safety**: ✅ Yes (ContextVar-based)

### Features

- **Thread Safety**: Uses ContextVar for proper isolation
- **Async Safety**: Works correctly in async environments
- **Server Access**: Get/set current server instance
- **Context Isolation**: Each thread/task has its own server context

### Usage Examples

#### Basic Server Management
```python
from jvspatial.api.context import get_current_server, set_current_server
from jvspatial.api import Server

# Set current server
server = Server(config=ServerConfig(title="My API"))
set_current_server(server)

# Get current server
current = get_current_server()
print(f"Current server: {current.config.title}")
```

#### Context Manager Usage
```python
from jvspatial.api.context import ServerContext
from jvspatial.api import Server

# Using context manager
with ServerContext(server) as ctx:
    # Server is available in this context
    current = get_current_server()
    print(f"Server: {current.config.title}")

# Server context is automatically cleaned up
```

#### Thread-Safe Operations
```python
import asyncio
from jvspatial.api.context import set_current_server, get_current_server

async def worker(server_id: int):
    """Worker function with isolated server context."""
    server = Server(config=ServerConfig(title=f"Server {server_id}"))
    set_current_server(server)

    # Each worker has its own server context
    current = get_current_server()
    print(f"Worker {server_id}: {current.config.title}")

# Run multiple workers with isolated contexts
async def main():
    await asyncio.gather(
        worker(1),
        worker(2),
        worker(3)
    )
```

### Advanced Usage

#### Server Context Nesting
```python
from jvspatial.api.context import ServerContext, set_current_server

# Outer server context
outer_server = Server(config=ServerConfig(title="Outer Server"))
with ServerContext(outer_server):
    print(f"Outer: {get_current_server().config.title}")

    # Inner server context
    inner_server = Server(config=ServerConfig(title="Inner Server"))
    with ServerContext(inner_server):
        print(f"Inner: {get_current_server().config.title}")

    # Back to outer context
    print(f"Back to outer: {get_current_server().config.title}")
```

#### Testing with Server Context
```python
from jvspatial.api.context import ServerContext
from jvspatial.api import Server

def test_with_server():
    """Test function that needs server context."""
    server = get_current_server()
    assert server is not None
    return server.config.title

# Test with server context
test_server = Server(config=ServerConfig(title="Test Server"))
with ServerContext(test_server):
    result = test_with_server()
    assert result == "Test Server"
```

---

## 🌍 **GlobalContext** - Generic Utilities

**Location**: `jvspatial.common.context`
**Purpose**: Lightweight global context for dependency injection
**Thread Safety**: ❌ No (intentionally simple)

### Features

- **Dependency Injection**: Override dependencies for testing
- **Factory Pattern**: Create instances on demand
- **Testing Support**: Easy mocking and testing
- **Simple API**: Minimal overhead

### Usage Examples

#### Basic Global Context
```python
from jvspatial.common.context import GlobalContext

# Create a global context for a service
def create_database_service():
    return DatabaseService(connection_string="sqlite:///test.db")

db_context = GlobalContext(create_database_service, "database")

# Use the context
db_service = db_context.get()
print(f"Database: {db_service.connection_string}")
```

#### Testing with Overrides
```python
from jvspatial.common.context import GlobalContext

# Production context
def create_production_db():
    return DatabaseService(connection_string="postgresql://prod")

# Test context
def create_test_db():
    return DatabaseService(connection_string="sqlite://:memory:")

# Set up context
db_context = GlobalContext(create_production_db, "database")

# Test with override
with db_context.override(create_test_db()):
    db_service = db_context.get()
    assert "sqlite" in db_service.connection_string

# Back to production
db_service = db_context.get()
assert "postgresql" in db_service.connection_string
```

#### Multiple Contexts
```python
from jvspatial.common.context import GlobalContext

# Database context
db_context = GlobalContext(
    lambda: DatabaseService("sqlite:///app.db"),
    "database"
)

# Cache context
cache_context = GlobalContext(
    lambda: CacheService("redis://localhost:6379"),
    "cache"
)

# Use both contexts
db_service = db_context.get()
cache_service = cache_context.get()

print(f"DB: {db_service.connection_string}")
print(f"Cache: {cache_service.redis_url}")
```

---

## 🔄 **Context Interaction Patterns**

### 1. **GraphContext + ServerContext**
```python
from jvspatial.core.context import GraphContext
from jvspatial.api.context import ServerContext

# Use both contexts together
with ServerContext(server):
    async with GraphContext() as graph_ctx:
        # Both server and graph contexts are available
        current_server = get_current_server()
        node = Node(name="api_node")
        await node.save()
```

### 2. **GlobalContext + GraphContext**
```python
from jvspatial.common.context import GlobalContext
from jvspatial.core.context import GraphContext

# Set up global context
db_context = GlobalContext(create_database, "database")

# Use in graph operations
async with GraphContext() as ctx:
    # Graph context can use global context
    db_service = db_context.get()
    # Perform operations
```

### 3. **Nested Contexts**
```python
# Multiple levels of context
with ServerContext(outer_server):
    async with GraphContext() as graph_ctx:
        with ServerContext(inner_server):
            # All contexts available
            pass
```

---

## 📚 **Best Practices**

### 1. **Context Selection**

| Use Case | Recommended Context | Reason |
|----------|-------------------|--------|
| Graph operations | `GraphContext` | Database management, performance monitoring |
| API server management | `ServerContext` | Thread-safe server access |
| Dependency injection | `GlobalContext` | Testing, configuration |
| Testing | `GlobalContext.override()` | Easy mocking |

### 2. **Error Handling**
```python
# Always handle context errors
try:
    async with GraphContext() as ctx:
        # Operations
        pass
except Exception as e:
    # Handle errors appropriately
    logger.error(f"Graph operation failed: {e}")
    raise
```

### 3. **Resource Management**
```python
# Use context managers for automatic cleanup
async with GraphContext() as ctx:
    # Resources automatically cleaned up
    pass

# Don't forget to clean up manually if needed
ctx = GraphContext()
try:
    await ctx.__aenter__()
    # Operations
finally:
    await ctx.__aexit__(None, None, None)
```

### 4. **Testing Patterns**
```python
# Test with context overrides
def test_graph_operations():
    with GlobalContext.override(mock_database):
        async with GraphContext() as ctx:
            # Test operations
            pass
```

---

## 🚨 **Common Pitfalls**

### 1. **Context Leakage**
```python
# ❌ Wrong - context not properly closed
ctx = GraphContext()
await ctx.__aenter__()
# Forgot to call __aexit__()

# ✅ Correct - use context manager
async with GraphContext() as ctx:
    # Automatic cleanup
    pass
```

### 2. **Thread Safety Issues**
```python
# ❌ Wrong - using GlobalContext in multi-threaded code
global_context = GlobalContext(create_service, "service")
# Not thread-safe!

# ✅ Correct - use ServerContext for thread safety
with ServerContext(server):
    # Thread-safe
    pass
```

### 3. **Context Nesting Issues**
```python
# ❌ Wrong - confusing context nesting
async with GraphContext() as ctx1:
    async with GraphContext() as ctx2:
        # Which context is active?

# ✅ Correct - clear context hierarchy
async with GraphContext() as outer:
    # Outer context
    async with GraphContext() as inner:
        # Inner context (nested)
        pass
```

---

## 🔧 **Migration Guide**

### From v0.1 to v0.2

**Old patterns**:
```python
# v0.1 - Global server registry
from jvspatial.api import get_current_server
server = get_current_server()  # Global state
```

**New patterns**:
```python
# v0.2 - Context-based server management
from jvspatial.api.context import get_current_server, ServerContext
with ServerContext(server):
    current = get_current_server()  # Context-aware
```

**Changes**:
- Server management moved to context-based approach
- Thread-safe ContextVar implementation
- Better isolation between threads/tasks

---

## 📖 **Related Documentation**

- [API Documentation](api-architecture.md)
- [Graph Traversal Guide](graph-traversal.md)
- [Database Guide](mongodb-query-interface.md)
- [Testing Guide](troubleshooting.md)

---

**Last Updated**: 2025-10-20
**Version**: 0.2.0
**Maintainer**: JVspatial Team
