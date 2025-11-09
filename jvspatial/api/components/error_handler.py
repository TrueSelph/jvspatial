"""Unified error handling system for jvspatial API.

This module provides centralized error handling with enhanced context and consistency,
following the new standard implementation approach.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from jvspatial.exceptions import JVSpatialAPIException


class APIErrorHandler:
    """Unified error handling system with enhanced context.

    This class provides centralized error handling with request context,
    following the new standard implementation approach.
    """

    def __init__(self):
        """Initialize the API error handler."""
        self._logger = logging.getLogger(__name__)

    @staticmethod
    async def handle_exception(request: Request, exc: Exception) -> JSONResponse:
        """Centralized error handling with request context.

        Args:
            request: FastAPI request object
            exc: Exception that occurred

        Returns:
            JSONResponse with error details
        """
        if isinstance(exc, JVSpatialAPIException):
            response_data = await exc.to_dict()
            response_data["request_id"] = getattr(request.state, "request_id", None)
            response_data["timestamp"] = datetime.utcnow().isoformat()
            response_data["path"] = request.url.path
            return JSONResponse(status_code=exc.status_code, content=response_data)

        # Handle unexpected errors
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "internal_error",
                "message": "An unexpected error occurred",
                "timestamp": datetime.utcnow().isoformat(),
                "path": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @staticmethod
    def create_error_response(
        error_code: str,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
    ) -> JSONResponse:
        """Create a standardized error response.

        Args:
            error_code: Error code identifier
            message: Error message
            status_code: HTTP status code
            details: Additional error details
            request: Optional request object for context

        Returns:
            JSONResponse with error details
        """
        response_data = {
            "error_code": error_code,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "status_code": status_code,
        }

        if details:
            response_data["details"] = details

        if request:
            response_data["path"] = request.url.path
            response_data["request_id"] = getattr(request.state, "request_id", None)

        return JSONResponse(status_code=status_code, content=response_data)


class ErrorHandler:
    """Unified error handling system for backward compatibility.

    This class provides the same interface as the original ErrorHandler
    while using the new APIErrorHandler internally.
    """

    @staticmethod
    async def handle_exception(request: Request, exc: Exception) -> JSONResponse:
        """Centralized error handling with request context.

        Args:
            request: FastAPI request object
            exc: Exception that occurred

        Returns:
            JSONResponse with error details
        """
        return await APIErrorHandler.handle_exception(request, exc)


__all__ = ["APIErrorHandler", "ErrorHandler"]
