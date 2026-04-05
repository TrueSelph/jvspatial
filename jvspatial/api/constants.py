"""Constants for the jvspatial API module.

This module provides centralized constants for routes, HTTP methods,
collection names, and other magic strings used throughout the API.

Values resolve from live environment reads on each attribute access.
"""

from http import HTTPStatus
from typing import Any, List

from jvspatial.env import (
    env,
    parse_bool_basic,
    parse_csv,
    resolve_cors_origins,
    resolve_files_route_base,
)


class _EnvAttr:
    """Descriptor: return transformed environment value on each access."""

    def __init__(self, resolver):
        self._resolver = resolver

    def __get__(self, obj: Any, owner: type) -> Any:
        return self._resolver()


class _FilesJoin:
    """Append a path segment to files route base."""

    def __init__(self, suffix: str):
        self._suffix = suffix

    def __get__(self, obj: Any, owner: type) -> str:
        base = resolve_files_route_base()
        return f"{base}{self._suffix}"


class APIRoutes:
    """API route path constants (resolved from env on access)."""

    PREFIX = _EnvAttr(lambda: env("JVSPATIAL_API_PREFIX", default="/api"))
    HEALTH = _EnvAttr(lambda: env("JVSPATIAL_API_HEALTH", default="/health"))
    ROOT = _EnvAttr(lambda: env("JVSPATIAL_API_ROOT", default="/"))

    FILES_ROOT = _EnvAttr(resolve_files_route_base)
    FILES_UPLOAD = _FilesJoin("/upload")
    FILES_PROXY = _FilesJoin("/proxy")

    PROXY_PREFIX = _EnvAttr(lambda: env("JVSPATIAL_PROXY_PREFIX", default="/p"))

    DEFERRED_INVOKE_SUFFIX = "/_internal/deferred"

    @classmethod
    def deferred_invoke_full_path(cls) -> str:
        """Full URL path for LWA pass-through and POST deferred invocations."""
        prefix = str(cls.PREFIX).rstrip("/")
        suffix = cls.DEFERRED_INVOKE_SUFFIX
        return f"{prefix}{suffix}" if prefix else suffix


