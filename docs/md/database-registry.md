# Database Registry System

The jvspatial library uses a flexible, registry-based database factory system that allows developers to easily extend the library with custom database implementations while maintaining clean separation of concerns.

## Overview

The database registry system provides:

- **Flexible Registration**: Easy registration of custom database implementations
- **Dynamic Configuration**: Custom configurator functions for database initialization
- **Default Management**: Configurable default database selection
- **Environment Support**: Environment variable overrides
- **Runtime Management**: Register and unregister databases at runtime

## Built-in Database Types

jvspatial comes with two built-in database implementations:

### JSON Database (`json`)
- **Type**: `json`
- **Class**: `JsonDB`
- **Default**: Yes (when no other default is set)
- **Configuration**:
  - `base_path`: Directory for JSON files (default: `"jvdb"`)
  - Environment variable: `JVSPATIAL_JSONDB_PATH`

```python
from jvspatial.db import get_database

# Use default path
db = get_database("json")

# Use custom path
db = get_database("json", base_path="/path/to/data")
```

### MongoDB (`mongodb`)
- **Type**: `mongodb`
- **Class**: `MongoDB`
- **Default**: No (automatically registered if motor/pymongo available)
- **Configuration**:
  - `uri`: MongoDB connection URI
  - `db_name`: Database name
  - Environment variables: `JVSPATIAL_MONGODB_URI`, `JVSPATIAL_MONGODB_DB_NAME`
  - Additional parameters passed to AsyncIOMotorClient

```python
from jvspatial.db import get_database

# Use environment variables or defaults
db = get_database("mongodb")

# Use custom configuration
db = get_database("mongodb",
                 uri="mongodb://localhost:27017",
                 db_name="my_app_db")
```

## Registry Functions

### `register_database(name, database_class, configurator=None, set_as_default=False)`

Register a new database implementation.

**Parameters:**
- `name`: Unique name for the database type
- `database_class`: Class that inherits from `Database`
- `configurator`: Optional function to configure the database with kwargs
- `set_as_default`: Whether to set this as the default database

**Example:**
```python
from jvspatial.db import register_database, Database

class MyDatabase(Database):
    def __init__(self, host: str = "localhost", port: int = 5432):
        self.host = host
        self.port = port

    # ... implement abstract methods ...

def my_configurator(kwargs):
    host = kwargs.get("host", "localhost")
    port = kwargs.get("port", 5432)
    return MyDatabase(host, port)

register_database("mydb", MyDatabase, my_configurator)
```

### `unregister_database(name)`

Remove a database implementation from the registry.

**Parameters:**
- `name`: Database type name to unregister

**Example:**
```python
from jvspatial.db import unregister_database

unregister_database("mydb")
```

### `set_default_database(name)`

Set the default database type.

**Parameters:**
- `name`: Database type name to use as default

**Example:**
```python
from jvspatial.db import set_default_database

set_default_database("mongodb")
```

### `get_default_database_type()`

Get the current default database type.

**Returns:** Default database type name

**Example:**
```python
from jvspatial.db import get_default_database_type

default_type = get_default_database_type()
print(f"Default database: {default_type}")
```

### `list_available_databases()`

Get all available database types.

**Returns:** Dictionary mapping database type names to their classes

**Example:**
```python
from jvspatial.db import list_available_databases

available = list_available_databases()
print(f"Available databases: {list(available.keys())}")
```

### `get_database(db_type=None, **kwargs)`

Create a database instance.

**Parameters:**
- `db_type`: Database type name (uses default if None)
- `**kwargs`: Database-specific configuration

**Returns:** Database instance

**Environment Override:**
The `JVSPATIAL_DB_TYPE` environment variable can override the default database type.

**Example:**
```python
from jvspatial.db import get_database

# Use default database
db = get_database()

# Use specific database
db = get_database("mongodb", uri="mongodb://localhost:27017")

# Environment variable override
import os
os.environ["JVSPATIAL_DB_TYPE"] = "mongodb"
db = get_database()  # Uses MongoDB
```

## Creating Custom Database Implementations

### Step 1: Create Database Class

Your database class must inherit from `Database` and implement all abstract methods:

```python
from jvspatial.db import Database
from typing import Any, Dict, List, Optional

class CustomDatabase(Database):
    def __init__(self, connection_string: str, timeout: int = 30):
        self.connection_string = connection_string
        self.timeout = timeout
        # Initialize your database connection

    async def clean(self) -> None:
        """Clean up orphaned edges with invalid node references."""
        # Implementation specific to your database
        pass

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save document to database."""
        # Implementation specific to your database
        pass

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        # Implementation specific to your database
        pass

    async def delete(self, collection: str, id: str) -> None:
        """Delete document by ID."""
        # Implementation specific to your database
        pass

    async def find(self, collection: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find documents matching query."""
        # Implementation specific to your database
        pass
```

