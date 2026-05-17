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

        # Pagination state (set after get_page() call)
        self.total_items = 0
        self.total_pages = 1
        self.has_previous = False
        self.has_next = False
        # Result caching removed (audit §8.2). The previous ``_cache``
        # was never invalidated on writes so callers got stale rows after
        # any save/delete on the underlying collection. Backend-level
        # caches (``create_database(cache_get_size=...)``) remain.
        self.is_cached = False

    async def get_page(
        self,
        page: int = 1,
        additional_filters: Optional[Dict[str, Any]] = None,
        after_id: Optional[str] = None,
    ) -> List[T]:
        """Retrieve a paginated list of objects using id-range pagination.

        When ``after_id`` is provided the method uses a keyset/cursor approach:
        it fetches ``page_size + 1`` documents whose ``id`` is greater than
        ``after_id``, sorted by id ascending.  This avoids loading the full
        matching set and sorting in Python.

        For backwards-compatible page-number access (``page`` ≥ 1) the method
        falls back to the former offset approach, but still avoids the
        ``find+len`` count call by using ``db.count``.

        Args:
            page: Page number to retrieve (1-based).  Ignored when ``after_id``
                is provided.
            additional_filters: Additional MongoDB-style filters to apply.
            after_id: Exclusive lower bound for keyset pagination.  When set,
                ``page`` is ignored.

        Returns:
            List of object instances for the current page.
        """
        from .context import get_default_context

        context = get_default_context()
        db = context.database

        # Merge filters
        merged_filters: Dict[str, Any] = {}
        if self.filters:
            merged_filters.update(self.filters)
        if additional_filters:
            merged_filters.update(additional_filters)

        collection, db_filter = await self.object_class._build_database_query(
            context, merged_filters, {}
        )

        # --- Keyset (cursor) pagination ---
        if after_id is not None:
            # Cursor semantics only hold when the sort key matches the
            # cursor field. ``after_id`` filters by ``id > after_id`` so
            # sorting by anything else would skip rows / return duplicates
            # on writes between pages. Reject the combo loudly rather
            # than silently return broken pages (audit §8.1).
            if self.order_by:
                raise ValueError(
                    "ObjectPager: ``after_id`` (keyset pagination) cannot be "
                    "combined with ``order_by``; the cursor only tracks id. "
                    "Use offset pagination if you need a custom sort key."
                )
            keyset_filter = dict(db_filter)
            keyset_filter["id"] = {"$gt": after_id}
            sort: Optional[List[Any]] = [("id", 1)]
            raw_items = await db.find(
                collection, keyset_filter, limit=self.page_size + 1, sort=sort
            )
            self.has_next = len(raw_items) > self.page_size
            if self.has_next:
                raw_items = raw_items[: self.page_size]
            objects: List[T] = []
            for item_data in raw_items:
                obj = await context._deserialize_entity(self.object_class, item_data)
                if obj:
                    objects.append(obj)
            self.is_cached = False
            return objects

        # --- Page-number (offset) pagination ---
        self.current_page = max(1, page)
        self.is_cached = False

        self.total_items = await db.count(collection, db_filter)
        self.total_pages = max(1, ceil(self.total_items / self.page_size))
        self.current_page = max(1, min(self.current_page, self.total_pages))
        self.has_previous = self.current_page > 1
        self.has_next = self.current_page < self.total_pages

        # Fetch only the required slice using DB-level sort + limit.
        page_sort: Optional[List[Any]] = None
        if self.order_by:
            page_sort = [
                (
                    f"context.{self.order_by}",
                    1 if self.order_direction.lower() == "asc" else -1,
                )
            ]
        else:
            page_sort = [("id", 1)]

        offset = (self.current_page - 1) * self.page_size

        # Most backends support limit; we emulate skip via the id-range approach
        # when offset > 0 to avoid fetching the full collection.
        if offset > 0 and page_sort == [("id", 1)]:
            # Get the id at the target offset using a minimal projection.
            skip_rows = await db.find(
                collection,
                db_filter,
                limit=offset,
                sort=page_sort,
            )
            if skip_rows:
                pivot_id = skip_rows[-1].get("id", "")
                slice_filter = dict(db_filter)
                slice_filter["id"] = {"$gt": pivot_id}
                page_items_raw = await db.find(
                    collection, slice_filter, limit=self.page_size, sort=page_sort
                )
            else:
                page_items_raw = []
        else:
            all_items_raw = await db.find(
                collection, db_filter, limit=offset + self.page_size, sort=page_sort
            )
            page_items_raw = all_items_raw[offset : offset + self.page_size]

        # Apply in-Python ordering when a non-id order_by is set.
        if self.order_by and page_sort != [("id", 1)]:
            reverse = self.order_direction.lower() == "desc"
            with contextlib.suppress(KeyError, TypeError):
                page_items_raw.sort(
                    key=lambda item: item.get("context", {}).get(self.order_by, 0),
                    reverse=reverse,
                )

        page_objects: List[T] = []
        for item_data in page_items_raw:
            obj = await context._deserialize_entity(self.object_class, item_data)
            if obj:
                page_objects.append(obj)

        return page_objects

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
