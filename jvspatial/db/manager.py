"""Database manager for handling multiple databases with a prime default database.

This module provides a centralized way to manage multiple database instances
within the same application, with automatic prime database management for
core persistence operations like authentication and session management.
"""

import os
from typing import Any, Dict, Optional

from .database import Database


class DatabaseManager:
    """Manages multiple database instances with a prime default database.

    The prime database is always used for core persistence operations
    such as authentication, session management, and system-level data.
    Additional databases can be registered and switched for application-specific data.

    Example:
        ```python
        from jvspatial.db import DatabaseManager, create_database

        # Initialize manager (creates prime database automatically)
        manager = DatabaseManager()

        # Access prime database
        prime_db = manager.get_prime_database()

        # Create and register additional database
        app_db = create_database("json", base_path="./app_data")
        manager.register_database("app", app_db)

        # Switch to app database
        manager.set_current_database("app")
        current_db = manager.get_current_database()

        # Switch back to prime
        manager.set_current_database("prime")

        # Unregister a non-prime database
        manager.unregister_database("app")
        ```
    """

    _instance: Optional["DatabaseManager"] = None
    _prime_database: Optional[Database] = None
    _databases: Dict[str, Database] = {}
    _current_database_name: str = "prime"

    def __init__(self, prime_database: Optional[Database] = None):
        """Initialize the database manager.

        Args:
            prime_database: Optional prime database instance. If not provided,
                          a default database is created based on environment.
        """
        # Initialize prime database
        if prime_database is None:
            # Create default prime database (avoid circular import)
            from .jsondb import JsonDB

            db_type = os.getenv("JVSPATIAL_DB_TYPE", "json")
            if db_type == "json":
                base_path = os.getenv("JVSPATIAL_JSONDB_PATH", "jvdb")
                self._prime_database = JsonDB(str(base_path))
            elif db_type == "mongodb":
                from .mongodb import MongoDB

                uri = os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017")
                db_name = os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvdb")
                self._prime_database = MongoDB(uri=uri, db_name=db_name)
            elif db_type == "sqlite":
                try:
                    from .sqlite import SQLiteDB
                except ImportError as exc:  # pragma: no cover - dependency missing
                    raise ImportError(
                        "aiosqlite is required for SQLite support. Install it with: pip install aiosqlite"
                    ) from exc

                db_path = os.getenv("JVSPATIAL_SQLITE_PATH", "jvdb/sqlite/jvspatial.db")
                self._prime_database = SQLiteDB(db_path=db_path)
            elif db_type == "dynamodb":
                try:
                    from .dynamodb import DynamoDB
                except ImportError as exc:  # pragma: no cover - dependency missing
                    raise ImportError(
                        "aioboto3 is required for DynamoDB support. Install it with: pip install aioboto3"
                    ) from exc

                table_name = os.getenv("JVSPATIAL_DYNAMODB_TABLE_NAME", "jvspatial")
                region_name = os.getenv("JVSPATIAL_DYNAMODB_REGION", "us-east-1")
                endpoint_url = os.getenv("JVSPATIAL_DYNAMODB_ENDPOINT_URL")
                aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
                aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
                self._prime_database = DynamoDB(
                    table_name=table_name,
                    region_name=region_name,
                    endpoint_url=endpoint_url,
                    aws_access_key_id=aws_access_key_id,
                    aws_secret_access_key=aws_secret_access_key,
                )
            else:
                # Fallback to JSON
                base_path = os.getenv("JVSPATIAL_JSONDB_PATH", "jvdb")
                self._prime_database = JsonDB(str(base_path))
        else:
            self._prime_database = prime_database

        # Register prime database
        self._databases["prime"] = self._prime_database
        self._current_database_name = "prime"

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        """Get or create the singleton database manager instance.

        Returns:
            DatabaseManager instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "DatabaseManager") -> None:
        """Set the singleton database manager instance.

        Args:
            instance: DatabaseManager instance to set
        """
        cls._instance = instance

    def get_prime_database(self) -> Database:
        """Get the prime database instance.

        The prime database is always used for core persistence operations
        such as authentication, session management, and system-level data.

        Returns:
            Prime database instance
        """
        if self._prime_database is None:
            raise RuntimeError("Prime database not initialized")
        return self._prime_database

    def get_current_database(self) -> Database:
        """Get the current active database instance.

        Returns:
            Current database instance (defaults to prime if not set)
        """
        if self._current_database_name not in self._databases:
            # Fallback to prime if current database was removed
            self._current_database_name = "prime"
        return self._databases[self._current_database_name]

    def register_database(self, name: str, database: Database) -> None:
        """Register a database instance with a name.

        Args:
            name: Database name (must not be "prime" which is reserved)
            database: Database instance to register

        Raises:
            ValueError: If name is "prime" or database is already registered
        """
        if name == "prime":
            raise ValueError("Cannot register database with name 'prime' (reserved)")
        if name in self._databases:
            raise ValueError(f"Database '{name}' is already registered")
        self._databases[name] = database

    def unregister_database(self, name: str) -> None:
        """Unregister a database instance.

        Args:
            name: Database name to unregister

        Raises:
            ValueError: If name is "prime" or database is not registered
        """
        if name == "prime":
            raise ValueError("Cannot unregister prime database")
        if name not in self._databases:
            raise ValueError(f"Database '{name}' is not registered")
        del self._databases[name]

        # If current database was removed, switch to prime
        if self._current_database_name == name:
            self._current_database_name = "prime"

    def set_current_database(self, name: str) -> None:
        """Set the current active database.

        Args:
            name: Database name to switch to

        Raises:
            ValueError: If database is not registered
        """
        if name not in self._databases:
            raise ValueError(f"Database '{name}' is not registered")
        self._current_database_name = name

    def get_database(self, name: Optional[str] = None) -> Database:
        """Get a specific database by name, or current database if not specified.

        Args:
            name: Database name (defaults to current database)

        Returns:
            Database instance

        Raises:
            ValueError: If database is not registered
        """
        if name is None:
            return self.get_current_database()
        if name not in self._databases:
            raise ValueError(f"Database '{name}' is not registered")
        return self._databases[name]

    def list_databases(self) -> Dict[str, Any]:
        """List all registered databases.

        Returns:
            Dictionary mapping database names to metadata
        """
        return {
            name: {
                "name": name,
                "is_prime": name == "prime",
                "is_current": name == self._current_database_name,
                "type": type(db).__name__,
            }
            for name, db in self._databases.items()
        }

    def reset(self) -> None:
        """Reset the database manager (for testing).

        Clears all registered databases except prime and resets current to prime.
        """
        self._databases = {"prime": self._prime_database}
        self._current_database_name = "prime"


# Global instance access
def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance.

    Returns:
        DatabaseManager instance
    """
    return DatabaseManager.get_instance()


def set_database_manager(manager: DatabaseManager) -> None:
    """Set the global database manager instance.

    Args:
        manager: DatabaseManager instance
    """
    DatabaseManager.set_instance(manager)
