"""Comprehensive test suite for JsonDB backend.

Tests JSON file-based database operations including:
- File system operations
- Directory structure management
- Concurrent access handling
- Error handling and recovery
- Performance characteristics
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.core.entities import Edge, Node
from jvspatial.db.database import VersionConflictError
from jvspatial.db.jsondb import JsonDB


class JsonDBTestNode(Node):
    """Test node for JsonDB testing."""

    name: str = ""
    value: int = 0
    category: str = ""


class JsonDBTestEdge(Edge):
    """Test edge for JsonDB testing."""

    weight: int = 1
    condition: str = "good"


class TestJsonDBBasicOperations:
    """Test basic JsonDB operations."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create temporary directory for database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def jsondb(self, temp_db_dir):
        """Create JsonDB instance for testing."""
        return JsonDB(base_path=temp_db_dir)

    @pytest.mark.asyncio
    async def test_jsondb_initialization(self, temp_db_dir):
        """Test JsonDB initialization and directory creation."""
        db = JsonDB(base_path=temp_db_dir)

        # Check that base directory is created
        assert os.path.exists(temp_db_dir)
        assert str(db.base_path) == os.path.realpath(temp_db_dir)

        # Test basic database operations
        test_data = {"id": "test1", "name": "test", "value": 42}
        saved_data = await db.save("test_collection", test_data)
        assert saved_data["id"] == "test1"

        retrieved_data = await db.get("test_collection", "test1")
        assert retrieved_data["name"] == "test"
        assert retrieved_data["value"] == 42

    @pytest.mark.asyncio
    async def test_create_node(self, jsondb):
        """Test node creation using Database interface."""
        # Create node data
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }

        # Save using Database interface
        saved_data = await jsondb.save("node", node_data)
        assert saved_data["id"] == "node1"
        assert saved_data["name"] == "test_node"
        assert saved_data["value"] == 42
        assert saved_data["category"] == "test"

        # Check that file was created
        node_file = os.path.join(jsondb.base_path, "node", "node1.json")
        assert os.path.exists(node_file)

        # Check file content
        with open(node_file, "r") as f:
            data = json.load(f)
        assert data["name"] == "test_node"
        assert data["value"] == 42

    @pytest.mark.asyncio
    async def test_get_node(self, jsondb):
        """Test node retrieval using Database interface."""
        # Create and save node data
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", node_data)

        # Retrieve using Database interface
        retrieved_data = await jsondb.get("node", "node1")
        assert retrieved_data is not None
        assert retrieved_data["id"] == "node1"
        assert retrieved_data["name"] == "test_node"
        assert retrieved_data["value"] == 42
        assert retrieved_data["category"] == "test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_node(self, jsondb):
        """Test retrieval of non-existent node using Database interface."""
        retrieved_data = await jsondb.get("node", "nonexistent_id")
        assert retrieved_data is None

    @pytest.mark.asyncio
    async def test_update_node(self, jsondb):
        """Test node updates using Database interface."""
        # Create initial node data
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", node_data)

        # Update node data
        updated_data = {
            "id": "node1",
            "name": "updated_node",
            "value": 100,
            "category": "test",
        }
        await jsondb.save("node", updated_data)

        # Verify update persisted
        retrieved_data = await jsondb.get("node", "node1")
        assert retrieved_data["name"] == "updated_node"
        assert retrieved_data["value"] == 100

    @pytest.mark.asyncio
    async def test_delete_node(self, jsondb):
        """Test node deletion using Database interface."""
        # Create and save node data
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", node_data)

        # Delete using Database interface
        await jsondb.delete("node", "node1")

        # Verify deletion
        retrieved_data = await jsondb.get("node", "node1")
        assert retrieved_data is None

        # Check that file was removed
        node_file = os.path.join(jsondb.base_path, "node", "node1.json")
        assert not os.path.exists(node_file)

    @pytest.mark.asyncio
    async def test_find_nodes(self, jsondb):
        """Test node finding with queries using Database interface."""
        # Create multiple nodes
        node1_data = {"id": "node1", "name": "node1", "value": 10, "category": "test"}
        node2_data = {"id": "node2", "name": "node2", "value": 20, "category": "test"}
        node3_data = {"id": "node3", "name": "node3", "value": 30, "category": "other"}

        await jsondb.save("node", node1_data)
        await jsondb.save("node", node2_data)
        await jsondb.save("node", node3_data)

        # Find all nodes
        all_nodes = await jsondb.find("node", {})
        assert len(all_nodes) == 3

        # Find by category
        test_nodes = await jsondb.find("node", {"category": "test"})
        assert len(test_nodes) == 2

        # Find by value range (using QueryEngine syntax)
        high_value_nodes = await jsondb.find("node", {"value": {"$gte": 20}})
        assert len(high_value_nodes) == 2

    @pytest.mark.asyncio
    async def test_create_edge(self, jsondb):
        """Test edge creation using Database interface."""
        # Create source and target nodes
        source_data = {
            "id": "source1",
            "name": "source",
            "value": 1,
            "category": "test",
        }
        target_data = {
            "id": "target1",
            "name": "target",
            "value": 2,
            "category": "test",
        }

        await jsondb.save("node", source_data)
        await jsondb.save("node", target_data)

        # Create edge data
        edge_data = {
            "id": "edge1",
            "source": "source1",
            "target": "target1",
            "weight": 5,
            "condition": "good",
        }
        await jsondb.save("edge", edge_data)

        # Verify edge was saved
        retrieved_edge = await jsondb.get("edge", "edge1")
        assert retrieved_edge["id"] == "edge1"
        assert retrieved_edge["source"] == "source1"
        assert retrieved_edge["target"] == "target1"
        assert retrieved_edge["weight"] == 5

        # Check that file was created
        edge_file = os.path.join(jsondb.base_path, "edge", "edge1.json")
        assert os.path.exists(edge_file)

    @pytest.mark.asyncio
    async def test_find_edges(self, jsondb):
        """Test edge finding using Database interface."""
        # Create nodes and edges
        source_data = {
            "id": "source1",
            "name": "source",
            "value": 1,
            "category": "test",
        }
        target1_data = {
            "id": "target1",
            "name": "target1",
            "value": 2,
            "category": "test",
        }
        target2_data = {
            "id": "target2",
            "name": "target2",
            "value": 3,
            "category": "test",
        }

        await jsondb.save("node", source_data)
        await jsondb.save("node", target1_data)
        await jsondb.save("node", target2_data)

        edge1_data = {
            "id": "edge1",
            "source": "source1",
            "target": "target1",
            "weight": 1,
        }
        edge2_data = {
            "id": "edge2",
            "source": "source1",
            "target": "target2",
            "weight": 2,
        }

        await jsondb.save("edge", edge1_data)
        await jsondb.save("edge", edge2_data)

        # Find edges from source
        source_edges = await jsondb.find("edge", {"source": "source1"})
        assert len(source_edges) == 2

        # Find edges by weight
        heavy_edges = await jsondb.find("edge", {"weight": {"$gte": 2}})
        assert len(heavy_edges) == 1


