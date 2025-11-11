"""Test suite for SQLite database operations.

Tests the SQLite database implementation including CRUD operations,
query functionality, connection management, and integration with entities.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Edge, Node, Object
from jvspatial.db import create_database

try:
    from jvspatial.db.sqlite import SQLiteDB

    HAS_SQLITE = True
except ImportError:  # pragma: no cover - exercised when aiosqlite missing
    SQLiteDB = None  # type: ignore[misc]
    HAS_SQLITE = False

# Skip all tests if SQLite is not available
pytestmark = pytest.mark.skipif(
    not HAS_SQLITE, reason="aiosqlite is required for SQLite tests"
)


# Test fixtures
@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        yield db_path


@pytest.fixture
async def sqlite_db(temp_db_path):
    """Create a SQLite database instance for testing."""
    db = create_database("sqlite", db_path=str(temp_db_path))
    try:
        yield db
    finally:
        if hasattr(db, "close"):
            await db.close()


@pytest.fixture
async def sqlite_context(sqlite_db):
    """Create a GraphContext with SQLite database."""
    ctx = GraphContext(database=sqlite_db)
    set_default_context(ctx)
    return ctx


# Test entity classes
class TestNode(Node):
    """Test node class."""

    __test__ = False  # Tell pytest not to collect this as a test class

    name: str = ""
    value: int = 0
    active: bool = True


class TestEdge(Edge):
    """Test edge class."""

    __test__ = False  # Tell pytest not to collect this as a test class

    weight: float = 0.0
    label: str = ""


class TestObject(Object):
    """Test object class."""

    __test__ = False  # Tell pytest not to collect this as a test class

    name: str = ""
    category: str = ""


class TestSQLiteBasicOperations:
    """Test basic SQLite database operations."""

    @pytest.mark.asyncio
    async def test_sqlite_initialization(self, temp_db_path):
        """Test SQLite database initialization."""
        db = create_database("sqlite", db_path=str(temp_db_path))
        try:
            assert isinstance(db, SQLiteDB)
            # Compare resolved paths for consistency
            assert db.db_path.resolve() == temp_db_path.resolve()
            assert db.timeout == 5.0  # Default timeout
            assert db.journal_mode == "WAL"  # Default journal mode
            assert db.synchronous == "NORMAL"  # Default synchronous
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_sqlite_initialization_with_config(self, temp_db_path):
        """Test SQLite database initialization with custom configuration."""
        db = create_database(
            "sqlite",
            db_path=str(temp_db_path),
            timeout=10.0,
            journal_mode="DELETE",
            synchronous="FULL",
        )
        try:
            assert isinstance(db, SQLiteDB)
            # Compare resolved paths for consistency
            assert db.db_path.resolve() == temp_db_path.resolve()
            assert db.timeout == 10.0
            assert db.journal_mode == "DELETE"
            assert db.synchronous == "FULL"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_sqlite_memory_database(self):
        """Test in-memory SQLite database."""
        db = create_database("sqlite", db_path=":memory:")
        try:
            assert isinstance(db, SQLiteDB)
            assert db.db_path_str == ":memory:"

            # Test operations work with in-memory database
            data = {"id": "test-1", "name": "Test"}
            saved = await db.save("test", data)
            assert saved["id"] == "test-1"

            retrieved = await db.get("test", "test-1")
            assert retrieved is not None
            assert retrieved["name"] == "Test"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_save_and_get(self, sqlite_db):
        """Test saving and retrieving records."""
        # Save a record
        data = {"id": "test-id", "name": "Test Record", "value": 42}
        result = await sqlite_db.save("test", data)
        assert result["id"] == "test-id"
        assert result["name"] == "Test Record"
        assert result["value"] == 42

        # Retrieve the record
        retrieved = await sqlite_db.get("test", "test-id")
        assert retrieved is not None
        assert retrieved["name"] == "Test Record"
        assert retrieved["value"] == 42

    @pytest.mark.asyncio
    async def test_save_without_id(self, sqlite_db):
        """Test saving record without ID generates one."""
        data = {"name": "No ID Record", "value": 100}
        result = await sqlite_db.save("test", data)

        assert "id" in result
        assert result["id"] is not None
        assert len(result["id"]) > 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_record(self, sqlite_db):
        """Test getting non-existent record returns None."""
        result = await sqlite_db.get("test", "nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_record(self, sqlite_db):
        """Test deleting records."""
        # Save a record
        data = {"id": "delete-me", "name": "To Delete"}
        await sqlite_db.save("test", data)

        # Verify it exists
        retrieved = await sqlite_db.get("test", "delete-me")
        assert retrieved is not None

        # Delete it
        await sqlite_db.delete("test", "delete-me")

        # Verify it's gone
        retrieved = await sqlite_db.get("test", "delete-me")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_find_records(self, sqlite_db):
        """Test finding records with queries."""
        # Create multiple records
        records = [
            {
                "id": f"record-{i}",
                "name": f"Record {i}",
                "value": i,
                "category": f"cat_{i % 3}",
            }
            for i in range(10)
        ]

        for record in records:
            await sqlite_db.save("test", record)

        # Find all records
        all_records = await sqlite_db.find("test", {})
        assert len(all_records) == 10

        # Find with simple query
        category_0 = await sqlite_db.find("test", {"category": "cat_0"})
        assert len(category_0) >= 3  # Should have at least 3 records

        # Find with value query
        high_value = await sqlite_db.find("test", {"value": {"$gte": 5}})
        assert len(high_value) == 5

    @pytest.mark.asyncio
    async def test_find_one(self, sqlite_db):
        """Test finding a single record."""
        # Create a record
        data = {"id": "find-one", "name": "Find Me", "value": 42}
        await sqlite_db.save("test", data)

        # Find it
        result = await sqlite_db.find_one("test", {"name": "Find Me"})
        assert result is not None
        assert result["id"] == "find-one"
        assert result["value"] == 42

        # Find non-existent
        result = await sqlite_db.find_one("test", {"name": "Not Found"})
        assert result is None

    @pytest.mark.asyncio
    async def test_count_records(self, sqlite_db):
        """Test counting records."""
        # Create multiple records
        for i in range(5):
            await sqlite_db.save("test", {"id": f"count-{i}", "value": i})

        # Count all
        count = await sqlite_db.count("test", {})
        assert count == 5

        # Count with filter
        count_filtered = await sqlite_db.count("test", {"value": {"$gte": 3}})
        assert count_filtered == 2

    @pytest.mark.asyncio
    async def test_update_record(self, sqlite_db):
        """Test updating records by saving again."""
        # Create a record
        data = {"id": "update-me", "name": "Original", "value": 10}
        await sqlite_db.save("test", data)

        # Update it
        updated_data = {"id": "update-me", "name": "Updated", "value": 20}
        await sqlite_db.save("test", updated_data)

        # Verify update
        retrieved = await sqlite_db.get("test", "update-me")
        assert retrieved["name"] == "Updated"
        assert retrieved["value"] == 20

    @pytest.mark.asyncio
    async def test_close_connection(self, sqlite_db):
        """Test closing database connection."""
        # Use the database
        await sqlite_db.save("test", {"id": "test-1", "name": "Test"})

        # Close it
        await sqlite_db.close()

        # Verify connection is closed
        assert sqlite_db._connection is None
        assert sqlite_db._initialized is False


class TestSQLiteQueryOperations:
    """Test SQLite query operations."""

    @pytest.mark.asyncio
    async def test_simple_equality_query(self, sqlite_db):
        """Test simple equality queries."""
        records = [
            {
                "id": f"r{i}",
                "name": f"Record {i}",
                "status": "active" if i % 2 == 0 else "inactive",
            }
            for i in range(10)
        ]

        for record in records:
            await sqlite_db.save("test", record)

        # Find active records
        active = await sqlite_db.find("test", {"status": "active"})
        assert len(active) == 5

    @pytest.mark.asyncio
    async def test_comparison_operators(self, sqlite_db):
        """Test comparison operators in queries."""
        records = [
            {"id": f"r{i}", "value": i * 10, "score": i * 2.5} for i in range(10)
        ]

        for record in records:
            await sqlite_db.save("test", record)

        # Test $gte
        high_value = await sqlite_db.find("test", {"value": {"$gte": 50}})
        assert len(high_value) == 5

        # Test $lt
        low_value = await sqlite_db.find("test", {"value": {"$lt": 30}})
        assert len(low_value) == 3

        # Test $gt
        greater = await sqlite_db.find("test", {"value": {"$gt": 70}})
        assert len(greater) == 2

        # Test $lte
        less_equal = await sqlite_db.find("test", {"value": {"$lte": 20}})
        assert len(less_equal) == 3

    @pytest.mark.asyncio
    async def test_nested_field_queries(self, sqlite_db):
        """Test queries on nested fields."""
        records = [
            {
                "id": f"r{i}",
                "metadata": {"category": f"cat_{i % 3}", "priority": i},
                "tags": ["tag1", "tag2"] if i % 2 == 0 else ["tag3"],
            }
            for i in range(6)
        ]

        for record in records:
            await sqlite_db.save("test", record)

        # Query nested field
        cat_0 = await sqlite_db.find("test", {"metadata.category": "cat_0"})
        assert len(cat_0) == 2

        # Query nested with comparison
        high_priority = await sqlite_db.find("test", {"metadata.priority": {"$gte": 3}})
        assert len(high_priority) == 3


class TestSQLiteEntityOperations:
    """Test SQLite with entity operations."""

    @pytest.mark.asyncio
    async def test_node_creation_and_retrieval(self, sqlite_context):
        """Test creating and retrieving nodes."""
        # Create a node
        node = await TestNode.create(name="Test Node", value=42, active=True)
        assert node.id is not None
        assert node.name == "Test Node"
        assert node.value == 42

        # Retrieve it
        retrieved = await TestNode.get(node.id)
        assert retrieved is not None
        assert retrieved.name == "Test Node"
        assert retrieved.value == 42

    @pytest.mark.asyncio
    async def test_node_find_operations(self, sqlite_context):
        """Test finding nodes with queries."""
        # Create multiple nodes
        nodes = [
            await TestNode.create(name=f"Node {i}", value=i, active=i % 2 == 0)
            for i in range(10)
        ]

        # Find all
        all_nodes = await TestNode.find({})
        assert len(all_nodes) == 10

        # Find with filter
        active_nodes = await TestNode.find({"context.active": True})
        assert len(active_nodes) == 5

        # Find with value filter
        high_value = await TestNode.find({"context.value": {"$gte": 5}})
        assert len(high_value) == 5

    @pytest.mark.asyncio
    async def test_node_update_operations(self, sqlite_context):
        """Test updating nodes."""
        # Create a node
        node = await TestNode.create(name="Original", value=10, active=True)
        original_id = node.id

        # Update it
        node.name = "Updated"
        node.value = 20
        await node.save()

        # Retrieve and verify
        retrieved = await TestNode.get(original_id)
        assert retrieved is not None
        assert retrieved.name == "Updated"
        assert retrieved.value == 20

    @pytest.mark.asyncio
    async def test_node_delete_operations(self, sqlite_context):
        """Test deleting nodes."""
        # Create a node
        node = await TestNode.create(name="To Delete", value=1)
        node_id = node.id

        # Verify it exists
        retrieved = await TestNode.get(node_id)
        assert retrieved is not None

        # Delete it
        await node.delete()

        # Verify it's gone
        retrieved = await TestNode.get(node_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_edge_creation(self, sqlite_context):
        """Test creating edges between nodes."""
        # Create nodes
        node1 = await TestNode.create(name="Node 1", value=1)
        node2 = await TestNode.create(name="Node 2", value=2)

        # Create edge
        edge = await node1.connect(node2, TestEdge, weight=1.5, label="connects")
        assert edge.id is not None
        assert edge.weight == 1.5
        assert edge.label == "connects"

    @pytest.mark.asyncio
    async def test_object_operations(self, sqlite_context):
        """Test Object operations with SQLite."""
        # Create objects
        obj1 = await TestObject.create(name="Object 1", category="cat1")
        obj2 = await TestObject.create(name="Object 2", category="cat2")

        # Find all
        all_objects = await TestObject.find({})
        assert len(all_objects) == 2

        # Find by category
        # For Objects, fields are stored at root level
        # Object.find() now handles this correctly - can use either format
        cat1_objects = await TestObject.find({"category": "cat1"})
        assert len(cat1_objects) == 1
        assert cat1_objects[0].name == "Object 1"


class TestSQLiteErrorHandling:
    """Test SQLite error handling."""

    @pytest.mark.asyncio
    async def test_invalid_path_handling(self):
        """Test handling of invalid database paths."""
        # Try to create database with invalid path
        # The error should occur during __init__ when trying to create parent directory
        invalid_path = Path("/nonexistent_directory_for_testing/db.db")

        # On some systems, this might not raise an error until connection time
        # So we test both scenarios
        try:
            db = create_database("sqlite", db_path=str(invalid_path))
            # If creation succeeded, the error will occur when trying to connect
            # Try to use it (should fail on first operation)
            try:
                await db.save("test", {"id": "test", "name": "test"})
                # If we get here, the path was actually valid (unlikely but possible)
                await db.close()
                pytest.skip("Path was actually valid on this system")
            except (OSError, PermissionError) as e:
                # Expected - connection failed when trying to create directory
                await db.close()
                # This is acceptable - error occurred when expected
                pass
        except (OSError, PermissionError):
            # Expected - directory creation failed during __init__
            pass

    @pytest.mark.asyncio
    async def test_missing_collection_handling(self, sqlite_db):
        """Test operations on non-existent collections."""
        # Get from non-existent collection
        result = await sqlite_db.get("nonexistent", "some-id")
        assert result is None

        # Find from non-existent collection
        results = await sqlite_db.find("nonexistent", {})
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_operations_after_close(self, sqlite_db):
        """Test operations after closing database."""
        # Close the database
        await sqlite_db.close()

        # Verify connection is closed
        assert sqlite_db._connection is None
        assert sqlite_db._initialized is False

        # Try to use it (should reconnect automatically via _get_connection)
        data = {"id": "test-1", "name": "Test"}
        await sqlite_db.save("test", data)

        # Verify it worked and connection was recreated
        assert sqlite_db._connection is not None
        assert sqlite_db._initialized is True

        retrieved = await sqlite_db.get("test", "test-1")
        assert retrieved is not None
        assert retrieved["name"] == "Test"


class TestSQLitePerformance:
    """Test SQLite performance considerations."""

    @pytest.mark.asyncio
    async def test_bulk_operations(self, sqlite_db):
        """Test bulk database operations."""
        # Create many records
        records = [
            {"id": f"record_{i}", "value": i, "category": f"cat_{i % 3}"}
            for i in range(100)
        ]

        # Save all records
        for record in records:
            await sqlite_db.save("test", record)

        # Verify count
        count = await sqlite_db.count("test", {})
        assert count == 100

        # Find with filter
        category_0_records = await sqlite_db.find("test", {"category": "cat_0"})
        assert len(category_0_records) >= 30  # Should be roughly 1/3

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, sqlite_db):
        """Test concurrent database operations."""

        # Create concurrent tasks
        async def save_records(start_idx: int, count: int):
            tasks = []
            for i in range(start_idx, start_idx + count):
                record = {"id": f"concurrent_{i}", "value": i}
                tasks.append(sqlite_db.save("test", record))
            await asyncio.gather(*tasks)

        # Run concurrent saves
        await asyncio.gather(
            save_records(0, 10), save_records(10, 10), save_records(20, 10)
        )

        # Verify all records were saved
        count = await sqlite_db.count("test", {})
        assert count == 30

    @pytest.mark.asyncio
    async def test_large_data_handling(self, sqlite_db):
        """Test handling of large data records."""
        # Create record with large data
        large_data = {
            "id": "large-record",
            "name": "Large Record",
            "data": "x" * 10000,  # 10KB of data
            "metadata": {"items": list(range(1000))},
        }

        await sqlite_db.save("test", large_data)

        # Retrieve it
        retrieved = await sqlite_db.get("test", "large-record")
        assert retrieved is not None
        assert len(retrieved["data"]) == 10000
        assert len(retrieved["metadata"]["items"]) == 1000


class TestSQLiteConnectionManagement:
    """Test SQLite connection management."""

    @pytest.mark.asyncio
    async def test_connection_lazy_initialization(self, temp_db_path):
        """Test that connection is created lazily."""
        db = create_database("sqlite", db_path=str(temp_db_path))
        try:
            # Connection should not exist yet
            assert db._connection is None
            assert db._initialized is False

            # First operation should create connection
            await db.save("test", {"id": "test-1", "name": "Test"})

            # Connection should now exist
            assert db._connection is not None
            assert db._initialized is True
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_multiple_operations_reuse_connection(self, sqlite_db):
        """Test that multiple operations reuse the same connection."""
        # Perform multiple operations
        for i in range(5):
            await sqlite_db.save("test", {"id": f"test-{i}", "value": i})

        # Connection should be initialized
        assert sqlite_db._connection is not None
        assert sqlite_db._initialized is True

        # All records should be accessible
        count = await sqlite_db.count("test", {})
        assert count == 5

    @pytest.mark.asyncio
    async def test_context_manager(self, temp_db_path):
        """Test using SQLite database as context manager."""
        db = create_database("sqlite", db_path=str(temp_db_path))
        async with db:
            # Use the database
            await db.save("test", {"id": "test-1", "name": "Test"})
            result = await db.get("test", "test-1")
            assert result is not None

        # Database should be closed after context exit
        assert db._connection is None


class TestSQLitePersistence:
    """Test SQLite database persistence."""

    @pytest.mark.asyncio
    async def test_persistence_across_connections(self, temp_db_path):
        """Test that data persists across database connections."""
        # Create database and save data
        db1 = create_database("sqlite", db_path=str(temp_db_path))
        try:
            await db1.save(
                "test", {"id": "persist-1", "name": "Persistent", "value": 42}
            )
        finally:
            await db1.close()

        # Create new connection to same database
        db2 = create_database("sqlite", db_path=str(temp_db_path))
        try:
            # Data should still be there
            retrieved = await db2.get("test", "persist-1")
            assert retrieved is not None
            assert retrieved["name"] == "Persistent"
            assert retrieved["value"] == 42
        finally:
            await db2.close()

    @pytest.mark.asyncio
    async def test_persistence_with_entities(self, temp_db_path):
        """Test entity persistence across connections."""
        # Create context and entity
        db1 = create_database("sqlite", db_path=str(temp_db_path))
        ctx1 = GraphContext(database=db1)
        set_default_context(ctx1)

        try:
            node = await TestNode.create(name="Persistent Node", value=100)
            node_id = node.id
        finally:
            await db1.close()

        # Create new connection
        db2 = create_database("sqlite", db_path=str(temp_db_path))
        ctx2 = GraphContext(database=db2)
        set_default_context(ctx2)

        try:
            # Node should still exist
            retrieved = await TestNode.get(node_id)
            assert retrieved is not None
            assert retrieved.name == "Persistent Node"
            assert retrieved.value == 100
        finally:
            await db2.close()
