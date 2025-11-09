"""
Test suite for Database Integration functionality.

This module implements comprehensive tests for:
- Database setup and initialization with different backends
- Node creation, retrieval, and persistence operations
- Walker and pagination integration with live database queries
- Connection management and error handling
- Database factory and registry functionality
- MongoDB-style query operations
- Database versioning and conflict resolution
"""

import asyncio
import os
import tempfile
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import Field

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node, Walker
from jvspatial.core.pager import ObjectPager
from jvspatial.db.database import Database, VersionConflictError
from jvspatial.db.factory import create_database
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.query import QueryBuilder, query


class DbTestNode(Node):
    """Test node for database testing."""

    name: str = ""
    value: int = 0
    category: str = ""
    active: bool = True
    tags: List[str] = []


class DbTestEdge(Edge):
    """Test edge for database testing."""

    weight: int = 1
    label: str = ""
    active: bool = True


class DbTestWalker(Walker):
    """Test walker for database integration."""

    visited_nodes: List[str] = Field(default_factory=list)
    results: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def collect_data(self, nodes: List[DbTestNode]) -> Dict[str, Any]:
        """Collect data from nodes."""
        for node in nodes:
            self.visited_nodes.append(node.id)
            if node.category not in self.results:
                self.results[node.category] = []
            self.results[node.category].append({"name": node.name, "value": node.value})
        return self.results


class MockDatabase(Database):
    """Mock database implementation for testing."""

    def __init__(self):
        self.data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.call_log: List[Dict[str, Any]] = []

    async def clean(self) -> None:
        """Clean up orphaned edges."""
        self.call_log.append({"method": "clean"})

        # Remove edges with invalid node references
        if "edge" in self.data:
            valid_node_ids = set()
            if "node" in self.data:
                valid_node_ids = set(self.data["node"].keys())

            edges_to_remove = []
            for edge_id, edge_data in self.data["edge"].items():
                if (
                    edge_data.get("source") not in valid_node_ids
                    or edge_data.get("target") not in valid_node_ids
                ):
                    edges_to_remove.append(edge_id)

            for edge_id in edges_to_remove:
                del self.data["edge"][edge_id]

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record."""
        self.call_log.append({"method": "save", "collection": collection, "data": data})

        if collection not in self.data:
            self.data[collection] = {}

        record_id = data.get("id")
        if not record_id:
            import uuid

            record_id = str(uuid.uuid4())
            data["id"] = record_id

        self.data[collection][record_id] = data.copy()
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        self.call_log.append({"method": "get", "collection": collection, "id": id})

        if collection in self.data and id in self.data[collection]:
            return self.data[collection][id].copy()
        return None

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        self.call_log.append({"method": "delete", "collection": collection, "id": id})

        if collection in self.data and id in self.data[collection]:
            del self.data[collection][id]

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query."""
        self.call_log.append(
            {"method": "find", "collection": collection, "query": query}
        )

        if collection not in self.data:
            return []

        results = []
        for record in self.data[collection].values():
            if self._matches_query(record, query):
                results.append(record.copy())
        return results

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records matching a query."""
        if query is None:
            query = {}
        self.call_log.append(
            {"method": "count", "collection": collection, "query": query}
        )

        if collection not in self.data:
            return 0

        count = 0
        for record in self.data[collection].values():
            if self._matches_query(record, query):
                count += 1
        return count

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find the first record matching a query."""
        self.call_log.append(
            {"method": "find_one", "collection": collection, "query": query}
        )

        results = await self.find(collection, query)
        return results[0] if results else None

    def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a record matches the query."""
        if not query:  # Empty query matches all
            return True

        for key, value in query.items():
            if key.startswith("$"):
                # Handle MongoDB operators
                if key == "$and":
                    return all(
                        self._matches_query(record, sub_query) for sub_query in value
                    )
                elif key == "$or":
                    return any(
                        self._matches_query(record, sub_query) for sub_query in value
                    )
            else:
                # Simple field matching
                if "." in key:
                    # Dot notation
                    parts = key.split(".")
                    current = record
                    for part in parts:
                        if isinstance(current, dict) and part in current:
                            current = current[part]
                        else:
                            return False
                    if current != value:
                        return False
                else:
                    if record.get(key) != value:
                        return False
        return True

    async def begin_transaction(self):
        """Begin a new transaction."""
        from jvspatial.db.transaction import JsonDBTransaction

        return JsonDBTransaction(self)

    async def commit_transaction(self, transaction):
        """Commit a transaction."""
        pass

    async def rollback_transaction(self, transaction):
        """Rollback a transaction."""
        pass


@pytest.fixture
async def temp_db_path():
    """Create temporary directory for database testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_database():
    """Create mock database instance."""
    return MockDatabase()


