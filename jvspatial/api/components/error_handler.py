"""Unified error handling system for jvspatial API.

This module provides centralized error handling with enhanced context and consistency,
following the new standard implementation approach.
"""

import contextvars
import logging
import traceback
from contextlib import suppress
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union

from fastapi import Request
from fastapi.responses import JSONResponse

from jvspatial.exceptions import JVSpatialAPIException

# Context variable to track exceptions that have been logged by our handler
# This prevents duplicate logging even if exceptions propagate through multiple layers
# Use a factory function to avoid mutable default (B039)
_logged_exceptions: contextvars.ContextVar[Set[int]] = contextvars.ContextVar(
    "_logged_exceptions"
)

# Context variable to track error responses that have been logged by our handler
# This prevents duplicate access logs for error responses (4xx/5xx)
# Stores tuples of (request_id, status_code) for logged error responses
_logged_error_responses: contextvars.ContextVar[Set[tuple]] = contextvars.ContextVar(
    "_logged_error_responses"
)


def _add_request_id_to_content(
    request: Request, content: Dict[str, Any]
) -> Dict[str, Any]:
    """Add request_id to response content if available.

    Args:
        request: FastAPI request object
        content: Response content dictionary

    Returns:
        Content dictionary with request_id added if available
    """
    if hasattr(request.state, "request_id") and request.state.request_id:
        content["request_id"] = request.state.request_id
    return content


def _format_clean_traceback(exc: Exception) -> str:
    """Format traceback as string, excluding framework frames.

    Extracts the root exception and formats a traceback string that only includes
    application code frames, filtering out uvicorn/starlette/fastapi framework frames.

    Args:
        exc: Exception to format

    Returns:
        Formatted traceback string with only application frames
    """
    # Extract root exception
    root_exc = _extract_root_exception(exc)

    # Format the exception with traceback
    exc_lines = traceback.format_exception(
        type(root_exc), root_exc, root_exc.__traceback__
    )

    # Filter out lines from framework packages
    framework_paths = [
        "uvicorn",
        "starlette",
        "fastapi",
        "anyio",
        "site-packages/starlette",
        "site-packages/uvicorn",
        "site-packages/fastapi",
        "site-packages/anyio",
    ]

    filtered_lines = [
        line
        for line in exc_lines
        if not any(framework in line for framework in framework_paths)
    ]

    # If we filtered everything, return at least the exception message
    if not filtered_lines:
        return f"{type(root_exc).__name__}: {root_exc}\n"

    return "".join(filtered_lines)


def _extract_root_exception(
    exc: Exception, visited: Optional[Set[int]] = None
) -> Exception:
    """Extract root exception from ExceptionGroup or chained exceptions.

    This function handles:
    - ExceptionGroup (Python 3.11+) - extracts the first nested exception
    - Exception chaining - follows __cause__ and __context__ to find root cause
    - Prevents infinite recursion by tracking visited exceptions

    Args:
        exc: Exception to extract root from
        visited: Set of exception IDs already visited (for cycle detection)

    Returns:
        Root cause exception
    """
    # Initialize visited set on first call
    if visited is None:
        visited = set()

    # Prevent infinite recursion by tracking visited exceptions
    exc_id = id(exc)
    if exc_id in visited:
        # Circular reference detected - return current exception
        return exc
    visited.add(exc_id)

    # Handle ExceptionGroup (Python 3.11+)
    # ExceptionGroup has an 'exceptions' attribute containing nested exceptions
    if hasattr(exc, "exceptions") and hasattr(exc, "__cause__"):
        with suppress(AttributeError, IndexError, TypeError):
            # Get the first nested exception from the group
            if hasattr(exc, "exceptions") and exc.exceptions:
                nested = exc.exceptions[0]
                # Recursively extract root from nested exception
                return _extract_root_exception(nested, visited)

    # Handle exception chaining - follow __cause__ first (explicit chaining)
    if hasattr(exc, "__cause__") and exc.__cause__ is not None:
        cause = exc.__cause__
        if isinstance(cause, Exception):
            return _extract_root_exception(cause, visited)

    # Handle exception context (implicit chaining)
    # Only follow context if it's not the same as cause (avoid loops)
    if (
        hasattr(exc, "__context__")
        and exc.__context__ is not None
        and exc.__context__ is not exc.__cause__
    ):
        context = exc.__context__
        if isinstance(context, Exception):
            return _extract_root_exception(context, visited)

    # This is the root exception
    return exc


