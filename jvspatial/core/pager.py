"""
Object pager implementation for jvspatial core module.

Provides efficient, database-level pagination for objects (including nodes) with filtering capabilities.
Designed to integrate seamlessly with UI frameworks requiring paginated data.
"""

import contextlib
from math import ceil
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, TypeVar

if TYPE_CHECKING:
    from .entities import Object

T = TypeVar("T", bound="Object")


class ObjectPager:
    """Efficient pagination for objects with database-level optimization.

    Provides a clean interface for paginating object results with filtering,
    designed specifically for UI integration and large datasets. Works with
    any Object subclass including Node, Edge, and custom objects.

    Example:
        # Basic pagination for nodes
        pager = ObjectPager(City, page_size=10)
        cities = pager.get_page()

        # Pagination for any object type
        document_pager = ObjectPager(Document, page_size=20)
        docs = document_pager.get_page()

        # With filtering
        large_cities = pager.get_page({"context.population": {"$gt": 1000000}})

        # Pagination info for UI
        info = pager.to_dict()
    """

    def __init__(
        self,
        object_class: Type[T],
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_direction: str = "asc",
    ) -> None:
        """Initialize the ObjectPager.

        Args:
            object_class: Object class to paginate (e.g., City, Person, Document, Edge)
            page_size: Number of items per page (default: 20)
            filters: Optional database-level filters
            order_by: Optional field name to sort by
            order_direction: Sort direction - "asc" (default) or "desc"
        """
        self.object_class = object_class
        self.page_size = max(1, page_size)  # Ensure at least 1 item per page
        self.current_page = 1
        self.filters = filters or {}
        self.order_by = order_by
        self.order_direction = order_direction

        # Pagination state (updated after get_page() call)
        self.total_items = 0
        self.total_pages = 1
        self.has_previous = False
        self.has_next = False
        self.is_cached = False

        # Internal cache for results (now includes filter hash in key)
        self._cache: Dict[str, List[T]] = {}

    async def get_page(
        self, page: int = 1, additional_filters: Optional[Dict[str, Any]] = None
    ) -> List[T]:
        """Retrieve a paginated list of objects using MongoDB-style queries.

        Args:
            page: Page number to retrieve (1-based)
            additional_filters: Additional MongoDB-style filters to apply

        Returns:
            List of object instances for the current page
        """
        from .context import get_default_context

        self.current_page = max(1, page)

        # Check cache first (include additional_filters in cache key)
        cache_key = f"{self.current_page}_{hash(str(additional_filters))}"
        if cache_key in self._cache:
            self.is_cached = True
            return self._cache[cache_key]  # type: ignore[return-value]

        self.is_cached = False

        # Build MongoDB-style query with proper class filtering
        db_filter = {"name": self.object_class.__name__}

        # Merge instance filters
        if self.filters:
            db_filter.update(self.filters)

        # Merge any additional filters passed to this method
        if additional_filters:
            db_filter.update(additional_filters)

        context = get_default_context()
        # Get type_code from model fields
        type_code_field = self.object_class.model_fields.get("type_code")
        type_code = type_code_field.default if type_code_field else "o"
        collection = context._get_collection_name(type_code)

        # Use enhanced database methods for better performance
        # Get total count using the new count method
        from unittest.mock import AsyncMock

        if isinstance(context.database, AsyncMock):
            # Handle AsyncMock case (tests)
            self.total_items = await context.database.count(collection, db_filter)
        else:
            # Handle real database case
            db = context.database
            self.total_items = await db.count(collection, db_filter)

        # Calculate pagination state
        self.total_pages = max(1, ceil(self.total_items / self.page_size))
        self.current_page = max(1, min(self.current_page, self.total_pages))
        self.has_previous = self.current_page > 1
        self.has_next = self.current_page < self.total_pages

        # For ordering, we'll need to fetch and sort in Python for now
        # TODO: Implement database-level sorting with MongoDB operators
        if isinstance(context.database, AsyncMock):
            # Handle AsyncMock case (tests)
            all_items = await context.database.find(collection, db_filter)
        else:
            # Handle real database case
            all_items = await db.find(collection, db_filter)

        # Apply ordering if specified
        if self.order_by:
            reverse = self.order_direction.lower() == "desc"
            with contextlib.suppress(KeyError, TypeError):
                all_items.sort(
                    key=lambda item: item.get("context", {}).get(self.order_by, 0),
                    reverse=reverse,
                )

        # Calculate offset for current page
        offset = (self.current_page - 1) * self.page_size
        page_items = all_items[offset : offset + self.page_size]

        # Deserialize items to object instances
        objects = []
        for item_data in page_items:
            obj = await context._deserialize_entity(self.object_class, item_data)
            if obj:
                objects.append(obj)

        # Cache the result with the cache key
        self._cache[cache_key] = objects  # type: ignore[assignment]

        return objects

    async def next_page(
        self, additional_filters: Optional[Dict[str, Any]] = None
    ) -> List[T]:
        """Move to next page and return results.

        Args:
            additional_filters: Additional MongoDB-style filters to apply

        Returns:
            List of objects for the next page
        """
        if self.has_next_page():
            return await self.get_page(self.current_page + 1, additional_filters)
        return []

    async def previous_page(
        self, additional_filters: Optional[Dict[str, Any]] = None
    ) -> List[T]:
        """Move to previous page and return results.

        Args:
            additional_filters: Additional MongoDB-style filters to apply

        Returns:
            List of objects for the previous page
        """
        if self.has_previous_page():
            return await self.get_page(self.current_page - 1, additional_filters)
        return []

    def has_next_page(self) -> bool:
        """Check if there is a next page available.

        Returns:
            True if there is a next page
        """
        return self.current_page < self.total_pages

    def has_previous_page(self) -> bool:
        """Check if there is a previous page available.

        Returns:
            True if there is a previous page
        """
        return self.current_page > 1

    def to_dict(self) -> Dict[str, Any]:
        """Get pagination information as a dictionary.

        Perfect for UI frameworks that need pagination metadata.

        Returns:
            Dictionary containing:
            - total_items: Total number of items across all pages
            - total_pages: Total number of pages
            - current_page: Current page number (1-based)
            - page_size: Number of items per page
            - has_previous: Whether there's a previous page
            - has_next: Whether there's a next page
            - previous_page: Previous page number (None if no previous)
            - next_page: Next page number (None if no next)
            - start_index: 0-based start index of current page items
            - end_index: 0-based end index of current page items
            - object_type: Name of the object class being paginated
        """
        start_index = (self.current_page - 1) * self.page_size
        end_index = min(start_index + self.page_size - 1, self.total_items - 1)

        return {
            "total_items": self.total_items,
            "total_pages": self.total_pages,
            "current_page": self.current_page,
            "page_size": self.page_size,
            "has_previous": self.has_previous,
            "has_next": self.has_next,
            "previous_page": self.current_page - 1 if self.has_previous else None,
            "next_page": self.current_page + 1 if self.has_next else None,
            "start_index": start_index,
            "end_index": end_index if self.total_items > 0 else None,
            "object_type": self.object_class.__name__,
        }

    def __repr__(self) -> str:
        """String representation of the pager."""
        return (
            f"ObjectPager({self.object_class.__name__}, "
            f"page {self.current_page}/{self.total_pages}, "
            f"size={self.page_size}, total={self.total_items})"
        )


