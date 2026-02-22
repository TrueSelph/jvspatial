# Module Responsibility Matrix

**Date**: 2025-02-22
**Version**: 0.0.3

This document provides a clear matrix of module responsibilities, helping developers understand where to find specific functionality.

---

## 📊 **Module Overview**

| Module | Primary Responsibility | Size | Status |
|--------|----------------------|------|--------|
| **core** | Graph entities & traversal | 14 files | ✅ Stable |
| **api** | REST API & server | 30+ files | ✅ Reorganized |
| **db** | Database abstraction | 6 files | ✅ Stable |
| **cache** | Caching backends | 6 files | ✅ Stable |
| **storage** | File storage | 8 files | ✅ Stable |
| **utils** | Utilities & helpers | 7 files | ✅ Enhanced |

---

## 🌐 **Core Module** (`jvspatial.core`)

**Responsibility**: Graph entities, traversal patterns, and core abstractions

| File/Directory | Purpose | Key Classes/Functions |
|----------------|---------|----------------------|
| `entities/object.py` | Base entity | `Object` |
| `entities/node.py` | Graph nodes | `Node` |
| `entities/edge.py` | Graph edges | `Edge` |
| `entities/root.py` | Root node | `Root` |
| `entities/walker.py` | Walker pattern | `Walker` |
| `entities/walker_components/` | Walker support | Event system, protection, queues |
| `context.py` | Graph context | `GraphContext`, `PerformanceMonitor` |
| `decorators.py` | Graph decorators | `@on_visit`, `@on_exit` |
| `events.py` | Event system | Event handling |
| `entities/node_query.py` | Node queries | `NodeQuery` |
| `annotations.py` | Annotations | `@attribute` |
| `utils.py` | Core utilities | Serialization, helpers |
| `pager.py` | Pagination | `ObjectPager` |
| `entities/` | Entity re-exports | Central import point |

**When to use**:
- Creating graph entities (nodes, edges, walkers)
- Graph traversal operations
- Event handling during traversal
- Database-agnostic graph operations

---

## 🚀 **API Module** (`jvspatial.api`)

**Responsibility**: REST API, server management, endpoints, authentication

| Subdirectory | Purpose | Key Components |
|--------------|---------|----------------|
| `decorators/` | Route & field decorators | `@endpoint`, `endpoint_field` |
| `endpoints/` | Endpoint management | `EndpointRouter`, `ResponseHelper`, `Registry` |
| `integrations/` | External services | Webhooks, scheduler, storage |
| `middleware/` | Request processing | `MiddlewareManager`, `ErrorMiddleware` |
| `auth/` | Authentication | Auth entities, middleware, endpoints |
| `services/` | Core services | Discovery, lifecycle |
| `server.py` | Main server | `Server`, `ServerConfig` |
| `context.py` | Server context | `ServerContext`, context management |
| `exceptions.py` | API exceptions | Exception hierarchy |

**When to use**:
- Creating REST API endpoints
- Server configuration and management
- Authentication and authorization
- Webhook integration
- Scheduled tasks

---

## 💾 **Database Module** (`jvspatial.db`)

**Responsibility**: Database abstraction and persistence

| File | Purpose | Key Components |
|------|---------|----------------|
| `database.py` | Base database | `Database` |
| `jsondb.py` | JSON backend | `JsonDB` |
| `mongodb.py` | MongoDB backend | `MongoDB` |
| `factory.py` | Database factory | `create_database()`, `register_database_type()` |
| `query.py` | Query engine | `QueryEngine` |

**When to use**:
- Storing/retrieving entities
- Database operations
- Query building
- Switching database backends

---

## ⚡ **Cache Module** (`jvspatial.cache`)

**Responsibility**: Caching strategies and backends

| File | Purpose | Key Components |
|------|---------|----------------|
| `base.py` | Base cache | `CacheBackend` |
| `memory.py` | In-memory cache | `MemoryCache` |
| `redis.py` | Redis cache | `RedisCache` |
| `layered.py` | Multi-tier cache | `LayeredCache` |
| `factory.py` | Cache factory | `create_cache()` |

**When to use**:
- Caching frequently accessed data
- Performance optimization
- Distributed caching (Redis)
- Multi-tier caching strategies

---

## 📁 **Storage Module** (`jvspatial.storage`)

**Responsibility**: File storage and management

| Subdirectory | Purpose | Key Components |
|--------------|---------|----------------|
| `interfaces/` | Storage interfaces | `FileStorageInterface`, `LocalFileInterface`, `S3FileInterface` |
| `managers/` | Storage managers | `ProxyManager` |
| `security/` | Security | `PathSanitizer`, `FileValidator` |
| `models.py` | Storage models | Data models |
| `exceptions.py` | Storage exceptions | Exception types |

**When to use**:
- File upload/download
- Cloud storage (S3)
- Local file storage
| File security and validation

---

