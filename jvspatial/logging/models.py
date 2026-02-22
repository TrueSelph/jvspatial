"""Log entry models for database logging.

This module provides the base DBLog model for storing log information
in a separate logging database. The model is designed to be extensible,
allowing implementations to add custom fields via the log_data dictionary.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from jvspatial.core import Object
from jvspatial.core.annotations import attribute, compound_index


@compound_index([("context.logged_at", -1)], name="logged_at")
@compound_index(
    [("context.status_code", 1), ("context.logged_at", -1)], name="status_logged_at"
)
@compound_index(
    [("context.event_code", 1), ("context.logged_at", -1)], name="event_code_logged_at"
)
@compound_index([("context.path", 1), ("context.logged_at", -1)], name="path_logged_at")
@compound_index(
    [("context.log_level", 1), ("context.logged_at", -1)], name="log_level_logged_at"
)
@compound_index(
    [("context.log_data.agent_id", 1), ("context.logged_at", -1)],
    name="agent_id_logged_at",
)
@compound_index(
    [
        ("context.log_level", 1),
        ("context.log_data.agent_id", 1),
        ("context.logged_at", -1),
    ],
    name="log_level_agent_id_logged_at",
)
class DBLog(Object):
    """Base log entry for database logging.

    This model stores comprehensive log information for debugging and traceability.
    It is designed to be extensible - implementations can add custom fields via
    the log_data dictionary without needing to subclass.

    Attributes:
        status_code: Optional HTTP status code (indexed for filtering, None for non-HTTP logs)
        event_code: Machine-readable event identifier (indexed for filtering)
        log_level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL, CUSTOM, or custom levels) (indexed)
        path: Optional request path that generated the log (indexed for filtering)
        method: Optional HTTP method (GET, POST, etc.)
        logged_at: Timestamp when logged (indexed, descending)
        log_data: Dictionary containing:
            - message: Human-readable message (required)
            - log_level: Log level name (required)
            - details: Additional details (optional)
            - traceback: Stack trace for exceptions (optional)
            - agent_id: Agent identifier for cross-referencing (optional, indexed)
            - Any custom fields added by implementations

    Example:
        Error log entry:
        ```python
        log_entry = DBLog(
            status_code=500,
            event_code="internal_error",
            log_level="ERROR",
            path="/api/users",
            method="POST",
            log_data={
                "message": "Database connection failed",
                "log_level": "ERROR",
                "details": {"database": "users", "host": "localhost"},
                "traceback": "Traceback (most recent call last)..."
            }
        )
        ```

        Info log entry:
        ```python
        log_entry = DBLog(
            status_code=200,
            event_code="action_completed",
            log_level="INFO",
            path="/api/agents/123/actions",
            method="POST",
            log_data={
                "message": "Action executed successfully",
                "log_level": "INFO",
                "agent_id": "agent_456",
                "details": {"action": "process_data", "duration": 0.5}
            }
        )
        ```

        Non-HTTP log entry (e.g., background task):
        ```python
        log_entry = DBLog(
            event_code="task_completed",
            log_level="INFO",
            log_data={
                "message": "Background task completed",
                "log_level": "INFO",
                "task_id": "task_123",
                "details": {"duration": 45.2, "items_processed": 1000}
            }
        )
        ```

        Extended with custom fields:
        ```python
        log_entry = DBLog(
            status_code=422,
            event_code="validation_warning",
            log_level="WARNING",
            path="/api/agents/123/actions",
            method="POST",
            log_data={
                "message": "Invalid action parameters",
                "log_level": "WARNING",
                "details": [...],
                # Custom fields added by implementation
                "app_id": "app_123",
                "agent_id": "agent_456",
                "user_id": "user_789",
                "session_id": "session_abc",
                "interaction_id": "interaction_xyz"
            }
        )
        ```
    """

    status_code: Optional[int] = attribute(
        indexed=True,
        default=None,
        description="Optional HTTP status code (None for non-HTTP logs)",
    )
    event_code: str = attribute(
        indexed=True,
        default="",
        description="Machine-readable event identifier",
    )
    log_level: str = attribute(
        indexed=True,
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL, CUSTOM, or custom levels)",
    )
    path: str = attribute(
        indexed=True,
        default="",
        description="Optional request path (empty for non-HTTP logs)",
    )
    method: str = attribute(
        default="",
        description="Optional HTTP method (empty for non-HTTP logs)",
    )
    logged_at: datetime = attribute(
        indexed=True,
        index_direction=-1,
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when logged",
    )
    log_data: Dict[str, Any] = attribute(
        default_factory=dict,
        description="Log payload with message, log_level, details, and optional custom fields",
    )


__all__ = [
    "DBLog",
]
