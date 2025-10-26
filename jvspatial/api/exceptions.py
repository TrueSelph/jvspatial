"""Standardized exception hierarchy for the jvspatial API.

This module provides a consistent exception hierarchy for all API errors,
ensuring uniform error responses and better error tracking.
"""

import logging
from http import HTTPStatus
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class JVSpatialAPIException(Exception):
    """Base exception for all jvspatial API errors.

    Attributes:
        status_code: HTTP status code for the error
        error_code: Machine-readable error code
        default_message: Default human-readable message
        message: Actual error message (overrides default)
        details: Additional error details
    """

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    default_message: str = "An internal error occurred"

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Custom error message (uses default_message if not provided)
            details: Additional context about the error
        """
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    async def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response.

        Returns:
            Dictionary with error_code, message, and optional details
        """
        result: Dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result


# ============================================================================
# Authentication Errors
# ============================================================================


class AuthenticationError(JVSpatialAPIException):
    """Base authentication error."""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "authentication_failed"
    default_message = "Authentication failed"


class InvalidCredentialsError(AuthenticationError):
    """Invalid username or password."""

    error_code = "invalid_credentials"
    default_message = "Invalid username or password"


class TokenExpiredError(AuthenticationError):
    """Authentication token expired."""

    error_code = "token_expired"
    default_message = "Authentication token has expired"


class InvalidTokenError(AuthenticationError):
    """Invalid authentication token."""

    error_code = "invalid_token"
    default_message = "Invalid authentication token"


class MissingAuthenticationError(AuthenticationError):
    """No authentication credentials provided."""

    error_code = "missing_authentication"
    default_message = "Authentication credentials required"


# ============================================================================
# Authorization Errors
# ============================================================================


class AuthorizationError(JVSpatialAPIException):
    """Base authorization error."""

    status_code = HTTPStatus.FORBIDDEN
    error_code = "authorization_failed"
    default_message = "Access denied"


class InsufficientPermissionsError(AuthorizationError):
    """User lacks required permissions."""

    error_code = "insufficient_permissions"
    default_message = "Insufficient permissions"


class InactiveUserError(AuthorizationError):
    """User account is inactive."""

    error_code = "inactive_user"
    default_message = "User account is inactive"


class AdminRequiredError(AuthorizationError):
    """Admin access required."""

    error_code = "admin_required"
    default_message = "Admin access required"


class RoleRequiredError(AuthorizationError):
    """Specific role required."""

    error_code = "role_required"
    default_message = "Required role not assigned"


# ============================================================================
# Resource Errors
# ============================================================================


class ResourceError(JVSpatialAPIException):
    """Base resource error."""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "resource_error"
    default_message = "Resource error"


class ResourceNotFoundError(ResourceError):
    """Resource not found."""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "not_found"
    default_message = "Resource not found"


class ResourceConflictError(ResourceError):
    """Resource conflict (duplicate)."""

    status_code = HTTPStatus.CONFLICT
    error_code = "conflict"
    default_message = "Resource already exists"


class ResourceGoneError(ResourceError):
    """Resource no longer available."""

    status_code = HTTPStatus.GONE
    error_code = "gone"
    default_message = "Resource no longer available"


# ============================================================================
# Validation Errors
# ============================================================================


