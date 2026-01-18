"""Tests for WalkerExecutor component."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.api.endpoints.router import EndpointRouter
from jvspatial.api.endpoints.walker_executor import (
    DirectExecutionWalker,
    WalkerExecutor,
)
from jvspatial.core.entities import Node, Walker


class MockDirectExecutionWalker(Walker):
    """Test walker implementing direct execution protocol."""

    async def execute(self):
        """Direct execution method."""
        return {"result": "direct_execution"}


class MockLegacyWalker(Walker):
    """Test walker using execute method (replaces legacy analyze_users pattern)."""

    async def execute(self):
        """Direct execution method."""
        return {"result": "legacy_method"}


class MockTraversalWalker(Walker):
    """Test walker for traditional graph traversal."""

    async def visit_node(self, node: Node):
        """Visit node during traversal."""
        await self.report({"visited": node.id})


class TestWalkerExecutor:
    """Test WalkerExecutor functionality."""

    @pytest.fixture
    def router(self):
        """Create mock router."""
        router = MagicMock(spec=EndpointRouter)

        def format_response(data=None, **kwargs):
            """Mock format_response that actually uses the data parameter."""
            return {"success": True, "data": data if data is not None else {}}

        router.format_response = MagicMock(side_effect=format_response)
        router.raise_error = MagicMock(side_effect=Exception("Test error"))
        return router

    @pytest.fixture
    def executor(self, router):
        """Create WalkerExecutor instance."""
        return WalkerExecutor(router)

    @pytest.mark.asyncio
    async def test_execute_direct_execution_walker(self, executor):
        """Test execution of walker implementing DirectExecutionWalker protocol."""
        walker = MockDirectExecutionWalker()
        walker_cls = MockDirectExecutionWalker

        result = await executor.execute_walker(walker, walker_cls)

        assert result == {"success": True, "data": {"result": "direct_execution"}}

    @pytest.mark.asyncio
    async def test_execute_method_walker(self, executor):
        """Test execution of walker with execute method."""
        walker = MockLegacyWalker()
        walker_cls = MockLegacyWalker

        result = await executor.execute_walker(walker, walker_cls)

        assert result == {"success": True, "data": {"result": "legacy_method"}}

    @pytest.mark.asyncio
    async def test_execute_traversal_walker(self, executor):
        """Test execution of traditional graph traversal walker."""
        walker = MockTraversalWalker()
        walker_cls = MockTraversalWalker

        # Mock graph context and node
        with patch(
            "jvspatial.api.endpoints.walker_executor.get_default_context"
        ) as mock_context:
            mock_ctx = MagicMock()
            mock_node = MagicMock(spec=Node)
            mock_node.id = "n.TestNode.test"
            mock_ctx.get = AsyncMock(return_value=mock_node)
            mock_context.return_value = mock_ctx

            # Mock walker spawn
            mock_result = MagicMock()
            mock_result.get_report = AsyncMock(
                return_value=[{"visited": "n.TestNode.test"}]
            )
            walker.spawn = AsyncMock(return_value=mock_result)

            result = await executor.execute_walker(walker, walker_cls, None)

            # Should format response with traversal results
            assert "success" in result or "data" in result
            walker.spawn.assert_called_once_with(mock_node)

    @pytest.mark.asyncio
    async def test_execute_traversal_walker_with_start_node(self, executor):
        """Test traversal walker with explicit start node."""
        walker = MockTraversalWalker()
        walker_cls = MockTraversalWalker

        with patch(
            "jvspatial.api.endpoints.walker_executor.get_default_context"
        ) as mock_context:
            mock_ctx = MagicMock()
            mock_node = MagicMock(spec=Node)
            mock_node.id = "n.CustomNode.custom"
            mock_ctx.get = AsyncMock(return_value=mock_node)
            mock_context.return_value = mock_ctx

            mock_result = MagicMock()
            mock_result.get_report = AsyncMock(
                return_value=[{"visited": "n.CustomNode.custom"}]
            )
            walker.spawn = AsyncMock(return_value=mock_result)

            result = await executor.execute_walker(
                walker, walker_cls, "n.CustomNode.custom"
            )

            # Should use provided start node
            mock_ctx.get.assert_called_once_with(Node, "n.CustomNode.custom")
            walker.spawn.assert_called_once_with(mock_node)

    @pytest.mark.asyncio
    async def test_execute_traversal_walker_start_node_not_found(self, executor):
        """Test error when start node is not found."""
        walker = MockTraversalWalker()
        walker_cls = MockTraversalWalker

        with patch(
            "jvspatial.api.endpoints.walker_executor.get_default_context"
        ) as mock_context:
            mock_ctx = MagicMock()
            mock_ctx.get = AsyncMock(return_value=None)
            mock_context.return_value = mock_ctx

            # Should raise error
            with pytest.raises(Exception, match="Test error"):
                await executor.execute_walker(
                    walker, walker_cls, "n.Nonexistent.missing"
                )

            executor.router.raise_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_response_schema(self, executor):
        """Test execution when response schema is defined."""
        walker = MockDirectExecutionWalker()
        walker_cls = MockDirectExecutionWalker

        # Mock response schema
        walker_cls._jvspatial_endpoint_config = {"response": MagicMock()}

        result = await executor.execute_walker(walker, walker_cls)

        # Should return result directly (not wrapped)
        assert result == {"result": "direct_execution"}

    @pytest.mark.asyncio
    async def test_execute_traversal_error_handling(self, executor):
        """Test error handling in traversal execution."""
        walker = MockTraversalWalker()
        walker_cls = MockTraversalWalker

        with patch(
            "jvspatial.api.endpoints.walker_executor.get_default_context"
        ) as mock_context:
            mock_ctx = MagicMock()
            mock_node = MagicMock(spec=Node)
            mock_ctx.get = AsyncMock(return_value=mock_node)
            mock_context.return_value = mock_ctx

            # Mock error report
            mock_result = MagicMock()
            mock_result.get_report = AsyncMock(
                return_value=[{"status": 404, "error": "Not found", "not_found": True}]
            )
            walker.spawn = AsyncMock(return_value=mock_result)

            # Should raise error
            with pytest.raises(Exception, match="Test error"):
                await executor.execute_walker(walker, walker_cls, None)

            executor.router.raise_error.assert_called_once()