# Convenience functions for common pagination patterns
async def paginate_objects(
    object_class: Type[T],
    page: int = 1,
    page_size: int = 20,
    filters: Optional[Dict[str, Any]] = None,
) -> List[T]:
    """Convenience function for simple object pagination.

    Args:
        object_class: Object class to paginate (Node, Edge, or custom Object)
        page: Page number (1-based)
        page_size: Page size
        filters: Optional MongoDB-style database filters

    Returns:
        List of objects for the specified page
    """
    pager = ObjectPager(object_class, page_size=page_size, filters=filters)
    return await pager.get_page(page)


async def paginate_by_field(
    object_class: Type[T],
    field: str,
    page: int = 1,
    page_size: int = 20,
    order: str = "asc",
    filters: Optional[Dict[str, Any]] = None,
) -> List[T]:
    """Convenience function for field-based pagination with ordering.

    Args:
        object_class: Object class to paginate
        field: Field name to order by (will be accessed via context.field)
        page: Page number (1-based)
        page_size: Page size
        order: Sort order ('asc' or 'desc')
        filters: Additional MongoDB-style database filters

    Returns:
        List of objects ordered by the specified field
    """
    pager = ObjectPager(
        object_class,
        page_size=page_size,
        filters=filters,
        order_by=field,
        order_direction=order,
    )

    return await pager.get_page(page)
