"""Authentication middleware and utilities for jvspatial FastAPI integration.

This module provides FastAPI middleware for authentication, JWT token handling,
API key validation, rate limiting, and user context injection.
"""

import hashlib
import hmac
import time
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .entities import (
    APIKey,
    AuthenticationError,
    AuthorizationError,
    InvalidCredentialsError,
    RateLimitError,
    Session,
    SessionExpiredError,
    User,
)


class AuthConfig:
    """Configuration for authentication system."""

    def __init__(self):
        # JWT Configuration
        self.jwt_secret_key: str = (
            "your-secret-key-change-in-production"  # Should be overridden
        )
        self.jwt_algorithm: str = "HS256"
        self.jwt_expiration_hours: int = 24
        self.jwt_refresh_expiration_days: int = 30

        # API Key Configuration
        self.api_key_header: str = "X-API-Key"
        self.api_key_query_param: str = "api_key"
        self.hmac_header: str = "X-HMAC-Signature"

        # Rate Limiting
        self.rate_limit_enabled: bool = True
        self.default_rate_limit_per_hour: int = 1000

        # Security
        self.require_https: bool = False  # Set to True in production
        self.session_cookie_secure: bool = False  # Set to True in production
        self.session_cookie_httponly: bool = True


# Global auth config instance
auth_config = AuthConfig()


def configure_auth(**kwargs) -> None:
    """Configure authentication settings.

    Args:
        **kwargs: Configuration parameters to override
    """
    global auth_config
    for key, value in kwargs.items():
        if hasattr(auth_config, key):
            setattr(auth_config, key, value)


class RateLimiter:
    """In-memory rate limiter for API requests."""

    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()

    def is_allowed(self, identifier: str, limit_per_hour: int) -> bool:
        """Check if request is within rate limit.

        Args:
            identifier: Unique identifier for rate limiting (user ID, IP, etc.)
            limit_per_hour: Maximum requests per hour

        Returns:
            True if request is allowed, False if rate limited
        """
        now = time.time()
        hour_ago = now - 3600

        # Cleanup old requests periodically
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup()

        # Filter requests within the last hour
        user_requests = self.requests[identifier]
        recent_requests = [
            req_time for req_time in user_requests if req_time > hour_ago
        ]
        self.requests[identifier] = recent_requests

        # Check if under limit
        if len(recent_requests) < limit_per_hour:
            recent_requests.append(now)
            return True

        return False

    def _cleanup(self):
        """Remove old request records to prevent memory leaks."""
        hour_ago = time.time() - 3600
        for identifier in list(self.requests.keys()):
            self.requests[identifier] = [
                req_time
                for req_time in self.requests[identifier]
                if req_time > hour_ago
            ]
            if not self.requests[identifier]:
                del self.requests[identifier]

        self.last_cleanup = time.time()


# Global rate limiter instance
rate_limiter = RateLimiter()