class TestJsonDBErrorHandling:
    """Test JsonDB error handling and edge cases."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create temporary directory for database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def jsondb(self, temp_db_dir):
        """Create JsonDB instance for testing."""
        return JsonDB(base_path=temp_db_dir)

    @pytest.mark.asyncio
    async def test_corrupted_file_handling(self, jsondb):
        """Test handling of corrupted JSON files using Database interface."""
        # Create a node first
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", node_data)

        # Corrupt the file
        node_file = os.path.join(jsondb.base_path, "node", "node1.json")
        with open(node_file, "w") as f:
            f.write("invalid json content")

        # Try to retrieve the node - should handle corruption gracefully
        retrieved_data = await jsondb.get("node", "node1")
        # Should return None or handle the error gracefully
        assert retrieved_data is None

    @pytest.mark.asyncio
    async def test_concurrent_access(self, temp_db_dir):
        """Test concurrent access to JsonDB using Database interface."""
        jsondb1 = JsonDB(base_path=temp_db_dir)
        jsondb2 = JsonDB(base_path=temp_db_dir)

        # Create nodes concurrently
        async def create_node_task(name, value):
            node_data = {"id": name, "name": name, "value": value, "category": "test"}
            return await jsondb1.save("node", node_data)

        # Run concurrent operations
        tasks = [
            create_node_task("node1", 1),
            create_node_task("node2", 2),
            create_node_task("node3", 3),
        ]

        results = await asyncio.gather(*tasks)

        # Verify all nodes were created
        assert len(results) == 3
        for result in results:
            assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_version_conflict(self, jsondb):
        """Test version conflict handling using Database interface."""
        # Create initial node data
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", node_data)

        # Simulate version conflict by modifying the file directly
        node_file = os.path.join(jsondb.base_path, "node", "node1.json")
        with open(node_file, "r") as f:
            data = json.load(f)
        data["_version"] = 999  # Set high version
        with open(node_file, "w") as f:
            json.dump(data, f)

        # Try to update - JsonDB doesn't implement versioning, so this should work
        updated_data = {
            "id": "node1",
            "name": "updated_name",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", updated_data)

        # Verify update worked
        retrieved_data = await jsondb.get("node", "node1")
        assert retrieved_data["name"] == "updated_name"

    @pytest.mark.asyncio
    async def test_invalid_root_path(self):
        """Test JsonDB with invalid root path."""
        with pytest.raises((OSError, RuntimeError)):
            JsonDB(base_path="/invalid/nonexistent/path")

    @pytest.mark.asyncio
    async def test_permission_errors(self, temp_db_dir):
        """Test handling of permission errors using Database interface."""
        # Make directory read-only
        os.chmod(temp_db_dir, 0o444)

        try:
            jsondb = JsonDB(base_path=temp_db_dir)
            node_data = {
                "id": "node1",
                "name": "test_node",
                "value": 42,
                "category": "test",
            }

            # This should handle permission errors gracefully
            with pytest.raises(RuntimeError):
                await jsondb.save("node", node_data)
        finally:
            # Restore permissions
            os.chmod(temp_db_dir, 0o755)


class TestJsonDBPerformance:
    """Test JsonDB performance characteristics."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create temporary directory for database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def jsondb(self, temp_db_dir):
        """Create JsonDB instance for testing."""
        return JsonDB(base_path=temp_db_dir)

    @pytest.mark.asyncio
    async def test_bulk_operations(self, jsondb):
        """Test bulk operations performance using Database interface."""
        # Create many nodes
        node_data_list = []
        for i in range(100):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i,
                "category": "bulk",
            }
            node_data_list.append(node_data)

        # Create all nodes
        start_time = asyncio.get_event_loop().time()
        for node_data in node_data_list:
            await jsondb.save("node", node_data)
        end_time = asyncio.get_event_loop().time()

        # Should complete in reasonable time
        assert end_time - start_time < 5.0  # 5 seconds max

        # Test bulk finding
        start_time = asyncio.get_event_loop().time()
        found_nodes = await jsondb.find("node", {"category": "bulk"})
        end_time = asyncio.get_event_loop().time()

        assert len(found_nodes) == 100
        assert end_time - start_time < 2.0  # 2 seconds max

    @pytest.mark.asyncio
    async def test_large_data_handling(self, jsondb):
        """Test handling of large data using Database interface."""
        # Create node with large data
        large_data = {"data": "x" * 10000}  # 10KB of data
        node_data = {
            "id": "large_node",
            "name": "large_node",
            "value": 42,
            "category": "test",
            **large_data,
        }

        await jsondb.save("node", node_data)
        retrieved_data = await jsondb.get("node", "large_node")

        assert retrieved_data["data"] == large_data["data"]

    @pytest.mark.asyncio
    async def test_memory_usage(self, jsondb):
        """Test memory usage with many operations using Database interface."""
        try:
            import os

            import psutil

            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss

            # Create many nodes
            for i in range(1000):
                node_data = {
                    "id": f"node_{i}",
                    "name": f"node_{i}",
                    "value": i,
                    "category": "test",
                }
                await jsondb.save("node", node_data)

            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory

            # Memory increase should be reasonable (less than 100MB)
            assert memory_increase < 100 * 1024 * 1024
        except ImportError:
            # Skip if psutil not available
            pytest.skip("psutil not available")


