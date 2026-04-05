"""Configuration for logging database.

This module provides database initialization and configuration for the logging system.
"""

import logging
from typing import Any, Dict, Optional, Set

from jvspatial.db import create_database, get_database_manager
from jvspatial.env import env, parse_bool_basic

logger = logging.getLogger(__name__)


def get_logging_config() -> Dict[str, Any]:
    """Get logging database configuration from environment variables and defaults.

    Returns:
        Dictionary with logging database configuration

    Environment Variables:
        See :mod:`jvspatial.env` (JVSPATIAL_DB_LOGGING_*, JVSPATIAL_LOG_DB_*).
    """
    enabled = env("JVSPATIAL_DB_LOGGING_ENABLED", default=True, parse=parse_bool_basic)

    log_levels_str = env("JVSPATIAL_DB_LOGGING_LEVELS", default="ERROR,CRITICAL")
    log_level_names = [level.strip().upper() for level in log_levels_str.split(",")]

    log_levels: Set[int] = set()
    for level_name in log_level_names:
        try:
            level = getattr(logging, level_name)
            log_levels.add(level)
        except AttributeError:
            logger.warning(f"Invalid log level: {level_name}, skipping")

    if not log_levels:
        log_levels = {logging.ERROR, logging.CRITICAL}

    database_name = env("JVSPATIAL_DB_LOGGING_DB_NAME", default="logs")
    enable_api_endpoints = env(
        "JVSPATIAL_DB_LOGGING_API_ENABLED", default=True, parse=parse_bool_basic
    )

    db_type = env("JVSPATIAL_LOG_DB_TYPE") or env("JVSPATIAL_DB_TYPE", default="json")

    if db_type == "json":
        log_db_path_raw = env("JVSPATIAL_LOG_DB_PATH")
        db_path = log_db_path_raw or "./jvspatial_logs"
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
        log_db_path_raw = env("JVSPATIAL_LOG_DB_PATH")
        db_path = log_db_path_raw or "jvspatial_logs/sqlite/jvspatial_logs.db"
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
        db_uri = env("JVSPATIAL_LOG_DB_URI") or env(
            "JVSPATIAL_MONGODB_URI", default="mongodb://localhost:27017"
        )
        db_name = env("JVSPATIAL_LOG_DB_NAME", default="jvspatial_logs")
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
        table_name = env("JVSPATIAL_LOG_DB_TABLE_NAME", default="jvspatial_logs")
        region_name = env("JVSPATIAL_LOG_DB_REGION") or env(
            "JVSPATIAL_DYNAMODB_REGION", default="us-east-1"
        )
        endpoint_url = env("JVSPATIAL_LOG_DB_ENDPOINT_URL") or env(
            "JVSPATIAL_DYNAMODB_ENDPOINT_URL"
        )
        aws_access_key_id = env("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = env("AWS_SECRET_ACCESS_KEY")
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
        db_path = env("JVSPATIAL_LOG_DB_PATH") or "./jvspatial_logs"
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

    if enabled is not None:
        config["enabled"] = enabled
    if database_name is not None:
        config["database_name"] = database_name
    if log_levels is not None:
        config["log_levels"] = log_levels
    if enable_api_endpoints is not None:
        config["enable_api_endpoints"] = enable_api_endpoints

    if not config.get("enabled", True):
        logger.info("Database logging is disabled")
        return False

    try:
        manager = get_database_manager()
        db_type = config["db_type"]
        db_name = config.get("database_name", "logs")

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
            log_db = create_database(
                db_type="json",
                base_path=config.get("db_path", "./jvspatial_logs"),
            )

        try:
            manager.get_database(db_name)
            logger.debug(f"Logging database '{db_name}' already registered")
        except (ValueError, KeyError):
            manager.register_database(db_name, log_db)
            logger.info(f"Logging database initialized: type={db_type}, name={db_name}")

        from jvspatial.logging.handler import install_db_log_handler

        install_db_log_handler(
            database_name=db_name,
            enabled=config.get("enabled", True),
            log_levels=config.get("log_levels"),
        )

        if config.get("enable_api_endpoints", True):
            try:
                from jvspatial.logging.endpoints import register_logging_endpoints

                register_logging_endpoints(database_name=db_name)
            except ImportError:
                logger.debug("Logging endpoints not available for registration")
            except Exception as e:
                logger.warning(f"Failed to register logging endpoints: {e}")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize logging database: {e}", exc_info=True)
        return False


__all__ = [
    "get_logging_config",
    "initialize_logging_database",
]
