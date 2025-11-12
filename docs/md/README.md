# JVspatial Documentation

**Version**: 0.0.1
**Last Updated**: 2025-10-20

Welcome to the jvspatial documentation! This guide will help you understand and use the jvspatial library effectively.

---

## 📚 **Documentation Index**

### **Getting Started**

| Document | Description | Audience |
|----------|-------------|----------|
| [Quick Start Guide](quick-start-guide.md) | Get started in 5 minutes | Beginners |
| [Examples](examples.md) | Code examples and tutorials | All levels |
| [Installation Guide](../README.md) | Installation and setup | Beginners |

### **Core Concepts**

| Document | Description | Audience |
|----------|-------------|----------|
| [Graph Traversal](graph-traversal.md) | Walker pattern and graph operations | Intermediate |
| [Graph Visualization](graph-visualization.md) | Export graphs in DOT/Mermaid formats | All levels |
| [Entity Reference](entity-reference.md) | Node, Edge, Walker classes | All levels |
| [Context Management](context-management-guide.md) | GraphContext, ServerContext usage | Intermediate |
| [Node Operations](node-operations.md) | Working with nodes | All levels |

### **API & Server**

| Document | Description | Audience |
|----------|-------------|----------|
| [REST API](rest-api.md) | API design and endpoints | All levels |
| [API Architecture](api-architecture.md) | Server architecture | Advanced |
| [Server API](server-api.md) | Server configuration | Intermediate |
| [Examples](examples.md) | **Standard implementation examples** | ⭐ **Start Here** |
| [Decorator Reference](decorator-reference.md) | All decorators explained | All levels |

### **Authentication & Security**

| Document | Description | Audience |
|----------|-------------|----------|
| [Authentication](authentication.md) | Auth system overview | Intermediate |
| [Auth Quickstart](auth-quickstart.md) | Get auth working fast | Beginners |

### **Integrations**

| Document | Description | Audience |
|----------|-------------|----------|
| [Webhooks Architecture](webhook-architecture.md) | Webhook system design | Advanced |
| [Webhooks Quickstart](webhooks-quickstart.md) | Using webhooks | Intermediate |
| [Scheduler](scheduler.md) | Background job scheduling | Intermediate |
| [File Storage](file-storage-architecture.md) | File storage system | Intermediate |
| [File Storage Usage](file-storage-usage.md) | Using file storage | All levels |

### **Database & Caching**

| Document | Description | Audience |
|----------|-------------|----------|
| [Graph Context](graph-context.md) | Database management and multi-database support | Intermediate |
| [MongoDB Query Interface](mongodb-query-interface.md) | Database queries | Intermediate |
| [Custom Database Guide](custom-database-guide.md) | Implementing custom database backends | Advanced |
| [Caching](caching.md) | Cache strategies | Intermediate |

### **Advanced Topics**

| Document | Description | Audience |
|----------|-------------|----------|
| [Architectural Decisions](architectural-decisions.md) | ADRs and design rationale | Advanced |
| [Module Responsibility Matrix](module-responsibility-matrix.md) | Module organization | Advanced |
| [Import Patterns](import-patterns.md) | Best practices for imports | Intermediate |
| [Design Decisions](design-decisions.md) | Design philosophy | Advanced |
| [Optimization](optimization.md) | Performance tuning | Advanced |
| [Error Handling](error-handling.md) | Error patterns | Intermediate |

### **Development**

| Document | Description | Audience |
|----------|-------------|----------|
| [Contributing](contributing.md) | Contribution guide | Developers |
| [Custom Database Guide](custom-database-guide.md) | Extending with custom databases | Advanced |
| [Troubleshooting](troubleshooting.md) | Common issues | All levels |
| [Migration Guide](migration.md) | Adopting jvspatial | Users |

### **Reference**

| Document | Description | Audience |
|----------|-------------|----------|
| [Attribute Annotations](attribute-annotations.md) | @attribute | All levels |
| [Walker Events](walker-reporting-events.md) | Walker event system | Intermediate |
| [Walker Queue](walker-queue-operations.md) | Queue management | Advanced |
| [Walker Trail](walker-trail-tracking.md) | Trail tracking | Advanced |
| [Pagination](pagination.md) | Paginating results | Intermediate |
| [Environment Config](environment-configuration.md) | Configuration options | All levels |
| [Infinite Walk Protection](infinite-walk-protection.md) | Preventing infinite loops | Advanced |

---

## 🎯 **Learning Paths**

### **Path 1: Beginner → Intermediate**

1. ✅ [Quick Start Guide](quick-start-guide.md)
2. ✅ [Examples](examples.md)
3. ✅ [Entity Reference](entity-reference.md)
4. ✅ [Graph Traversal](graph-traversal.md)
5. ✅ [REST API](rest-api.md)
6. ✅ [Decorator Reference](decorator-reference.md)

### **Path 2: API Development**

1. ✅ [Quick Start Guide](quick-start-guide.md)
2. ✅ [REST API](rest-api.md)
3. ✅ [Decorator Reference](decorator-reference.md)
4. ✅ [Authentication](authentication.md)
5. ✅ [Server API](server-api.md)
6. ✅ [Webhooks Quickstart](webhooks-quickstart.md)

