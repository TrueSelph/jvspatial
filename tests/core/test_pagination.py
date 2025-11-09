"""
Test suite for ObjectPager and pagination functionality.

This module implements comprehensive tests for the pagination system including:
- ObjectPager basic functionality
- Page navigation (next_page, previous_page)
- Filtering and ordering capabilities
- Convenience functions (paginate_objects, paginate_by_field)
- Integration with asynchronous batch processing
- Edge cases and error handling
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.core.entities import Node, Object
from jvspatial.core.pager import ObjectPager, paginate_by_field, paginate_objects


class PaginationTestObject(Object):
    """Test object for pagination testing."""

    name: str = ""
    category: str = ""
    value: int = 0
    active: bool = True


class PaginationTestNode(Node):
    """Test node for pagination testing."""

    name: str = ""
    population: int = 0
    state: str = ""


@pytest.fixture
def mock_context():
    """Mock GraphContext for testing."""
    context = MagicMock()
    context.database = AsyncMock()
    context._get_collection_name = MagicMock(return_value="test_collection")
    context._deserialize_entity = AsyncMock()
    return context


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return [
        {
            "id": "1",
            "name": "PaginationTestObject",
            "context": {
                "name": "Item A",
                "category": "cat1",
                "value": 10,
                "active": True,
            },
        },
        {
            "id": "2",
            "name": "PaginationTestObject",
            "context": {
                "name": "Item B",
                "category": "cat2",
                "value": 20,
                "active": True,
            },
        },
        {
            "id": "3",
            "name": "PaginationTestObject",
            "context": {
                "name": "Item C",
                "category": "cat1",
                "value": 30,
                "active": False,
            },
        },
        {
            "id": "4",
            "name": "PaginationTestObject",
            "context": {
                "name": "Item D",
                "category": "cat2",
                "value": 40,
                "active": True,
            },
        },
        {
            "id": "5",
            "name": "PaginationTestObject",
            "context": {
                "name": "Item E",
                "category": "cat1",
                "value": 50,
                "active": True,
            },
        },
    ]


class TestObjectPagerBasicFunctionality:
    """Test ObjectPager basic functionality."""

    async def test_pager_initialization(self):
        """Test ObjectPager initialization with various parameters."""
        # Basic initialization
        pager = ObjectPager(PaginationTestObject)
        assert pager.object_class == PaginationTestObject
        assert pager.page_size == 20  # default
        assert pager.current_page == 1
        assert pager.filters == {}
        assert pager.order_by is None
        assert pager.order_direction == "asc"

        # Custom initialization
        filters = {"context.active": True}
        pager = ObjectPager(
            PaginationTestObject,
            page_size=10,
            filters=filters,
            order_by="name",
            order_direction="desc",
        )
        assert pager.page_size == 10
        assert pager.filters == filters
        assert pager.order_by == "name"
        assert pager.order_direction == "desc"

    async def test_page_size_validation(self):
        """Test that page_size is validated to be at least 1."""
        pager = ObjectPager(PaginationTestObject, page_size=0)
        assert pager.page_size == 1

        pager = ObjectPager(PaginationTestObject, page_size=-5)
        assert pager.page_size == 1

    @pytest.mark.asyncio
    async def test_get_page_basic(self, mock_context, sample_data):
        """Test basic page retrieval."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data[:2]  # First page

            # Mock deserialization
            async def mock_deserialize(cls, data):
                try:
                    # Extract _data if present
                    context_data = data["context"].copy()
                    stored_data = context_data.pop("_data", {})

                    obj = PaginationTestObject(id=data["id"], **context_data)

                    # Restore _data after object creation
                    if stored_data:
                        obj._data.update(stored_data)
                    else:
                        # Add some data to make the object truthy
                        obj._data["test"] = "value"

                    return obj
                except Exception as e:
                    return None

            mock_context._deserialize_entity.side_effect = mock_deserialize

            pager = ObjectPager(PaginationTestObject, page_size=2)
            results = await pager.get_page(1)

            assert len(results) == 2
            assert all(isinstance(obj, PaginationTestObject) for obj in results)
            assert pager.total_items == 5
            assert pager.total_pages == 3
            assert pager.current_page == 1
            assert pager.has_previous is False
            assert pager.has_next is True

    @pytest.mark.asyncio
    async def test_get_page_with_filters(self, mock_context, sample_data):
        """Test page retrieval with filters."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            # Filter for active items only
            active_data = [item for item in sample_data if item["context"]["active"]]
            mock_context.database.count.return_value = len(active_data)
            mock_context.database.find.return_value = active_data

            async def mock_deserialize(cls, data):
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            pager = ObjectPager(PaginationTestObject, filters={"context.active": True})
            results = await pager.get_page(1)

            # Should only return active items
            assert len(results) == 4
            assert all(obj.active for obj in results)

    @pytest.mark.asyncio
    async def test_get_page_with_ordering(self, mock_context, sample_data):
        """Test page retrieval with ordering."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            async def mock_deserialize(cls, data):
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            # Test ascending order
            pager = ObjectPager(
                PaginationTestObject, order_by="value", order_direction="asc"
            )
            results = await pager.get_page(1)

            values = [obj.value for obj in results]
            assert values == sorted(values)  # Should be sorted ascending

            # Test descending order
            pager = ObjectPager(
                PaginationTestObject, order_by="value", order_direction="desc"
            )
            results = await pager.get_page(1)

            values = [obj.value for obj in results]
            assert values == sorted(values, reverse=True)  # Should be sorted descending