class ValidationError(JVSpatialAPIException):
    """Validation error."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "validation_error"
    default_message = "Validation failed"


class InvalidInputError(ValidationError):
    """Invalid input provided."""

    error_code = "invalid_input"
    default_message = "Invalid input"


class MissingFieldError(ValidationError):
    """Required field missing."""

    error_code = "missing_field"
    default_message = "Required field missing"


class InvalidFieldError(ValidationError):
    """Field value invalid."""

    error_code = "invalid_field"
    default_message = "Invalid field value"


# ============================================================================
# Storage Errors
# ============================================================================


class StorageError(JVSpatialAPIException):
    """Base storage error."""

    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "storage_error"
    default_message = "Storage operation failed"


class FileNotFoundError(StorageError):
    """File not found in storage."""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "file_not_found"
    default_message = "File not found"


class PathTraversalError(StorageError):
    """Path traversal attempt detected."""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "path_traversal"
    default_message = "Invalid file path"


class FileTooLargeError(StorageError):
    """File exceeds size limit."""

    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    error_code = "file_too_large"
    default_message = "File exceeds maximum size"


class StorageQuotaExceededError(StorageError):
    """Storage quota exceeded."""

    status_code = HTTPStatus.INSUFFICIENT_STORAGE
    error_code = "quota_exceeded"
    default_message = "Storage quota exceeded"


# ============================================================================
# Webhook Errors
# ============================================================================


class WebhookError(JVSpatialAPIException):
    """Base webhook error."""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "webhook_error"
    default_message = "Webhook error"


class InvalidSignatureError(WebhookError):
    """Webhook signature verification failed."""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "invalid_signature"
    default_message = "Invalid webhook signature"


class WebhookPayloadError(WebhookError):
    """Webhook payload error."""

    error_code = "payload_error"
    default_message = "Invalid webhook payload"


# ============================================================================
# Rate Limiting Errors
# ============================================================================


class RateLimitError(JVSpatialAPIException):
    """Rate limit exceeded."""

    status_code = HTTPStatus.TOO_MANY_REQUESTS
    error_code = "rate_limit_exceeded"
    default_message = "Rate limit exceeded"


# ============================================================================
# Configuration Errors
# ============================================================================


class ConfigurationError(JVSpatialAPIException):
    """Configuration error."""

    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "configuration_error"
    default_message = "Configuration error"


class DatabaseError(JVSpatialAPIException):
    """Database operation error."""

    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "database_error"
    default_message = "Database operation failed"


# ============================================================================
# Service Errors
# ============================================================================


class ServiceUnavailableError(JVSpatialAPIException):
    """Service temporarily unavailable."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    error_code = "service_unavailable"
    default_message = "Service temporarily unavailable"


class TimeoutError(JVSpatialAPIException):
    """Operation timed out."""

    status_code = HTTPStatus.GATEWAY_TIMEOUT
    error_code = "timeout"
    default_message = "Operation timed out"


# Export all exception classes
__all__ = [
    # Base
    "JVSpatialAPIException",
    # Authentication
    "AuthenticationError",
    "InvalidCredentialsError",
    "TokenExpiredError",
    "InvalidTokenError",
    "MissingAuthenticationError",
    # Authorization
    "AuthorizationError",
    "InsufficientPermissionsError",
    "InactiveUserError",
    "AdminRequiredError",
    "RoleRequiredError",
    # Resources
    "ResourceError",
    "ResourceNotFoundError",
    "ResourceConflictError",
    "ResourceGoneError",
    # Validation
    "ValidationError",
    "InvalidInputError",
    "MissingFieldError",
    "InvalidFieldError",
    # Storage
    "StorageError",
    "FileNotFoundError",
    "PathTraversalError",
    "FileTooLargeError",
    "StorageQuotaExceededError",
    # Webhook
    "WebhookError",
    "InvalidSignatureError",
    "WebhookPayloadError",
    # Rate Limiting
    "RateLimitError",
    # Configuration
    "ConfigurationError",
    "DatabaseError",
    # Service
    "ServiceUnavailableError",
    "TimeoutError",
]


# ============================================================================
# FastAPI Exception Handlers (merged from error_handlers.py)
# ============================================================================

logger = logging.getLogger(__name__)


async def jvspatial_exception_handler(
    request: Request, exc: "JVSpatialAPIException"
) -> JSONResponse:
    """Handle JVSpatialAPIException instances.

    Args:
        request: The FastAPI request
        exc: The exception instance

    Returns:
        JSON response with error details
    """
    # Log the error
    if exc.status_code >= 500:
        logger.error(
            f"API Error [{exc.error_code}]: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "status_code": exc.status_code,
                "details": exc.details,
                "path": request.url.path,
                "method": request.method,
            },
            exc_info=True,
        )
    else:
        logger.warning(
            f"API Error [{exc.error_code}]: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "status_code": exc.status_code,
                "path": request.url.path,
                "method": request.method,
            },
        )

    # Return standardized error response
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with a FastAPI application.

    Args:
        app: The FastAPI application instance
    """
    app.add_exception_handler(JVSpatialAPIException, jvspatial_exception_handler)
    logger.info("Registered jvspatial exception handlers")
