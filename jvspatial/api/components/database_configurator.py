"""Database configuration for jvspatial API.

This module provides database initialization and configuration logic,
extracted from the Server class for better separation of concerns.
"""

import inspect
import logging
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.db.manager import (
    DatabaseManager,
    get_database_manager,
    set_database_manager,
)
from jvspatial.runtime.serverless import is_serverless_mode


class DatabaseConfigurator:
    """Configurator for database initialization and GraphContext setup.

    Handles creation of the prime database and GraphContext initialization
    based on server configuration.
    """

    def __init__(self, config: Any):
        """Initialize the database configurator.

        Args:
            config: Server configuration object
        """
        self.config = config
        self._logger = logging.getLogger(__name__)

    def _resolve_db_path(self, db_path: str) -> str:
        """Resolve relative db_path when db_path_resolve is configured."""
        db_config = self.config.database
        resolve_mode = getattr(db_config, "db_path_resolve", None)
        if not resolve_mode or resolve_mode != "app":
            return db_path
        if os.path.isabs(db_path):
            return db_path
        base_dir = self._get_app_base_dir()
        if base_dir is None:
            self._logger.warning(
                "db_path_resolve='app' but could not determine app base dir; "
                "using cwd for relative path"
            )
            base_dir = os.getcwd()
        return str(Path(base_dir) / db_path)

    def _get_app_base_dir(self) -> Optional[str]:
        """Get the directory of the module that instantiated Server (app root)."""
        frame = inspect.currentframe()
        try:
            for _ in range(20):
                if frame is None:
                    break
                frame = frame.f_back
                if frame is None:
                    break
                module_name = frame.f_globals.get("__name__", "")
                if module_name and not module_name.startswith("jvspatial."):
                    fname = frame.f_globals.get("__file__")
                    if fname:
                        return os.path.dirname(os.path.abspath(fname))
        finally:
            del frame
        return None

    def _resolve_mongodb_connection(self) -> Tuple[str, str]:
        """Resolve Mongo URI and database name from server configuration only."""
        db = self.config.database
        uri = (db.db_connection_string or "").strip() or "mongodb://localhost:27017"
        db_name = (db.db_database_name or "").strip() or "jvdb"
        return uri, db_name

    def initialize_graph_context(self) -> Optional[GraphContext]:
        """Initialize GraphContext with current database configuration.

        This sets up the prime database for core persistence operations
        (authentication, session management) and creates a GraphContext
        that uses the current database from DatabaseManager.

        Returns:
            GraphContext instance if initialization succeeds, None otherwise

        Raises:
            ValueError: If database type is unsupported or configuration is invalid
        """
        # Get database type from grouped config
        db_type = self.config.database.db_type

        # If db_type is None or empty, return None
        if not db_type:
            return None

        try:
            # Create prime database based on configuration FIRST.
            prime_db = None

            if db_type == "json":
                # Check if db_path is an S3 path (not supported for file-based databases)
                default_json_path = (
                    "/tmp/jvdb" if is_serverless_mode(self.config) else "./jvdb"
                )
                db_path = self.config.database.db_path or default_json_path
                db_path = self._resolve_db_path(db_path)
                if db_path.startswith("s3://"):
                    raise ValueError(
                        f"JSON database does not support S3 paths. "
                        f"Received: {db_path}. "
                        f"Use a local path or DynamoDB (db_type='dynamodb') for cloud storage."
                    )

                # Create database with the configured db_path
                prime_db = create_database(
                    db_type="json",
                    base_path=db_path,
                )
            elif db_type == "mongodb":
                mongo_uri, mongo_db_name = self._resolve_mongodb_connection()
                prime_db = create_database(
                    db_type="mongodb",
                    uri=mongo_uri,
                    db_name=mongo_db_name,
                )
            elif db_type == "sqlite":
                # Check if db_path is an S3 path (not supported for file-based databases)
                default_sqlite_path = (
                    "/tmp/jvdb/sqlite/jvspatial.db"
                    if is_serverless_mode(self.config)
                    else "jvdb/sqlite/jvspatial.db"
                )
                db_path = self.config.database.db_path or default_sqlite_path
                db_path = self._resolve_db_path(db_path)
                if db_path.startswith("s3://"):
                    raise ValueError(
                        f"SQLite database does not support S3 paths. "
                        f"Received: {db_path}. "
                        f"Use a local path or DynamoDB (db_type='dynamodb') for cloud storage."
                    )
                prime_db = create_database(
                    db_type="sqlite",
                    db_path=db_path,
                )
            elif db_type == "dynamodb":
                prime_db = create_database(
                    db_type="dynamodb",
                    table_name=self.config.database.dynamodb_table_name or "jvspatial",
                    region_name=self.config.database.dynamodb_region or "us-east-1",
                    endpoint_url=self.config.database.dynamodb_endpoint_url,
                    aws_access_key_id=self.config.database.dynamodb_access_key_id,
                    aws_secret_access_key=self.config.database.dynamodb_secret_access_key,
                )
            else:
                raise ValueError(f"Unsupported database type: {db_type}")

            # Get or create database manager and set the prime database
            # This ensures the manager uses our configured database, not defaults

            try:
                manager = get_database_manager()
                manager.set_prime_database(prime_db)
            except (RuntimeError, AttributeError):
                # Manager doesn't exist yet, create it with our prime database
                manager = DatabaseManager(prime_database=prime_db)
                set_database_manager(manager)

            # Create GraphContext using current database (which defaults to prime)
            graph_context = GraphContext(database=manager.get_current_database())

            # Set as default context so entities can use it automatically
            set_default_context(graph_context)

            self._logger.debug(
                f"🎯 GraphContext initialized with {db_type} database (prime) and set as default"
            )

            return graph_context

        except Exception as e:
            self._logger.error(f"❌ Failed to initialize GraphContext: {e}")
            raise


__all__ = ["DatabaseConfigurator"]
