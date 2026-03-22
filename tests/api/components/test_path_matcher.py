"""PathMatcher tests for auth exemption rules."""

from jvspatial.api.components.path_matcher import PathMatcher


def test_deferred_invoke_exempt_even_when_omitted_from_config():
    """LWA self-invoke cannot send JWT; /_internal/deferred must stay exempt."""
    pm = PathMatcher(["/health"])
    assert pm.is_exempt("/api/_internal/deferred")


def test_builtin_auth_paths_still_merged():
    pm = PathMatcher([])
    assert pm.is_exempt("/api/auth/login")
