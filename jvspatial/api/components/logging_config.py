"""Logging configuration for jvspatial API.

This module provides centralized logging configuration including:
- Exception logging filters to prevent duplicate logs
- Access log filtering for error responses
- Custom formatters for known errors
"""

import logging
import re
import traceback

from fastapi import HTTPException

from jvspatial.exceptions import JVSpatialAPIException


def _is_client_error(exc_type, exc_value) -> bool:
    """Check if exception is a known client error (4xx).

    Args:
        exc_type: Exception type
        exc_value: Exception value

    Returns:
        True if the exception is a client error (4xx)
    """
    # Check for FastAPI HTTPException
    if exc_type is HTTPException:
        return exc_value.status_code < 500

    # Check for JVSpatialAPIException
    if exc_type is JVSpatialAPIException or isinstance(
        exc_value, JVSpatialAPIException
    ):
        return hasattr(exc_value, "status_code") and exc_value.status_code < 500

    # Check for httpx.HTTPStatusError (external API errors)
    try:
        import httpx

        if isinstance(exc_value, httpx.HTTPStatusError):
            return exc_value.response.status_code < 500
    except ImportError:
        pass  # httpx not installed

    return False


class CentralizedErrorFilter(logging.Filter):
    """Filter that suppresses framework-level error logs.

    Our APIErrorHandler is the authoritative source for error logging.
    This filter suppresses uvicorn/starlette error logs to prevent duplicates,
    ensuring each exception is logged exactly once with proper context.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out framework-level exception log records.

        Args:
            record: Log record to filter

        Returns:
            True if the record should be logged, False to suppress
        """
        # Only filter exception logs from uvicorn/starlette
        logger_name = record.name

        # NEVER filter our own error handler logs - it's the authoritative source
        if logger_name == "jvspatial.api.components.error_handler":
            return True  # Always allow our error handler logs

        # Check for exact logger name match
        # Suppress ALL ERROR/CRITICAL level logs from uvicorn/starlette
        # Our custom exception handlers log all exceptions with proper context
        # This prevents duplicate logging - we suppress unconditionally since uvicorn
        # logs BEFORE our handler runs, so timing-based checks won't work
        if (
            logger_name == "uvicorn.error" or logger_name == "starlette.error"
        ) and record.levelno >= logging.ERROR:
            # Suppress ALL ERROR/CRITICAL logs from these loggers
            # Our handler will log all exceptions properly
            return False

        # Also check root logger handlers for propagated uvicorn/starlette errors
        # Sometimes errors propagate to root logger, but only suppress if NOT from our handler
        if (
            record.levelno >= logging.ERROR
            and logger_name != "jvspatial.api.components.error_handler"
        ):
            try:
                message = str(record.getMessage())
                # Check if this looks like a uvicorn/starlette error message
                # But be careful - our error handler also includes tracebacks
                # Only suppress if it's clearly a uvicorn/starlette message
                if any(
                    pattern in message
                    for pattern in [
                        "Exception in ASGI application",
                        "During handling of the above exception",
                    ]
                ):
                    # This is likely a propagated uvicorn/starlette error
                    # Suppress it since our handler will log it
                    return False
            except Exception:
                pass

        # Allow all other logs
        return True


class ErrorAwareAccessFilter(logging.Filter):
    """Filter that suppresses access logs for error responses already logged by error handler.

    This filter intelligently correlates access logs with error logs to prevent
    duplicate reporting. If an error response (4xx/5xx) was already logged by
    the internal error handler, the corresponding access log is suppressed.
    Successful responses (2xx/3xx) are always logged.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out access logs for error responses that were already logged.

        Args:
            record: Log record to filter

        Returns:
            True if the record should be logged, False to suppress
        """
        # Only filter uvicorn.access logs
        if record.name != "uvicorn.access":
            return True  # Allow all non-access logs

        # Parse status code and request details from access log message
        # Format: "127.0.0.1:57637 - "POST /auth/login HTTP/1.1" 401"
        try:
            message = record.getMessage()

            # Extract status code from end of message (last 3-digit number)
            status_match = re.search(r"\s(\d{3})\s*$", message)
            if not status_match:
                # Can't parse status code, allow the log (fail open)
                return True

            status_code = int(status_match.group(1))

            # Only suppress error responses (4xx, 5xx)
            # Successful responses (2xx, 3xx) should always be logged
            if status_code < 400:
                return True  # Always log successful responses

            # Check if this error response was already logged by error handler
            from jvspatial.api.components.error_handler import (
                _logged_error_responses,
            )

            try:
                logged_responses = _logged_error_responses.get()
                # Check if any error response with matching status code was logged
                # Since access logs come after error logs in the request lifecycle,
                # any error logged by our handler should be in the context
                # We check for matching status code - if multiple errors with same
                # status occur, we suppress all (conservative approach)
                if any(status == status_code for _, status in logged_responses):
                    # An error with this status code was logged by our handler
                    # Suppress the access log to avoid duplication
                    return False
            except LookupError:
                # No logged errors in context, allow the log
                # This can happen if error handler didn't run or context wasn't initialized
                pass

            # If we can't determine correlation, allow the log (fail open)
            return True

        except Exception:
            # If parsing fails, allow the log (fail open for safety)
            # Better to have duplicate logs than missing logs
            return True