### **Path 3: Advanced Architecture**

1. ✅ [Module Responsibility Matrix](module-responsibility-matrix.md)
2. ✅ [Import Patterns](import-patterns.md)
3. ✅ [API Architecture](api-architecture.md)
4. ✅ [Architectural Decisions](architectural-decisions.md)
5. ✅ [Design Decisions](design-decisions.md)
6. ✅ [Optimization](optimization.md)

---

## 🔍 **Quick Reference**

### **Common Tasks**

| Task | Document | Section |
|------|----------|---------|
| Create a node | [Quick Start](quick-start-guide.md) | Pattern 1 |
| Define an endpoint | [Quick Start](quick-start-guide.md) | Step 3 |
| Build a walker | [Graph Traversal](graph-traversal.md) | Basic Walker |
| Visualize graph | [Graph Visualization](graph-visualization.md) | Quick Start |
| Query database | [MongoDB Query](mongodb-query-interface.md) | Query Builder |
| Add authentication | [Auth Quickstart](auth-quickstart.md) | Setup |
| Setup caching | [Caching](caching.md) | Configuration |
| Handle files | [File Storage Usage](file-storage-usage.md) | Basic Usage |
| Schedule jobs | [Scheduler](scheduler.md) | Basic Tasks |

### **Common Issues**

| Issue | Document | Solution |
|-------|----------|----------|
| Import errors | [Troubleshooting](troubleshooting.md) | Import Issues |
| Context errors | [Context Management](context-management-guide.md) | Usage Patterns |
| Import patterns | [Import Patterns](import-patterns.md) | Best Practices |
| Authentication fails | [Troubleshooting](troubleshooting.md) | Auth Issues |

---

## 📖 **Document Categories**

### **By Complexity**

**Beginner** (⭐):
- Quick Start Guide
- Examples
- Entity Reference
- Node Operations
- REST API
- Auth Quickstart
- Webhooks Quickstart
- File Storage Usage

**Intermediate** (⭐⭐):
- Graph Traversal
- Context Management
- Authentication
- Server API
- Scheduler
- MongoDB Query Interface
- Caching
- Import Patterns
- Error Handling

**Advanced** (⭐⭐⭐):
- API Architecture
- Module Responsibility Matrix
- Architectural Decisions
- Design Decisions
- Optimization
- Webhook Architecture
- File Storage Architecture
- Walker Queue Operations
- Walker Trail Tracking
- Infinite Walk Protection

### **By Topic**

**Core Graph**:
- Graph Traversal
- Graph Visualization
- Entity Reference
- Node Operations
- Walker Events
- Walker Queue Operations
- Walker Trail Tracking

**API Development**:
- REST API
- API Architecture
- Server API
- Decorator Reference
- Error Handling

**Authentication & Security**:
- Authentication
- Auth Quickstart
- Attribute Annotations

**Integrations**:
- Webhooks Architecture
- Webhooks Quickstart
- Scheduler
- File Storage Architecture
- File Storage Usage

**Data Management**:
- MongoDB Query Interface
- Caching
- Pagination

**Architecture**:
- Module Responsibility Matrix
- Import Patterns
- Architectural Decisions
- Design Decisions

---

## 🎓 **Glossary**

| Term | Definition |
|------|------------|
| **Node** | A data point in the graph |
| **Edge** | A relationship between nodes |
| **Walker** | A pattern for traversing the graph |
| **Context** | Manages database and configuration |
| **Root** | Entry point to the graph |
| **Endpoint** | An API route |
| **Query Builder** | Fluent interface for database queries |
| **Cache Backend** | Storage for cached data |
| **Storage Interface** | File storage abstraction |
| **Decorator** | Function/class modifier |

---

## 🔧 **API Reference**

### **Core Modules**

```python
# Core entities
from jvspatial import Object, Node, Edge, Walker, Root

# Graph operations
from jvspatial.core import GraphContext, on_visit, on_exit

# Graph visualization
from jvspatial.core.graph import generate_graph_dot, generate_graph_mermaid, export_graph

# API
from jvspatial.api import Server, ServerConfig, endpoint

# Database
from jvspatial.db import create_database, Database

# Cache
from jvspatial.cache import get_cache_backend

# Storage
from jvspatial.storage.interfaces import LocalFileInterface

# Utils
from jvspatial.utils import memoize, retry, NodeId
```

---

## 📊 **Version History**

| Version | Date | Changes |
|---------|------|---------|
| **0.2.0** | 2025-10-20 | Major reorganization, utils module, new docs |
| **0.1.x** | 2025-09-xx | Initial release |

---

## 🤝 **Contributing**

Want to improve the documentation?

1. Read the [Contributing Guide](contributing.md)
2. Check for open documentation issues
3. Submit a pull request

---

## 📧 **Support**

- **Documentation Issues**: Open a GitHub issue
- **Questions**: GitHub Discussions
- **Email**: support@jvspatial.com

---

## 📝 **License**

See [License](license.md) for details.

---

**Last Updated**: 2025-10-20
**Version**: 0.0.1
**Maintainer**: JVspatial Team
