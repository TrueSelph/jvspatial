import pytest
from jvspatial.core.entities import Node

class TestNode:
    @pytest.mark.asyncio
    async def test_node_creation(self):
        node = Node()
        assert node.id.startswith("n:Node:")
        assert node.edge_ids == []

    @pytest.mark.asyncio
    async def test_node_connection(self):
        node1 = Node()
        node2 = Node()
        await node1.connect(node2)
        assert len(node1.edge_ids) == 1
        assert len(node2.edge_ids) == 1
        assert node1.edge_ids == node2.edge_ids