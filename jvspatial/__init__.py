"""
jvspatial - Async object-spatial Python library.

jvspatial is an asynchronous, object-spatial Python library designed for building
robust persistence and business logic application layers. Inspired by Jaseci's
object-spatial paradigm and leveraging Python's async capabilities.

Key Features:
- Typed node/edge modeling via Pydantic
- Precise control over graph traversal
- Multi-backend persistence (JSON, MongoDB, etc.)
- Integrated REST API endpoints
- Async/await architecture

Main Exports (Import from top level):
    Core Entities:
        - Object: Base class for all entities
        - Node: Graph nodes with spatial data
        - Edge: Relationships between nodes
        - Walker: Graph traversal and pathfinding
        - Root: Singleton root node
        - GraphContext: Graph database context

    Decorators:
        - on_visit: Register visit hooks for graph traversal
        - on_exit: Register exit hooks for graph traversal
        - on_emit: Register event handlers

    API:
        - Server: FastAPI server for graph operations
        - ServerConfig: Server configuration

    Database & Cache:
        - Database: Database interface
        - get_database: Database factory function
        - Query: Query builder
        - get_cache: Cache factory function
        - CacheBackend: Cache interface

    Utilities:
        - serialize_datetime: Serialize datetime objects
        - deserialize_datetime: Deserialize datetime objects

    Modules:
        - exceptions: Custom exception classes
        - storage: File storage interfaces

Example:
    >>> from jvspatial import Object, Node, Edge, Walker, Server
    >>>
    >>> # Create a node
    >>> node = Node()
    >>>
    >>> # Create a walker
    >>> walker = Walker()
    >>>
    >>> # Create a server
    >>> server = Server(title="My API", db_type="json", db_path="./data")
"""

__version__ = "0.2.0"

# Modules
from . import exceptions, storage

# API server
from .api import (
    Server,
    ServerConfig,
)
from .cache import (
    CacheBackend,
    get_cache_backend,
)

# Decorators
# Core entities
from .core import (
    Edge,
    GraphContext,
    Node,
    Object,
    Root,
    Walker,
    on_emit,
    on_exit,
    on_visit,
)

# Database & Cache
from .db import (
    Database,
    QueryBuilder,
    get_database,
)

# Utilities
from .utils.serialization import (
    deserialize_datetime,
    serialize_datetime,
)

__all__ = [
    # Version
    "__version__",
    # Core entities
    "Object",
    "Node",
    "Edge",
    "Walker",
    "Root",
    "GraphContext",
    # Decorators
    "on_visit",
    "on_exit",
    "on_emit",
    # API
    "Server",
    "ServerConfig",
    # Database & Cache
    "Database",
    "get_database",
    "QueryBuilder",
    "get_cache_backend",
    "CacheBackend",
    # Utilities
    "serialize_datetime",
    "deserialize_datetime",
    # Modules
    "exceptions",
    "storage",
]
