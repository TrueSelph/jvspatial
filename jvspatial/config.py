"""Unified configuration system for jvspatial.

This module provides a single Config class that replaces multiple
configuration classes with a simplified approach.
"""

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Unified configuration for jvspatial.

    This class replaces ServerConfig, AuthConfig, and other configuration
    classes with a single simplified configuration system.
    """

    # ============================================================================
    # Server Configuration
    # ============================================================================

    # API Configuration
    title: str = Field(default="jvspatial API", description="API title")
    description: str = Field(
        default="API built with jvspatial framework", description="API description"
    )
    version: str = Field(default="1.0.0", description="API version")
    debug: bool = Field(default=False, description="Enable debug mode")

    # Server Configuration
    host: str = Field(default="localhost", description="Server host address")
    port: int = Field(default=8000, description="Server port number")
    docs_url: Optional[str] = Field(
        default="/docs", description="OpenAPI documentation URL"
    )
    redoc_url: Optional[str] = Field(
        default="/redoc", description="ReDoc documentation URL"
    )

    # CORS Configuration
    cors_enabled: bool = Field(default=True, description="Enable CORS middleware")
    cors_origins: List[str] = Field(
        default_factory=lambda: ["*"], description="Allowed CORS origins"
    )
    cors_methods: List[str] = Field(
        default_factory=lambda: ["*"], description="Allowed CORS methods"
    )
    cors_headers: List[str] = Field(
        default_factory=lambda: ["*"], description="Allowed CORS headers"
    )

    # ============================================================================
    # Database Configuration
    # ============================================================================

    db_type: str = Field(default="json", description="Database type (json, mongodb)")
    db_base_path: Optional[str] = Field(
        default=".data", description="Database base path for JSON database"
    )
    db_uri: Optional[str] = Field(default=None, description="Database URI for MongoDB")
    db_name: Optional[str] = Field(
        default=None, description="Database name for MongoDB"
    )
    db_connection_string: Optional[str] = Field(
        default=None, description="Database connection string"
    )
    db_pool_size: int = Field(default=10, description="Database connection pool size")
    db_max_connections: int = Field(
        default=100, description="Maximum database connections"
    )

    # ============================================================================
    # Authentication Configuration
    # ============================================================================

    # General Authentication Settings
    auth_enabled: bool = Field(
        default=True, description="Enable authentication middleware"
    )
    auth_exempt_paths: List[str] = Field(
        default_factory=lambda: [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        ],
        description="Paths exempt from authentication",
    )

    # JWT Configuration
    jwt_secret: str = Field(default="your-secret-key", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expire_minutes: int = Field(
        default=30, description="JWT expiration time in minutes"
    )
    jwt_refresh_expire_days: int = Field(
        default=7, description="JWT refresh token expiration in days"
    )

    # Password Configuration
    password_min_length: int = Field(default=8, description="Minimum password length")
    password_require_special_chars: bool = Field(
        default=True, description="Require special characters in password"
    )

    # API Key Configuration
    api_key_header: str = Field(
        default="x-api-key", description="Header name for API key"
    )

    # Session Configuration
    session_cookie_name: str = Field(
        default="session", description="Session cookie name"
    )
    session_expire_minutes: int = Field(
        default=60, description="Session expiration time in minutes"
    )

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(default=False, description="Enable rate limiting")
    rate_limit_requests_per_minute: int = Field(
        default=60, description="Requests per minute limit"
    )

    # Brute Force Protection
    brute_force_protection_enabled: bool = Field(
        default=False, description="Enable brute force protection"
    )
    max_login_attempts: int = Field(
        default=5, description="Maximum login attempts before lockout"
    )
    lockout_duration_minutes: int = Field(
        default=15, description="Lockout duration in minutes"
    )

    # ============================================================================
    # Cache Configuration
    # ============================================================================

    cache_backend: str = Field(
        default="memory", description="Cache backend (memory, redis, layered)"
    )
    cache_size: int = Field(default=1000, description="Cache size for memory backend")
    cache_ttl_seconds: int = Field(default=3600, description="Cache TTL in seconds")
    cache_key_prefix: str = Field(default="jvspatial:", description="Cache key prefix")
    redis_url: Optional[str] = Field(default=None, description="Redis URL for cache")

    # ============================================================================
    # Storage Configuration
    # ============================================================================

    storage_enabled: bool = Field(default=False, description="Enable file storage")
    storage_provider: str = Field(
        default="local", description="Storage provider (local, s3)"
    )
    storage_root: str = Field(default=".files", description="Storage root directory")
    storage_base_url: str = Field(
        default="http://localhost:8000", description="Storage base URL"
    )
    storage_max_size: int = Field(
        default=100 * 1024 * 1024, description="Maximum file size (100MB)"
    )

    # S3 Configuration
    s3_bucket_name: Optional[str] = Field(default=None, description="S3 bucket name")
    s3_region: Optional[str] = Field(default=None, description="S3 region")
    s3_access_key: Optional[str] = Field(default=None, description="S3 access key")
    s3_secret_key: Optional[str] = Field(default=None, description="S3 secret key")
    s3_endpoint_url: Optional[str] = Field(default=None, description="S3 endpoint URL")

    # ============================================================================
    # Logging Configuration
    # ============================================================================

    log_level: str = Field(default="info", description="Logging level")

    # ============================================================================
    # Lifecycle Hooks
    # ============================================================================

    startup_hooks: List[str] = Field(
        default_factory=list, description="Startup hook function names"
    )
    shutdown_hooks: List[str] = Field(
        default_factory=list, description="Shutdown hook function names"
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: Any) -> Any:  # type: ignore[no-any-return]
        """Validate port number."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: Any) -> Any:  # type: ignore[no-any-return]
        """Validate host string."""
        if not v or v.strip() == "":
            raise ValueError("Host cannot be empty")
        return v

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables.

        Returns:
            Config instance with values from environment variables
        """
        env_mapping = {
            # Server
            "title": "JVSPATIAL_TITLE",
            "description": "JVSPATIAL_DESCRIPTION",
            "version": "JVSPATIAL_VERSION",
            "debug": "JVSPATIAL_DEBUG",
            "host": "JVSPATIAL_HOST",
            "port": "JVSPATIAL_PORT",
            # Database
            "db_type": "JVSPATIAL_DB_TYPE",
            "db_path": "JVSPATIAL_DB_PATH",
            "db_uri": "JVSPATIAL_DB_URI",
            "db_name": "JVSPATIAL_DB_NAME",
            # Authentication
            "auth_enabled": "JVSPATIAL_AUTH_ENABLED",
            "jwt_secret": "JVSPATIAL_JWT_SECRET_KEY",  # pragma: allowlist secret
            "jwt_algorithm": "JVSPATIAL_JWT_ALGORITHM",
            "jwt_expire_minutes": "JVSPATIAL_JWT_EXPIRE_MINUTES",
            # Cache
            "cache_backend": "JVSPATIAL_CACHE_BACKEND",
            "cache_size": "JVSPATIAL_CACHE_SIZE",
            "redis_url": "JVSPATIAL_REDIS_URL",
            # Storage
            "storage_enabled": "JVSPATIAL_STORAGE_ENABLED",
            "storage_provider": "JVSPATIAL_STORAGE_PROVIDER",
            "storage_root": "JVSPATIAL_STORAGE_ROOT",
            "s3_bucket_name": "JVSPATIAL_S3_BUCKET_NAME",
            "s3_region": "JVSPATIAL_S3_REGION",
            "s3_access_key": "JVSPATIAL_S3_ACCESS_KEY",
            "s3_secret_key": "JVSPATIAL_S3_SECRET_KEY",  # pragma: allowlist secret
            # Logging
            "log_level": "JVSPATIAL_LOG_LEVEL",
        }

        config_data: Dict[str, Any] = {}

        for field_name, env_var in env_mapping.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # Convert string values to appropriate types
                if field_name in [
                    "debug",
                    "auth_enabled",
                    "rate_limit_enabled",
                    "brute_force_protection_enabled",
                    "storage_enabled",
                ]:
                    config_data[field_name] = env_value.lower() in ("true", "1", "yes")
                elif field_name in [
                    "port",
                    "cache_size",
                    "storage_max_size",
                    "jwt_expire_minutes",
                    "rate_limit_requests_per_minute",
                    "max_login_attempts",
                    "lockout_duration_minutes",
                ]:
                    config_data[field_name] = int(env_value)
                else:
                    config_data[field_name] = env_value

        return cls(**config_data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation of the configuration
        """
        return self.model_dump()

    def update(self, **kwargs: Any) -> None:
        """Update configuration with new values.

        Args:
            **kwargs: Configuration values to update
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance.

    Returns:
        Global configuration instance
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance.

    Args:
        config: Configuration instance to set as global
    """
    global _config
    _config = config
