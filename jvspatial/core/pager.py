"""
Object pager implementation for jvspatial core module.

Provides efficient, database-level pagination for objects (including nodes) with filtering capabilities.
Designed to integrate seamlessly with UI frameworks requiring paginated data.
"""

import base64
import json
from math import ceil
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from jvspatial.db.database import finalize_find_results

if TYPE_CHECKING:
    from .entities import Object

T = TypeVar("T", bound="Object")


class ObjectPager(Generic[T]):
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
        *,
        count_total: bool = True,
    ) -> None:
        """Initialize the ObjectPager.

        Args:
            object_class: Object class to paginate (e.g., City, Person, Document, Edge)
            page_size: Number of items per page (default: 20)
            filters: Optional database-level filters
            order_by: Optional field name to sort by
            order_direction: Sort direction - "asc" (default) or "desc"
            count_total: Compute exact totals (default). False uses lookahead;
                total_items/total_pages stay None and pages are not clamped.
        """
        self.object_class = object_class
        self.page_size = max(1, page_size)  # Ensure at least 1 item per page
        self.current_page = 1
        self.filters = filters or {}
        self.order_by = order_by
        self.order_direction = order_direction
        self.count_total = count_total

        # Pagination state (set after get_page() call)
        self.total_items: Optional[int] = 0 if count_total else None
        self.total_pages: Optional[int] = 1 if count_total else None
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
        requests an offset ID projection and hydrates only the chosen page.
        Native SQL/Mongo projections avoid transferring discarded payloads.
        ``count_total=False`` skips the separate count query.

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
            keyset_filter = {"$and": [db_filter, {"id": {"$gt": after_id}}]}
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

        if self.count_total:
            self.total_items = await db.count(collection, db_filter)
            self.total_pages = max(1, ceil(self.total_items / self.page_size))
            self.current_page = max(1, min(self.current_page, self.total_pages))
            self.has_next = self.current_page < self.total_pages
        else:
            self.total_items = self.total_pages = None
        self.has_previous = self.current_page > 1

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

        # Offset is evaluated in the backend's ID projection. Only the page
        # payloads are then hydrated, not a discarded prefix of full records.
        ids = await db.find_ids(
            collection,
            db_filter,
            limit=self.page_size + (not self.count_total),
            sort=page_sort,
            offset=offset,
        )
        if not self.count_total:
            self.has_next = len(ids) > self.page_size
            ids = ids[: self.page_size]
        page_records = await db.find_many(collection, ids)
        page_items_raw = [page_records[rid] for rid in ids if rid in page_records]

        # Safety net for a backend that ignored the requested sort. Route it
        # through the same helper the adapters use so it is a no-op when the
        # sort was honored: an ad-hoc key here would disagree with the DB-side
        # ordering that produced the slice above. In particular, defaulting a
        # missing value to ``0`` ordered it among the real values while the
        # slice had already placed it in the trailing missing-value run, which
        # duplicates or drops rows across page boundaries.
        if self.order_by and page_sort != [("id", 1)]:
            page_items_raw = finalize_find_results(page_items_raw, sort=page_sort)

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
        return (
            self.has_next
            if self.total_pages is None
            else self.current_page < self.total_pages
        )

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
        end_index = (
            min(start_index + self.page_size - 1, self.total_items - 1)
            if self.total_items is not None
            else None
        )

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
            "end_index": (
                end_index
                if self.total_items is not None and self.total_items > 0
                else None
            ),
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


# ---- keyset cursors ---------------------------------------------------------
# Shared by ``GraphContext.find_page`` and ``Node.nodes_page`` so both mint and
# read the same opaque cursor: base64(json({"id": <last id>, "sort": <value>})).


def keyset_sort_fields(
    sort: Optional[List[Tuple[str, int]]],
) -> List[Tuple[str, int]]:
    """Normalise a keyset sort: default ``[("id", 1)]``, ``id`` appended as tiebreaker."""
    from jvspatial.db.database import _keyset_sort_fields

    return _keyset_sort_fields(sort)


def encode_keyset_cursor(
    record: Dict[str, Any], sort_fields: List[Tuple[str, int]]
) -> str:
    """Opaque cursor positioned after ``record`` for a sort led by ``sort_fields[0]``.

    Dotted sort fields (``context.started_at``) resolve through the same path
    walk the adapters use; a flat ``.get`` would mint a ``None`` sort value
    for every cursor and stall pagination.
    """
    from jvspatial.db.database import _keyset_payload

    payload = _keyset_payload(record, sort_fields)
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()


def decode_keyset_cursor(
    cursor: Optional[Union[str, Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Decode a cursor from :func:`encode_keyset_cursor`; ``None`` if absent or malformed."""
    if isinstance(cursor, dict):
        return cursor
    if not isinstance(cursor, str) or not cursor:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def keyset_filter(
    sort_fields: List[Tuple[str, int]],
    cursor_payload: Optional[Dict[str, Any]],
    *,
    nulls_first: bool = False,
) -> Optional[Dict[str, Any]]:
    """Mongo-style filter selecting records strictly after the cursor.

    Honors the nulls-last contract of ``finalize_find_results``: records
    with no value for the primary sort field come after every valued record
    in both directions. ``None`` when there is no (usable) cursor.
    """
    from jvspatial.db.database import _keyset_condition

    return _keyset_condition(sort_fields, cursor_payload, nulls_first=nulls_first)
