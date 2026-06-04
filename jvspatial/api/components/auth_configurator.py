"""Authentication configuration for jvspatial API.

This module provides authentication endpoint registration and configuration,
extracted from the Server class for better separation of concerns.
"""

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jvspatial.api.auth.api_key_service import APIKeyService
from jvspatial.api.auth.config import AuthConfig
from jvspatial.api.auth.models import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    ForgotPasswordRequest,
    PasswordChangeRequest,
    ResetPasswordRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserCreate,
    UserCreateAdmin,
    UserLogin,
    UserPermissionsUpdate,
    UserResponse,
    UserRolesUpdate,
)
from jvspatial.api.auth.service import AuthenticationService
from jvspatial.api.exceptions import RegistrationDisabledError
from jvspatial.core.context import GraphContext
from jvspatial.db import get_prime_database


class AuthConfigurator:
    """Configurator for authentication endpoints and middleware.

    Handles registration of authentication endpoints (register, login, logout)
    and API key management endpoints.
    """

    def __init__(
        self,
        config: Any,
        logger: Optional[logging.Logger] = None,
        server: Optional[Any] = None,
    ):
        """Initialize the auth configurator.

        Args:
            config: Server configuration object
            logger: Optional logger instance (defaults to module logger)
            server: Optional Server instance for callbacks (on_user_registered)
        """
        self.config = config
        self._logger = logger or logging.getLogger(__name__)
        self._server = server
        self._auth_config: Optional[AuthConfig] = None
        self._auth_router: Optional[APIRouter] = None
        self._auth_endpoints_registered = False
        self._auth_service: Optional[AuthenticationService] = None
        self._oauth_router: Optional[APIRouter] = None
        self._well_known_router: Optional[APIRouter] = None

    def configure(self) -> Optional[AuthConfig]:
        """Configure authentication middleware and register auth endpoints if enabled.

        Returns:
            AuthConfig instance if auth is enabled, None otherwise
        """
        if not self.config.auth.enabled:
            return None

        # Return existing config if already configured (idempotent)
        if self._auth_config is not None:
            return self._auth_config

        # Use unified config directly - no mapping needed
        self._auth_config = self.config.auth

        # Store values for closures (avoid closure issues)
        self._jwt_secret = self._auth_config.jwt_secret
        self._jwt_algorithm = self._auth_config.jwt_algorithm
        self._jwt_expire_minutes = self._auth_config.jwt_expire_minutes
        self._refresh_expire_days = self._auth_config.refresh_expire_days
        self._refresh_token_rotation = self._auth_config.refresh_token_rotation
        self._blacklist_cache_ttl_seconds = (
            self._auth_config.blacklist_cache_ttl_seconds
        )
        self._role_permission_mapping = self._auth_config.role_permission_mapping
        self._admin_role = self._auth_config.admin_role
        self._default_role = self._auth_config.default_role

        # Create and cache the auth service singleton for consumer apps
        self._auth_service = AuthenticationService(
            GraphContext(database=get_prime_database()),
            jwt_secret=self._jwt_secret,
            jwt_algorithm=self._jwt_algorithm,
            jwt_expire_minutes=self._jwt_expire_minutes,
            refresh_expire_days=self._refresh_expire_days,
            refresh_token_rotation=self._refresh_token_rotation,
            blacklist_cache_ttl_seconds=self._blacklist_cache_ttl_seconds,
            password_reset_token_expiry_minutes=getattr(
                self._auth_config,
                "password_reset_token_expiry_minutes",
                60,
            ),
            role_permission_mapping=self._role_permission_mapping,
            admin_role=self._admin_role,
            default_role=self._default_role,
            registration_open=self.config.auth.registration_open,
        )

        # Register authentication endpoints
        self._register_auth_endpoints()

        self._logger.debug(
            f"🔐 Authentication configured: JWT=enabled, "
            f"API-key-mgmt={self._auth_config.api_key_management_enabled}, "
            f"endpoints-registered={self._auth_endpoints_registered}"
        )

        return self._auth_config

    def _register_auth_endpoints(self) -> None:
        """Register authentication endpoints if auth is enabled."""
        if self._auth_endpoints_registered:
            return

        def get_auth_service():
            """Get cached authentication service singleton."""
            return self._auth_service

        # Create auth router
        auth_router = APIRouter(prefix="/auth", tags=["Auth"])

        # Use auto_error=False so we can raise 401 (not 403) for missing credentials.
        # FastAPI's HTTPBearer returns 403 in older versions and 401 in newer ones;
        # we explicitly raise 401 for consistency across environments.
        security = HTTPBearer(scheme_name="BearerAuth", auto_error=False)

        # Helper function to get current user from token.
        # Uses HTTPBearer dependency so auth is handled via security scheme (no redundant param).
        async def get_current_user(
            credentials: Optional[HTTPAuthorizationCredentials] = Depends(  # noqa: B008
                security
            ),
        ) -> UserResponse:
            """Get current user from Authorization header."""
            if not credentials:
                raise HTTPException(status_code=401, detail="Not authenticated")
            token = credentials.credentials

            # Initialize authentication service and validate token
            auth_service = get_auth_service()
            user = await auth_service.validate_token(token)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid or expired token")

            return user

        async def require_admin(
            current_user: UserResponse = Depends(get_current_user),  # noqa: B008
        ) -> UserResponse:
            """Require admin role. Raises 403 if user is not admin."""
            if self._admin_role not in (current_user.roles or []):
                raise HTTPException(
                    status_code=403,
                    detail="Admin access required",
                )
            return current_user

        # Register endpoint (accepts extra fields for on_user_registered callback)
        @auth_router.post("/register", response_model=UserResponse)
        async def register(request: Request):
            """Register a new user.

            The email field is validated by Pydantic's EmailStr type.
            Extra fields in the request body are passed to on_user_registered callback.
            """
            try:
                body = await request.json() if hasattr(request, "json") else {}
            except Exception:
                body = {}
            if not isinstance(body, dict):
                body = {}
            email = body.get("email")
            password = body.get("password")
            if not email or not password:
                raise HTTPException(
                    status_code=422,
                    detail="email and password are required",
                )
            if len(password) < 6:
                raise HTTPException(
                    status_code=422,
                    detail="password must be at least 6 characters",
                )
            try:
                auth_service = get_auth_service()
                user_data = UserCreate(email=email, password=password)
                user = await auth_service.register_user(user_data)
                callback = (
                    getattr(self._server, "_on_user_registered", None)
                    if self._server
                    else None
                )
                if callback and user:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(user, body)
                        else:
                            callback(user, body)
                    except Exception as e:
                        self._logger.exception(
                            "on_user_registered callback failed: %s", e
                        )
                return user
            except RegistrationDisabledError:
                raise
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                self._logger.error(f"Registration error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Current user endpoint (requires authentication)
        @auth_router.get("/me")
        async def get_me(
            current_user: UserResponse = Depends(get_current_user),  # noqa: B008
        ):
            """Get the currently authenticated user's information."""
            data = current_user.model_dump()
            callback = (
                getattr(self._server, "_on_enrich_current_user", None)
                if self._server
                else None
            )
            if callback:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        extra = await callback(current_user)
                    else:
                        extra = callback(current_user)
                    if isinstance(extra, dict):
                        data.update(extra)
                except Exception as e:
                    self._logger.exception(
                        "on_enrich_current_user callback failed: %s", e
                    )
            return {"user": data}

        # Login endpoint
        @auth_router.post("/login", response_model=TokenResponse)
        async def login(login_data: UserLogin):
            """Login endpoint for authentication."""
            try:
                # Initialize authentication service with current context
                auth_service = get_auth_service()
                token_response = await auth_service.login_user(login_data)
                return token_response
            except ValueError as e:
                raise HTTPException(status_code=401, detail=str(e))
            except Exception as e:
                self._logger.error(f"Login error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Logout endpoint (requires authentication)
        # Note: Depends(security) is required by FastAPI for dependency injection
        _default_security_dep = Depends(security)  # noqa: B008

        @auth_router.post("/logout", dependencies=[_default_security_dep])
        async def logout(credentials: HTTPAuthorizationCredentials = _default_security_dep):  # type: ignore[assignment]
            """Logout endpoint for authentication."""
            try:
                # Initialize authentication service with current context
                auth_service = get_auth_service()

                # Get token from credentials
                token = credentials.credentials

                # Validate token and blacklist it
                await auth_service.logout_user(token)

                return {"message": "Logged out successfully"}
            except Exception as e:
                self._logger.error(f"Logout error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Refresh token endpoint
        @auth_router.post("/refresh", response_model=TokenResponse)
        async def refresh_token(request: TokenRefreshRequest):
            """Refresh access token using refresh token."""
            try:
                auth_service = get_auth_service()
                token_response = await auth_service.refresh_access_token(
                    request.refresh_token
                )
                return token_response
            except ValueError as e:
                raise HTTPException(status_code=401, detail=str(e))
            except Exception as e:
                self._logger.error(f"Token refresh error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Revoke all tokens endpoint (requires authentication)
        @auth_router.post("/revoke-all", dependencies=[_default_security_dep])
        async def revoke_all_tokens(
            current_user: UserResponse = Depends(get_current_user),  # noqa: B008
        ):
            """Revoke all refresh tokens for the authenticated user."""
            try:
                auth_service = get_auth_service()
                revoked_count = await auth_service.revoke_all_user_tokens(
                    current_user.id
                )
                return {
                    "message": f"Revoked {revoked_count} token(s) successfully",
                    "revoked_count": revoked_count,
                }
            except Exception as e:
                self._logger.error(f"Revoke all tokens error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Change password endpoint (requires authentication)
        if getattr(self.config.auth, "password_change_enabled", True):

            @auth_router.post("/change-password", dependencies=[_default_security_dep])
            async def change_password(
                request: PasswordChangeRequest,
                current_user: UserResponse = Depends(get_current_user),  # noqa: B008
            ):
                """Change password for the authenticated user."""
                try:
                    auth_service = get_auth_service()
                    await auth_service.change_password(
                        current_user.id,
                        request.current_password,
                        request.new_password,
                    )
                    return {"message": "Password changed successfully"}
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                except Exception as e:
                    self._logger.error(f"Change password error: {e}")
                    raise HTTPException(status_code=500, detail="Internal server error")

        # Forgot password endpoint (public)
        if getattr(self.config.auth, "password_reset_enabled", True):

            @auth_router.post("/forgot-password")
            async def forgot_password(request: ForgotPasswordRequest):
                """Request a password reset link. Always returns success (no enumeration)."""
                try:
                    auth_service = get_auth_service()
                    on_reset = getattr(
                        self._server, "_on_password_reset_requested", None
                    )
                    reset_base = (
                        getattr(self.config.auth, "password_reset_base_url", None) or ""
                    )
                    await auth_service.request_password_reset(
                        request.email,
                        on_reset_requested=on_reset,
                        reset_base_url=reset_base,
                    )
                    return {
                        "message": "If an account exists, a reset link has been sent."
                    }
                except Exception as e:
                    self._logger.error(f"Forgot password error: {e}")
                    raise HTTPException(status_code=500, detail="Internal server error")

            @auth_router.post("/reset-password")
            async def reset_password(request: ResetPasswordRequest):
                """Complete password reset with token from email."""
                try:
                    auth_service = get_auth_service()
                    await auth_service.reset_password_with_token(
                        request.token, request.new_password
                    )
                    return {"message": "Password reset successfully"}
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid or expired token",
                    )
                except Exception as e:
                    self._logger.error(f"Reset password error: {e}")
                    raise HTTPException(status_code=500, detail="Internal server error")

        # API Key Management Endpoints (require authentication)
        if self.config.auth.api_key_management_enabled:
            # Helper function to get API key service
            def get_api_key_service():
                """Get API key service using prime database."""
                prime_ctx = GraphContext(database=get_prime_database())
                return APIKeyService(prime_ctx)

            # Create API key endpoint
            @auth_router.post(
                "/api-keys",
                response_model=APIKeyCreateResponse,
                dependencies=[Depends(security)],  # Require authentication
            )
            async def create_api_key(
                request: APIKeyCreateRequest,
                current_user: UserResponse = Depends(get_current_user),  # noqa: B008
            ):
                """Generate a new API key for the authenticated user."""
                try:
                    service = get_api_key_service()
                    plaintext_key, api_key = await service.generate_key(
                        user_id=current_user.id,
                        name=request.name,
                        permissions=request.permissions or [],
                        rate_limit_override=request.rate_limit_override,
                        expires_in_days=request.expires_in_days,
                        allowed_ips=request.allowed_ips or [],
                        allowed_endpoints=request.allowed_endpoints or [],
                        key_prefix=self.config.auth.api_key_prefix,
                    )

                    return APIKeyCreateResponse(
                        key=plaintext_key,
                        key_id=api_key.id,
                        key_prefix=api_key.key_prefix,
                        name=api_key.name,
                        message="Store this key securely. It won't be shown again.",
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                except Exception as e:
                    self._logger.error(f"API key creation error: {e}")
                    raise HTTPException(status_code=500, detail="Internal server error")

            # List API keys endpoint
            @auth_router.get(
                "/api-keys",
                response_model=List[APIKeyResponse],
                dependencies=[Depends(security)],  # Require authentication
            )
            async def list_api_keys(
                current_user: UserResponse = Depends(get_current_user),  # noqa: B008
            ):
                """List all API keys for the authenticated user."""
                try:
                    service = get_api_key_service()
                    keys = await service.get_user_keys(current_user.id)

                    return [
                        APIKeyResponse(
                            id=key.id,
                            name=key.name,
                            key_prefix=key.key_prefix,
                            created_at=key.created_at,
                            last_used_at=key.last_used_at,
                            expires_at=key.expires_at,
                            is_active=key.is_active,
                            permissions=key.permissions,
                            rate_limit_override=key.rate_limit_override,
                        )
                        for key in keys
                    ]
                except Exception as e:
                    self._logger.error(f"API key listing error: {e}")
                    raise HTTPException(status_code=500, detail="Internal server error")

            # Revoke API key endpoint
            @auth_router.delete(
                "/api-keys/{key_id}",
                dependencies=[Depends(security)],  # Require authentication
            )
            async def revoke_api_key(
                key_id: str,
                current_user: UserResponse = Depends(get_current_user),  # noqa: B008
            ):
                """Revoke an API key."""
                try:
                    service = get_api_key_service()
                    success = await service.revoke_key(key_id, current_user.id)
                    if not success:
                        raise HTTPException(
                            status_code=404, detail="API key not found or unauthorized"
                        )
                    return {"message": "API key revoked successfully"}
                except HTTPException:
                    raise
                except Exception as e:
                    self._logger.error(f"API key revocation error: {e}")
                    raise HTTPException(status_code=500, detail="Internal server error")

        # Admin user management endpoints (require admin role)
        @auth_router.post(
            "/admin/users",
            response_model=UserResponse,
            dependencies=[Depends(security)],
        )
        async def create_user_admin(
            user_data: UserCreateAdmin,
            _: UserResponse = Depends(require_admin),  # noqa: B008
        ):
            """Create a user with specified roles and permissions (admin only)."""
            try:
                auth_service = get_auth_service()
                return await auth_service.create_user_with_roles(user_data)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                self._logger.error(f"Admin user creation error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @auth_router.patch(
            "/admin/users/{user_id}/roles",
            response_model=UserResponse,
            dependencies=[Depends(security)],
        )
        async def update_user_roles_admin(
            user_id: str,
            roles_update: UserRolesUpdate,
            _: UserResponse = Depends(require_admin),  # noqa: B008
        ):
            """Update user roles (admin only)."""
            try:
                auth_service = get_auth_service()
                result = await auth_service.update_user_roles(user_id, roles_update)
                if not result:
                    raise HTTPException(status_code=404, detail="User not found")
                return result
            except HTTPException:
                raise
            except Exception as e:
                self._logger.error(f"Admin role update error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @auth_router.patch(
            "/admin/users/{user_id}/permissions",
            response_model=UserResponse,
            dependencies=[Depends(security)],
        )
        async def update_user_permissions_admin(
            user_id: str,
            permissions_update: UserPermissionsUpdate,
            _: UserResponse = Depends(require_admin),  # noqa: B008
        ):
            """Update user direct permissions (admin only)."""
            try:
                auth_service = get_auth_service()
                result = await auth_service.update_user_permissions(
                    user_id, permissions_update
                )
                if not result:
                    raise HTTPException(status_code=404, detail="User not found")
                return result
            except HTTPException:
                raise
            except Exception as e:
                self._logger.error(f"Admin permissions update error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        @auth_router.get(
            "/admin/users",
            response_model=List[UserResponse],
            dependencies=[Depends(security)],
        )
        async def list_users_admin(
            _: UserResponse = Depends(require_admin),  # noqa: B008
        ):
            """List all users with roles and permissions (admin only)."""
            try:
                auth_service = get_auth_service()
                users = await auth_service.list_users()
                return users
            except Exception as e:
                self._logger.error(f"Admin user list error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Store auth router
        self._auth_router = auth_router
        self._auth_endpoints_registered = True

        # OAuth 2.1 authorization server (opt-in). The /.well-known discovery
        # documents are public by spec (RFC 8615), so they are exempted from the
        # bearer middleware unconditionally — when the routes are not mounted
        # (oauth disabled) the exemption simply lets FastAPI return its natural
        # 404 instead of a spurious 401 from the deny-by-default resolver.
        self._exempt_oauth_paths(
            [
                "/.well-known/oauth-authorization-server",
                "/.well-known/jwks.json",
                "/.well-known/oauth-protected-resource",
            ]
        )
        if getattr(self._auth_config, "oauth_enabled", False):
            self._configure_oauth_endpoints(get_current_user)

    def _configure_oauth_endpoints(self, get_current_user: Any) -> None:
        """Build the OAuth routers, exempt their paths, and register the key hook.

        The token/register/revoke endpoints are client-authenticated (or public),
        never bearer-gated, so their prefix-relative paths are added to the
        auth-exempt set (the deny-by-default endpoint resolver would otherwise
        401 these plain FastAPI routes). ``/authorize`` is likewise exempt from
        the middleware, but its GET/POST handlers gate on the *session user* via
        ``Depends(get_current_user)`` — the consent step needs the authenticated
        resource owner so its permissions (never client/request input) can be
        intersected with the requested scope. The signing key is generated at
        startup via a lifecycle hook so the first JWKS / token request is warm.

        Args:
            get_current_user: The session-user dependency closure from
                :meth:`_register_auth_endpoints`, threaded into the authorize
                route so it can resolve the bearer-authenticated resource owner.
        """
        from jvspatial.api.auth.oauth.routes import build_oauth_routers

        self._oauth_router, self._well_known_router = build_oauth_routers(
            self._auth_config, get_current_user=get_current_user
        )

        prefix = getattr(self._auth_config, "oauth_prefix", "/oauth") or "/oauth"
        prefix = "/" + prefix.strip("/")
        self._exempt_oauth_paths(
            [
                f"{prefix}/{name}"
                for name in ("token", "register", "revoke", "authorize")
            ]
        )

        if self._server is not None:
            self._server.lifecycle_manager.add_startup_hook(
                self._ensure_oauth_signing_key
            )
            self._wire_dcr_rate_limit(prefix)

    def _wire_dcr_rate_limit(self, oauth_prefix: str) -> None:
        """Register a tight rate-limit override for the DCR endpoint (I-1).

        Dynamic Client Registration is unauthenticated, so an uncapped endpoint
        can be abused to fill the database with junk clients (resource-exhaustion
        DoS). When ``oauth_enabled`` and ``oauth_dcr_rate_limit_per_minute > 0``,
        we write a per-path override onto ``server.config.rate_limit`` BEFORE
        ``get_app()`` calls ``_configure_rate_limit_middleware``, which reads the
        override dict at build time.

        We also enable ``rate_limit_enabled`` when it is still False, so that an
        application that has not explicitly configured rate limiting still gets the
        DCR protection. We never flip the flag back to False — if the caller already
        set ``rate_limit_enabled=True`` we leave it alone.

        Multi-worker note: this cap inherits whatever backend the rate-limit
        middleware selects. The default in-memory backend counts per process, so
        under ``N`` workers the DCR endpoint effectively allows ``N × cap``
        registrations/min. For a hard global DCR cap, supply a shared backend via
        ``ServerConfig.rate_limit_backend`` (e.g. ``RedisRateLimitBackend``).

        Args:
            oauth_prefix: The OAuth router prefix (e.g. ``/oauth``), already
                normalised to a leading slash by the caller.
        """
        if self._server is None or self._auth_config is None:
            return
        cap = getattr(self._auth_config, "oauth_dcr_rate_limit_per_minute", 0)
        if not cap:
            return

        from jvspatial.api.constants import APIRoutes

        # Full path that the rate-limit middleware matches against request.url.path.
        # oauth_prefix is already "/oauth"; the DCR handler is at "/register".
        # The oauth_router is mounted with prefix=APIRoutes.PREFIX ("/api"), so the
        # full path is "/api/oauth/register".  We store it with the full prefix so
        # _build_rate_limit_config does not double-add it.
        dcr_path = f"{APIRoutes.PREFIX}{oauth_prefix}/register"

        rl = self._server.config.rate_limit
        rl.rate_limit_overrides[dcr_path] = {"requests": cap, "window": 60}

        # Enable rate limiting when it has not been explicitly turned on yet.
        # This ensures open-DCR protection even when the server operator has not
        # configured rate_limit_enabled=True globally.
        if not rl.rate_limit_enabled:
            rl.rate_limit_enabled = True
            self._logger.debug(
                "rate_limit_enabled implicitly set to True for DCR protection (I-1)"
            )

        self._logger.debug("DCR rate limit: %d req/min on %s (I-1)", cap, dcr_path)

    def _exempt_oauth_paths(self, paths: List[str]) -> None:
        """Add *paths* to the auth-config exempt list (idempotent).

        The auth middleware constructs its :class:`PathMatcher` from
        ``auth_config.exempt_paths`` when the app is built (after this configurator
        runs), so mutating the list here is reflected at request time. PathMatcher
        expands both prefixed (``/api/oauth/token``) and bare (``/oauth/token``)
        variants, so prefix-relative entries suffice.
        """
        if self._auth_config is None:
            return
        existing = list(self._auth_config.exempt_paths or [])
        for path in paths:
            if path not in existing:
                existing.append(path)
        self._auth_config.exempt_paths = existing

    async def _ensure_oauth_signing_key(self) -> None:
        """Startup hook: ensure an active RS256 OAuth signing key exists."""
        from jvspatial.api.auth.oauth import keys

        await keys.ensure_signing_key()

    @property
    def oauth_router(self) -> Optional[APIRouter]:
        """Get the OAuth router (token/register/revoke/authorize), or None.

        Returns:
            The API-prefixed OAuth :class:`APIRouter` when oauth is enabled,
            otherwise ``None``.
        """
        return self._oauth_router

    @property
    def well_known_router(self) -> Optional[APIRouter]:
        """Get the root-mounted OAuth discovery router, or None.

        Returns:
            The :class:`APIRouter` serving ``/.well-known`` metadata + JWKS when
            oauth is enabled, otherwise ``None``.
        """
        return self._well_known_router

    @property
    def auth_config(self) -> Optional[AuthConfig]:
        """Get the auth configuration.

        Returns:
            AuthConfig instance if configured, None otherwise
        """
        return self._auth_config

    @property
    def auth_service(self) -> Optional[AuthenticationService]:
        """Get the cached authentication service singleton.

        Returns:
            AuthenticationService instance if auth is configured, None otherwise
        """
        return self._auth_service

    @property
    def auth_router(self) -> Optional[APIRouter]:
        """Get the auth router.

        Returns:
            APIRouter instance if endpoints are registered, None otherwise
        """
        return self._auth_router

    @property
    def has_auth_endpoints(self) -> bool:
        """Check if auth endpoints are registered.

        Returns:
            True if auth endpoints are registered, False otherwise
        """
        return self._auth_endpoints_registered


__all__ = ["AuthConfigurator"]
