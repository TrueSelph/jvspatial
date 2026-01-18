"""Tests for AuthConfigurator component."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter

from jvspatial.api.components.auth_configurator import AuthConfigurator
from jvspatial.api.config import ServerConfig


class TestAuthConfigurator:
    """Test AuthConfigurator functionality."""

    @pytest.fixture
    def config(self):
        """Create test server config with auth enabled."""
        return ServerConfig(
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret",
                jwt_algorithm="HS256",
                jwt_expire_minutes=30,
                api_key_auth_enabled=True,
                api_key_prefix="sk_test_",
            )
        )

    @pytest.fixture
    def configurator(self, config):
        """Create AuthConfigurator instance."""
        return AuthConfigurator(config)

    def test_initialization(self, configurator, config):
        """Test configurator initialization."""
        assert configurator.config == config
        assert configurator._auth_config is None
        assert configurator._auth_router is None
        assert configurator._auth_endpoints_registered is False

    def test_configure_auth_disabled(self):
        """Test that configure returns None when auth is disabled."""
        config = ServerConfig()
        config.auth.auth_enabled = False
        configurator = AuthConfigurator(config)

        result = configurator.configure()
        assert result is None
        assert configurator._auth_endpoints_registered is False

    def test_configure_auth_enabled(self, configurator):
        """Test auth configuration when enabled."""
        result = configurator.configure()

        assert result is not None
        assert configurator._auth_config is not None
        assert configurator._auth_router is not None
        assert configurator._auth_endpoints_registered is True
        assert configurator.has_auth_endpoints is True

    def test_auth_config_properties(self, configurator):
        """Test auth config properties."""
        configurator.configure()

        assert configurator.auth_config is not None
        assert configurator.auth_router is not None
        assert isinstance(configurator.auth_router, APIRouter)
        assert configurator.has_auth_endpoints is True

    def test_auth_router_registration(self, configurator):
        """Test that auth router has correct routes."""
        configurator.configure()

        router = configurator.auth_router
        assert router is not None

        # Check that router has routes registered
        routes = [route.path for route in router.routes if hasattr(route, "path")]

        # Should have register, login, logout at minimum
        assert any("/register" in path for path in routes)
        assert any("/login" in path for path in routes)
        assert any("/logout" in path for path in routes)

    def test_api_key_endpoints_registration(self, configurator):
        """Test API key endpoints are registered when enabled."""
        configurator.configure()

        router = configurator.auth_router
        routes = [route.path for route in router.routes if hasattr(route, "path")]

        # Should have API key endpoints
        assert any("api-keys" in path for path in routes)

    def test_no_api_key_endpoints_when_disabled(self):
        """Test API key endpoints are not registered when disabled."""
        config = ServerConfig(
            auth=dict(
                auth_enabled=True,
                api_key_auth_enabled=False,
            )
        )
        configurator = AuthConfigurator(config)
        configurator.configure()

        router = configurator.auth_router
        assert router is not None
        routes = [route.path for route in router.routes if hasattr(route, "path")]

        # Should not have API key endpoints
        assert not any("api-keys" in path for path in routes)

    def test_configure_idempotent(self, configurator):
        """Test that configure can be called multiple times safely."""
        result1 = configurator.configure()
        result2 = configurator.configure()

        # Should return same config object (idempotent)
        assert result1 is result2
        # Should not register endpoints twice
        assert configurator._auth_endpoints_registered is True
