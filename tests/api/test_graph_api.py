"""
Tests for GraphAPI endpoint registration and execution.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from pydantic import ValidationError

from jvspatial.api.api import GraphAPI
from jvspatial.core.entities import Walker, Node, RootNode, on_visit, on_exit


class TestNode(Node):
    """Test node for API testing"""
    name: str = "TestNode"


class TestGraphAPIBasics:
    """Test basic GraphAPI functionality"""
    
    def test_graph_api_initialization(self):
        """Test GraphAPI initialization"""
        api = GraphAPI()
        
        assert hasattr(api, 'router')
        assert api.router is not None

    def test_endpoint_decorator_registration(self):
        """Test endpoint decorator registration"""
        api = GraphAPI()
        
        @api.endpoint("/test", methods=["POST"])
        class TestWalker(Walker):
            @on_visit(RootNode)
            async def on_root(self, here):
                self.response["test"] = "success"
        
        # Check that route was added
        routes = api.router.routes
        assert len(routes) >= 1
        
        # Find our test route
        test_route = None
        for route in routes:
            if hasattr(route, 'path') and route.path == "/test":
                test_route = route
                break
        
        assert test_route is not None
        assert "POST" in test_route.methods


class TestWalkerExecution:
    """Test walker execution through API endpoints"""
    
    @pytest.mark.asyncio
    async def test_simple_walker_execution(self):
        """Test simple walker execution"""
        api = GraphAPI()
        
        @api.endpoint("/simple", methods=["POST"])
        class SimpleWalker(Walker):
            @on_visit(RootNode)
            async def on_root(self, here):
                self.response["status"] = "visited_root"
                self.response["node_id"] = here.id
        
        # Get the handler function
        routes = api.router.routes
        handler = None
        for route in routes:
            if hasattr(route, 'path') and route.path == "/simple":
                handler = route.endpoint
                break
        
        assert handler is not None
        
        # Execute handler
        request_data = {}
        result = await handler(request_data)
        
        assert "status" in result
        assert result["status"] == "visited_root"
        assert "node_id" in result

    @pytest.mark.asyncio
    async def test_walker_with_parameters(self):
        """Test walker execution with parameters"""
        api = GraphAPI()
        
        @api.endpoint("/parameterized", methods=["POST"])
        class ParameterizedWalker(Walker):
            name: str = "default"
            count: int = 1
            
            @on_visit(RootNode)
            async def on_root(self, here):
                self.response["name"] = self.name
                self.response["count"] = self.count
        
        # Get handler
        routes = api.router.routes
        handler = None
        for route in routes:
            if hasattr(route, 'path') and route.path == "/parameterized":
                handler = route.endpoint
                break
        
        assert handler is not None
        
        # Execute with parameters
        request_data = {"name": "test_walker", "count": 5}
        result = await handler(request_data)
        
        assert result["name"] == "test_walker"
        assert result["count"] == 5


class TestErrorHandling:
    """Test error handling in API endpoints"""
    
    @pytest.mark.asyncio
    async def test_validation_error_handling(self):
        """Test handling of Pydantic validation errors"""
        api = GraphAPI()
        
        @api.endpoint("/validation", methods=["POST"])
        class ValidationWalker(Walker):
            required_field: str  # Required field
            number_field: int = 0
        
        # Get handler
        routes = api.router.routes
        handler = None
        for route in routes:
            if hasattr(route, 'path') and route.path == "/validation":
                handler = route.endpoint
                break
        
        assert handler is not None
        
        # Test with missing required field
        with pytest.raises(HTTPException) as exc_info:
            await handler({"number_field": 42})  # Missing required_field
        
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_walker_execution_error(self):
        """Test handling of errors during walker execution"""
        api = GraphAPI()
        
        @api.endpoint("/error", methods=["POST"])
        class ErrorWalker(Walker):
            @on_visit(RootNode)
            async def on_root(self, here):
                raise RuntimeError("Test error")
        
        # Get handler
        routes = api.router.routes
        handler = None
        for route in routes:
            if hasattr(route, 'path') and route.path == "/error":
                handler = route.endpoint
                break
        
        assert handler is not None
        
        # Execute should raise HTTPException with 500 status
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await handler({})
        
        # Should be a 500 error
        assert exc_info.value.status_code == 500


class TestComplexWalkers:
    """Test complex walker scenarios"""
    
    @pytest.mark.asyncio
    async def test_multi_node_traversal(self):
        """Test walker that traverses multiple nodes"""
        api = GraphAPI()
        
        @api.endpoint("/traversal", methods=["POST"])
        class TraversalWalker(Walker):
            @on_visit(RootNode)
            async def on_root(self, here):
                if "visited_nodes" not in self.response:
                    self.response["visited_nodes"] = []
                self.response["visited_nodes"].append("root")
                
                # Create and visit test nodes
                node1 = await TestNode.create(name="Node1")
                node2 = await TestNode.create(name="Node2")
                await here.connect(node1)
                await here.connect(node2)
                await self.visit([node1, node2])
            
            @on_visit(TestNode)
            async def on_test_node(self, here):
                if "visited_nodes" not in self.response:
                    self.response["visited_nodes"] = []
                self.response["visited_nodes"].append(here.name)
        
        # Get handler
        routes = api.router.routes
        handler = None
        for route in routes:
            if hasattr(route, 'path') and route.path == "/traversal":
                handler = route.endpoint
                break
        
        assert handler is not None
        
        # Execute traversal
        result = await handler({})
        
        visited = result.get("visited_nodes", [])
        assert "root" in visited
        assert "Node1" in visited
        assert "Node2" in visited
        assert len(visited) == 3