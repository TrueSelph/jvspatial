"""
Test suite for API Integration functionality.

This module implements comprehensive tests for:
- Endpoint decorators (@walker_endpoint, @endpoint)
- Parameter models generated from Walker fields and EndpointField configurations
- API routes and JSON responses
- Error handling in API endpoints (validation, not found, exceptions)
- Startup/shutdown hooks and middleware registration
- API documentation generation (OpenAPI/Swagger UI)
- Server lifecycle management
"""

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from jvspatial.api.endpoint.router import EndpointField, EndpointRouter
from jvspatial.api.server import Server, ServerConfig
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node, Walker, on_exit, on_visit


class ApiTestNode(Node):
    """Test node for API testing."""

    name: str = ""
    value: int = 0
    category: str = ""


class ApiTestWalker(Walker):
    """Test walker for API endpoint testing."""

    name: str = EndpointField(description="Name parameter")
    limit: int = EndpointField(default=10, description="Limit results")
    category: Optional[str] = EndpointField(
        default=None, description="Filter by category"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.processed_data = []

    @on_visit(ApiTestNode)
    async def process_node(self, here):
        """Process test nodes."""
        if self.category is None or here.category == self.category:
            self.processed_data.append(
                {"name": here.name, "value": here.value, "category": here.category}
            )

        if len(self.processed_data) >= self.limit:
            await self.disengage()


class FailingWalker(Walker):
    """Walker that intentionally fails for error testing."""

    should_fail: bool = EndpointField(default=False, description="Whether to fail")

    @on_visit(ApiTestNode)
    async def process_with_failure(self, here):
        """Process with potential failure."""
        if self.should_fail:
            raise ValueError("Intentional test failure")
        self.report({"status": "success"})


class ValidationWalker(Walker):
    """Walker for testing parameter validation."""

    required_param: str = EndpointField(description="Required parameter")
    min_value: int = EndpointField(ge=1, description="Minimum value of 1")
    max_length: str = EndpointField(max_length=10, description="Max 10 characters")


@pytest.fixture
def mock_context():
    """Mock GraphContext for testing."""
    context = MagicMock(spec=GraphContext)
    context.database = AsyncMock()
    return context


@pytest.fixture
def server_config():
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
def test_server(server_config):
    """Create test server instance."""
    return Server(config=server_config)


@pytest.fixture
def test_app(test_server):
    """Create FastAPI app for testing."""
    app = test_server._create_app()
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestServerInitialization:
    """Test Server initialization and configuration."""

    def test_server_basic_initialization(self):
        """Test basic server initialization."""
        server = Server()
        assert server.config.title == "jvspatial API"
        assert server.config.port == 8000
        assert server.config.cors_enabled is True
        assert isinstance(server.endpoint_router, EndpointRouter)

    def test_server_with_config_dict(self):
        """Test server initialization with config dictionary."""
        config = {"title": "Custom API", "port": 9000, "debug": True}
        server = Server(config=config)
        assert server.config.title == "Custom API"
        assert server.config.port == 9000
        assert server.config.debug is True

    def test_server_with_config_object(self, server_config):
        """Test server initialization with ServerConfig object."""
        server = Server(config=server_config)
        assert server.config.title == server_config.title
        assert server.config.port == server_config.port

    def test_server_with_kwargs(self):
        """Test server initialization with kwargs."""
        server = Server(title="Kwargs API", port=7000, debug=True)
        assert server.config.title == "Kwargs API"
        assert server.config.port == 7000
        assert server.config.debug is True

    def test_server_config_merge(self, server_config):
        """Test server configuration merging with kwargs."""
        server = Server(config=server_config, port=9999, debug=False)
        assert server.config.title == server_config.title  # From config
        assert server.config.port == 9999  # Overridden by kwargs
        assert server.config.debug is False  # Overridden by kwargs


class TestWalkerEndpointDecorator:
    """Test @walker_endpoint decorator functionality."""

    def test_walker_endpoint_registration(self, test_server):
        """Test walker endpoint registration."""

        @test_server.walker("/test-walker")
        class TestAPIWalker(Walker):
            param: str = EndpointField(description="Test parameter")

        # Check walker is registered using endpoint registry
        assert test_server._endpoint_registry.has_walker(TestAPIWalker)

    def test_walker_endpoint_with_methods(self, test_server):
        """Test walker endpoint with specific HTTP methods."""

        @test_server.walker("/test-methods", methods=["GET", "POST"])
        class MethodWalker(Walker):
            data: str = EndpointField(description="Input data")

        endpoint_info = test_server._endpoint_registry.get_walker_info(MethodWalker)
        assert endpoint_info.methods == ["GET", "POST"]

    def test_walker_endpoint_with_metadata(self, test_server):
        """Test walker endpoint with tags and summary."""

        @test_server.walker("/test-meta", tags=["testing"], summary="Test endpoint")
        class MetaWalker(Walker):
            value: int = EndpointField(description="Test value")

        endpoint_info = test_server._endpoint_registry.get_walker_info(MetaWalker)
        assert endpoint_info.kwargs["tags"] == ["testing"]
        assert endpoint_info.kwargs["summary"] == "Test endpoint"

    def test_multiple_walker_endpoints(self, test_server):
        """Test registering multiple walker endpoints."""

        @test_server.walker("/walker1")
        class Walker1(Walker):
            param1: str = EndpointField(description="Parameter 1")

        @test_server.walker("/walker2")
        class Walker2(Walker):
            param2: int = EndpointField(description="Parameter 2")

        walkers = test_server._endpoint_registry.list_walkers()
        assert len(walkers) == 2
        assert test_server._endpoint_registry.has_walker(Walker1)
        assert test_server._endpoint_registry.has_walker(Walker2)


class TestEndpointDecorator:
    """Test @endpoint decorator functionality."""

    def test_function_endpoint_registration(self, test_server):
        """Test function endpoint registration."""

        @test_server.route("/test-function")
        async def test_function():
            """Test function endpoint."""
            return {"message": "Hello from function"}

        # Check function is registered using endpoint registry
        assert test_function in test_server._custom_routes or any(
            route.get("endpoint") == test_function
            for route in test_server._custom_routes
        )

    def test_function_endpoint_with_parameters(self, test_server):
        """Test function endpoint with parameters."""

        @test_server.route("/test-params", methods=["POST"])
        async def param_function(name: str, value: int = 10):
            """Function with parameters."""
            return {"name": name, "value": value}

        # Check in custom routes
        found_route = next(
            (
                route
                for route in test_server._custom_routes
                if route.get("endpoint") == param_function
            ),
            None,
        )
        assert found_route is not None
        assert found_route["methods"] == ["POST"]

    def test_function_endpoint_with_metadata(self, test_server):
        """Test function endpoint with metadata."""

        @test_server.route(
            "/test-function-meta",
            tags=["functions"],
            summary="Test function",
            description="A test function endpoint",
        )
        async def meta_function():
            """Function with metadata."""
            return {"status": "ok"}

        # Check in custom routes
        found_route = next(
            (
                route
                for route in test_server._custom_routes
                if route.get("endpoint") == meta_function
            ),
            None,
        )
        assert found_route is not None
        assert found_route.get("tags") == ["functions"]
        assert found_route.get("summary") == "Test function"


class TestParameterModels:
    """Test parameter model generation from Walker fields."""

    def test_endpoint_field_parameter_extraction(self, test_server):
        """Test EndpointField parameter extraction."""

        @test_server.walker("/param-test")
        class ParamWalker(Walker):
            required_field: str = EndpointField(description="Required parameter")
            optional_field: int = EndpointField(
                default=42, description="Optional parameter"
            )
            constrained_field: str = EndpointField(
                min_length=2, max_length=20, description="Constrained parameter"
            )

        # Create the app to trigger parameter model generation
        app = test_server._create_app()

        # Verify parameters are extracted correctly
        # This would be checked through the generated OpenAPI schema
        assert app is not None

    def test_parameter_validation_types(self, test_server):
        """Test parameter validation with various types."""

        @test_server.walker("/validation-test")
        class ValidationTestWalker(Walker):
            string_param: str = EndpointField(description="String parameter")
            int_param: int = EndpointField(ge=0, description="Non-negative integer")
            float_param: float = EndpointField(gt=0.0, description="Positive float")
            bool_param: bool = EndpointField(
                default=True, description="Boolean parameter"
            )
            list_param: List[str] = EndpointField(
                default_factory=list, description="List of strings"
            )

        app = test_server._create_app()
        assert app is not None

    def test_parameter_with_pydantic_constraints(self, test_server):
        """Test parameters with Pydantic validation constraints."""

        @test_server.walker("/constraints-test")
        class ConstraintsWalker(Walker):
            email: str = EndpointField(
                pattern=r"^[^@]+@[^@]+\.[^@]+$", description="Email address"
            )
            age: int = EndpointField(ge=0, le=120, description="Age in years")
            score: float = EndpointField(
                ge=0.0, le=1.0, description="Score between 0 and 1"
            )

        app = test_server._create_app()
        assert app is not None


class TestAPIRoutes:
    """Test API route functionality and responses."""

    @pytest.mark.asyncio
    async def test_walker_endpoint_basic_request(self, test_server):
        """Test basic walker endpoint request."""

        @test_server.walker("/basic-walker")
        class BasicWalker(Walker):
            message: str = EndpointField(description="Message to process")

            @on_visit(ApiTestNode)
            async def process(self, here):
                self.report({"processed_message": self.message.upper()})

        app = test_server._create_app()
        client = TestClient(app)

        with patch("jvspatial.core.entities.Root.get") as mock_root:
            root_node = ApiTestNode(name="root")
            mock_root.return_value = root_node

            response = client.post("/api/basic-walker", json={"message": "hello world"})
            assert response.status_code == 200
            data = response.json()
            assert "processed_message" in data
            assert data["processed_message"] == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_walker_endpoint_get_request(self, test_server):
        """Test walker endpoint with GET request."""

        @test_server.walker("/get-walker", methods=["GET"])
        class GetWalker(Walker):
            param: str = EndpointField(default="default", description="Query parameter")

            @on_visit(ApiTestNode)
            async def process(self, here):
                self.report({"param_received": self.param})

        app = test_server._create_app()
        client = TestClient(app)

        with patch("jvspatial.core.entities.Root.get") as mock_root:
            root_node = ApiTestNode(name="root")
            mock_root.return_value = root_node

            response = client.get("/api/get-walker?param=test_value")
            if response.status_code != 200:
                print(f"Response status: {response.status_code}")
                print(f"Response body: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["param_received"] == "test_value"

    @pytest.mark.asyncio
    async def test_function_endpoint_response(self, test_server):
        """Test function endpoint response."""

        @test_server.route("/test-function")
        async def test_function(name: str = "world"):
            """Test function."""
            return {"greeting": f"Hello, {name}!"}

        app = test_server._create_app()
        client = TestClient(app)

        response = client.get("/test-function?name=test")
        assert response.status_code == 200
        data = response.json()
        assert data["greeting"] == "Hello, test!"

    @pytest.mark.asyncio
    async def test_complex_walker_response(self, test_server):
        """Test complex walker with node processing."""

        @test_server.walker("/complex-walker")
        class ComplexWalker(Walker):
            filter_category: Optional[str] = EndpointField(
                default=None, description="Category filter"
            )
            limit: int = EndpointField(default=5, ge=1, description="Result limit")
            results: List[Dict[str, Any]] = EndpointField(
                default_factory=list, exclude_endpoint=True
            )

            def __init__(self, **kwargs):
                super().__init__(**kwargs)

            @on_visit(ApiTestNode)
            async def collect_nodes(self, here):
                if (
                    self.filter_category is None
                    or here.category == self.filter_category
                ):
                    self.results.append(
                        {
                            "name": here.name,
                            "value": here.value,
                            "category": here.category,
                        }
                    )

                if len(self.results) >= self.limit:
                    await self.disengage()

            @on_exit
            async def finalize_results(self):
                self.report({"results": self.results})
                self.report({"count": len(self.results)})

        app = test_server._create_app()
        client = TestClient(app)

        # Mock node traversal
        with patch("jvspatial.core.entities.Root.get") as mock_root:
            root_node = ApiTestNode(name="root", category="test")
            mock_root.return_value = root_node

            response = client.post(
                "/api/complex-walker", json={"filter_category": "test", "limit": 3}
            )

            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert "count" in data


class TestAPIErrorHandling:
    """Test API error handling."""

    @pytest.mark.asyncio
    async def test_validation_error_handling(self, test_server):
        """Test parameter validation error handling."""

        @test_server.walker("/validation-test")
        class ValidationWalker(Walker):
            required_param: str = EndpointField(description="Required parameter")
            positive_int: int = EndpointField(gt=0, description="Positive integer")

        app = test_server._create_app()
        client = TestClient(app)

        # Test missing required parameter
        response = client.post("/api/validation-test", json={"positive_int": 5})
        assert response.status_code == 422  # Validation error

        # Test invalid constraint
        response = client.post(
            "/api/validation-test", json={"required_param": "test", "positive_int": -1}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_walker_runtime_error_handling(self, test_server):
        """Test walker runtime error handling."""

        @test_server.walker("/error-walker")
        class ErrorWalker(Walker):
            should_fail: bool = EndpointField(
                default=False, description="Trigger error"
            )

            @on_visit(ApiTestNode)
            async def process_with_error(self, here):
                if self.should_fail:
                    raise RuntimeError("Test runtime error")
                self.report({"status": "success"})

        app = test_server._create_app()
        client = TestClient(app)

        with patch("jvspatial.core.entities.Root.get") as mock_root:
            root_node = ApiTestNode(name="root")
            mock_root.return_value = root_node

            # Test successful execution
            response = client.post("/api/error-walker", json={"should_fail": False})
            assert response.status_code == 200

            # Test error handling - errors should be reported via reporting system
            response = client.post("/api/error-walker", json={"should_fail": True})
            assert response.status_code == 200
            data = response.json()
            assert "hook_error" in data
            assert "hook_name" in data
            assert data["hook_error"] == "Test runtime error"
            assert data["hook_name"] == "process_with_error"

    @pytest.mark.asyncio
    async def test_function_error_handling(self, test_server):
        """Test function endpoint error handling."""

        @test_server.route("/error-function")
        async def error_function(should_fail: bool = False):
            """Function that can fail."""
            if should_fail:
                raise ValueError("Test function error")
            return {"status": "ok"}

        app = test_server._create_app()
        client = TestClient(app)

        # Test successful execution
        response = client.get("/error-function?should_fail=false")
        assert response.status_code == 200

        # Test error handling - should expect exception to be raised
        with pytest.raises(ValueError, match="Test function error"):
            client.get("/error-function?should_fail=true")

    def test_404_error_handling(self, test_server):
        """Test 404 error for non-existent endpoints."""
        app = test_server._create_app()
        client = TestClient(app)

        response = client.get("/non-existent-endpoint")
        assert response.status_code == 404


class TestLifecycleHooks:
    """Test startup and shutdown hooks."""

    @pytest.mark.asyncio
    async def test_startup_hooks(self, test_server):
        """Test server startup hooks."""
        startup_called = []

        @test_server.on_startup
        async def startup_hook1():
            """First startup hook."""
            startup_called.append("hook1")

        @test_server.on_startup
        async def startup_hook2():
            """Second startup hook."""
            startup_called.append("hook2")

        # Simulate startup
        app = test_server._create_app()

        # Manually trigger startup events for testing using lifecycle manager
        for task in test_server._lifecycle_manager._startup_hooks:
            if asyncio.iscoroutinefunction(task):
                await task()
            else:
                task()

        assert len(startup_called) == 2
        assert "hook1" in startup_called
        assert "hook2" in startup_called

    @pytest.mark.asyncio
    async def test_shutdown_hooks(self, test_server):
        """Test server shutdown hooks."""
        shutdown_called = []

        @test_server.on_shutdown
        async def shutdown_hook1():
            """First shutdown hook."""
            shutdown_called.append("hook1")

        @test_server.on_shutdown
        async def shutdown_hook2():
            """Second shutdown hook."""
            shutdown_called.append("hook2")

        # Simulate shutdown using lifecycle manager
        for task in test_server._lifecycle_manager._shutdown_hooks:
            if asyncio.iscoroutinefunction(task):
                await task()
            else:
                task()

        assert len(shutdown_called) == 2
        assert "hook1" in shutdown_called
        assert "hook2" in shutdown_called

    def test_middleware_registration(self, test_server):
        """Test custom middleware registration."""

        @test_server.middleware("http")
        async def custom_middleware(request, call_next):
            """Custom middleware."""
            response = await call_next(request)
            response.headers["X-Custom-Header"] = "test-value"
            return response

        # Verify middleware is registered using middleware manager
        assert len(test_server._middleware_manager._custom_middleware) == 1
        middleware_entry = test_server._middleware_manager._custom_middleware[0]
        assert middleware_entry["func"] == custom_middleware
        assert middleware_entry["middleware_type"] == "http"


class TestOpenAPIDocumentation:
    """Test OpenAPI documentation generation."""

    def test_openapi_schema_generation(self, test_server):
        """Test OpenAPI schema is generated."""

        @test_server.walker(
            "/documented-walker",
            summary="Test Walker",
            description="A walker for testing documentation",
        )
        class DocumentedWalker(Walker):
            name: str = EndpointField(description="User name")
            age: int = EndpointField(ge=0, le=120, description="User age")

        app = test_server._create_app()
        client = TestClient(app)

        # Get OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == test_server.config.title
        assert "paths" in schema
        assert "/api/documented-walker" in schema["paths"]

    def test_swagger_ui_accessible(self, test_server):
        """Test Swagger UI is accessible."""
        app = test_server._create_app()
        client = TestClient(app)

        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    def test_redoc_accessible(self, test_server):
        """Test ReDoc is accessible."""
        app = test_server._create_app()
        client = TestClient(app)

        response = client.get("/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()

    def test_endpoint_documentation_metadata(self, test_server):
        """Test endpoint documentation includes metadata."""

        @test_server.walker(
            "/meta-walker",
            tags=["testing"],
            summary="Metadata Walker",
            description="Walker with rich metadata",
        )
        class MetaWalker(Walker):
            query: str = EndpointField(description="Search query", example="test query")
            limit: int = EndpointField(
                default=10, ge=1, le=100, description="Result limit"
            )

        app = test_server._create_app()
        client = TestClient(app)

        schema_response = client.get("/openapi.json")
        schema = schema_response.json()

        walker_path = schema["paths"]["/api/meta-walker"]
        assert "tags" in walker_path["post"]
        assert "testing" in walker_path["post"]["tags"]
        assert walker_path["post"]["summary"] == "Metadata Walker"


class TestServerConfiguration:
    """Test server configuration options."""

    def test_cors_configuration(self):
        """Test CORS configuration."""
        config = ServerConfig(
            cors_enabled=True,
            cors_origins=["http://localhost:3000"],
            cors_methods=["GET", "POST"],
            cors_headers=["Content-Type"],
        )
        server = Server(config=config)

        assert server.config.cors_enabled is True
        assert server.config.cors_origins == ["http://localhost:3000"]
        assert server.config.cors_methods == ["GET", "POST"]

    def test_database_configuration(self):
        """Test database configuration."""
        config = ServerConfig(db_type="json", db_path="jvdb/tests")
        server = Server(config=config)

        assert server.config.db_type == "json"
        assert server.config.db_path == "jvdb/tests"

    def test_api_documentation_configuration(self):
        """Test API documentation configuration."""
        config = ServerConfig(docs_url="/api/docs", redoc_url="/api/redoc")
        server = Server(config=config)

        assert server.config.docs_url == "/api/docs"
        assert server.config.redoc_url == "/api/redoc"

    def test_logging_configuration(self):
        """Test logging configuration."""
        config = ServerConfig(log_level="debug")
        server = Server(config=config)

        assert server.config.log_level == "debug"


class TestDynamicEndpointManagement:
    """Test dynamic endpoint registration and removal."""

    def test_dynamic_walker_registration(self, test_server):
        """Test dynamic walker registration after server creation."""

        # Register walker dynamically
        @test_server.walker("/dynamic-walker")
        class DynamicWalker(Walker):
            param: str = EndpointField(description="Dynamic parameter")

        assert test_server._endpoint_registry.has_walker(DynamicWalker)

        # Create app and test endpoint
        app = test_server._create_app()
        client = TestClient(app)

        # Verify endpoint exists in OpenAPI schema
        schema_response = client.get("/openapi.json")
        schema = schema_response.json()
        assert "/api/dynamic-walker" in schema["paths"]

    def test_endpoint_removal(self, test_server):
        """Test endpoint registration tracking (removal not yet implemented)."""

        @test_server.walker("/removable-walker")
        class RemovableWalker(Walker):
            param: str = EndpointField(description="Removable walker")

        # Initially registered using endpoint registry
        assert test_server._endpoint_registry.has_walker(RemovableWalker)

        # For now, just verify registration tracking works
        # TODO: Implement removal functionality
        endpoint_info = test_server._endpoint_registry.get_walker_info(RemovableWalker)
        assert endpoint_info.path == "/removable-walker"

    def test_multiple_endpoint_registration_removal(self, test_server):
        """Test registering multiple endpoints (removal not yet implemented)."""

        @test_server.walker("/walker-a")
        class WalkerA(Walker):
            param_a: str = EndpointField(description="Parameter A")

        @test_server.walker("/walker-b")
        class WalkerB(Walker):
            param_b: str = EndpointField(description="Parameter B")

        walkers = test_server._endpoint_registry.list_walkers()
        assert len(walkers) == 2
        assert test_server._endpoint_registry.has_walker(WalkerA)
        assert test_server._endpoint_registry.has_walker(WalkerB)

        # Verify both are properly mapped
        endpoint_info_a = test_server._endpoint_registry.get_walker_info(WalkerA)
        endpoint_info_b = test_server._endpoint_registry.get_walker_info(WalkerB)
        assert endpoint_info_a.path == "/walker-a"
        assert endpoint_info_b.path == "/walker-b"
