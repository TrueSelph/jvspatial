"""Constants for the jvspatial API module.

This module provides centralized constants for routes, HTTP methods,
collection names, and other magic strings used throughout the API.

Values resolve from :func:`jvspatial.env.load_env` on each attribute read so
environment changes take effect after :func:`~jvspatial.env.clear_load_env_cache`.
"""

from http import HTTPStatus
from typing import Any, List

from jvspatial.env import load_env


class _EnvAttr:
    """Descriptor: return ``getattr(load_env(), attr_name)``."""

    def __init__(self, attr_name: str):
        self._attr_name = attr_name

    def __get__(self, obj: Any, owner: type) -> Any:
        return getattr(load_env(), self._attr_name)


class _StorageJoin:
    """Append a path segment to ``load_env().storage_prefix``."""

    def __init__(self, suffix: str):
        self._suffix = suffix

    def __get__(self, obj: Any, owner: type) -> str:
        base = load_env().storage_prefix
        return f"{base}{self._suffix}"


class APIRoutes:
    """API route path constants (resolved via load_env on access)."""

    PREFIX = _EnvAttr("api_prefix")
    HEALTH = _EnvAttr("api_health")
    ROOT = _EnvAttr("api_root")

    STORAGE_PREFIX = _EnvAttr("storage_prefix")
    STORAGE_UPLOAD = _StorageJoin("/upload")
    STORAGE_FILES = _StorageJoin("/files")
    STORAGE_PROXY = _StorageJoin("/proxy")

    PROXY_PREFIX = _EnvAttr("proxy_prefix")

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
    """Database collection names (resolved via load_env on access)."""

    USERS = _EnvAttr("collection_users")
    API_KEYS = _EnvAttr("collection_api_keys")  # pragma: allowlist secret
    SESSIONS = _EnvAttr("collection_sessions")
    WEBHOOKS = _EnvAttr("collection_webhooks")
    WEBHOOK_REQUESTS = _EnvAttr("collection_webhook_requests")
    SCHEDULED_TASKS = _EnvAttr("collection_scheduled_tasks")


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
        return list(load_env().cors_origins)


class _CorsMethodsCopy:
    def __get__(self, obj: Any, owner: type) -> List[str]:
        return list(load_env().cors_methods)


class _CorsHeadersCopy:
    def __get__(self, obj: Any, owner: type) -> List[str]:
        return list(load_env().cors_headers)


class Defaults:
    """Default configuration values (resolved via load_env on access)."""

    API_TITLE = _EnvAttr("api_title")
    API_VERSION = _EnvAttr("api_version")
    API_DESCRIPTION = _EnvAttr("api_description")

    HOST = _EnvAttr("host")
    PORT = _EnvAttr("port")
    LOG_LEVEL = _EnvAttr("log_level")
    DEBUG = _EnvAttr("debug")

    CORS_ENABLED = _EnvAttr("cors_enabled")
    CORS_ORIGINS = _CorsListCopy()
    CORS_METHODS = _CorsMethodsCopy()
    CORS_HEADERS = _CorsHeadersCopy()

    FILE_STORAGE_ENABLED = _EnvAttr("file_storage_enabled")
    FILE_STORAGE_PROVIDER = _EnvAttr("file_storage_provider")
    FILE_STORAGE_ROOT = _EnvAttr("file_storage_root")
    FILE_STORAGE_MAX_SIZE = _EnvAttr("file_storage_max_size")
    FILE_STORAGE_BASE_URL = _EnvAttr("file_storage_base_url")

    PROXY_ENABLED = _EnvAttr("proxy_enabled")
    PROXY_EXPIRATION = _EnvAttr("proxy_expiration")
    PROXY_MAX_EXPIRATION = _EnvAttr("proxy_max_expiration")

    DB_TYPE = _EnvAttr("db_type")
    DB_PATH = _EnvAttr("db_path")


__all__ = [
    "APIRoutes",
    "HTTPMethods",
    "Collections",
    "LogIcons",
    "ErrorMessages",
    "Defaults",
    "HTTPStatus",
]
