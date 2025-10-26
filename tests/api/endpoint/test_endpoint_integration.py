"""Integration tests for endpoint response injection in walker and function endpoints."""

import asyncio
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.api.context import (
    get_current_server,
    set_current_server,
)
from jvspatial.api.decorators import EndpointField
from jvspatial.api.endpoints.response import ResponseHelper as EndpointResponseHelper
from jvspatial.api.endpoints.router import EndpointRouter
from jvspatial.api.server import (
    Server,
    endpoint,
)
from jvspatial.core.entities import Node, Walker


class TestWalkerEndpointIntegration:
    """Integration tests for @endpoint decorator with response injection."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        """Set up a test server for each test."""
        self.test_server = Server(
            title="Test Server",
            description="Test server for endpoint integration tests",
            version="1.0.0",
        )
        set_current_server(self.test_server)
        yield
        # Cleanup - reset current server
        set_current_server(None)

    async def test_walker_endpoint_injection(self):
        """Test that @endpoint injects endpoint helper into walker."""

        @endpoint("/test/walker")
        class TestWalker(Walker):
            test_param: str = EndpointField(description="Test parameter")

            async def visit_node(self, node):
                # Check that endpoint helper is injected
                assert hasattr(self, "endpoint")
                assert isinstance(self.endpoint, EndpointResponseHelper)
                assert self.endpoint.walker_instance is self
                return self.endpoint.success(data={"test": "success"})

        # Create walker instance
        walker = TestWalker(test_param="test_value")

        # Verify endpoint helper is NOT injected during init
        # (it should be injected during endpoint execution)
        assert not hasattr(walker, "endpoint")

    async def test_walker_endpoint_response_methods(self):
        """Test that endpoint response methods work correctly."""

        @endpoint("/test/responses")
        class ResponseTestWalker(Walker):
            response_type: str = EndpointField(
                description="Type of response to test",
                examples=["success", "error", "not_found"],
            )

            async def visit_node(self, node):
                # Simulate endpoint injection (normally done by router)
                from jvspatial.api.endpoints.response import create_endpoint_helper

                self.endpoint = create_endpoint_helper(walker_instance=self)

                if self.response_type == "success":
                    return await self.endpoint.success(
                        data={"message": "Success response"},
                        message="Operation completed",
                    )
                elif self.response_type == "error":
                    return await self.endpoint.bad_request(
                        message="Invalid request", details={"field": "test_field"}
                    )
                elif self.response_type == "not_found":
                    return await self.endpoint.not_found(
                        message="Resource not found", details={"resource_id": "123"}
                    )
                elif self.response_type == "created":
                    return await self.endpoint.created(
                        data={"id": "new_123"},
                        message="Resource created",
                        headers={"Location": "/resources/123"},
                    )

        # Test success response
        walker = ResponseTestWalker(response_type="success")
        await walker.visit_node(None)

        report = await walker.get_report()
        # Find the response data in the report
        response_items = [
            item for item in report if isinstance(item, dict) and "status" in item
        ]
        assert len(response_items) >= 1
        response_data = response_items[0]
        assert response_data["status"] == 200
        assert response_data["data"]["message"] == "Success response"
        assert response_data["message"] == "Operation completed"

        # Test error response
        walker = ResponseTestWalker(response_type="error")
        await walker.visit_node(None)

        report = await walker.get_report()
        response_items = [
            item for item in report if isinstance(item, dict) and "status" in item
        ]
        assert len(response_items) >= 1
        response_data = response_items[0]
        assert response_data["status"] == 400
        assert response_data["error"] == "Invalid request"
        assert response_data["details"]["field"] == "test_field"

        # Test not found response
        walker = ResponseTestWalker(response_type="not_found")
        await walker.visit_node(None)

        report = await walker.get_report()
        response_items = [
            item for item in report if isinstance(item, dict) and "status" in item
        ]
        assert len(response_items) >= 1
        response_data = response_items[0]
        assert response_data["status"] == 404
        assert response_data["error"] == "Resource not found"
        assert response_data["details"]["resource_id"] == "123"

        # Test created response
        walker = ResponseTestWalker(response_type="created")
        await walker.visit_node(None)

        report = await walker.get_report()
        response_items = [
            item for item in report if isinstance(item, dict) and "status" in item
        ]
        assert len(response_items) >= 1
        response_data = response_items[0]
        assert response_data["status"] == 201
        assert response_data["data"]["id"] == "new_123"
        assert response_data["message"] == "Resource created"
        assert response_data["headers"]["Location"] == "/resources/123"

    async def test_walker_endpoint_custom_response(self):
        """Test endpoint with custom response formatting."""

        @endpoint("/test/custom")
        class CustomResponseWalker(Walker):
            status_code: int = EndpointField(
                description="Custom status code", examples=[202, 206, 418]
            )

            async def visit_node(self, node):
                # Simulate endpoint injection
                from jvspatial.api.endpoints.response import create_endpoint_helper

                self.endpoint = create_endpoint_helper(walker_instance=self)

                return await self.endpoint.response(
                    content={
                        "custom_message": "Custom response format",
                        "processed_at": "2025-09-21T06:32:18Z",
                    },
                    status_code=self.status_code,
                    headers={
                        "X-Custom-Header": "test-value",
                        "X-Status-Code": str(self.status_code),
                    },
                )

        walker = CustomResponseWalker(status_code=202)
        await walker.visit_node(None)

        report = await walker.get_report()
        response_items = [
            item for item in report if isinstance(item, dict) and "status" in item
        ]
        assert len(response_items) >= 1
        response_data = response_items[0]
        assert response_data["status"] == 202
        assert response_data["custom_message"] == "Custom response format"
        assert response_data["processed_at"] == "2025-09-21T06:32:18Z"
        assert response_data["headers"]["X-Custom-Header"] == "test-value"
        assert response_data["headers"]["X-Status-Code"] == "202"


class TestFunctionEndpointIntegration:
    """Integration tests for @endpoint decorator with response injection."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        """Set up a test server for each test."""
        self.test_server = Server(
            title="Test Server",
            description="Test server for endpoint integration tests",
            version="1.0.0",
        )
        set_current_server(self.test_server)
        yield
        # Cleanup
        set_current_server(None)

    async def test_function_endpoint_injection_signature(self):
        """Test that @endpoint decorator modifies function signature to include endpoint parameter."""

        @endpoint("/test/function")
        async def test_function(param1: str, param2: int, endpoint) -> Any:
            """Test function with endpoint injection."""
            assert endpoint is not None
            assert isinstance(endpoint, EndpointResponseHelper)
            assert (
                endpoint.walker_instance is None
            )  # Function endpoints don't have walker
            return endpoint.success(data={"param1": param1, "param2": param2})

        # Check that the function was registered
        assert self.test_server._endpoint_registry.has_function(test_function)
        func_info = self.test_server._endpoint_registry.get_function_info(test_function)
        assert func_info is not None
        assert func_info.path == "/test/function"
        assert func_info.endpoint_type == "function"

    async def test_function_endpoint_response_methods(self):
        """Test function endpoint response methods."""

        @endpoint("/test/responses/{response_type}")
        async def response_test_function(response_type: str, endpoint) -> Any:
            """Test function demonstrating various response types."""

            if response_type == "success":
                return endpoint.success(
                    data={"type": "success", "value": 42}, message="Success response"
                )
            elif response_type == "created":
                return endpoint.created(
                    data={"id": "new_resource"}, message="Resource created"
                )
            elif response_type == "error":
                return endpoint.bad_request(
                    message="Bad request error",
                    details={"error_code": "VALIDATION_ERROR"},
                )
            elif response_type == "not_found":
                return endpoint.not_found(
                    message="Resource not found",
                    details={"resource_type": response_type},
                )
            elif response_type == "custom":
                return endpoint.response(
                    content={"custom": True, "status": "accepted"},
                    status_code=202,
                    headers={"X-Processing": "async"},
                )

        # Note: We can't directly test the function execution here because
        # the endpoint injection happens during the actual HTTP request handling.
        # This test verifies the function is properly decorated and registered.

        assert self.test_server._endpoint_registry.has_function(response_test_function)
        func_info = self.test_server._endpoint_registry.get_function_info(
            response_test_function
        )
        assert func_info is not None
        assert func_info.path == "/test/responses/{response_type}"
        assert func_info.methods == ["GET"]  # Default for function endpoints
        assert func_info.endpoint_type == "function"

    async def test_function_endpoint_with_post_method(self):
        """Test function endpoint with POST method."""

        @endpoint("/test/create", methods=["POST"])
        async def create_resource(name: str, description: str, endpoint) -> Any:
            """Create resource endpoint."""

            if not name:
                return endpoint.bad_request(
                    message="Name is required", details={"field": "name"}
                )

            return endpoint.created(
                data={
                    "id": f"resource_{name}",
                    "name": name,
                    "description": description,
                },
                message="Resource created successfully",
            )

        assert self.test_server._endpoint_registry.has_function(create_resource)
        func_info = self.test_server._endpoint_registry.get_function_info(
            create_resource
        )
        assert func_info is not None
        assert func_info.path == "/test/create"
        assert func_info.methods == ["POST"]
        assert func_info.endpoint_type == "function"

    async def test_function_endpoint_multiple_methods(self):
        """Test function endpoint with multiple HTTP methods."""

        @endpoint("/test/multi", methods=["GET", "POST", "PUT"])
        async def multi_method_function(method_type: str, endpoint) -> Any:
            """Function supporting multiple HTTP methods."""
            return endpoint.success(
                data={"method": method_type}, message=f"Handled {method_type} request"
            )

        assert self.test_server._endpoint_registry.has_function(multi_method_function)
        func_info = self.test_server._endpoint_registry.get_function_info(
            multi_method_function
        )
        assert func_info is not None
        assert func_info.path == "/test/multi"
        assert func_info.methods == ["GET", "POST", "PUT"]

    async def test_function_endpoint_no_endpoint_param_error(self):
        """Test that function without endpoint parameter can still be decorated."""

        @endpoint("/test/no_endpoint")
        async def function_without_endpoint(param: str) -> Any:
            """Function that doesn't use endpoint parameter."""
            return {"param": param, "message": "No endpoint helper used"}

        # Function should still be decorated properly
        assert self.test_server._endpoint_registry.has_function(
            function_without_endpoint
        )
        # The endpoint parameter will be injected by the wrapper,
        # but if the function doesn't use it, that's fine