class KnownErrorFormatter(logging.Formatter):
    """Formatter that suppresses stack traces for known errors."""

    def formatException(self, ei):  # noqa: N802
        """Override to return empty string for known errors.

        Args:
            ei: Exception info tuple

        Returns:
            Empty string for client errors, full traceback for server errors
        """
        if not ei:
            return ""

        exc_type, exc_value, exc_tb = ei
        # Suppress stack traces for client errors (4xx) - they're not real exceptions
        if _is_client_error(exc_type, exc_value):
            return ""  # No stack trace for client errors

        # For server errors, format the exception
        # Try using the parent's formatException first (handles real tracebacks well)
        try:
            result = super().formatException(ei)
            # If it returns empty (might happen with mock tracebacks), try traceback.format_exception
            if result:
                return result
        except (AttributeError, TypeError):
            pass  # Fall through to traceback.format_exception

        # Fallback to traceback.format_exception
        # This handles cases where traceback is a mock or super() returned empty
        try:
            formatted = traceback.format_exception(exc_type, exc_value, exc_tb)
            result = "".join(formatted)
            # If still empty, return at least the exception type and message
            if not result:
                result = f"{exc_type.__name__}: {exc_value}\n"
            return result
        except Exception:
            # Last resort: return at least the exception type and message
            return f"{exc_type.__name__}: {exc_value}\n"


class LoggingConfigurator:
    """Configurator for API logging filters and formatters.

    This class handles the setup of logging filters and formatters to prevent
    duplicate error logs and ensure consistent error reporting.
    """

    @staticmethod
    def configure_exception_logging() -> None:
        """Configure exception logging filters and formatters.

        This method sets up:
        - Centralized error filter to suppress framework-level error logs
        - Error-aware access filter to suppress duplicate access logs
        - Known error formatter to suppress stack traces for client errors
        """
        starlette_error_logger = logging.getLogger("starlette.error")
        uvicorn_error_logger = logging.getLogger("uvicorn.error")
        uvicorn_access_logger = logging.getLogger("uvicorn.access")

        # Set log level to CRITICAL to prevent these loggers from emitting ERROR logs
        # This adds defense in depth alongside the filter
        starlette_error_logger.setLevel(logging.CRITICAL)
        uvicorn_error_logger.setLevel(logging.CRITICAL)

        # Create filter and formatter instances
        centralized_error_filter = CentralizedErrorFilter()
        error_aware_access_filter = ErrorAwareAccessFilter()
        known_error_formatter = KnownErrorFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Add filter to logger itself FIRST (applies to all handlers, including future ones)
        # This ensures the filter runs before any handlers process the log records
        starlette_error_logger.addFilter(centralized_error_filter)
        uvicorn_error_logger.addFilter(centralized_error_filter)
        uvicorn_access_logger.addFilter(error_aware_access_filter)

        # Apply filter and formatter to existing handlers
        from logging import Handler

        # Get a fresh copy of handlers list to avoid modification during iteration
        starlette_handlers = list(starlette_error_logger.handlers)
        uvicorn_handlers = list(uvicorn_error_logger.handlers)
        uvicorn_access_handlers = list(uvicorn_access_logger.handlers)

        for log_handler in starlette_handlers:
            # Remove any existing CentralizedErrorFilter to avoid duplicates
            log_handler.filters = [
                f
                for f in log_handler.filters
                if not isinstance(f, CentralizedErrorFilter)
            ]
            log_handler.addFilter(centralized_error_filter)
            log_handler.setFormatter(known_error_formatter)

        # Also configure uvicorn's error logger
        for uvicorn_log_handler in uvicorn_handlers:
            # Remove any existing CentralizedErrorFilter to avoid duplicates
            uvicorn_log_handler.filters = [
                f
                for f in uvicorn_log_handler.filters
                if not isinstance(f, CentralizedErrorFilter)
            ]
            uvicorn_log_handler.addFilter(centralized_error_filter)
            uvicorn_log_handler.setFormatter(known_error_formatter)

        # Configure uvicorn's access logger with error-aware filter
        for uvicorn_access_handler in uvicorn_access_handlers:
            # Remove any existing ErrorAwareAccessFilter to avoid duplicates
            uvicorn_access_handler.filters = [
                f
                for f in uvicorn_access_handler.filters
                if not isinstance(f, ErrorAwareAccessFilter)
            ]
            uvicorn_access_handler.addFilter(error_aware_access_filter)

        # Also add filter to root logger handlers to catch any propagated logs
        root_logger = logging.getLogger()
        for root_handler in root_logger.handlers:
            # Only add filter if it's not already there
            if not any(
                isinstance(f, CentralizedErrorFilter) for f in root_handler.filters
            ):
                root_handler.addFilter(centralized_error_filter)
            # Also add access filter if not present
            if not any(
                isinstance(f, ErrorAwareAccessFilter) for f in root_handler.filters
            ):
                root_handler.addFilter(error_aware_access_filter)

        # Also configure the logger to use this formatter for any new handlers
        if not starlette_error_logger.handlers:
            new_handler: Handler = logging.StreamHandler()
            new_handler.addFilter(centralized_error_filter)
            new_handler.setFormatter(known_error_formatter)
            starlette_error_logger.addHandler(new_handler)


__all__ = [
    "LoggingConfigurator",
    "CentralizedErrorFilter",
    "ErrorAwareAccessFilter",
    "KnownErrorFormatter",
]
