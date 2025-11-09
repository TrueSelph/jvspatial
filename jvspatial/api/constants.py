"""Constants for the jvspatial API module.

This module provides centralized constants for routes, HTTP methods,
collection names, and other magic strings used throughout the API.

All constants can be overridden via environment variables with the prefix 'JVSPATIAL_'.
For example, to override APIRoutes.PREFIX, set JVSPATIAL_API_PREFIX in your environment.
"""

import os
from http import HTTPStatus


class APIRoutes:
    """API route path constants.

    All values can be overridden via environment variables:
    - JVSPATIAL_API_PREFIX
    - JVSPATIAL_API_HEALTH
    - JVSPATIAL_API_ROOT
    - JVSPATIAL_STORAGE_PREFIX
    - JVSPATIAL_PROXY_PREFIX
    """

    # Core routes
    PREFIX = os.getenv("JVSPATIAL_API_PREFIX", "/api")
    HEALTH = os.getenv("JVSPATIAL_API_HEALTH", "/health")
    ROOT = os.getenv("JVSPATIAL_API_ROOT", "/")

    # Storage routes
    STORAGE_PREFIX = os.getenv("JVSPATIAL_STORAGE_PREFIX", "/storage")
    STORAGE_UPLOAD = f"{STORAGE_PREFIX}/upload"
    STORAGE_FILES = f"{STORAGE_PREFIX}/files"
    STORAGE_PROXY = f"{STORAGE_PREFIX}/proxy"

    # Proxy routes
    PROXY_PREFIX = os.getenv("JVSPATIAL_PROXY_PREFIX", "/p")


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
    """Database collection names.

    All values can be overridden via environment variables:
    - JVSPATIAL_COLLECTION_USERS
    - JVSPATIAL_COLLECTION_API_KEYS
    - JVSPATIAL_COLLECTION_SESSIONS
    - JVSPATIAL_COLLECTION_WEBHOOKS
    - JVSPATIAL_COLLECTION_WEBHOOK_REQUESTS
    - JVSPATIAL_COLLECTION_SCHEDULED_TASKS
    """

    USERS = os.getenv("JVSPATIAL_COLLECTION_USERS", "users")
    API_KEYS = os.getenv(
        "JVSPATIAL_COLLECTION_API_KEYS", "api_keys"
    )  # pragma: allowlist secret
    SESSIONS = os.getenv("JVSPATIAL_COLLECTION_SESSIONS", "sessions")
    WEBHOOKS = os.getenv("JVSPATIAL_COLLECTION_WEBHOOKS", "webhooks")
    WEBHOOK_REQUESTS = os.getenv(
        "JVSPATIAL_COLLECTION_WEBHOOK_REQUESTS", "webhook_requests"
    )
    SCHEDULED_TASKS = os.getenv(
        "JVSPATIAL_COLLECTION_SCHEDULED_TASKS", "scheduled_tasks"
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

    # Authentication
    AUTH_REQUIRED = "Authentication required"
    INVALID_CREDENTIALS = "Invalid credentials"
    TOKEN_EXPIRED = "Authentication token has expired"
    INVALID_TOKEN = "Invalid authentication token"

    # Authorization
    INACTIVE_USER = "User account is inactive"
    ADMIN_REQUIRED = "Admin access required"
    PERMISSION_DENIED = "Permission denied"
    INSUFFICIENT_PERMISSIONS = "Insufficient permissions"

    # Resources
    NOT_FOUND = "Resource not found"
    ALREADY_EXISTS = "Resource already exists"
    CONFLICT = "Resource conflict"

    # Validation
    VALIDATION_FAILED = "Validation failed"
    INVALID_INPUT = "Invalid input"

    # Storage
    FILE_NOT_FOUND = "File not found"
    STORAGE_ERROR = "Storage operation failed"
    PATH_TRAVERSAL = "Invalid file path"
    FILE_TOO_LARGE = "File exceeds maximum size"

    # Generic
    INTERNAL_ERROR = "Internal server error"
    SERVICE_UNAVAILABLE = "Service temporarily unavailable"


class Defaults:
    """Default configuration values.

    All values can be overridden via environment variables with 'JVSPATIAL_' prefix.
    For boolean values, use 'true', '1', 'yes' for True, anything else for False.
    For list values (like CORS_ORIGINS), use comma-separated strings.
    """

    # API
    API_TITLE = os.getenv("JVSPATIAL_API_TITLE", "jvspatial API")
    API_VERSION = os.getenv("JVSPATIAL_API_VERSION", "1.0.0")
    API_DESCRIPTION = os.getenv(
        "JVSPATIAL_API_DESCRIPTION", "API built with jvspatial framework"
    )

    # Server
    HOST = os.getenv("JVSPATIAL_HOST", "0.0.0.0")
    PORT = int(os.getenv("JVSPATIAL_PORT", "8000"))
    LOG_LEVEL = os.getenv("JVSPATIAL_LOG_LEVEL", "info")
    DEBUG = os.getenv("JVSPATIAL_DEBUG", "false").lower() in ("true", "1", "yes")

    # CORS
    CORS_ENABLED = os.getenv("JVSPATIAL_CORS_ENABLED", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    CORS_ORIGINS = (
        os.getenv("JVSPATIAL_CORS_ORIGINS", "*").split(",")
        if os.getenv("JVSPATIAL_CORS_ORIGINS")
        else ["*"]
    )
    CORS_METHODS = (
        os.getenv("JVSPATIAL_CORS_METHODS", "*").split(",")
        if os.getenv("JVSPATIAL_CORS_METHODS")
        else ["*"]
    )
    CORS_HEADERS = (
        os.getenv("JVSPATIAL_CORS_HEADERS", "*").split(",")
        if os.getenv("JVSPATIAL_CORS_HEADERS")
        else ["*"]
    )

    # File Storage
    FILE_STORAGE_ENABLED = os.getenv(
        "JVSPATIAL_FILE_STORAGE_ENABLED", "false"
    ).lower() in ("true", "1", "yes")
    FILE_STORAGE_PROVIDER = os.getenv("JVSPATIAL_FILE_STORAGE_PROVIDER", "local")
    FILE_STORAGE_ROOT = os.getenv("JVSPATIAL_FILE_STORAGE_ROOT", ".files")
    FILE_STORAGE_MAX_SIZE = int(
        os.getenv("JVSPATIAL_FILE_STORAGE_MAX_SIZE", str(100 * 1024 * 1024))
    )  # 100MB
    FILE_STORAGE_BASE_URL = os.getenv(
        "JVSPATIAL_FILE_STORAGE_BASE_URL", "http://localhost:8000"
    )

    # Proxy
    PROXY_ENABLED = os.getenv("JVSPATIAL_PROXY_ENABLED", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    PROXY_EXPIRATION = int(os.getenv("JVSPATIAL_PROXY_EXPIRATION", "3600"))  # 1 hour
    PROXY_MAX_EXPIRATION = int(
        os.getenv("JVSPATIAL_PROXY_MAX_EXPIRATION", "86400")
    )  # 24 hours

    # Database
    DB_TYPE = os.getenv("JVSPATIAL_DB_TYPE", "json")
    DB_PATH = os.getenv("JVSPATIAL_DB_PATH", "./jvdb")


# Re-export HTTPStatus for convenience
__all__ = [
    "APIRoutes",
    "HTTPMethods",
    "Collections",
    "LogIcons",
    "ErrorMessages",
    "Defaults",
    "HTTPStatus",
]
