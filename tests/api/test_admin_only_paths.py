"""Tests for admin-only API path detection (status, logs, graph)."""

import pytest

from jvspatial.api.components.endpoint_auth_resolver import (
    path_requires_admin_only_role,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/graph", True),
        ("/api/graph/expand", True),
        ("/api/logs", True),
        ("/api/logs/export", True),
        ("/api/status", True),
        ("/api/status/detail", True),
        ("/api/health", False),
        ("/api/auth/login", False),
        ("/api/users", False),
        ("/api/graphics", False),
    ],
)
def test_path_requires_admin_only_role_default_prefix(path, expected):
    assert path_requires_admin_only_role(path) is expected
