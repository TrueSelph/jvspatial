"""Test suite for PackageDiscoveryService."""

from unittest.mock import MagicMock

import pytest

from jvspatial.api.services.discovery import PackageDiscoveryService


class TestPackageDiscoveryService:
    """Test PackageDiscoveryService functionality."""

    def setup_method(self):
        """Set up test environment."""
        from jvspatial.api.server import Server

        server = Server()
        self.service = PackageDiscoveryService(server)

    async def test_discovery_service_initialization(self):
        """Test discovery service initialization."""
        assert self.service is not None

    async def test_discover_packages(self):
        """Test package discovery."""
        count = self.service.discover_and_register()
        assert isinstance(count, int)

    async def test_discover_modules(self):
        """Test module discovery."""
        # The service doesn't have a discover_modules method, test discover_in_module instead
        import sys

        count = self.service.discover_in_module(sys)
        assert isinstance(count, int)
