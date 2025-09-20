"""Database package for jvspatial.

Provides database abstraction layer with support for multiple backends
including JSON file storage and MongoDB, with extensibility for custom
implementations.
"""

from .database import Database, VersionConflictError
from .factory import (
    get_database,
    get_default_database_type,
    list_available_databases,
    register_database,
    set_default_database,
    unregister_database,
)
from .jsondb import JsonDB
from .query import (
    QueryBuilder,
    QueryOperator,
    matches_query,
    query,
)

# MongoDB is optional and may not be available
try:
    from .mongodb import MongoDB  # noqa: F401

    __all__ = [
        "Database",
        "VersionConflictError",
        "get_database",
        "register_database",
        "unregister_database",
        "set_default_database",
        "get_default_database_type",
        "list_available_databases",
        "JsonDB",
        "MongoDB",
        "query",
        "QueryBuilder",
        "QueryOperator",
        "matches_query",
    ]
except ImportError:
    __all__ = [
        "Database",
        "VersionConflictError",
        "get_database",
        "register_database",
        "unregister_database",
        "set_default_database",
        "get_default_database_type",
        "list_available_databases",
        "JsonDB",
        "query",
        "QueryBuilder",
        "QueryOperator",
        "matches_query",
    ]