## 🛠️ **Utils Module** (`jvspatial.utils`)

**Responsibility**: Shared utilities and helpers

| File | Purpose | Key Components |
|------|---------|----------------|
| `decorators.py` | Utility decorators | `@memoize`, `@retry`, `@timeout` |
| `types.py` | Type definitions | Type aliases, type guards, converters |
| `context.py` | Global context | `GlobalContext` |
| `factory.py` | Plugin factory | `PluginFactory` |
| `serialization.py` | Serialization | `serialize_datetime()` |
| `validation.py` | Validation | `PathValidator` |

**When to use**:
- Cross-module utilities
- Type hints and type safety
- Decorator patterns
- Configuration management

---

## 🔍 **Responsibility Decision Tree**

### **"Where should I put this code?"**

```
START
  ↓
Is it a graph entity or traversal logic?
  YES → core/
  NO ↓

Is it an API/server concern?
  YES → api/
  NO ↓

Is it database persistence?
  YES → db/
  NO ↓

Is it caching?
  YES → cache/
  NO ↓

Is it file storage?
  YES → storage/
  NO ↓

Is it a shared utility?
  YES → utils/
  NO ↓

Consider creating new module or extending existing one
```

---

## 📝 **Common Patterns**

### **Pattern 1: Graph Operations**
```
core/entities → db/database → cache/backend
```
Create entities in `core`, persist with `db`, cache with `cache`

### **Pattern 2: API Endpoints**
```
api/decorators → api/endpoints → core/walker → db/database
```
Define with decorators, route with endpoints, implement with walkers, persist with db

### **Pattern 3: File Handling**
```
api/endpoints → storage/interfaces → storage/security
```
Receive via API, store with storage, validate with security

### **Pattern 4: Background Tasks**
```
api/integrations/scheduler → core/walker → db/database
```
Schedule with scheduler, implement with walkers, persist with db

---

## 🎯 **Import Patterns**

### **Core Entities**
```python
from jvspatial import Object, Node, Edge, Walker, Root
from jvspatial.core import GraphContext, on_visit, on_exit
```

### **API**
```python
from jvspatial.api import Server, ServerConfig
from jvspatial.api.decorators import endpoint, endpoint_field
```

### **Database**
```python
from jvspatial.db import create_database, Database, JsonDB, get_database_manager
```

### **Cache**
```python
from jvspatial.cache import create_cache
```

### **Storage**
```python
from jvspatial.storage.interfaces import LocalFileInterface, S3FileInterface
```

### **Utils**
```python
from jvspatial.utils import memoize, retry, NodeId, is_dict, to_dict
```

---

## 🚫 **Anti-Patterns**

### **❌ Don't: Cross-layer violations**
```python
# ❌ Bad: API importing from internal walker modules
from jvspatial.core.entities.walker_components.event_system import EventManager

# ✅ Good: Use public API
from jvspatial.core import Walker
```

### **❌ Don't: Circular dependencies**
```python
# ❌ Bad: Core importing from API
# core/something.py
from jvspatial.api import Server

# ✅ Good: Use dependency injection
def my_function(server: Server):
    pass
```

### **❌ Don't: Mixing responsibilities**
```python
# ❌ Bad: Database logic in API endpoints
@endpoint("/users")
def get_users():
    # Direct database access here
    pass

# ✅ Good: Separate concerns
class UserWalker(Walker):
    # Database logic in walker
    pass

@endpoint("/users")
def get_users():
    # API logic only
    pass
```

---

## 📚 **Module Dependencies**

```
utils  (no dependencies)
  ↑
core  (depends on: utils, db, cache)
  ↑
api  (depends on: core, utils, db, cache, storage)
  ↑
storage  (depends on: utils)
  ↑
db  (depends on: utils)
  ↑
cache  (depends on: utils)
```

**Dependency Rules**:
1. `utils` has NO dependencies (foundation)
2. `core` can use `utils`, `db`, `cache`
3. `api` can use everything
4. `db`, `cache`, `storage` can only use `utils`

---

## 🔧 **Extension Points**

### **Adding New Functionality**

| What | Where | Pattern |
|------|-------|---------|
| New graph entity | `core/` | Inherit from `Object` |
| New API endpoint | `api/endpoints/` | Use `@endpoint` decorator |
| New database backend | `db/` | Implement `Database` interface |
| New cache backend | `cache/` | Implement `CacheBackend` interface |
| New storage provider | `storage/interfaces/` | Implement `FileStorageInterface` |
| New utility | `utils/` | Add to appropriate file |

---

## 📖 **Related Documentation**

- [API Architecture](api-architecture.md)
- [Graph Traversal](graph-traversal.md)
- [Decorator Reference](decorator-reference.md)
- [Context Management](context-management-guide.md)
- [Database Guide](mongodb-query-interface.md)

---

**Last Updated**: 2025-02-22
**Version**: 0.0.3
**Maintainer**: JVspatial Team