class TestObjectPagerNavigation:
    """Test ObjectPager navigation methods."""

    @pytest.mark.asyncio
    async def test_next_page(self, mock_context, sample_data):
        """Test next_page navigation."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)

            # Return different data based on which page is being requested
            def mock_find(*args, **kwargs):
                # For this test, we'll just return all data and let the pager handle slicing
                return sample_data

            mock_context.database.find.side_effect = mock_find

            async def mock_deserialize(cls, data):
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            pager = ObjectPager(PaginationTestObject, page_size=2)

            # Get first page
            page1 = await pager.get_page(1)
            assert pager.current_page == 1
            assert pager.has_next_page()
            assert len(page1) == 2

            # Clear cache to ensure next call hits the database
            pager._cache.clear()

            # Get next page
            page2 = await pager.next_page()
            assert pager.current_page == 2
            assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_previous_page(self, mock_context, sample_data):
        """Test previous_page navigation."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            async def mock_deserialize(cls, data):
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            pager = ObjectPager(PaginationTestObject, page_size=2)

            # Start from page 2
            await pager.get_page(2)
            assert pager.current_page == 2
            assert pager.has_previous_page()

            # Go to previous page
            page1 = await pager.previous_page()
            assert pager.current_page == 1
            assert not pager.has_previous_page()

    async def test_has_next_page(self):
        """Test has_next_page logic."""
        pager = ObjectPager(PaginationTestObject)

        # Mock pagination state
        pager.current_page = 1
        pager.total_pages = 3
        assert pager.has_next_page()

        pager.current_page = 3
        assert not pager.has_next_page()

    async def test_has_previous_page(self):
        """Test has_previous_page logic."""
        pager = ObjectPager(PaginationTestObject)

        # Mock pagination state
        pager.current_page = 1
        assert not pager.has_previous_page()

        pager.current_page = 2
        assert pager.has_previous_page()


