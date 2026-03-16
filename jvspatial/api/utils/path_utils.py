"""Path utilities for endpoint registration and routing."""

import re

from jvspatial.api.constants import APIRoutes


def normalize_endpoint_path(path: str) -> str:
    """Normalize an endpoint path for consistent registration and lookup.

    - Ensures leading slash: "tracks" -> "/tracks"
    - Strips API prefix when present: "/api/tracks" -> "/tracks"
    - Collapses multiple slashes: "//tracks" -> "/tracks"
    - Ensures path is suitable for router (prefix is applied at mount time)

    Args:
        path: Raw path from @endpoint decorator or config

    Returns:
        Normalized path without API prefix, with leading slash
    """
    if not path or not isinstance(path, str):
        return "/"

    # Collapse multiple slashes and strip whitespace
    normalized = re.sub(r"/+", "/", path.strip())

    # Ensure leading slash
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    # Strip API prefix if present (router adds it at mount time)
    prefix = APIRoutes.PREFIX or ""
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    if prefix and prefix != "/" and normalized.startswith(prefix):
        suffix = normalized[len(prefix) :].lstrip("/") or ""
        normalized = "/" + suffix if suffix else "/"

    # Collapse any double slashes from stripping
    normalized = re.sub(r"/+", "/", normalized)

    # Ensure we have at least "/"
    return normalized if normalized else "/"


def path_matches(pattern: str, path: str) -> bool:
    """Check if a request path matches a route pattern with path parameters.

    Supports FastAPI-style path parameters like {param} or {resource_id}.

    Args:
        pattern: Route pattern (e.g. /integrations/{service}/webhook/{id})
        path: Actual request path (e.g. /integrations/foo/webhook/abc123)

    Returns:
        True if path matches the pattern
    """
    if not pattern or not path:
        return False
    escaped = re.escape(pattern)
    regex = re.sub(r"\\\{(\w+)\\\}", r"[^/]+", escaped)
    regex = re.sub(r"\{(\w+)\}", r"[^/]+", regex)
    return bool(re.match(f"^{regex}$", path))


def normalize_request_path(request_path: str) -> str:
    """Normalize a request path for registry lookup (strip API prefix).

    Registry stores paths without API prefix. Use this to convert
    request.url.path to the form used in the registry.

    Args:
        request_path: Raw request path (e.g. /api/integrations/foo/webhook/abc123)

    Returns:
        Normalized path (e.g. /integrations/foo/webhook/abc123)
    """
    return normalize_endpoint_path(request_path)


__all__ = ["normalize_endpoint_path", "path_matches", "normalize_request_path"]
