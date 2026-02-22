"""Test suite for EndpointDiscoveryService."""

from unittest.mock import MagicMock

import pytest

from jvspatial.api.services.discovery import EndpointDiscoveryService


class TestEndpointDiscoveryService:
    """Test EndpointDiscoveryService functionality."""

    def setup_method(self):
        """Set up test environment."""
        from jvspatial.api.server import Server

        server = Server()
        self.service = EndpointDiscoveryService(server)

    def test_discovery_service_initialization(self):
        """Test discovery service initialization."""
        assert self.service is not None

    def test_discover_packages_no_patterns(self):
        """Test that discovery returns 0 when no patterns configured."""
        # No patterns = no discovery (decorator-based registration only)
        count = self.service.discover_and_register()
        assert count == 0

    def test_discover_packages_with_patterns(self):
        """Test explicit pattern-based discovery."""
        # Enable discovery with explicit patterns
        self.service.enable(patterns=["tests.api.test_components"])
        count = self.service.discover_and_register()
        assert isinstance(count, int)
        assert count >= 0

    def test_discover_packages_invalid_pattern(self):
        """Test discovery with invalid module pattern."""
        # Enable discovery with invalid pattern
        self.service.enable(patterns=["nonexistent.module.that.does.not.exist"])
        count = self.service.discover_and_register()
        # Should handle ImportError gracefully and return 0
        assert count == 0

    def test_discover_modules(self):
        """Test module discovery."""
        # Test discover_in_module for a specific module
        # Use importlib to handle potential import issues
        import importlib
        import sys

        try:
            # Try to import the module
            module = importlib.import_module("tests.api.test_components")
            count = self.service.discover_in_module(module)
            assert isinstance(count, int)
            assert count >= 0
        except ImportError:
            # If module can't be imported, skip the test
            pytest.skip("Module tests.api.test_components not available")

    def test_enable_with_patterns(self):
        """Test enabling discovery with patterns."""
        self.service.enable(patterns=["myapp.routes", "myapp.api"])
        assert self.service.enabled is True
        assert len(self.service._patterns) == 2
        assert "myapp.routes" in self.service._patterns
        assert "myapp.api" in self.service._patterns

    def test_enable_without_patterns(self):
        """Test enabling discovery without patterns (decorator-based only)."""
        self.service.enable(enabled=True, patterns=None)
        assert self.service.enabled is True
        # Patterns should remain empty (decorator-based registration)
        assert len(self.service._patterns) == 0
