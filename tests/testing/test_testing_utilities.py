"""Test suite for testing utilities.

Tests the new testing framework:
- JVSpatialTestClient
- Test fixtures
- Performance testing utilities
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.core.entities import Edge, Node, Object, Walker
from jvspatial.testing import JVSpatialTestClient, test_context, test_server


class TestJVSpatialTestClient:
    """Test JVSpatialTestClient functionality."""

    @pytest.fixture
    def mock_server(self):
        """Create mock server for testing."""
        server = MagicMock()
        server.app = MagicMock()
        return server

    @pytest.fixture
    def test_client(self, mock_server):
        """Create JVSpatialTestClient instance for testing."""
        return JVSpatialTestClient(mock_server)

    async def test_test_client_initialization(self, test_client, mock_server):
        """Test JVSpatialTestClient initialization."""
        assert test_client.server == mock_server
        assert test_client.client is not None
        assert test_client._test_data == []

    async def test_create_test_entity(self, test_client):
        """Test creating test entities."""
        # Mock entity creation
        with patch("jvspatial.testing.create_entity") as mock_create:
            mock_create.return_value = {"id": "test_id", "type": "Node"}

            entity = await test_client.create_test_entity(Node, name="test")

            assert entity["id"] == "test_id"
            assert entity["type"] == "Node"
            assert len(test_client._test_data) == 1

    async def test_cleanup_test_data(self, test_client):
        """Test cleaning up test data."""
        # Add some test data
        test_client._test_data = [
            {"id": "test1", "type": "Node"},
            {"id": "test2", "type": "Edge"},
        ]

        # Cleanup
        await test_client.cleanup_test_data()

        # Verify cleanup
        assert len(test_client._test_data) == 0

    async def test_create_multiple_entities(self, test_client):
        """Test creating multiple test entities."""
        # Mock entity creation
        with patch("jvspatial.testing.create_entity") as mock_create:
            mock_create.side_effect = [
                {"id": "node1", "type": "Node"},
                {"id": "edge1", "type": "Edge"},
                {"id": "walker1", "type": "Walker"},
            ]

            # Create multiple entities
            node = await test_client.create_test_entity(Node, name="node1")
            edge = await test_client.create_test_entity(
                Edge, source="node1", target="node2"
            )
            walker = await test_client.create_test_entity(Walker, name="walker1")

            # Verify all entities were created
            assert len(test_client._test_data) == 3
            assert node["id"] == "node1"
            assert edge["id"] == "edge1"
            assert walker["id"] == "walker1"


class TestTestFixtures:
    """Test test fixtures functionality."""

    @pytest.mark.asyncio
    async def test_test_context_fixture(self, test_context):
        """Test test_context fixture."""
        # Use the fixture as parameter
        assert test_context is not None
        assert hasattr(test_context, "enable_performance_monitoring")

    @pytest.mark.asyncio
    async def test_test_server_fixture(self, test_server):
        """Test test_server fixture."""
        # Use the fixture as parameter
        assert test_server is not None
        assert hasattr(test_server, "config")
        assert hasattr(test_server.config, "title")
        assert hasattr(test_server, "app")

    @pytest.mark.asyncio
    async def test_fixtures_cleanup(self, test_context, test_server):
        """Test that fixtures properly clean up."""
        # Test context cleanup
        assert test_context is not None

        # Test server cleanup
        assert test_server is not None
        # Fixtures should be cleaned up automatically by pytest


class TestPerformanceTesting:
    """Test performance testing utilities."""

    async def test_performance_measurement(self):
        """Test performance measurement utilities."""
        from jvspatial.testing import measure_performance

        # Test performance measurement
        async def test_operation():
            await asyncio.sleep(0.01)  # Simulate work
            return "result"

        result, duration = await measure_performance(test_operation)

        assert result == "result"
        assert duration > 0
        assert duration < 1.0  # Should be less than 1 second

    async def test_performance_comparison(self):
        """Test performance comparison utilities."""
        from jvspatial.testing import compare_performance

        # Test performance comparison
        async def fast_operation():
            await asyncio.sleep(0.001)
            return "fast"

        async def slow_operation():
            await asyncio.sleep(0.01)
            return "slow"

        comparison = await compare_performance(fast_operation, slow_operation)

        assert "fast_duration" in comparison
        assert "slow_duration" in comparison
        assert "speedup_ratio" in comparison
        assert comparison["fast_duration"] < comparison["slow_duration"]

    async def test_memory_usage_tracking(self):
        """Test memory usage tracking."""
        from jvspatial.testing import track_memory_usage

        # Test memory tracking
        async def memory_intensive_operation():
            # Create some data
            data = [i for i in range(1000)]
            return data

        memory_stats = await track_memory_usage(memory_intensive_operation)

        assert "peak_memory" in memory_stats
        assert "final_memory" in memory_stats
        assert "memory_delta" in memory_stats


class TestTestingUtilities:
    """Test general testing utilities."""

    async def test_mock_entity_creation(self):
        """Test mock entity creation utilities."""
        from jvspatial.testing import create_mock_entity

        # Test mock entity creation
        mock_node = await create_mock_entity(Node, name="test", value=42)

        assert mock_node.name == "test"
        assert mock_node.value == 42
        assert hasattr(mock_node, "id")

    async def test_test_data_generation(self):
        """Test test data generation utilities."""
        from jvspatial.testing import generate_test_data

        # Test data generation
        test_data = await generate_test_data("node", count=5, name="test", value=42)

        assert len(test_data) == 5
        for item in test_data:
            assert hasattr(item, "id")
            assert hasattr(item, "name")
            assert hasattr(item, "value")

    async def test_assertion_helpers(self):
        """Test assertion helper utilities."""
        from jvspatial.testing import assert_entity_valid, assert_graph_consistent

        # Test entity validation
        node = Node(name="test", value=42)
        assert_entity_valid(node)

        # Test graph consistency
        context = MagicMock()  # Mock GraphContext
        assert_graph_consistent(context)

    async def test_test_isolation(self):
        """Test test isolation utilities."""
        from jvspatial.testing import isolated_test_context

        # Test isolation
        async with isolated_test_context() as ctx:
            # Create some test data
            node = await ctx.create_test_entity("Node", name="isolated")
            assert node.name == "isolated"

        # Context should be cleaned up
        # (exact verification depends on implementation)


class TestTestingIntegration:
    """Test testing framework integration."""

    async def test_full_test_workflow(self):
        """Test complete testing workflow."""
        # Create test client
        server = MagicMock()
        test_client = JVSpatialTestClient(server)

        # Create test entities
        node = await test_client.create_test_entity("Node", name="test")
        edge = await test_client.create_test_entity(
            "Edge", source=node.id, target="target"
        )

        # Verify entities
        assert node.name == "test"
        assert edge.source == node.id

        # Cleanup
        await test_client.cleanup_test_data()
        assert len(test_client._test_data) == 0

    async def test_performance_testing_workflow(self):
        """Test performance testing workflow."""
        from jvspatial.testing import performance_test

        # Test performance testing decorator
        @performance_test()
        async def test_operation():
            await asyncio.sleep(0.01)
            return "result"

        # Run performance test
        result = await test_operation()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_integration_testing_workflow(self, test_context):
        """Test integration testing workflow."""
        from jvspatial.testing import integration_test

        # Test integration testing decorator
        @integration_test()
        async def test_integration():
            # Test full integration using the fixture parameter
            assert test_context is not None
            # Create a mock node for testing
            from jvspatial.testing import create_entity

            node = await create_entity("Node", name="integration_test")
            assert node.name == "integration_test"

        # Run integration test
        await test_integration()
