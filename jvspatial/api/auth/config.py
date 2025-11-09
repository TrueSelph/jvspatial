"""Authentication configuration for jvspatial API.

This module provides authentication configuration models for the jvspatial API,
including JWT, API key, and session-based authentication settings.
"""

from typing import List

from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Authentication configuration model.

    Attributes:
        enabled: Enable authentication middleware
        exempt_paths: List of paths exempt from authentication
        jwt_secret: JWT secret key
        jwt_algorithm: JWT algorithm
        jwt_expire_minutes: JWT expiration time in minutes
        api_key_header: Header name for API key authentication
        session_cookie_name: Cookie name for session authentication
        session_expire_minutes: Session expiration time in minutes
    """

    # General Authentication Settings
    enabled: bool = True
    exempt_paths: List[str] = Field(
        default_factory=lambda: [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        ]
    )

    # JWT Configuration
    jwt_secret: str = Field(default="your-secret-key", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expire_minutes: int = Field(
        default=30, description="JWT expiration time in minutes"
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


__all__ = ["AuthConfig"]
