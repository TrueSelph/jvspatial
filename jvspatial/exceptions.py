"""
jvspatial exceptions module.

This module provides a centralized collection of all jvspatial exceptions while
maintaining separation of concerns by importing from specialized modules.

The hybrid approach provides:
1. Centralized access: from jvspatial.exceptions import NodeNotFoundError
2. Modular definitions: Exceptions defined in their respective domains
3. No circular imports: Base exceptions here, specific ones in modules
"""

import contextlib
from typing import Any, Dict, Optional

# Import API exceptions for re-export
# Note: Some exceptions are defined locally below, so we import only those
# that are not locally defined
try:
    from jvspatial.api.exceptions import (
        AuthenticationError,
        AuthorizationError,
        InvalidCredentialsError,
        JVSpatialAPIException,
        RateLimitError,
    )
except ImportError:
    # Fallback if API module is not available - use type: ignore for mypy
    # These will be None if API module is unavailable, but that's acceptable
    AuthenticationError = None  # type: ignore[assignment,misc]
    AuthorizationError = None  # type: ignore[assignment,misc]
    InvalidCredentialsError = None  # type: ignore[assignment,misc]
    JVSpatialAPIException = None  # type: ignore[assignment,misc]
    RateLimitError = None  # type: ignore[assignment,misc]

# =============================================================================
# BASE EXCEPTIONS - Defined here to avoid circular imports
# =============================================================================


class JVSpatialError(Exception):
    """Base exception for all jvspatial-related errors.

    All jvspatial exceptions inherit from this base class to provide
    consistent error handling and reporting capabilities.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation of the exception."""
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class EntityError(JVSpatialError):
    """Base exception for entity-related operations."""

    pass


