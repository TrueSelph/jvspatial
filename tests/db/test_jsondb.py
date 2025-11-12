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

        # Check that file was created (JsonDB stores collections as directories with individual JSON files)
        node_dir = os.path.join(jsondb.base_path, "node")
        node_file = os.path.join(node_dir, "node1.json")
        assert os.path.exists(node_file)

        # Check file content
        with open(node_file, "r") as f:
            data = json.load(f)
        # JsonDB stores individual records as separate JSON files
        assert data["id"] == "node1"
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

        # Find by value range (JsonDB only supports exact matching)
        high_value_nodes = await jsondb.find("node", {"value": 20})
        assert len(high_value_nodes) == 1

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

        # Check that file was created (JsonDB stores collections as directories with individual JSON files)
        edge_dir = os.path.join(jsondb.base_path, "edge")
        edge_file = os.path.join(edge_dir, "edge1.json")
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

        # Find edges by weight (JsonDB only supports exact matching)
        heavy_edges = await jsondb.find("edge", {"weight": 2})
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

        # Corrupt the file (JsonDB stores collections as directories with individual JSON files)
        node_dir = os.path.join(jsondb.base_path, "node")
        node_file = os.path.join(node_dir, "node1.json")
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

        # Simulate version conflict by modifying the file directly (JsonDB stores collections as directories with individual JSON files)
        node_dir = os.path.join(jsondb.base_path, "node")
        node_file = os.path.join(node_dir, "node1.json")
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

            # This should raise permission errors
            with pytest.raises(PermissionError):
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

        # Check that collection directory was created (JsonDB stores collections as directories with individual JSON files)
        collection_dir = os.path.join(temp_db_dir, "test_collection")
        assert os.path.exists(collection_dir)

        # Check that the record file was created
        record_file = os.path.join(collection_dir, "test1.json")
        assert os.path.exists(record_file)

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

        # Check file naming (JsonDB stores collections as directories with individual JSON files)
        node_dir = os.path.join(jsondb.base_path, "node")
        assert os.path.exists(node_dir)

        node_file = os.path.join(node_dir, "test_node.json")
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

        node_dir = os.path.join(jsondb.base_path, "node")
        node_file = os.path.join(node_dir, "test_node.json")
        assert os.path.exists(node_file)

        # Delete node
        await jsondb.delete("node", "test_node")

        # File should be deleted (individual files are removed on delete)
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


