"""Test suite for MongoDB database implementation.

Tests the simplified MongoDB database functionality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.db.mongodb import MongoDB
from jvspatial.exceptions import DatabaseError


class TestMongoDBBasicOperations:
    """Test basic MongoDB operations."""

    @pytest.fixture
    def mongodb(self):
        """Create MongoDB instance for testing."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient") as mock_client_class:
            mock_client = MagicMock()
            mock_db = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__getitem__.return_value = mock_db

            db = MongoDB(uri="mongodb://localhost:27017/test", db_name="test_db")
            db._client = mock_client
            db._db = mock_db
            return db

    @pytest.fixture
    def mock_collection(self, mongodb):
        """Create mock collection for testing."""
        mock_collection = AsyncMock()
        mongodb._db.__getitem__.return_value = mock_collection
        return mock_collection

    @pytest.mark.asyncio
    async def test_mongodb_initialization(self):
        """Test MongoDB initialization."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient"):
            db = MongoDB(uri="mongodb://test:27017", db_name="test_db")
            assert db.uri == "mongodb://test:27017"
            assert db.db_name == "test_db"
            assert db._client is None
            assert db._db is None

    @pytest.mark.asyncio
    async def test_save_record(self, mongodb, mock_collection):
        """Test saving a record."""
        test_data = {"id": "test_id", "name": "test_record", "value": 42}

        mock_collection.replace_one.return_value = AsyncMock()

        result = await mongodb.save("test_collection", test_data)

        assert result == test_data
        assert result["_id"] == "test_id"  # MongoDB uses _id
        mock_collection.replace_one.assert_called_once_with(
            {"_id": "test_id"}, test_data, upsert=True
        )

    @pytest.mark.asyncio
    async def test_save_record_without_id(self, mongodb, mock_collection):
        """Test saving a record without ID (generates UUID)."""
        test_data = {"name": "test_record", "value": 42}

        mock_collection.replace_one.return_value = AsyncMock()

        with patch("uuid.uuid4", return_value=MagicMock(hex="test-uuid")):
            result = await mongodb.save("test_collection", test_data)

        assert result["_id"] is not None
        mock_collection.replace_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_record(self, mongodb, mock_collection):
        """Test retrieving a record."""
        test_data = {"_id": "test_id", "name": "test_record", "value": 42}

        mock_collection.find_one.return_value = test_data

        result = await mongodb.get("test_collection", "test_id")

        assert result == test_data
        mock_collection.find_one.assert_called_once_with({"_id": "test_id"})

    @pytest.mark.asyncio
    async def test_get_nonexistent_record(self, mongodb, mock_collection):
        """Test retrieving a non-existent record."""
        mock_collection.find_one.return_value = None

        result = await mongodb.get("test_collection", "nonexistent_id")

        assert result is None
        mock_collection.find_one.assert_called_once_with({"_id": "nonexistent_id"})

    @pytest.mark.asyncio
    async def test_delete_record(self, mongodb, mock_collection):
        """Test deleting a record."""
        mock_collection.delete_one.return_value = AsyncMock()

        await mongodb.delete("test_collection", "test_id")

        mock_collection.delete_one.assert_called_once_with({"_id": "test_id"})

    @pytest.mark.asyncio
    async def test_find_records(self, mongodb, mock_collection):
        """Test finding records with query."""
        test_data = [
            {"_id": "id1", "name": "record1", "value": 10},
            {"_id": "id2", "name": "record2", "value": 20},
        ]

        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = test_data
        mock_collection.find = MagicMock(return_value=mock_cursor)

        query = {"value": {"$gte": 10}}
        result = await mongodb.find("test_collection", query)

        assert result == test_data
        mock_collection.find.assert_called_once_with(query)
        mock_cursor.to_list.assert_called_once_with(length=None)

    @pytest.mark.asyncio
    async def test_find_all_records(self, mongodb, mock_collection):
        """Test finding all records (empty query)."""
        test_data = [
            {"_id": "id1", "name": "record1"},
            {"_id": "id2", "name": "record2"},
        ]

        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = test_data
        mock_collection.find = MagicMock(return_value=mock_cursor)

        result = await mongodb.find("test_collection", {})

        assert result == test_data
        mock_collection.find.assert_called_once_with({})

    @pytest.mark.asyncio
    async def test_close_connection(self, mongodb):
        """Test closing database connection."""
        mock_client = MagicMock()
        mongodb._client = mock_client
        mongodb._db = MagicMock()

        await mongodb.close()

        mock_client.close.assert_called_once()
        assert mongodb._client is None
        assert mongodb._db is None


class TestMongoDBErrorHandling:
    """Test MongoDB error handling."""

    @pytest.fixture
    def mongodb(self):
        """Create MongoDB instance for testing."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient") as mock_client_class:
            mock_client = MagicMock()
            mock_db = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__getitem__.return_value = mock_db

            db = MongoDB(uri="mongodb://localhost:27017/test", db_name="test_db")
            db._client = mock_client
            db._db = mock_db
            return db

    @pytest.mark.asyncio
    async def test_save_error_handling(self, mongodb):
        """Test error handling during save operation."""
        from pymongo.errors import PyMongoError

        mock_collection = AsyncMock()
        mock_collection.replace_one.side_effect = PyMongoError("Connection failed")

        mongodb._db = MagicMock()
        mongodb._db.__getitem__.return_value = mock_collection

        test_data = {"id": "test_id", "name": "test"}

        with pytest.raises(DatabaseError) as exc_info:
            await mongodb.save("test_collection", test_data)

        assert "MongoDB save error" in str(exc_info.value)
        assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_error_handling(self, mongodb):
        """Test error handling during get operation."""
        from pymongo.errors import PyMongoError

        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = PyMongoError("Query failed")

        mongodb._db = MagicMock()
        mongodb._db.__getitem__.return_value = mock_collection

        with pytest.raises(DatabaseError) as exc_info:
            await mongodb.get("test_collection", "test_id")

        assert "MongoDB get error" in str(exc_info.value)
        assert "Query failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_error_handling(self, mongodb):
        """Test error handling during delete operation."""
        from pymongo.errors import PyMongoError

        mock_collection = AsyncMock()
        mock_collection.delete_one.side_effect = PyMongoError("Delete failed")

        mongodb._db = MagicMock()
        mongodb._db.__getitem__.return_value = mock_collection

        with pytest.raises(DatabaseError) as exc_info:
            await mongodb.delete("test_collection", "test_id")

        assert "MongoDB delete error" in str(exc_info.value)
        assert "Delete failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_find_error_handling(self, mongodb):
        """Test error handling during find operation."""
        from pymongo.errors import PyMongoError

        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list.side_effect = PyMongoError("Find failed")
        mock_collection.find = MagicMock(return_value=mock_cursor)

        mongodb._db.__getitem__.return_value = mock_collection

        with pytest.raises(DatabaseError) as exc_info:
            await mongodb.find("test_collection", {"name": "test"})

        assert "MongoDB find error" in str(exc_info.value)
        assert "Find failed" in str(exc_info.value)