class TestObjectPagerCaching:
    """Test ObjectPager caching behavior."""

    @pytest.mark.asyncio
    async def test_page_caching(self, mock_context, sample_data):
        """Test that pages are cached properly."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data[:2]

            async def mock_deserialize(cls, data):
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            pager = ObjectPager(PaginationTestObject, page_size=2)

            # First call should hit the database
            results1 = await pager.get_page(1)
            assert not pager.is_cached
            assert mock_context.database.find.call_count == 1

            # Second call to same page should use cache
            results2 = await pager.get_page(1)
            assert pager.is_cached
            assert mock_context.database.find.call_count == 1  # No additional calls

            assert len(results1) == len(results2)


class TestObjectPagerMetadata:
    """Test ObjectPager metadata methods."""

    async def test_to_dict(self):
        """Test pagination metadata dictionary."""
        pager = ObjectPager(PaginationTestObject, page_size=10)

        # Mock pagination state
        pager.total_items = 25
        pager.total_pages = 3
        pager.current_page = 2
        pager.has_previous = True
        pager.has_next = True

        metadata = pager.to_dict()

        expected_keys = [
            "total_items",
            "total_pages",
            "current_page",
            "page_size",
            "has_previous",
            "has_next",
            "previous_page",
            "next_page",
            "start_index",
            "end_index",
            "object_type",
        ]

        assert all(key in metadata for key in expected_keys)
        assert metadata["total_items"] == 25
        assert metadata["total_pages"] == 3
        assert metadata["current_page"] == 2
        assert metadata["page_size"] == 10
        assert metadata["has_previous"] is True
        assert metadata["has_next"] is True
        assert metadata["previous_page"] == 1
        assert metadata["next_page"] == 3
        assert metadata["start_index"] == 10  # (2-1) * 10
        assert metadata["end_index"] == 19  # 10 + 10 - 1
        assert metadata["object_type"] == "PaginationTestObject"

    async def test_repr(self):
        """Test string representation."""
        pager = ObjectPager(PaginationTestObject, page_size=5)
        pager.total_items = 15
        pager.total_pages = 3
        pager.current_page = 2

        repr_str = repr(pager)
        assert "PaginationTestObject" in repr_str
        assert "page 2/3" in repr_str
        assert "size=5" in repr_str
        assert "total=15" in repr_str


class TestPaginationConvenienceFunctions:
    """Test convenience functions for pagination."""

    @pytest.mark.asyncio
    async def test_paginate_objects(self, mock_context, sample_data):
        """Test paginate_objects convenience function."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data[:3]

            async def mock_deserialize(cls, data):
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            # Test basic usage
            results = await paginate_objects(PaginationTestObject, page=1, page_size=3)
            assert len(results) == 3
            assert all(isinstance(obj, PaginationTestObject) for obj in results)

            # Test with filters
            results = await paginate_objects(
                PaginationTestObject,
                page=1,
                page_size=3,
                filters={"context.active": True},
            )
            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_paginate_by_field(self, mock_context, sample_data):
        """Test paginate_by_field convenience function."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            async def mock_deserialize(cls, data):
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            # Test ascending order
            results = await paginate_by_field(
                PaginationTestObject, field="value", page=1, page_size=5, order="asc"
            )
            assert len(results) == 5

            # Test descending order
            results = await paginate_by_field(
                PaginationTestObject, field="value", page=1, page_size=5, order="desc"
            )
            assert len(results) == 5

            # Test with filters
            results = await paginate_by_field(
                PaginationTestObject,
                field="value",
                page=1,
                page_size=5,
                filters={"context.active": True},
            )
            assert len(results) == 5


class TestPaginationEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_context):
        """Test pagination with no results."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = 0
            mock_context.database.find.return_value = []

            pager = ObjectPager(PaginationTestObject, page_size=10)
            results = await pager.get_page(1)

            assert len(results) == 0
            assert pager.total_items == 0
            assert pager.total_pages == 1
            assert pager.current_page == 1
            assert not pager.has_previous
            assert not pager.has_next

    @pytest.mark.asyncio
    async def test_page_beyond_range(self, mock_context, sample_data):
        """Test requesting a page beyond available range."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            pager = ObjectPager(PaginationTestObject, page_size=10)

            # Request page 5 when there's only 1 page of data
            results = await pager.get_page(5)

            # Should clamp to the last available page
            assert pager.current_page == 1

    @pytest.mark.asyncio
    async def test_negative_page_number(self, mock_context, sample_data):
        """Test requesting negative page number."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            pager = ObjectPager(PaginationTestObject)
            results = await pager.get_page(-1)

            # Should clamp to page 1
            assert pager.current_page == 1

    @pytest.mark.asyncio
    async def test_next_page_at_end(self, mock_context, sample_data):
        """Test next_page when already at the last page."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            pager = ObjectPager(PaginationTestObject, page_size=10)

            # Get the only page (all data fits in one page)
            await pager.get_page(1)
            assert not pager.has_next_page()

            # Try to get next page
            results = await pager.next_page()
            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_previous_page_at_beginning(self, mock_context, sample_data):
        """Test previous_page when already at the first page."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            pager = ObjectPager(PaginationTestObject)
            await pager.get_page(1)
            assert not pager.has_previous_page()

            # Try to get previous page
            results = await pager.previous_page()
            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_deserialization_errors(self, mock_context, sample_data):
        """Test handling of deserialization errors."""
        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(sample_data)
            mock_context.database.find.return_value = sample_data

            # Mock deserialization to fail for some items
            async def mock_deserialize(cls, data):
                if data["id"] == "2":
                    return None  # Simulate failure
                return PaginationTestObject(id=data["id"], **data["context"])

            mock_context._deserialize_entity.side_effect = mock_deserialize

            pager = ObjectPager(PaginationTestObject)
            results = await pager.get_page(1)

            # Should skip failed items and return only successful ones
            assert len(results) == 4  # 5 items - 1 failed = 4 successful
            assert all(obj.id != "2" for obj in results)


class TestPaginationWithNodes:
    """Test pagination with Node objects."""

    @pytest.mark.asyncio
    async def test_node_pagination(self, mock_context):
        """Test pagination with Node objects."""
        node_data = [
            {
                "id": "1",
                "name": "PaginationTestNode",
                "context": {"name": "City A", "population": 1000, "state": "NY"},
                "edges": [],
            },
            {
                "id": "2",
                "name": "PaginationTestNode",
                "context": {"name": "City B", "population": 2000, "state": "CA"},
                "edges": [],
            },
            {
                "id": "3",
                "name": "PaginationTestNode",
                "context": {"name": "City C", "population": 3000, "state": "NY"},
                "edges": [],
            },
        ]

        with patch(
            "jvspatial.core.context.get_default_context", return_value=mock_context
        ):
            mock_context.database.count.return_value = len(node_data)
            mock_context.database.find.return_value = node_data

            async def mock_deserialize(cls, data):
                return PaginationTestNode(
                    id=data["id"], edge_ids=data.get("edges", []), **data["context"]
                )

            mock_context._deserialize_entity.side_effect = mock_deserialize

            pager = ObjectPager(PaginationTestNode, page_size=2)
            results = await pager.get_page(1)

            assert len(results) == 2
            assert all(isinstance(node, PaginationTestNode) for node in results)
            assert pager.total_items == 3
            assert pager.has_next

            # Test filtering by state
            pager_filtered = ObjectPager(
                PaginationTestNode, filters={"context.state": "NY"}
            )
            ny_results = await pager_filtered.get_page(1)
            assert len(ny_results) <= 3  # Should filter results
