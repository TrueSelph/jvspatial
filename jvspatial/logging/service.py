"""Base logging service for database logging.

This module provides the base logging service that handles logging to a
separate database. The service supports all log levels (DEBUG, INFO, WARNING,
ERROR, CRITICAL, and custom levels). Implementations can extend this service
to add custom functionality.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jvspatial.core.context import GraphContext
from jvspatial.db import get_database_manager
from jvspatial.logging.models import DBLog

logger = logging.getLogger(__name__)


class BaseLoggingService:
    """Base logging service for database logging.

    This service provides core logging functionality that implementations
    can extend with custom behavior. It handles:
    - Database connection management
    - Log creation and persistence (supports all log levels including custom)
    - Log querying with pagination and filtering
    - Log deletion/purging

    Implementations can extend this class to add:
    - Custom validation or filtering
    - Additional log types (e.g., interaction logs, audit logs)
    - Custom fields in logs via **kwargs
    - App-specific or tenant-specific logic
    - Custom log levels via the log_level parameter

    Example:
        Basic usage:
        ```python
        from jvspatial.logging.service import get_logging_service

        service = get_logging_service()
        await service.log_error(
            status_code=500,
            error_code="internal_error",
            message="Database connection failed",
            path="/api/users",
            method="POST",
            details={"database": "users"},
            traceback_str="Traceback..."
        )
        ```

        Extended with custom fields:
        ```python
        await service.log_error(
            status_code=422,
            error_code="validation_error",
            message="Invalid input",
            path="/api/data",
            method="POST",
            # Custom fields via kwargs
            tenant_id="tenant_123",
            request_id="req_abc",
        )
        ```
    """

    def __init__(self, database_name: str = "logs"):
        """Initialize the logging service.

        Args:
            database_name: Name of the logging database (default: "logs")
        """
        self._log_db = None
        self._database_name = database_name

    def _get_log_database(self):
        """Get the logging database instance.

        Returns:
            Database instance or None if database is not available

        Note:
            This method caches the database instance after first retrieval.
            Call initialize_logging_database() before using the service.
            If database is not found on first try, it will retry on subsequent calls.
        """
        # Always check if database is available (in case it was registered after service creation)
        try:
            manager = get_database_manager()
            registered_dbs = manager.list_databases()

            if self._database_name in registered_dbs:
                # Database is registered, get it (or refresh if already cached)
                self._log_db = manager.get_database(self._database_name)
                if self._log_db:
                    logger.debug(
                        f"Retrieved logging database: {type(self._log_db).__name__}"
                    )
                    return self._log_db

            # Database not found
            if self._log_db is None:
                # First attempt - log warning
                logger.warning(
                    f"Logging database '{self._database_name}' not found in registered databases: {registered_dbs}. "
                    f"Make sure initialize_logging_database() was called."
                )
            else:
                # Database was cached but is no longer available - log and clear cache
                logger.warning(
                    f"Logging database '{self._database_name}' no longer available. "
                    f"Registered databases: {registered_dbs}"
                )
                self._log_db = None
            return None
        except Exception as e:
            logger.error(f"Failed to get logging database: {e}", exc_info=True)
            self._log_db = None
            return None

    async def log_error(
        self,
        status_code: Optional[int] = None,
        error_code: str = "",
        message: str = "",
        path: str = "",
        method: str = "",
        details: Optional[Dict[str, Any]] = None,
        traceback_str: Optional[str] = None,
        **kwargs: Any,  # Allow extensions to pass custom fields
    ) -> None:
        """Log a message to the database.

        This method can log at any level (ERROR, WARNING, INFO, or custom levels).
        The log level is automatically determined from status_code, or can be
        explicitly set via the log_level parameter in kwargs.

        Args:
            status_code: Optional HTTP status code (None for non-HTTP logs)
            error_code: Machine-readable event/code identifier
            message: Human-readable log message
            path: Optional request path (empty for non-HTTP logs)
            method: Optional HTTP method (empty for non-HTTP logs)
            details: Additional log details
            traceback_str: Optional traceback string (for exceptions)
            **kwargs: Custom fields for extensions (stored in log_data)
                     Can include 'log_level' to override default level detection
                     (e.g., log_level="AUDIT", log_level="INTERACTION")

        Note:
            This method never raises exceptions - failures are logged but don't
            interrupt the main flow.

        Example:
            Standard error logging:
            ```python
            await service.log_error(
                status_code=500,
                error_code="database_error",
                message="Connection timeout",
                path="/api/users",
                method="POST",
                details={"timeout": 30},
                traceback_str="Traceback...",
                tenant_id="tenant_123",
                user_id="user_456"
            )
            ```

            Custom log level:
            ```python
            await service.log_error(
                error_code="audit_event",
                message="User action performed",
                log_level="AUDIT",
                details={"action": "data_export"},
                user_id="user_123"
            )
            ```
        """
        try:
            logger.debug(
                f"Attempting to log error {error_code} (status {status_code}) at {path}"
            )

            # Get logging database
            log_db = self._get_log_database()
            if not log_db:
                logger.warning(
                    f"Logging database '{self._database_name}' not available, skipping error log. "
                    f"Registered databases: {get_database_manager().list_databases() if hasattr(get_database_manager(), 'list_databases') else 'unknown'}"
                )
                return

            # Determine log level from status code if not provided
            log_level = kwargs.pop("log_level", None)
            if log_level is None:
                if status_code is None:
                    log_level = "INFO"
                elif status_code >= 500:
                    log_level = "ERROR"
                elif status_code >= 400:
                    log_level = "WARNING"
                else:
                    log_level = "INFO"

            # Build log data
            log_data: Dict[str, Any] = {
                "message": message,
                "log_level": log_level,
            }

            # Add details if provided
            if details:
                log_data["details"] = details

            # Include traceback if provided
            if traceback_str:
                log_data["traceback"] = traceback_str

            # Add custom fields from kwargs
            # This allows implementations to add their own fields without subclassing
            if kwargs:
                log_data.update(kwargs)

            # Create log entry
            log_entry = DBLog(
                status_code=status_code,
                event_code=error_code,
                log_level=log_level,
                path=path,
                method=method,
                log_data=log_data,
                logged_at=datetime.now(timezone.utc),
            )
            logger.debug(f"Created DB log entry with ID {log_entry.id}")

            # Save to logging database using separate context
            log_context = GraphContext(database=log_db)
            # Ensure indexes are created before saving
            await log_context.ensure_indexes(DBLog)
            logger.debug("Ensured indexes for DBLog")

            # Set context on the log entry so it uses the logging database
            await log_entry.set_context(log_context)
            await log_entry.save()
            logger.info(
                f"Successfully logged error {error_code} (status {status_code}) to logging database"
            )

        except Exception as e:
            # Log error but don't fail - logging should never break the main flow
            logger.error(f"Failed to log error: {e}", exc_info=True)

    async def log_custom(
        self,
        event_code: str = "",
        message: str = "",
        status_code: Optional[int] = None,
        path: str = "",
        method: str = "",
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Log a custom level message to the database.

        This is a convenience method for logging at the CUSTOM level.
        It calls log_error() with log_level="CUSTOM".

        Args:
            event_code: Machine-readable event identifier
            message: Human-readable log message
            status_code: Optional HTTP status code (None for non-HTTP logs)
            path: Optional request path (empty for non-HTTP logs)
            method: Optional HTTP method (empty for non-HTTP logs)
            details: Additional log details
            **kwargs: Custom fields for extensions (stored in log_data)

        Example:
            ```python
            await service.log_custom(
                event_code="user_action",
                message="User performed custom action",
                path="/api/custom",
                method="POST",
                details={"action": "export_data"},
                user_id="user_123",
                session_id="session_456"
            )
            ```
        """
        await self.log_error(
            status_code=status_code,
            error_code=event_code,
            message=message,
            path=path,
            method=method,
            details=details,
            log_level="CUSTOM",
            **kwargs,
        )

    async def get_error_logs(
        self,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        path: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
        **kwargs: Any,  # Allow extensions to filter by custom fields
    ) -> Dict[str, Any]:
        """Query logs with filters and pagination.

        This method can query logs at any level (ERROR, WARNING, INFO, or custom levels).

        Args:
            error_code: Optional error code filter
            status_code: Optional status code filter
            path: Optional path filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            page: Page number (1-indexed)
            page_size: Items per page
            **kwargs: Custom field filters (e.g., log_level="ERROR", log_level="AUDIT", agent_id="123")

        Returns:
            Dictionary with logs and pagination metadata:
            {
                "errors": [
                    {
                        "log_id": "...",
                        "status_code": 500,
                        "event_code": "...",
                        "message": "...",
                        "path": "...",
                        "method": "...",
                        "logged_at": "...",
                        "log_data": {...}
                    },
                    ...
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total": 100,
                    "total_pages": 2
                }
            }

        Note:
            The "errors" key is kept for backward compatibility, but the method
            returns logs of any level, not just errors.
        """
        log_db = self._get_log_database()
        if not log_db:
            return {
                "errors": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0},
            }

        try:
            # Build query - require entity type
            query: Dict[str, Any] = {
                "entity": "DBLog",
            }

            if error_code:
                query["context.event_code"] = error_code
            if status_code:
                query["context.status_code"] = status_code
            if path:
                query["context.path"] = path

            # Handle datetime filters
            if start_time or end_time:
                logged_at_filter: Dict[str, Any] = {}
                if start_time:
                    logged_at_filter["$gte"] = start_time.isoformat()
                if end_time:
                    logged_at_filter["$lte"] = end_time.isoformat()
                query["context.logged_at"] = logged_at_filter

            # Add custom field filters from kwargs
            # Handle both direct fields and nested log_data fields
            for key, value in kwargs.items():
                if value is None:
                    continue

                # Special handling for log_level (direct field)
                if key == "log_level":
                    query["context.log_level"] = value
                # Special handling for agent_id (in log_data)
                elif key == "agent_id":
                    query["context.log_data.agent_id"] = value
                # Other custom fields are stored in log_data
                else:
                    query[f"context.log_data.{key}"] = value

            # Query logs
            log_context = GraphContext(database=log_db)
            all_logs = await log_context.database.find("object", query)

            # Convert to DBLog objects and sort by logged_at descending
            log_entries: List[DBLog] = []
            for log_data in all_logs:
                try:
                    context_data = log_data.get("context", {}).copy()
                    log_id = log_data.get("id", "")

                    # Parse logged_at if it's a string
                    if "logged_at" in context_data and isinstance(
                        context_data["logged_at"], str
                    ):
                        try:
                            context_data["logged_at"] = datetime.fromisoformat(
                                context_data["logged_at"].replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            logger.warning(
                                f"Failed to parse logged_at: {context_data.get('logged_at')}"
                            )
                            context_data["logged_at"] = datetime.now(timezone.utc)

                    # Create DBLog with id passed during initialization
                    log_entry = DBLog(id=log_id, **context_data)
                    log_entries.append(log_entry)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse error log entry {log_data.get('id', 'unknown')}: {e}"
                    )
                    continue

            # Sort by logged_at descending (most recent first)
            log_entries.sort(key=lambda x: x.logged_at, reverse=True)

            # Paginate
            total_errors = len(log_entries)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_errors = log_entries[start_idx:end_idx]

            # Format response
            result_errors = []
            for log in paginated_errors:
                result_errors.append(
                    {
                        "log_id": log.id,
                        "status_code": log.status_code,
                        "event_code": log.event_code,
                        "message": log.log_data.get("message", ""),
                        "path": log.path,
                        "method": log.method,
                        "logged_at": log.logged_at.isoformat(),
                        "log_data": log.log_data,
                    }
                )

            return {
                "errors": result_errors,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total_errors,
                    "total_pages": (total_errors + page_size - 1) // page_size,
                },
            }

        except Exception as e:
            logger.error(f"Failed to get error logs: {e}", exc_info=True)
            return {
                "errors": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0},
            }

    async def purge_error_logs(
        self,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        path: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **kwargs: Any,  # Allow extensions to filter by custom fields
    ) -> Dict[str, Any]:
        """Purge logs matching criteria.

        This method can purge logs at any level (ERROR, WARNING, INFO, or custom levels).

        Args:
            error_code: Optional error code filter
            status_code: Optional status code filter
            path: Optional path filter
            start_time: Optional start time filter (delete logs before this time)
            end_time: Optional end time filter (delete logs after this time)
            **kwargs: Custom field filters (e.g., log_level="AUDIT")

        Returns:
            Dictionary with purge statistics:
            {
                "deleted": 10,
                "error": "..." (if failure)
            }

        Warning:
            This operation is permanent and cannot be undone.
        """
        log_db = self._get_log_database()
        if not log_db:
            return {"deleted": 0, "error": "Logging database not available"}

        try:
            # Build query - require entity type
            query: Dict[str, Any] = {
                "entity": "DBLog",
            }

            if error_code:
                query["context.event_code"] = error_code
            if status_code:
                query["context.status_code"] = status_code
            if path:
                query["context.path"] = path

            # Handle datetime filters
            if start_time or end_time:
                logged_at_filter: Dict[str, Any] = {}
                if start_time:
                    logged_at_filter["$gte"] = start_time.isoformat()
                if end_time:
                    logged_at_filter["$lte"] = end_time.isoformat()
                query["context.logged_at"] = logged_at_filter

            # Add custom field filters
            for key, value in kwargs.items():
                query[f"context.log_data.{key}"] = value

            # Find matching logs
            log_context = GraphContext(database=log_db)
            matching_logs = await log_context.database.find("object", query)

            # Delete each log
            deleted_count = 0
            for log_data in matching_logs:
                try:
                    log_id = log_data.get("id")
                    if log_id:
                        await log_context.database.delete("object", log_id)
                        deleted_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to delete error log {log_data.get('id')}: {e}"
                    )

            return {"deleted": deleted_count}

        except Exception as e:
            logger.error(f"Failed to purge error logs: {e}", exc_info=True)
            return {"deleted": 0, "error": str(e)}


# Singleton instance
_logging_service: Optional[BaseLoggingService] = None


def get_logging_service(database_name: str = "logs") -> BaseLoggingService:
    """Get the singleton logging service instance.

    Args:
        database_name: Name of the logging database (default: "logs")

    Returns:
        BaseLoggingService instance

    Note:
        This returns a singleton instance. All calls with the same database_name
        will return the same instance.
    """
    global _logging_service
    if _logging_service is None:
        _logging_service = BaseLoggingService(database_name=database_name)
    return _logging_service


__all__ = [
    "BaseLoggingService",
    "get_logging_service",
]
