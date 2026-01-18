"""Rate limiting middleware for jvspatial API endpoints.

This module provides per-endpoint rate limiting with pluggable backend storage.
Rate limits can be configured per endpoint via the @endpoint decorator or
globally via server configuration.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .rate_limit_backend import MemoryRateLimitBackend, RateLimitBackend


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting an endpoint."""

    requests: int = 60  # Number of requests allowed
    window: int = 60  # Time window in seconds
    identifier: Optional[str] = None  # Custom identifier key (defaults to IP)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-endpoint rate limiting middleware with in-memory storage.

    This middleware tracks request counts per client and endpoint, enforcing
    rate limits based on configuration. Counters are stored in-memory for
    optimal performance.

    Attributes:
        _limits: Dictionary mapping endpoint paths to RateLimitConfig
        _counters: In-memory storage for request counters
        _default_limit: Default requests per window
        _default_window: Default window in seconds
        _logger: Logger instance
    """

    def __init__(
        self,
        app,
        config: Optional[Dict[str, RateLimitConfig]] = None,
        default_limit: int = 60,
        default_window: int = 60,
        backend: Optional[RateLimitBackend] = None,
    ):
        """Initialize the rate limit middleware.

        Args:
            app: FastAPI application instance
            config: Dictionary mapping endpoint paths to RateLimitConfig
            default_limit: Default number of requests allowed per window
            default_window: Default time window in seconds
            backend: Optional rate limiting backend (defaults to MemoryRateLimitBackend)
        """
        super().__init__(app)
        self._limits = config or {}
        self._default_limit = default_limit
        self._default_window = default_window
        self._backend = backend or MemoryRateLimitBackend()
        self._logger = logging.getLogger(__name__)

    def _get_client_identifier(self, request: Request) -> str:
        """Get a unique identifier for the client.

        Uses IP address by default, but can be enhanced to use API key or
        user ID if available from request state.

        Args:
            request: FastAPI request object

        Returns:
            Client identifier string
        """
        # Try to get authenticated user/API key ID for more accurate tracking
        if hasattr(request.state, "user") and request.state.user:
            user = request.state.user
            # Extract user_id from various formats
            if hasattr(user, "id"):
                return f"user:{user.id}"
            if hasattr(user, "user_id"):
                return f"user:{user.user_id}"
            if isinstance(user, dict):
                user_id = user.get("id") or user.get("user_id")
                if user_id:
                    return f"user:{user_id}"

        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        # Include user agent for additional uniqueness
        user_agent = request.headers.get("user-agent", "")
        # Create a hash for privacy
        identifier = f"{client_ip}:{user_agent}"
        return hashlib.sha256(identifier.encode()).hexdigest()[:16]

    def _match_endpoint(self, path: str) -> Optional[str]:
        """Match request path to configured endpoint.

        Args:
            path: Request URL path

        Returns:
            Matching endpoint key from config, or None
        """
        # Try exact match first
        if path in self._limits:
            return path

        # Try prefix matching (for path parameters)
        for endpoint_path in self._limits.keys():
            # Convert FastAPI path pattern to regex-like matching
            # e.g., "/api/users/{user_id}" should match "/api/users/123"
            if self._path_matches(endpoint_path, path):
                return endpoint_path

        return None

    def _path_matches(self, pattern: str, path: str) -> bool:
        """Check if a request path matches a route pattern with path parameters.

        Args:
            pattern: Route pattern (e.g., "/api/users/{user_id}")
            path: Actual request path (e.g., "/api/users/123")

        Returns:
            True if path matches pattern, False otherwise
        """
        import re

        # Convert pattern to regex by replacing {param} with [^/]+
        escaped_pattern = re.escape(pattern)
        # Replace escaped {param} patterns with regex
        regex_pattern = re.sub(r"\\\{(\w+)\\\}", r"[^/]+", escaped_pattern)
        # Also handle unescaped patterns
        regex_pattern = re.sub(r"\{(\w+)\}", r"[^/]+", regex_pattern)

        # Match the entire path
        regex_pattern = f"^{regex_pattern}$"
        return bool(re.match(regex_pattern, path))

    async def _is_rate_limited(
        self, client_key: str, endpoint_key: str, limit: RateLimitConfig
    ) -> bool:
        """Check if a client has exceeded the rate limit for an endpoint.

        Args:
            client_key: Client identifier
            endpoint_key: Endpoint path
            limit: Rate limit configuration

        Returns:
            True if rate limited, False otherwise
        """
        counter_key = f"{client_key}:{endpoint_key}"

        # Increment and get count using backend
        count = await self._backend.increment(counter_key, limit.window)

        # Check if limit exceeded
        return count > limit.requests

    def _get_rate_limit_config(self, endpoint_key: str) -> RateLimitConfig:
        """Get rate limit configuration for an endpoint.

        Args:
            endpoint_key: Endpoint path

        Returns:
            RateLimitConfig for the endpoint, or default config
        """
        if endpoint_key in self._limits:
            return self._limits[endpoint_key]

        # Return default configuration
        return RateLimitConfig(
            requests=self._default_limit, window=self._default_window
        )

    def _rate_limit_response(self, limit: RateLimitConfig) -> JSONResponse:
        """Create a rate limit exceeded response.

        Args:
            limit: Rate limit configuration

        Returns:
            JSONResponse with 429 status and rate limit information
        """
        return JSONResponse(
            status_code=429,
            content={
                "error_code": "rate_limit_exceeded",
                "message": f"Rate limit exceeded: {limit.requests} requests per {limit.window} seconds",
                "limit": limit.requests,
                "window": limit.window,
            },
            headers={
                "X-RateLimit-Limit": str(limit.requests),
                "X-RateLimit-Window": str(limit.window),
                "Retry-After": str(limit.window),
            },
        )

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting.

        Args:
            request: Incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response from next handler or rate limit error response
        """
        # Skip rate limiting for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Match endpoint to configuration
        endpoint_key = self._match_endpoint(request.url.path)

        # If endpoint has rate limiting configured, check it
        if endpoint_key:
            limit = self._get_rate_limit_config(endpoint_key)
            client_key = self._get_client_identifier(request)

            if await self._is_rate_limited(client_key, endpoint_key, limit):
                self._logger.warning(
                    f"Rate limit exceeded for {client_key} on {endpoint_key}"
                )
                return self._rate_limit_response(limit)

        # Apply default rate limit if configured
        elif self._default_limit > 0:
            limit = RateLimitConfig(
                requests=self._default_limit, window=self._default_window
            )
            client_key = self._get_client_identifier(request)
            # Use path as endpoint key for default limits
            endpoint_key = request.url.path

            if await self._is_rate_limited(client_key, endpoint_key, limit):
                self._logger.warning(
                    f"Default rate limit exceeded for {client_key} on {endpoint_key}"
                )
                return self._rate_limit_response(limit)

        # Request allowed, proceed
        return await call_next(request)


__all__ = ["RateLimitMiddleware", "RateLimitConfig"]
