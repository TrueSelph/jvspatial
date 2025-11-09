"""Structured logging system for jvspatial applications.

This module provides structured logging as the default logging approach,
following the new standard implementation.
"""

import logging
import sys
from typing import Any

try:
    import structlog

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


class JVSpatialLogger:
    """Enhanced logger with structured logging capabilities.

    Provides structured logging with context and performance tracking,
    falling back to standard logging if structlog is not available.
    """

    def __init__(self, name: str, enable_structured: bool = True):
        """Initialize the logger.

        Args:
            name: Logger name
            enable_structured: Whether to enable structured logging
        """
        self.name = name
        self.enable_structured = enable_structured and STRUCTLOG_AVAILABLE

        if self.enable_structured:
            self.logger = structlog.get_logger(name)
        else:
            self.logger = logging.getLogger(name)

    def info(self, message: str, **context: Any) -> None:
        """Log info message with structured context.

        Args:
            message: Log message
            **context: Additional context data
        """
        if self.enable_structured:
            self.logger.info(message, **context)
        else:
            formatted_context = " ".join([f"{k}={v}" for k, v in context.items()])
            self.logger.info(f"{message} {formatted_context}".strip())

    def error(self, message: str, **context: Any) -> None:
        """Log error message with structured context.

        Args:
            message: Log message
            **context: Additional context data
        """
        if self.enable_structured:
            self.logger.error(message, **context)
        else:
            formatted_context = " ".join([f"{k}={v}" for k, v in context.items()])
            self.logger.error(f"{message} {formatted_context}".strip())

    def warning(self, message: str, **context: Any) -> None:
        """Log warning message with structured context.

        Args:
            message: Log message
            **context: Additional context data
        """
        if self.enable_structured:
            self.logger.warning(message, **context)
        else:
            formatted_context = " ".join([f"{k}={v}" for k, v in context.items()])
            self.logger.warning(f"{message} {formatted_context}".strip())

    def debug(self, message: str, **context: Any) -> None:
        """Log debug message with structured context.

        Args:
            message: Log message
            **context: Additional context data
        """
        if self.enable_structured:
            self.logger.debug(message, **context)
        else:
            formatted_context = " ".join([f"{k}={v}" for k, v in context.items()])
            self.logger.debug(f"{message} {formatted_context}".strip())

    def critical(self, message: str, **context: Any) -> None:
        """Log critical message with structured context.

        Args:
            message: Log message
            **context: Additional context data
        """
        if self.enable_structured:
            self.logger.critical(message, **context)
        else:
            formatted_context = " ".join([f"{k}={v}" for k, v in context.items()])
            self.logger.critical(f"{message} {formatted_context}".strip())


class StructuredLoggingConfig:
    """Configuration for structured logging system."""

    def __init__(self, enable_json: bool = True, enable_colors: bool = True):
        """Initialize structured logging configuration.

        Args:
            enable_json: Whether to use JSON formatting
            enable_colors: Whether to enable colored output
        """
        self.enable_json = enable_json
        self.enable_colors = enable_colors

    def configure(self) -> None:
        """Configure structured logging system."""
        if not STRUCTLOG_AVAILABLE:
            self._configure_fallback()
            return

        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        if self.enable_colors and not self.enable_json:
            processors.append(structlog.dev.ConsoleRenderer(colors=True))
        elif self.enable_json:
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer(colors=False))

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

    def _configure_fallback(self) -> None:
        """Configure fallback logging when structlog is not available."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
        )


class PerformanceLogger:
    """Logger specifically for performance metrics."""

    def __init__(self, logger_name: str = "jvspatial.performance"):
        """Initialize performance logger.

        Args:
            logger_name: Name for the performance logger
        """
        self.logger = JVSpatialLogger(logger_name)

    def log_operation(
        self, operation_name: str, duration: float, **metrics: Any
    ) -> None:
        """Log performance metrics for an operation.

        Args:
            operation_name: Name of the operation
            duration: Duration in seconds
            **metrics: Additional performance metrics
        """
        self.logger.info(
            f"Operation completed: {operation_name}",
            operation=operation_name,
            duration=duration,
            duration_ms=duration * 1000,
            **metrics,
        )

    def log_database_operation(
        self, operation: str, collection: str, duration: float, **metrics: Any
    ) -> None:
        """Log database operation performance.

        Args:
            operation: Database operation type
            collection: Collection name
            duration: Duration in seconds
            **metrics: Additional metrics
        """
        self.logger.info(
            f"Database operation: {operation}",
            operation=operation,
            collection=collection,
            duration=duration,
            duration_ms=duration * 1000,
            **metrics,
        )

    def log_cache_operation(
        self, operation: str, key: str, hit: bool, duration: float
    ) -> None:
        """Log cache operation performance.

        Args:
            operation: Cache operation type
            key: Cache key
            hit: Whether it was a cache hit
            duration: Duration in seconds
        """
        self.logger.info(
            f"Cache operation: {operation}",
            operation=operation,
            key=key,
            hit=hit,
            duration=duration,
            duration_ms=duration * 1000,
        )


class SecurityLogger:
    """Logger specifically for security events."""

    def __init__(self, logger_name: str = "jvspatial.security"):
        """Initialize security logger.

        Args:
            logger_name: Name for the security logger
        """
        self.logger = JVSpatialLogger(logger_name)

    def log_auth_attempt(
        self, username: str, success: bool, client_ip: str, **context: Any
    ) -> None:
        """Log authentication attempt.

        Args:
            username: Username attempting authentication
            success: Whether authentication was successful
            client_ip: Client IP address
            **context: Additional context
        """
        self.logger.info(
            f"Authentication attempt: {username}",
            username=username,
            success=success,
            client_ip=client_ip,
            event_type="auth_attempt",
            **context,
        )

    def log_rate_limit(
        self, client_ip: str, user_agent: str = "", **context: Any
    ) -> None:
        """Log rate limiting event.

        Args:
            client_ip: Client IP address
            user_agent: Client user agent
            **context: Additional context
        """
        self.logger.warning(
            f"Rate limit exceeded: {client_ip}",
            client_ip=client_ip,
            user_agent=user_agent,
            event_type="rate_limit",
            **context,
        )

    def log_brute_force(self, username: str, client_ip: str, **context: Any) -> None:
        """Log brute force attack attempt.

        Args:
            username: Username under attack
            client_ip: Client IP address
            **context: Additional context
        """
        self.logger.warning(
            f"Brute force attempt detected: {username}",
            username=username,
            client_ip=client_ip,
            event_type="brute_force",
            **context,
        )


def get_logger(name: str) -> JVSpatialLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name

    Returns:
        JVSpatialLogger instance
    """
    return JVSpatialLogger(name)


def configure_logging(enable_json: bool = True, enable_colors: bool = True) -> None:
    """Configure structured logging system.

    Args:
        enable_json: Whether to use JSON formatting
        enable_colors: Whether to enable colored output
    """
    config = StructuredLoggingConfig(
        enable_json=enable_json, enable_colors=enable_colors
    )
    config.configure()


# Global loggers
performance_logger = PerformanceLogger()
security_logger = SecurityLogger()


__all__ = [
    "JVSpatialLogger",
    "StructuredLoggingConfig",
    "PerformanceLogger",
    "SecurityLogger",
    "get_logger",
    "configure_logging",
    "performance_logger",
    "security_logger",
]
