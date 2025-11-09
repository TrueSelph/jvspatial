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

from jvspatial.config import Config


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
        self.exempt_paths = exempt_paths
        self._compiled_patterns = self._compile_exempt_patterns()

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

    def __init__(self, app, auth_config: Config, server=None):
        """Initialize the authentication middleware.

        Args:
            app: FastAPI application instance
            auth_config: Authentication configuration
            server: Optional server instance (for test compatibility)
        """
        super().__init__(app)
        self.auth_config = auth_config
        self.path_matcher = PathMatcher(auth_config.exempt_paths)
        self._logger = logging.getLogger(__name__)
        self._server = server  # Store server reference for test compatibility

    async def dispatch(self, request: Request, call_next):
        """Optimized request processing with streamlined authentication logic.

        Args:
            request: Incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response from next handler or authentication error response
        """
        # Check if path is exempt from authentication
        if self.path_matcher.is_exempt(request.url.path):
            return await call_next(request)

        # Check if this endpoint requires authentication
        if not self._endpoint_requires_auth(request):
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

    def _endpoint_requires_auth(self, request: Request) -> bool:
        """Check if the current endpoint requires authentication.

        Args:
            request: Incoming request

        Returns:
            True if endpoint requires authentication, False otherwise
        """
        try:
            # Get the current server from context
            from jvspatial.api.context import get_current_server

            server = get_current_server()

            if not server:
                return False

            # Check if any endpoints in the registry require auth for this path
            registry = server._endpoint_registry

            # Check function endpoints
            for func_info in registry.list_functions():
                # Handle both dict and other formats
                if isinstance(func_info, dict):
                    func_path = func_info.get("path")
                    func = func_info.get("func")
                else:
                    # If func_info is not a dict, skip or handle differently
                    continue

                if func_path == request.url.path:
                    endpoint_config = getattr(func, "_jvspatial_endpoint_config", None)
                    if endpoint_config and endpoint_config.get("auth_required"):
                        return True

            # Check walker endpoints
            for walker_info in registry.list_walkers():
                # Handle both dict and other formats
                if isinstance(walker_info, dict):
                    walker_path = walker_info.get("path")
                    walker_class = walker_info.get("walker_class")
                else:
                    # If walker_info is not a dict, skip or handle differently
                    continue

                if walker_path == request.url.path:
                    endpoint_config = getattr(
                        walker_class, "_jvspatial_endpoint_config", None
                    )
                    if endpoint_config and endpoint_config.get("auth_required"):
                        return True

            # Check manually registered endpoints by inspecting the FastAPI app routes
            # This is needed because manually registered endpoints bypass the registry
            try:
                app = server.get_app()
                for route in app.routes:
                    if (
                        hasattr(route, "path")
                        and route.path == request.url.path
                        and hasattr(route, "endpoint")
                    ):
                        endpoint_config = getattr(
                            route.endpoint, "_jvspatial_endpoint_config", None
                        )
                        if endpoint_config and endpoint_config.get("auth_required"):
                            return True
            except Exception as e:
                self._logger.debug(f"Could not check FastAPI routes: {e}")

            # Fallback: Apply auth to all /api/* endpoints except exempt ones
            # This ensures manually registered endpoints are protected
            if request.url.path.startswith("/api/"):
                return True

            return False

        except Exception as e:
            self._logger.warning(f"Error checking endpoint auth requirements: {e}")
            return False

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
            # Try to get server from stored reference first (for test compatibility)
            # Then fall back to context variable
            server = self._server
            if not server:
                from jvspatial.api.context import get_current_server

                server = get_current_server()

            if not server:
                return None

            # Initialize authentication service
            from jvspatial.api.auth.service import AuthenticationService

            auth_service = AuthenticationService(server._graph_context)

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
            # Placeholder API key authentication implementation
            api_key = request.headers.get("x-api-key", "")
            if not api_key:
                return None

            # Simple API key validation (replace with actual verification)
            if api_key and len(api_key) > 5:
                return {"user_id": "api_user", "api_key": api_key}

            return None

        except Exception as e:
            self._logger.error(f"API key authentication error: {e}")
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
