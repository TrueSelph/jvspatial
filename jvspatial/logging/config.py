"""Configuration for logging database.

This module provides database initialization and configuration for the logging system.
"""

import logging
import os
from typing import Any, Dict, Optional, Set

from jvspatial.db import create_database, get_database_manager

logger = logging.getLogger(__name__)


def get_logging_config() -> Dict[str, Any]:
    """Get logging database configuration from environment variables and defaults.

    Returns:
        Dictionary with logging database configuration

    Environment Variables:
        JVSPATIAL_DB_LOGGING_ENABLED: Enable/disable database logging (default: "true")
        JVSPATIAL_DB_LOGGING_LEVELS: Comma-separated log levels to capture (default: "ERROR,CRITICAL")
        JVSPATIAL_DB_LOGGING_DB_NAME: Database name for logging (default: "logs")
        JVSPATIAL_DB_LOGGING_API_ENABLED: Enable/disable API endpoints (default: "true")
        JVSPATIAL_LOG_DB_TYPE: Database type (json, sqlite, mongodb, dynamodb)
        JVSPATIAL_LOG_DB_PATH: Path for file-based databases (json, sqlite)
        JVSPATIAL_LOG_DB_URI: Connection URI for MongoDB
        JVSPATIAL_LOG_DB_NAME: Database name for MongoDB
        JVSPATIAL_LOG_DB_TABLE_NAME: Table name for DynamoDB
        JVSPATIAL_LOG_DB_REGION: AWS region for DynamoDB
        JVSPATIAL_LOG_DB_ENDPOINT_URL: Custom endpoint URL (for local testing)
    """
    # Check if logging is enabled
    enabled = os.getenv("JVSPATIAL_DB_LOGGING_ENABLED", "true").lower() == "true"

    # Parse log levels
    log_levels_str = os.getenv("JVSPATIAL_DB_LOGGING_LEVELS", "ERROR,CRITICAL")
    log_level_names = [level.strip().upper() for level in log_levels_str.split(",")]

    # Convert level names to logging constants
    log_levels: Set[int] = set()
    for level_name in log_level_names:
        try:
            level = getattr(logging, level_name)
            log_levels.add(level)
        except AttributeError:
            logger.warning(f"Invalid log level: {level_name}, skipping")

    # Default to ERROR and CRITICAL if no valid levels
    if not log_levels:
        log_levels = {logging.ERROR, logging.CRITICAL}

    # Get database name
    database_name = os.getenv("JVSPATIAL_DB_LOGGING_DB_NAME", "logs")

    # Check if API endpoints are enabled
    enable_api_endpoints = (
        os.getenv("JVSPATIAL_DB_LOGGING_API_ENABLED", "true").lower() == "true"
    )

    # Get database type (defaults to same as prime DB)
    db_type = os.getenv("JVSPATIAL_LOG_DB_TYPE") or os.getenv(
        "JVSPATIAL_DB_TYPE", "json"
    )

    # Build config based on database type
    if db_type == "json":
        db_path = os.getenv("JVSPATIAL_LOG_DB_PATH", "./jvspatial_logs")
        config = {
            "enabled": enabled,
            "log_levels": log_levels,
            "log_level_names": log_level_names,
            "database_name": database_name,
            "enable_api_endpoints": enable_api_endpoints,
            "db_type": db_type,
            "db_path": db_path,
        }
    elif db_type == "sqlite":
        db_path = os.getenv(
            "JVSPATIAL_LOG_DB_PATH", "jvspatial_logs/sqlite/jvspatial_logs.db"
        )
        config = {
            "enabled": enabled,
            "log_levels": log_levels,
            "log_level_names": log_level_names,
            "database_name": database_name,
            "enable_api_endpoints": enable_api_endpoints,
            "db_type": db_type,
            "db_path": db_path,
        }
    elif db_type == "mongodb":
        db_uri = os.getenv("JVSPATIAL_LOG_DB_URI") or os.getenv(
            "JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"
        )
        db_name = os.getenv("JVSPATIAL_LOG_DB_NAME", "jvspatial_logs")
        config = {
            "enabled": enabled,
            "log_levels": log_levels,
            "log_level_names": log_level_names,
            "database_name": database_name,
            "enable_api_endpoints": enable_api_endpoints,
            "db_type": db_type,
            "db_uri": db_uri,
            "db_name": db_name,
        }
    elif db_type == "dynamodb":
        table_name = os.getenv("JVSPATIAL_LOG_DB_TABLE_NAME", "jvspatial_logs")
        region_name = os.getenv("JVSPATIAL_LOG_DB_REGION") or os.getenv(
            "JVSPATIAL_DYNAMODB_REGION", "us-east-1"
        )
        endpoint_url = os.getenv("JVSPATIAL_LOG_DB_ENDPOINT_URL") or os.getenv(
            "JVSPATIAL_DYNAMODB_ENDPOINT_URL"
        )
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        config = {
            "enabled": enabled,
            "log_levels": log_levels,
            "log_level_names": log_level_names,
            "database_name": database_name,
            "enable_api_endpoints": enable_api_endpoints,
            "db_type": db_type,
            "table_name": table_name,
            "region_name": region_name,
            "endpoint_url": endpoint_url,
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
        }
    else:
        # Fallback to JSON
        db_path = os.getenv("JVSPATIAL_LOG_DB_PATH", "./jvspatial_logs")
        config = {
            "enabled": enabled,
            "log_levels": log_levels,
            "log_level_names": log_level_names,
            "database_name": database_name,
            "enable_api_endpoints": enable_api_endpoints,
            "db_type": "json",
            "db_path": db_path,
        }

    return config


