"""Tests for endpoint path normalization and routing.

Verifies that path normalization works correctly for registration,
routing, and auth resolution. Covers both prefixed and unprefixed paths.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.config import ServerConfig
from jvspatial.api.decorators.route import endpoint
from jvspatial.api.server import Server
from jvspatial.api.utils.path_utils import normalize_endpoint_path


class TestNormalizeEndpointPath:
    """Test path normalization utility."""

    def test_adds_leading_slash(self):
        assert normalize_endpoint_path("tracks") == "/tracks"

    def test_strips_api_prefix(self):
        assert normalize_endpoint_path("/api/tracks") == "/tracks"

    def test_collapses_multiple_slashes(self):
        assert normalize_endpoint_path("//tracks") == "/tracks"
        assert normalize_endpoint_path("/api//tracks") == "/tracks"

    def test_preserves_path_params(self):
        assert normalize_endpoint_path("/tracks/{track_id}") == "/tracks/{track_id}"
        assert normalize_endpoint_path("/api/tracks/{track_id}") == "/tracks/{track_id}"

    def test_empty_returns_root(self):
        assert normalize_endpoint_path("") == "/"

    def test_none_returns_root(self):
        assert normalize_endpoint_path(None) == "/"


class TestEndpointPathRouting:
    """Test that endpoint paths route correctly after normalization."""

    @pytest.fixture
    def server_config(self):
        db_path = os.path.join(tempfile.mkdtemp(), "test_path_routing_db")
        return ServerConfig(
            database=dict(db_type="json", db_path=db_path),
        )

    @pytest.fixture
    def server(self, server_config):
        return Server(config=server_config)

    def test_endpoint_without_prefix_resolves_to_api_path(self, server):
        """@endpoint("/tracks") -> request to /api/tracks succeeds."""

        @endpoint("/tracks", methods=["GET"], auth=False)
        async def get_tracks():
            return {"tracks": []}

        server.app = server._create_app_instance()
        client = TestClient(server.app)

        response = client.get("/api/tracks")
        assert response.status_code == 200
        assert response.json() == {"tracks": []}

    def test_endpoint_with_api_prefix_normalizes_and_resolves(self, server):
        """@endpoint("/api/tracks") -> request to /api/tracks succeeds (no double prefix)."""

        @endpoint("/api/tracks", methods=["GET"], auth=False)
        async def get_tracks_legacy():
            return {"tracks": []}

        server.app = server._create_app_instance()
        client = TestClient(server.app)

        response = client.get("/api/tracks")
        assert response.status_code == 200
        assert response.json() == {"tracks": []}

    def test_path_with_params_matches(self, server):
        """Path /tracks/{track_id} matches /api/tracks/123."""

        @endpoint("/tracks/{track_id}", methods=["GET"], auth=False)
        async def get_track(track_id: str):
            return {"track_id": track_id}

        server.app = server._create_app_instance()
        client = TestClient(server.app)

        response = client.get("/api/tracks/123")
        assert response.status_code == 200
        assert response.json() == {"track_id": "123"}


class TestAuthExemptPaths:
    """Test auth exempt paths with and without prefix."""

    @pytest.fixture
    def server_config(self):
        db_path = os.path.join(tempfile.mkdtemp(), "test_auth_exempt_db")
        return ServerConfig(
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret",
                jwt_algorithm="HS256",
                jwt_expire_minutes=30,
            ),
            database=dict(db_type="json", db_path=db_path),
        )

    @pytest.fixture
    def server(self, server_config):
        return Server(config=server_config)

    def test_public_endpoint_without_prefix(self, server):
        """Auth exempt path /public works at /api/public."""

        @endpoint("/public", methods=["GET"], auth=False)
        async def public():
            return {"status": "ok"}

        server.app = server._create_app_instance()
        client = TestClient(server.app)

        response = client.get("/api/public")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_public_endpoint_with_api_prefix_normalized(self, server):
        """Auth exempt path /api/public normalizes and works at /api/public."""

        @endpoint("/api/public", methods=["GET"], auth=False)
        async def public_legacy():
            return {"status": "ok"}

        server.app = server._create_app_instance()
        client = TestClient(server.app)

        response = client.get("/api/public")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
