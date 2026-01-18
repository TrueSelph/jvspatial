"""Authentication configuration for jvspatial API.

This module provides authentication endpoint registration and configuration,
extracted from the Server class for better separation of concerns.
"""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jvspatial.api.auth.api_key_service import APIKeyService
from jvspatial.api.auth.config import AuthConfig
from jvspatial.api.auth.models import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from jvspatial.api.auth.service import AuthenticationService
from jvspatial.core.context import GraphContext
from jvspatial.db import get_prime_database


class AuthConfigurator:
    """Configurator for authentication endpoints and middleware.

    Handles registration of authentication endpoints (register, login, logout)
    and API key management endpoints.
    """

    def __init__(self, config: Any, logger: Optional[logging.Logger] = None):
        """Initialize the auth configurator.

        Args:
            config: Server configuration object
            logger: Optional logger instance (defaults to module logger)
        """
        self.config = config
        self._logger = logger or logging.getLogger(__name__)
        self._auth_config: Optional[AuthConfig] = None
        self._auth_router: Optional[APIRouter] = None
        self._auth_endpoints_registered = False

    def configure(self) -> Optional[AuthConfig]:
        """Configure authentication middleware and register auth endpoints if enabled.

        Returns:
            AuthConfig instance if auth is enabled, None otherwise
        """
        if not self.config.auth.auth_enabled:
            return None

        # Return existing config if already configured (idempotent)
        if self._auth_config is not None:
            return self._auth_config

        # Create auth configuration - only pass fields that are not None
        # AuthConfig has defaults for all fields, so we only override when explicitly set
        auth_config_kwargs = {
            "enabled": True,
        }

        # Only include fields that are explicitly set (not None)
        if self.config.auth.auth_exempt_paths is not None:
            auth_config_kwargs["exempt_paths"] = self.config.auth.auth_exempt_paths
        # Always include JWT config if auth is enabled (they have defaults but should use config values)
        auth_config_kwargs["jwt_secret"] = self.config.auth.jwt_secret
        auth_config_kwargs["jwt_algorithm"] = self.config.auth.jwt_algorithm
        auth_config_kwargs["jwt_expire_minutes"] = self.config.auth.jwt_expire_minutes
        if self.config.auth.api_key_header is not None:
            auth_config_kwargs["api_key_header"] = self.config.auth.api_key_header
        # Include api_key_management_enabled (supports both new and old flag names)
        api_key_mgmt_enabled = getattr(
            self.config.auth, "api_key_management_enabled", None
        ) or getattr(self.config.auth, "api_key_auth_enabled", True)
        if api_key_mgmt_enabled is not None:
            auth_config_kwargs["api_key_management_enabled"] = api_key_mgmt_enabled
        if self.config.auth.session_cookie_name is not None:
            auth_config_kwargs["session_cookie_name"] = (
                self.config.auth.session_cookie_name
            )
        if self.config.auth.session_expire_minutes is not None:
            auth_config_kwargs["session_expire_minutes"] = (
                self.config.auth.session_expire_minutes
            )

        self._auth_config = AuthConfig(**auth_config_kwargs)

        # Store JWT config for use in closures (avoid closure issues)
        self._jwt_secret = self._auth_config.jwt_secret
        self._jwt_algorithm = self._auth_config.jwt_algorithm
        self._jwt_expire_minutes = self._auth_config.jwt_expire_minutes

        # Register authentication endpoints
        self._register_auth_endpoints()

        # Log authentication configuration
        api_key_mgmt = getattr(self._auth_config, "api_key_management_enabled", True)
        self._logger.debug(
            f"🔐 Authentication configured: JWT=enabled, "
            f"API-key-mgmt={api_key_mgmt}, "
            f"endpoints-registered={self._auth_endpoints_registered}"
        )

        return self._auth_config

    def _register_auth_endpoints(self) -> None:
        """Register authentication endpoints if auth is enabled."""
        if self._auth_endpoints_registered:
            return

        # Helper function to get authentication service
        # Use stored JWT config values to avoid closure issues
        jwt_secret = self._jwt_secret
        jwt_algorithm = self._jwt_algorithm
        jwt_expire_minutes = self._jwt_expire_minutes

        def get_auth_service():
            """Get authentication service using prime database for core persistence.

            Authentication and session management always use the prime database
            regardless of the current database context.
            """
            # Create context with prime database for auth operations
            prime_ctx = GraphContext(database=get_prime_database())
            return AuthenticationService(
                prime_ctx,
                jwt_secret=jwt_secret,
                jwt_algorithm=jwt_algorithm,
                jwt_expire_minutes=jwt_expire_minutes,
            )

        # Create auth router
        auth_router = APIRouter(prefix="/auth", tags=["App"])

        # Create custom security scheme for BearerAuth compatibility
        security = HTTPBearer(scheme_name="BearerAuth")

        # Helper function to get current user from token
        # Note: Header(None) is required by FastAPI for optional headers
        _default_header = Header(None)  # noqa: B008

        async def get_current_user(
            authorization: Optional[str] = _default_header,  # type: ignore[assignment]
        ) -> UserResponse:
            """Get current user from Authorization header."""
            if not authorization:
                raise HTTPException(
                    status_code=401, detail="Authorization header required"
                )

            # Extract token from "Bearer <token>" format
            try:
                scheme, token = authorization.split(" ", 1)
                if scheme.lower() != "bearer":
                    raise HTTPException(
                        status_code=401, detail="Invalid authentication scheme"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=401, detail="Invalid authorization header format"
                )

            # Initialize authentication service and validate token
            auth_service = get_auth_service()
            user = await auth_service.validate_token(token)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid or expired token")

            return user

        # Register endpoint
        @auth_router.post("/register", response_model=UserResponse)
        async def register(user_data: UserCreate):
            """Register a new user.

            The email field is validated by Pydantic's EmailStr type,
            which ensures proper email format before this function is called.
            """
            try:
                # Initialize authentication service with current context
                auth_service = get_auth_service()
                user = await auth_service.register_user(user_data)
                return user
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                self._logger.error(f"Registration error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

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

        # API Key Management Endpoints (require authentication)
        # Support both new and deprecated flag names for backward compatibility
        api_key_mgmt_enabled = getattr(
            self.config.auth, "api_key_management_enabled", None
        ) or getattr(self.config.auth, "api_key_auth_enabled", True)
        if api_key_mgmt_enabled:
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

        # Store auth router
        self._auth_router = auth_router
        self._auth_endpoints_registered = True

    @property
    def auth_config(self) -> Optional[AuthConfig]:
        """Get the auth configuration.

        Returns:
            AuthConfig instance if configured, None otherwise
        """
        return self._auth_config

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
