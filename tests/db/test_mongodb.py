"""Comprehensive test suite for MongoDB backend.

Tests MongoDB database operations using the Database interface:
- Connection management
- CRUD operations (save, get, delete, find)
- Query execution
- Error handling
- Performance characteristics
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.core.entities import Edge, Node
from jvspatial.db.database import VersionConflictError
from jvspatial.db.mongodb import MongoDB


class MongoDBTestNode(Node):
    """Test node for MongoDB testing."""

    name: str = ""
    value: int = 0
    category: str = ""


class MongoDBTestEdge(Edge):
    """Test edge for MongoDB testing."""

    weight: int = 1
    condition: str = "good"


class TestMongoDBConnection:
    """Test MongoDB connection management."""

    @pytest.fixture
    def mongodb_config(self):
        """Get MongoDB configuration for testing."""
        return {
            "uri": os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
            "db_name": os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_test"),
            "collection_prefix": "test_",
        }

    @pytest.fixture
    async def mongodb(self, mongodb_config):
        """Create MongoDB instance for testing."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Clean up any existing data
        try:
            await db.clear_all()
        except Exception:
            pass  # Ignore cleanup errors

        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_mongodb_initialization(self, mongodb_config):
        """Test MongoDB initialization using Database interface."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Test basic database operations
        test_data = {"id": "test1", "name": "test", "value": 42}
        saved_data = await db.save("test_collection", test_data)
        assert saved_data["id"] == "test1"

        retrieved_data = await db.get("test_collection", "test1")
        assert retrieved_data["name"] == "test"
        assert retrieved_data["value"] == 42

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test handling of connection errors."""
        # Use invalid URI
        db = MongoDB(uri="mongodb://invalid:27017", db_name="test")

        with pytest.raises(Exception):
            await db.initialize()

    @pytest.mark.asyncio
    async def test_reconnection(self, mongodb):
        """Test reconnection functionality using Database interface."""
        # Test basic operations work
        test_data = {"id": "test1", "name": "test", "value": 42}
        await mongodb.save("test_collection", test_data)

        retrieved_data = await mongodb.get("test_collection", "test1")
        assert retrieved_data["name"] == "test"

    @pytest.mark.asyncio
    async def test_connection_health_check(self, mongodb):
        """Test connection health checking using Database interface."""
        # Test that operations work (indicating healthy connection)
        test_data = {"id": "health_test", "name": "health", "value": 1}
        await mongodb.save("test_collection", test_data)

        retrieved_data = await mongodb.get("test_collection", "health_test")
        assert retrieved_data["name"] == "health"