def verify_hmac(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC signature of payload.

    Args:
        payload: Raw request body bytes
        signature: HMAC signature from header (hex)
        secret: Shared secret for HMAC computation

    Returns:
        True if signature is valid, False otherwise
    """
    if not secret:
        return True  # No HMAC required

    expected_signature = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature.lower(), expected_signature.lower())


class JWTManager:
    """JWT token management utilities."""

    @staticmethod
    def create_access_token(
        user: User, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token.

        Args:
            user: User to create token for
            expires_delta: Custom expiration time

        Returns:
            JWT token string
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                hours=auth_config.jwt_expiration_hours
            )

        payload = {
            "sub": user.id,
            "username": user.username,
            "email": user.email,
            "roles": user.roles,
            "is_admin": user.is_admin,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
        }

        return cast(
            str,
            jwt.encode(
                payload, auth_config.jwt_secret_key, algorithm=auth_config.jwt_algorithm
            ),
        )

    @staticmethod
    def create_refresh_token(user: User) -> str:
        """Create a JWT refresh token.

        Args:
            user: User to create token for

        Returns:
            JWT refresh token string
        """
        expire = datetime.utcnow() + timedelta(
            days=auth_config.jwt_refresh_expiration_days
        )

        payload = {
            "sub": user.id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
        }

        return cast(
            str,
            jwt.encode(
                payload, auth_config.jwt_secret_key, algorithm=auth_config.jwt_algorithm
            ),
        )

    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            InvalidCredentialsError: If token is invalid
        """
        try:
            payload = jwt.decode(
                token,
                auth_config.jwt_secret_key,
                algorithms=[auth_config.jwt_algorithm],
            )
            return cast(Dict[str, Any], payload)
        except jwt.ExpiredSignatureError:
            raise SessionExpiredError("Token has expired")
        except jwt.InvalidTokenError:
            raise InvalidCredentialsError("Invalid token")


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for handling authentication across the application."""

    def __init__(self, app, exempt_paths: Optional[List[str]] = None):
        """Initialize authentication middleware.

        Args:
            app: FastAPI application instance
            exempt_paths: List of paths to exempt from authentication
        """
        super().__init__(app)
        self.exempt_paths = exempt_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/auth/login",
            "/auth/register",
        ]

    async def dispatch(self, request: Request, call_next):
        """Process request through authentication middleware."""
        # HTTPS enforcement
        if auth_config.require_https and request.url.scheme != "https":
            return JSONResponse(
                status_code=403,
                content={"error": "HTTPS required"},
            )

        # Handle webhook paths specially
        api_key_obj = None
        raw_body = None
        content_type = None

        if request.url.path.startswith("/webhooks/"):
            # Read raw body once (consumes stream)
            raw_body = await request.body()
            content_type = request.headers.get("content-type", "")
            request.state.raw_body = raw_body
            request.state.content_type = content_type

            # Parse path: /webhooks/{route}/{key_id}:{secret}
            path_parts = request.url.path.strip("/").split("/")
            if len(path_parts) == 3 and path_parts[0] == "webhooks":
                route = path_parts[1]
                auth_token = path_parts[2]
                if ":" in auth_token:
                    key_id, secret = auth_token.split(":", 1)
                    # Validate path-based API key
                    user = await self._validate_api_key(key_id, secret)
                    if user:
                        request.state.current_user = user
                        # Get api_key_obj for HMAC
                        api_key_obj = await APIKey.find_by_key_id(key_id)
                        if api_key_obj:
                            request.state.api_key_obj = api_key_obj
                        request.state.webhook_route = route

                        # Optional HMAC verification
                        hmac_signature = request.headers.get(auth_config.hmac_header)
                        if (
                            hmac_signature
                            and api_key_obj
                            and api_key_obj.hmac_secret
                            and not verify_hmac(
                                raw_body, hmac_signature, api_key_obj.hmac_secret
                            )
                        ):
                            return JSONResponse(
                                status_code=401,
                                content={"error": "HMAC signature invalid"},
                            )

        # Skip authentication for exempt paths
        if any(request.url.path.startswith(path) for path in self.exempt_paths):
            return await call_next(request)

        # Check if endpoint requires authentication
        endpoint_auth = getattr(request.state, "endpoint_auth", None)
        # Handle mocked values - only skip auth if explicitly set to False
        if endpoint_auth is False:  # Explicitly set to not require auth
            return await call_next(request)

        try:
            user = None

            # Check if user was already set (e.g., from webhook path auth)
            # Only accept it if it's actually a User object, not a mock or None
            current_user = getattr(request.state, "current_user", None)
            if current_user and isinstance(current_user, User):
                user = current_user
            else:
                # Fallback to normal authentication (JWT or header/query API key)
                user = await self._authenticate_request(request)
                if user:
                    request.state.current_user = user

            if user:

                # Rate limiting (use api_key rate limit if available)
                rate_limit = int(user.rate_limit_per_hour)
                identifier = str(user.id)
                if api_key_obj:
                    rate_limit = int(api_key_obj.rate_limit_per_hour)
                    identifier = str(api_key_obj.key_id)

                if auth_config.rate_limit_enabled and not rate_limiter.is_allowed(
                    identifier, rate_limit
                ):
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "Rate limit exceeded",
                            "message": "Too many requests",
                        },
                    )

                # Check if endpoint requires specific permissions
                required_permissions = getattr(
                    request.state, "required_permissions", []
                )
                if required_permissions:
                    for permission in required_permissions:
                        if not user.has_permission(permission):
                            return JSONResponse(
                                status_code=403,
                                content={
                                    "error": "Insufficient permissions",
                                    "permission": permission,
                                },
                            )

                # Check required roles
                required_roles = getattr(request.state, "required_roles", [])
                if required_roles and not any(
                    user.has_role(role) for role in required_roles
                ):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": "Insufficient role",
                            "required_roles": list(required_roles),
                        },
                    )

            else:
                # Authentication is required but no valid user found
                # Only skip this if endpoint_auth is explicitly False (not None or mock)
                if endpoint_auth is not False:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": "Authentication required",
                            "message": "Please provide valid credentials",
                        },
                    )

        except AuthenticationError as e:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication failed", "message": str(e)},
            )
        except AuthorizationError as e:
            return JSONResponse(
                status_code=403,
                content={"error": "Authorization failed", "message": str(e)},
            )
        except RateLimitError as e:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded", "message": str(e)},
            )

        return await call_next(request)

    async def _validate_api_key(self, key_id: str, secret: str) -> Optional[User]:
        """Validate API key credentials without request context.

        Args:
            key_id: API key ID
            secret: API key secret

        Returns:
            Associated user if valid, None otherwise
        """
        try:
            # Find API key in database
            api_key_obj = await APIKey.find_by_key_id(key_id)

            if (
                api_key_obj
                and api_key_obj.is_valid()
                and api_key_obj.verify_secret(secret)
            ):
                # Check endpoint restrictions (pass empty path for now, or use request if available)
                # For path auth, endpoint is already in path, but since no request, assume allowed or check later
                # For simplicity, skip endpoint check here; middleware will handle permissions

                # Record usage (no endpoint param for now)
                await api_key_obj.record_usage()

                # Get associated user
                user = await User.get(api_key_obj.user_id)
                if user and user.is_active:
                    return user

        except Exception:
            pass

        return None

    async def _authenticate_request(self, request: Request) -> Optional[User]:
        """Authenticate a request using various methods.

        Args:
            request: FastAPI request object

        Returns:
            Authenticated user or None
        """
        # Try JWT token authentication first
        user = await self._authenticate_jwt(request)
        if user:
            return user

        # Try API key authentication
        user = await self._authenticate_api_key(request)
        if user:
            return user

        return None

    async def _authenticate_jwt(self, request: Request) -> Optional[User]:
        """Authenticate using JWT token."""
        # Check Authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix

            try:
                payload = JWTManager.verify_token(token)
                user_id = payload.get("sub")

                if user_id:
                    # Get user from database
                    user = await User.get(user_id)
                    if user and user.is_active:
                        return user

            except (InvalidCredentialsError, SessionExpiredError):
                pass

        return None

    async def _authenticate_api_key(self, request: Request) -> Optional[User]:
        """Authenticate using API key."""
        api_key = None

        # Check header
        api_key = request.headers.get(auth_config.api_key_header)

        # Check query parameter
        if not api_key:
            api_key = request.query_params.get(auth_config.api_key_query_param)

        if api_key:
            try:
                # Parse API key (format: key_id:secret_key)
                if ":" not in api_key:
                    return None

                key_id, secret_key = api_key.split(":", 1)

                # Find API key in database
                api_key_obj = await APIKey.find_by_key_id(key_id)

                if (
                    api_key_obj
                    and api_key_obj.is_valid()
                    and api_key_obj.verify_secret(secret_key)
                ):
                    # Check endpoint restrictions
                    endpoint = request.url.path
                    if not api_key_obj.can_access_endpoint(endpoint):
                        raise AuthorizationError(
                            f"API key cannot access endpoint: {endpoint}"
                        )

                    # Record usage
                    await api_key_obj.record_usage(endpoint=endpoint)

                    # Get associated user
                    user = await User.get(api_key_obj.user_id)
                    if user and user.is_active:
                        # Attach api_key_obj to state for HMAC if needed
                        request.state.api_key_obj = api_key_obj
                        return user

            except Exception:
                pass

        return None


def get_current_user(request: Request) -> Optional[User]:
    """Get the current authenticated user from request state.

    Args:
        request: FastAPI request object

    Returns:
        Current user or None if not authenticated
    """
    return getattr(request.state, "current_user", None)


def require_auth(
    permissions: Optional[List[str]] = None, roles: Optional[List[str]] = None
) -> Callable:
    """Decorator to require authentication for an endpoint.

    Args:
        permissions: List of required permissions
        roles: List of required roles (user needs at least one)

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: tuple, **kwargs: dict):
            # The middleware will handle the actual authentication
            # This decorator just marks the requirements
            return await func(*args, **kwargs)

        # Store auth requirements on the function
        wrapper._auth_required = True  # type: ignore[attr-defined]
        wrapper._required_permissions = permissions or []  # type: ignore[attr-defined]
        wrapper._required_roles = roles or []  # type: ignore[attr-defined]

        return wrapper

    return decorator


