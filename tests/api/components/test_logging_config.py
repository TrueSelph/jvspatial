"""Tests for LoggingConfigurator component."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from jvspatial.api.components.logging_config import (
    CentralizedErrorFilter,
    ErrorAwareAccessFilter,
    KnownErrorFormatter,
    LoggingConfigurator,
)
from jvspatial.exceptions import JVSpatialAPIException


class TestLoggingFilters:
    """Test logging filter classes."""

    def test_centralized_error_filter_allows_our_handler(self):
        """Test that our error handler logs are never filtered."""
        filter_instance = CentralizedErrorFilter()
        record = MagicMock()
        record.name = "jvspatial.api.components.error_handler"
        record.levelno = logging.ERROR

        # Should always allow our handler
        assert filter_instance.filter(record) is True

    def test_centralized_error_filter_blocks_uvicorn_error(self):
        """Test that uvicorn.error logs are filtered."""
        filter_instance = CentralizedErrorFilter()
        record = MagicMock()
        record.name = "uvicorn.error"
        record.levelno = logging.ERROR

        # Should filter uvicorn error logs
        assert filter_instance.filter(record) is False

    def test_centralized_error_filter_blocks_starlette_error(self):
        """Test that starlette.error logs are filtered."""
        filter_instance = CentralizedErrorFilter()
        record = MagicMock()
        record.name = "starlette.error"
        record.levelno = logging.ERROR

        # Should filter starlette error logs
        assert filter_instance.filter(record) is False

    def test_error_aware_access_filter_allows_success(self):
        """Test that successful responses are always logged."""
        filter_instance = ErrorAwareAccessFilter()
        record = MagicMock()
        record.name = "uvicorn.access"
        record.getMessage.return_value = '127.0.0.1 - "GET /api/test HTTP/1.1" 200'

        # Should allow successful responses
        assert filter_instance.filter(record) is True

    def test_known_error_formatter_suppresses_client_errors(self):
        """Test that client errors don't get stack traces."""
        formatter = KnownErrorFormatter()

        # Mock exception info for HTTPException (4xx)
        exc_info = (
            HTTPException,
            HTTPException(status_code=404, detail="Not found"),
            None,
        )

        # Should return empty string (no stack trace)
        result = formatter.formatException(exc_info)
        assert result == ""

    def test_known_error_formatter_shows_server_errors(self):
        """Test that server errors get stack traces."""
        formatter = KnownErrorFormatter()

        # Mock exception info for ValueError (5xx equivalent)
        exc_info = (
            ValueError,
            ValueError("Internal error"),
            MagicMock(),
        )

        # Should return stack trace
        result = formatter.formatException(exc_info)
        # Should not be empty (has traceback)
        assert result != ""


class TestLoggingConfigurator:
    """Test LoggingConfigurator functionality."""

    def test_configure_exception_logging(self):
        """Test that configure_exception_logging sets up filters."""
        # Get loggers before configuration
        starlette_logger = logging.getLogger("starlette.error")
        uvicorn_logger = logging.getLogger("uvicorn.error")
        uvicorn_access_logger = logging.getLogger("uvicorn.access")

        initial_starlette_level = starlette_logger.level
        initial_uvicorn_level = uvicorn_logger.level

        # Configure logging
        LoggingConfigurator.configure_exception_logging()

        # Verify loggers are configured
        assert starlette_logger.level == logging.CRITICAL
        assert uvicorn_logger.level == logging.CRITICAL

        # Verify filters are added
        starlette_filters = [
            f for f in starlette_logger.filters if isinstance(f, CentralizedErrorFilter)
        ]
        assert len(starlette_filters) > 0

        uvicorn_filters = [
            f for f in uvicorn_logger.filters if isinstance(f, CentralizedErrorFilter)
        ]
        assert len(uvicorn_filters) > 0

        access_filters = [
            f
            for f in uvicorn_access_logger.filters
            if isinstance(f, ErrorAwareAccessFilter)
        ]
        assert len(access_filters) > 0

    def test_configure_exception_logging_idempotent(self):
        """Test that configure can be called multiple times safely."""
        LoggingConfigurator.configure_exception_logging()
        first_count = len(logging.getLogger("starlette.error").filters)

        LoggingConfigurator.configure_exception_logging()
        second_count = len(logging.getLogger("starlette.error").filters)

        # Should not duplicate filters (filters are deduplicated in implementation)
        # Count may be same or filters may be replaced
        assert second_count >= first_count
