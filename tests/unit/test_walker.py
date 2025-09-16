"""Unit tests for basic Walker functionality."""

import pytest

from jvspatial.core.entities import Node, Walker, on_visit


class TestWalker:
    """Test basic Walker class functionality."""

    @pytest.mark.asyncio
    async def test_walker_traversal(self: "TestWalker") -> None:
        """Test walker traversal functionality."""

        class City(Node):
            name: str = "TestCity"

        class Tourist(Walker):
            @on_visit(City)
            async def visit_city(self: "Tourist", city: City) -> None:
                self.response["visited"] = True

        city = City()
        tourist = Tourist()
        await tourist.spawn(start=city)

        assert tourist.response.get("visited") is True

    @pytest.mark.asyncio
    async def test_walker_disengage(self: "TestWalker") -> None:
        """Test that disengage halts the walker and removes it from the graph."""
        # Create a node and walker
        node = Node()
        walker = Walker()

        # Set walker to visit the node
        walker.current_node = node
        node.visitor = walker

        # Disengage the walker
        await walker.disengage()

        # Verify walker is paused and removed from node
        assert walker.paused is True
        assert walker.current_node is None
        assert node.visitor is None
