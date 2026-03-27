"""Authenticated API endpoints for querying database logs.

This module provides REST API endpoints for querying logs with pagination,
category filtering, date range filtering, and optional MongoDB-style filter.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from jvspatial.api.decorators.route import endpoint
from jvspatial.logging.filter_utils import validate_log_filter
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
    event_code: str = Field(..., description="Machine-readable event identifier")
    message: str = Field(..., description="Log message")
    path: str = Field(..., description="Request path")
    method: str = Field(..., description="HTTP method")
    logged_at: str = Field(..., description="ISO timestamp when logged")
    log_data: Dict[str, Any] = Field(..., description="Additional log data")


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


@endpoint("/logs", methods=["GET"], auth=True, roles=["admin"], tags=["App"])
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
    filter: Optional[str] = Query(  # noqa: B008
        None,
        description='MongoDB-style filter JSON (e.g. {"context.log_level":"ERROR","context.log_data.user_id":"123"})',
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),  # noqa: B008
    page_size: int = Query(  # noqa: B008
        50, ge=1, le=200, description="Items per page (max 200)"
    ),
) -> LogsResponse:
    """Query logs with filters and pagination.

    Retrieves paginated log entries with optional filtering by log level category,
    date range, and MongoDB-style filter. Requires authentication.

    **Query Parameters:**
    - `category`: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL, or custom levels)
    - `start_date`: Start date in ISO format (e.g., `2024-01-01T00:00:00Z`)
    - `end_date`: End date in ISO format (e.g., `2024-01-31T23:59:59Z`)
    - `filter`: MongoDB-style filter JSON. All keys must use `context.` prefix.
      Supports operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $regex, $exists, $and, $or
    - `page`: Page number (1-indexed, default: 1)
    - `page_size`: Items per page (1-200, default: 50)

    **Returns:**
    - `LogsResponse` containing paginated log entries and pagination metadata

    **Examples:**
    ```
    GET /api/logs?category=ERROR&page=1&page_size=50
    GET /api/logs?filter={"context.log_level":"ERROR","context.log_data.user_id":"123"}
    GET /api/logs?filter={"context.status_code":{"$gte":400}}&start_date=2024-01-01T00:00:00Z
    ```
    """
    try:
        # Parse and validate filter if provided
        filter_query: Optional[Dict[str, Any]] = None
        if filter:
            try:
                filter_dict = json.loads(filter)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid filter JSON: {e}",
                ) from e
            if not isinstance(filter_dict, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Filter must be a JSON object",
                )
            filter_query = validate_log_filter(filter_dict)

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
        result = await service.get_error_logs(
            event_code=None,
            status_code=None,
            path=None,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
            log_level=category.upper() if category else None,
            filter_query=filter_query,
        )

        # Transform service result to log entries (service returns event_code and log_data)
        log_entries: List[LogEntry] = []
        for entry in result.get("errors", []):
            log_data = entry.get("log_data", {})
            log_entries.append(
                LogEntry(
                    log_id=entry.get("log_id", ""),
                    log_level=log_data.get("log_level", "ERROR"),
                    status_code=entry.get("status_code") or 0,
                    event_code=entry.get("event_code", ""),
                    message=entry.get("message", ""),
                    path=entry.get("path", ""),
                    method=entry.get("method", ""),
                    logged_at=entry.get("logged_at", ""),
                    log_data=log_data,
                )
            )

        # Build pagination info
        pagination_data = result.get("pagination", {})
        pagination = PaginationInfo(
            page=pagination_data.get("page", page),
            page_size=pagination_data.get("page_size", page_size),
            total=pagination_data.get("total", 0),
            total_pages=pagination_data.get("total_pages", 0),
        )

        return LogsResponse(logs=log_entries, pagination=pagination)

    except HTTPException:
        raise
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
