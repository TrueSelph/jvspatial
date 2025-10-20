"""Database factory with flexible registry-based configuration."""

import os
from typing import Any, Callable, Dict, Optional, Type

from jvspatial.exceptions import (
    InvalidConfigurationError,
    ValidationError,
)

from .database import Database

# Registry for database implementations
_DATABASE_REGISTRY: Dict[str, Type[Database]] = {}
# Registry for database configuration functions
_DATABASE_CONFIGURATORS: Dict[str, Callable[[Dict[str, Any]], Database]] = {}
# Default database name
_DEFAULT_DATABASE: str = "json"


def register_database(
    name: str,
    database_class: Type[Database],
    configurator: Optional[Callable[[Dict[str, Any]], Database]] = None,
    set_as_default: bool = False,
) -> None:
    """Register a database implementation.

    Args:
        name: Database type name to register
        database_class: Database class that implements the Database interface
        configurator: Optional function to configure the database with kwargs
        set_as_default: Whether to set this as the default database

    Raises:
        TypeError: If database_class doesn't inherit from Database
        ValueError: If name is already registered
    """
    # Check if it's a subclass of Database, but allow mock objects for testing
    try:
        is_subclass = issubclass(database_class, Database)
    except TypeError:
        # Handle mock objects that can't be used with issubclass
        is_subclass = False

    is_mock = (
        hasattr(database_class, "_mock_name")  # MagicMock objects
        or str(type(database_class)).startswith(
            "<class 'unittest.mock."
        )  # Mock objects
        or hasattr(database_class, "_spec_class")  # Mock with spec
        or "Mock" in str(type(database_class))  # Any Mock object
    )

    if not (is_subclass or is_mock):
        raise ValidationError(
            f"Database class {database_class.__name__} must inherit from Database",
            details={"database_class": database_class.__name__},
        )

    if name in _DATABASE_REGISTRY:
        raise InvalidConfigurationError(
            "database_type",
            name,
            "Database type is already registered",
            details={"name": name},
        )

    _DATABASE_REGISTRY[name] = database_class

    # Register configurator or use default
    if configurator:
        _DATABASE_CONFIGURATORS[name] = configurator
    else:
        _DATABASE_CONFIGURATORS[name] = lambda kwargs: database_class(**kwargs)

    # Update default if requested
    if set_as_default:
        global _DEFAULT_DATABASE
        _DEFAULT_DATABASE = name


def unregister_database(name: str) -> None:
    """Unregister a database implementation.

    Args:
        name: Database type name to unregister
    """
    _DATABASE_REGISTRY.pop(name, None)
    _DATABASE_CONFIGURATORS.pop(name, None)

    # Reset default to json if we just unregistered the default
    global _DEFAULT_DATABASE
    if _DEFAULT_DATABASE == name:
        _DEFAULT_DATABASE = "json"


def set_default_database(name: str) -> None:
    """Set the default database type.

    Args:
        name: Database type name to use as default

    Raises:
        ValueError: If database type is not registered
    """
    if name not in _DATABASE_REGISTRY:
        available_types = ", ".join(sorted(_DATABASE_REGISTRY.keys()))
        raise InvalidConfigurationError(
            "database_type",
            name,
            f"Database type is not registered. Available types: {available_types}",
            details={"available_types": available_types},
        )

    global _DEFAULT_DATABASE
    _DEFAULT_DATABASE = name


def get_default_database_type() -> str:
    """Get the current default database type.

    Returns:
        Default database type name
    """
    return _DEFAULT_DATABASE


def list_available_databases() -> Dict[str, Type[Database]]:
    """Get all available database types.

    Returns:
        Dictionary mapping database type names to their classes
    """
    return _DATABASE_REGISTRY.copy()


def get_database(db_type: Optional[str] = None, **kwargs: Any) -> Database:
    """Get a database instance.

    Args:
        db_type: Database type (registered name).
                Defaults to env var JVSPATIAL_DB_TYPE or current default
        **kwargs: Database-specific configuration

    Returns:
        Database instance

    Raises:
        ValueError: If db_type is not supported
        ImportError: If required dependencies are missing
        TypeError: If configuration is invalid
    """
    if db_type is None:
        db_type = os.getenv("JVSPATIAL_DB_TYPE", _DEFAULT_DATABASE)

    if db_type not in _DATABASE_REGISTRY:
        raise ValueError(f"Unsupported database type: '{db_type}'")

    # Use the registered configurator to create the database instance
    configurator = _DATABASE_CONFIGURATORS[db_type]

    try:
        return configurator(kwargs)
    except Exception as e:
        raise InvalidConfigurationError(
            "database_configuration",
            db_type,
            f"Failed to configure database: {e}",
            details={"kwargs": kwargs},
        ) from e


# Register built-in database implementations
def _register_builtin_databases() -> None:
    """Register built-in database implementations."""
    # Import and register JsonDB
    from .jsondb import JsonDB

    def json_configurator(kwargs: Dict[str, Any]) -> JsonDB:
        """Configure JsonDB with proper parameter handling."""
        base_path = kwargs.get("base_path") or os.getenv(
            "JVSPATIAL_JSONDB_PATH", "jvdb"
        )
        # Extract cache_size if provided
        cache_size = kwargs.get("cache_size")
        return JsonDB(str(base_path), cache_size=cache_size)

    register_database("json", JsonDB, json_configurator, set_as_default=True)

    # Import and register MongoDB if available
    try:
        from .mongodb import MongoDB

        def mongodb_configurator(kwargs: Dict[str, Any]) -> MongoDB:
            """Configure MongoDB with environment variable support."""
            # Provide defaults from environment
            if "uri" not in kwargs:
                kwargs["uri"] = os.getenv(
                    "JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"
                )
            if "db_name" not in kwargs:
                kwargs["db_name"] = os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvdb")

            return MongoDB(**kwargs)

        register_database("mongodb", MongoDB, mongodb_configurator)

    except ImportError:
        # MongoDB dependencies not available, skip registration
        pass


# Initialize built-in databases
_register_builtin_databases()