class HTTPMethods:
    """Standard HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class Collections:
    """Database collection names (resolved from env on access)."""

    USERS = _EnvAttr(lambda: env("JVSPATIAL_COLLECTION_USERS", default="users"))
    API_KEYS = _EnvAttr(
        lambda: env("JVSPATIAL_COLLECTION_API_KEYS", default="api_keys")
    )  # pragma: allowlist secret
    SESSIONS = _EnvAttr(
        lambda: env("JVSPATIAL_COLLECTION_SESSIONS", default="sessions")
    )
    WEBHOOKS = _EnvAttr(
        lambda: env("JVSPATIAL_COLLECTION_WEBHOOKS", default="webhooks")
    )
    WEBHOOK_REQUESTS = _EnvAttr(
        lambda: env("JVSPATIAL_COLLECTION_WEBHOOK_REQUESTS", default="webhook_requests")
    )
    SCHEDULED_TASKS = _EnvAttr(
        lambda: env("JVSPATIAL_COLLECTION_SCHEDULED_TASKS", default="scheduled_tasks")
    )


class LogIcons:
    """Emoji icons for consistent logging."""

    START = "🚀"
    STOP = "🛑"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    DATABASE = "📊"
    STORAGE = "📁"
    NETWORK = "🔌"
    DISCOVERY = "🔍"
    REGISTERED = "📝"
    UNREGISTERED = "🗑️"
    DYNAMIC = "🔄"
    WEBHOOK = "🔗"
    CONTEXT = "🎯"
    HEALTH = "🏥"
    CONFIG = "🔧"
    TREE = "🌳"
    PACKAGE = "📦"
    DEBUG = "🐛"
    WORLD = "🌐"


class ErrorMessages:
    """Standard error messages."""

    AUTH_REQUIRED = "Authentication required"
    INVALID_CREDENTIALS = "Invalid credentials"
    TOKEN_EXPIRED = "Authentication token has expired"
    INVALID_TOKEN = "Invalid authentication token"

    INACTIVE_USER = "User account is inactive"
    ADMIN_REQUIRED = "Admin access required"
    PERMISSION_DENIED = "Permission denied"
    INSUFFICIENT_PERMISSIONS = "Insufficient permissions"

    NOT_FOUND = "Resource not found"
    ALREADY_EXISTS = "Resource already exists"
    CONFLICT = "Resource conflict"

    VALIDATION_FAILED = "Validation failed"
    INVALID_INPUT = "Invalid input"

    FILE_NOT_FOUND = "File not found"
    STORAGE_ERROR = "Storage operation failed"
    PATH_TRAVERSAL = "Invalid file path"
    FILE_TOO_LARGE = "File exceeds maximum size"

    INTERNAL_ERROR = "Internal server error"
    SERVICE_UNAVAILABLE = "Service temporarily unavailable"


class _CorsListCopy:
    def __get__(self, obj: Any, owner: type) -> List[str]:
        return list(resolve_cors_origins())


class _CorsMethodsCopy:
    def __get__(self, obj: Any, owner: type) -> List[str]:
        return list(env("JVSPATIAL_CORS_METHODS", default=["*"], parse=parse_csv))


class _CorsHeadersCopy:
    def __get__(self, obj: Any, owner: type) -> List[str]:
        return list(env("JVSPATIAL_CORS_HEADERS", default=["*"], parse=parse_csv))


class Defaults:
    """Default configuration values (resolved from env on access)."""

    API_TITLE = _EnvAttr(lambda: env("JVSPATIAL_API_TITLE", default="jvspatial API"))
    API_VERSION = _EnvAttr(lambda: env("JVSPATIAL_API_VERSION", default="1.0.0"))
    API_DESCRIPTION = _EnvAttr(
        lambda: env(
            "JVSPATIAL_API_DESCRIPTION", default="API built with jvspatial framework"
        )
    )

    HOST = _EnvAttr(lambda: env("JVSPATIAL_HOST", default="0.0.0.0"))
    PORT = _EnvAttr(lambda: env("JVSPATIAL_PORT", default=8000, parse=int))
    LOG_LEVEL = _EnvAttr(lambda: env("JVSPATIAL_LOG_LEVEL", default="info"))
    DEBUG = _EnvAttr(
        lambda: env("JVSPATIAL_DEBUG", default=False, parse=parse_bool_basic)
    )

    CORS_ENABLED = _EnvAttr(
        lambda: env("JVSPATIAL_CORS_ENABLED", default=True, parse=parse_bool_basic)
    )
    CORS_ORIGINS = _CorsListCopy()
    CORS_METHODS = _CorsMethodsCopy()
    CORS_HEADERS = _CorsHeadersCopy()

    FILE_STORAGE_ENABLED = _EnvAttr(
        lambda: env(
            "JVSPATIAL_FILE_STORAGE_ENABLED", default=False, parse=parse_bool_basic
        )
    )
    FILE_STORAGE_PROVIDER = _EnvAttr(
        lambda: env("JVSPATIAL_FILE_STORAGE_PROVIDER", default="local")
    )
    FILE_STORAGE_ROOT = _EnvAttr(
        lambda: env("JVSPATIAL_FILES_ROOT_PATH", default="./.files")
    )
    FILE_STORAGE_MAX_SIZE = _EnvAttr(
        lambda: env(
            "JVSPATIAL_FILE_STORAGE_MAX_SIZE", default=100 * 1024 * 1024, parse=int
        )
    )
    FILE_STORAGE_BASE_URL = _EnvAttr(
        lambda: env("JVSPATIAL_FILE_STORAGE_BASE_URL", default="http://localhost:8000")
    )
    FILES_PUBLIC_READ = _EnvAttr(
        lambda: env("JVSPATIAL_FILES_PUBLIC_READ", default=True, parse=parse_bool_basic)
    )

    PROXY_ENABLED = _EnvAttr(
        lambda: env("JVSPATIAL_PROXY_ENABLED", default=False, parse=parse_bool_basic)
    )
    PROXY_EXPIRATION = _EnvAttr(
        lambda: env("JVSPATIAL_PROXY_DEFAULT_EXPIRATION", default=3600, parse=int)
    )
    PROXY_MAX_EXPIRATION = _EnvAttr(
        lambda: env("JVSPATIAL_PROXY_MAX_EXPIRATION", default=86400, parse=int)
    )

    DB_TYPE = _EnvAttr(lambda: env("JVSPATIAL_DB_TYPE", default="json"))
    DB_PATH = _EnvAttr(
        lambda: env("JVSPATIAL_DB_PATH", default="jvdb/sqlite/jvspatial.db")
    )


__all__ = [
    "APIRoutes",
    "HTTPMethods",
    "Collections",
    "LogIcons",
    "ErrorMessages",
    "Defaults",
    "HTTPStatus",
]