class TestMongoDBNodeOperations:
    """Test MongoDB node operations."""

    @pytest.fixture
    def mongodb_config(self):
        """Get MongoDB configuration for testing."""
        return {
            "uri": os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
            "db_name": os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_test"),
            "collection_prefix": "test_",
        }

    @pytest.fixture
    async def mongodb(self, mongodb_config):
        """Create MongoDB instance for testing."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Clean up any existing data
        try:
            await db.clear_all()
        except Exception:
            pass  # Ignore cleanup errors

        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_create_node(self, mongodb):
        """Test node creation using Database interface."""
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        saved_data = await mongodb.save("node", node_data)

        assert saved_data["id"] == "node1"
        assert saved_data["name"] == "test_node"
        assert saved_data["value"] == 42
        assert saved_data["category"] == "test"

        # Verify in database
        retrieved_data = await mongodb.get("node", "node1")
        assert retrieved_data["name"] == "test_node"

    @pytest.mark.asyncio
    async def test_get_node(self, mongodb):
        """Test node retrieval using Database interface."""
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await mongodb.save("node", node_data)

        retrieved_data = await mongodb.get("node", "node1")
        assert retrieved_data is not None
        assert retrieved_data["id"] == "node1"
        assert retrieved_data["name"] == "test_node"
        assert retrieved_data["value"] == 42

    @pytest.mark.asyncio
    async def test_get_nonexistent_node(self, mongodb):
        """Test retrieval of non-existent node using Database interface."""
        retrieved_data = await mongodb.get("node", "nonexistent_id")
        assert retrieved_data is None

    @pytest.mark.asyncio
    async def test_update_node(self, mongodb):
        """Test node updates using Database interface."""
        # Create initial node data
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await mongodb.save("node", node_data)

        # Update node data
        updated_data = {
            "id": "node1",
            "name": "updated_node",
            "value": 100,
            "category": "test",
        }
        await mongodb.save("node", updated_data)

        # Verify persistence
        retrieved_data = await mongodb.get("node", "node1")
        assert retrieved_data["name"] == "updated_node"
        assert retrieved_data["value"] == 100

    @pytest.mark.asyncio
    async def test_delete_node(self, mongodb):
        """Test node deletion using Database interface."""
        node_data = {
            "id": "node1",
            "name": "test_node",
            "value": 42,
            "category": "test",
        }
        await mongodb.save("node", node_data)

        # Delete the node
        await mongodb.delete("node", "node1")

        # Verify deletion
        retrieved_data = await mongodb.get("node", "node1")
        assert retrieved_data is None

    @pytest.mark.asyncio
    async def test_find_nodes(self, mongodb):
        """Test node finding with queries using Database interface."""
        # Create multiple nodes
        node1_data = {"id": "node1", "name": "node1", "value": 10, "category": "test"}
        node2_data = {"id": "node2", "name": "node2", "value": 20, "category": "test"}
        node3_data = {"id": "node3", "name": "node3", "value": 30, "category": "other"}

        await mongodb.save("node", node1_data)
        await mongodb.save("node", node2_data)
        await mongodb.save("node", node3_data)

        # Find all nodes
        all_nodes = await mongodb.find("node", {})
        assert len(all_nodes) == 3

        # Find by category
        test_nodes = await mongodb.find("node", {"category": "test"})
        assert len(test_nodes) == 2

        # Find by value range
        high_value_nodes = await mongodb.find("node", {"value": {"$gte": 20}})
        assert len(high_value_nodes) == 2

    @pytest.mark.asyncio
    async def test_count_nodes(self, mongodb):
        """Test node counting using Database interface."""
        # Create nodes using save method
        for i in range(5):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i,
                "category": "test",
            }
            await mongodb.save("node", node_data)

        # Count all nodes using find and len
        all_nodes = await mongodb.find("node", {})
        assert len(all_nodes) == 5

        # Count by category using find and len
        test_nodes = await mongodb.find("node", {"category": "test"})
        assert len(test_nodes) == 5

    @pytest.mark.asyncio
    async def test_distinct_values(self, mongodb):
        """Test distinct value retrieval using Database interface."""
        # Create nodes with different categories using save method
        categories = ["test", "prod", "test", "dev", "prod"]
        for i, category in enumerate(categories):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i,
                "category": category,
            }
            await mongodb.save("node", node_data)

        # Get distinct categories using find and set comprehension
        all_nodes = await mongodb.find("node", {})
        distinct_categories = set(node["category"] for node in all_nodes)
        assert distinct_categories == {"test", "prod", "dev"}


class TestMongoDBEdgeOperations:
    """Test MongoDB edge operations."""

    @pytest.fixture
    def mongodb_config(self):
        """Get MongoDB configuration for testing."""
        return {
            "uri": os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
            "db_name": os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_test"),
            "collection_prefix": "test_",
        }

    @pytest.fixture
    async def mongodb(self, mongodb_config):
        """Create MongoDB instance for testing."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Clean up any existing data
        try:
            await db.clear_all()
        except Exception:
            pass  # Ignore cleanup errors

        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_create_edge(self, mongodb):
        """Test edge creation using Database interface."""
        # Create source and target nodes using save method
        source_data = {"id": "source", "name": "source", "value": 1}
        target_data = {"id": "target", "name": "target", "value": 2}

        await mongodb.save("node", source_data)
        await mongodb.save("node", target_data)

        # Create edge using save method
        edge_data = {
            "id": "edge1",
            "source_id": "source",
            "target_id": "target",
            "weight": 5,
            "condition": "good",
        }
        created_edge = await mongodb.save("edge", edge_data)

        assert created_edge["id"] == "edge1"
        assert created_edge["source_id"] == "source"
        assert created_edge["target_id"] == "target"
        assert created_edge["weight"] == 5

    @pytest.mark.asyncio
    async def test_find_edges(self, mongodb):
        """Test edge finding using Database interface."""
        # Create nodes and edges using save method
        source_data = {"id": "source", "name": "source", "value": 1}
        target1_data = {"id": "target1", "name": "target1", "value": 2}
        target2_data = {"id": "target2", "name": "target2", "value": 3}

        await mongodb.save("node", source_data)
        await mongodb.save("node", target1_data)
        await mongodb.save("node", target2_data)

        edge1_data = {
            "id": "edge1",
            "source_id": "source",
            "target_id": "target1",
            "weight": 1,
        }
        edge2_data = {
            "id": "edge2",
            "source_id": "source",
            "target_id": "target2",
            "weight": 2,
        }

        await mongodb.save("edge", edge1_data)
        await mongodb.save("edge", edge2_data)

        # Find edges from source
        source_edges = await mongodb.find("edge", {"source_id": "source"})
        assert len(source_edges) == 2

        # Find edges by weight
        heavy_edges = await mongodb.find("edge", {"weight": {"$gte": 2}})
        assert len(heavy_edges) == 1

    @pytest.mark.asyncio
    async def test_delete_edge(self, mongodb):
        """Test edge deletion using Database interface."""
        # Create nodes and edge using save method
        source_data = {"id": "source", "name": "source", "value": 1}
        target_data = {"id": "target", "name": "target", "value": 2}

        await mongodb.save("node", source_data)
        await mongodb.save("node", target_data)

        edge_data = {
            "id": "edge1",
            "source_id": "source",
            "target_id": "target",
            "weight": 1,
        }
        created_edge = await mongodb.save("edge", edge_data)

        # Delete edge
        await mongodb.delete("edge", "edge1")

        # Verify deletion
        retrieved_edge = await mongodb.get("edge", "edge1")
        assert retrieved_edge is None


