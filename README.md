# jvspatial

An async-first Python library for building graph-based spatial applications with FastAPI integration. Provides entity-centric database operations with automatic context management.

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/releases)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/TrueSelph/jvspatial/test-jvspatial.yaml)](https://github.com/TrueSelph/jvspatial/actions)
[![GitHub issues](https://img.shields.io/github/issues/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/pulls)
[![GitHub](https://img.shields.io/github/license/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/blob/main/LICENSE)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [Basic Example](#basic-example)
- [Core Concepts](#core-concepts)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Overview

jvspatial is an async-first Python library for building graph-based spatial applications with FastAPI integration. It provides entity-centric database operations with automatic context management.

Inspired by [Jaseci's](https://jaseci.org) object-spatial paradigm and leveraging Python's async capabilities, jvspatial empowers developers to model complex relationships, traverse object graphs, and implement agent-based architectures that scale with modern cloud-native concurrency requirements.

**Key Design Principles:**
- **Hierarchy**: Object → Node → Edge/Walker inheritance
- **Entity-Centric**: Direct database operations via entity methods
- **Unified Decorators**: `@attribute` for entity attributes, `@endpoint` for API endpoints
- **Automatic Context**: Server automatically provides database context to entities
- **Essential CRUD**: Core database operations with pagination support
- **Unified Configuration**: Single `Config` class for all settings
- **Async-First**: Built for modern Python async/await patterns

## Key Features

### 🎯 Inheritance Hierarchy
- **Object**: Base class for all entities
- **Node**: Graph nodes with spatial data (inherits from Object)
- **Edge**: Relationships between nodes (inherits from Object)
- **Walker**: Graph traversal and pathfinding (inherits from Object)
- **Root**: Singleton root node (inherits from Node)

### 🎨 Unified Decorator System
- `@attribute` - Define entity attributes with protection, transient flags, and validation
- `@endpoint` - Unified endpoint decorator for both functions and Walker classes
- Automatic parameter and response schema generation

### 🗄️ Entity-Centric Database Operations
- Entity methods: `Entity.get()`, `Entity.find()`, `Entity.create()`, `entity.save()`, `entity.delete()`
- Automatic context management
- Support for JSON, SQLite, MongoDB, and **DynamoDB** backends
- Multi-database support with prime database for core persistence
- Custom database registration for extensibility
- Pagination with `ObjectPager`

### ⚙️ Unified Configuration
- Single `Config` class for all settings
- Environment variable support
- Type-safe configuration

### 🚀 FastAPI Integration
- Built-in FastAPI server with automatic OpenAPI documentation
- Automatic endpoint registration from decorators
- Authentication and authorization with automatic endpoint registration when enabled
- Response schema definitions with examples
- Entity-centric CRUD operations

### ⚡ Performance Mixins
- **DeferredSaveMixin**: Batch multiple `save()` calls into a single database write
- Configurable via `JVSPATIAL_ENABLE_DEFERRED_SAVES` environment variable
- Ideal for entities with rapid, sequential updates

## Installation

```bash
# Core installation
pip install jvspatial
```

## Quick Start

> **Standard Examples**: For production-ready API implementations, see:
> - **Authenticated API**: [examples/api/authenticated_endpoints_example.py](https://github.com/TrueSelph/jvspatial/blob/main/examples/api/authenticated_endpoints_example.py) - Complete CRUD with authentication
> - **Unauthenticated API**: [examples/api/unauthenticated_endpoints_example.py](https://github.com/TrueSelph/jvspatial/blob/main/examples/api/unauthenticated_endpoints_example.py) - Public read-only API

### Basic Example

```python
from jvspatial.api import Server, endpoint
from jvspatial.core import Node

# Create server (entity-centric operations available automatically)
server = Server(
    title="My API",
    db_type="json",
    db_path="./jvdb",
    auth_enabled=False  # Set to True to enable authentication
)

# Define entity
class User(Node):
    name: str = ""
    email: str = ""

# Create endpoint
@endpoint("/users/{user_id}", methods=["GET"])
async def get_user(user_id: str):
    user = await User.get(user_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": await user.export()}

if __name__ == "__main__":
    server.run()
```

## Core Concepts

### Entity Definition and Attributes

```python
from jvspatial.core import Node
from jvspatial.core.annotations import attribute

class User(Node):
    name: str = ""
    email: str = ""
    cache: dict = attribute(transient=True, default_factory=dict)
```

### Unified Endpoint Decorator

The `@endpoint` decorator works with both functions and Walker classes:

```python
from jvspatial.api import Server, endpoint
from jvspatial.core import Node

server = Server(title="My API", db_type="json", db_path="./jvdb")

# Function endpoint
@endpoint("/api/users", methods=["GET"])
async def list_users(page: int = 1, per_page: int = 10):
    from jvspatial.core.pager import ObjectPager
    pager = ObjectPager(User, page_size=per_page)
    users = await pager.get_page(page=page)
    import asyncio
    users_list = await asyncio.gather(*[user.export() for user in users])
    return {"users": users_list}

# Authenticated endpoint
@endpoint("/api/admin", methods=["GET"], auth=True, roles=["admin"])
async def admin_panel():
    return {"admin": "dashboard"}

# Endpoint with response schema
from jvspatial.api.endpoints.response import ResponseField, success_response

@endpoint(
    "/api/users",
    methods=["GET"],
    response=success_response(
        data={
            "users": ResponseField(List[Dict], "List of users"),
            "total": ResponseField(int, "Total count")
        }
    )
)
async def get_users():
    return {"users": [], "total": 0}
```

### Entity-Centric Database Operations

```python
from jvspatial.core import Node

class User(Node):
    name: str = ""
    email: str = ""

# Entity-centric operations (no context needed - server provides it automatically)
user = await User.create(name="John", email="john@example.com")
users = await User.find({"context.name": "John"})  # Use context. prefix for fields
user = await User.get(user_id)  # Returns None if not found
if user:
    await user.save()
    await user.delete()

# Efficient counting
total_users = await User.count()  # Count all users
active_users = await User.count({"context.active": True})  # Count filtered users using query dict
active_users = await User.count(active=True)  # Count filtered users using keyword arguments
```

## Configuration

### Server Configuration

```python
from jvspatial.api import Server

# Basic server
server = Server(
    title="My API",
    description="API description",
    version="1.0.0",
    db_type="json",
    db_path="./jvdb"
)

# Server with authentication
server = Server(
    title="Secure API",
    auth_enabled=True,  # Automatically registers /auth/register, /auth/login, /auth/logout
    jwt_auth_enabled=True,
    jwt_secret="your-secret-key",
    jwt_expire_minutes=60,
    db_type="json",
    db_path="./jvdb"
)

# Server without authentication (public API)
server = Server(
    title="Public API",
    auth_enabled=False,  # NO authentication endpoints registered
    db_type="json",
    db_path="./jvdb_public"
)
```

### Authentication Behavior

- **`auth_enabled=True`**: Server automatically registers authentication endpoints (`/auth/register`, `/auth/login`, `/auth/logout`)
- **`auth_enabled=False`**: Authentication endpoints are **NOT** registered (public API)

## Documentation

### Getting Started
- [Quick Start Guide](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/quick-start-guide.md) - Get started in 5 minutes
- [Examples](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/examples.md) - Standard implementation examples
  - [Authenticated API Example](https://github.com/TrueSelph/jvspatial/blob/main/examples/api/authenticated_endpoints_example.py) - Complete CRUD with authentication
  - [Unauthenticated API Example](https://github.com/TrueSelph/jvspatial/blob/main/examples/api/unauthenticated_endpoints_example.py) - Public read-only API

### API Development
- [REST API Guide](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/rest-api.md) - API design patterns
- [Server API Guide](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/server-api.md) - Server configuration
- [Authentication Guide](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/authentication.md) - Authentication patterns
- [Entity Reference](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/entity-reference.md) - Node, Edge, Walker classes

### Advanced Topics
- [API Architecture](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/api-architecture.md) - System architecture
- [Graph Context Guide](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/graph-context.md) - Context management and multi-database support
- [Custom Database Guide](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/custom-database-guide.md) - Implementing custom database backends
- [Graph Visualization](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/graph-visualization.md) - Export graphs in DOT/Mermaid formats
- [Pagination](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/pagination.md) - ObjectPager usage

## Contributors

<p align="center">
    <a href="https://github.com/TrueSelph/jvspatial/graphs/contributors">
        <img src="https://contrib.rocks/image?repo=TrueSelph/jvspatial" />
    </a>
</p>

## Contributing

We welcome contributions! Please see our [Contributing Guide](https://github.com/TrueSelph/jvspatial/blob/main/docs/md/contributing.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/TrueSelph/jvspatial/blob/main/LICENSE) file for details.