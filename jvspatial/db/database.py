"""Simplified database interface focusing on essential CRUD operations.

This module provides a streamlined database interface that removes
unnecessary complexity while maintaining core functionality.
"""

import logging
from abc import ABC, abstractmethod
from functools import partial
from typing import Any, Dict, List, Optional, Tuple, Union

from jvspatial.db.query import QueryEngine

logger = logging.getLogger(__name__)


def _find_sort_key(record: Dict[str, Any], field: str) -> Tuple[bool, Any]:
    """Sort key: non-``None`` values first, then by value (with ``None`` last)."""
    value = record.get(field)
    return (value is None, value)


def _normalize_id_query(query: Dict[str, Any]) -> Dict[str, Any]:
    """Map ``_id`` → ``id`` when only ``_id`` is present.

    The default ``find_one_and_update`` / ``find_one_and_delete`` impls
    feed the query into ``QueryEngine.match`` against records stored by
    non-Mongo backends (JsonDB / SQLite / DynamoDB) which only persist
    ``id``. Callers that follow the Mongo-style convention of querying
    by ``_id`` would otherwise silently miss every row on those backends
    (audit §5.3). When both keys are present the caller's intent is
    preserved verbatim.
    """
    if "_id" in query and "id" not in query:
        normalized = {k: v for k, v in query.items() if k != "_id"}
        normalized["id"] = query["_id"]
        return normalized
    return query


