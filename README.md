# jvspatial

An async-first Python library for building graph-based spatial applications with FastAPI integration. Provides entity-centric database operations with automatic context management.

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/releases)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/TrueSelph/jvspatial/test-jvspatial.yaml)](https://github.com/TrueSelph/jvspatial/actions)
[![GitHub issues](https://img.shields.io/github/issues/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/pulls)
[![GitHub](https://img.shields.io/github/license/TrueSelph/jvspatial)](LICENSE)

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
  - [Basic Example](#basic-example)
  - [Serverless Deployment (AWS Lambda)](#serverless-deployment-aws-lambda)
- [Core Concepts](#core-concepts)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Overview

jvspatial is an async-first Python library for building graph-based spatial applications with FastAPI integration. It provides entity-centric database operations with automatic context management.

Inspired by [Jaseci's](https://jaseci.org) object-spatial paradigm and leveraging Python's async capabilities, jvspatial empowers developers to model complex relationships, traverse object graphs, and implement agent-based architectures that scale with modern cloud-native concurrency requirements.

**🚀 Serverless Ready**: Deploy to AWS Lambda with zero configuration changes. Enable `serverless_mode=True` and your FastAPI app is automatically wrapped with Mangum for Lambda compatibility. Includes native DynamoDB support for persistent storage in serverless environments.

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

### ☁️ Serverless Deployment (AWS Lambda)
- **Zero-configuration Lambda deployment** with `serverless_mode=True`
- Automatic Mangum integration for FastAPI → Lambda compatibility
- **Native DynamoDB support** for persistent storage in serverless environments
- Handler automatically exposed at module level for Lambda
- Works seamlessly with API Gateway
- See [Lambda Example](examples/api/lambda_example.py) for complete deployment guide

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
- **Serverless deployment** to AWS Lambda with automatic handler setup

## Installation

```bash
# Core installation
pip install jvspatial

# With serverless support (AWS Lambda + DynamoDB)
pip install jvspatial[serverless]
```

## Quick Start

> **💡 Standard Examples**: For production-ready API implementations, see:
> - **Authenticated API**: [`examples/api/authenticated_endpoints_example.py`](examples/api/authenticated_endpoints_example.py) - Complete CRUD with authentication
> - **Unauthenticated API**: [`examples/api/unauthenticated_endpoints_example.py`](examples/api/unauthenticated_endpoints_example.py) - Public read-only API
> - **🚀 Serverless Lambda**: [`examples/api/lambda_example.py`](examples/api/lambda_example.py) - AWS Lambda deployment with DynamoDB

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
    return {"user": user.export()}

if __name__ == "__main__":
    server.run()
```

### Serverless Deployment (AWS Lambda)

Deploy to AWS Lambda with zero configuration changes:

```python
from jvspatial.api import Server, endpoint
from jvspatial.core import Node

# Enable serverless mode - handler is automatically created and exposed
server = Server(
    title="Lambda API",
    serverless_mode=True,  # Automatic Lambda handler setup
    db_type="dynamodb",    # Use DynamoDB for persistent storage
    dynamodb_table_name="myapp",
    dynamodb_region="us-east-1",
)

class Product(Node):
    name: str = ""
    price: float = 0.0

@endpoint("/products", methods=["GET"])
async def list_products():
    products = await Product.find({})
    return {"products": [p.export() for p in products]}

# Handler is automatically available at module level for Lambda
# No manual assignment needed! AWS Lambda will call: lambda_example.handler
```

**Deployment Steps:**
1. Install: `pip install jvspatial[serverless]`
2. Package your code and dependencies
3. Set Lambda handler to: `your_module.handler`
4. Configure API Gateway trigger
5. Deploy!

See the [complete Lambda example](examples/api/lambda_example.py) for full deployment guide.

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
    return {"users": [user.export() for user in users]}

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

# Counting: use len() with find() - Object.count() doesn't exist
count = len(await User.find({"context.active": True}))
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
- [Quick Start Guide](docs/md/quick-start-guide.md) - Get started in 5 minutes
- [Examples](docs/md/examples.md) - **Standard implementation examples** ⭐
  - [Authenticated API Example](examples/api/authenticated_endpoints_example.py) - Complete CRUD with authentication
  - [Unauthenticated API Example](examples/api/unauthenticated_endpoints_example.py) - Public read-only API
- [API Implementation Standards](docs/md/API_IMPLEMENTATION_STANDARDS.md) - Standard patterns and best practices

### API Development
- [REST API Guide](docs/md/rest-api.md) - API design patterns
- [Server API Guide](docs/md/server-api.md) - Server configuration and **serverless deployment**
- [Authentication Guide](docs/md/authentication.md) - Authentication patterns
- [Entity Reference](docs/md/entity-reference.md) - Node, Edge, Walker classes
- [Lambda Deployment Example](examples/api/lambda_example.py) - Complete AWS Lambda setup with DynamoDB

### Advanced Topics
- [API Architecture](docs/md/api-architecture.md) - System architecture
- [Graph Context Guide](docs/md/graph-context.md) - Context management and multi-database support
- [Custom Database Guide](docs/md/custom-database-guide.md) - Implementing custom database backends
- [Graph Visualization](docs/md/graph-visualization.md) - Export graphs in DOT/Mermaid formats
- [Pagination](docs/md/pagination.md) - ObjectPager usage

## Contributors

<p align="center">
    <a href="https://github.com/TrueSelph/jvspatial/graphs/contributors">
        <img src="https://contrib.rocks/image?repo=TrueSelph/jvspatial" />
    </a>
</p>

## Contributing

We welcome contributions! Please see our [Contributing Guide](docs/md/contributing.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.