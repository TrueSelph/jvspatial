"""
jvspatial - Enhanced async object-spatial Python library.

jvspatial is an asynchronous, object-spatial Python library designed for building
robust persistence and business logic application layers. This enhanced version
maintains the original inheritance hierarchy while providing simplified APIs.

Key Features:
- Maintained inheritance hierarchy: Object → Node → Edge/Walker
- Enhanced classes with simplified decorator support
- Simplified decorator system (@attribute, @endpoint)
- Direct instantiation (no complex factories)
- Essential CRUD operations
- Unified configuration system
- Async/await architecture

Main Exports (Import from top level):
    Core Entities (Maintaining Original Hierarchy):
        - Object: Base class for all entities
        - Node: Graph nodes with spatial data (inherits from Object)
        - Edge: Relationships between nodes (inherits from Object)
        - Walker: Graph traversal and pathfinding (inherits from Object)
        - Root: Singleton root node (inherits from Node)
        - GraphContext: Graph database context

    Decorators:
        - attribute: Unified attribute decorator (@attribute(protected=True))
        - endpoint: Unified endpoint decorator (@endpoint("/api/users"))

    API:
        - Server: FastAPI server for graph operations
        - Config: Unified configuration system

    Database & Cache:
        - Database: Simplified database interface
        - create_database: Direct database creation
        - create_cache: Direct cache creation

    Utilities:
        - serialize_datetime: Serialize datetime objects
        - deserialize_datetime: Deserialize datetime objects

Example:
    # Using enhanced classes with maintained hierarchy
    from jvspatial import Node, Walker, Server, Config, create_database

    # Node inherits from Object with all original functionality
    node = Node(id="test-node")

    # Walker inherits from Object with all original functionality
    walker = Walker()
    await walker.spawn(node)
"""

# API server
from .api import Server
from .api.decorators.route import endpoint
from .cache import create_cache

# Unified configuration
from .config import Config

# Simplified decorators
from .core.annotations import attribute
from .core.context import GraphContext

# Unified entity system
from .core.entities import Edge, Node, Object, Root, Walker

# Simplified database and cache
from .db import Database, create_database

# Utilities
from .utils.serialization import deserialize_datetime, serialize_datetime

# Version is managed in version.py
# Update version.py to release a new version
from .version import __version__

__all__ = [
    # Version
    "__version__",
    # Unified configuration
    "Config",
    # Core entities
    "Object",
    "Node",
    "Edge",
    "Walker",
    "Root",
    "GraphContext",
    # Simplified decorators
    "attribute",
    "endpoint",
    # API
    "Server",
    # Database & Cache
    "Database",
    "create_database",
    "create_cache",
    # Utilities
    "serialize_datetime",
    "deserialize_datetime",
]
