"""Test suite for API components.

Tests the new focused components:
- AppBuilder
- EndpointManager
- ErrorHandler
- AuthenticationMiddleware
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jvspatial.api.components import (
    AppBuilder,
    AuthenticationMiddleware,
    EndpointManager,
    ErrorHandler,
)
from jvspatial.api.config import ServerConfig
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Walker


class TestAppBuilder:
    """Test AppBuilder component."""

    @pytest.fixture
    def server_config(self):
        """Basic server configuration for testing."""
        return ServerConfig(
            title="Test API",
            description="Test API Description",
            version="1.0.0",
            debug=True,
            port=8001,
            cors_enabled=True,
        )

    @pytest.fixture
    def app_builder(self, server_config):
        """Create AppBuilder instance for testing."""
        return AppBuilder(server_config)

    async def test_app_builder_initialization(self, app_builder, server_config):
        """Test AppBuilder initialization."""
        assert app_builder.config == server_config

    async def test_create_app(self, app_builder):
        """Test FastAPI app creation."""
        app = app_builder.create_app()

        assert isinstance(app, FastAPI)
        assert app.title == "Test API"
        assert app.description == "Test API Description"
        assert app.version == "1.0.0"
        assert app.debug is True

    async def test_create_app_with_lifespan(self, app_builder):
        """Test FastAPI app creation with lifespan."""
        from contextlib import asynccontextmanager

        lifespan_called = []

        @asynccontextmanager
        def lifespan(app: FastAPI):
            async def _lifespan():
                lifespan_called.append("startup")
                yield
                lifespan_called.append("shutdown")

            return _lifespan()

        app = app_builder.create_app(lifespan=lifespan)

        assert isinstance(app, FastAPI)
        # Note: lifespan testing would require actually starting the app

    async def test_register_core_routes(self, app_builder):
        """Test core route registration."""
        app = app_builder.create_app()

        # Register core routes
        app_builder.register_core_routes(app)

        # Test that routes are registered
        client = TestClient(app)

        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Test API"

        # Test root endpoint
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Test API"
        assert data["version"] == "1.0.0"

    async def test_configure_openapi_security(self, app_builder):
        """Test OpenAPI security configuration."""
        app = app_builder.create_app()

        # Configure OpenAPI security
        app_builder.configure_openapi_security(app, has_auth_endpoints=True)

        # Verify app is configured (exact verification depends on implementation)
        assert isinstance(app, FastAPI)


class TestEndpointManager:
    """Test EndpointManager component."""

    @pytest.fixture
    def endpoint_manager(self):
        """Create EndpointManager instance for testing."""
        return EndpointManager()

    async def test_endpoint_manager_initialization(self, endpoint_manager):
        """Test EndpointManager initialization."""
        assert endpoint_manager._endpoint_registry is not None
        assert endpoint_manager._endpoint_router is None  # Initially None until set

    async def test_get_registry(self, endpoint_manager):
        """Test registry access."""
        registry = endpoint_manager.get_registry()
        assert registry is not None

    async def test_get_router(self, endpoint_manager):
        """Test router access."""
        router = endpoint_manager.get_router()
        assert router is None  # Initially None until set

    async def test_register_walker_endpoint(self, endpoint_manager):
        """Test walker endpoint registration."""

        class TestWalker(Walker):
            param: str = ""

        # Register walker
        decorator = endpoint_manager.register_endpoint("/test-walker")
        decorated_walker = decorator(TestWalker)

        # Verify registration
        assert decorated_walker == TestWalker
        assert endpoint_manager.get_registry().has_walker(TestWalker)

    async def test_register_function_endpoint(self, endpoint_manager):
        """Test function endpoint registration."""

        async def test_function():
            return {"message": "test"}

        # Register function
        decorator = endpoint_manager.register_endpoint("/test-function")
        decorated_function = decorator(test_function)

        # Verify registration
        assert decorated_function == test_function
        assert endpoint_manager.get_registry().has_function(test_function)

    async def test_register_endpoint_with_methods(self, endpoint_manager):
        """Test endpoint registration with specific methods."""

        class TestWalker(Walker):
            param: str = ""

        # Register with specific methods
        decorator = endpoint_manager.register_endpoint(
            "/test-methods", methods=["GET", "POST"]
        )
        decorated_walker = decorator(TestWalker)

        # Verify registration
        assert decorated_walker == TestWalker
        assert endpoint_manager.get_registry().has_walker(TestWalker)

    async def test_register_endpoint_with_metadata(self, endpoint_manager):
        """Test endpoint registration with metadata."""

        class TestWalker(Walker):
            param: str = ""

        # Register with metadata
        decorator = endpoint_manager.register_endpoint(
            "/test-meta", tags=["testing"], summary="Test endpoint"
        )
        decorated_walker = decorator(TestWalker)

        # Verify registration
        assert decorated_walker == TestWalker
        assert endpoint_manager.get_registry().has_walker(TestWalker)


class TestErrorHandler:
    """Test ErrorHandler component."""

    async def test_error_handler_initialization(self):
        """Test ErrorHandler initialization."""
        handler = ErrorHandler()
        assert handler is not None

    async def test_handle_exception_with_jvspatial_error(self):
        """Test handling JVSpatialAPIException."""
        from jvspatial.exceptions import JVSpatialAPIException

        # Create mock request
        request = MagicMock()
        request.state.request_id = "test-request-123"
        request.url.path = "/test/path"

        # Create test exception
        exc = JVSpatialAPIException("Test error")
        exc.status_code = 400

        # Handle exception
        response = await ErrorHandler.handle_exception(request, exc)

        # Verify response
        assert response.status_code == 400
        data = response.body.decode()
        assert "Test error" in data
        assert "test-request-123" in data
        assert "/test/path" in data

    async def test_handle_exception_with_generic_error(self):
        """Test handling generic exceptions."""
        # Create mock request
        request = MagicMock()
        request.state.request_id = "test-request-456"
        request.url.path = "/test/path"

        # Create generic exception
        exc = ValueError("Generic error")

        # Handle exception
        response = await ErrorHandler.handle_exception(request, exc)

        # Verify response
        assert response.status_code == 500
        data = response.body.decode()
        assert "internal_error" in data
        assert "unexpected error" in data

    async def test_handle_exception_without_request_id(self):
        """Test handling exceptions without request ID."""
        # Create mock request without request_id
        request = MagicMock()
        request.state.request_id = None
        request.url.path = "/test/path"

        # Create test exception
        exc = ValueError("Test error")

        # Handle exception
        response = await ErrorHandler.handle_exception(request, exc)

        # Verify response
        assert response.status_code == 500
        data = response.body.decode()
        assert "internal_error" in data


class TestComponentsIntegration:
    """Test integration between components."""

    @pytest.fixture
    def server_config(self):
        """Basic server configuration for testing."""
        return ServerConfig(
            title="Integration Test API",
            description="Integration Test Description",
            version="1.0.0",
            debug=True,
        )

    async def test_components_work_together(self, server_config):
        """Test that components work together."""
        # Create components
        app_builder = AppBuilder(server_config)
        endpoint_manager = EndpointManager()
        error_handler = ErrorHandler()

        # Create app
        app = app_builder.create_app()

        # Register core routes
        app_builder.register_core_routes(app)

        # Test app functionality
        client = TestClient(app)

        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200

        # Test root endpoint
        response = client.get("/")
        assert response.status_code == 200

    async def test_endpoint_manager_with_app_builder(self, server_config):
        """Test EndpointManager integration with AppBuilder."""
        app_builder = AppBuilder(server_config)
        endpoint_manager = EndpointManager()

        # Create app
        app = app_builder.create_app()

        # Register endpoint
        class TestWalker(Walker):
            param: str = ""

        decorator = endpoint_manager.register_endpoint("/test")
        decorator(TestWalker)

        # Verify endpoint is registered
        assert endpoint_manager.get_registry().has_walker(TestWalker)

    async def test_error_handler_integration(self, server_config):
        """Test ErrorHandler integration."""
        app_builder = AppBuilder(server_config)
        error_handler = ErrorHandler()

        # Create app
        app = app_builder.create_app()

        # Add error handler
        app.add_exception_handler(Exception, error_handler.handle_exception)

        # Test error handling
        client = TestClient(app)

        # This would test error handling if we had an endpoint that raises an error
        # For now, just verify the handler is registered
        assert len(app.exception_handlers) > 0