def initialize_logging_database(
    config: Optional[Dict[str, Any]] = None,
    database_name: Optional[str] = None,
    enabled: Optional[bool] = None,
    log_levels: Optional[Set[int]] = None,
    enable_api_endpoints: Optional[bool] = None,
) -> bool:
    """Initialize and register the logging database.

    This function also automatically installs the DBLogHandler to intercept
    log records at configured levels and save them to the database.

    Args:
        config: Optional configuration dictionary. If not provided, reads from environment.
        database_name: Name to register the database under (default: "logs")
        enabled: Whether logging is enabled (default: from config or True)
        log_levels: Set of log levels to capture (default: from config or {ERROR, CRITICAL})
        enable_api_endpoints: Whether to register API endpoints (default: from config or True)

    Returns:
        True if logging database was initialized, False otherwise

    Raises:
        No exceptions are raised - failures are logged and False is returned
    """
    if config is None:
        config = get_logging_config()

    # Override config with explicit parameters if provided
    if enabled is not None:
        config["enabled"] = enabled
    if database_name is not None:
        config["database_name"] = database_name
    if log_levels is not None:
        config["log_levels"] = log_levels
    if enable_api_endpoints is not None:
        config["enable_api_endpoints"] = enable_api_endpoints

    # Check if logging is enabled
    if not config.get("enabled", True):
        logger.info("Database logging is disabled")
        return False

    try:
        manager = get_database_manager()
        db_type = config["db_type"]
        db_name = config.get("database_name", "logs")

        # Create logging database based on type
        if db_type == "json":
            log_db = create_database(
                db_type="json",
                base_path=config["db_path"],
            )
        elif db_type == "sqlite":
            log_db = create_database(
                db_type="sqlite",
                db_path=config["db_path"],
            )
        elif db_type == "mongodb":
            log_db = create_database(
                db_type="mongodb",
                uri=config["db_uri"],
                db_name=config["db_name"],
            )
        elif db_type == "dynamodb":
            log_db = create_database(
                db_type="dynamodb",
                table_name=config["table_name"],
                region_name=config["region_name"],
                endpoint_url=config.get("endpoint_url"),
                aws_access_key_id=config.get("aws_access_key_id"),
                aws_secret_access_key=config.get("aws_secret_access_key"),
            )
        else:
            # Fallback to JSON
            log_db = create_database(
                db_type="json",
                base_path=config.get("db_path", "./jvspatial_logs"),
            )

        # Register database (idempotent - check if already registered)
        try:
            # Check if already registered by trying to get it
            manager.get_database(db_name)
            # If we get here, it's already registered
            logger.debug(f"Logging database '{db_name}' already registered")
        except (ValueError, KeyError):
            # Not registered yet, register it
            manager.register_database(db_name, log_db)
            logger.info(f"Logging database initialized: type={db_type}, name={db_name}")

        # Install database log handler automatically
        from jvspatial.logging.handler import install_db_log_handler

        install_db_log_handler(
            database_name=db_name,
            enabled=config.get("enabled", True),
            log_levels=config.get("log_levels"),
        )

        # Register API endpoints if enabled
        if config.get("enable_api_endpoints", True):
            try:
                from jvspatial.logging.endpoints import register_logging_endpoints

                register_logging_endpoints(database_name=db_name)
            except ImportError:
                # Endpoints module not available yet
                logger.debug("Logging endpoints not available for registration")
            except Exception as e:
                logger.warning(f"Failed to register logging endpoints: {e}")

        return True

    except Exception as e:
        # Log error but don't fail
        logger.error(f"Failed to initialize logging database: {e}", exc_info=True)
        return False


__all__ = [
    "get_logging_config",
    "initialize_logging_database",
]