class TestMongoDBConnection:
    """Test MongoDB connection handling."""

    @pytest.mark.asyncio
    async def test_connection_lazy_initialization(self):
        """Test that connection is only established when needed."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient") as mock_client_class:
            db = MongoDB(uri="mongodb://localhost:27017/test", db_name="test_db")

            # Connection should not be established yet
            assert db._client is None
            assert db._db is None

            # Mock the client and database
            mock_client = MagicMock()
            mock_db = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__getitem__.return_value = mock_db

            # Mock collection operations
            mock_collection = AsyncMock()
            mock_collection.find_one.return_value = {"_id": "test", "name": "test"}
            mock_db.__getitem__.return_value = mock_collection

            # Now perform an operation that requires connection
            result = await db.get("test_collection", "test_id")

            # Connection should now be established
            assert db._client is not None
            assert db._db is not None
            mock_client_class.assert_called_once_with("mongodb://localhost:27017/test")
            assert result is not None

    @pytest.mark.asyncio
    async def test_multiple_operations_reuse_connection(self):
        """Test that multiple operations reuse the same connection."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient") as mock_client_class:
            db = MongoDB(uri="mongodb://localhost:27017/test", db_name="test_db")

            # Mock the client and database
            mock_client = MagicMock()
            mock_db = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__getitem__.return_value = mock_db

            # Mock collection operations
            mock_collection = AsyncMock()
            mock_collection.find_one.return_value = {"_id": "test", "name": "test"}
            mock_collection.replace_one.return_value = AsyncMock()
            mock_db.__getitem__.return_value = mock_collection

            # Perform multiple operations
            await db.get("test_collection", "test_id")
            await db.save("test_collection", {"id": "test", "name": "test"})

            # Client should only be created once
            assert mock_client_class.call_count == 1
            assert db._client is not None
            assert db._db is not None


