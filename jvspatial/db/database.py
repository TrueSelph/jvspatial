"""Simplified database interface focusing on essential CRUD operations.

This module provides a streamlined database interface that removes
unnecessary complexity while maintaining core functionality.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

from jvspatial.db.query import QueryEngine

logger = logging.getLogger(__name__)


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
    """

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
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

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
        doc = await self.find_one(collection, query)
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
        doc = await self.find_one(collection, query)
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


class DatabaseError(Exception):
    """Base exception for database operations."""

    pass


class VersionConflictError(DatabaseError):
    """Raised when a document version conflict occurs during update."""

    pass