### Step 2: Create Configurator Function

The configurator function handles database initialization with parameters:

```python
def custom_configurator(kwargs: Dict[str, Any]) -> CustomDatabase:
    """Configure CustomDatabase with parameters."""
    connection_string = kwargs.get("connection_string", "default://localhost")
    timeout = kwargs.get("timeout", 30)

    # Handle environment variables
    import os
    if "connection_string" not in kwargs:
        connection_string = os.getenv("CUSTOM_DB_CONNECTION", connection_string)

    return CustomDatabase(connection_string, timeout)
```

### Step 3: Register Database

Register your database implementation:

```python
from jvspatial.db import register_database

register_database("custom", CustomDatabase, custom_configurator)

# Optionally set as default
# register_database("custom", CustomDatabase, custom_configurator, set_as_default=True)
```

### Step 4: Use Your Database

Now you can use your database throughout jvspatial:

```python
from jvspatial.db import get_database
from jvspatial.core import GraphContext

# Create database instance
db = get_database("custom", connection_string="custom://myserver:5432", timeout=60)

# Use with GraphContext
ctx = GraphContext(database=db)

# Use as default
from jvspatial.db import set_default_database
set_default_database("custom")

# Now get_database() will return your custom database by default
default_db = get_database()
```

## Advanced Patterns

### Conditional Registration

Register databases based on available dependencies:

```python
# Register PostgreSQL only if asyncpg is available
try:
    import asyncpg
    register_database("postgresql", PostgreSQLDatabase, postgres_configurator)
except ImportError:
    pass  # PostgreSQL not available
```

### Multiple Instances

Create multiple instances of the same database type:

```python
# Development database
dev_db = get_database("mongodb", db_name="myapp_dev")

# Test database
test_db = get_database("mongodb", db_name="myapp_test")

# Production database
prod_db = get_database("mongodb", db_name="myapp_prod")
```

### Environment-Based Configuration

Configure databases based on environment:

```python
import os

def environment_aware_configurator(kwargs):
    env = os.getenv("APP_ENV", "development")

    if env == "production":
        return ProductionDatabase(**kwargs)
    elif env == "test":
        return TestDatabase(**kwargs)
    else:
        return DevelopmentDatabase(**kwargs)

register_database("smart", BaseDatabase, environment_aware_configurator)
```

## Best Practices

### 1. Use Descriptive Names
Choose clear, descriptive names for your database types:

```python
# Good
register_database("redis_cache", RedisCacheDatabase, redis_configurator)
register_database("postgres_main", PostgreSQLDatabase, postgres_configurator)

# Avoid
register_database("db1", SomeDatabase, some_configurator)
register_database("x", AnotherDatabase, another_configurator)
```

### 2. Handle Environment Variables

Support environment variable configuration in your configurators:

```python
def my_configurator(kwargs):
    # Allow override via environment variables
    host = kwargs.get("host") or os.getenv("MYDB_HOST", "localhost")
    port = kwargs.get("port") or int(os.getenv("MYDB_PORT", "5432"))
    return MyDatabase(host, port)
```

### 3. Validate Configuration

Validate parameters in your configurator:

```python
def validated_configurator(kwargs):
    host = kwargs.get("host", "localhost")
    port = kwargs.get("port", 5432)

    if not isinstance(port, int) or port <= 0:
        raise ValueError(f"Invalid port: {port}")

    return MyDatabase(host, port)
```

### 4. Provide Defaults

Always provide sensible defaults in your configurators:

```python
def robust_configurator(kwargs):
    # Provide defaults for all parameters
    config = {
        "host": "localhost",
        "port": 5432,
        "username": "user",
        "password": "",
        "database": "myapp",
        **kwargs  # Override with user-provided values
    }

    return MyDatabase(**config)
```

## Migration Guide

If you have existing code using the old explicit database selection, here's how to migrate:

### Old Pattern (Deprecated)
```python
# Old explicit database selection
from jvspatial.db.factory import get_database

if db_type == "mongodb":
    db = MongoDB(**kwargs)
elif db_type == "json":
    db = JsonDB(kwargs.get("base_path", "jvdb"))
```

### New Pattern (Registry-Based)
```python
# New registry-based approach
from jvspatial.db import get_database

# The registry handles all the configuration logic
db = get_database(db_type, **kwargs)
```

The new system is backward compatible for the built-in database types (`json` and `mongodb`), so existing code should continue to work without changes.