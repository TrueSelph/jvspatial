"""Database logging handler for automatic log persistence.

This handler intercepts log records at configurable levels and automatically
saves them to the DBLog database. Applications can simply use the standard
logger with optional 'details' in the extra parameter.
"""

import asyncio
import contextlib
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from jvspatial.core.context import GraphContext
from jvspatial.db import get_database_manager
from jvspatial.logging.models import DBLog

logger = logging.getLogger(__name__)


class DBLogHandler(logging.Handler):
    """Logging handler that automatically saves log records to database.

    This handler intercepts log records at configurable levels and saves them
    to the DBLog database. Applications can use the standard logger with
    optional 'details' parameter:

    Example:
        ```python
        import logging

        logger = logging.getLogger(__name__)

        # Simple error logging
        logger.error("Database connection failed")

        # Info level logging (if configured)
        logger.info("User logged in", extra={"agent_id": "agent_123"})

        # With details
        logger.error(
            "Validation failed",
            extra={
                "details": {"field": "email", "value": "invalid"},
                "status_code": 422,
                "event_code": "validation_error",
                "path": "/api/users",
                "method": "POST",
                "agent_id": "agent_456"
            }
        )

        # With exception
        try:
            risky_operation()
        except Exception:
            logger.error("Operation failed", exc_info=True)

        # With custom log levels
        from jvspatial.logging.custom_levels import add_custom_log_level
        AUDIT = add_custom_log_level("AUDIT", 35)
        logger.audit("User action performed", extra={"user_id": "user_123"})
        ```

    The handler extracts:
    - Message from log record
    - Log level from record (including custom levels)
    - Exception/traceback from exc_info
    - status_code, event_code (or error_code/code), path, method from extra
    - agent_id from extra (for cross-referencing)
    - Any other fields from extra (stored in log_data)

    Note:
        Custom log levels are fully supported. Use add_custom_log_level() to register
        custom levels, then include them in the log_levels parameter when creating
        the handler.
    """

    def __init__(
        self,
        database_name: str = "logs",
        enabled: bool = True,
        log_levels: Optional[Set[int]] = None,
    ):
        """Initialize the database log handler.

        Args:
            database_name: Name of the logging database (default: "logs")
            enabled: Whether the handler is enabled (default: True)
            log_levels: Set of log levels to capture (default: {ERROR, CRITICAL})
        """
        # Default to ERROR and CRITICAL if no levels specified
        if log_levels is None:
            log_levels = {logging.ERROR, logging.CRITICAL}

        # Set handler level to the minimum of specified levels
        min_level = min(log_levels) if log_levels else logging.ERROR
        super().__init__(level=min_level)

        self._database_name = database_name
        self._enabled = enabled
        self._log_levels = log_levels
        self._log_db = None

    def _get_log_database(self):
        """Get the logging database instance.

        Returns:
            Database instance or None if not available
        """
        if self._log_db is None:
            try:
                manager = get_database_manager()
                registered_dbs = manager.list_databases()

                if self._database_name in registered_dbs:
                    self._log_db = manager.get_database(self._database_name)
                    return self._log_db
                else:
                    logger.debug(
                        f"DB log database '{self._database_name}' not found. "
                        f"Registered databases: {registered_dbs}"
                    )
                    return None
            except Exception as e:
                logger.debug(f"Failed to get DB log database: {e}")
                return None
        return self._log_db

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the database.

        This method is called by the logging system for configured log levels.
        It extracts information from the log record and saves it to the database
        asynchronously (fire-and-forget).

        Args:
            record: The log record to process
        """
        try:
            # Check if handler is enabled
            if not self._enabled:
                return

            # Check if this log level should be captured
            if record.levelno not in self._log_levels:
                return

            # Get database
            log_db = self._get_log_database()
            if not log_db:
                # Database not available, skip silently
                return

            # Extract log information from record
            message = record.getMessage()
            log_level = record.levelname  # DEBUG, INFO, WARNING, ERROR, CRITICAL

            # Extract fields from record attributes
            # Python logging adds all fields from the 'extra' parameter as attributes
            # directly on the LogRecord object. For example:
            #   logger.log(level, "message", extra={"app_id": "app_123", "user_id": "user_456"})
            # Results in: record.app_id = "app_123", record.user_id = "user_456"
            #
            # We extract these by checking record.__dict__ for non-standard attributes.
            # Also check record.extra dict if it exists (defensive check)
            extra_dict = getattr(record, "extra", {}) or {}

            # Extract from record attributes first, then fall back to extra dict
            status_code = getattr(record, "status_code", None) or extra_dict.get(
                "status_code"
            )
            # Support error_code, event_code, and code field names (all are valid)
            event_code = (
                getattr(record, "error_code", None)
                or getattr(record, "event_code", None)
                or getattr(record, "code", None)
                or extra_dict.get("error_code")
                or extra_dict.get("event_code")
                or extra_dict.get("code", "")
            )
            path = getattr(record, "path", "") or extra_dict.get("path", "")
            method = getattr(record, "method", "") or extra_dict.get("method", "")
            agent_id = getattr(record, "agent_id", "") or extra_dict.get("agent_id", "")

            # Extract details from record attributes or extra dict
            details = getattr(record, "details", None) or extra_dict.get("details")

            # Extract traceback if exception info is available
            traceback_str = None
            if record.exc_info:
                traceback_str = "".join(traceback.format_exception(*record.exc_info))

            # Build log_data with message and any additional fields from record
            log_data: Dict[str, Any] = {
                "message": message,
                "log_level": log_level,
            }

            if details:
                log_data["details"] = details

            if traceback_str:
                log_data["traceback"] = traceback_str

            # Add agent_id to log_data if present
            if agent_id:
                log_data["agent_id"] = agent_id

            # Extract all custom fields from record attributes
            # Python logging adds fields from 'extra' parameter as attributes on the LogRecord
            # Standard LogRecord attributes that we should exclude
            standard_attrs = {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "extra",
                "getMessage",
                "__dict__",
                "__class__",
                "__module__",
                "__doc__",
                "__weakref__",
                "__repr__",
                "__str__",
                "__hash__",
                "__eq__",
                "__ne__",
                "__lt__",
                "__le__",
                "__gt__",
                "__ge__",
            }

            # Fields we've already extracted and added to log_data
            already_handled = {
                "status_code",
                "error_code",
                "event_code",
                "code",
                "path",
                "method",
                "details",
                "agent_id",
            }

            # Get all custom attributes from the record (these come from 'extra' parameter)
            # Use __dict__ for efficiency and to get actual attributes, not methods
            if hasattr(record, "__dict__"):
                for attr_name, attr_value in record.__dict__.items():
                    # Skip standard attributes and already handled fields
                    if (
                        attr_name not in standard_attrs
                        and attr_name not in already_handled
                        and not callable(attr_value)
                    ):
                        log_data[attr_name] = attr_value

            # Also check extra_dict (defensive check if record.extra exists as dict)
            if extra_dict and isinstance(extra_dict, dict):
                for key, value in extra_dict.items():
                    if key not in already_handled and key not in log_data:
                        log_data[key] = value

            # Create log entry
            log_entry = DBLog(
                status_code=status_code,
                event_code=event_code,
                log_level=log_level,
                path=path,
                method=method,
                log_data=log_data,
                logged_at=datetime.now(timezone.utc),
            )

            # Save to database asynchronously (fire-and-forget)
            async def save_log():
                """Save log entry to database."""
                try:
                    log_context = GraphContext(database=log_db)
                    await log_context.ensure_indexes(DBLog)
                    await log_entry.set_context(log_context)
                    await log_entry.save()
                except Exception as e:
                    # Log error but don't fail - logging should never break the main flow
                    logger.debug(f"Failed to save log to database: {e}")

            # Create task for async save (fire-and-forget)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Event loop is running, create task
                    asyncio.create_task(save_log())
                else:
                    # No event loop running, run synchronously
                    asyncio.run(save_log())
            except RuntimeError:
                # No event loop available, try to create one
                with contextlib.suppress(Exception):
                    asyncio.run(save_log())

        except Exception as e:
            # Never let logging failures break the application
            logger.debug(f"Error in DBLogHandler.emit: {e}")


# Store original exception hook
_original_excepthook = sys.excepthook
_exception_hook_installed = False


def install_exception_hook() -> bool:
    """Install exception hook to catch uncaught exceptions.

    This patches sys.excepthook to route uncaught exceptions through the
    logging system at CRITICAL level, allowing them to be captured by
    the DBLogHandler if configured.

    Returns:
        True if hook was installed, False if already installed
    """
    global _exception_hook_installed

    if _exception_hook_installed:
        return False

    def exception_hook(exc_type, exc_value, exc_traceback):
        """Custom exception hook that logs to logging system."""
        # Skip KeyboardInterrupt to allow Ctrl+C
        if issubclass(exc_type, KeyboardInterrupt):
            _original_excepthook(exc_type, exc_value, exc_traceback)
            return

        # Log the exception at CRITICAL level
        logger.critical(
            f"Uncaught exception: {exc_type.__name__}: {exc_value}",
            exc_info=(exc_type, exc_value, exc_traceback),
            extra={
                "event_code": "uncaught_exception",
                "status_code": 500,
            },
        )

        # Call original hook
        _original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = exception_hook
    _exception_hook_installed = True
    logger.info("Exception hook installed for uncaught exceptions")
    return True


def install_db_log_handler(
    database_name: str = "logs",
    enabled: bool = True,
    log_levels: Optional[Set[int]] = None,
) -> bool:
    """Install the database log handler to the root logger.

    Args:
        database_name: Name of the logging database (default: "logs")
        enabled: Whether the handler is enabled (default: True)
        log_levels: Set of log levels to capture (default: {ERROR, CRITICAL})

    Returns:
        True if handler was installed, False if already exists
    """
    if not enabled:
        logger.debug("DBLogHandler installation skipped (disabled)")
        return False

    root_logger = logging.getLogger()

    # Check if handler already exists
    handler_exists = any(
        isinstance(h, DBLogHandler) and h._database_name == database_name
        for h in root_logger.handlers
    )

    if not handler_exists:
        handler = DBLogHandler(
            database_name=database_name,
            enabled=enabled,
            log_levels=log_levels,
        )
        root_logger.addHandler(handler)

        # Convert log levels to names for logging
        if log_levels:
            level_names = [logging.getLevelName(level) for level in sorted(log_levels)]
            logger.info(
                f"DBLogHandler installed for database '{database_name}' "
                f"(levels: {', '.join(level_names)})"
            )
        else:
            logger.info(f"DBLogHandler installed for database '{database_name}'")

        # Install exception hook to catch uncaught exceptions
        install_exception_hook()

        return True

    return False


__all__ = [
    "DBLogHandler",
    "install_db_log_handler",
    "install_exception_hook",
]