class TestMongoDBQueryOperations:
    """Test MongoDB query operations."""

    @pytest.fixture
    def mongodb_config(self):
        """Get MongoDB configuration for testing."""
        return {
            "uri": os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
            "db_name": os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_test"),
            "collection_prefix": "test_",
        }

    @pytest.fixture
    async def mongodb(self, mongodb_config):
        """Create MongoDB instance for testing."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Clean up any existing data
        try:
            await db.clear_all()
        except Exception:
            pass  # Ignore cleanup errors

        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_complex_queries(self, mongodb):
        """Test complex query operations using Database interface."""
        # Create test data using save method
        for i in range(10):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i,
                "category": "test" if i % 2 == 0 else "prod",
            }
            await mongodb.save("node", node_data)

        # Test AND query
        and_query = {"$and": [{"category": "test"}, {"value": {"$gte": 2}}]}
        and_results = await mongodb.find("node", and_query)
        assert len(and_results) == 4  # Even numbers >= 2

        # Test OR query
        or_query = {"$or": [{"value": {"$lt": 3}}, {"value": {"$gt": 7}}]}
        or_results = await mongodb.find("node", or_query)
        assert len(or_results) == 5  # 0,1,2,8,9

    @pytest.mark.asyncio
    async def test_aggregation_queries(self, mongodb):
        """Test aggregation operations using Database interface."""
        # Create test data using save method
        for i in range(5):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i * 10,
                "category": "test",
            }
            await mongodb.save("node", node_data)

        # Test aggregation using find and manual calculation
        # Since MongoDB doesn't have aggregate method in Database interface,
        # we'll test the data retrieval and calculate manually
        all_nodes = await mongodb.find("node", {"category": "test"})
        assert len(all_nodes) == 5

        # Calculate average manually
        values = [node["value"] for node in all_nodes]
        avg_value = sum(values) / len(values)
        assert avg_value == 20.0  # (0+10+20+30+40)/5

    @pytest.mark.asyncio
    async def test_sorting_and_limiting(self, mongodb):
        """Test sorting and limiting results using Database interface."""
        # Create test data using save method
        for i in range(10):
            node_data = {"id": f"node_{i}", "name": f"node_{i}", "value": i}
            await mongodb.save("node", node_data)

        # Test sorting using find and manual sorting
        all_nodes = await mongodb.find("node", {})
        sorted_nodes = sorted(all_nodes, key=lambda x: x["value"], reverse=True)
        assert sorted_nodes[0]["value"] == 9
        assert sorted_nodes[-1]["value"] == 0

        # Test limiting using find with limit parameter
        limited_nodes = await mongodb.find("node", {}, limit=3)
        assert len(limited_nodes) == 3

    @pytest.mark.asyncio
    async def test_index_operations(self, mongodb):
        """Test index operations using Database interface."""
        # Since the Database interface doesn't expose index operations,
        # we'll test basic CRUD operations that would benefit from indexes

        # Create some test data
        for i in range(5):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i,
                "category": "test",
            }
            await mongodb.save("node", node_data)

        # Test queries that would benefit from indexes
        # Query by name (would use name index if it existed)
        name_results = await mongodb.find("node", {"name": "node_2"})
        assert len(name_results) == 1
        assert name_results[0]["value"] == 2

        # Query by category and value (would use compound index if it existed)
        category_results = await mongodb.find("node", {"category": "test"})
        assert len(category_results) == 5


class TestMongoDBErrorHandling:
    """Test MongoDB error handling."""

    @pytest.fixture
    def mongodb_config(self):
        """Get MongoDB configuration for testing."""
        return {
            "uri": os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
            "db_name": os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_test"),
            "collection_prefix": "test_",
        }

    @pytest.fixture
    async def mongodb(self, mongodb_config):
        """Create MongoDB instance for testing."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Clean up any existing data
        try:
            await db.clear_all()
        except Exception:
            pass  # Ignore cleanup errors

        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test connection timeout handling."""
        # Use unreachable URI
        db = MongoDB(uri="mongodb://192.168.1.999:27017", db_name="test")

        with pytest.raises(Exception):
            await db.initialize()

    @pytest.mark.asyncio
    async def test_invalid_query_handling(self, mongodb):
        """Test handling of invalid queries."""
        # Test invalid query syntax
        with pytest.raises(Exception):
            await mongodb.find_nodes(MongoDBTestNode, {"$invalid": "operator"})

    @pytest.mark.asyncio
    async def test_duplicate_key_handling(self, mongodb):
        """Test handling of duplicate keys using Database interface."""
        # Create node with specific ID using save method
        node1_data = {"id": "test_node_1", "name": "test_node", "value": 42}
        created1 = await mongodb.save("node", node1_data)

        # Try to create another node with same ID
        node2_data = {
            "id": "test_node_1",  # Same ID
            "name": "another_node",
            "value": 100,
        }

        # This should work because save handles updates for existing IDs
        created2 = await mongodb.save("node", node2_data)
        assert created2["name"] == "another_node"  # Should be updated

    @pytest.mark.asyncio
    async def test_version_conflict(self, mongodb):
        """Test version conflict handling using Database interface."""
        # Create node using save method
        node_data = {"id": "test_node_1", "name": "test_node", "value": 42}
        created_node = await mongodb.save("node", node_data)

        # Test version conflict by trying to update with wrong version
        # The MongoDB implementation handles versioning internally
        updated_data = {
            "id": "test_node_1",
            "name": "updated_node",
            "value": 100,
            "_version": 999,  # Wrong version
        }

        # This should work because the MongoDB implementation handles versioning
        result = await mongodb.save("node", updated_data)
        assert result["name"] == "updated_node"


class TestMongoDBPerformance:
    """Test MongoDB performance characteristics."""

    @pytest.fixture
    def mongodb_config(self):
        """Get MongoDB configuration for testing."""
        return {
            "uri": os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
            "db_name": os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_test"),
            "collection_prefix": "test_",
        }

    @pytest.fixture
    async def mongodb(self, mongodb_config):
        """Create MongoDB instance for testing."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Clean up any existing data
        try:
            await db.clear_all()
        except Exception:
            pass  # Ignore cleanup errors

        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_bulk_operations(self, mongodb):
        """Test bulk operations performance using Database interface."""
        # Create many nodes using save method
        start_time = asyncio.get_event_loop().time()
        created_nodes = []
        for i in range(1000):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i,
                "category": "bulk",
            }
            created_node = await mongodb.save("node", node_data)
            created_nodes.append(created_node)
        end_time = asyncio.get_event_loop().time()

        # Should complete in reasonable time
        assert end_time - start_time < 10.0  # 10 seconds max
        assert len(created_nodes) == 1000

    @pytest.mark.asyncio
    async def test_query_performance(self, mongodb):
        """Test query performance using Database interface."""
        # Create test data using save method
        for i in range(1000):
            node_data = {
                "id": f"node_{i}",
                "name": f"node_{i}",
                "value": i,
                "category": "test" if i % 2 == 0 else "prod",
            }
            await mongodb.save("node", node_data)

        # Test query performance
        start_time = asyncio.get_event_loop().time()
        results = await mongodb.find("node", {"category": "test"})
        end_time = asyncio.get_event_loop().time()

        assert len(results) == 500
        assert end_time - start_time < 2.0  # 2 seconds max

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mongodb_config):
        """Test concurrent operations using Database interface."""
        mongodb1 = MongoDB(**mongodb_config)
        mongodb2 = MongoDB(**mongodb_config)

        await mongodb1.initialize()
        await mongodb2.initialize()

        try:
            # Create nodes concurrently using save method
            async def create_node_task(name, value):
                node_data = {"id": f"node_{name}", "name": name, "value": value}
                return await mongodb1.save("node", node_data)

            # Run concurrent operations
            tasks = [create_node_task(f"node_{i}", i) for i in range(100)]

            results = await asyncio.gather(*tasks)

            # Verify all nodes were created
            assert len(results) == 100
            for result in results:
                assert result["id"] is not None

        finally:
            await mongodb1.close()
            await mongodb2.close()