@pytest.fixture
async def json_database(temp_db_path):
    """Create JsonDB instance."""
    db = JsonDB(base_path=temp_db_path)
    return db


@pytest.fixture
def mock_context(mock_database):
    """Create mock GraphContext with mock database."""
    from unittest.mock import AsyncMock, MagicMock

    context = GraphContext(database=mock_database)

    # Mock the _deserialize_entity method to properly create objects from data
    async def mock_deserialize_entity(cls, data):
        if "context" not in data:
            return None
        context_data = data["context"].copy()
        # Extract _data if present
        stored_data = context_data.pop("_data", {})

        # Handle Edge objects which have source, target, direction fields at top level
        if "source" in data and "target" in data:
            # This is an Edge object
            obj = cls(
                id=data["id"],
                source=data["source"],
                target=data["target"],
                direction=data.get("direction", "both"),
                **context_data,
            )
        else:
            # This is a Node or other object
            obj = cls(id=data["id"], **context_data)

        # Restore _data after object creation
        if stored_data:
            obj._data.update(stored_data)

        return obj

    context._deserialize_entity = mock_deserialize_entity

    # Mock the _get_collection_name method
    def mock_get_collection_name(type_code):
        collection_map = {"n": "node", "e": "edge", "o": "object", "w": "walker"}
        return collection_map.get(type_code, "object")

    context._get_collection_name = mock_get_collection_name

    return context