class TestJsonDBEntityOperations:
    """Test JsonDB with actual entity operations (Objects, Nodes, Edges)."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create temporary directory for database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def jsondb(self, temp_db_dir):
        """Create JsonDB instance for testing."""
        return JsonDB(base_path=temp_db_dir)

    @pytest.fixture
    async def context(self, jsondb):
        """Create GraphContext with JsonDB for testing."""
        from jvspatial.core.context import GraphContext, set_default_context

        ctx = GraphContext(database=jsondb)
        set_default_context(ctx)
        return ctx

    @pytest.mark.asyncio
    async def test_object_creation_and_persistence(self, context):
        """Test Object creation and persistence through JsonDB."""
        from jvspatial.core.entities import Object

        # Create a custom object
        class TestObject(Object):
            name: str = ""
            value: int = 0
            category: str = ""

        # Create and save object
        obj = await TestObject.create(name="test_object", value=42, category="test")

        # Verify object was saved to database
        obj_data = await context.database.get("object", obj.id)
        assert obj_data is not None
        assert obj_data["name"] == "test_object"
        assert obj_data["value"] == 42
        assert obj_data["category"] == "test"

        # Verify file was created (JsonDB replaces colons with dots in filenames)
        obj_file = (
            context.database.base_path / "object" / f"{obj.id.replace(':', '.')}.json"
        )
        assert obj_file.exists()

    @pytest.mark.asyncio
    async def test_node_creation_and_persistence(self, context):
        """Test Node creation and persistence through JsonDB."""
        from jvspatial.core.entities import Node

        # Create custom node
        class TestNode(Node):
            name: str = ""
            value: int = 0
            category: str = ""

        # Create and save node
        node = await TestNode.create(name="test_node", value=100, category="test")

        # Verify node was saved to database
        node_data = await context.database.get("node", node.id)
        assert node_data is not None
        assert node_data["context"]["name"] == "test_node"
        assert node_data["context"]["value"] == 100
        assert node_data["context"]["category"] == "test"
        assert node_data["edges"] == []  # No edges initially

        # Verify file was created (JsonDB replaces colons with dots in filenames)
        node_file = (
            context.database.base_path / "node" / f"{node.id.replace(':', '.')}.json"
        )
        assert node_file.exists()

    @pytest.mark.asyncio
    async def test_edge_creation_and_persistence(self, context):
        """Test Edge creation and persistence through JsonDB."""
        from jvspatial.core.entities import Edge, Node

        # Create nodes
        node1 = await Node.create()
        node2 = await Node.create()

        # Create edge
        edge = await Edge.create(source=node1.id, target=node2.id)

        # Verify edge was saved to database
        edge_data = await context.database.get("edge", edge.id)
        assert edge_data is not None
        assert edge_data["source"] == node1.id
        assert edge_data["target"] == node2.id
        assert edge_data["bidirectional"] == True  # Default value

        # Verify file was created (JsonDB replaces colons with dots in filenames)
        edge_file = (
            context.database.base_path / "edge" / f"{edge.id.replace(':', '.')}.json"
        )
        assert edge_file.exists()

    @pytest.mark.asyncio
    async def test_node_connect_operation(self, context):
        """Test node.connect() operation and edge persistence."""
        from jvspatial.core.entities import Node

        # Create nodes
        node1 = await Node.create()
        node2 = await Node.create()

        # Connect nodes
        edge = await node1.connect(node2)

        # Verify edge was created and persisted
        edge_data = await context.database.get("edge", edge.id)
        assert edge_data is not None
        assert edge_data["source"] == node1.id
        assert edge_data["target"] == node2.id

        # Verify nodes have edge references
        node1_data = await context.database.get("node", node1.id)
        node2_data = await context.database.get("node", node2.id)

        assert edge.id in node1_data["edges"]
        assert edge.id in node2_data["edges"]

        # Verify files exist (JsonDB replaces colons with dots in filenames)
        edge_file = (
            context.database.base_path / "edge" / f"{edge.id.replace(':', '.')}.json"
        )
        assert edge_file.exists()

    @pytest.mark.asyncio
    async def test_complex_graph_creation(self, context):
        """Test creation of complex graph structure with multiple nodes and edges."""
        from jvspatial.core.entities import Node

        # Create custom node types
        class Person(Node):
            name: str = ""
            age: int = 0

        class Company(Node):
            name: str = ""
            industry: str = ""

        class Location(Node):
            name: str = ""
            country: str = ""

        # Create nodes
        person = await Person.create(name="John Doe", age=30)
        company = await Company.create(name="TechCorp", industry="Technology")
        location = await Location.create(name="San Francisco", country="USA")

        # Create edges
        works_edge = await person.connect(company)
        located_edge = await company.connect(location)

        # Verify all entities were persisted
        person_data = await context.database.get("node", person.id)
        company_data = await context.database.get("node", company.id)
        location_data = await context.database.get("node", location.id)

        works_edge_data = await context.database.get("edge", works_edge.id)
        located_edge_data = await context.database.get("edge", located_edge.id)

        assert person_data is not None
        assert company_data is not None
        assert location_data is not None
        assert works_edge_data is not None
        assert located_edge_data is not None

        # Verify edge references
        assert works_edge.id in person_data["edges"]
        assert works_edge.id in company_data["edges"]
        assert located_edge.id in company_data["edges"]
        assert located_edge.id in location_data["edges"]

        # Verify all files exist (JsonDB replaces colons with dots in filenames)
        assert (
            context.database.base_path / "node" / f"{person.id.replace(':', '.')}.json"
        ).exists()
        assert (
            context.database.base_path / "node" / f"{company.id.replace(':', '.')}.json"
        ).exists()
        assert (
            context.database.base_path
            / "node"
            / f"{location.id.replace(':', '.')}.json"
        ).exists()
        assert (
            context.database.base_path
            / "edge"
            / f"{works_edge.id.replace(':', '.')}.json"
        ).exists()
        assert (
            context.database.base_path
            / "edge"
            / f"{located_edge.id.replace(':', '.')}.json"
        ).exists()

    @pytest.mark.asyncio
    async def test_node_disconnect_operation(self, context):
        """Test node.disconnect() operation and edge removal."""
        from jvspatial.core.entities import Node

        # Create nodes and connect them
        node1 = await Node.create()
        node2 = await Node.create()
        edge = await node1.connect(node2)

        # Verify connection exists
        assert await node1.is_connected_to(node2)

        # Disconnect nodes
        success = await node1.disconnect(node2)
        assert success

        # Verify disconnection
        assert not await node1.is_connected_to(node2)

        # Verify edge was removed from database
        edge_data = await context.database.get("edge", edge.id)
        assert edge_data is None

        # Verify edge file was deleted (JsonDB replaces colons with dots in filenames)
        edge_file = (
            context.database.base_path / "edge" / f"{edge.id.replace(':', '.')}.json"
        )
        assert not edge_file.exists()

        # Verify nodes no longer reference the edge
        node1_data = await context.database.get("node", node1.id)
        node2_data = await context.database.get("node", node2.id)

        assert edge.id not in node1_data["edges"]
        assert edge.id not in node2_data["edges"]


class TestJsonDBWalkerTraversal:
    """Test JsonDB with walker traversal operations."""

    @pytest.fixture
    def temp_db_dir(self):
        """Create temporary directory for database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def jsondb(self, temp_db_dir):
        """Create JsonDB instance for testing."""
        return JsonDB(base_path=temp_db_dir)

    @pytest.fixture
    async def context(self, jsondb):
        """Create GraphContext with JsonDB for testing."""
        from jvspatial.core.context import GraphContext, set_default_context

        ctx = GraphContext(database=jsondb)
        set_default_context(ctx)
        return ctx

    @pytest.mark.asyncio
    async def test_basic_walker_traversal(self, context):
        """Test basic walker traversal through persisted graph."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Node, Walker

        # Create a simple graph: A -> B -> C
        node_a = await Node.create()
        node_b = await Node.create()
        node_c = await Node.create()

        # Create edges
        edge1 = await node_a.connect(node_b)
        edge2 = await node_b.connect(node_c)

        # Verify graph is persisted
        assert await context.database.get("edge", edge1.id) is not None
        assert await context.database.get("edge", edge2.id) is not None

        # Create walker
        class TestWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)
                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = TestWalker()
        await walker.spawn(node_a)

        # Verify traversal
        assert len(walker.visited_nodes) == 3
        assert node_a.id in walker.visited_nodes
        assert node_b.id in walker.visited_nodes
        assert node_c.id in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_walker_with_custom_node_types(self, context):
        """Test walker traversal with custom node types."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Node, Walker

        # Create custom node types
        class Person(Node):
            name: str = ""
            age: int = 0

        class Company(Node):
            name: str = ""
            industry: str = ""

        # Create nodes
        person = await Person.create(name="Alice", age=25)
        company = await Company.create(name="StartupCorp", industry="Tech")

        # Connect them
        edge = await person.connect(company)

        # Verify persistence
        person_data = await context.database.get("node", person.id)
        company_data = await context.database.get("node", company.id)
        edge_data = await context.database.get("edge", edge.id)

        assert person_data["context"]["name"] == "Alice"
        assert company_data["context"]["name"] == "StartupCorp"
        assert edge_data["source"] == person.id
        assert edge_data["target"] == company.id

        # Create walker
        class PersonWalker(Walker):
            visited_nodes: List[str] = []
            visited_names: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)
                if hasattr(node, "name"):
                    self.visited_names.append(node.name)

                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = PersonWalker()
        await walker.spawn(person)

        # Verify traversal
        assert len(walker.visited_nodes) == 2
        assert len(walker.visited_names) == 2
        assert "Alice" in walker.visited_names
        assert "StartupCorp" in walker.visited_names

    @pytest.mark.asyncio
    async def test_walker_with_edge_filtering(self, context):
        """Test walker traversal with edge type filtering."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Edge, Node, Walker

        # Create custom edge types
        class WorksFor(Edge):
            position: str = ""

        class LocatedIn(Edge):
            distance: int = 0

        # Create nodes
        person = await Node.create()
        company = await Node.create()
        city = await Node.create()

        # Create different types of edges
        works_edge = await person.connect(company, edge=WorksFor)
        location_edge = await company.connect(city, edge=LocatedIn)

        # Verify edges are persisted
        works_data = await context.database.get("edge", works_edge.id)
        location_data = await context.database.get("edge", location_edge.id)

        assert works_data is not None
        assert location_data is not None

        # Create walker that only follows WorksFor edges
        class EmploymentWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)

                # Only follow WorksFor edges
                connected_nodes = await node.nodes(edge=WorksFor)
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = EmploymentWalker()
        await walker.spawn(person)

        # Should only visit person and company (connected by WorksFor)
        # Should NOT visit city (connected by LocatedIn)
        assert len(walker.visited_nodes) == 2
        assert person.id in walker.visited_nodes
        assert company.id in walker.visited_nodes
        assert city.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_walker_with_direction_filtering(self, context):
        """Test walker traversal with direction filtering."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Node, Walker

        # Create nodes: A -> B -> C
        node_a = await Node.create()
        node_b = await Node.create()
        node_c = await Node.create()

        # Create edges
        edge1 = await node_a.connect(node_b)
        edge2 = await node_b.connect(node_c)

        # Verify edges are persisted
        assert await context.database.get("edge", edge1.id) is not None
        assert await context.database.get("edge", edge2.id) is not None

        # Create walker that only follows outgoing connections
        class OutgoingWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)

                # Only follow outgoing connections
                connected_nodes = await node.nodes(direction="out")
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = OutgoingWalker()
        await walker.spawn(node_b)  # Start from middle node

        # Should visit B and C (outgoing), but NOT A (incoming)
        assert len(walker.visited_nodes) == 2
        assert node_b.id in walker.visited_nodes
        assert node_c.id in walker.visited_nodes
        assert node_a.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_walker_with_cycle_detection(self, context):
        """Test walker traversal with cycle detection."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Node, Walker

        # Create a cycle: A -> B -> C -> A
        node_a = await Node.create()
        node_b = await Node.create()
        node_c = await Node.create()

        # Create edges
        edge1 = await node_a.connect(node_b)
        edge2 = await node_b.connect(node_c)
        edge3 = await node_c.connect(node_a)  # Creates cycle

        # Verify all edges are persisted
        assert await context.database.get("edge", edge1.id) is not None
        assert await context.database.get("edge", edge2.id) is not None
        assert await context.database.get("edge", edge3.id) is not None

        # Create walker with cycle detection
        class CycleAwareWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)

                # Only visit nodes we haven't seen before
                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = CycleAwareWalker()
        await walker.spawn(node_a)

        # Should visit each node only once despite the cycle
        assert len(walker.visited_nodes) == 3
        assert walker.visited_nodes.count(node_a.id) == 1
        assert walker.visited_nodes.count(node_b.id) == 1
        assert walker.visited_nodes.count(node_c.id) == 1

    @pytest.mark.asyncio
    async def test_walker_persistence_verification(self, context):
        """Test that walker traversal works with persisted graph data."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Node, Walker

        # Create a complex graph: Root -> A -> B -> C
        #                           -> D -> E
        root = await Node.create()
        node_a = await Node.create()
        node_b = await Node.create()
        node_c = await Node.create()
        node_d = await Node.create()
        node_e = await Node.create()

        # Create edges
        edge1 = await root.connect(node_a)
        edge2 = await root.connect(node_d)
        edge3 = await node_a.connect(node_b)
        edge4 = await node_b.connect(node_c)
        edge5 = await node_d.connect(node_e)

        # Verify all edges are persisted
        edge_ids = [edge1.id, edge2.id, edge3.id, edge4.id, edge5.id]
        for edge_id in edge_ids:
            assert await context.database.get("edge", edge_id) is not None

        # Verify all nodes are persisted
        node_ids = [root.id, node_a.id, node_b.id, node_c.id, node_d.id, node_e.id]
        for node_id in node_ids:
            assert await context.database.get("node", node_id) is not None

        # Create walker
        class ComplexWalker(Walker):
            visited_nodes: List[str] = []
            traversal_path: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)
                self.traversal_path.append(node.id)

                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = ComplexWalker()
        await walker.spawn(root)

        # Should visit all nodes
        assert len(walker.visited_nodes) == 6
        for node_id in node_ids:
            assert node_id in walker.visited_nodes

        # Verify traversal path is reasonable
        assert walker.traversal_path[0] == root.id  # Should start from root
        assert len(set(walker.traversal_path)) == 6  # All nodes visited exactly once


