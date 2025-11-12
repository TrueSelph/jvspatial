# Import Patterns Guide

**Version**: 0.0.1
**Date**: 2025-10-20

This guide documents recommended import patterns for the jvspatial library, ensuring consistency and maintainability across your codebase.

---

## 🎯 **Core Principles**

1. **Import from the highest level possible** - Use public API imports
2. **Avoid internal imports** - Don't import from private modules
3. **Be explicit** - Named imports over wildcard imports
4. **Group imports logically** - Standard → Third-party → Local

---

## 📦 **Top-Level Imports**

### **Core Entities (Recommended)**

```python
# ✅ Best: Import from main package
from jvspatial import Object, Node, Edge, Walker, Root

# ✅ Also good: Import from core
from jvspatial.core import Object, Node, Edge, Walker, Root

# ❌ Avoid: Import from specific files
from jvspatial.core.node import Node  # Too specific
```

### **Server & API**

```python
# ✅ Best: Import from main package
from jvspatial import Server, ServerConfig

# ✅ Also good: Import from api
from jvspatial.api import Server, ServerConfig

# ❌ Avoid: Import from server file
from jvspatial.api.server import Server  # Too specific
```

---

## 🎨 **Decorator Patterns**

### **Route Decorators**

```python
# ✅ Best: Import from api.decorators
from jvspatial.api.decorators import (
    endpoint,
    auth_endpoint,
    webhook_endpoint,
    admin_endpoint,
)

# ✅ Also good: Import from main api
from jvspatial.api import endpoint, auth_endpoint

# ❌ Avoid: Import from internal modules
from jvspatial.api.decorators.route import endpoint  # Too specific
```

### **Field Decorators**

```python
# ✅ Best: Import from api.decorators
from jvspatial.api.decorators import endpoint_field, EndpointFieldInfo

# ✅ Also good: For advanced use
from jvspatial.api.decorators.field import endpoint_field

# ❌ Avoid: Don't import from endpoints
from jvspatial.api.endpoints.decorators import endpoint_field  # Wrong module
```

### **Graph Decorators**

```python
# ✅ Best: Import from core
from jvspatial.core import on_visit, on_exit, attribute

# ✅ Also good: Import from specific modules
from jvspatial.core.decorators import on_visit, on_exit
from jvspatial.core.annotations import attribute

# ❌ Avoid: Import from main package (not re-exported)
from jvspatial import on_visit  # Not available at top level
```

---

## 💾 **Database Patterns**

### **Database Setup**

```python
# ✅ Best: Import factory function
from jvspatial.db import create_database

# ✅ For specific backends
from jvspatial.db import Database, JsonDatabase, MongoDBDatabase

# ❌ Avoid: Import base classes directly
from jvspatial.db.database import Database  # Only for subclassing
```

### **Example: Database Usage**

```python
from jvspatial.db import create_database

# Create database instance
db = create_database("json", base_path="./data")

# Or for MongoDB
db = create_database("mongodb", db_name="mydb", connection_string="mongodb://localhost:27017")
```

---

## ⚡ **Cache Patterns**

```python
# ✅ Best: Import factory function
from jvspatial.cache import get_cache_backend

# ✅ For specific backends
from jvspatial.cache import MemoryCache, RedisCache, LayeredCache

# Example usage
from jvspatial.cache import get_cache_backend

cache = get_cache_backend()  # Uses env config
await cache.set("key", "value", ttl=300)
```

---

## 📁 **Storage Patterns**

```python
# ✅ Best: Import from interfaces
from jvspatial.storage.interfaces import (
    FileStorageInterface,
    LocalFileInterface,
    S3FileInterface,
)

# ✅ For managers
from jvspatial.storage.managers import ProxyManager

# ✅ For models
from jvspatial.storage.models import FileMetadata

# ❌ Avoid: Import from base files
from jvspatial.storage.interfaces.base import FileStorageInterface  # Too specific
```

---

## 🛠️ **Utils Patterns**

### **Decorators**

```python
# ✅ Best: Import from utils
from jvspatial.utils import (
    memoize,
    retry,
    timeout,
    validate_args,
    log_calls,
)

# ✅ Also good: Import from decorators module
from jvspatial.utils.decorators import memoize, retry

# ✅ All imports should use the utils module
```

### **Type System**

```python
# ✅ Best: Import from utils
from jvspatial.utils import (
    # Type aliases
    NodeId,
    EdgeId,
    WalkerId,
    GraphData,
    APIResponse,

    # Type guards
    is_string,
    is_dict,
    is_list,

    # Converters
    to_string,
    to_dict,
    to_list,
)

# ✅ Also good: Import from types module
from jvspatial.utils.types import NodeId, is_dict, to_dict
```

### **Utilities**

```python
# ✅ Best: Import from utils
from jvspatial.utils import (
    PluginFactory,
    GlobalContext,
    PathValidator,
    serialize_datetime,
    deserialize_datetime,
)

# ✅ Also good: Import from specific modules
from jvspatial.utils.factory import PluginFactory
from jvspatial.utils.context import GlobalContext
from jvspatial.utils.serialization import serialize_datetime
```

---

## 🔗 **Context Patterns**

### **Graph Context**

