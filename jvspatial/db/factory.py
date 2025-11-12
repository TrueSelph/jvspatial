"""Simplified database creation utilities.

This module provides simple utilities for creating database instances,
replacing the complex factory pattern with direct instantiation.
Includes integration with DatabaseManager for multi-database support.
Supports custom database registration for seamless extension.
"""

import os
from typing import Any, Callable, Dict, Optional

from .database import Database
from .jsondb import JsonDB
from .manager import get_database_manager

try:  # Optional dependency (requires aiosqlite)
    from .sqlite import SQLiteDB  # noqa: F401

    _SQLITE_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency missing
    SQLiteDB = None  # type: ignore[misc]
    _SQLITE_AVAILABLE = False

try:  # Optional dependency (requires aioboto3)
    from .dynamodb import DynamoDB  # noqa: F401

    _DYNAMODB_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency missing
    DynamoDB = None  # type: ignore[misc]
    _DYNAMODB_AVAILABLE = False

# Registry for custom database implementations
_DATABASE_REGISTRY: Dict[str, Callable[..., Database]] = {}


def register_database_type(db_type: str, factory: Callable[..., Database]) -> None:
    """Register a custom database type for use with create_database().

    This allows you to seamlessly integrate custom database implementations
    into the jvspatial factory system. Once registered, your custom database
    can be created using create_database() just like built-in types.

    Args:
        db_type: Unique identifier for the database type (e.g., 'redis', 'postgresql')
        factory: Factory function that creates a Database instance.
                 Should accept **kwargs and return a Database instance.

    Example:
        ```python
        from jvspatial.db import Database, register_database_type, create_database

        class MyCustomDB(Database):
            def __init__(self, connection_string: str):
                self.connection_string = connection_string
            # ... implement abstract methods ...

        def create_my_custom_db(**kwargs):
            return MyCustomDB(kwargs.get("connection_string", "default://"))

        # Register the custom database
        register_database_type("my_custom", create_my_custom_db)

        # Now use it like built-in types
        db = create_database("my_custom", connection_string="custom://example")
        ```

    Raises:
        ValueError: If db_type is already registered or conflicts with built-in types
    """
    if db_type in ("json", "mongodb", "sqlite", "dynamodb"):
        raise ValueError(f"Cannot register '{db_type}' - it's a built-in database type")
    if db_type in _DATABASE_REGISTRY:
        raise ValueError(
            f"Database type '{db_type}' is already registered. "
            "Use unregister_database_type() first to replace it."
        )
    _DATABASE_REGISTRY[db_type] = factory


def unregister_database_type(db_type: str) -> None:
    """Unregister a custom database type.

    Args:
        db_type: Database type identifier to unregister

    Raises:
        ValueError: If db_type is not registered or is a built-in type
    """
    if db_type in ("json", "mongodb", "sqlite", "dynamodb"):
        raise ValueError(
            f"Cannot unregister '{db_type}' - it's a built-in database type"
        )
    if db_type not in _DATABASE_REGISTRY:
        raise ValueError(f"Database type '{db_type}' is not registered")
    del _DATABASE_REGISTRY[db_type]


def list_database_types() -> Dict[str, str]:
    """List all available database types (built-in and registered).

    Returns:
        Dictionary mapping database type names to their descriptions
    """
    types = {
        "json": "JSON file-based database (built-in)",
        "mongodb": "MongoDB database (built-in)",
    }

    if _SQLITE_AVAILABLE:
        types["sqlite"] = "SQLite database (built-in)"
    else:
        types["sqlite"] = "SQLite database (requires aiosqlite)"

    if _DYNAMODB_AVAILABLE:
        types["dynamodb"] = "DynamoDB database (built-in, for AWS Lambda)"
    else:
        types["dynamodb"] = "DynamoDB database (requires aioboto3)"
    for db_type, factory in _DATABASE_REGISTRY.items():
        types[db_type] = f"Custom database: {factory.__name__}"
    return types


