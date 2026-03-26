"""Endpoint auth resolution for authentication middleware.

Resolves whether an endpoint requires authentication by checking the
endpoint registry and FastAPI routes.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import Request

from jvspatial.api.constants import APIRoutes


def _route_paths_for_comparison(route_path: str) -> List[str]:
    """Build list of route path variants for matching (prefixed and normalized).

    FastAPI routes may have path with or without API prefix depending on mount.
    Registry stores paths without prefix. Returns both forms for robust matching.
    """
    paths = [route_path]
    prefix = APIRoutes.PREFIX or ""
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    if prefix and prefix != "/" and route_path.startswith(prefix):
        suffix = route_path[len(prefix) :].lstrip("/") or ""
        normalized = "/" + suffix if suffix else "/"
        if normalized not in paths:
            paths.append(normalized)
    return paths


def _path_matches(pattern: str, path: str) -> bool:
    """Check if a request path matches a route pattern with path parameters.

    Supports single-segment params ``{name}`` / ``{name:int}`` and Starlette/FastAPI
    ``{name:path}`` (slashes allowed in the capture).
    """
    if pattern == path:
        return True
    segments = [s for s in pattern.split("/") if s]
    if not segments:
        return path == "/"
    regex_parts: List[str] = []
    for seg in segments:
        if seg.startswith("{") and seg.endswith("}"):
            inner = seg[1:-1]
            if ":" in inner:
                _, conv = inner.split(":", 1)
                regex_parts.append("(.+)" if conv == "path" else r"[^/]+")
            else:
                regex_parts.append(r"[^/]+")
        else:
            regex_parts.append(re.escape(seg))
    regex = "^/" + "/".join(regex_parts) + "$"
    return bool(re.match(regex, path))


def _endpoint_info_matches_method(
    endpoint_info: Any, request_method: Optional[str]
) -> bool:
    """True if the request method is allowed for this registry entry (or method unknown)."""
    if not request_method:
        return True
    methods = getattr(endpoint_info, "methods", None) or []
    if not methods:
        return True
    upper = request_method.upper()
    return upper in {m.upper() for m in methods}


class EndpointAuthResolver:
    """Resolves auth requirements for endpoints from registry and FastAPI routes."""

    def __init__(
        self, server: Any, path_matcher: Any, logger: Optional[logging.Logger] = None
    ):
        self._server = server
        self._path_matcher = path_matcher
        self._logger = logger or logging.getLogger(__name__)

    def endpoint_requires_auth(self, request: Request) -> bool:
        """Check if endpoint requires authentication. Deny by default for security."""
        try:
            if not self._server:
                self._logger.error("_endpoint_requires_auth: No server - DENYING")
                return True

            registry = self._server._endpoint_registry
            request_path = request.url.path

            # Exempt paths must never require auth, regardless of registry state
            if self._path_matcher and self._path_matcher.is_exempt(request_path):
                return False

            api_prefix = APIRoutes.PREFIX
            normalized_path = request_path
            if api_prefix and request_path.startswith(api_prefix):
                normalized_path = request_path[len(api_prefix) :] or "/"

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

            req_method = getattr(request, "method", None)

            for func, endpoint_info in registry._function_registry.items():
                if not _endpoint_info_matches_method(endpoint_info, req_method):
                    continue
                func_path = endpoint_info.path
                if func_path in paths_to_check or any(
                    _path_matches(func_path, p) for p in paths_to_check
                ):
                    cfg = getattr(func, "_jvspatial_endpoint_config", None)
                    if cfg is None:
                        self._logger.warning(
                            f"Endpoint missing config: {normalized_path} - DENYING"
                        )
                        return True
                    return cfg.get("auth_required", False)

            for walker_class, endpoint_info in registry._walker_registry.items():
                if not _endpoint_info_matches_method(endpoint_info, req_method):
                    continue
                walker_path = endpoint_info.path
                if walker_path in paths_to_check or any(
                    _path_matches(walker_path, p) for p in paths_to_check
                ):
                    cfg = getattr(walker_class, "_jvspatial_endpoint_config", None)
                    if cfg is None:
                        self._logger.warning(
                            f"Walker missing config: {normalized_path} - DENYING"
                        )
                        return True
                    return cfg.get("auth_required", False)

            if hasattr(self._server, "app") and self._server.app:
                from fastapi.routing import APIRoute

                for route in self._server.app.routes:
                    if not isinstance(route, APIRoute):
                        continue
                    route_paths = _route_paths_for_comparison(route.path)
                    if not (
                        any(rp in (request_path, normalized_path) for rp in route_paths)
                        or any(
                            _path_matches(rp, request_path)
                            or _path_matches(rp, normalized_path)
                            for rp in route_paths
                        )
                    ):
                        continue
                    request_method = getattr(request, "method", None)
                    if (
                        request_method is not None
                        and request_method not in route.methods
                    ):
                        continue
                    if route.dependencies:
                        for dep in route.dependencies:
                            s = str(dep).lower()
                            if "security" in s or "bearer" in s or "auth" in s:
                                return True
                    if "/auth/" in request_path and not self._path_matcher.is_exempt(
                        request_path
                    ):
                        return True
                    endpoint_func = route.endpoint
                    if hasattr(endpoint_func, "_jvspatial_endpoint_config"):
                        cfg = endpoint_func._jvspatial_endpoint_config  # type: ignore[attr-defined]
                        if "auth_required" in cfg:
                            return cfg.get("auth_required", True)
                    # Before blindly denying, check if this route path is itself exempt
                    route_is_exempt = self._path_matcher and any(
                        self._path_matcher.is_exempt(rp) for rp in route_paths
                    )
                    if route_is_exempt:
                        return False
                    self._logger.debug(
                        "Unregistered route %s (method=%s) - requiring auth by default. "
                        "Ensure the endpoint is registered with @endpoint before the auth "
                        "middleware runs, or add to auth_exempt_paths if public.",
                        request_path,
                        getattr(request, "method", "?"),
                    )
                    return True

            self._logger.debug(
                "Endpoint not found in registry: %s (method=%s) - requiring auth by default. "
                "Check endpoint registration order or add to auth_exempt_paths if public.",
                normalized_path,
                getattr(request, "method", "?"),
            )
            return True
        except Exception as e:
            self._logger.error(
                "Error checking auth for %s: %s - requiring auth by default",
                request.url.path,
                e,
                exc_info=True,
            )
            return True

    def endpoint_has_fastapi_auth(self, request: Request) -> bool:
        """Check if route has FastAPI auth dependencies."""
        try:
            if (
                not self._server
                or not getattr(self._server, "app", None)
                or not self._server.app
            ):
                return False

            from fastapi.routing import APIRoute

            request_path = request.url.path
            api_prefix = APIRoutes.PREFIX
            normalized_path = request_path
            if api_prefix and request_path.startswith(api_prefix):
                normalized_path = request_path[len(api_prefix) :] or "/"

            for route in self._server.app.routes:
                if not isinstance(route, APIRoute):
                    continue
                route_paths = _route_paths_for_comparison(route.path)
                if not (
                    any(rp in (request_path, normalized_path) for rp in route_paths)
                    or any(
                        _path_matches(rp, request_path)
                        or _path_matches(rp, normalized_path)
                        for rp in route_paths
                    )
                ):
                    continue
                if (
                    getattr(request, "method", None)
                    and request.method not in route.methods
                ):
                    continue
                if route.dependencies:
                    for dep in route.dependencies:
                        s = str(dep).lower()
                        if "security" in s or "bearer" in s or "auth" in s:
                            return True
            return False
        except Exception:
            return False

    def get_endpoint_config(self, request: Request) -> Optional[Dict[str, Any]]:
        """Get endpoint config for the current request path."""
        try:
            if not self._server:
                return None

            registry = self._server._endpoint_registry
            request_path = request.url.path
            api_prefix = APIRoutes.PREFIX
            normalized_path = request_path
            if api_prefix and request_path.startswith(api_prefix):
                normalized_path = request_path[len(api_prefix) :] or "/"

            paths = [normalized_path, request_path]
            if api_prefix and request_path.startswith(api_prefix):
                p = request_path[len(api_prefix) :] or "/"
                if p not in paths:
                    paths.append(p)

            req_method = getattr(request, "method", None)

            for func, endpoint_info in registry._function_registry.items():
                if not _endpoint_info_matches_method(endpoint_info, req_method):
                    continue
                if endpoint_info.path in paths or any(
                    _path_matches(endpoint_info.path, x) for x in paths
                ):
                    return getattr(func, "_jvspatial_endpoint_config", None)

            for walker_class, endpoint_info in registry._walker_registry.items():
                if not _endpoint_info_matches_method(endpoint_info, req_method):
                    continue
                if endpoint_info.path in paths or any(
                    _path_matches(endpoint_info.path, x) for x in paths
                ):
                    return getattr(walker_class, "_jvspatial_endpoint_config", None)

            if hasattr(self._server, "app") and self._server.app:
                from fastapi.routing import APIRoute

                for route in self._server.app.routes:
                    if not isinstance(route, APIRoute):
                        continue
                    route_paths = _route_paths_for_comparison(route.path)
                    if not (
                        any(rp in (request_path, normalized_path) for rp in route_paths)
                        or any(
                            _path_matches(rp, request_path)
                            or _path_matches(rp, normalized_path)
                            for rp in route_paths
                        )
                    ):
                        continue
                    if req_method is not None and req_method not in route.methods:
                        continue
                    if hasattr(route.endpoint, "_jvspatial_endpoint_config"):
                        return route.endpoint._jvspatial_endpoint_config  # type: ignore[attr-defined]
            return None
        except Exception:
            return None


__all__ = ["EndpointAuthResolver"]