def _get_request_identifier(request: Request) -> str:
    """Generate a unique identifier for a request.

    Uses request object id for uniqueness, which is stable for the request lifetime.
    Falls back to path + method + client if id is not available.

    Args:
        request: FastAPI request object

    Returns:
        Unique string identifier for the request
    """
    # Use request object id as primary identifier (most reliable)
    request_id = id(request)

    # Fallback: create identifier from request attributes
    # This ensures we have a unique identifier even if id() is not stable
    fallback_id = f"{request.method}:{request.url.path}:{request.client.host if request.client else 'unknown'}"

    # Prefer request.state.request_id if available (set by middleware)
    if hasattr(request.state, "request_id") and request.state.request_id:
        return str(request.state.request_id)

    # Use object id as primary, with fallback for safety
    return f"{request_id}:{hash(fallback_id)}"


def _mark_error_logged(request: Request, status_code: int) -> None:
    """Mark a request as having been logged as an error.

    This allows the access log filter to suppress duplicate access logs
    for error responses that were already logged by the error handler.

    Args:
        request: FastAPI request object
        status_code: HTTP status code of the error response
    """
    try:
        request_id = _get_request_identifier(request)
        try:
            logged = _logged_error_responses.get()
        except LookupError:
            logged = set()

        # Store tuple of (request_id, status_code) for correlation
        logged.add((request_id, status_code))
        _logged_error_responses.set(logged)
    except Exception:
        # If marking fails, continue - better to have duplicate logs than no logs
        pass


def _is_error_logged(request: Request, status_code: int) -> bool:
    """Check if a request with the given status code has been logged as an error.

    Args:
        request: FastAPI request object
        status_code: HTTP status code to check

    Returns:
        True if this error response was already logged, False otherwise
    """
    try:
        request_id = _get_request_identifier(request)
        try:
            logged = _logged_error_responses.get()
        except LookupError:
            return False

        return (request_id, status_code) in logged
    except Exception:
        return False


async def _log_error_to_service(
    request: Request,
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    traceback_str: Optional[str] = None,
) -> None:
    """Log error using the standard logger with details.

    The DBLogHandler will automatically intercept ERROR level logs and
    save them to the database. This simplifies error logging - just use
    the logger with optional details in the extra parameter.

    Args:
        request: FastAPI request object
        status_code: HTTP status code
        error_code: Error code
        message: Error message
        details: Optional error details
        traceback_str: Optional traceback string (for 5xx errors)
    """
    try:
        logger = logging.getLogger("jvspatial.api.components.error_handler")

        # Build extra dict with error details
        extra: Dict[str, Any] = {
            "status_code": status_code,
            "error_code": error_code,
            "path": request.url.path,
            "method": request.method,
        }

        # Add details if provided
        if details:
            extra["details"] = details

        # Add any custom fields from request state
        if hasattr(request.state, "user_id") and request.state.user_id:
            extra["user_id"] = request.state.user_id
        if hasattr(request.state, "session_id") and request.state.session_id:
            extra["session_id"] = request.state.session_id
        if hasattr(request.state, "interaction_id") and request.state.interaction_id:
            extra["interaction_id"] = request.state.interaction_id

        # Log the error - DBLogHandler will automatically save to database
        # Include traceback in details if provided
        if traceback_str:
            error_details = details.copy() if isinstance(details, dict) else {}
            if isinstance(details, list):
                error_details["validation_errors"] = details
            error_details["traceback"] = traceback_str
            extra["details"] = error_details

        logger.error(message, extra=extra)

    except Exception as e:
        # Don't let error logging failures affect the error response
        logger = logging.getLogger("jvspatial.api.components.error_handler")
        logger.warning(f"Error logging failed: {e}", exc_info=True)


