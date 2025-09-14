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
