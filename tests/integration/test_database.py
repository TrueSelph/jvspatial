"""Integration tests for database persistence functionality."""

import os

import pytest

from jvspatial.core.entities import Node, Object


class TestDatabase:
    """Test database integration functionality."""

    @pytest.mark.asyncio
    async def test_object_persistence(self: "TestDatabase") -> None:
        """Test object persistence functionality."""
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
        assert retrieved is not None
        assert retrieved.id == node.id
        assert retrieved.edge_ids == []
