"""Optimized authentication middleware for jvspatial API.

This module provides streamlined authentication middleware with pre-compiled patterns
for optimal performance, following the new standard implementation approach.
"""

import logging
import re
from typing import Any, List, Optional, Pattern

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from jvspatial.api.auth.config import AuthConfig
from jvspatial.api.constants import APIRoutes


class PathMatcher:
    """Optimized path matching with pre-compiled patterns.

    This class provides efficient path matching for authentication exemptions
    using pre-compiled regular expressions.
    """

    def __init__(self, exempt_paths: List[str]):
        """Initialize the path matcher.

        Args:
            exempt_paths: List of path patterns to exempt from authentication
        """
        self.exempt_paths = self._expand_api_variants(exempt_paths)
        self._compiled_patterns = self._compile_exempt_patterns()

    def _expand_api_variants(self, exempt_paths: List[str]) -> List[str]:
        """Add API-prefixed and un-prefixed variants, honoring configurable prefix.

        Handles dynamically set APIRoutes.PREFIX (default "/api") so auth
        exemptions remain correct even when the API is mounted under a custom
        prefix or at root.
        """
        prefix = APIRoutes.PREFIX or ""
        # Normalize prefix to start with "/" and have no trailing "/"
        if prefix and not prefix.startswith("/"):
            prefix = f"/{prefix}"
        if prefix.endswith("/") and prefix != "/":
            prefix = prefix.rstrip("/")

        expanded: List[str] = []
        for path in exempt_paths:
            # normalize path to start with "/"
            normalized = path if path.startswith("/") else f"/{path}"
            expanded.append(normalized)

            # Add prefixed version when prefix is non-empty and not already present
            if prefix and prefix != "/" and not normalized.startswith(prefix):
                expanded.append(f"{prefix}{normalized}")

            # If config already provided prefixed path, add unprefixed twin
            if prefix and prefix != "/" and normalized.startswith(prefix):
                without_prefix = normalized[len(prefix) :] or "/"
                expanded.append(without_prefix)

        # Preserve order but drop duplicates
        seen = set()
        deduped: List[str] = []
        for p in expanded:
            if p not in seen:
                deduped.append(p)
                seen.add(p)
        return deduped

    def _compile_exempt_patterns(self) -> List[Pattern]:
        """Pre-compile patterns for optimal performance.

        Returns:
            List of compiled regular expression patterns
        """
        compiled_patterns = []
        for pattern in self.exempt_paths:
            # Convert wildcard pattern to regex
            regex_pattern = pattern.replace("*", ".*")
            try:
                compiled_patterns.append(re.compile(regex_pattern))
            except re.error as e:
                logging.getLogger(__name__).warning(f"Invalid pattern '{pattern}': {e}")

        return compiled_patterns

    def is_exempt(self, path: str) -> bool:
        """Check if a path is exempt from authentication.

        Args:
            path: URL path to check

        Returns:
            True if path is exempt, False otherwise
        """
        return any(pattern.match(path) for pattern in self._compiled_patterns)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Streamlined authentication middleware with optimized performance.

    This middleware provides efficient authentication with pre-compiled patterns
    and streamlined request processing, following the new standard implementation.
    """

    def __init__(self, app, auth_config: AuthConfig, server):
        """Initialize the authentication middleware.

        Args:
            app: FastAPI application instance
            auth_config: Authentication configuration
            server: Server instance (required for endpoint auth checking)
        """
        super().__init__(app)
        self.auth_config = auth_config
        self.path_matcher = PathMatcher(auth_config.exempt_paths)
        self._logger = logging.getLogger(__name__)
        if server is None:
            raise ValueError("AuthenticationMiddleware requires a server instance")
        self._server = server  # Store server reference - always use this, not context

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
        if self.path_matcher.is_exempt(request.url.path):
            return await call_next(request)

        # Check if this endpoint requires authentication
        auth_required = self._endpoint_requires_auth(request)

        if not auth_required:
            return await call_next(request)

        # Streamlined authentication logic
        user = await self._authenticate_request(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={
                    "error_code": "authentication_required",
                    "message": "Authentication required",
                    "path": request.url.path,
                },
            )

        # Set user in request state for downstream handlers
        request.state.user = user
        return await call_next(request)

    def _path_matches(self, pattern: str, path: str) -> bool:
        """Check if a request path matches a route pattern with path parameters.

        Args:
            pattern: Route pattern (e.g., "/agents/{agent_id}/interact")
            path: Actual request path (e.g., "/agents/abc123/interact")

        Returns:
            True if path matches pattern, False otherwise
        """
        import re

        # Convert pattern to regex by replacing {param} with [^/]+
        # Escape other special regex characters first
        escaped_pattern = re.escape(pattern)
        # Replace escaped {param} patterns with regex
        regex_pattern = re.sub(r"\\\{(\w+)\\\}", r"[^/]+", escaped_pattern)
        # Also handle unescaped patterns (in case pattern wasn't escaped)
        regex_pattern = re.sub(r"\{(\w+)\}", r"[^/]+", regex_pattern)

        # Match the entire path
        regex_pattern = f"^{regex_pattern}$"

        return bool(re.match(regex_pattern, path))

    def _endpoint_requires_auth(self, request: Request) -> bool:
        """Check if endpoint requires authentication using registry only.

        SECURITY: This method defaults to requiring authentication unless the endpoint
        is explicitly registered with auth=False. This "deny by default" approach
        ensures that path matching failures don't create security vulnerabilities.

        Args:
            request: Incoming request

        Returns:
            True if authentication is required (default), False only if endpoint
            is explicitly registered with auth=False
        """
        try:
            # Always use stored server reference - it's required during initialization
            server = self._server

            if not server:
                self._logger.error(
                    "_endpoint_requires_auth: No server found - DENYING access"
                )
                return True  # SECURITY: Deny by default

            # Check if any endpoints in the registry require auth for this path
            registry = server._endpoint_registry
            request_path = request.url.path

            # Normalize request path by removing API prefix for registry comparison
            # Registry stores paths without prefix (router adds it when including routes)
            # Requests include prefix (e.g., "/api/agents/123")
            api_prefix = APIRoutes.PREFIX
            normalized_path = request_path

            if api_prefix and request_path.startswith(api_prefix):
                # Remove prefix: "/api/agents/123" -> "/agents/123"
                normalized_path = request_path[len(api_prefix) :]
                # Handle edge case: "/api" -> "" should become "/"
                if not normalized_path:
                    normalized_path = "/"

            # Log path normalization for debugging (at debug level)
            if normalized_path != request_path:
                self._logger.debug(
                    f"Path normalized: {request_path} -> {normalized_path}"
                )

            # Check function endpoints by accessing internal registry directly
            # This gives us access to both the handler and the EndpointInfo
            for func, endpoint_info in registry._function_registry.items():
                func_path = endpoint_info.path

                # Match using normalized path (for paths registered without prefix)
                # Also check original request path for backward compatibility
                if (
                    func_path in (normalized_path, request_path)
                    or self._path_matches(func_path, normalized_path)
                    or self._path_matches(func_path, request_path)
                ):
                    endpoint_config = getattr(func, "_jvspatial_endpoint_config", None)
                    if endpoint_config is None:
                        # SECURITY: Endpoint found but no config - deny access
                        self._logger.warning(
                            f"Endpoint found in registry but missing config: {normalized_path} - DENYING access"
                        )
                        return True

                    auth_required = endpoint_config.get("auth_required", False)
                    self._logger.debug(
                        f"Function endpoint {normalized_path}: auth_required={auth_required}"
                    )
                    return auth_required

            # Check walker endpoints by accessing internal registry directly
            for walker_class, endpoint_info in registry._walker_registry.items():
                walker_path = endpoint_info.path

                # Match using normalized path (for paths registered without prefix)
                # Also check original request path for backward compatibility
                if (
                    walker_path in (normalized_path, request_path)
                    or self._path_matches(walker_path, normalized_path)
                    or self._path_matches(walker_path, request_path)
                ):
                    endpoint_config = getattr(
                        walker_class, "_jvspatial_endpoint_config", None
                    )
                    if endpoint_config is None:
                        # SECURITY: Endpoint found but no config - deny access
                        self._logger.warning(
                            f"Walker endpoint found in registry but missing config: {normalized_path} - DENYING access"
                        )
                        return True

                    auth_required = endpoint_config.get("auth_required", False)
                    self._logger.debug(
                        f"Walker endpoint {normalized_path}: auth_required={auth_required}"
                    )
                    return auth_required

            # SECURITY: Endpoint not in registry - DENY by default
            # This is a critical security decision: we require authentication for any
            # endpoint that isn't explicitly registered, preventing bypass via path manipulation
            self._logger.debug(
                f"Endpoint not found in registry: {normalized_path} (original: {request_path}) - DENYING access"
            )
            return True  # SECURITY: Deny by default

        except Exception as e:
            # SECURITY: On any error, deny access to prevent bypasses
            self._logger.error(
                f"Error checking endpoint auth requirements for {request.url.path}: {e} - DENYING access",
                exc_info=True,
            )
            return True  # SECURITY: Deny on error

    async def _authenticate_request(self, request: Request) -> Optional[Any]:
        """Authenticate the incoming request.

        Args:
            request: Incoming request

        Returns:
            User object if authenticated, None otherwise
        """
        try:
            # Try JWT authentication first
            if "authorization" in request.headers:
                return await self._authenticate_jwt(request)

            # Try API key authentication
            if "x-api-key" in request.headers:
                return await self._authenticate_api_key(request)

            # Try session authentication
            if "session" in request.cookies:
                return await self._authenticate_session(request)

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
            # Always use stored server reference - it's required during initialization
            server = self._server

            if not server:
                self._logger.error(
                    "_authenticate_jwt: No server found (this should never happen)"
                )
                return None

            # Initialize authentication service with JWT config from auth_config
            from jvspatial.api.auth.service import AuthenticationService

            auth_service = AuthenticationService(
                server._graph_context,
                jwt_secret=self.auth_config.jwt_secret,
                jwt_algorithm=self.auth_config.jwt_algorithm,
                jwt_expire_minutes=self.auth_config.jwt_expire_minutes,
            )

            # Extract token from Authorization header
            auth_header = request.headers.get("authorization", "")
            if not auth_header.startswith("Bearer "):
                return None

            token = auth_header[7:]  # Remove "Bearer " prefix

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

    async def _authenticate_session(self, request: Request) -> Optional[Any]:
        """Authenticate using session cookie.

        Args:
            request: Incoming request

        Returns:
            User object if session is valid, None otherwise
        """
        try:
            # Placeholder session authentication implementation
            session_id = request.cookies.get("session", "")
            if not session_id:
                return None

            # Simple session validation (replace with actual verification)
            if session_id and len(session_id) > 5:
                return {"user_id": "session_user", "session_id": session_id}

            return None

        except Exception as e:
            self._logger.error(f"Session authentication error: {e}")
            return None


__all__ = ["AuthenticationMiddleware", "PathMatcher"]