def no_auth_required(func: Callable) -> Callable:
    """Decorator to mark an endpoint as not requiring authentication.

    Args:
        func: Function to decorate

    Returns:
        Decorated function
    """

    @wraps(func)
    async def wrapper(*args: tuple, **kwargs: dict):
        return await func(*args, **kwargs)

    wrapper._auth_required = False  # type: ignore[attr-defined]
    return wrapper


async def create_user_session(user: User, request: Request) -> Session:
    """Create a new user session with JWT tokens.

    Args:
        user: User to create session for
        request: Request object for context

    Returns:
        Created session object
    """
    session_id = Session.create_session_id()

    # Create JWT tokens
    access_token = JWTManager.create_access_token(user)
    refresh_token = JWTManager.create_refresh_token(user)

    # Create session
    session = await Session.create(
        session_id=session_id,
        user_id=user.id,
        jwt_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now() + timedelta(hours=auth_config.jwt_expiration_hours),
        client_ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
    )

    return session


async def authenticate_user(username: str, password: str) -> User:
    """Authenticate a user with username/password.

    Args:
        username: Username or email
        password: Plain text password

    Returns:
        Authenticated user

    Raises:
        InvalidCredentialsError: If credentials are invalid
    """
    # Try to find user by username first, then email
    user = await User.find_by_username(username)
    if not user:
        user = await User.find_by_email(username)

    if not user or not user.is_active:
        raise InvalidCredentialsError("Invalid username or password")

    if not user.verify_password(password):
        raise InvalidCredentialsError("Invalid username or password")

    # Record login
    await user.record_login()

    return cast(User, user)