```python
# ✅ Best: Import from core
from jvspatial.core import GraphContext

# Example usage
from jvspatial import GraphContext, Node

async with GraphContext() as ctx:
    node = await Node.get("some_id", ctx=ctx)
```

### **Server Context**

```python
# ✅ Best: Import from api
from jvspatial.api import ServerContext

# Example usage
from jvspatial.api import ServerContext, Server

async with ServerContext() as ctx:
    server = Server(context=ctx)
```

### **Global Context**

```python
# ✅ Best: Import from utils
from jvspatial.utils import GlobalContext

# Example usage
from jvspatial.utils import GlobalContext

db_context = GlobalContext(
    factory=lambda: create_database("json", base_path="./data"),
    name="database_context"
)

db = db_context.get()
```

---

## 📚 **Complete Example**

### **Building a Complete Application**

```python
"""Example application showing recommended import patterns."""

# Standard library
import asyncio
from typing import Optional

# Third-party (if any)
# import httpx

# JVspatial - Core
from jvspatial import (
    Node,
    Edge,
    Walker,
    Root,
    GraphContext,
)

# JVspatial - API
from jvspatial.api import (
    Server,
    ServerConfig,
    endpoint,
    auth_endpoint,
)

# JVspatial - Database
from jvspatial.db import (
    create_database,
    Database,
)

# JVspatial - Cache
from jvspatial.cache import get_cache_backend

# JVspatial - Utils
from jvspatial.utils import (
    memoize,
    retry,
    NodeId,
    is_dict,
)

# Your custom nodes
class User(Node):
    name: str
    email: str

# Your custom walkers
class UserWalker(Walker):
    @on_visit
    async def visit_user(self, node: User):
        return {"user": node.to_dict()}

# Your endpoints
@endpoint("/users/{user_id}")
async def get_user(user_id: str):
    async with GraphContext() as ctx:
        user = await User.get(user_id, ctx=ctx)
        return {"user": user.to_dict()}

# Server setup
async def main():
    server = Server(
        config=ServerConfig(
            host="0.0.0.0",
            port=8000,
        )
    )
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🚫 **Anti-Patterns**

### **❌ Don't: Wildcard Imports**

```python
# ❌ Bad: Wildcard imports
from jvspatial.core import *
from jvspatial.api import *

# ✅ Good: Explicit imports
from jvspatial.core import Node, Edge, Walker
from jvspatial.api import Server, endpoint
```

### **❌ Don't: Internal Module Imports**

```python
# ❌ Bad: Importing from internal modules
from jvspatial.core.walker.event_system import EventManager
from jvspatial.api.endpoints.router import BaseRouter

# ✅ Good: Use public API
from jvspatial.core import Walker
from jvspatial.api.endpoints import EndpointRouter
```

### **❌ Don't: Circular Imports**

```python
# ❌ Bad: Core importing from API
# mywalker.py (in core package)
from jvspatial.api import Server  # Circular dependency!

# ✅ Good: Use dependency injection
# mywalker.py
class MyWalker(Walker):
    def __init__(self, server=None):
        super().__init__()
        self.server = server
```

### **❌ Don't: Relative Imports in Examples**

```python
# ❌ Bad: Relative imports in your code
from ..core import Node
from ...api import Server

# ✅ Good: Absolute imports
from jvspatial.core import Node
from jvspatial.api import Server
```

---

## 📋 **Quick Reference**

| What You Need | Import From | Example |
|--------------|-------------|---------|
| Core entities | `jvspatial` or `jvspatial.core` | `from jvspatial import Node, Edge` |
| Route decorators | `jvspatial.api.decorators` | `from jvspatial.api.decorators import endpoint` |
| Field decorators | `jvspatial.api.decorators` | `from jvspatial.api.decorators import endpoint_field` |
| Graph decorators | `jvspatial.core` | `from jvspatial.core import on_visit` |
| Server | `jvspatial.api` | `from jvspatial.api import Server` |
| Database | `jvspatial.db` | `from jvspatial.db import create_database` |
| Cache | `jvspatial.cache` | `from jvspatial.cache import get_cache_backend` |
| Storage | `jvspatial.storage.interfaces` | `from jvspatial.storage.interfaces import LocalFileInterface` |
| Utils decorators | `jvspatial.utils` | `from jvspatial.utils import memoize` |
| Type system | `jvspatial.utils` | `from jvspatial.utils import NodeId, is_dict` |
| Context | `jvspatial.core` or `jvspatial.api` | `from jvspatial.core import GraphContext` |

---

## 🔧 **IDE Configuration**

### **VS Code: Import Suggestions**

Add to `.vscode/settings.json`:

```json
{
  "python.analysis.extraPaths": [
    "./jvspatial"
  ],
  "python.autoComplete.extraPaths": [
    "./jvspatial"
  ]
}
```

### **PyCharm: Import Optimization**

1. Go to: **Settings → Editor → Code Style → Python → Imports**
2. Check: **Optimize imports on the fly**
3. Set: **Sort imports** to **true**

---

## 📖 **Related Documentation**

- [Module Responsibility Matrix](module-responsibility-matrix.md)
- [API Architecture](api-architecture.md)
- [Decorator Reference](decorator-reference.md)

---

**Last Updated**: 2025-10-20
**Version**: 0.0.1
**Maintainer**: JVspatial Team

