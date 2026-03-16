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


__all__ = ["normalize_endpoint_path"]
