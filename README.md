<div align="center">

# jvspatial

An async-first Python library for building graph-based spatial applications with FastAPI integration.

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/releases)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/TrueSelph/jvspatial/test-jvspatial.yaml)](https://github.com/TrueSelph/jvspatial/actions)
[![GitHub issues](https://img.shields.io/github/issues/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/TrueSelph/jvspatial)](https://github.com/TrueSelph/jvspatial/pulls)
[![GitHub](https://img.shields.io/github/license/TrueSelph/jvspatial)](LICENSE)

</div>

## Table of Contents

- [Overview](#overview)
  - [Design Principles](#design-principles)
  - [Use Cases](#use-cases)
- [Features](#features)
  - [Core Features](#core-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Key Concepts](#key-concepts)
  - [Entity-Centric Design](#entity-centric-design)
  - [Graph Traversal](#graph-traversal)
  - [Entity Operations](#entity-operations)
- [Examples](#examples)
  - [Core Functionality](#core-functionality)
  - [API & Integration](#api--integration)
- [Configuration](#configuration)
  - [Core Settings](#core-settings)
  - [Auth Settings](#auth-settings)
  - [Storage Settings](#storage-settings)
  - [Walker Settings](#walker-settings)
- [Documentation](#documentation)
  - [Official Docs](#official-docs)
  - [User Resources](#user-resources)
  - [Developer Guides](#developer-guides)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
  - [Development Setup](#development-setup)
  - [Development Workflow](#development-workflow)
- [Contributors](#contributors)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Overview

jvspatial combines graph databases with spatial processing for building complex applications. Inspired by Jaseci Labs' object-spatial paradigm, it provides an async-first API with enterprise-grade features for building spatial applications, middleware, and services.

### Design Principles

- **Simple APIs**: Clean, predictable interfaces for graph operations
- **Type Safety**: Comprehensive validation with Pydantic
- **Async First**: Native async/await for high performance
- **Enterprise Ready**: Built-in security, storage, and caching
- **Extensible**: Pluggable backends and custom behaviors


## Comparison

How jvspatial compares to adjacent tools:

- **NetworkX**: Great for in-memory graph algorithms; jvspatial focuses on async application development, persistence, and REST integration.
- **Neo4j drivers**: Low-level graph database access; jvspatial provides a higher-level object-spatial model with walkers, endpoints, and auth.
- **Plain FastAPI + ORM**: Excellent for CRUD; jvspatial adds graph traversal, node/edge relationships, and spatial patterns.

## Who is this for?

- Backend engineers building spatially-aware services
- Data engineers modeling complex relationships as graphs
- Teams needing graph traversal with REST integration and auth
- Developers who prefer Python async patterns with clear APIs

## When to use

- You have entities with relationships (roads between cities, users following users)
- You need to traverse or analyze connected data efficiently
- You want REST endpoints backed by safe, async graph operations
- You need enterprise features: authentication, storage, caching

### Use Cases

- **Spatial Services**: Location-based APIs and analysis
- **Graph Processing**: Complex relationship traversal
- **Data APIs**: REST endpoints with built-in auth and storage
- **ETL Pipelines**: Async data processing and transformation
- **Middleware**: Secure integrations and event processing

## Key Concepts

jvspatial is built around three core concepts: Nodes, Edges, and Walkers. These provide the foundation for building complex spatial applications.

### Entity-Centric Design

```python
from jvspatial.core import Node

class User(Node):
    name: str
    email: str
    department: str

# Create and query entities
user = await User.create(name="Alice", email="alice@company.com")
active_users = await User.find({"context.active": True})

# Complex queries work across all backends
senior_engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.years": {"$gte": 5}}
    ]
})
```

### Graph Traversal

```python
from jvspatial.core import Walker, on_visit

class TeamAnalyzer(Walker):
    @on_visit(User)
    async def analyze_team(self, here: User):
        # Find team members
        team = await here.nodes(
            node="User",
            department=here.department,
            active=True
        )
        await self.visit(team)
```

### Entity Operations

```python
# CRUD operations
user = await User.get(user_id)
user.name = "Alice Johnson"
await user.save()

# Filtering and aggregation
count = await User.count({"context.role": "engineer"})
depts = await User.distinct("department")
```

## Installation

```bash
pip install jvspatial            # Basic installation
pip install jvspatial[all]       # All features
pip install jvspatial[api]       # FastAPI integration
pip install jvspatial[storage]   # S3 storage support
pip install jvspatial[auth]      # Authentication features
pip install jvspatial[cache]     # Redis caching support
```

Requirements:
- Python 3.9+
- FastAPI 0.88+ (for REST API)
- MongoDB 5.0+ (optional)
- Redis (optional)

## Quick Start

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install jvspatial
```

2. Create a `.env` file:
```bash
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=./jvdb/dev

# Auth settings
JVSPATIAL_JWT_SECRET=your-secret-key
JVSPATIAL_JWT_ALGORITHM=HS256
```

3. Create a server:
```python
from jvspatial.api import Server
from jvspatial.api.auth.decorators import auth_endpoint

# Create server
server = Server(
    title="My API",
    description="First jvspatial API",
    auth_enabled=True
)

# Add endpoint
@auth_endpoint("/api/hello")
async def hello(name: str = "World", endpoint=None):
    return endpoint.success({
        "message": f"Hello, {name}!"
    })

if __name__ == "__main__":
    server.run()
```

## Features

### Core Features

#### Entity System
- **Entity-Centric Design** - [docs/md/entity-reference.md](docs/md/entity-reference.md)
  - MongoDB-style query interface across all backends
  - Unified API for JSON and MongoDB storage
  - Extensible database interface
  - Consistent CRUD operations

- **Type Safety** - [docs/md/attribute-annotations.md](docs/md/attribute-annotations.md)
  - Full Pydantic integration
  - Runtime type validation
  - Rich type hints and IDE support
  - Custom type converters

- **Attribute Control** - [docs/md/attribute-annotations.md](docs/md/attribute-annotations.md)
  - `@protected` decorator for immutable fields
  - `@private` decorator for private properties
  - `@transient` decorator for runtime-only data
  - Computed properties
  - Validation hooks
  - Validation hooks

#### Graph Processing
- **Graph Traversal** - [docs/md/node-operations.md](docs/md/node-operations.md)
  - Walker-based graph processing
  - Semantic path filtering
  - Bidirectional traversal
  - Custom traversal strategies

- **Walker Features** - [docs/md/walker-reporting-events.md](docs/md/walker-reporting-events.md)
  - Event-driven walker coordination
  - Built-in reporting system
  - Data collection and aggregation
  - Inter-walker communication

- **Safety Features** - [docs/md/infinite-walk-protection.md](docs/md/infinite-walk-protection.md)
  - Infinite walk protection
  - Configurable step limits
  - Visit frequency control
  - Execution time limits

#### Data Management
- **Database Operations** - [docs/md/mongodb-query-interface.md](docs/md/mongodb-query-interface.md)
  - Multi-backend support (JSON, MongoDB)
  - Atomic transactions
  - Bulk operations
  - Query optimization

- **Caching System** - [docs/md/caching.md](docs/md/caching.md)
  - Multi-level cache architecture
  - In-memory caching
  - Redis integration
  - Cache invalidation strategies

- **Pagination** - [docs/md/pagination.md](docs/md/pagination.md)
  - Database-level pagination
  - Efficient `ObjectPager`
  - Cursor-based navigation
  - Automatic count handling

#### API & Integration
- **FastAPI Integration** - [docs/md/rest-api.md](docs/md/rest-api.md)
  - Built-in REST endpoints
  - Automatic OpenAPI docs
  - Request validation
  - Response formatting

- **Webhook System** - [docs/md/webhook-architecture.md](docs/md/webhook-architecture.md)
  - HMAC signature verification
  - Idempotency handling
  - Path-based authentication
  - Async webhook processing
  - Automatic payload injection

- **Background Tasks**
  - Async task scheduling
  - Task prioritization
  - Error handling
  - Task monitoring

#### Security
- **Authentication** - [docs/md/authentication.md](docs/md/authentication.md)
  - JWT token support
  - API key management
  - Multi-scheme auth
  - Token refresh handling

- **Authorization**
  - Role-based access control (RBAC)
  - Spatial permissions system
  - Granular access policies
  - Permission inheritance

- **Security Features**
  - Rate limiting
  - Request validation
  - CORS support
  - SSL/TLS configuration

#### Storage & Files
- **File Storage** - [docs/md/file-storage-architecture.md](docs/md/file-storage-architecture.md)
  - Local file system support
  - S3 compatible storage
  - File streaming
  - Metadata management

- **Storage Features**
  - Automatic cleanup
  - Version control
  - Content validation
  - Access control

#### Development Tools
- **Testing Support**
  - Comprehensive test utilities
  - Mock data generators
  - Test fixtures
  - Performance testing tools

- **Debugging**
  - Detailed logging
  - Performance profiling
  - Query analysis
  - Error tracking

- **Documentation**
  - Extensive API docs
  - Code examples
  - Best practices
  - Migration guides

## Examples

Browse example categories in the `/examples` directory:

### Core Functionality
- [Core Examples](examples/core/) - Entity modeling and basic operations
- [Database Examples](examples/database/) - Query and ORM features
- [Walker Examples](examples/walkers/) - Graph traversal patterns

### API & Integration
- [API Examples](examples/api/) - Server and endpoint setup
- [Auth Examples](examples/auth/) - Authentication and permissions
- [Storage Examples](examples/storage/) - File storage features
- [Integration Examples](examples/integrations/) - External system integrations

## Configuration

See [.env.example](.env.example) for all configuration options.

### Core Settings

- `JVSPATIAL_DB_TYPE`: Database backend (`json` or `mongodb`)
- `JVSPATIAL_JSONDB_PATH`: Path for JSON database files
- `JVSPATIAL_MONGODB_URI`: MongoDB connection URI

### Authentication

- `JVSPATIAL_JWT_SECRET`: JWT signing key
- `JVSPATIAL_JWT_ALGORITHM`: JWT algorithm (default: HS256)
- `JVSPATIAL_JWT_EXPIRATION_HOURS`: JWT token expiration
- `JVSPATIAL_API_KEY_HEADER`: API key header name
- `JVSPATIAL_API_KEY_PREFIX`: API key prefix

### Storage

- `JVSPATIAL_FILE_STORAGE_ENABLED`: Enable file storage
- `JVSPATIAL_FILE_STORAGE_PROVIDER`: Storage provider (`local` or `s3`)
- `JVSPATIAL_FILE_STORAGE_ROOT`: Local storage directory
- `JVSPATIAL_S3_*`: AWS S3 configuration

### Walker Settings

- `JVSPATIAL_WALKER_PROTECTION_ENABLED`: Enable infinite walk protection
- `JVSPATIAL_WALKER_MAX_STEPS`: Maximum steps before halting (default: 10000)
- `JVSPATIAL_WALKER_MAX_VISITS_PER_NODE`: Maximum node revisits (default: 100)
- `JVSPATIAL_WALKER_MAX_EXECUTION_TIME`: Maximum execution time in seconds

## Documentation

### Core Documentation
- [API Architecture](docs/md/api-architecture.md) - API system design and components
- [Authentication](docs/md/authentication.md) - Authentication and authorization
- [Graph Context](docs/md/graph-context.md) - Understanding graph operations
- [Node Operations](docs/md/node-operations.md) - Working with nodes
- [Entity Reference](docs/md/entity-reference.md) - Entity types and usage

### Advanced Topics
- [MongoDB Query Interface](docs/md/mongodb-query-interface.md) - Query patterns
- [Infinite Walk Protection](docs/md/infinite-walk-protection.md) - Safety features
- [Caching System](docs/md/caching.md) - Performance optimization
- [File Storage](docs/md/file-storage-architecture.md) - Storage architecture

### Development Guides
- [Error Handling](docs/md/error-handling.md) - Error management
- [Optimization](docs/md/optimization.md) - Performance tuning
- [Troubleshooting](docs/md/troubleshooting.md) - Common issues
- [Webhooks](docs/md/webhook-architecture.md) - Event processing

### User Resources
- [GitHub Issues](https://github.com/TrueSelph/jvspatial/issues) - Bug reports and feature requests
- [GitHub Discussions](https://github.com/TrueSelph/jvspatial/discussions) - Community discussions
- [Stack Overflow](https://stackoverflow.com/questions/tagged/jvspatial) - Q&A

### Developer Guides
- [Contributing Guide](CONTRIBUTING.md) - Development setup
- [Architecture Guide](docs/architecture.md) - System design
- [Testing Guide](docs/testing.md) - Test patterns

## Project Structure

```
jvspatial/
├── jvspatial/              # Core package
│   ├── api/                # API components
│   │   ├── auth/           # Authentication
│   │   ├── endpoint/       # Endpoint routing
│   │   └── storage/        # Storage backends
│   ├── core/               # Core features
│   │   ├── entities/       # Node, Edge, Walker
│   │   ├── events/         # Event system
│   │   └── query/          # Query engine
│   └── db/                 # Database backends
│       ├── json/           # JSON storage
│       └── mongo/          # MongoDB integration
│
├── docs/                   # Documentation
│   ├── guides/             # User guides
│   ├── api/                # API reference
│   └── examples/           # Example code
│
├── examples/               # Example projects
│   ├── core/               # Core features
│   ├── api/                # API servers
│   ├── auth/               # Authentication
│   ├── database/           # Database usage
│   ├── storage/            # Storage examples
│   └── walkers/            # Walker patterns
│
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── e2e/                # End-to-end tests
│
├── .env.example           # Environment template
├── CHANGELOG.md           # Version history
├── CONTRIBUTING.md        # Contribution guide
├── LICENSE                # MIT license
├── MANIFEST.in            # Package manifest
├── README.md             # This file
├── pyproject.toml        # Project metadata
└── setup.py              # Package setup
```

## Contributing

### Development Setup

1. Clone repository:
```bash
git clone https://github.com/user/jvspatial.git
cd jvspatial
```

2. Set up environment:
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"      # Development install
pip install -e ".[test]"     # Test dependencies
pip install -e ".[docs]"     # Documentation tools
```

3. Configure environment:
```bash
# Copy example config
cp .env.example .env

# Edit configuration
vim .env  # Or your preferred editor
```

4. Verify setup:
```bash
# Run tests
pytest tests/

# Run linting
flake8
mypy .

# Build docs
mkdocs build
```

### Development Workflow

1. Create a feature branch:
```bash
git checkout -b feature/your-feature
```

2. Make changes and run tests:
```bash
# Run specific test file
pytest tests/test_your_feature.py -v

# Run with coverage
pytest --cov=jvspatial
```

3. Update documentation:
```bash
# Live preview
mkdocs serve
```

4. Submit changes:
```bash
# Format code
black .
isort .

# Run all checks
pre-commit run --all-files

# Commit and push
git add .
git commit -m "feat: your feature description"
git push origin feature/your-feature
```

## Contributors

<p align="center">
    <a href="https://github.com/TrueSelph/jvspatial/graphs/contributors">
        <img src="https://contrib.rocks/image?repo=TrueSelph/jvspatial" />
    </a>
</p>

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Inspired by [Jaseci](https://github.com/Jaseci-Labs/jaseci) and its Object-Spatial paradigm
- Built with [Pydantic](https://pydantic-docs.helpmanual.io/) for data validation
- REST API powered by [FastAPI](https://fastapi.tiangolo.com/)