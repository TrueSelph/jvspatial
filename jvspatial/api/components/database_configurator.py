"""Database configuration for jvspatial API.

This module provides database initialization and configuration logic,
extracted from the Server class for better separation of concerns.
"""

import logging
from typing import Any, Optional

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.db.manager import (
    DatabaseManager,
    get_database_manager,
    set_database_manager,
)


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
            # Create prime database based on configuration FIRST
            # This ensures we use the server's configuration, not default environment variables
            prime_db = None

            if db_type == "json":
                # Check if db_path is an S3 path (not supported for file-based databases)
                db_path = self.config.database.db_path or "./jvdb"
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
                prime_db = create_database(
                    db_type="mongodb",
                    uri=self.config.database.db_connection_string
                    or "mongodb://localhost:27017",
                    db_name=self.config.database.db_database_name or "jvdb",
                )
            elif db_type == "sqlite":
                # Check if db_path is an S3 path (not supported for file-based databases)
                db_path = self.config.database.db_path or "jvdb/sqlite/jvspatial.db"
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
                # Update prime database if manager already exists
                manager._prime_database = prime_db
                manager._databases["prime"] = prime_db
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