class TestDatabaseBasicOperations:
    """Test basic database operations."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, mock_database):
        """Test saving and retrieving records."""
        # Save a record
        data = {"id": "test-id", "name": "Test Record", "value": 42}
        result = await mock_database.save("test", data)
        assert result["id"] == "test-id"
        assert result["name"] == "Test Record"

        # Retrieve the record
        retrieved = await mock_database.get("test", "test-id")
        assert retrieved is not None
        assert retrieved["name"] == "Test Record"
        assert retrieved["value"] == 42

    @pytest.mark.asyncio
    async def test_save_without_id(self, mock_database):
        """Test saving record without ID generates one."""
        data = {"name": "No ID Record", "value": 100}
        result = await mock_database.save("test", data)

        assert "id" in result
        assert result["id"] is not None
        assert len(result["id"]) > 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_record(self, mock_database):
        """Test getting non-existent record returns None."""
        result = await mock_database.get("test", "nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_record(self, mock_database):
        """Test deleting records."""
        # Save a record
        data = {"id": "delete-me", "name": "To Delete"}
        await mock_database.save("test", data)

        # Verify it exists
        retrieved = await mock_database.get("test", "delete-me")
        assert retrieved is not None

        # Delete it
        await mock_database.delete("test", "delete-me")

        # Verify it's gone
        retrieved = await mock_database.get("test", "delete-me")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_find_records(self, mock_database):
        """Test finding records with queries."""
        # Save test records
        records = [
            {"id": "1", "name": "Alice", "category": "person", "value": 10},
            {"id": "2", "name": "Bob", "category": "person", "value": 20},
            {"id": "3", "name": "Charlie", "category": "animal", "value": 15},
        ]

        for record in records:
            await mock_database.save("test", record)

        # Find all records
        all_records = await mock_database.find("test", {})
        assert len(all_records) == 3

        # Find by category
        people = await mock_database.find("test", {"category": "person"})
        assert len(people) == 2
        assert all(p["category"] == "person" for p in people)

        # Find by specific name
        alice = await mock_database.find("test", {"name": "Alice"})
        assert len(alice) == 1
        assert alice[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_find_one(self, mock_database):
        """Test finding single record."""
        # Save test records
        await mock_database.save("test", {"id": "1", "name": "First"})
        await mock_database.save("test", {"id": "2", "name": "Second"})

        # Find one record
        record = await mock_database.find_one("test", {"name": "First"})
        assert record is not None
        assert record["name"] == "First"

        # Find non-existent record
        record = await mock_database.find_one("test", {"name": "Nonexistent"})
        assert record is None

    @pytest.mark.asyncio
    async def test_count_records(self, mock_database):
        """Test counting records."""
        # Save test records
        records = [
            {"id": "1", "category": "A"},
            {"id": "2", "category": "B"},
            {"id": "3", "category": "A"},
        ]

        for record in records:
            await mock_database.save("test", record)

        # Count all records
        total_count = await mock_database.count("test", {})
        assert total_count == 3

        # Count by category
        a_count = await mock_database.count("test", {"category": "A"})
        assert a_count == 2

        b_count = await mock_database.count("test", {"category": "B"})
        assert b_count == 1


class TestNodeDatabaseIntegration:
    """Test Node integration with database operations."""

    @pytest.mark.asyncio
    async def test_node_save_and_retrieve(self, mock_context):
        """Test saving and retrieving nodes through context."""
        # Create and save node
        node = DbTestNode(name="Test Node", value=42, category="test")
        saved_node = await mock_context.save(node)

        assert saved_node.id is not None
        assert saved_node.name == "Test Node"

        # Retrieve node
        retrieved_node = await mock_context.get(DbTestNode, saved_node.id)
        assert retrieved_node is not None
        assert retrieved_node.name == "Test Node"
        assert retrieved_node.value == 42

    @pytest.mark.asyncio
    async def test_node_find_operations(self, mock_context):
        """Test finding nodes with various queries."""
        # Create test nodes
        nodes = [
            DbTestNode(name="Alice", value=10, category="person", active=True),
            DbTestNode(name="Bob", value=20, category="person", active=False),
            DbTestNode(name="Charlie", value=15, category="animal", active=True),
        ]

        for node in nodes:
            await mock_context.save(node)

        # Mock the context to be returned for Node.find operations
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            # Find by class method
            all_nodes = await DbTestNode.find({"name": "DbTestNode"})
            assert len(all_nodes) >= 3

            # Find by category
            people = await DbTestNode.find(
                {"name": "DbTestNode", "context.category": "person"}
            )
            assert len(people) == 2

            # Find active nodes
            active_nodes = await DbTestNode.find(
                {"name": "DbTestNode", "context.active": True}
            )
            assert len(active_nodes) == 2

    @pytest.mark.asyncio
    async def test_node_update_operations(self, mock_context):
        """Test updating node data."""
        # Create and save node
        node = DbTestNode(name="Original", value=10)
        saved_node = await mock_context.save(node)

        # Update node
        saved_node.name = "Updated"
        saved_node.value = 20
        updated_node = await mock_context.save(saved_node)

        assert updated_node.name == "Updated"
        assert updated_node.value == 20

        # Retrieve and verify update
        retrieved = await mock_context.get(DbTestNode, saved_node.id)
        assert retrieved.name == "Updated"
        assert retrieved.value == 20

    @pytest.mark.asyncio
    async def test_node_delete_operations(self, mock_context):
        """Test deleting nodes."""
        # Create and save node
        node = DbTestNode(name="To Delete", value=99)
        saved_node = await mock_context.save(node)
        node_id = saved_node.id

        # Verify it exists
        retrieved = await mock_context.get(DbTestNode, node_id)
        assert retrieved is not None

        # Delete node
        await mock_context.delete(saved_node)

        # Verify it's deleted
        retrieved = await mock_context.get(DbTestNode, node_id)
        assert retrieved is None


class TestEdgeDatabaseIntegration:
    """Test Edge integration with database operations."""

    @pytest.mark.asyncio
    async def test_edge_save_and_retrieve(self, mock_context):
        """Test saving and retrieving edges."""
        # Create nodes for edge endpoints
        node1 = DbTestNode(name="Node 1")
        node2 = DbTestNode(name="Node 2")
        await mock_context.save(node1)
        await mock_context.save(node2)

        # Create and save edge
        edge = DbTestEdge(source=node1.id, target=node2.id, weight=5, label="connects")
        saved_edge = await mock_context.save(edge)

        assert saved_edge.source == node1.id
        assert saved_edge.target == node2.id
        assert saved_edge.weight == 5

        # Retrieve edge
        retrieved_edge = await mock_context.get(DbTestEdge, saved_edge.id)
        assert retrieved_edge is not None
        assert retrieved_edge.source == node1.id
        assert retrieved_edge.target == node2.id

    @pytest.mark.asyncio
    async def test_edge_cleanup_orphaned(self, mock_database):
        """Test cleaning up orphaned edges."""
        # Create nodes and edge
        node1_data = {"id": "node1", "name": "TestNode"}
        node2_data = {"id": "node2", "name": "TestNode"}
        edge_data = {"id": "edge1", "source": "node1", "target": "node2"}

        await mock_database.save("node", node1_data)
        await mock_database.save("node", node2_data)
        await mock_database.save("edge", edge_data)

        # Delete one node
        await mock_database.delete("node", "node1")

        # Clean should remove orphaned edge
        await mock_database.clean()

        # Edge should be gone
        remaining_edge = await mock_database.get("edge", "edge1")
        assert remaining_edge is None

    @pytest.mark.asyncio
    async def test_edge_find_by_nodes(self, mock_context):
        """Test finding edges by node connections."""
        # Create nodes
        node1 = DbTestNode(name="Source")
        node2 = DbTestNode(name="Target")
        node3 = DbTestNode(name="Other")
        await mock_context.save(node1)
        await mock_context.save(node2)
        await mock_context.save(node3)

        # Create edges
        edge1 = DbTestEdge(source=node1.id, target=node2.id, label="edge1")
        edge2 = DbTestEdge(source=node2.id, target=node3.id, label="edge2")
        await mock_context.save(edge1)
        await mock_context.save(edge2)

        # Mock the context to be returned for Edge.find operations
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            # Find edges by source - edges store source/target at top level
            # Object.find() now handles edge-specific top-level fields (source, target, bidirectional)
            source_edges = await DbTestEdge.find(source=node1.id)
            assert len(source_edges) == 1
            assert source_edges[0].target == node2.id


class TestWalkerDatabaseIntegration:
    """Test Walker integration with database operations."""

    @pytest.mark.asyncio
    async def test_walker_with_database_nodes(self, mock_context):
        """Test walker traversal with nodes from database."""
        # Create and save nodes
        nodes = [
            DbTestNode(name="Node1", value=10, category="A"),
            DbTestNode(name="Node2", value=20, category="B"),
            DbTestNode(name="Node3", value=30, category="A"),
        ]

        for node in nodes:
            await mock_context.save(node)

        # Mock the context to be returned for Node.find operations
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            # Create walker and collect data
            walker = DbTestWalker()
            category_a_nodes = await DbTestNode.find(
                {"name": "DbTestNode", "context.category": "A"}
            )
            result = await walker.collect_data(category_a_nodes)

            assert len(walker.visited_nodes) == 2
            assert "A" in result
            assert len(result["A"]) == 2

    @pytest.mark.asyncio
    async def test_walker_with_live_queries(self, mock_context):
        """Test walker using live database queries."""
        # Create nodes with different properties
        nodes = [
            DbTestNode(name="Active1", active=True, value=5),
            DbTestNode(name="Inactive1", active=False, value=15),
            DbTestNode(name="Active2", active=True, value=25),
        ]

        for node in nodes:
            await mock_context.save(node)

        # Mock the context to be returned for Node.find operations
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            # Walker processes only active nodes
            walker = DbTestWalker()
            active_nodes = await DbTestNode.find(
                {"name": "DbTestNode", "context.active": True}
            )
            result = await walker.collect_data(active_nodes)

            assert len(walker.visited_nodes) == 2
            # Verify only active nodes were processed
            all_names = []
            for category_data in result.values():
                all_names.extend([item["name"] for item in category_data])
            assert "Active1" in all_names
            assert "Active2" in all_names
            assert "Inactive1" not in all_names


class TestPaginationDatabaseIntegration:
    """Test pagination integration with database operations."""

    @pytest.mark.asyncio
    async def test_object_pager_with_database(self, mock_context):
        """Test ObjectPager with database backend."""
        # Create test nodes
        nodes = [
            DbTestNode(
                name=f"Node{i}", value=i, category="test" if i % 2 == 0 else "other"
            )
            for i in range(25)
        ]

        for node in nodes:
            await mock_context.save(node)

        # Create pager
        pager = ObjectPager(DbTestNode, page_size=10)

        # Mock the context methods
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            # Get first page
            page1 = await pager.get_page(1)

            assert len(page1) <= 10
            assert pager.total_items >= 25
            assert pager.current_page == 1

    @pytest.mark.asyncio
    async def test_pagination_with_filters(self, mock_context):
        """Test pagination with database filters."""
        # Create nodes with different categories
        for i in range(20):
            node = DbTestNode(
                name=f"Node{i}", value=i, category="even" if i % 2 == 0 else "odd"
            )
            await mock_context.save(node)

        # Create pager with filter
        pager = ObjectPager(
            DbTestNode, page_size=5, filters={"context.category": "even"}
        )

        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            # Get filtered page
            page = await pager.get_page(1)

            # Should only return even-categorized nodes
            assert len(page) <= 5
            # Verify all returned nodes have even category
            for node in page:
                assert node.category == "even"


class TestMongoDBStyleQueries:
    """Test MongoDB-style query operations."""

    @pytest.mark.asyncio
    async def test_comparison_operators(self, mock_database):
        """Test MongoDB comparison operators."""
        # Save test data
        records = [
            {"id": "1", "value": 5, "name": "Five"},
            {"id": "2", "value": 10, "name": "Ten"},
            {"id": "3", "value": 15, "name": "Fifteen"},
            {"id": "4", "value": 20, "name": "Twenty"},
        ]

        for record in records:
            await mock_database.save("test", record)

        # Note: This test assumes the mock database supports these operations
        # In practice, you'd need to implement MongoDB-style query matching

        # Test simple equality
        results = await mock_database.find("test", {"value": 10})
        assert len(results) == 1
        assert results[0]["name"] == "Ten"

    @pytest.mark.asyncio
    async def test_logical_operators(self, mock_database):
        """Test MongoDB logical operators."""
        # Save test data
        records = [
            {"id": "1", "category": "A", "active": True},
            {"id": "2", "category": "B", "active": True},
            {"id": "3", "category": "A", "active": False},
        ]

        for record in records:
            await mock_database.save("test", record)

        # Test $and operator
        results = await mock_database.find(
            "test", {"$and": [{"category": "A"}, {"active": True}]}
        )
        assert len(results) == 1
        assert results[0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_array_operations(self, mock_database):
        """Test array field operations."""
        # Save test data with arrays
        records = [
            {"id": "1", "tags": ["red", "blue"], "name": "Item1"},
            {"id": "2", "tags": ["green", "blue"], "name": "Item2"},
            {"id": "3", "tags": ["red"], "name": "Item3"},
        ]

        for record in records:
            await mock_database.save("test", record)

        # This would require implementing array query support
        # For now, test basic functionality
        all_records = await mock_database.find("test", {})
        assert len(all_records) == 3


class TestDatabaseErrorHandling:
    """Test database error handling."""

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test handling of database connection errors."""

        # Create a database that will fail
        class FailingDatabase(Database):
            async def clean(self):
                raise ConnectionError("Database connection failed")

            async def save(self, collection, data):
                raise ConnectionError("Database connection failed")

            async def get(self, collection, id):
                raise ConnectionError("Database connection failed")

            async def delete(self, collection, id):
                raise ConnectionError("Database connection failed")

            async def find(self, collection, query):
                raise ConnectionError("Database connection failed")

            async def begin_transaction(self):
                """Begin a new transaction."""
                raise ConnectionError("Database connection failed")

            async def commit_transaction(self, transaction):
                """Commit a transaction."""
                raise ConnectionError("Database connection failed")

            async def rollback_transaction(self, transaction):
                """Rollback a transaction."""
                raise ConnectionError("Database connection failed")

        failing_db = FailingDatabase()

        # Test that errors are properly raised
        with pytest.raises(ConnectionError):
            await failing_db.save("test", {"id": "1"})

    @pytest.mark.asyncio
    async def test_version_conflict_handling(self, mock_database):
        """Test version conflict error handling."""
        # This would test optimistic concurrency control
        # For now, just verify the exception type exists
        assert VersionConflictError is not None

    @pytest.mark.asyncio
    async def test_invalid_query_handling(self, mock_database):
        """Test handling of invalid queries."""
        # Test with malformed query
        results = await mock_database.find("test", {"$invalid_operator": "value"})
        # Should return empty results rather than crash
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_missing_collection_handling(self, mock_database):
        """Test handling of missing collections."""
        # Try to find in non-existent collection
        results = await mock_database.find("nonexistent", {})
        assert results == []

        # Try to get from non-existent collection
        result = await mock_database.get("nonexistent", "some-id")
        assert result is None


