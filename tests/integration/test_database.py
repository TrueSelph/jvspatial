import pytest
import os
from jvspatial.core.entities import Object, Node

class TestDatabase:
    @pytest.mark.asyncio
    async def test_object_persistence(self):
        # Set up in-memory database
        os.environ["JVSPATIAL_DB_TYPE"] = "json"
        os.environ["JVSPATIAL_DB_PATH"] = ":memory:"
        
        # Reset database instance
        Object.set_db(None)
        
        # Create and save object
        node = Node()
        await node.save()
        
        # Retrieve object
        retrieved = await Node.get(node.id)
        assert retrieved.id == node.id
        assert retrieved.edge_ids == []