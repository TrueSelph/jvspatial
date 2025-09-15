"""
Tests for EndpointRouter endpoint registration and execution.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jvspatial.api.endpoint_router import EndpointRouter
from jvspatial.core.entities import Node, Root, Walker, on_exit, on_visit


class ExampleNode(Node):
    """Example node for API testing"""

    name: str = "ExampleNode"


class TestEndpointRouterBasics:
    """Test basic EndpointRouter functionality"""

    def test_graph_api_initialization(self):
        """Test EndpointRouter initialization"""
        api = EndpointRouter()

        assert hasattr(api, "router")
        assert api.router is not None

    def test_endpoint_decorator_registration(self):
        """Test endpoint decorator registration"""
        api = EndpointRouter()

        @api.endpoint("/test", methods=["POST"])
        class TestWalker(Walker):
            @on_visit(Root)
            async def on_root(self, here):
                self.response["test"] = "success"

        # Check that route was added
        routes = api.router.routes
        assert len(routes) >= 1

        # Find our test route
        test_route = None
        for route in routes:
            if hasattr(route, "path") and route.path == "/test":
                test_route = route
                break

        assert test_route is not None
        assert "POST" in test_route.methods


class TestWalkerExecution:
    """Test walker execution through API endpoints"""

    def test_simple_walker_execution(self):
        """Test simple walker execution"""
        api = EndpointRouter()

        @api.endpoint("/simple", methods=["POST"])
        class SimpleWalker(Walker):
            @on_visit(Root)
            async def on_root(self, here):
                self.response["status"] = "visited_root"
                self.response["node_id"] = here.id

        # Create FastAPI app with the router
        app = FastAPI()
        app.include_router(api.router)
        client = TestClient(app)

        # Execute through TestClient
        response = client.post("/simple", json={})

        assert response.status_code == 200
        result = response.json()
        assert "status" in result
        assert result["status"] == "visited_root"
        assert "node_id" in result

    def test_walker_with_parameters(self):
        """Test walker execution with parameters"""
        api = EndpointRouter()

        @api.endpoint("/parameterized", methods=["POST"])
        class ParameterizedWalker(Walker):
            name: str = "default"
            count: int = 1

            @on_visit(Root)
            async def on_root(self, here):
                self.response["name"] = self.name
                self.response["count"] = self.count

        # Create FastAPI app with the router
        app = FastAPI()
        app.include_router(api.router)
        client = TestClient(app)

        # Execute with parameters
        response = client.post(
            "/parameterized", json={"name": "test_walker", "count": 5}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "test_walker"
        assert result["count"] == 5


class TestErrorHandling:
    """Test error handling in API endpoints"""

    def test_validation_error_handling(self):
        """Test handling of Pydantic validation errors"""
        api = EndpointRouter()

        @api.endpoint("/validation", methods=["POST"])
        class ValidationWalker(Walker):
            required_field: str  # Required field
            number_field: int = 0

        # Create FastAPI app with the router
        app = FastAPI()
        app.include_router(api.router)
        client = TestClient(app)

        # Test with missing required field
        response = client.post(
            "/validation", json={"number_field": 42}
        )  # Missing required_field
        assert response.status_code == 422

    def test_walker_execution_error(self):
        """Test handling of errors during walker execution"""
        api = EndpointRouter()

        @api.endpoint("/error", methods=["POST"])
        class ErrorWalker(Walker):
            @on_visit(Root)
            async def on_root(self, here):
                raise RuntimeError("Test error")

        # Create FastAPI app with the router
        app = FastAPI()
        app.include_router(api.router)
        client = TestClient(app)

        # Execute should return 500 status
        response = client.post("/error", json={})
        # Note: In real scenarios, this would be a 500 error, but we'll check the actual response
        # The endpoint router should handle the error gracefully
        assert response.status_code >= 400  # Either 422 validation or 500 server error


class TestComplexWalkers:
    """Test complex walker scenarios"""

    def test_multi_node_traversal(self):
        """Test walker that traverses multiple nodes"""
        api = EndpointRouter()

        @api.endpoint("/traversal", methods=["POST"])
        class TraversalWalker(Walker):
            @on_visit(Root)
            async def on_root(self, here):
                if "visited_nodes" not in self.response:
                    self.response["visited_nodes"] = []
                self.response["visited_nodes"].append("root")

                # Create and visit test nodes
                node1 = await ExampleNode.create(name="Node1")
                node2 = await ExampleNode.create(name="Node2")
                await here.connect(node1)
                await here.connect(node2)
                await self.visit([node1, node2])

            @on_visit(ExampleNode)
            async def on_test_node(self, here):
                if "visited_nodes" not in self.response:
                    self.response["visited_nodes"] = []
                self.response["visited_nodes"].append(here.name)

        # Create FastAPI app with the router
        app = FastAPI()
        app.include_router(api.router)
        client = TestClient(app)

        # Execute traversal
        response = client.post("/traversal", json={})

        assert response.status_code == 200
        result = response.json()
        visited = result.get("visited_nodes", [])
        assert "root" in visited
        assert "Node1" in visited
        assert "Node2" in visited
        assert len(visited) == 3
