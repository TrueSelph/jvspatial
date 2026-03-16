"""Configuration groups for jvspatial Server.

This module provides logical configuration groups that compose into ServerConfig,
improving organization and maintainability.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_ROLE_MAPPING: Dict[str, List[str]] = {"admin": ["*"], "user": []}


class DatabaseConfig(BaseModel):
    """Database configuration group."""

    db_type: Optional[str] = None
    db_path: Optional[str] = None
    db_path_resolve: Optional[str] = Field(
        default=None,
        description="When set to 'app', resolve relative db_path against the directory "
        "of the module that instantiated Server. Use when cwd varies (e.g. running from "
        "project root vs backend dir).",
    )
    db_connection_string: Optional[str] = None
    db_database_name: Optional[str] = None

    # DynamoDB Configuration (only used if db_type is "dynamodb")
    dynamodb_table_name: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_DYNAMODB_TABLE_NAME"
    )
    dynamodb_region: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_DYNAMODB_REGION"
    )
    dynamodb_endpoint_url: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_DYNAMODB_ENDPOINT_URL"
    )
    dynamodb_access_key_id: Optional[str] = Field(
        default=None, validation_alias="AWS_ACCESS_KEY_ID"
    )
    dynamodb_secret_access_key: Optional[str] = Field(
        default=None, validation_alias="AWS_SECRET_ACCESS_KEY"
    )


class CORSConfig(BaseModel):
    """CORS configuration group."""

    cors_enabled: bool = True
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    cors_methods: List[str] = Field(default_factory=lambda: ["*"])
    cors_headers: List[str] = Field(default_factory=lambda: ["*"])


class AuthConfig(BaseModel):
    """Authentication configuration group.

    Authentication behavior:
    - enabled/auth_enabled: Master switch for authentication middleware. When True:
    """

    model_config = ConfigDict(populate_by_name=True)

    # Master switch (accept auth_enabled for backward compat)
    enabled: bool = Field(
        default=False,
        description="Enable authentication middleware (JWT + API key)",
        validation_alias="auth_enabled",
    )

    # Test mode: when True, honors request.state.user set by test fixtures for
    # in-process ASGI testing (e.g. TestClient with ASGITransport)
    test_mode: bool = Field(
        default=False,
        description="When True, use request.state.user if set (for testing). "
        "See docs Request State Contract.",
    )

    # API key management endpoint control
    api_key_management_enabled: bool = Field(
        default=True,
        description="Enable API key management endpoints (/auth/api-keys). "
        "Does not affect API key authentication availability.",
    )

    # JWT Configuration
    jwt_secret: str = Field(default="your-secret-key", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expire_minutes: int = Field(
        default=30, description="JWT expiration time in minutes"
    )
    refresh_expire_days: int = Field(
        default=7, description="Refresh token expiration time in days"
    )
    refresh_token_rotation: bool = Field(
        default=False, description="Enable refresh token rotation on refresh"
    )
    blacklist_cache_ttl_seconds: int = Field(
        default=3600, description="Cache TTL for blacklist checks in seconds"
    )

    # API Key Configuration
    api_key_header: str = Field(
        default="x-api-key", description="Header name for API key"
    )
    api_key_min_length: int = Field(default=32, description="Minimum API key length")
    api_key_prefix: str = Field(
        default="sk_", description="Key prefix (e.g., sk_live_, sk_test_)"
    )

    # Session Configuration (cookie names; session auth not implemented)
    session_cookie_name: str = Field(
        default="session", description="Session cookie name"
    )
    session_expire_minutes: int = Field(
        default=60, description="Session expiration time in minutes"
    )

    # RBAC Configuration
    rbac_enabled: bool = Field(
        default=True,
        description="Enable role and permission enforcement",
    )
    default_role: str = Field(
        default="user",
        description="Role for new users (non-bootstrap)",
    )
    admin_role: str = Field(
        default="admin",
        description="Role name for bootstrap and admin-only checks",
    )
    registration_open: bool = Field(
        default=True,
        description="When False, disable public register even when no users",
    )
    role_permission_mapping: Dict[str, List[str]] = Field(
        default_factory=lambda: dict(_DEFAULT_ROLE_MAPPING),
        description="Maps each role to its permissions. Use '*' for admin-all.",
    )

    # Bootstrap admin (create first admin from env on startup when set)
    bootstrap_admin_email: Optional[str] = Field(
        default=None,
        description="Admin email for bootstrap. When set with bootstrap_admin_password, "
        "creates an admin user on startup if none exists. Typically from ADMIN_EMAIL env.",
    )
    bootstrap_admin_password: Optional[str] = Field(
        default=None,
        description="Admin password for bootstrap. Min 6 chars. Typically from ADMIN_PASSWORD env.",
    )
    bootstrap_admin_name: Optional[str] = Field(
        default=None,
        description="Admin display name for bootstrap. Defaults to email. Typically from ADMIN_NAME env.",
    )

    # Authentication Exempt Paths (accept auth_exempt_paths for backward compat)
    exempt_paths: List[str] = Field(
        default_factory=lambda: [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/api/auth/register",
            "/api/auth/login",
            "/api/auth/refresh",
            "/api/auth/logout",
            "/auth/login",
            "/auth/logout",
            "/auth/register",
            "/auth/refresh",
            "/auth/register",
        ],
        validation_alias="auth_exempt_paths",
    )

    # Backward compatibility: allow access via auth_enabled/auth_exempt_paths
    @property
    def auth_enabled(self) -> bool:
        """Return whether authentication is enabled (alias for enabled)."""
        return self.enabled

    @property
    def auth_exempt_paths(self) -> List[str]:
        """Return paths exempt from authentication (alias for exempt_paths)."""
        return self.exempt_paths


class RateLimitConfig(BaseModel):
    """Rate limiting configuration group."""

    rate_limit_enabled: bool = Field(
        default=False, description="Enable rate limiting middleware"
    )
    rate_limit_default_requests: int = Field(
        default=60, description="Default requests per window"
    )
    rate_limit_default_window: int = Field(
        default=60, description="Default time window in seconds"
    )
    rate_limit_overrides: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Per-endpoint rate limit overrides: {path: {requests: N, window: M}}",
    )


class FileStorageConfig(BaseModel):
    """File storage configuration group."""

    file_storage_enabled: bool = Field(
        default=False, validation_alias="JVSPATIAL_FILE_STORAGE_ENABLED"
    )
    file_storage_provider: str = Field(
        default="local", validation_alias="JVSPATIAL_FILE_STORAGE_PROVIDER"
    )  # "local" or "s3"
    file_storage_root: str = Field(
        default=".files", validation_alias="JVSPATIAL_FILE_STORAGE_ROOT"
    )
    file_storage_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="JVSPATIAL_FILE_STORAGE_BASE_URL",
    )
    file_storage_max_size: int = Field(
        default=100 * 1024 * 1024, validation_alias="JVSPATIAL_FILE_STORAGE_MAX_SIZE"
    )  # 100MB default

    # S3 Configuration (only used if provider is "s3")
    s3_bucket_name: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_BUCKET_NAME"
    )
    s3_region: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_REGION"
    )
    s3_access_key: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_ACCESS_KEY"
    )
    s3_secret_key: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_SECRET_KEY"
    )
    s3_endpoint_url: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_ENDPOINT_URL"
    )


class WebhookConfig(BaseModel):
    """Webhook configuration group."""

    webhook_api_key_header: str = Field(
        default="x-api-key",
        description="Header name for webhook API key authentication",
    )
    webhook_api_key_query_param: str = Field(
        default="api_key",
        description="Query parameter name for webhook API key authentication",
    )
    webhook_api_key_require_https: bool = Field(
        default=True, description="Require HTTPS for query parameter authentication"
    )
    webhook_https_required: bool = Field(
        default=True,
        description="Require HTTPS for webhook endpoints (general requirement)",
    )


class ProxyConfig(BaseModel):
    """URL proxy configuration group."""

    proxy_enabled: bool = Field(
        default=False, validation_alias="JVSPATIAL_PROXY_ENABLED"
    )
    proxy_default_expiration: int = Field(
        default=3600, validation_alias="JVSPATIAL_PROXY_DEFAULT_EXPIRATION"
    )  # 1 hour
    proxy_max_expiration: int = Field(
        default=86400, validation_alias="JVSPATIAL_PROXY_MAX_EXPIRATION"
    )  # 24 hours


__all__ = [
    "DatabaseConfig",
    "CORSConfig",
    "AuthConfig",
    "RateLimitConfig",
    "FileStorageConfig",
    "WebhookConfig",
    "ProxyConfig",
]
