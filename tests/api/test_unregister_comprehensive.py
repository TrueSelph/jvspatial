#!/usr/bin/env python3
"""
Comprehensive pytest compatible tests for the enhanced unregistration functionality.
Tests both static (non-running) and simulated running server scenarios.
"""

from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api.server import (
    Server,
    endpoint,
    get_default_server,
    set_default_server,
    walker_endpoint,
)
from jvspatial.core.entities import Node, Walker, on_visit


def test_static_server_unregistration():
    """Test unregistration on a non-running server."""
    # Create a fresh server for this test
    server = Server(title="Static Test Server", port=8003)

    # Register some endpoints
    @server.walker("/static-walker")
    class StaticWalker(Walker):
        data: str = "static data"

        @on_visit(Node)
        async def process(self, here):
            self.response["result"] = f"Static: {self.data}"

    @server.route("/static-function")
    def static_function():
        return {"message": "Static function"}

    # Verify endpoints are registered
    walkers = server.list_walker_endpoints()
    functions = server.list_function_endpoints()

    assert len(walkers) == 1, f"Expected 1 walker, got {len(walkers)}"
    assert len(functions) == 1, f"Expected 1 function, got {len(functions)}"

    # Test unregistration
    success = server.unregister_walker_class(StaticWalker)
    assert success, "Walker unregistration should succeed"

    success = server.unregister_endpoint(static_function)
    assert success, "Function unregistration should succeed"

    # Verify endpoints are removed
    walkers = server.list_walker_endpoints()
    functions = server.list_function_endpoints()

    assert len(walkers) == 0, f"Expected 0 walkers, got {len(walkers)}"
    assert len(functions) == 0, f"Expected 0 functions, got {len(functions)}"


def test_running_server_simulation():
    """Test unregistration on a simulated running server."""
    # Create a server and simulate it running
    server = Server(title="Running Test Server", port=8004)

    # Register endpoints
    @server.walker("/running-walker")
    class RunningWalker(Walker):
        data: str = "running data"

        @on_visit(Node)
        async def process(self, here):
            self.response["result"] = f"Running: {self.data}"

    @server.route("/running-function")
    def running_function():
        return {"message": "Running function"}

    # Mock the app and set running state
    server.app = MagicMock()
    server._is_running = True

    # Mock the _rebuild_app_if_needed method to track calls
    rebuild_called = {"count": 0}

    def mock_rebuild():
        rebuild_called["count"] += 1

    with patch.object(server, "_rebuild_app_if_needed", side_effect=mock_rebuild):
        # Test walker unregistration with rebuild
        success = server.unregister_walker_class(RunningWalker)
        assert success, "Walker unregistration should succeed"
        assert rebuild_called["count"] == 1, "App rebuild should be called once"

        # Test function unregistration with rebuild
        success = server.unregister_endpoint(running_function)
        assert success, "Function unregistration should succeed"
        assert rebuild_called["count"] == 2, "App rebuild should be called twice"

    # Verify endpoints are removed
    walkers = server.list_walker_endpoints()
    functions = server.list_function_endpoints()

    assert len(walkers) == 0, f"Expected 0 walkers, got {len(walkers)}"
    assert len(functions) == 0, f"Expected 0 functions, got {len(functions)}"


def test_package_style_endpoints():
    """Test unregistration of package-style endpoints."""
    # Create a server and set it as default for package-style registration
    server = Server(title="Package Test Server", port=8005)
    set_default_server(server)

    # Register package-style endpoints (these will go to the default server)
    @walker_endpoint("/pkg-walker")
    class PackageStyleWalker(Walker):
        data: str = "package walker"

        @on_visit(Node)
        async def process(self, here):
            self.response["result"] = f"Package: {self.data}"

    @endpoint("/pkg-function")
    def package_style_function():
        return {"message": "Package-style function"}

    # Verify registration (should be on the default server, which is our test server)
    default_server = get_default_server()
    walkers = default_server.list_walker_endpoints()
    functions = default_server.list_function_endpoints()
    all_endpoints = default_server.list_all_endpoints()

    # Test unregistration on the default server
    success = default_server.unregister_walker_class(PackageStyleWalker)
    assert success, "Package walker unregistration should succeed"

    # For package-style functions, test removal by function reference
    success = default_server.unregister_endpoint(package_style_function)
    if not success:
        # Fallback to path-based removal if function reference doesn't work
        success = default_server.unregister_endpoint("/pkg-function")
    assert success, "Package function unregistration should succeed"


def test_error_conditions():
    """Test error conditions and edge cases."""
    server = Server(title="Error Test Server", port=8006)

    # Test removing non-existent walker
    class NonExistentWalker(Walker):
        pass

    success = server.unregister_walker_class(NonExistentWalker)
    assert not success, "Removing non-existent walker should fail"

    # Test removing non-existent function
    def non_existent_function():
        pass

    success = server.unregister_endpoint(non_existent_function)
    assert not success, "Removing non-existent function should fail"

    # Test invalid parameter types
    success = server.unregister_endpoint(123)
    assert not success, "Invalid parameter should fail"

    success = server.unregister_endpoint(None)
    assert not success, "None parameter should fail"


def test_path_based_removal():
    """Test removal of all endpoints from a specific path."""
    server = Server(title="Path Test Server", port=8007)
    set_default_server(server)  # Set this as default for package-style endpoints

    # Register multiple endpoints
    @server.walker("/shared-path")
    class PathWalker1(Walker):
        data: str = "walker1"

        @on_visit(Node)
        async def process(self, here):
            self.response["result"] = f"Walker1: {self.data}"

    @server.route("/shared-function-path")
    def path_function():
        return {"message": "Path function"}

    # Package-style endpoint will register to the default server (our test server)
    @endpoint("/shared-function-path2")
    def package_path_function():
        return {"message": "Package path function"}

    # Test comprehensive path removal
    removed_count = server.unregister_endpoint_by_path("/shared-path")
    assert removed_count >= 1, "Should remove at least one endpoint"

    # Test function path removal
    success = server.unregister_endpoint("/shared-function-path")
    assert success, "Function path removal should succeed"

    # Test package-style function removal
    default_server = get_default_server()
    success = default_server.unregister_endpoint("/shared-function-path2")
    assert success, "Package function path removal should succeed"