def create_database(
    db_type: str = "json",
    register: bool = False,
    name: Optional[str] = None,
    **kwargs: Any,
) -> Database:
    """Create a database instance with direct instantiation.

    Supports both built-in database types ('json', 'sqlite', 'mongodb', 'dynamodb') and custom
    database types registered via register_database_type().

    Args:
        db_type: Database type ('json', 'mongodb', 'sqlite', 'dynamodb', or a registered custom type)
        register: If True, register the database with DatabaseManager
        name: Database name for registration (required if register=True)
        **kwargs: Database-specific configuration passed to the database constructor

    Returns:
        Database instance

    Examples:
        # JSON database (not registered)
        db = create_database("json", base_path="./data")

        # MongoDB database (registered with manager)
        db = create_database("mongodb", uri="mongodb://localhost:27017",
                            register=True, name="app_db")

        # SQLite database (file-based storage)
        db = create_database("sqlite", db_path="./data/app.db")

        # DynamoDB database (AWS Lambda serverless)
        db = create_database("dynamodb", table_name="myapp", region_name="us-east-1")

        # Custom database (after registration)
        db = create_database("my_custom", connection_string="custom://",
                            register=True, name="custom_db")

        # Create and auto-register as current database
        db = create_database("json", base_path="./app_data",
                            register=True, name="app")
        manager = get_database_manager()
        manager.set_current_database("app")

    Raises:
        ValueError: If db_type is not supported or registration fails
    """
    # Check built-in types first
    db: Database
    if db_type == "json":
        base_path = kwargs.get("base_path") or os.getenv(
            "JVSPATIAL_JSONDB_PATH", "jvdb"
        )
        db = JsonDB(str(base_path))

    elif db_type == "mongodb":
        from .mongodb import MongoDB

        # Provide defaults from environment
        if "uri" not in kwargs:
            kwargs["uri"] = os.getenv(
                "JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"
            )
        if "db_name" not in kwargs:
            kwargs["db_name"] = os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvdb")

        db = MongoDB(**kwargs)

    elif db_type == "sqlite":
        if not _SQLITE_AVAILABLE:
            raise ImportError(
                "aiosqlite is required for SQLite support. Install it with: pip install aiosqlite"
            )

        sqlite_kwargs = kwargs.copy()
        db_path = (
            sqlite_kwargs.pop("db_path", None)
            or sqlite_kwargs.pop("path", None)
            or os.getenv("JVSPATIAL_SQLITE_PATH", "jvdb/sqlite/jvspatial.db")
        )
        db = SQLiteDB(db_path=db_path, **sqlite_kwargs)

    elif db_type == "dynamodb":
        if not _DYNAMODB_AVAILABLE:
            raise ImportError(
                "aioboto3 is required for DynamoDB support. Install it with: pip install aioboto3"
            )

        from .dynamodb import DynamoDB

        # Provide defaults from environment
        dynamodb_kwargs = kwargs.copy()
        if "table_name" not in dynamodb_kwargs:
            dynamodb_kwargs["table_name"] = os.getenv(
                "JVSPATIAL_DYNAMODB_TABLE_NAME", "jvspatial"
            )
        if "region_name" not in dynamodb_kwargs:
            dynamodb_kwargs["region_name"] = os.getenv(
                "JVSPATIAL_DYNAMODB_REGION", "us-east-1"
            )
        if "endpoint_url" not in dynamodb_kwargs:
            dynamodb_kwargs["endpoint_url"] = os.getenv(
                "JVSPATIAL_DYNAMODB_ENDPOINT_URL"
            )
        if "aws_access_key_id" not in dynamodb_kwargs:
            dynamodb_kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID")
        if "aws_secret_access_key" not in dynamodb_kwargs:
            dynamodb_kwargs["aws_secret_access_key"] = os.getenv(
                "AWS_SECRET_ACCESS_KEY"
            )

        db = DynamoDB(**dynamodb_kwargs)

    # Check registered custom types
    elif db_type in _DATABASE_REGISTRY:
        factory = _DATABASE_REGISTRY[db_type]
        db = factory(**kwargs)

    else:
        available = ", ".join(list_database_types().keys())
        raise ValueError(
            f"Unsupported database type: '{db_type}'. " f"Available types: {available}"
        )

    # Register with manager if requested
    if register:
        if name is None:
            raise ValueError("Database name is required when register=True")
        manager = get_database_manager()
        manager.register_database(name, db)

    return db


def create_default_database() -> Database:
    """Create the default database based on environment.

    This creates the prime database used for core persistence operations
    such as authentication and session management.

    Returns:
        Configured database instance (prime database)
    """
    manager = get_database_manager()
    return manager.get_prime_database()


def get_prime_database() -> Database:
    """Get the prime database instance.

    The prime database is always used for core persistence operations
    such as authentication, session management, and system-level data.

    Returns:
        Prime database instance
    """
    manager = get_database_manager()
    return manager.get_prime_database()


def get_current_database() -> Database:
    """Get the current active database instance.

    Returns:
        Current database instance (defaults to prime if not set)
    """
    manager = get_database_manager()
    return manager.get_current_database()


def switch_database(name: str) -> Database:
    """Switch to a different database by name.

    Args:
        name: Database name to switch to

    Returns:
        The database instance that was switched to

    Raises:
        ValueError: If database is not registered
    """
    manager = get_database_manager()
    manager.set_current_database(name)
    return manager.get_current_database()


def unregister_database(name: str) -> None:
    """Unregister a non-prime database instance.

    Removes a database from the DatabaseManager. If the database being
    removed is the current database, automatically switches back to prime.

    Args:
        name: Database name to unregister

    Raises:
        ValueError: If name is "prime" (cannot unregister prime database)
                    or database is not registered

    Example:
        ```python
        from jvspatial.db import create_database, unregister_database

        # Register a database
        db = create_database("json", base_path="./temp_data", register=True, name="temp")

        # Later, unregister it
        unregister_database("temp")
        ```
    """
    manager = get_database_manager()
    manager.unregister_database(name)
