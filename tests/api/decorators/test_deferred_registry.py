"""Test suite for deferred endpoint registry.

This module tests the automatic endpoint discovery system that registers
endpoints decorated before server initialization.
"""

import pytest

from jvspatial.api import (
    Server,
    ServerConfig,
    clear_deferred_endpoints,
    flush_deferred_endpoints,
    get_deferred_endpoint_count,
)
from jvspatial.api.config_groups import DatabaseConfig
from jvspatial.api.context import ServerContext, get_current_server
from jvspatial.api.decorators.deferred_registry import (
    DeferredEndpoint,
    register_deferred_endpoint,
)
from jvspatial.api.decorators.route import endpoint
from jvspatial.core.entities import Walker


# Test endpoints defined BEFORE server creation
@endpoint("/test/deferred/function", methods=["GET"])
async def deferred_function_endpoint() -> dict:
    """Test function endpoint defined before server."""
    return {"status": "ok", "source": "deferred"}


class DeferredTestWalker(Walker):
    """Test walker defined before server."""

    @endpoint("/test/deferred/walker", methods=["POST"])
    async def execute(self) -> dict:
        """Execute the walker."""
        return {"status": "ok", "source": "deferred_walker"}


class TestDeferredRegistry:
    """Test deferred endpoint registry functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Clear any existing deferred endpoints
        clear_deferred_endpoints()

    def teardown_method(self):
        """Clean up after tests."""
        # Clear deferred endpoints after each test
        clear_deferred_endpoints()

    def test_register_deferred_endpoint_function(self):
        """Test registering a deferred function endpoint."""
        config = {
            "path": "/test/path",
            "methods": ["GET"],
            "auth_required": False,
            "is_function": True,
        }

        async def test_func():
            return {"test": "data"}

        initial_count = get_deferred_endpoint_count()
        register_deferred_endpoint(test_func, config)
        assert get_deferred_endpoint_count() == initial_count + 1

    def test_register_deferred_endpoint_walker(self):
        """Test registering a deferred walker endpoint."""
        config = {
            "path": "/test/walker",
            "methods": ["POST"],
            "auth_required": True,
            "is_function": False,
        }

        class TestWalker(Walker):
            pass

        initial_count = get_deferred_endpoint_count()
        register_deferred_endpoint(TestWalker, config)
        assert get_deferred_endpoint_count() == initial_count + 1

    def test_flush_deferred_endpoints_to_server(self):
        """Test flushing deferred endpoints to a server."""
        # Register some deferred endpoints
        config1 = {
            "path": "/test/flush1",
            "methods": ["GET"],
            "auth_required": False,
            "is_function": True,
        }

        async def func1():
            return {"test": 1}

        config2 = {
            "path": "/test/flush2",
            "methods": ["POST"],
            "auth_required": False,
            "is_function": False,
        }

        class TestWalker(Walker):
            pass

        register_deferred_endpoint(func1, config1)
        register_deferred_endpoint(TestWalker, config2)

        assert get_deferred_endpoint_count() == 2

        # Create server - it will automatically flush deferred endpoints during init
        server = Server(
            config=ServerConfig(
                title="Test Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # Server.init already flushed, so count should be 0
        assert get_deferred_endpoint_count() == 0  # Registry should be cleared

        # Verify endpoints were registered
        assert server._endpoint_registry.has_function(func1)
        assert server._endpoint_registry.has_walker(TestWalker)

    def test_endpoint_defined_before_server_auto_registered(self):
        """Test that endpoints defined before server creation are auto-registered."""
        # The endpoints were decorated at module import time and should be in deferred registry
        # But setup_method cleared them, so we need to re-register them
        from jvspatial.api.decorators.deferred_registry import (
            register_deferred_endpoint,
        )

        # Re-register the module-level endpoints that were cleared in setup_method
        register_deferred_endpoint(
            deferred_function_endpoint,
            {
                "path": "/test/deferred/function",
                "methods": ["GET"],
                "auth_required": False,
                "is_function": True,
            },
        )
        register_deferred_endpoint(
            DeferredTestWalker,
            {
                "path": "/test/deferred/walker",
                "methods": ["POST"],
                "auth_required": False,
                "is_function": False,
            },
        )

        # Create a server - it should automatically flush deferred endpoints
        server = Server(
            config=ServerConfig(
                title="Test Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # The deferred endpoints should have been flushed during server initialization
        # Verify they're registered
        assert server._endpoint_registry.has_function(deferred_function_endpoint)
        assert server._endpoint_registry.has_walker(DeferredTestWalker)

    def test_endpoint_defined_after_server_immediate_registration(self):
        """Test that endpoints defined after server creation register immediately."""
        # Create server first
        server = Server(
            config=ServerConfig(
                title="Test Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # Define endpoint after server exists
        @endpoint("/test/immediate", methods=["GET"])
        async def immediate_endpoint() -> dict:
            """Endpoint defined after server."""
            return {"status": "ok", "source": "immediate"}

        # Should be registered immediately (not deferred)
        assert server._endpoint_registry.has_function(immediate_endpoint)
        assert get_deferred_endpoint_count() == 0

    def test_multiple_servers_sequential(self):
        """Test that multiple servers in sequence work correctly."""
        # First server
        server1 = Server(
            config=ServerConfig(
                title="Server 1",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # Define endpoint after first server
        @endpoint("/test/server1", methods=["GET"])
        async def server1_endpoint() -> dict:
            return {"server": 1}

        assert server1._endpoint_registry.has_function(server1_endpoint)

        # Second server (should flush any new deferred endpoints)
        server2 = Server(
            config=ServerConfig(
                title="Server 2",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # server1_endpoint should NOT be in server2 (it was registered to server1)
        assert not server2._endpoint_registry.has_function(server1_endpoint)

    def test_server_context_flushes_deferred(self):
        """Test that ServerContext flushes deferred endpoints."""
        # Register a deferred endpoint
        config = {
            "path": "/test/context",
            "methods": ["GET"],
            "auth_required": False,
            "is_function": True,
        }

        async def context_endpoint():
            return {"test": "context"}

        register_deferred_endpoint(context_endpoint, config)
        assert get_deferred_endpoint_count() == 1

        # Create server
        server = Server(
            config=ServerConfig(
                title="Context Test Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # Enter context - should flush deferred endpoints
        with ServerContext(server):
            # Endpoint should be registered
            assert server._endpoint_registry.has_function(context_endpoint)
            assert get_deferred_endpoint_count() == 0

    def test_clear_deferred_endpoints(self):
        """Test clearing deferred endpoints."""
        config = {
            "path": "/test/clear",
            "methods": ["GET"],
            "auth_required": False,
            "is_function": True,
        }

        async def clear_test():
            return {}

        register_deferred_endpoint(clear_test, config)
        assert get_deferred_endpoint_count() == 1

        clear_deferred_endpoints()
        assert get_deferred_endpoint_count() == 0

    def test_flush_empty_registry(self):
        """Test flushing an empty registry."""
        server = Server(
            config=ServerConfig(
                title="Empty Test Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # Flush when registry is empty
        count = flush_deferred_endpoints(server)
        assert count == 0

    def test_deferred_endpoint_with_auth(self):
        """Test deferred endpoint with authentication requirements."""
        config = {
            "path": "/test/auth",
            "methods": ["POST"],
            "auth_required": True,
            "permissions": ["read:data"],
            "roles": ["admin"],
            "is_function": True,
        }

        async def auth_endpoint():
            return {"auth": "required"}

        register_deferred_endpoint(auth_endpoint, config)

        server = Server(
            config=ServerConfig(
                title="Auth Test Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        flush_deferred_endpoints(server)

        # Verify endpoint is registered with auth
        assert server._endpoint_registry.has_function(auth_endpoint)
        # Check auth attributes
        assert hasattr(auth_endpoint, "_auth_required")
        assert auth_endpoint._auth_required is True  # type: ignore[attr-defined]

    def test_deferred_walker_registration(self):
        """Test deferred walker registration."""
        config = {
            "path": "/test/walker/deferred",
            "methods": ["POST"],
            "auth_required": False,
            "is_function": False,
        }

        class DeferredWalker(Walker):
            pass

        register_deferred_endpoint(DeferredWalker, config)

        server = Server(
            config=ServerConfig(
                title="Walker Test Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        flush_deferred_endpoints(server)

        # Verify walker is registered
        assert server._endpoint_registry.has_walker(DeferredWalker)
        assert hasattr(DeferredWalker, "_auth_required")
        assert DeferredWalker._auth_required is False  # type: ignore[attr-defined]

    def test_no_double_registration(self):
        """Test that endpoints aren't registered twice."""
        config = {
            "path": "/test/no-double",
            "methods": ["GET"],
            "auth_required": False,
            "is_function": True,
        }

        async def no_double_endpoint():
            return {"test": "no-double"}

        # Register as deferred
        register_deferred_endpoint(no_double_endpoint, config)

        # Create server - it will automatically flush deferred endpoints during init
        server = Server(
            config=ServerConfig(
                title="No Double Server",
                database=DatabaseConfig(db_type="json", db_path=":memory:"),
            )
        )

        # Server.init already flushed, so count should be 0
        assert get_deferred_endpoint_count() == 0

        # Flush again (should be empty since already flushed)
        count2 = flush_deferred_endpoints(server)
        assert count2 == 0

        # Endpoint should still be registered
        assert server._endpoint_registry.has_function(no_double_endpoint)