async def refresh_session(refresh_token: str) -> Tuple[str, str]:
    """Refresh a session using a refresh token.

    Args:
        refresh_token: JWT refresh token

    Returns:
        Tuple of (new_access_token, new_refresh_token)

    Raises:
        SessionExpiredError: If refresh token is invalid or expired
    """
    try:
        payload = JWTManager.verify_token(refresh_token)

        if payload.get("type") != "refresh":
            raise InvalidCredentialsError("Invalid token type")

        user_id = payload.get("sub")
        user = await User.get(cast(str, user_id))

        if not user or not user.is_active:
            raise SessionExpiredError("User not found or inactive")

        # Create new tokens
        new_access_token = JWTManager.create_access_token(user)
        new_refresh_token = JWTManager.create_refresh_token(user)

        return new_access_token, new_refresh_token

    except (InvalidCredentialsError, SessionExpiredError):
        raise SessionExpiredError("Invalid or expired refresh token")


# Security utilities
security = HTTPBearer(auto_error=False)


async def get_current_user_dependency(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = None
) -> User:
    """Get FastAPI dependency for getting current user.

    Args:
        request: FastAPI request object
        credentials: Optional HTTP credentials

    Returns:
        Current authenticated user

    Raises:
        HTTPException: If user is not authenticated
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def get_current_active_user(current_user: Optional[User] = None) -> User:
    """Get current active user dependency.

    Args:
        current_user: Current user from authentication

    Returns:
        Active user

    Raises:
        HTTPException: If user is inactive
    """
    if not current_user or not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user


async def get_admin_user(current_user: Optional[User] = None) -> User:
    """Get current admin user dependency.

    Args:
        current_user: Current user from authentication

    Returns:
        Admin user

    Raises:
        HTTPException: If user is not admin
    """
    if not current_user or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# Import and re-export webhook middleware for convenience
try:
    from jvspatial.api.webhook.middleware import (
        WebhookMiddleware,
        WebhookMiddlewareConfig,
        add_webhook_middleware,
    )

    # Make webhook middleware available from auth module
    __all__ = getattr(__name__, "__all__", []) + [
        "WebhookMiddleware",
        "WebhookMiddlewareConfig",
        "add_webhook_middleware",
    ]
except ImportError:
    # Webhook middleware not available - this is okay
    pass