def finalize_find_results(
    records: List[Dict[str, Any]],
    *,
    sort: Optional[List[Tuple[str, int]]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Apply optional Mongo-style sort and limit in memory.

    ``sort`` is a list of ``(field, direction)`` with ``direction`` ``1`` for
    ascending and ``-1`` for descending. Sorting is stable; compound sorts are
    applied from the last key to the first.
    """
    out = records
    if sort:
        out = list(records)
        for field, direction in reversed(sort):
            out.sort(
                key=partial(_find_sort_key, field=field),
                reverse=(direction == -1),
            )
    if limit is not None:
        out = out[:limit]
    return out


class Database(ABC):
    """Simplified abstract base class for database adapters.

    Provides essential CRUD operations without complex transaction support.
    Focuses on core functionality.

    All implementations must support:
    - Basic CRUD operations (save, get, delete, find)
    - Collection-based data organization
    - Simple query operations with dict-based filters

    **Standard compound operations** (always available on built-in adapters):

    - ``find_one_and_update`` — default uses ``find_one`` + ``QueryEngine.apply_update``
      + ``save`` (read-modify-write; **not** atomic under concurrency except where
      overridden, e.g. MongoDB native).
    - ``find_one_and_delete`` — default uses ``find_one`` + ``delete`` (not atomic
      except MongoDB native override).

    Query matching for both follows the same rules as :meth:`find_one` / :meth:`find`
    (Mongo-style operators via :class:`~jvspatial.db.query.QueryEngine` where the
    adapter applies it).

    Capability flags
    ----------------
    Subclasses set the following class attributes so callers can branch on
    capabilities without sniffing for adapter classes:

    ``supports_transactions``
        ``True`` if :meth:`begin_transaction` returns a real transaction
        with ACID semantics (e.g. MongoDB replica set). ``False`` for
        adapters where transactions are unavailable or only available in a
        weak buffered form. Default ``False``.
    """

    # Capability flags. Override in subclasses.
    supports_transactions: bool = False

    @abstractmethod
    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Args:
            collection: Collection name
            data: Record data

        Returns:
            Saved record with any database-generated fields
        """
        pass

    @abstractmethod
    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data or None if not found
        """
        pass

    @abstractmethod
    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID.

        Args:
            collection: Collection name
            id: Record ID
        """
        pass

    @abstractmethod
    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)
            limit: Optional maximum number of documents to return after matching
            sort: Optional list of ``(field, direction)`` tuples (``1`` asc, ``-1`` desc)

        Returns:
            List of matching records
        """
        pass

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records matching a query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

        Returns:
            Number of matching records
        """
        if query is None:
            query = {}
        results = await self.find(collection, query)
        return len(results)

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find the first record matching a query.

        Args:
            collection: Collection name
            query: Query parameters

        Returns:
            First matching record or None if not found
        """
        results = await self.find(collection, query)
        return results[0] if results else None

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Bulk-fetch records by id in one round trip per backend.

        Args:
            collection: Collection name.
            ids: Record IDs to fetch. Duplicates are de-duplicated.

        Returns:
            ``{id: record}`` for each id that exists. Missing ids are
            simply absent from the result (no exception, no ``None``
            placeholder). Order is **not** preserved across backends --
            iterate the returned dict by your input ``ids`` list if you
            need stable ordering.

        Performance:
            * MongoDB: single ``find({"_id": {"$in": ids}})`` call.
            * SQLite: single ``WHERE collection=? AND id IN (?,?,...)`` SELECT.
            * DynamoDB: chunked ``BatchGetItem`` (100 ids/request) with
              parallel batches.
            * JsonDB: parallel ``asyncio.gather`` over per-file reads.

            The default implementation in this base class issues N
            sequential ``get()`` calls -- adapters should override.
        """
        if not ids:
            return {}
        unique_ids = list(dict.fromkeys(ids))  # de-dup, preserve order
        out: Dict[str, Dict[str, Any]] = {}
        for rec_id in unique_ids:
            doc = await self.get(collection, rec_id)
            if doc is not None:
                out[rec_id] = doc
        return out

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Save many records in one round trip per backend.

        Args:
            collection: Collection name.
            records: Iterable of record dicts. Each must have an ``id``
                field. Records without ``id`` raise ``ValueError``.

        Returns:
            Number of records successfully saved.

        Atomicity (per backend):
            * MongoDB: ``bulk_write`` with ``ordered=False`` -- partial
              successes are reported; failures don't block other writes.
            * SQLite: single transaction with ``executemany``; **all
              records or none** land. A constraint violation rolls back
              the whole batch.
            * DynamoDB: ``BatchWriteItem`` with unprocessed-item retry;
              partial successes possible.
            * JsonDB: parallel atomic per-file writes; partial successes
              possible.

            The default implementation in this base class is a serial
            loop of ``save()`` calls (partial success on failure), which
            is correct but slow -- adapters should override.
        """
        if not records:
            return 0
        for r in records:
            if "id" not in r:
                raise ValueError(
                    "bulk_save requires every record to have an 'id' field"
                )
        # Sequential save() calls; on any failure the exception
        # propagates and the caller sees no return value, so reaching
        # the ``return`` always means every record persisted.
        for r in records:
            await self.save(collection, dict(r))
        return len(records)

    async def find_one_and_delete(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find and delete the first record matching ``query``.

        **Query semantics** match :meth:`find_one` (same dict filters and operators
        supported by the adapter, typically via :class:`~jvspatial.db.query.QueryEngine`).

        **Atomicity:** the default implementation is ``find_one`` then ``delete`` and is
        **not** atomic under concurrent writers. MongoDB overrides with a native
        ``find_one_and_delete`` for atomicity.

        Args:
            collection: Collection name
            query: Query parameters (e.g. ``{"_id": "x", "_jv_claim": "token"}``)

        Returns:
            Deleted document if found, ``None`` otherwise
        """
        # Non-Mongo backends store records keyed by ``id`` only. Normalize
        # the Mongo-style ``_id`` filter so default matching works
        # uniformly (audit §5.3 / SPEC §4.1).
        doc = await self.find_one(collection, _normalize_id_query(query))
        if doc is None:
            return None
        record_id = doc.get("_id", doc.get("id"))
        if record_id is not None:
            await self.delete(collection, str(record_id))
        return doc

    async def find_one_and_update(
        self,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find and update the first record matching ``query``.

        Default implementation: ``find_one`` + ``QueryEngine.apply_update`` + ``save``.
        **Not atomic** under concurrent writers (MongoDB overrides with native
        ``find_one_and_update``).

        Supported update operators include ``$set``, ``$unset``, ``$inc``, ``$push``,
        ``$addToSet``, and ``$setOnInsert`` when ``upsert=True``.

        Args:
            collection: Collection name
            query: Query parameters (e.g. ``{"_id": "sender_id"}``)
            update: MongoDB-style update document
            upsert: If ``True``, create a document when no match

        Returns:
            Updated document, or ``None`` if no match and ``upsert`` is ``False``
        """
        # Non-Mongo backends store records keyed by ``id`` only. Normalize
        # the Mongo-style ``_id`` filter so default matching works
        # uniformly (audit §5.3 / SPEC §4.1).
        normalized = _normalize_id_query(query)
        doc = await self.find_one(collection, normalized)
        is_new = doc is None
        if is_new:
            if not upsert:
                return None
            doc = {}
            doc_id = query.get("_id", query.get("id"))
            if doc_id is not None:
                doc["_id"] = doc_id
                doc["id"] = str(doc_id)
            QueryEngine.apply_update(doc, update, apply_set_on_insert=True)
        else:
            QueryEngine.apply_update(doc, update, apply_set_on_insert=False)

        record_id = doc.get("id", doc.get("_id"))
        if record_id is not None:
            doc["id"] = str(record_id)
        await self.save(collection, doc)
        return doc

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Create an index on the specified field(s).

        This is an optional method that databases can implement for performance optimization.
        Databases that don't support indexing should override this with a no-op implementation.

        Args:
            collection: Collection name
            field_or_fields: Single field name (str) or list of (field_name, direction) tuples for compound indexes
            unique: Whether the index should enforce uniqueness
            **kwargs: Additional database-specific index options (e.g., expireAfterSeconds for TTL indexes)

        Note:
            Default implementation logs a warning. Database implementations should override this method.
        """
        logger.warning(
            f"create_index() called on {self.__class__.__name__} but indexing is not implemented. "
            f"Index creation for collection '{collection}' on field(s) '{field_or_fields}' was ignored."
        )

    async def drop_deprecated_indexes(self, deprecated: Dict[str, List[str]]) -> None:
        """Drop indexes that were removed or renamed in code (orphan cleanup).

        Called once at startup with a map of collection name → list of old index
        names to remove.  The default implementation is a no-op so that adapters
        which do not use named indexes (e.g. in-memory) can ignore it.

        Adapters that do support named indexes (MongoDB, PostgreSQL with explicit
        index names, etc.) should override this to silently skip missing indexes
        and log a warning for any other errors.

        Args:
            deprecated: Mapping of collection name to old index names.
                        Example: ``{"node": ["conv_id_only", "context.session_id_1"]}``
        """
        return None


class DatabaseError(Exception):
    """Base exception for database operations."""

    pass


class VersionConflictError(DatabaseError):
    """Raised when a document version conflict occurs during update."""

    pass
