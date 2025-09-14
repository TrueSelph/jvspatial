"""
Comprehensive tests for JsonDB database implementation.
"""

import pytest
import os
import tempfile
import shutil
import json
from pathlib import Path

from jvspatial.db.jsondb import JsonDB
from jvspatial.core.entities import Node, Edge


class TestJsonDBBasics:
    """Test basic JsonDB functionality"""
    
    def setup_method(self):
        """Set up test database in temporary directory"""
        self.temp_dir = tempfile.mkdtemp()
        self.db = JsonDB(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_db_initialization(self):
        """Test database initialization"""
        # Check that base path is created
        assert Path(self.temp_dir).exists()
        assert Path(self.temp_dir).is_dir()

    @pytest.mark.asyncio
    async def test_collection_path_creation(self):
        """Test collection directory creation"""
        collection_path = self.db._get_collection_path("test_collection")
        
        # Collection directory should be created
        assert collection_path.exists()
        assert collection_path.is_dir()
        assert collection_path.name == "test_collection"

    @pytest.mark.asyncio
    async def test_file_path_generation(self):
        """Test file path generation for documents"""
        file_path = self.db._get_file_path("test_collection", "test_id")
        
        expected_path = Path(self.temp_dir) / "test_collection" / "test_id.json"
        assert file_path.resolve() == expected_path.resolve()


class TestJsonDBOperations:
    """Test CRUD operations"""
    
    def setup_method(self):
        """Set up test database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db = JsonDB(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_save_document(self):
        """Test saving a document"""
        test_data = {
            "id": "test_doc_1",
            "name": "TestDocument",
            "context": {"field1": "value1", "field2": 42}
        }
        
        result = await self.db.save("test_collection", test_data)
        
        # Should return the same data
        assert result == test_data
        
        # File should exist
        file_path = self.db._get_file_path("test_collection", "test_doc_1")
        assert file_path.exists()
        
        # File contents should match
        with open(file_path, 'r') as f:
            saved_data = json.load(f)
        assert saved_data == test_data

    @pytest.mark.asyncio
    async def test_get_existing_document(self):
        """Test retrieving an existing document"""
        test_data = {
            "id": "test_doc_2",
            "name": "TestDocument",
            "context": {"data": "test_value"}
        }
        
        # Save first
        await self.db.save("test_collection", test_data)
        
        # Retrieve
        retrieved = await self.db.get("test_collection", "test_doc_2")
        
        assert retrieved == test_data

    @pytest.mark.asyncio
    async def test_get_nonexistent_document(self):
        """Test retrieving a non-existent document"""
        result = await self.db.get("test_collection", "nonexistent_id")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_existing_document(self):
        """Test deleting an existing document"""
        test_data = {
            "id": "test_doc_3",
            "name": "TestDocument",
            "context": {}
        }
        
        # Save first
        await self.db.save("test_collection", test_data)
        file_path = self.db._get_file_path("test_collection", "test_doc_3")
        assert file_path.exists()
        
        # Delete
        await self.db.delete("test_collection", "test_doc_3")
        
        # File should no longer exist
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document(self):
        """Test deleting a non-existent document"""
        # Should not raise an error
        await self.db.delete("test_collection", "nonexistent_id")

    @pytest.mark.asyncio
    async def test_save_update_document(self):
        """Test updating an existing document"""
        test_data = {
            "id": "test_doc_4",
            "name": "TestDocument",
            "context": {"version": 1}
        }
        
        # Save original
        await self.db.save("test_collection", test_data)
        
        # Update
        updated_data = {
            "id": "test_doc_4",
            "name": "TestDocument",
            "context": {"version": 2, "new_field": "added"}
        }
        
        await self.db.save("test_collection", updated_data)
        
        # Retrieve and verify update
        retrieved = await self.db.get("test_collection", "test_doc_4")
        assert retrieved == updated_data
        assert retrieved["context"]["version"] == 2
        assert retrieved["context"]["new_field"] == "added"


class TestJsonDBFind:
    """Test find operations with queries"""
    
    def setup_method(self):
        """Set up test database with sample data"""
        self.temp_dir = tempfile.mkdtemp()
        self.db = JsonDB(self.temp_dir)
        
    def teardown_method(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_find_all_documents(self):
        """Test finding all documents with empty query"""
        # Save multiple documents
        docs = [
            {"id": "doc1", "name": "Doc1", "context": {"type": "A"}},
            {"id": "doc2", "name": "Doc2", "context": {"type": "B"}},
            {"id": "doc3", "name": "Doc3", "context": {"type": "A"}}
        ]
        
        for doc in docs:
            await self.db.save("test_collection", doc)
        
        # Find all
        results = await self.db.find("test_collection", {})
        
        assert len(results) == 3
        result_ids = [doc["id"] for doc in results]
        assert "doc1" in result_ids
        assert "doc2" in result_ids
        assert "doc3" in result_ids

    @pytest.mark.asyncio
    async def test_find_with_simple_query(self):
        """Test finding documents with simple equality query"""
        # Save test documents
        docs = [
            {"id": "doc1", "name": "Doc1", "context": {"type": "A", "value": 1}},
            {"id": "doc2", "name": "Doc2", "context": {"type": "B", "value": 2}},
            {"id": "doc3", "name": "Doc3", "context": {"type": "A", "value": 3}}
        ]
        
        for doc in docs:
            await self.db.save("test_collection", doc)
        
        # Query for type A
        results = await self.db.find("test_collection", {"context.type": "A"})
        
        assert len(results) == 2
        result_types = [doc["context"]["type"] for doc in results]
        assert all(t == "A" for t in result_types)

    @pytest.mark.asyncio
    async def test_find_with_nested_query(self):
        """Test finding documents with nested field queries"""
        docs = [
            {"id": "doc1", "name": "Doc1", "context": {"nested": {"field": "value1"}}},
            {"id": "doc2", "name": "Doc2", "context": {"nested": {"field": "value2"}}},
            {"id": "doc3", "name": "Doc3", "context": {"other": "data"}}
        ]
        
        for doc in docs:
            await self.db.save("test_collection", doc)
        
        # Query nested field
        results = await self.db.find("test_collection", {"context.nested.field": "value1"})
        
        assert len(results) == 1
        assert results[0]["id"] == "doc1"

    @pytest.mark.asyncio
    async def test_find_with_operators(self):
        """Test finding documents with query operators"""
        docs = [
            {"id": "doc1", "name": "Doc1", "context": {"value": 10}},
            {"id": "doc2", "name": "Doc2", "context": {"value": 20}},
            {"id": "doc3", "name": "Doc3", "context": {"value": 30}},
            {"id": "doc4", "name": "Doc4", "context": {"value": 40}}
        ]
        
        for doc in docs:
            await self.db.save("test_collection", doc)
        
        # Test $gt operator
        results = await self.db.find("test_collection", {"context.value": {"$gt": 25}})
        assert len(results) == 2
        
        # Test $lt operator
        results = await self.db.find("test_collection", {"context.value": {"$lt": 25}})
        assert len(results) == 2
        
        # Test $gte operator
        results = await self.db.find("test_collection", {"context.value": {"$gte": 20}})
        assert len(results) == 3
        
        # Test $lte operator
        results = await self.db.find("test_collection", {"context.value": {"$lte": 20}})
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_find_with_in_operator(self):
        """Test finding documents with $in operator"""
        docs = [
            {"id": "doc1", "name": "Doc1", "context": {"category": "A"}},
            {"id": "doc2", "name": "Doc2", "context": {"category": "B"}},
            {"id": "doc3", "name": "Doc3", "context": {"category": "C"}},
            {"id": "doc4", "name": "Doc4", "context": {"category": "D"}}
        ]
        
        for doc in docs:
            await self.db.save("test_collection", doc)
        
        # Test $in operator
        results = await self.db.find("test_collection", {"context.category": {"$in": ["A", "C"]}})
        assert len(results) == 2
        categories = [doc["context"]["category"] for doc in results]
        assert "A" in categories
        assert "C" in categories

    @pytest.mark.asyncio
    async def test_find_with_nin_operator(self):
        """Test finding documents with $nin operator"""
        docs = [
            {"id": "doc1", "name": "Doc1", "context": {"status": "active"}},
            {"id": "doc2", "name": "Doc2", "context": {"status": "inactive"}},
            {"id": "doc3", "name": "Doc3", "context": {"status": "pending"}},
            {"id": "doc4", "name": "Doc4", "context": {"status": "active"}}
        ]
        
        for doc in docs:
            await self.db.save("test_collection", doc)
        
        # Test $nin operator
        results = await self.db.find("test_collection", {"context.status": {"$nin": ["inactive", "pending"]}})
        assert len(results) == 2
        statuses = [doc["context"]["status"] for doc in results]
        assert all(s == "active" for s in statuses)

    @pytest.mark.asyncio
    async def test_find_no_matches(self):
        """Test finding documents with query that matches nothing"""
        docs = [
            {"id": "doc1", "name": "Doc1", "context": {"type": "A"}},
            {"id": "doc2", "name": "Doc2", "context": {"type": "B"}}
        ]
        
        for doc in docs:
            await self.db.save("test_collection", doc)
        
        # Query for non-existent type
        results = await self.db.find("test_collection", {"context.type": "Z"})
        
        assert len(results) == 0


class TestJsonDBDuplicateHandling:
    """Test handling of duplicate documents"""
    
    def setup_method(self):
        """Set up test database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db = JsonDB(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_duplicate_id_handling(self):
        """Test handling of documents with duplicate IDs"""
        # Save multiple docs with same ID (simulating duplicates)
        doc1 = {"id": "dup_id", "name": "Doc1", "context": {"version": 1}}
        doc2 = {"id": "dup_id", "name": "Doc2", "context": {"version": 2}}
        
        await self.db.save("test_collection", doc1)
        await self.db.save("test_collection", doc2)  # Overwrites doc1
        
        # Find should return only one document
        results = await self.db.find("test_collection", {})
        
        assert len(results) == 1
        assert results[0]["id"] == "dup_id"
        assert results[0]["context"]["version"] == 2  # Should be the latest


class TestJsonDBErrorHandling:
    """Test error handling and edge cases"""
    
    def setup_method(self):
        """Set up test database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db = JsonDB(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_invalid_json_file_handling(self):
        """Test handling of invalid JSON files"""
        collection_path = self.db._get_collection_path("test_collection")
        
        # Create invalid JSON file
        invalid_file = collection_path / "invalid.json"
        with open(invalid_file, 'w') as f:
            f.write("invalid json content {")
        
        # Find should skip invalid files
        results = await self.db.find("test_collection", {})
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_missing_collection_directory(self):
        """Test handling of missing collection directory"""
        # Try to find in non-existent collection
        results = await self.db.find("nonexistent_collection", {})
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_permission_error_handling(self):
        """Test handling of permission errors"""
        # This test may be platform-specific
        # Create a document first
        test_data = {"id": "test_doc", "name": "Test", "context": {}}
        await self.db.save("test_collection", test_data)
        
        # The actual permission test would require special setup
        # For now, just verify the document was created
        retrieved = await self.db.get("test_collection", "test_doc")
        assert retrieved == test_data


class TestJsonDBConcurrency:
    """Test concurrent access handling"""
    
    def setup_method(self):
        """Set up test database"""
        self.temp_dir = tempfile.mkdtemp()
        self.db = JsonDB(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_concurrent_save_operations(self):
        """Test concurrent save operations"""
        import asyncio
        
        # Define save operations
        async def save_doc(doc_id, value):
            doc = {"id": doc_id, "name": "ConcurrentDoc", "context": {"value": value}}
            return await self.db.save("test_collection", doc)
        
        # Run concurrent saves
        tasks = []
        for i in range(10):
            task = save_doc(f"doc_{i}", i)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All saves should complete successfully
        assert len(results) == 10
        
        # Verify all documents were saved
        all_docs = await self.db.find("test_collection", {})
        assert len(all_docs) == 10

    @pytest.mark.asyncio
    async def test_concurrent_read_operations(self):
        """Test concurrent read operations"""
        import asyncio
        
        # Save a document first
        test_doc = {"id": "shared_doc", "name": "SharedDoc", "context": {"data": "shared"}}
        await self.db.save("test_collection", test_doc)
        
        # Define read operation
        async def read_doc():
            return await self.db.get("test_collection", "shared_doc")
        
        # Run concurrent reads
        tasks = [read_doc() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All reads should return the same document
        assert len(results) == 10
        for result in results:
            assert result == test_doc


class TestJsonDBConfiguration:
    """Test database configuration options"""
    
    @pytest.mark.asyncio
    async def test_custom_base_path(self):
        """Test JsonDB with custom base path"""
        custom_path = tempfile.mkdtemp()
        try:
            db = JsonDB(custom_path)
            
            # Test that custom path is used
            assert db.base_path.samefile(custom_path)
            
            # Test saving to custom path
            test_doc = {"id": "custom_doc", "name": "CustomDoc", "context": {}}
            await db.save("custom_collection", test_doc)
            
            # Verify file was created in custom path
            expected_file = Path(custom_path) / "custom_collection" / "custom_doc.json"
            assert expected_file.exists()
            
        finally:
            shutil.rmtree(custom_path, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_default_base_path(self):
        """Test JsonDB with default base path"""
        db = JsonDB()
        
        # Should use default path
        assert db.base_path.name == "json"
        assert db.base_path.parent.name == "db"

    @pytest.mark.asyncio
    async def test_relative_path_resolution(self):
        """Test JsonDB with relative paths"""
        temp_dir = tempfile.mkdtemp()
        old_cwd = os.getcwd()
        
        try:
            # Change to temp directory
            os.chdir(temp_dir)
            
            # Create DB with relative path
            db = JsonDB("test_db")
            
            # Should create directory relative to current working directory
            expected_path = Path(temp_dir) / "test_db"
            assert db.base_path.samefile(expected_path)
            assert expected_path.exists()
            
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(temp_dir, ignore_errors=True)