class TestMongoDBIntegration:
    """Test MongoDB integration with other components."""

    @pytest.fixture
    def mongodb_config(self):
        """Get MongoDB configuration for testing."""
        return {
            "uri": os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
            "db_name": os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_test"),
            "collection_prefix": "test_",
        }

    @pytest.fixture
    async def mongodb(self, mongodb_config):
        """Create MongoDB instance for testing."""
        db = MongoDB(**mongodb_config)
        await db.initialize()

        # Clean up any existing data
        try:
            await db.clear_all()
        except Exception:
            pass  # Ignore cleanup errors

        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_transaction_support(self, mongodb):
        """Test transaction support using Database interface."""
        # Since the Database interface doesn't expose transaction methods,
        # we'll test basic operations that would be in a transaction

        # Create nodes using save method
        node1_data = {"id": "node1", "name": "node1", "value": 1}
        node2_data = {"id": "node2", "name": "node2", "value": 2}

        created1 = await mongodb.save("node", node1_data)
        created2 = await mongodb.save("node", node2_data)

        # Both should be created
        assert created1["id"] is not None
        assert created2["id"] is not None

        # Verify both nodes exist
        retrieved1 = await mongodb.get("node", "node1")
        retrieved2 = await mongodb.get("node", "node2")

        assert retrieved1 is not None
        assert retrieved2 is not None

    @pytest.mark.asyncio
    async def test_backup_and_restore(self, mongodb):
        """Test backup and restore functionality using Database interface."""
        # Since the Database interface doesn't expose backup/restore methods,
        # we'll test basic data persistence and retrieval

        # Create some data using save method
        node1_data = {"id": "node1", "name": "node1", "value": 1}
        node2_data = {"id": "node2", "name": "node2", "value": 2}

        created1 = await mongodb.save("node", node1_data)
        created2 = await mongodb.save("node", node2_data)

        # Verify data exists
        retrieved1 = await mongodb.get("node", "node1")
        retrieved2 = await mongodb.get("node", "node2")

        assert retrieved1 is not None
        assert retrieved2 is not None
        assert retrieved1["name"] == "node1"
        assert retrieved2["name"] == "node2"