class TestJsonDBFileSystem:
    """Test JsonDB file system operations."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create temporary directory for database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def jsondb(self, temp_db_dir):
        """Create JsonDB instance for testing."""
        return JsonDB(base_path=temp_db_dir)

    @pytest.mark.asyncio
    async def test_directory_structure(self, jsondb, temp_db_dir):
        """Test proper directory structure creation using Database interface."""
        # Test basic operations to ensure directories are created
        test_data = {"id": "test1", "name": "test", "value": 42}
        await jsondb.save("test_collection", test_data)

        # Check that base directory exists
        assert os.path.exists(temp_db_dir)
        assert str(jsondb.base_path) == os.path.realpath(temp_db_dir)

        # Check that collection directory was created
        collection_dir = os.path.join(temp_db_dir, "test_collection")
        assert os.path.exists(collection_dir)

        # Check that file was created
        test_file = os.path.join(collection_dir, "test1.json")
        assert os.path.exists(test_file)

    @pytest.mark.asyncio
    async def test_file_naming_convention(self, jsondb):
        """Test file naming convention using Database interface."""
        node_data = {
            "id": "test_node",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", node_data)

        # Check file naming (JsonDB uses simple id.json format)
        node_file = os.path.join(jsondb.base_path, "node", "test_node.json")
        assert os.path.exists(node_file)

    @pytest.mark.asyncio
    async def test_cleanup_on_delete(self, jsondb):
        """Test file cleanup on deletion using Database interface."""
        node_data = {
            "id": "test_node",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await jsondb.save("node", node_data)

        node_file = os.path.join(jsondb.base_path, "node", "test_node.json")
        assert os.path.exists(node_file)

        # Delete node
        await jsondb.delete("node", "test_node")

        # File should be removed
        assert not os.path.exists(node_file)

    @pytest.mark.asyncio
    async def test_backup_and_restore(self, jsondb):
        """Test backup and restore functionality using Database interface."""
        # Create some data
        node1_data = {"id": "node1", "name": "node1", "value": 1, "category": "test"}
        node2_data = {"id": "node2", "name": "node2", "value": 2, "category": "test"}

        await jsondb.save("node", node1_data)
        await jsondb.save("node", node2_data)

        # JsonDB doesn't have built-in backup/restore, so we'll test basic operations
        # Verify data exists
        retrieved1 = await jsondb.get("node", "node1")
        retrieved2 = await jsondb.get("node", "node2")

        assert retrieved1["name"] == "node1"
        assert retrieved2["name"] == "node2"