class APIErrorHandler:
    """Unified error handling system with enhanced context.

    This class provides centralized error handling with request context,
    following the new standard implementation approach.

    Errors are automatically logged to the database via the DBLogHandler,
    which intercepts ERROR level log records. No additional setup is required
    beyond initializing the logging database.
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
        # Get logger - use explicit name to ensure it's not filtered
        logger = logging.getLogger("jvspatial.api.components.error_handler")

        try:
            # Extract root exception to handle ExceptionGroup and chaining (for tracking)
            root_exc = _extract_root_exception(exc)
            exc_id = id(root_exc)

            # Check if this exception has already been logged
            try:
                logged = _logged_exceptions.get()
            except LookupError:
                logged = set()
            already_logged = exc_id in logged

            if not already_logged:
                # Mark exception as logged
                logged.add(exc_id)
                _logged_exceptions.set(logged)
        except Exception as e:
            # If exception tracking fails, log it but continue
            logger.warning(f"Error in exception tracking: {e}", exc_info=True)
            already_logged = False

        if isinstance(exc, JVSpatialAPIException):
            # Log based on status code severity
            # Only log if not already logged
            if not already_logged:
                if exc.status_code >= 500:
                    # Server errors (5xx): ERROR level with full stack trace for debugging
                    logger.error(
                        f"API Error [{exc.error_code}]: {exc.message}",
                        exc_info=True,  # Include full stack trace for debugging
                        extra={
                            "error_code": exc.error_code,
                            "status_code": exc.status_code,
                            "path": request.url.path,
                            "method": request.method,
                            "details": exc.details,
                        },
                    )
                else:
                    # Client errors (4xx): ERROR level without stack trace
                    logger.error(
                        f"API Error [{exc.error_code}]: {exc.message}",
                        exc_info=False,  # No stack trace for client errors
                        extra={
                            "error_code": exc.error_code,
                            "status_code": exc.status_code,
                            "path": request.url.path,
                            "method": request.method,
                        },
                    )
                # Mark this error response as logged to prevent duplicate access logs
                _mark_error_logged(request, exc.status_code)

                # Log to error logging service
                traceback_str = None
                if exc.status_code >= 500:
                    traceback_str = _format_clean_traceback(exc)
                await _log_error_to_service(
                    request=request,
                    status_code=exc.status_code,
                    error_code=exc.error_code,
                    message=exc.message,
                    details=exc.details if exc.details else None,
                    traceback_str=traceback_str,
                )

            response_data = await exc.to_dict()
            response_data["timestamp"] = datetime.utcnow().isoformat()
            response_data["path"] = request.url.path
            response_data = _add_request_id_to_content(request, response_data)
            return JSONResponse(status_code=exc.status_code, content=response_data)

        # Handle ValidationError with detailed messages
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            # Validation errors (422): ERROR level without stack trace (client error)
            # Only log if not already logged
            if not already_logged:
                logger.error(
                    f"Validation error: {exc}",
                    exc_info=False,  # No stack trace for validation errors (client error)
                    extra={
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
                # Mark this error response as logged to prevent duplicate access logs
                _mark_error_logged(request, 422)

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

            # Log to error logging service with detailed message
            await _log_error_to_service(
                request=request,
                status_code=422,
                error_code="validation_error",
                message=error_message,
                details=error_details if error_details else None,
                traceback_str=None,
            )

            content = {
                "error_code": "validation_error",
                "message": error_message,
                "details": error_details if error_details else None,
                "timestamp": datetime.utcnow().isoformat(),
                "path": request.url.path,
            }
            content = _add_request_id_to_content(request, content)
            return JSONResponse(status_code=422, content=content)

        # Handle httpx.HTTPStatusError from external API calls
        try:
            import httpx

            if isinstance(exc, httpx.HTTPStatusError):
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
                # Only log if not already logged
                if not already_logged:
                    if status_code >= 500:
                        # Server errors (5xx): ERROR level with stack trace
                        logger.error(
                            f"External API Error [{status_code}]: {error_message}",
                            exc_info=True,  # Include full stack trace for debugging
                            extra={
                                "status_code": status_code,
                                "error_code": error_code,
                                "path": request.url.path,
                                "method": request.method,
                                "external_url": str(exc.request.url),
                            },
                        )
                    else:
                        # Client errors (4xx): ERROR level without stack trace
                        logger.error(
                            f"External API Error [{status_code}]: {error_message}",
                            exc_info=False,  # No stack trace for client errors
                            extra={
                                "status_code": status_code,
                                "error_code": error_code,
                                "path": request.url.path,
                                "method": request.method,
                                "external_url": str(exc.request.url),
                            },
                        )
                    # Mark this error response as logged to prevent duplicate access logs
                    _mark_error_logged(request, status_code)

                    # Log to error logging service
                    traceback_str = None
                    if status_code >= 500:
                        traceback_str = _format_clean_traceback(exc)
                    await _log_error_to_service(
                        request=request,
                        status_code=status_code,
                        error_code=error_code,
                        message=error_message,
                        details=(
                            {"external_url": str(exc.request.url)}
                            if hasattr(exc, "request")
                            else None
                        ),
                        traceback_str=traceback_str,
                    )

                content = {
                    "error_code": error_code,
                    "message": error_message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path,
                }
                content = _add_request_id_to_content(request, content)
                return JSONResponse(status_code=status_code, content=content)
        except ImportError:
            pass  # httpx not installed, continue to next handler

        # Handle HTTPException from FastAPI (raised by raise_error)
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
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
            # Only log if not already logged
            if not already_logged:
                if exc.status_code >= 500:
                    # Server errors (5xx): ERROR level with stack trace
                    logger.error(
                        f"HTTP Error [{exc.status_code}]: {error_message}",
                        exc_info=True,  # Include full stack trace for debugging
                        extra={
                            "status_code": exc.status_code,
                            "error_code": error_code,
                            "path": request.url.path,
                            "method": request.method,
                        },
                    )
                else:
                    # Client errors (4xx): ERROR level without stack trace
                    logger.error(
                        f"HTTP Error [{exc.status_code}]: {error_message}",
                        exc_info=False,  # No stack trace for client errors
                        extra={
                            "status_code": exc.status_code,
                            "error_code": error_code,
                            "path": request.url.path,
                            "method": request.method,
                        },
                    )
                # Mark this error response as logged to prevent duplicate access logs
                _mark_error_logged(request, exc.status_code)

                # Log to error logging service
                traceback_str = None
                if exc.status_code >= 500:
                    traceback_str = _format_clean_traceback(exc)
                await _log_error_to_service(
                    request=request,
                    status_code=exc.status_code,
                    error_code=error_code,
                    message=error_message,
                    details=None,
                    traceback_str=traceback_str,
                )

            content = {
                "error_code": error_code,
                "message": error_message,
                "timestamp": datetime.utcnow().isoformat(),
                "path": request.url.path,
            }
            content = _add_request_id_to_content(request, content)
            return JSONResponse(status_code=exc.status_code, content=content)

        # Handle other httpx exceptions (timeouts, connection errors, etc.)
        try:
            import httpx

            if isinstance(
                exc, (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout)
            ):
                # Only log if not already logged
                if not already_logged:
                    logger.error(
                        f"External API timeout: {exc}",
                        exc_info=True,  # Include full stack trace for debugging
                        extra={
                            "error_type": type(exc).__name__,
                            "path": request.url.path,
                            "method": request.method,
                        },
                    )
                    # Mark this error response as logged to prevent duplicate access logs
                    _mark_error_logged(request, 504)

                    # Log to error logging service
                    await _log_error_to_service(
                        request=request,
                        status_code=504,
                        error_code="gateway_timeout",
                        message="External service request timed out. Please try again.",
                        details={"error_type": type(exc).__name__},
                        traceback_str=_format_clean_traceback(exc),
                    )
                content = {
                    "error_code": "gateway_timeout",
                    "message": "External service request timed out. Please try again.",
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path,
                }
                content = _add_request_id_to_content(request, content)
                return JSONResponse(status_code=504, content=content)

            if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
                # Only log if not already logged
                if not already_logged:
                    logger.error(
                        f"External API connection error: {exc}",
                        exc_info=True,  # Include full stack trace for debugging
                        extra={
                            "error_type": type(exc).__name__,
                            "path": request.url.path,
                            "method": request.method,
                        },
                    )
                    # Mark this error response as logged to prevent duplicate access logs
                    _mark_error_logged(request, 502)

                    # Log to error logging service
                    await _log_error_to_service(
                        request=request,
                        status_code=502,
                        error_code="bad_gateway",
                        message="Unable to connect to external service. Please try again.",
                        details={"error_type": type(exc).__name__},
                        traceback_str=_format_clean_traceback(exc),
                    )
                content = {
                    "error_code": "bad_gateway",
                    "message": "Unable to connect to external service. Please try again.",
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path,
                }
                content = _add_request_id_to_content(request, content)
                return JSONResponse(status_code=502, content=content)
        except ImportError:
            pass  # httpx not installed, continue to next handler

        # Handle unexpected errors (not HTTPException, not ValidationError, not JVSpatialAPIException, not httpx)
        # These are truly unexpected and should be logged with full context
        # Only log if not already logged
        if not already_logged:
            # Extract root exception and format clean traceback (excluding uvicorn/starlette frames)
            root_exc = _extract_root_exception(exc)
            clean_traceback = _format_clean_traceback(root_exc)

            # Log with the clean traceback included in the message
            # Use exc_info=False to avoid double-formatting, include traceback in message
            logger.error(
                f"Unexpected error: {type(root_exc).__name__}: {root_exc}\n{clean_traceback}",
                exc_info=False,  # Don't use exc_info since we're formatting traceback manually
                extra={
                    "error_type": type(root_exc).__name__,
                    "path": request.url.path,
                    "method": request.method,
                },
            )
            # Mark this error response as logged to prevent duplicate access logs
            _mark_error_logged(request, 500)

            # Log to error logging service
            root_exc = _extract_root_exception(exc)
            clean_traceback = _format_clean_traceback(root_exc)
            await _log_error_to_service(
                request=request,
                status_code=500,
                error_code="internal_error",
                message=f"An unexpected error occurred: {str(exc)}",
                details={"error_type": type(root_exc).__name__},
                traceback_str=clean_traceback,
            )

        # Always return proper error response structure
        try:
            content = {
                "error_code": "internal_error",
                "message": f"An unexpected error occurred: {str(exc)}",
                "timestamp": datetime.utcnow().isoformat(),
                "path": request.url.path,
            }
            content = _add_request_id_to_content(request, content)
            return JSONResponse(status_code=500, content=content)
        except Exception as response_error:
            # If creating response fails, log and return minimal response
            logger.error(
                f"Failed to create error response: {response_error}", exc_info=True
            )
            content = {
                "error_code": "internal_error",
                "message": "An unexpected error occurred. Please contact support if this persists.",
                "timestamp": datetime.utcnow().isoformat(),
                "path": getattr(request, "url", None) and request.url.path or "/",
            }
            content = _add_request_id_to_content(request, content)
            return JSONResponse(status_code=500, content=content)

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
            response_data = _add_request_id_to_content(request, response_data)

        return JSONResponse(status_code=status_code, content=response_data)


__all__ = [
    "APIErrorHandler",
    "_extract_root_exception",
    "_logged_exceptions",
    "_logged_error_responses",
    "_get_request_identifier",
    "_mark_error_logged",
    "_is_error_logged",
    "_log_error_to_service",
]
