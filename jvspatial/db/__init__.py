"""Simplified database package for jvspatial.

Provides simplified database abstraction layer with direct instantiation
and essential CRUD operations. Includes multi-database management with
a prime default database for core persistence operations.
"""

from .database import Database, DatabaseError, VersionConflictError
from .factory import (
    create_database,
    create_default_database,
    get_current_database,
    get_prime_database,
    list_database_types,
    register_database_type,
    switch_database,
    unregister_database,
    unregister_database_type,
)
from .jsondb import JsonDB
from .manager import DatabaseManager, get_database_manager, set_database_manager

try:  # Optional dependency (requires aiosqlite)
    from .sqlite import SQLiteDB  # noqa: F401

    _SQLITE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when dependency missing
    SQLiteDB = None  # type: ignore[misc]
    _SQLITE_AVAILABLE = False

try:  # Optional dependency (requires Motor)
    from .mongodb import MongoDB  # noqa: F401

    _MONGODB_AVAILABLE = True
except ImportError:  # pragma: no cover - mongo optional
    MongoDB = None  # type: ignore[misc]
    _MONGODB_AVAILABLE = False

try:  # Optional dependency (requires aioboto3)
    from .dynamodb import DynamoDB  # noqa: F401

    _DYNAMODB_AVAILABLE = True
except ImportError:  # pragma: no cover - dynamodb optional
    DynamoDB = None  # type: ignore[misc]
    _DYNAMODB_AVAILABLE = False

__all__ = [
    "Database",
    "DatabaseError",
    "VersionConflictError",
    "create_database",
    "create_default_database",
    "get_prime_database",
    "get_current_database",
    "switch_database",
    "unregister_database",
    "register_database_type",
    "unregister_database_type",
    "list_database_types",
    "DatabaseManager",
    "get_database_manager",
    "set_database_manager",
    "JsonDB",
]

if _SQLITE_AVAILABLE:
    __all__.append("SQLiteDB")

if _MONGODB_AVAILABLE:
    __all__.append("MongoDB")

if _DYNAMODB_AVAILABLE:
    __all__.append("DynamoDB")
