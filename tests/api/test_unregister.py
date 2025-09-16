#!/usr/bin/env python3
"""
Pytest compatible tests for the enhanced unregistration functionality in Server class.
Tests both walker class and function endpoint unregistration.
"""

import pytest

from jvspatial.api.server import Server, endpoint, set_default_server, walker_endpoint
from jvspatial.core.entities import Node, Walker, on_visit


class TestServerUnregistration:
    """Test suite for server endpoint unregistration functionality."""

    def test_walker_unregistration(self):
        """Test unregistering walker classes."""
        server = Server(title="Walker Test Server", port=8001)

        @server.walker("/test-walker")
        class TestWalker(Walker):
            message: str = "Hello from test walker"

            @on_visit(Node)
            async def process(self, here):
                self.response["result"] = f"Processed: {self.message}"

        # Verify walker is registered
        walker_endpoints = server.list_walker_endpoints()
        assert "TestWalker" in walker_endpoints
        assert len(walker_endpoints) == 1

        # Unregister walker
        success = server.unregister_walker_class(TestWalker)
        assert success, "Walker unregistration should succeed"

        # Verify walker is removed
        walker_endpoints = server.list_walker_endpoints()
        assert len(walker_endpoints) == 0

        # Try to unregister again (should fail)
        success = server.unregister_walker_class(TestWalker)
        assert not success, "Repeat unregistration should fail"

    def test_function_endpoint_unregistration_by_reference(self):
        """Test unregistering function endpoints by function reference."""
        server = Server(title="Function Test Server", port=8002)

        @server.route("/test-function")
        def test_function():
            """Test function endpoint."""
            return {"message": "Hello from test function"}

        # Verify function is registered
        function_endpoints = server.list_function_endpoints()
        assert "test_function" in function_endpoints
        assert len(function_endpoints) == 1

        # Unregister function by reference
        success = server.unregister_endpoint(test_function)
        assert success, "Function unregistration should succeed"

        # Verify function is removed
        function_endpoints = server.list_function_endpoints()
        assert len(function_endpoints) == 0

    def test_function_endpoint_unregistration_by_path(self):
        """Test unregistering function endpoints by path."""
        server = Server(title="Path Test Server", port=8003)
        set_default_server(server)

        @endpoint("/package-function")
        def package_function():
            """Package-style function endpoint."""
            return {"message": "Hello from package function"}

        # Unregister function by path
        success = server.unregister_endpoint("/package-function")
        assert success, "Function path unregistration should succeed"

        # Verify function is removed from custom routes
        assert (
            len(
                [
                    r
                    for r in server._custom_routes
                    if r.get("path") == "/package-function"
                ]
            )
            == 0
        )

    def test_path_based_comprehensive_unregistration(self):
        """Test removing all endpoints from a specific path."""
        server = Server(title="Comprehensive Path Test Server", port=8004)
        set_default_server(server)

        @server.walker("/shared-path")
        class PathWalker(Walker):
            data: str = "walker data"

            @on_visit(Node)
            async def process(self, here):
                self.response["result"] = f"Processed: {self.data}"

        # Test comprehensive path removal
        removed_count = server.unregister_endpoint_by_path("/shared-path")
        assert removed_count >= 1, "Should remove at least one endpoint"

        # Verify walker is removed
        walker_endpoints = server.list_walker_endpoints()
        assert len(walker_endpoints) == 0

    def test_invalid_unregistration_parameters(self):
        """Test error handling for invalid unregistration parameters."""
        server = Server(title="Error Test Server", port=8005)

        # Test invalid parameter types
        success = server.unregister_endpoint(123)
        assert not success, "Invalid parameter should fail"

        success = server.unregister_endpoint(None)
        assert not success, "None parameter should fail"

        # Test non-existent walker
        class NonExistentWalker(Walker):
            pass

        success = server.unregister_walker_class(NonExistentWalker)
        assert not success, "Removing non-existent walker should fail"

        # Test non-existent function
        def non_existent_function():
            pass

        success = server.unregister_endpoint(non_existent_function)
        assert not success, "Removing non-existent function should fail"

    def test_endpoint_listing_methods(self):
        """Test the various endpoint listing methods."""
        server = Server(title="Listing Test Server", port=8006)

        @server.walker("/list-walker")
        class ListWalker(Walker):
            data: str = "list walker"

            @on_visit(Node)
            async def process(self, here):
                self.response["result"] = f"Listed: {self.data}"

        @server.route("/list-function")
        def list_function():
            return {"message": "List function"}

        # Test individual listing methods
        walker_endpoints = server.list_walker_endpoints()
        function_endpoints = server.list_function_endpoints()
        all_endpoints = server.list_all_endpoints()

        assert len(walker_endpoints) == 1
        assert "ListWalker" in walker_endpoints
        assert len(function_endpoints) == 1
        assert "list_function" in function_endpoints

        assert "walkers" in all_endpoints
        assert "functions" in all_endpoints
        assert len(all_endpoints["walkers"]) == 1
        assert len(all_endpoints["functions"]) == 1

    def test_package_style_endpoint_unregistration(self):
        """Test unregistration of package-style endpoints."""
        server = Server(title="Package Style Test Server", port=8007)
        set_default_server(server)

        @walker_endpoint("/pkg-walker")
        class PackageStyleWalker(Walker):
            data: str = "package walker"

            @on_visit(Node)
            async def process(self, here):
                self.response["result"] = f"Package: {self.data}"

        # Verify walker is registered
        walker_endpoints = server.list_walker_endpoints()
        assert "PackageStyleWalker" in walker_endpoints

        # Unregister package-style walker
        success = server.unregister_walker_class(PackageStyleWalker)
        assert success, "Package walker unregistration should succeed"

        # Verify walker is removed
        walker_endpoints = server.list_walker_endpoints()
        assert "PackageStyleWalker" not in walker_endpoints
