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

# MongoDB is optional and may not be available
try:
    from .mongodb import MongoDB  # noqa: F401

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
        "MongoDB",
    ]
except ImportError:
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
