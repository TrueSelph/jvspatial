"""Path matching for authentication exemptions.

This module provides optimized path matching with pre-compiled patterns
for authentication exemption checks.
"""

import logging
import re
from typing import List, Pattern

from jvspatial.api.constants import APIRoutes

# Built-in auth paths always exempt (login, register, refresh, signup, password reset)
_BUILTIN_AUTH_EXEMPT = [
    "/auth/register",
    "/auth/login",
    "/auth/refresh",
    "/auth/logout",
    "/auth/signup",
    "/auth/forgot-password",
    "/auth/reset-password",
]


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
        merged = list(exempt_paths) if exempt_paths else []
        for p in _BUILTIN_AUTH_EXEMPT:
            if p not in merged:
                merged.append(p)
        self.exempt_paths = self._expand_api_variants(merged)
        self._compiled_patterns = self._compile_exempt_patterns()

    def _expand_api_variants(self, exempt_paths: List[str]) -> List[str]:
        """Add API-prefixed and un-prefixed variants, honoring configurable prefix.

        Handles dynamically set APIRoutes.PREFIX (default "/api") so auth
        exemptions remain correct even when the API is mounted under a custom
        prefix or at root.
        """
        prefix = APIRoutes.PREFIX or ""
        if prefix and not prefix.startswith("/"):
            prefix = f"/{prefix}"
        if prefix.endswith("/") and prefix != "/":
            prefix = prefix.rstrip("/")

        expanded: List[str] = []
        for path in exempt_paths:
            if path is None or not isinstance(path, str):
                continue
            normalized = path if path.startswith("/") else f"/{path}"
            expanded.append(normalized)
            if prefix and prefix != "/" and not normalized.startswith(prefix):
                expanded.append(f"{prefix}{normalized}")
            if prefix and prefix != "/" and normalized.startswith(prefix):
                without_prefix = normalized[len(prefix) :] or "/"
                expanded.append(without_prefix)

        seen: set[str] = set()
        deduped: List[str] = []
        for p in expanded:
            if p not in seen:
                deduped.append(p)
                seen.add(p)
        return deduped

    def _compile_exempt_patterns(self) -> List[Pattern]:
        """Pre-compile patterns for optimal performance."""
        compiled_patterns = []
        for pattern in self.exempt_paths:
            regex_pattern = "^" + pattern.replace("*", ".*") + "$"
            try:
                compiled_patterns.append(re.compile(regex_pattern))
            except re.error as e:
                logging.getLogger(__name__).warning(f"Invalid pattern '{pattern}': {e}")
        return compiled_patterns

    def is_exempt(self, path: str) -> bool:
        """Check if a path is exempt from authentication."""
        return any(p.match(path) for p in self._compiled_patterns)


__all__ = ["PathMatcher"]