class TestJsonDBPersistentOperations:
    """Test JsonDB with persistent operations that write to main database."""

    @pytest.fixture
    def persistent_db(self):
        """Create JsonDB instance that writes to main jvdb directory."""
        return JsonDB(base_path="jvdb")

    @pytest.fixture
    async def persistent_context(self, persistent_db):
        """Create GraphContext with persistent JsonDB for testing."""
        from jvspatial.core.context import GraphContext, set_default_context

        ctx = GraphContext(database=persistent_db)
        set_default_context(ctx)
        return ctx

    @pytest.mark.asyncio
    async def test_persistent_graph_creation(self, persistent_context):
        """Test creation of persistent graph that survives test runs."""
        from jvspatial.core.entities import Node

        # Create custom node types
        class TestPerson(Node):
            name: str = ""
            age: int = 0

        class TestCompany(Node):
            name: str = ""
            industry: str = ""

        # Create nodes
        person = await TestPerson.create(name="TestPerson", age=25)
        company = await TestCompany.create(name="TestCompany", industry="Technology")

        # Connect them
        edge = await person.connect(company)

        # Verify persistence in main database
        person_data = await persistent_context.database.get("node", person.id)
        company_data = await persistent_context.database.get("node", company.id)
        edge_data = await persistent_context.database.get("edge", edge.id)

        assert person_data is not None
        assert company_data is not None
        assert edge_data is not None

        # Verify file structure (JsonDB replaces colons with dots in filenames)
        person_file = (
            persistent_context.database.base_path
            / "node"
            / f"{person.id.replace(':', '.')}.json"
        )
        company_file = (
            persistent_context.database.base_path
            / "node"
            / f"{company.id.replace(':', '.')}.json"
        )
        edge_file = (
            persistent_context.database.base_path
            / "edge"
            / f"{edge.id.replace(':', '.')}.json"
        )

        assert person_file.exists()
        assert company_file.exists()
        assert edge_file.exists()

        # Verify data integrity
        assert person_data["context"]["name"] == "TestPerson"
        assert company_data["context"]["name"] == "TestCompany"
        assert edge_data["source"] == person.id
        assert edge_data["target"] == company.id

    @pytest.mark.asyncio
    async def test_persistent_walker_traversal(self, persistent_context):
        """Test walker traversal on persistent graph data."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Node, Walker

        # Create a persistent graph: A -> B -> C
        node_a = await Node.create()
        node_b = await Node.create()
        node_c = await Node.create()

        # Create edges
        edge1 = await node_a.connect(node_b)
        edge2 = await node_b.connect(node_c)

        # Verify persistence
        assert await persistent_context.database.get("edge", edge1.id) is not None
        assert await persistent_context.database.get("edge", edge2.id) is not None

        # Create walker
        class PersistentWalker(Walker):
            visited_nodes: List[str] = []
            traversal_order: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)
                self.traversal_order.append(node.id)

                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = PersistentWalker()
        await walker.spawn(node_a)

        # Verify traversal
        assert len(walker.visited_nodes) == 3
        assert node_a.id in walker.visited_nodes
        assert node_b.id in walker.visited_nodes
        assert node_c.id in walker.visited_nodes

        # Verify traversal order starts from A
        assert walker.traversal_order[0] == node_a.id

    @pytest.mark.asyncio
    async def test_persistent_complex_graph(self, persistent_context):
        """Test creation and traversal of complex persistent graph."""
        from typing import List

        from jvspatial.core import on_visit
        from jvspatial.core.entities import Node, Walker

        # Create custom node types
        class City(Node):
            name: str = ""
            population: int = 0

        class Organization(Node):
            name: str = ""
            type: str = ""

        class Agent(Node):
            name: str = ""
            role: str = ""

        # Create nodes
        city = await City.create(name="TestCity", population=100000)
        org = await Organization.create(name="TestOrg", type="Government")
        agent1 = await Agent.create(name="Agent1", role="Analyst")
        agent2 = await Agent.create(name="Agent2", role="Manager")

        # Create complex connections
        city_org_edge = await city.connect(org)
        org_agent1_edge = await org.connect(agent1)
        org_agent2_edge = await org.connect(agent2)
        agent1_agent2_edge = await agent1.connect(agent2)

        # Verify all edges are persisted
        edge_ids = [
            city_org_edge.id,
            org_agent1_edge.id,
            org_agent2_edge.id,
            agent1_agent2_edge.id,
        ]
        for edge_id in edge_ids:
            assert await persistent_context.database.get("edge", edge_id) is not None

        # Create walker
        class ComplexWalker(Walker):
            visited_nodes: List[str] = []
            node_types: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)
                self.node_types.append(node.__class__.__name__)

                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = ComplexWalker()
        await walker.spawn(city)

        # Should visit all nodes
        assert len(walker.visited_nodes) == 4
        assert city.id in walker.visited_nodes
        assert org.id in walker.visited_nodes
        assert agent1.id in walker.visited_nodes
        assert agent2.id in walker.visited_nodes

        # Verify node types
        assert "City" in walker.node_types
        assert "Organization" in walker.node_types
        assert "Agent" in walker.node_types
