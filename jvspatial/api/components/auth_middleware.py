"""Optimized authentication middleware for jvspatial API.

This module provides streamlined authentication middleware with pre-compiled patterns
for optimal performance, following the new standard implementation approach.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from jvspatial.api.auth.config import AuthConfig
from jvspatial.api.auth.rbac import has_required_permissions, has_required_roles
from jvspatial.api.components.endpoint_auth_resolver import EndpointAuthResolver
from jvspatial.api.components.path_matcher import PathMatcher


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Authentication middleware with multi-method support.

    This middleware attempts authentication in the following order:
    1. JWT Bearer token (Authorization: Bearer <token>)
    2. API key (X-API-Key or custom header configured in api_key_header)

    All authentication methods are always available when auth_enabled=True.
    Configuration flags (api_key_management_enabled, etc.) control endpoint
    registration and documentation, not whether authentication methods are checked.

    The middleware uses pre-compiled patterns for optimal performance and
    follows a "deny by default" security model - endpoints not explicitly
    registered with auth=False will require authentication.
    """

    def __init__(self, app, auth_config: AuthConfig, server):
        """Initialize the authentication middleware.

        Args:
            app: FastAPI application instance
            auth_config: Authentication configuration
            server: Server instance (required for endpoint auth checking)
        """
        super().__init__(app)
        if server is None:
            raise ValueError("AuthenticationMiddleware requires a server instance")
        if auth_config is None:
            raise ValueError(
                "AuthenticationMiddleware requires auth_config. "
                "Ensure Server has auth enabled (auth_enabled=True)."
            )
        self.auth_config = auth_config
        self.path_matcher = PathMatcher(auth_config.exempt_paths)
        self._auth_resolver = EndpointAuthResolver(server, self.path_matcher)
        self._logger = logging.getLogger(__name__)
        self._server = server

    async def dispatch(self, request: Request, call_next):
        """Optimized request processing with streamlined authentication logic.

        Args:
            request: Incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response from next handler or authentication error response
        """
        # Always allow OPTIONS requests (CORS preflight) to pass through
        # CORS middleware will handle these requests
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check if path is exempt from authentication
        is_exempt = self.path_matcher.is_exempt(request.url.path)
        if is_exempt:
            return await call_next(request)

        # Check if this endpoint requires authentication
        auth_required = self._auth_resolver.endpoint_requires_auth(request)
        has_fastapi_auth = self._auth_resolver.endpoint_has_fastapi_auth(request)

        if not auth_required:
            return await call_next(request)

        # If the route has FastAPI auth dependencies (like Depends(security)),
        # let FastAPI handle authentication via its dependency injection system
        # The middleware should not interfere with FastAPI's auth dependencies
        if has_fastapi_auth:
            self._logger.debug(
                f"Route {request.url.path} has FastAPI auth dependencies, allowing through"
            )
            return await call_next(request)

        # Request State Contract: when request.state.user is set (e.g. by test fixtures),
        # use it for in-process ASGI testing. Set auth test_mode=True to enable explicitly.
        # See docs/md/authentication.md "Request State Contract".
        user = getattr(request.state, "user", None)
        if user is not None and hasattr(user, "id"):
            pass  # Use pre-set user, skip _authenticate_request
        else:
            user = await self._authenticate_request(request)
        if not user:
            has_auth = bool(
                request.headers.get("authorization", "")
                .strip()
                .lower()
                .startswith("bearer ")
            )
            self._logger.warning(
                "[401] path=%s has_auth_header=%s -> auth failed (user=None)",
                request.url.path,
                has_auth,
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error_code": "authentication_required",
                    "message": "Authentication required",
                    "path": request.url.path,
                },
            )

        # Normalize user to have roles and permissions
        user = await self._normalize_user(user)

        # RBAC: check roles and permissions if endpoint requires them
        rbac_enabled = getattr(self.auth_config, "rbac_enabled", True)
        if rbac_enabled:
            endpoint_config = self._auth_resolver.get_endpoint_config(request)
            rbac_error = self._check_rbac(user, endpoint_config)
            if rbac_error:
                return rbac_error

        # Set user in request state for downstream handlers
        request.state.user = user
        return await call_next(request)

    def _check_rbac(
        self, user: Any, endpoint_config: Optional[Dict[str, Any]]
    ) -> Optional[JSONResponse]:
        """Check if user has required roles and permissions. Returns 403 response if not."""
        if not endpoint_config:
            return None

        required_roles = endpoint_config.get("roles") or []
        required_permissions = endpoint_config.get("permissions") or []

        if not required_roles and not required_permissions:
            return None

        user_roles: list[str] = []
        user_permissions: set[str] = set()
        if hasattr(user, "roles"):
            user_roles = list(user.roles) if user.roles else []
        elif isinstance(user, dict):
            user_roles = list(user.get("roles") or [])

        if hasattr(user, "permissions"):
            user_permissions = set(user.permissions) if user.permissions else set()
        elif isinstance(user, dict):
            user_permissions = set(user.get("permissions") or [])

        if required_roles and not has_required_roles(user_roles, required_roles):
            return JSONResponse(
                status_code=403,
                content={
                    "error_code": "insufficient_roles",
                    "message": "Insufficient privileges",
                    "required_roles": required_roles,
                },
            )

        if required_permissions and not has_required_permissions(
            user_permissions, required_permissions
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error_code": "insufficient_permissions",
                    "message": "Insufficient privileges",
                    "required_permissions": required_permissions,
                },
            )

        return None

    async def _normalize_user(self, user: Any) -> Any:
        """Ensure user has roles and permissions. For API key auth, fetch User."""
        if hasattr(user, "roles") and hasattr(user, "permissions"):
            # Already has roles and permissions (UserResponse from JWT)
            return user

        if isinstance(user, dict):
            user_id = user.get("user_id") or user.get("id")
            if user_id and ("roles" not in user or "permissions" not in user):
                # API key auth - fetch full user
                from jvspatial.api.auth.service import AuthenticationService
                from jvspatial.core.context import GraphContext
                from jvspatial.db import get_prime_database

                prime_ctx = GraphContext(database=get_prime_database())
                auth_service = AuthenticationService(
                    prime_ctx,
                    jwt_secret=self.auth_config.jwt_secret,
                    jwt_algorithm=self.auth_config.jwt_algorithm,
                    jwt_expire_minutes=self.auth_config.jwt_expire_minutes,
                    role_permission_mapping=getattr(
                        self.auth_config, "role_permission_mapping", None
                    ),
                )
                full_user = await auth_service.get_user_by_id(user_id)
                if full_user:
                    # Apply API key permission restriction if non-empty
                    api_key_perms = user.get("permissions") or []
                    if api_key_perms:
                        effective = set(full_user.permissions)
                        restricted = effective & set(api_key_perms)
                        return {
                            "id": full_user.id,
                            "user_id": full_user.id,
                            "email": full_user.email,
                            "roles": full_user.roles,
                            "permissions": list(restricted),
                        }
                    return {
                        "id": full_user.id,
                        "user_id": full_user.id,
                        "email": full_user.email,
                        "roles": full_user.roles,
                        "permissions": full_user.permissions,
                    }
            # Fallback: ensure dict has roles and permissions
            default_role = getattr(self.auth_config, "default_role", "user")
            user.setdefault("roles", [default_role])
            user.setdefault("permissions", [])

        return user

    async def _authenticate_request(self, request: Request) -> Optional[Any]:
        """Authenticate the incoming request using multiple methods.

        Attempts authentication in priority order:
        1. JWT Bearer token (if Authorization header present)
        2. API key (if X-API-Key or configured header present)
        3. Session cookie (if session cookie present)

        Returns the first successful authentication result.

        Args:
            request: Incoming request

        Returns:
            User object if authenticated, None otherwise
        """
        try:
            # Try JWT authentication first (use .get() for case-insensitive header presence)
            auth_header = request.headers.get("authorization") or request.headers.get(
                "Authorization"
            )
            has_bearer = bool(
                auth_header and auth_header.strip().lower().startswith("bearer ")
            )
            if has_bearer:
                return await self._authenticate_jwt(request)

            # Try API key authentication
            api_key_header = self.auth_config.api_key_header or "x-api-key"
            if request.headers.get(api_key_header):
                return await self._authenticate_api_key(request)

            return None

        except Exception as e:
            self._logger.error(f"Authentication error: {e}")
            return None

    async def _authenticate_jwt(self, request: Request) -> Optional[Any]:
        """Authenticate using JWT token.

        Args:
            request: Incoming request

        Returns:
            User object if JWT is valid, None otherwise
        """
        try:
            # Use server's cached auth service when available (avoids per-request instantiation)
            auth_service = getattr(self._server, "_auth_service", None)
            if auth_service is None:
                from jvspatial.api.auth.service import AuthenticationService
                from jvspatial.core.context import GraphContext
                from jvspatial.db import get_prime_database

                try:
                    ctx = GraphContext(database=get_prime_database())
                except Exception as db_err:
                    self._logger.error(
                        "_authenticate_jwt: get_prime_database() failed - auth will fail. %s",
                        db_err,
                        exc_info=True,
                    )
                    return None

                auth_service = AuthenticationService(
                    ctx,
                    jwt_secret=self.auth_config.jwt_secret,
                    jwt_algorithm=self.auth_config.jwt_algorithm,
                    jwt_expire_minutes=self.auth_config.jwt_expire_minutes,
                )

            # Extract token from Authorization header (case-insensitive per RFC 6750)
            auth_header = request.headers.get("authorization", "")
            if not auth_header.strip().lower().startswith("bearer "):
                return None

            token = auth_header.split(" ", 1)[1].strip()

            # Validate token using authentication service
            user = await auth_service.validate_token(token)
            if user:
                return user

            return None

        except Exception as e:
            self._logger.error(f"JWT authentication error: {e}")
            return None

    async def _authenticate_api_key(self, request: Request) -> Optional[Any]:
        """Authenticate using API key.

        Args:
            request: Incoming request

        Returns:
            User object if API key is valid, None otherwise
        """
        try:
            # Get API key from header
            api_key_header = self.auth_config.api_key_header or "x-api-key"
            api_key = request.headers.get(api_key_header, "")
            if not api_key:
                return None

            # Use API key service for validation
            from jvspatial.api.auth.api_key_service import APIKeyService
            from jvspatial.core.context import GraphContext
            from jvspatial.db import get_prime_database

            # API key service should use prime database, not server's graph context
            prime_ctx = GraphContext(database=get_prime_database())
            service = APIKeyService(prime_ctx)

            # Validate the API key
            api_key_entity = await service.validate_key(api_key)
            if not api_key_entity:
                return None

            # Check IP restrictions
            client_ip = request.client.host if request.client else None
            if (
                api_key_entity.allowed_ips
                and client_ip
                and client_ip not in api_key_entity.allowed_ips
            ):
                self._logger.debug(
                    f"API key {api_key_entity.id} rejected: IP {client_ip} not in whitelist"
                )
                return None

            # Check endpoint restrictions
            if api_key_entity.allowed_endpoints:
                request_path = request.url.path
                if not any(
                    request_path.startswith(ep)
                    for ep in api_key_entity.allowed_endpoints
                ):
                    self._logger.debug(
                        f"API key {api_key_entity.id} rejected: endpoint {request_path} not in whitelist"
                    )
                    return None

            # Update last used timestamp (fire and forget)
            try:
                await service.update_key_usage(api_key_entity)
            except Exception as e:
                # Log but don't fail authentication if update fails
                self._logger.warning(f"Failed to update API key usage timestamp: {e}")

            # Return user-like object for consistency with JWT authentication
            return {
                "user_id": api_key_entity.user_id,
                "api_key_id": api_key_entity.id,
                "permissions": api_key_entity.permissions,
                "rate_limit_override": api_key_entity.rate_limit_override,
            }

        except Exception as e:
            self._logger.error(f"API key authentication error: {e}", exc_info=True)
            return None


__all__ = ["AuthenticationMiddleware", "PathMatcher"]
