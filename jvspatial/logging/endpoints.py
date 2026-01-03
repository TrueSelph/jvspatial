"""Authenticated API endpoints for querying database logs.

This module provides REST API endpoints for querying logs with pagination,
category filtering, date range filtering, and agent_id cross-referencing.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Query
from pydantic import BaseModel, Field

from jvspatial.api.decorators.route import endpoint
from jvspatial.logging.service import get_logging_service

logger = logging.getLogger(__name__)


# Response models
class LogEntry(BaseModel):
    """Log entry response model."""

    log_id: str = Field(..., description="Unique log entry identifier")
    log_level: str = Field(
        ...,
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL, or custom levels)",
    )
    status_code: int = Field(..., description="HTTP status code")
    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Log message")
    path: str = Field(..., description="Request path")
    method: str = Field(..., description="HTTP method")
    agent_id: Optional[str] = Field(None, description="Agent ID for cross-referencing")
    logged_at: str = Field(..., description="ISO timestamp when logged")
    error_data: Dict[str, Any] = Field(..., description="Additional log data")


class PaginationInfo(BaseModel):
    """Pagination information."""

    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")


class LogsResponse(BaseModel):
    """Response model for logs query."""

    logs: List[LogEntry] = Field(..., description="List of log entries")
    pagination: PaginationInfo = Field(..., description="Pagination information")


@endpoint("/logs", methods=["GET"], auth=True)
async def get_logs(
    category: Optional[str] = Query(  # noqa: B008
        None,
        description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL, or custom levels)",
    ),
    start_date: Optional[str] = Query(  # noqa: B008
        None,
        description="Start date (ISO format, e.g., 2024-01-01T00:00:00Z)",
    ),
    end_date: Optional[str] = Query(  # noqa: B008
        None,
        description="End date (ISO format, e.g., 2024-01-31T23:59:59Z)",
    ),
    agent_id: Optional[str] = Query(  # noqa: B008
        None,
        description="Filter by agent ID for cross-referencing",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),  # noqa: B008
    page_size: int = Query(  # noqa: B008
        50, ge=1, le=200, description="Items per page (max 200)"
    ),
) -> LogsResponse:
    """Query logs with filters and pagination.

    This endpoint requires authentication and allows querying logs with various
    filters including log level category, date range, and agent_id for cross-referencing.

    Args:
        category: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        start_date: ISO format start date
        end_date: ISO format end date
        agent_id: Filter by agent_id for cross-referencing
        page: Page number (1-indexed)
        page_size: Items per page (max 200)

    Returns:
        LogsResponse with paginated log entries and metadata

    Example:
        GET /api/logs?category=ERROR&page=1&page_size=50
        GET /api/logs?agent_id=agent_123&start_date=2024-01-01T00:00:00Z
    """
    try:
        # Get logging service
        service = get_logging_service()

        # Parse dates if provided
        start_time = None
        end_time = None
        if start_date:
            try:
                start_time = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Invalid start_date format: {start_date}")

        if end_date:
            try:
                end_time = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Invalid end_date format: {end_date}")

        # Query logs using the service
        # Note: The service needs to be enhanced to support log_level filtering
        result = await service.get_error_logs(
            error_code=None,
            status_code=None,
            path=None,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
            # Pass category and agent_id as kwargs for filtering
            log_level=category.upper() if category else None,
            agent_id=agent_id,
        )

        # Transform error logs to log entries
        log_entries: List[LogEntry] = []
        for error in result.get("errors", []):
            error_data = error.get("error_data", {})
            log_entry = LogEntry(
                log_id=error["log_id"],
                log_level=error_data.get("log_level", "ERROR"),
                status_code=error["status_code"],
                error_code=error["error_code"],
                message=error.get("message", ""),
                path=error["path"],
                method=error["method"],
                agent_id=error_data.get("agent_id"),
                logged_at=error["logged_at"],
                error_data=error_data,
            )
            log_entries.append(log_entry)

        # Build pagination info
        pagination_data = result.get("pagination", {})
        pagination = PaginationInfo(
            page=pagination_data.get("page", page),
            page_size=pagination_data.get("page_size", page_size),
            total=pagination_data.get("total", 0),
            total_pages=pagination_data.get("total_pages", 0),
        )

        return LogsResponse(logs=log_entries, pagination=pagination)

    except Exception as e:
        logger.error(f"Failed to query logs: {e}", exc_info=True)
        # Return empty result on error
        return LogsResponse(
            logs=[],
            pagination=PaginationInfo(
                page=page, page_size=page_size, total=0, total_pages=0
            ),
        )


def register_logging_endpoints(database_name: str = "logs") -> None:
    """Register logging endpoints with the server.

    This function is called by initialize_logging_database() to register
    the logging query endpoints with the server if API endpoints are enabled.

    Args:
        database_name: Name of the logging database (for future use)

    Note:
        Endpoints are automatically registered through the @endpoint decorator
        when imported by the server context. This function serves as a
        placeholder for future explicit registration logic if needed.
    """
    logger.debug(f"Logging endpoints registered for database '{database_name}'")


__all__ = [
    "get_logs",
    "register_logging_endpoints",
    "LogEntry",
    "LogsResponse",
    "PaginationInfo",
]