class TestMongoDBIntegration:
    """Test MongoDB integration scenarios."""

    @pytest.fixture
    def mongodb(self):
        """Create MongoDB instance for testing."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient") as mock_client_class:
            mock_client = MagicMock()
            mock_db = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__getitem__.return_value = mock_db

            db = MongoDB(uri="mongodb://localhost:27017/test", db_name="test_db")
            db._client = mock_client
            db._db = mock_db
            return db

    @pytest.fixture
    def mock_collection(self, mongodb):
        """Create mock collection for testing."""
        mock_collection = AsyncMock()
        mongodb._db.__getitem__.return_value = mock_collection
        return mock_collection

    @pytest.mark.asyncio
    async def test_crud_workflow(self, mongodb, mock_collection):
        """Test complete CRUD workflow."""
        # Create
        test_data = {"id": "test_id", "name": "test_record", "value": 42}
        mock_collection.replace_one.return_value = AsyncMock()

        saved_data = await mongodb.save("test_collection", test_data)
        assert saved_data == test_data

        # Read
        mock_collection.find_one.return_value = test_data
        retrieved_data = await mongodb.get("test_collection", "test_id")
        assert retrieved_data == test_data

        # Update
        updated_data = {"id": "test_id", "name": "updated_record", "value": 100}
        mock_collection.replace_one.return_value = AsyncMock()

        saved_updated = await mongodb.save("test_collection", updated_data)
        assert saved_updated == updated_data

        # Delete
        mock_collection.delete_one.return_value = AsyncMock()
        await mongodb.delete("test_collection", "test_id")

        # Verify all operations were called
        assert mock_collection.replace_one.call_count == 2
        assert mock_collection.find_one.call_count == 1
        assert mock_collection.delete_one.call_count == 1

    @pytest.mark.asyncio
    async def test_query_operations(self, mongodb, mock_collection):
        """Test various query operations."""
        # Mock cursor and results
        mock_cursor = AsyncMock()
        test_results = [
            {"_id": "id1", "name": "record1", "value": 10},
            {"_id": "id2", "name": "record2", "value": 20},
            {"_id": "id3", "name": "record3", "value": 30},
        ]
        mock_cursor.to_list.return_value = test_results
        mock_collection.find = MagicMock(return_value=mock_cursor)

        # Test different query types
        queries = [
            {},  # Find all
            {"name": "record1"},  # Exact match
            {"value": {"$gte": 20}},  # Range query
            {"name": {"$regex": "record"}},  # Regex query
        ]

        for query in queries:
            result = await mongodb.find("test_collection", query)
            assert result == test_results
            mock_collection.find.assert_called_with(query)

        # Verify find was called for each query
        assert mock_collection.find.call_count == len(queries)

    @pytest.mark.asyncio
    async def test_collection_isolation(self, mongodb, mock_collection):
        """Test that different collections are isolated."""
        # Mock different collections
        mock_collection1 = AsyncMock()
        mock_collection2 = AsyncMock()

        mongodb._db = MagicMock()
        mongodb._db.__getitem__.side_effect = lambda name: {
            "collection1": mock_collection1,
            "collection2": mock_collection2,
        }[name]

        # Test operations on different collections
        mock_collection1.replace_one.return_value = AsyncMock()
        mock_collection2.replace_one.return_value = AsyncMock()

        await mongodb.save("collection1", {"id": "test1", "name": "test1"})
        await mongodb.save("collection2", {"id": "test2", "name": "test2"})

        # Verify each collection was accessed correctly
        mock_collection1.replace_one.assert_called_once()
        mock_collection2.replace_one.assert_called_once()
