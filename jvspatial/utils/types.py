"""Common type definitions for jvspatial.

This module provides common type definitions, protocols, and type aliases
used throughout the library for better type safety and documentation.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, TypeVar, Union

from typing_extensions import TypeAlias

# ============================================================================
# Core Type Variables
# ============================================================================

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

# ============================================================================
# Entity Types
# ============================================================================

NodeId: TypeAlias = str
EdgeId: TypeAlias = str
WalkerId: TypeAlias = str
ObjectId: TypeAlias = str

# ============================================================================
# Graph Types
# ============================================================================

GraphData: TypeAlias = Dict[str, Any]
NodeData: TypeAlias = Dict[str, Any]
EdgeData: TypeAlias = Dict[str, Any]
WalkerData: TypeAlias = Dict[str, Any]

# ============================================================================
# API Types
# ============================================================================

HTTPMethod: TypeAlias = str
HTTPStatus: TypeAlias = int
APIResponse: TypeAlias = Dict[str, Any]
EndpointPath: TypeAlias = str

# ============================================================================
# Database Types
# ============================================================================

DatabaseUrl: TypeAlias = str
CollectionName: TypeAlias = str
QueryFilter: TypeAlias = Dict[str, Any]
QueryOptions: TypeAlias = Dict[str, Any]

# ============================================================================
# Cache Types
# ============================================================================

CacheKey: TypeAlias = str
CacheValue: TypeAlias = Any
CacheTTL: TypeAlias = int

# ============================================================================
# Storage Types
# ============================================================================

FilePath: TypeAlias = str
FileContent: TypeAlias = bytes
FileMetadata: TypeAlias = Dict[str, Any]

# ============================================================================
# Protocol Definitions
# ============================================================================


class Serializable(Protocol):
    """Protocol for objects that can be serialized."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert object to dictionary."""
        ...


class Deserializable(Protocol):
    """Protocol for objects that can be deserialized."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Any:
        """Create object from dictionary."""
        ...


class Cacheable(Protocol):
    """Protocol for objects that can be cached."""

    def cache_key(self) -> str:
        """Get cache key for object."""
        ...


class Validatable(Protocol):
    """Protocol for objects that can be validated."""

    def validate(self) -> bool:
        """Validate object."""
        ...


class Configurable(Protocol):
    """Protocol for objects that can be configured."""

    def configure(self, **kwargs: Any) -> None:
        """Configure object with parameters."""
        ...


# ============================================================================
# Function Type Aliases
# ============================================================================

AsyncFunction: TypeAlias = Callable[..., Any]
SyncFunction: TypeAlias = Callable[..., Any]
DecoratorFunction: TypeAlias = Callable[[T], T]
FactoryFunction: TypeAlias = Callable[[], T]
ValidatorFunction: TypeAlias = Callable[[Any], bool]
TransformerFunction: TypeAlias = Callable[[Any], Any]

# ============================================================================
# Event Types
# ============================================================================

EventHandler: TypeAlias = Callable[[Any], None]
EventData: TypeAlias = Dict[str, Any]
EventName: TypeAlias = str

# ============================================================================
# Context Types
# ============================================================================

ContextData: TypeAlias = Dict[str, Any]
ContextKey: TypeAlias = str
ContextValue: TypeAlias = Any

# ============================================================================
# Error Types
# ============================================================================

ErrorCode: TypeAlias = str
ErrorMessage: TypeAlias = str
ErrorDetails: TypeAlias = Dict[str, Any]

# ============================================================================
# Configuration Types
# ============================================================================

ConfigValue: TypeAlias = Union[str, int, float, bool, List[str], Dict[str, Any]]
ConfigSection: TypeAlias = Dict[str, ConfigValue]
ConfigData: TypeAlias = Dict[str, ConfigSection]

# ============================================================================
# Utility Types
# ============================================================================

OptionalStr: TypeAlias = Optional[str]
OptionalInt: TypeAlias = Optional[int]
OptionalFloat: TypeAlias = Optional[float]
OptionalBool: TypeAlias = Optional[bool]
OptionalList: TypeAlias = Optional[List[T]]
OptionalDict: TypeAlias = Optional[Dict[K, V]]

# ============================================================================
# Generic Container Types
# ============================================================================

StringDict: TypeAlias = Dict[str, str]
StringList: TypeAlias = List[str]
AnyDict: TypeAlias = Dict[str, Any]
AnyList: TypeAlias = List[Any]

# ============================================================================
# Union Types
# ============================================================================

StringOrInt: TypeAlias = Union[str, int]
StringOrFloat: TypeAlias = Union[str, float]
StringOrBool: TypeAlias = Union[str, bool]
IntOrFloat: TypeAlias = Union[int, float]

# ============================================================================
# Special Types
# ============================================================================

JSONData: TypeAlias = Union[Dict[str, Any], List[Any], str, int, float, bool, None]
JSONDict: TypeAlias = Dict[str, JSONData]
JSONList: TypeAlias = List[JSONData]

# ============================================================================
# Type Guards
# ============================================================================


def is_string(value: Any) -> bool:
    """Check if value is a string."""
    return isinstance(value, str)


def is_integer(value: Any) -> bool:
    """Check if value is an integer."""
    return isinstance(value, int)


def is_float(value: Any) -> bool:
    """Check if value is a float."""
    return isinstance(value, float)


def is_boolean(value: Any) -> bool:
    """Check if value is a boolean."""
    return isinstance(value, bool)


def is_dict(value: Any) -> bool:
    """Check if value is a dictionary."""
    return isinstance(value, dict)


def is_list(value: Any) -> bool:
    """Check if value is a list."""
    return isinstance(value, list)


def is_callable(value: Any) -> bool:
    """Check if value is callable."""
    return callable(value)


def is_async_callable(value: Any) -> bool:
    """Check if value is an async callable."""
    return (
        callable(value)
        and hasattr(value, "__code__")
        and value.__code__.co_flags & 0x80
    )


# ============================================================================
# Type Conversion Helpers
# ============================================================================


def to_string(value: Any) -> str:
    """Convert value to string."""
    return str(value)


def to_integer(value: Any) -> int:
    """Convert value to integer."""
    return int(value)


def to_float(value: Any) -> float:
    """Convert value to float."""
    return float(value)


def to_boolean(value: Any) -> bool:
    """Convert value to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return bool(value)


