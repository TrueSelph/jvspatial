"""Constants for the jvspatial API module.

This module provides centralized constants for routes, HTTP methods,
collection names, and other magic strings used throughout the API.
"""

from http import HTTPStatus


class APIRoutes:
    """API route path constants."""

    # Core routes
    PREFIX = "/api"
    HEALTH = "/health"
    ROOT = "/"

    # Storage routes
    STORAGE_PREFIX = "/storage"
    STORAGE_UPLOAD = f"{STORAGE_PREFIX}/upload"
    STORAGE_FILES = f"{STORAGE_PREFIX}/files"
    STORAGE_PROXY = f"{STORAGE_PREFIX}/proxy"

    # Proxy routes
    PROXY_PREFIX = "/p"


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
    """Database collection names."""

    USERS = "users"
    API_KEYS = "api_keys"  # pragma: allowlist secret
    SESSIONS = "sessions"
    WEBHOOKS = "webhooks"
    WEBHOOK_REQUESTS = "webhook_requests"
    SCHEDULED_TASKS = "scheduled_tasks"


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
    """Default configuration values."""

    # API
    API_TITLE = "jvspatial API"
    API_VERSION = "1.0.0"
    API_DESCRIPTION = "API built with jvspatial framework"

    # Server
    HOST = "0.0.0.0"
    PORT = 8000
    LOG_LEVEL = "info"
    DEBUG = False

    # CORS
    CORS_ENABLED = True
    CORS_ORIGINS = ["*"]
    CORS_METHODS = ["*"]
    CORS_HEADERS = ["*"]

    # File Storage
    FILE_STORAGE_ENABLED = False
    FILE_STORAGE_PROVIDER = "local"
    FILE_STORAGE_ROOT = ".files"
    FILE_STORAGE_MAX_SIZE = 100 * 1024 * 1024  # 100MB
    FILE_STORAGE_BASE_URL = "http://localhost:8000"

    # Proxy
    PROXY_ENABLED = False
    PROXY_EXPIRATION = 3600  # 1 hour
    PROXY_MAX_EXPIRATION = 86400  # 24 hours

    # Database
    DB_TYPE = "json"
    DB_PATH = "./jvdb"


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