class ValidationError(JVSpatialError):
    """Base exception for validation errors."""

    def __init__(
        self,
        message: str,
        field_errors: Optional[Dict[str, str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.field_errors = field_errors or {}


class ConfigurationError(JVSpatialError):
    """Base exception for configuration-related errors."""

    pass


# =============================================================================
# COMMON ENTITY EXCEPTIONS - Used across modules
# =============================================================================


class EntityNotFoundError(EntityError):
    """Raised when an entity is not found in the database."""

    def __init__(
        self, entity_type: str, entity_id: str, details: Optional[Dict[str, Any]] = None
    ):
        message = f"{entity_type} with ID '{entity_id}' not found"
        super().__init__(message, details)
        self.entity_type = entity_type
        self.entity_id = entity_id


class NodeNotFoundError(EntityNotFoundError):
    """Raised when a node is not found in the database."""

    def __init__(self, node_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("Node", node_id, details)


class EdgeNotFoundError(EntityNotFoundError):
    """Raised when an edge is not found in the database."""

    def __init__(self, edge_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("Edge", edge_id, details)


class ObjectNotFoundError(EntityNotFoundError):
    """Raised when an object is not found in the database."""

    def __init__(self, object_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("Object", object_id, details)


class DuplicateEntityError(EntityError):
    """Raised when attempting to create an entity with a duplicate ID."""

    def __init__(
        self, entity_type: str, entity_id: str, details: Optional[Dict[str, Any]] = None
    ):
        message = f"{entity_type} with ID '{entity_id}' already exists"
        super().__init__(message, details)
        self.entity_type = entity_type
        self.entity_id = entity_id


class FieldValidationError(ValidationError):
    """Raised when a specific field fails validation."""

    def __init__(
        self,
        field_name: str,
        field_value: Any,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"Validation failed for field '{field_name}' with value '{field_value}': {reason}"
        field_errors = {field_name: reason}
        super().__init__(message, field_errors, details)
        self.field_name = field_name
        self.field_value = field_value
        self.reason = reason


# =============================================================================
# MODULE-SPECIFIC EXCEPTION IMPORTS
# =============================================================================

# Import core exceptions
with contextlib.suppress(ImportError):
    from .core.entities import (  # type: ignore[attr-defined]
        TraversalPaused,
        TraversalSkipped,
    )


# Import database exceptions
with contextlib.suppress(ImportError):
    from .db.database import VersionConflictError  # type: ignore[attr-defined]


# Import API exceptions from api module
with contextlib.suppress(ImportError):
    from .api.exceptions import JVSpatialAPIException  # type: ignore[attr-defined]


# =============================================================================
# ADDITIONAL DOMAIN-SPECIFIC EXCEPTIONS
# =============================================================================


# Database exceptions
class DatabaseError(JVSpatialError):
    """Base exception for database-related operations."""

    pass


class ConnectionError(DatabaseError):
    """Raised when database connection fails."""

    def __init__(
        self,
        database_type: str,
        connection_string: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"Failed to connect to {database_type} database"
        if connection_string:
            message += f" at '{connection_string}'"
        super().__init__(message, details)
        self.database_type = database_type
        self.connection_string = connection_string


class QueryError(DatabaseError):
    """Raised when a database query fails."""

    def __init__(
        self, query: str, reason: str, details: Optional[Dict[str, Any]] = None
    ):
        message = f"Query failed: {reason}"
        super().__init__(message, details)
        self.query = query
        self.reason = reason


class TransactionError(DatabaseError):
    """Raised when a database transaction fails."""

    def __init__(
        self, operation: str, reason: str, details: Optional[Dict[str, Any]] = None
    ):
        message = f"Transaction failed during {operation}: {reason}"
        super().__init__(message, details)
        self.operation = operation
        self.reason = reason


# Graph exceptions
class GraphError(JVSpatialError):
    """Base exception for graph-related operations."""

    pass


class InvalidGraphStructureError(GraphError):
    """Raised when graph structure is invalid."""

    def __init__(self, reason: str, details: Optional[Dict[str, Any]] = None):
        message = f"Invalid graph structure: {reason}"
        super().__init__(message, details)
        self.reason = reason


class CircularReferenceError(GraphError):
    """Raised when a circular reference is detected."""

    def __init__(self, path: list, details: Optional[Dict[str, Any]] = None):
        message = f"Circular reference detected in path: {' -> '.join(map(str, path))}"
        super().__init__(message, details)
        self.path = path


class EdgeConnectionError(GraphError):
    """Raised when edge connection is invalid."""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"Cannot connect '{source_id}' to '{target_id}': {reason}"
        super().__init__(message, details)
        self.source_id = source_id
        self.target_id = target_id
        self.reason = reason


# Walker exceptions
class WalkerError(JVSpatialError):
    """Base exception for walker-related operations."""

    pass


class WalkerExecutionError(WalkerError):
    """Raised when walker execution fails."""

    def __init__(
        self, walker_class: str, reason: str, details: Optional[Dict[str, Any]] = None
    ):
        message = f"Walker execution failed for {walker_class}: {reason}"
        super().__init__(message, details)
        self.walker_class = walker_class
        self.reason = reason


class WalkerTimeoutError(WalkerError):
    """Raised when walker execution times out."""

    def __init__(
        self,
        walker_class: str,
        timeout_seconds: float,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"Walker {walker_class} timed out after {timeout_seconds} seconds"
        super().__init__(message, details)
        self.walker_class = walker_class
        self.timeout_seconds = timeout_seconds


class InfiniteLoopError(WalkerError):
    """Raised when walker gets stuck in an infinite loop."""

    def __init__(
        self,
        walker_class: str,
        node_id: str,
        visit_count: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"Infinite loop detected: Walker {walker_class} visited node '{node_id}' {visit_count} times"
        super().__init__(message, details)
        self.walker_class = walker_class
        self.node_id = node_id
        self.visit_count = visit_count


# API exceptions
class APIError(JVSpatialError):
    """Base exception for API-related operations."""

    pass


class EndpointError(APIError):
    """Raised when API endpoint encounters an error."""

    def __init__(
        self,
        endpoint: str,
        method: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"{method} {endpoint} failed: {reason}"
        super().__init__(message, details)
        self.endpoint = endpoint
        self.method = method
        self.reason = reason


class ParameterError(APIError):
    """Raised when API parameter is invalid."""

    def __init__(
        self,
        parameter: str,
        value: Any,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = f"Invalid parameter '{parameter}' = '{value}': {reason}"
        super().__init__(message, details)
        self.parameter = parameter
        self.value = value
        self.reason = reason


# Security exceptions
class SecurityError(JVSpatialError):
    """Base exception for security-related errors."""

    pass


class PermissionDeniedError(SecurityError):
    """Raised when operation is not permitted."""

    def __init__(
        self,
        operation: str,
        resource: str,
        user: str = "",
        details: Optional[Dict[str, Any]] = None,
    ):
        message = (
            f"Permission denied for operation '{operation}' on resource '{resource}'"
        )
        if user:
            message += f" for user '{user}'"
        super().__init__(message, details)
        self.operation = operation
        self.resource = resource
        self.user = user


# Configuration exceptions
class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration is invalid."""

    def __init__(
        self,
        config_key: str,
        config_value: Any,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        message = (
            f"Invalid configuration for '{config_key}' = '{config_value}': {reason}"
        )
        super().__init__(message, details)
        self.config_key = config_key
        self.config_value = config_value
        self.reason = reason


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration is missing."""

    def __init__(self, config_key: str, details: Optional[Dict[str, Any]] = None):
        message = f"Required configuration '{config_key}' is missing"
        super().__init__(message, details)
        self.config_key = config_key


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Base exceptions
    "JVSpatialError",
    "EntityError",
    "ValidationError",
    "ConfigurationError",
    # Common entity exceptions
    "EntityNotFoundError",
    "NodeNotFoundError",
    "EdgeNotFoundError",
    "ObjectNotFoundError",
    "DuplicateEntityError",
    "FieldValidationError",
    # Core exceptions (from entities)
    "TraversalPaused",
    "TraversalSkipped",
    # Database exceptions
    "DatabaseError",
    "VersionConflictError",
    "ConnectionError",
    "QueryError",
    "TransactionError",
    # Graph exceptions
    "GraphError",
    "InvalidGraphStructureError",
    "CircularReferenceError",
    "EdgeConnectionError",
    # Walker exceptions
    "WalkerError",
    "WalkerExecutionError",
    "WalkerTimeoutError",
    "InfiniteLoopError",
    # API exceptions (imported from jvspatial.api.exceptions)
    "APIError",
    "JVSpatialAPIException",
    "EndpointError",
    "ParameterError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitError",
    "InvalidCredentialsError",
    # Note: UserNotFoundError, SessionExpiredError, APIKeyInvalidError
    # are not currently defined - removed from exports
    # Security exceptions
    "SecurityError",
    "PermissionDeniedError",
    # Configuration exceptions
    "InvalidConfigurationError",
    "MissingConfigurationError",
]