def to_dict(value: Any) -> Dict[str, Any]:
    """Convert value to dictionary."""
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        if isinstance(result, dict):
            return result
        return {"value": result}
    if hasattr(value, "__dict__"):
        result = value.__dict__
        if isinstance(result, dict):
            return result
        return {"value": result}
    raise ValueError(f"Cannot convert {type(value)} to dict")


def to_list(value: Any) -> List[Any]:
    """Convert value to list."""
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


__all__ = [
    # Type Variables
    "T",
    "K",
    "V",
    # Entity Types
    "NodeId",
    "EdgeId",
    "WalkerId",
    "ObjectId",
    # Graph Types
    "GraphData",
    "NodeData",
    "EdgeData",
    "WalkerData",
    # API Types
    "HTTPMethod",
    "HTTPStatus",
    "APIResponse",
    "EndpointPath",
    # Database Types
    "DatabaseUrl",
    "CollectionName",
    "QueryFilter",
    "QueryOptions",
    # Cache Types
    "CacheKey",
    "CacheValue",
    "CacheTTL",
    # Storage Types
    "FilePath",
    "FileContent",
    "FileMetadata",
    # Protocols
    "Serializable",
    "Deserializable",
    "Cacheable",
    "Validatable",
    "Configurable",
    # Function Types
    "AsyncFunction",
    "SyncFunction",
    "DecoratorFunction",
    "FactoryFunction",
    "ValidatorFunction",
    "TransformerFunction",
    # Event Types
    "EventHandler",
    "EventData",
    "EventName",
    # Context Types
    "ContextData",
    "ContextKey",
    "ContextValue",
    # Error Types
    "ErrorCode",
    "ErrorMessage",
    "ErrorDetails",
    # Configuration Types
    "ConfigValue",
    "ConfigSection",
    "ConfigData",
    # Utility Types
    "OptionalStr",
    "OptionalInt",
    "OptionalFloat",
    "OptionalBool",
    "OptionalList",
    "OptionalDict",
    # Container Types
    "StringDict",
    "StringList",
    "AnyDict",
    "AnyList",
    # Union Types
    "StringOrInt",
    "StringOrFloat",
    "StringOrBool",
    "IntOrFloat",
    # Special Types
    "JSONData",
    "JSONDict",
    "JSONList",
    # Type Guards
    "is_string",
    "is_integer",
    "is_float",
    "is_boolean",
    "is_dict",
    "is_list",
    "is_callable",
    "is_async_callable",
    # Conversion Helpers
    "to_string",
    "to_integer",
    "to_float",
    "to_boolean",
    "to_dict",
    "to_list",
]
