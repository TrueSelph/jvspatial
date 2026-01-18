"""Optimized authentication middleware for jvspatial API.

This module provides streamlined authentication middleware with pre-compiled patterns
for optimal performance, following the new standard implementation approach.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Pattern

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
    """Authentication middleware with multi-method support.

    This middleware attempts authentication in the following order:
    1. JWT Bearer token (Authorization: Bearer <token>)
    2. API key (X-API-Key or custom header configured in api_key_header)
    3. Session cookie (if configured)

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
        # #region agent log
        import json
        import time

        with open(
            "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A",
                        "location": "auth_middleware.py:135",
                        "message": "Request received",
                        "data": {
                            "path": request.url.path,
                            "method": request.method,
                            "has_auth_header": "authorization" in request.headers,
                            "has_api_key": "x-api-key"  # pragma: allowlist secret
                            in request.headers,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
        # #endregion

        # Always allow OPTIONS requests (CORS preflight) to pass through
        # CORS middleware will handle these requests
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check if path is exempt from authentication
        is_exempt = self.path_matcher.is_exempt(request.url.path)
        # #region agent log
        with open(
            "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "B",
                        "location": "auth_middleware.py:152",
                        "message": "Path exemption check",
                        "data": {"path": request.url.path, "is_exempt": is_exempt},
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
        # #endregion
        if is_exempt:
            return await call_next(request)

        # Check if this endpoint requires authentication
        auth_required = self._endpoint_requires_auth(request)
        has_fastapi_auth = self._endpoint_has_fastapi_auth(request)

        # #region agent log
        with open(
            "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "C",
                        "location": "auth_middleware.py:158",
                        "message": "Auth requirement check",
                        "data": {
                            "path": request.url.path,
                            "auth_required": auth_required,
                            "has_fastapi_auth": has_fastapi_auth,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
        # #endregion

        if not auth_required:
            # #region agent log
            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "D",
                            "location": "auth_middleware.py:164",
                            "message": "Allowing through - no auth required",
                            "data": {"path": request.url.path},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion
            return await call_next(request)

        # If the route has FastAPI auth dependencies (like Depends(security)),
        # let FastAPI handle authentication via its dependency injection system
        # The middleware should not interfere with FastAPI's auth dependencies
        if has_fastapi_auth:
            # #region agent log
            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "E",
                            "location": "auth_middleware.py:175",
                            "message": "Allowing through - FastAPI auth",
                            "data": {"path": request.url.path},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion
            self._logger.debug(
                f"Route {request.url.path} has FastAPI auth dependencies, allowing through"
            )
            return await call_next(request)

        # Streamlined authentication logic for routes without FastAPI auth dependencies
        user = await self._authenticate_request(request)
        # #region agent log
        with open(
            "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
        ) as f:
            # Extract user_id safely - handle both UserResponse objects and dicts
            user_id = None
            if user:
                if isinstance(user, dict):
                    user_id = user.get("user_id")
                elif hasattr(user, "id"):
                    user_id = user.id
                elif hasattr(user, "user_id"):
                    user_id = user.user_id
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "F",
                        "location": "auth_middleware.py:189",
                        "message": "Authentication result",
                        "data": {
                            "path": request.url.path,
                            "user_authenticated": user is not None,
                            "user_id": user_id,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
        # #endregion
        if not user:
            # #region agent log
            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "G",
                            "location": "auth_middleware.py:195",
                            "message": "Returning 401 - no user",
                            "data": {"path": request.url.path},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion
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
        # #region agent log
        with open(
            "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
        ) as f:
            # Extract user_id safely - handle both UserResponse objects and dicts
            user_id = None
            if user:
                if isinstance(user, dict):
                    user_id = user.get("user_id")
                elif hasattr(user, "id"):
                    user_id = user.id
                elif hasattr(user, "user_id"):
                    user_id = user.user_id
            f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "H",
                        "location": "auth_middleware.py:210",
                        "message": "Allowing through - authenticated",
                        "data": {"path": request.url.path, "user_id": user_id},
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
        # #endregion
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

    def _safe_serialize_endpoint_config(
        self, endpoint_config: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Safely serialize endpoint config for logging, excluding non-serializable objects.

        Args:
            endpoint_config: The endpoint config dictionary

        Returns:
            A dictionary with only serializable values, or None if config is None
        """
        if endpoint_config is None:
            return None

        # Only include keys that are JSON-serializable
        # Skip 'response' key which may contain ResponseSchema objects
        safe_config = {}
        for key in ["auth_required", "permissions", "roles", "tags"]:
            if key in endpoint_config:
                safe_config[key] = endpoint_config[key]

        return safe_config if safe_config else None

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
            # #region agent log
            import json
            import time

            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "I",
                            "location": "auth_middleware.py:230",
                            "message": "_endpoint_requires_auth called",
                            "data": {"path": request.url.path},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion

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
                # Try both with and without /api prefix for flexibility
                paths_to_check = [
                    normalized_path,
                    request_path,
                    (
                        request_path[len(api_prefix) :]
                        if api_prefix and request_path.startswith(api_prefix)
                        else None
                    ),
                ]
                paths_to_check = [p for p in paths_to_check if p is not None]

                if func_path in paths_to_check or any(
                    self._path_matches(func_path, p) for p in paths_to_check
                ):
                    endpoint_config = getattr(func, "_jvspatial_endpoint_config", None)
                    if endpoint_config is None:
                        # SECURITY: Endpoint found but no config - deny access
                        self._logger.warning(
                            f"Endpoint found in registry but missing config: {normalized_path} - DENYING access"
                        )
                        return True

                    auth_required = endpoint_config.get("auth_required", False)
                    # #region agent log
                    with open(
                        "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                        "a",
                    ) as f:
                        f.write(
                            json.dumps(
                                {
                                    "sessionId": "debug-session",
                                    "runId": "run1",
                                    "hypothesisId": "J",
                                    "location": "auth_middleware.py:282",
                                    "message": "Found in function registry",
                                    "data": {
                                        "path": normalized_path,
                                        "auth_required": auth_required,
                                        "endpoint_config": self._safe_serialize_endpoint_config(
                                            endpoint_config
                                        ),
                                    },
                                    "timestamp": int(time.time() * 1000),
                                }
                            )
                            + "\n"
                        )
                    # #endregion
                    self._logger.debug(
                        f"Function endpoint {normalized_path}: auth_required={auth_required}"
                    )
                    return auth_required

            # Check walker endpoints by accessing internal registry directly
            for walker_class, endpoint_info in registry._walker_registry.items():
                walker_path = endpoint_info.path

                # Match using normalized path (for paths registered without prefix)
                # Also check original request path for backward compatibility
                # Try both with and without /api prefix for flexibility
                paths_to_check = [
                    normalized_path,
                    request_path,
                    (
                        request_path[len(api_prefix) :]
                        if api_prefix and request_path.startswith(api_prefix)
                        else None
                    ),
                ]
                paths_to_check = [p for p in paths_to_check if p is not None]

                if walker_path in paths_to_check or any(
                    self._path_matches(walker_path, p) for p in paths_to_check
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
                    # #region agent log
                    with open(
                        "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                        "a",
                    ) as f:
                        f.write(
                            json.dumps(
                                {
                                    "sessionId": "debug-session",
                                    "runId": "run1",
                                    "hypothesisId": "K",
                                    "location": "auth_middleware.py:309",
                                    "message": "Found in walker registry",
                                    "data": {
                                        "path": normalized_path,
                                        "auth_required": auth_required,
                                        "endpoint_config": self._safe_serialize_endpoint_config(
                                            endpoint_config
                                        ),
                                    },
                                    "timestamp": int(time.time() * 1000),
                                }
                            )
                            + "\n"
                        )
                    # #endregion
                    self._logger.debug(
                        f"Walker endpoint {normalized_path}: auth_required={auth_required}"
                    )
                    return auth_required

            # Endpoint not in registry - check if it's a valid FastAPI route
            # Router endpoints (like auth endpoints) may not be in the registry
            # but are still valid FastAPI routes that should be handled
            # SECURITY: Only allow routes through without auth if they're from registered routers
            # Direct app routes not in registry should still require auth
            if hasattr(server, "app") and server.app:
                from fastapi.routing import APIRoute

                # Check if this is a valid FastAPI route
                for route in server.app.routes:
                    if isinstance(route, APIRoute):
                        # Check if path matches (accounting for path parameters)
                        route_path = route.path
                        if (
                            route_path in (request_path, normalized_path)
                            or self._path_matches(route_path, request_path)
                            or self._path_matches(route_path, normalized_path)
                        ):
                            # Check if method matches (if request has method attribute)
                            request_method = getattr(request, "method", None)
                            if (
                                request_method is None
                                or request_method in route.methods
                            ):
                                # #region agent log
                                with open(
                                    "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                    "a",
                                ) as f:
                                    f.write(
                                        json.dumps(
                                            {
                                                "sessionId": "debug-session",
                                                "runId": "run1",
                                                "hypothesisId": "M",
                                                "location": "auth_middleware.py:345",
                                                "message": "FastAPI route matched",
                                                "data": {
                                                    "request_path": request_path,
                                                    "route_path": route_path,
                                                    "normalized_path": normalized_path,
                                                    "has_dependencies": bool(
                                                        route.dependencies
                                                    ),
                                                    "dependencies_count": (
                                                        len(route.dependencies)
                                                        if route.dependencies
                                                        else 0
                                                    ),
                                                },
                                                "timestamp": int(time.time() * 1000),
                                            }
                                        )
                                        + "\n"
                                    )
                                # #endregion

                                # Check if route has auth dependencies
                                if route.dependencies:
                                    # Check for security/authentication dependencies
                                    for dep in route.dependencies:
                                        dep_str = str(dep).lower()
                                        # #region agent log
                                        with open(
                                            "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                            "a",
                                        ) as f:
                                            f.write(
                                                json.dumps(
                                                    {
                                                        "sessionId": "debug-session",
                                                        "runId": "run1",
                                                        "hypothesisId": "N",
                                                        "location": "auth_middleware.py:360",
                                                        "message": "Checking dependency",
                                                        "data": {
                                                            "dep_str": dep_str,
                                                            "has_security": "security"
                                                            in dep_str,
                                                            "has_bearer": "bearer"
                                                            in dep_str,
                                                            "has_auth": "auth"
                                                            in dep_str,
                                                        },
                                                        "timestamp": int(
                                                            time.time() * 1000
                                                        ),
                                                    }
                                                )
                                                + "\n"
                                            )
                                        # #endregion
                                        if (
                                            "security" in dep_str
                                            or "bearer" in dep_str
                                            or "auth" in dep_str
                                        ):
                                            # #region agent log
                                            with open(
                                                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                                "a",
                                            ) as f:
                                                f.write(
                                                    json.dumps(
                                                        {
                                                            "sessionId": "debug-session",
                                                            "runId": "run1",
                                                            "hypothesisId": "O",
                                                            "location": "auth_middleware.py:375",
                                                            "message": "Found FastAPI auth dependency",
                                                            "data": {
                                                                "path": request_path
                                                            },
                                                            "timestamp": int(
                                                                time.time() * 1000
                                                            ),
                                                        }
                                                    )
                                                    + "\n"
                                                )
                                            # #endregion
                                            self._logger.debug(
                                                f"Router endpoint {request_path} has FastAPI auth dependency"
                                            )
                                            # Route has FastAPI auth - require auth but let FastAPI handle it
                                            return True

                                # Route exists and method matches
                                # For /auth/ endpoints (except exempt ones), require auth
                                if (
                                    "/auth/" in request_path
                                    and request_path
                                    not in self.auth_config.exempt_paths
                                ):
                                    # #region agent log
                                    with open(
                                        "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                        "a",
                                    ) as f:
                                        f.write(
                                            json.dumps(
                                                {
                                                    "sessionId": "debug-session",
                                                    "runId": "run1",
                                                    "hypothesisId": "P",
                                                    "location": "auth_middleware.py:390",
                                                    "message": "Auth path - requiring auth",
                                                    "data": {"path": request_path},
                                                    "timestamp": int(
                                                        time.time() * 1000
                                                    ),
                                                }
                                            )
                                            + "\n"
                                        )
                                    # #endregion
                                    # Auth endpoints require authentication unless explicitly exempt
                                    self._logger.debug(
                                        f"Auth router endpoint {request_path} requires auth"
                                    )
                                    return True

                                # Check endpoint's _jvspatial_endpoint_config if available
                                # This allows add_route() to set auth=False even if not in registry
                                endpoint_func = route.endpoint
                                if hasattr(endpoint_func, "_jvspatial_endpoint_config"):
                                    endpoint_config = endpoint_func._jvspatial_endpoint_config  # type: ignore[attr-defined]
                                    if "auth_required" in endpoint_config:
                                        auth_required = endpoint_config.get(
                                            "auth_required", True
                                        )
                                        # #region agent log
                                        with open(
                                            "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                            "a",
                                        ) as f:
                                            f.write(
                                                json.dumps(
                                                    {
                                                        "sessionId": "debug-session",
                                                        "runId": "run1",
                                                        "hypothesisId": "Q",
                                                        "location": "auth_middleware.py:405",
                                                        "message": "FastAPI route with endpoint config",
                                                        "data": {
                                                            "path": request_path,
                                                            "auth_required": auth_required,
                                                            "endpoint_config": self._safe_serialize_endpoint_config(
                                                                endpoint_config
                                                            ),
                                                        },
                                                        "timestamp": int(
                                                            time.time() * 1000
                                                        ),
                                                    }
                                                )
                                                + "\n"
                                            )
                                        # #endregion
                                        self._logger.debug(
                                            f"FastAPI route {request_path} has endpoint config: auth_required={auth_required}"
                                        )
                                        return auth_required

                                # SECURITY: For routes not in registry and not under /auth/,
                                # require authentication by default (deny by default)
                                # Only routes explicitly registered with auth=False should be allowed
                                # Unregistered route - require auth by default
                                # #region agent log
                                with open(
                                    "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                    "a",
                                ) as f:
                                    f.write(
                                        json.dumps(
                                            {
                                                "sessionId": "debug-session",
                                                "runId": "run1",
                                                "hypothesisId": "Q",
                                                "location": "auth_middleware.py:405",
                                                "message": "Unregistered route - requiring auth",
                                                "data": {"path": request_path},
                                                "timestamp": int(time.time() * 1000),
                                            }
                                        )
                                        + "\n"
                                    )
                                # #endregion
                                self._logger.debug(
                                    f"Unregistered route {request_path} found, requiring auth (deny by default)"
                                )
                                return True

            # SECURITY: Endpoint not found in registry or FastAPI routes - DENY by default
            # This is a critical security decision: we require authentication for any
            # endpoint that isn't explicitly registered, preventing bypass via path manipulation
            # #region agent log
            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "L",
                            "location": "auth_middleware.py:369",
                            "message": "Not found in registry or routes - requiring auth",
                            "data": {
                                "normalized_path": normalized_path,
                                "request_path": request_path,
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion
            self._logger.debug(
                f"Endpoint not found in registry or routes: {normalized_path} (original: {request_path}) - DENYING access"
            )
            return True  # SECURITY: Deny by default

        except Exception as e:
            # SECURITY: On any error, deny access to prevent bypasses
            self._logger.error(
                f"Error checking endpoint auth requirements for {request.url.path}: {e} - DENYING access",
                exc_info=True,
            )
            return True  # SECURITY: Deny on error

    def _endpoint_has_fastapi_auth(self, request: Request) -> bool:
        """Check if endpoint has FastAPI authentication dependencies.

        This method checks if a route has FastAPI auth dependencies (like Depends(security))
        that should be handled by FastAPI's dependency injection system rather than the middleware.

        Args:
            request: Incoming request

        Returns:
            True if the route has FastAPI auth dependencies, False otherwise
        """
        try:
            # #region agent log
            import json
            import time

            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "R",
                            "location": "auth_middleware.py:430",
                            "message": "_endpoint_has_fastapi_auth called",
                            "data": {"path": request.url.path},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion

            server = self._server
            if not server or not hasattr(server, "app") or not server.app:
                return False

            from fastapi.routing import APIRoute

            request_path = request.url.path
            api_prefix = APIRoutes.PREFIX
            normalized_path = request_path

            if api_prefix and request_path.startswith(api_prefix):
                normalized_path = request_path[len(api_prefix) :]
                if not normalized_path:
                    normalized_path = "/"

            # Check FastAPI routes for auth dependencies
            for route in server.app.routes:
                if isinstance(route, APIRoute):
                    route_path = route.path
                    if (
                        route_path in (request_path, normalized_path)
                        or self._path_matches(route_path, request_path)
                        or self._path_matches(route_path, normalized_path)
                    ):
                        request_method = getattr(request, "method", None)
                        if (
                            request_method is None or request_method in route.methods
                        ) and route.dependencies:
                            # Check for security/authentication dependencies
                            for dep in route.dependencies:
                                dep_str = str(dep).lower()
                                # #region agent log
                                with open(
                                    "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                    "a",
                                ) as f:
                                    f.write(
                                        json.dumps(
                                            {
                                                "sessionId": "debug-session",
                                                "runId": "run1",
                                                "hypothesisId": "S",
                                                "location": "auth_middleware.py:460",
                                                "message": "Checking FastAPI dependency",
                                                "data": {
                                                    "path": request_path,
                                                    "dep_str": dep_str,
                                                    "has_security": "security"
                                                    in dep_str,
                                                    "has_bearer": "bearer" in dep_str,
                                                    "has_auth": "auth" in dep_str,
                                                },
                                                "timestamp": int(time.time() * 1000),
                                            }
                                        )
                                        + "\n"
                                    )
                                # #endregion
                                if (
                                    "security" in dep_str
                                    or "bearer" in dep_str
                                    or "auth" in dep_str
                                ):
                                    # #region agent log
                                    with open(
                                        "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log",
                                        "a",
                                    ) as f:
                                        f.write(
                                            json.dumps(
                                                {
                                                    "sessionId": "debug-session",
                                                    "runId": "run1",
                                                    "hypothesisId": "T",
                                                    "location": "auth_middleware.py:475",
                                                    "message": "Found FastAPI auth - returning True",
                                                    "data": {"path": request_path},
                                                    "timestamp": int(
                                                        time.time() * 1000
                                                    ),
                                                }
                                            )
                                            + "\n"
                                        )
                                    # #endregion
                                    return True
            # #region agent log
            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "U",
                            "location": "auth_middleware.py:485",
                            "message": "No FastAPI auth found",
                            "data": {"path": request_path},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion
            return False
        except Exception as e:
            # #region agent log
            import json
            import time

            with open(
                "/Users/eldonmarks/Briefcase/dev/jv/jvspatial/.cursor/debug.log", "a"
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "V",
                            "location": "auth_middleware.py:495",
                            "message": "Exception in _endpoint_has_fastapi_auth",
                            "data": {"path": request.url.path, "error": str(e)},
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
            # #endregion
            return False

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
