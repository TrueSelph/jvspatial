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
            # Log based on status code severity
            logger = logging.getLogger(__name__)
            if exc.status_code >= 500:
                logger.error(
                    f"API Error [{exc.error_code}]: {exc.message}",
                    exc_info=True,  # Include stack trace for server errors
                    extra={
                        "error_code": exc.error_code,
                        "status_code": exc.status_code,
                        "path": request.url.path,
                        "method": request.method,
                        "details": exc.details,
                    },
                )
            else:
                # Client errors (4xx) - log at DEBUG level to keep logs clean
                logger.debug(
                    f"API Error [{exc.error_code}]: {exc.message}",
                    extra={
                        "error_code": exc.error_code,
                        "status_code": exc.status_code,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )

            response_data = await exc.to_dict()
            response_data["request_id"] = getattr(request.state, "request_id", None)
            response_data["timestamp"] = datetime.utcnow().isoformat()
            response_data["path"] = request.url.path
            return JSONResponse(status_code=exc.status_code, content=response_data)

        # Handle ValidationError with detailed messages
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            logger = logging.getLogger(__name__)
            # Validation errors are client errors (422) - log at DEBUG level
            logger.debug(f"Validation error: {exc}")

            # Extract detailed validation error information
            error_details = []
            if hasattr(exc, "errors"):
                for err in exc.errors():
                    field_path = " -> ".join(str(loc) for loc in err.get("loc", []))
                    error_type = err.get("type", "validation_error")
                    error_msg = err.get("msg", "Validation failed")
                    error_details.append(
                        {"field": field_path, "type": error_type, "message": error_msg}
                    )

            error_message = "Validation failed"
            if error_details:
                # Create a more readable error message
                field_errors = [f"{e['field']}: {e['message']}" for e in error_details]
                error_message = "Validation failed: " + "; ".join(field_errors)
            elif str(exc):
                error_message = f"Validation failed: {str(exc)}"

            return JSONResponse(
                status_code=422,
                content={
                    "error_code": "validation_error",
                    "message": error_message,
                    "details": error_details if error_details else None,
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path,
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

        # Handle httpx.HTTPStatusError from external API calls
        try:
            import httpx

            if isinstance(exc, httpx.HTTPStatusError):
                logger = logging.getLogger(__name__)
                status_code = exc.response.status_code

                # Determine error code from status code
                error_code_map = {
                    400: "bad_request",
                    401: "unauthorized",
                    403: "forbidden",
                    404: "not_found",
                    408: "timeout",
                    409: "conflict",
                    422: "validation_error",
                    429: "rate_limit_exceeded",
                    500: "external_service_error",
                    502: "bad_gateway",
                    503: "service_unavailable",
                    504: "gateway_timeout",
                }
                error_code = error_code_map.get(status_code, "external_service_error")

                # Try to extract error message from response
                try:
                    response_data = exc.response.json()
                    if isinstance(response_data, dict):
                        error_message = (
                            response_data.get("error", {}).get("message")
                            or response_data.get("message")
                            or response_data.get("error")
                            or exc.response.text
                        )
                    else:
                        error_message = exc.response.text
                except Exception:
                    error_message = (
                        exc.response.text or f"External API returned {status_code}"
                    )

                # Log based on status code severity
                # Client errors (4xx) are logged at DEBUG level - they're expected errors
                # Server errors (5xx) are logged at ERROR level with stack traces
                if status_code >= 500:
                    logger.error(
                        f"External API Error [{status_code}]: {error_message}",
                        exc_info=True,
                        extra={
                            "status_code": status_code,
                            "error_code": error_code,
                            "path": request.url.path,
                            "method": request.method,
                            "external_url": str(exc.request.url),
                        },
                    )
                else:
                    # Client errors - log at DEBUG level to keep logs clean
                    logger.debug(
                        f"External API Error [{status_code}]: {error_message}",
                        extra={
                            "status_code": status_code,
                            "error_code": error_code,
                            "path": request.url.path,
                            "method": request.method,
                            "external_url": str(exc.request.url),
                        },
                    )

                return JSONResponse(
                    status_code=status_code,
                    content={
                        "error_code": error_code,
                        "message": error_message,
                        "timestamp": datetime.utcnow().isoformat(),
                        "path": request.url.path,
                        "request_id": getattr(request.state, "request_id", None),
                    },
                )
        except ImportError:
            pass  # httpx not installed, continue to next handler

        # Handle HTTPException from FastAPI (raised by raise_error)
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            logger = logging.getLogger(__name__)
            # Determine error code from status code
            error_code_map = {
                400: "bad_request",
                401: "unauthorized",
                403: "forbidden",
                404: "not_found",
                409: "conflict",
                422: "validation_error",
                500: "internal_error",
            }
            error_code = error_code_map.get(exc.status_code, "internal_error")

            # Extract error message from detail - handle string, dict, list, or None
            # Do this before logging so we can use it in log messages
            error_detail = exc.detail
            if error_detail is None:
                error_message = "An error occurred"
            elif isinstance(error_detail, str):
                error_message = error_detail
            elif isinstance(error_detail, dict):
                # If detail is a dict, try to extract message/error field, otherwise stringify
                error_message = (
                    error_detail.get("message")
                    or error_detail.get("error")
                    or str(error_detail)
                )
            else:
                # For list or other types, convert to string
                error_message = str(error_detail)

            # Log based on status code severity
            # For server errors (5xx), log with full context including stack trace
            # For client errors (4xx), log at DEBUG level to keep logs clean
            if exc.status_code >= 500:
                logger.error(
                    f"HTTP Error [{exc.status_code}]: {error_message}",
                    exc_info=True,  # Include stack trace for server errors
                    extra={
                        "status_code": exc.status_code,
                        "error_code": error_code,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
            else:
                # Client errors (4xx) - log at DEBUG level to keep logs clean
                logger.debug(
                    f"HTTP Error [{exc.status_code}]: {error_message}",
                    extra={
                        "status_code": exc.status_code,
                        "error_code": error_code,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )

            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error_code": error_code,
                    "message": error_message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path,
                    "request_id": getattr(request.state, "request_id", None),
                },
            )

        # Handle other httpx exceptions (timeouts, connection errors, etc.)
        try:
            import httpx

            if isinstance(
                exc, (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout)
            ):
                logger = logging.getLogger(__name__)
                logger.error(
                    f"External API timeout: {exc}",
                    exc_info=True,
                    extra={
                        "error_type": type(exc).__name__,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
                return JSONResponse(
                    status_code=504,
                    content={
                        "error_code": "gateway_timeout",
                        "message": "External service request timed out. Please try again.",
                        "timestamp": datetime.utcnow().isoformat(),
                        "path": request.url.path,
                        "request_id": getattr(request.state, "request_id", None),
                    },
                )

            if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
                logger = logging.getLogger(__name__)
                logger.error(
                    f"External API connection error: {exc}",
                    exc_info=True,
                    extra={
                        "error_type": type(exc).__name__,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
                return JSONResponse(
                    status_code=502,
                    content={
                        "error_code": "bad_gateway",
                        "message": "Unable to connect to external service. Please try again.",
                        "timestamp": datetime.utcnow().isoformat(),
                        "path": request.url.path,
                        "request_id": getattr(request.state, "request_id", None),
                    },
                )
        except ImportError:
            pass  # httpx not installed, continue to next handler

        # Handle unexpected errors (not HTTPException, not ValidationError, not JVSpatialAPIException, not httpx)
        # These are truly unexpected and should be logged with full context
        logger = logging.getLogger(__name__)
        logger.error(
            f"Unexpected error: {type(exc).__name__}: {exc}",
            exc_info=True,  # Always include stack trace for unexpected errors
            extra={
                "error_type": type(exc).__name__,
                "path": request.url.path,
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "internal_error",
                "message": "An unexpected error occurred. Please contact support if this persists.",
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
