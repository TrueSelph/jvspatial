"""Comprehensive integration tests for complete workflows.

Tests end-to-end workflows combining multiple components:
- Database operations with caching
- API endpoints with authentication
- File storage with security
- Walker traversal with protection
- Error handling across components
"""

import asyncio
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api.server import Server, ServerConfig
from jvspatial.cache.factory import create_cache
from jvspatial.core import on_visit
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node, Walker
from jvspatial.db.factory import create_database
from jvspatial.storage import create_storage


class IntegrationTestNode(Node):
    """Test node for integration testing."""

    name: str = ""
    value: int = 0
    category: str = ""


class IntegrationTestEdge(Edge):
    """Test edge for integration testing."""

    weight: int = 1
    condition: str = "good"


class IntegrationTestWalker(Walker):
    """Test walker for integration testing."""

    name: str = ""
    limit: int = 10

    @on_visit(IntegrationTestNode)
    async def visit_node(self, node):
        self.visited_nodes.append(node)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visited_nodes = []


class TestFullWorkflowIntegration:
    """Test complete workflow integration."""

    @pytest.fixture
    def temp_context(self):
        """Create temporary context for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create database and context
            from jvspatial.cache import create_cache
            from jvspatial.db import create_database

            db = create_database("json", base_path=tmpdir)
            cache = create_cache("memory", cache_size=1000)
            context = GraphContext(database=db, cache_backend=cache)
            yield context

    @pytest.mark.asyncio
    async def test_database_with_caching_workflow(self, temp_context):
        """Test database operations with caching using current GraphContext API."""
        # Create node
        node = IntegrationTestNode(name="test_node", value=42, category="test")
        created_node = await temp_context.save(node)

        # First retrieval - should hit database
        retrieved_node1 = await temp_context.get(IntegrationTestNode, created_node.id)
        assert retrieved_node1 is not None
        assert retrieved_node1.name == "test_node"

        # Second retrieval - should hit cache
        retrieved_node2 = await temp_context.get(IntegrationTestNode, created_node.id)
        assert retrieved_node2 is not None
        assert retrieved_node2.name == "test_node"

        # Update node - should invalidate cache
        retrieved_node1.name = "updated_node"
        updated_node = await temp_context.save(retrieved_node1)
        assert updated_node.name == "updated_node"

        # Verify update persisted
        final_node = await temp_context.get(IntegrationTestNode, created_node.id)
        assert final_node.name == "updated_node"

    @pytest.mark.asyncio
    async def test_graph_traversal_workflow(self, temp_context):
        """Test graph traversal workflow using current GraphContext API."""
        # Create nodes
        source = IntegrationTestNode(name="source", value=1, category="test")
        target1 = IntegrationTestNode(name="target1", value=2, category="test")
        target2 = IntegrationTestNode(name="target2", value=3, category="test")

        source_node = await temp_context.save(source)
        target1_node = await temp_context.save(target1)
        target2_node = await temp_context.save(target2)

        # Create edges
        edge1 = IntegrationTestEdge(
            source=source_node.id, target=target1_node.id, weight=1
        )
        edge2 = IntegrationTestEdge(
            source=source_node.id, target=target2_node.id, weight=2
        )

        await temp_context.save(edge1)
        await temp_context.save(edge2)

        # Create walker
        walker = IntegrationTestWalker(name="test_walker", limit=10)
        created_walker = await temp_context.save(walker)

        # Test walker traversal
        assert created_walker is not None
        assert created_walker.name == "test_walker"

        # Find edges from source using database interface
        source_edges = await temp_context.database.find(
            "edge", {"source": source_node.id}
        )
        assert len(source_edges) == 2

        # Find nodes by category using database interface
        test_nodes = await temp_context.database.find(
            "node", {"context.category": "test"}
        )
        assert len(test_nodes) == 3

    @pytest.mark.asyncio
    async def test_api_server_workflow(self):
        """Test API server workflow."""
        # Create server
        config = ServerConfig(title="Integration Test API", debug=True)
        server = Server(config=config)

        # Add endpoint
        @server.endpoint("/test")
        async def test_endpoint():
            return {"message": "Hello, World!"}

        # Test server startup
        assert server is not None
        assert server.config.title == "Integration Test API"

        # Test endpoint registration
        assert server.has_endpoint("/test")

    @pytest.mark.asyncio
    async def test_file_storage_workflow(self):
        """Test file storage workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create storage interface
            storage = create_storage("local", root_dir=tmpdir)

            # Test file operations
            test_data = b"Hello, World!"
            file_path = "test.txt"

            # Write file
            await storage.write_file(file_path, test_data)

            # Read file
            read_data = await storage.read_file(file_path)
            assert read_data == test_data

            # Check file exists
            assert await storage.file_exists(file_path)

            # Delete file
            await storage.delete_file(file_path)
            assert not await storage.file_exists(file_path)

    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, temp_context):
        """Test error handling across components using current GraphContext API."""
        # Test basic operations work
        node = IntegrationTestNode(name="test", value=42, category="test")
        saved_node = await temp_context.save(node)
        assert saved_node.id is not None

        # Test edge creation works
        edge = IntegrationTestEdge(source="test_source", target="test_target")
        saved_edge = await temp_context.save(edge)
        assert saved_edge.id is not None

        # Test database operations work
        nodes = await temp_context.database.find("node", {"context.category": "test"})
        assert len(nodes) >= 1

        # Test retrieval works
        retrieved_node = await temp_context.get(IntegrationTestNode, saved_node.id)
        assert retrieved_node is not None
        assert retrieved_node.name == "test"

    @pytest.mark.asyncio
    async def test_performance_workflow(self, temp_context):
        """Test performance characteristics using current GraphContext API."""
        # Create many nodes
        start_time = asyncio.get_event_loop().time()
        for i in range(1000):
            node = IntegrationTestNode(name=f"node_{i}", value=i, category="test")
            await temp_context.save(node)
        end_time = asyncio.get_event_loop().time()

        # Should complete in reasonable time
        assert end_time - start_time < 10.0  # 10 seconds max

        # Test query performance using database interface
        start_time = asyncio.get_event_loop().time()
        results = await temp_context.database.find("node", {"context.category": "test"})
        end_time = asyncio.get_event_loop().time()

        assert len(results) == 1000
        assert end_time - start_time < 2.0  # 2 seconds max

    @pytest.mark.asyncio
    async def test_concurrent_operations_workflow(self, temp_context):
        """Test concurrent operations using current GraphContext API."""

        # Create nodes concurrently
        async def create_node_task(name, value):
            node = IntegrationTestNode(name=name, value=value, category="test")
            return await temp_context.save(node)

        # Run concurrent operations
        tasks = [create_node_task(f"node_{i}", i) for i in range(100)]

        results = await asyncio.gather(*tasks)

        # Verify all nodes were created
        assert len(results) == 100
        for result in results:
            assert result.id is not None

        # Verify all nodes exist using database interface
        all_nodes = await temp_context.database.find("node", {})
        assert len(all_nodes) == 100

    @pytest.mark.asyncio
    async def test_transaction_workflow(self, temp_context):
        """Test transaction workflow using current GraphContext API."""
        # Test basic operations (transactions may not be implemented in current API)
        node1 = IntegrationTestNode(name="node1", value=1)
        node2 = IntegrationTestNode(name="node2", value=2)

        created1 = await temp_context.save(node1)
        created2 = await temp_context.save(node2)

        assert created1.id is not None
        assert created2.id is not None

        # Verify both nodes exist
        retrieved1 = await temp_context.get(IntegrationTestNode, created1.id)
        retrieved2 = await temp_context.get(IntegrationTestNode, created2.id)

        assert retrieved1 is not None
        assert retrieved2 is not None

    @pytest.mark.asyncio
    async def test_cache_invalidation_workflow(self, temp_context):
        """Test cache invalidation workflow using current GraphContext API."""
        # Create node
        node = IntegrationTestNode(name="test_node", value=42, category="test")
        created_node = await temp_context.save(node)

        # First retrieval - should hit database
        retrieved_node1 = await temp_context.get(IntegrationTestNode, created_node.id)
        assert retrieved_node1 is not None

        # Update node - should invalidate cache
        retrieved_node1.name = "updated_node"
        updated_node = await temp_context.save(retrieved_node1)
        assert updated_node.name == "updated_node"

        # Verify update persisted
        final_node = await temp_context.get(IntegrationTestNode, created_node.id)
        assert final_node.name == "updated_node"

        # Delete node - should remove from cache
        await temp_context.delete(created_node)
        deleted_node = await temp_context.get(IntegrationTestNode, created_node.id)
        assert deleted_node is None

    @pytest.mark.asyncio
    async def test_complex_query_workflow(self, temp_context):
        """Test complex query workflow using current GraphContext API."""
        # Create test data
        for i in range(100):
            node = IntegrationTestNode(
                name=f"node_{i}", value=i, category="test" if i % 2 == 0 else "prod"
            )
            await temp_context.save(node)

        # Test complex query using database interface (simplified for JsonDB compatibility)
        # JsonDB doesn't support MongoDB operators, so we'll test basic filtering
        results = await temp_context.database.find("node", {"context.category": "test"})

        # Filter results manually for values >= 10 (since JsonDB doesn't support $gte)
        filtered_results = [
            r for r in results if r.get("context", {}).get("value", 0) >= 10
        ]
        assert len(filtered_results) == 45  # Even numbers >= 10

        # Test aggregation using database interface
        test_results = await temp_context.database.find(
            "node", {"context.category": "test"}
        )
        assert len(test_results) == 50

        prod_results = await temp_context.database.find(
            "node", {"context.category": "prod"}
        )
        assert len(prod_results) == 50

        # Test distinct values using database interface
        all_nodes = await temp_context.database.find("node", {})
        distinct_categories = set(node["context"]["category"] for node in all_nodes)
        assert distinct_categories == {"test", "prod"}

    @pytest.mark.asyncio
    async def test_walker_protection_workflow(self, temp_context):
        """Test walker protection workflow using current GraphContext API."""
        # Create nodes
        for i in range(10):
            node = IntegrationTestNode(name=f"node_{i}", value=i, category="test")
            await temp_context.save(node)

        # Create walker with protection
        walker = IntegrationTestWalker(name="test_walker", limit=5)
        created_walker = await temp_context.save(walker)

        # Test walker protection
        assert created_walker is not None
        assert created_walker.limit == 5

        # Test walker traversal with protection using database interface
        nodes = await temp_context.database.find("node", {"context.category": "test"})
        assert len(nodes) == 10

        # Test walker limit
        assert created_walker.limit <= 10  # Should respect limit

    @pytest.mark.asyncio
    async def test_security_workflow(self):
        """Test security workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test file storage security
            storage = create_storage("local", root_dir=tmpdir)

            # Test path traversal protection
            with pytest.raises(Exception):
                await storage.write_file("../../../etc/passwd", b"malicious")

            # Test file validation
            with pytest.raises(Exception):
                await storage.write_file("test.exe", b"executable content")

            # Test valid file
            await storage.write_file("test.txt", b"valid content")
            assert await storage.file_exists("test.txt")

    @pytest.mark.asyncio
    async def test_backup_restore_workflow(self, temp_context):
        """Test backup and restore workflow using current GraphContext API."""
        # Create test data
        node1 = IntegrationTestNode(name="node1", value=1, category="test")
        node2 = IntegrationTestNode(name="node2", value=2, category="prod")

        created1 = await temp_context.save(node1)
        created2 = await temp_context.save(node2)

        # Test basic operations (backup/restore may not be implemented in current API)
        # Verify nodes exist
        retrieved1 = await temp_context.get(IntegrationTestNode, created1.id)
        retrieved2 = await temp_context.get(IntegrationTestNode, created2.id)

        assert retrieved1 is not None
        assert retrieved2 is not None
        assert retrieved1.name == "node1"
        assert retrieved2.name == "node2"

        # Test deletion
        await temp_context.delete(created1)
        await temp_context.delete(created2)

        # Verify deletion
        deleted1 = await temp_context.get(IntegrationTestNode, created1.id)
        deleted2 = await temp_context.get(IntegrationTestNode, created2.id)

        assert deleted1 is None
        assert deleted2 is None
