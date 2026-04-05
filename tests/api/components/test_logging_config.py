"""Tests for LoggingConfigurator component."""

import logging
import sys
import uuid
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from jvspatial.api.components.logging_config import (
    CentralizedErrorFilter,
    ErrorAwareAccessFilter,
    KnownErrorFormatter,
    LoggingConfigurator,
)


def _isolated_named_loggers():
    """Unique logger objects so configure_exception_logging never touches real uvicorn/starlette."""
    u = uuid.uuid4().hex[:12]
    return {
        "starlette.error": logging.getLogger(f"jv.isolated.{u}.starlette.error"),
        "uvicorn.error": logging.getLogger(f"jv.isolated.{u}.uvicorn.error"),
        "uvicorn.access": logging.getLogger(f"jv.isolated.{u}.uvicorn.access"),
        "root": logging.getLogger(f"jv.isolated.{u}.root"),
    }


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
        """Test that server errors get stack traces.

        Do not pass MagicMock as traceback: traceback.format_exception walks tb_next and
        can follow mocks indefinitely (hang / extreme slowdown in CI).
        """
        formatter = KnownErrorFormatter()
        try:
            raise ValueError("Internal error")
        except ValueError:
            exc_info = sys.exc_info()
        result = formatter.formatException(exc_info)
        assert result != ""


class TestLoggingConfigurator:
    """Test LoggingConfigurator without mutating real framework loggers."""

    def test_configure_exception_logging(self):
        """configure_exception_logging sets levels and attaches filters on target loggers."""
        loggers = _isolated_named_loggers()

        def get_logger(name=None):
            if name == "starlette.error":
                return loggers["starlette.error"]
            if name == "uvicorn.error":
                return loggers["uvicorn.error"]
            if name == "uvicorn.access":
                return loggers["uvicorn.access"]
            if name is None:
                return loggers["root"]
            return logging.getLogger(name)

        with patch(
            "jvspatial.api.components.logging_config.logging.getLogger",
            side_effect=get_logger,
        ):
            LoggingConfigurator.configure_exception_logging()

        starlette_logger = loggers["starlette.error"]
        uvicorn_logger = loggers["uvicorn.error"]
        uvicorn_access_logger = loggers["uvicorn.access"]

        assert starlette_logger.level == logging.CRITICAL
        assert uvicorn_logger.level == logging.CRITICAL

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
        """Calling configure twice should not break (still using isolated loggers)."""
        loggers = _isolated_named_loggers()

        def get_logger(name=None):
            if name == "starlette.error":
                return loggers["starlette.error"]
            if name == "uvicorn.error":
                return loggers["uvicorn.error"]
            if name == "uvicorn.access":
                return loggers["uvicorn.access"]
            if name is None:
                return loggers["root"]
            return logging.getLogger(name)

        with patch(
            "jvspatial.api.components.logging_config.logging.getLogger",
            side_effect=get_logger,
        ):
            LoggingConfigurator.configure_exception_logging()
            first_count = len(loggers["starlette.error"].filters)
            LoggingConfigurator.configure_exception_logging()
            second_count = len(loggers["starlette.error"].filters)

        assert second_count >= first_count