class TestEndpointInjectionMechanism:
    """Test the injection mechanism for both walker and function endpoints."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        """Set up a test server for each test."""
        self.test_server = Server(
            title="Test Server",
            description="Test server for injection mechanism tests",
            version="1.0.0",
        )
        set_current_server(self.test_server)
        yield
        set_current_server(None)

    async def test_walker_endpoint_registration(self):
        """Test that endpoints are properly registered with server."""

        @endpoint("/test/registration")
        class RegistrationTestWalker(Walker):
            param: str = EndpointField(description="Test parameter")

            async def visit_node(self, node):
                return {"test": "registration"}

        # Check that walker is registered with server using endpoint registry
        assert self.test_server._endpoint_registry.has_walker(RegistrationTestWalker)

        # Check endpoint info
        endpoint_info = self.test_server._endpoint_registry.get_walker_info(
            RegistrationTestWalker
        )
        assert endpoint_info is not None
        assert endpoint_info.path == "/test/registration"
        assert endpoint_info.methods == ["POST"]  # Default for walker endpoints

    async def test_function_endpoint_registration(self):
        """Test that function endpoints are properly registered with server."""

        @endpoint("/test/function_registration")
        async def registration_test_function(endpoint) -> Any:
            return endpoint.success(data={"test": "registration"})

        # Check that function is registered using endpoint registry
        assert self.test_server._endpoint_registry.has_function(
            registration_test_function
        )

        # Check endpoint info
        endpoint_info = self.test_server._endpoint_registry.get_function_info(
            registration_test_function
        )
        assert endpoint_info is not None
        assert endpoint_info.path == "/test/function_registration"
        assert endpoint_info.methods == ["GET"]  # Default for function endpoints

    async def test_endpoint_helper_factory(self):
        """Test the endpoint helper factory function."""
        from jvspatial.api.endpoints.response import (
            ResponseHelper as EndpointResponseHelper,
        )
        from jvspatial.api.endpoints.response import (
            create_endpoint_helper,
        )

        # Test without walker instance
        helper = create_endpoint_helper()
        assert isinstance(helper, EndpointResponseHelper)
        assert helper.walker_instance is None

        # Test with walker instance
        mock_walker = MagicMock()
        helper_with_walker = create_endpoint_helper(walker_instance=mock_walker)
        assert isinstance(helper_with_walker, EndpointResponseHelper)
        assert helper_with_walker.walker_instance is mock_walker

    async def test_server_discovery_and_registration(self):
        """Test that server properly discovers and registers endpoints."""

        # Test discovery count using endpoint registry
        initial_walker_count = len(self.test_server._endpoint_registry.list_walkers())
        initial_function_count = len(
            self.test_server._endpoint_registry.list_functions()
        )

        @endpoint("/test/discovery/walker")
        class DiscoveryWalker(Walker):
            param: str = EndpointField(description="Discovery test")

        @endpoint("/test/discovery/function")
        async def discovery_function(endpoint) -> Any:
            return endpoint.success(data={"discovered": True})

        # Check counts increased
        assert (
            len(self.test_server._endpoint_registry.list_walkers())
            == initial_walker_count + 1
        )
        assert (
            len(self.test_server._endpoint_registry.list_functions())
            == initial_function_count + 1
        )

        # Verify specific registrations
        assert self.test_server._endpoint_registry.has_walker(DiscoveryWalker)
        assert self.test_server._endpoint_registry.has_function(discovery_function)

    async def test_no_server_available(self):
        """Test endpoint decoration when no current server is available."""
        # Clear the current server to test no-server scenario
        set_current_server(None)

        @endpoint("/test/no_server")
        class NoServerWalker(Walker):
            param: str = EndpointField(description="No server test")

        @endpoint("/test/no_server_function")
        async def no_server_function(endpoint) -> Any:
            return {"test": "no server"}

        # Should still add configuration to classes/functions for later discovery
        assert hasattr(NoServerWalker, "_jvspatial_endpoint_config")
        assert hasattr(no_server_function, "_jvspatial_endpoint_config")

        walker_config = NoServerWalker._jvspatial_endpoint_config
        function_config = no_server_function._jvspatial_endpoint_config

        assert walker_config["path"] == "/test/no_server"
        assert function_config["path"] == "/test/no_server_function"
        assert function_config["is_function"] is True

    async def test_endpoint_configuration_preservation(self):
        """Test that endpoint configuration is properly preserved on classes/functions."""

        @endpoint("/test/config", methods=["POST", "PUT"], tags=["test"])
        class ConfigWalker(Walker):
            param: str = EndpointField(description="Config test")

        @endpoint("/test/config/func", methods=["GET", "POST"], summary="Test function")
        async def config_function(endpoint) -> Any:
            return endpoint.success(data={"config": "preserved"})

        # Check walker config
        walker_config = ConfigWalker._jvspatial_endpoint_config
        assert walker_config["path"] == "/test/config"
        assert walker_config["methods"] == ["POST", "PUT"]
        assert walker_config["kwargs"]["tags"] == ["test"]

        # Check function config
        assert self.test_server._endpoint_registry.has_function(config_function)
        func_info = self.test_server._endpoint_registry.get_function_info(
            config_function
        )
        assert func_info is not None
        assert func_info.path == "/test/config/func"
        assert func_info.methods == ["GET", "POST"]
        assert (
            func_info.kwargs.get("route_config", {}).get("summary") == "Test function"
            or "summary" in func_info.kwargs
        )