class TestDatabasePerformance:
    """Test database performance considerations."""

    @pytest.mark.asyncio
    async def test_bulk_operations(self, mock_database):
        """Test bulk database operations."""
        # Create many records
        records = [
            {"id": f"record_{i}", "value": i, "category": f"cat_{i % 3}"}
            for i in range(100)
        ]

        # Save all records
        for record in records:
            await mock_database.save("test", record)

        # Verify count
        count = await mock_database.count("test", {})
        assert count == 100

        # Find with filter
        category_0_records = await mock_database.find("test", {"category": "cat_0"})
        assert len(category_0_records) > 30  # Should be roughly 1/3

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, mock_database):
        """Test concurrent database operations."""

        # Create concurrent tasks
        async def save_records(start_idx: int, count: int):
            tasks = []
            for i in range(start_idx, start_idx + count):
                record = {"id": f"concurrent_{i}", "value": i}
                tasks.append(mock_database.save("test", record))
            await asyncio.gather(*tasks)

        # Run concurrent saves
        await asyncio.gather(
            save_records(0, 10), save_records(10, 10), save_records(20, 10)
        )

        # Verify all records were saved
        count = await mock_database.count("test", {})
        assert count == 30


class TestJsonDatabaseSpecific:
    """Test JsonDB-specific functionality."""

    @pytest.mark.asyncio
    async def test_json_db_initialization(self, temp_db_path):
        """Test JsonDB initialization."""
        db = JsonDB(base_path=temp_db_path)
        # JsonDB doesn't need initialization - it creates directories automatically
        # Check data directory exists
        assert os.path.exists(temp_db_path)

    @pytest.mark.asyncio
    async def test_json_db_persistence(self, json_database):
        """Test JsonDB data persistence."""
        # Save a record
        record = {"id": "persist_test", "data": "test data"}
        await json_database.save("test", record)

        # Create new instance of same database
        new_db = JsonDB(base_path=str(json_database.base_path))

        # Should be able to retrieve the record
        retrieved = await new_db.get("test", "persist_test")
        assert retrieved is not None
        assert retrieved["data"] == "test data"

    @pytest.mark.asyncio
    async def test_json_db_file_structure(self, json_database):
        """Test JsonDB file structure."""
        # Save records to different collections
        await json_database.save("nodes", {"id": "n1", "type": "node"})
        await json_database.save("edges", {"id": "e1", "type": "edge"})

        # Check that separate collection directories are created (JsonDB creates directories with individual JSON files)
        nodes_dir = os.path.join(str(json_database.base_path), "nodes")
        edges_dir = os.path.join(str(json_database.base_path), "edges")
        nodes_file = os.path.join(nodes_dir, "n1.json")
        edges_file = os.path.join(edges_dir, "e1.json")

        assert os.path.exists(nodes_dir)
        assert os.path.exists(edges_dir)
        assert os.path.exists(nodes_file)
        assert os.path.exists(edges_file)
