"""Transaction support for database operations.

PostgreSQL and :class:`MongoDBTransaction` offer native ACID semantics
(MongoDB requires a replica set, even single-node). Backends without native
transactions advertise ``Database.supports_transactions = False``; callers
should detect that flag via :func:`transaction_context` rather than relying
on best-effort writes.

JsonDB is a development-only backend with no transaction support — the
former ``JsonDBTransaction(best_effort=True)`` buffered-commit mode was
removed because it provided weaker-than-ACID guarantees that the audit
deemed misleading for a dev backend (it could lose writes on a mid-commit
process crash and was not atomic against external readers).
"""

import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class Transaction(ABC):
    """Abstract base class for database transactions.

    Provides a generic interface for managing database transactions
    across different database implementations.
    """

    def __init__(self, transaction_id: str):
        """Initialize the transaction.

        Args:
            transaction_id: Unique identifier for this transaction
        """
        self.transaction_id = transaction_id
        self.is_active = False
        self.is_committed = False
        self.is_rolled_back = False

    @abstractmethod
    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record within this transaction.

        Args:
            collection: Collection name
            data: Record data

        Returns:
            Saved record with any database-generated fields
        """
        pass

    @abstractmethod
    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID within this transaction.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete(self, collection: str, id: str) -> bool:
        """Delete a record within this transaction.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            True if record was deleted, False otherwise
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
        """Find records matching query within this transaction.

        Args:
            collection: Collection name
            query: Query dictionary

        Returns:
            List of matching records
        """
        pass

    async def find_projected(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        fields: List[str],
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Project through this transaction's find, never a pooled connection."""
        from jvspatial.db.database import project_record_fields, projection_fields

        names = projection_fields(fields)
        return [
            project_record_fields(row, names)
            for row in await self.find(collection, query, limit=limit, sort=sort)
        ]

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find one matching record without leaving this transaction."""
        rows = await self.find(collection, query, limit=1)
        return rows[0] if rows else None

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count matches in this transaction.

        Backends should override this with a native aggregate when available;
        the default keeps correctness and transaction visibility for adapters
        whose transaction API only supports ``find``.
        """
        return len(await self.find(collection, query or {}))

    async def find_ids(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        offset: int = 0,
    ) -> List[str]:
        """Return a transaction-consistent ID page.

        Adapters should override this to project IDs natively. The fallback
        preserves the Database contract and reads through this transaction.
        """
        if offset < 0 or (limit is not None and limit < 0):
            raise ValueError("offset and limit must be nonnegative")
        if limit == 0:
            return []
        from .database import _keyset_sort_fields

        rows = await self.find(
            collection,
            query,
            sort=_keyset_sort_fields(sort),
            limit=None if limit is None else offset + limit,
        )
        return [str(row["id"]) for row in rows[offset:] if "id" in row]

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch records by ID inside this transaction.

        Adapters should override this when they can perform a set query.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for record_id in dict.fromkeys(ids):
            record = await self.get(collection, record_id)
            if record is not None:
                out[record_id] = record
        return out

    async def find_iter(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        sort: Optional[List[Tuple[str, int]]] = None,
        batch_size: int = 100,
        cursor: Optional[bytes] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Iterate transaction-visible results using deterministic keysets."""
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size < 1
        ):
            raise ValueError("batch_size must be a positive integer")
        from .database import (
            _keyset_condition,
            _keyset_payload,
            _keyset_sort_fields,
            decode_cursor,
        )

        fields = _keyset_sort_fields(sort)
        payload = decode_cursor(cursor)
        while True:
            after = _keyset_condition(fields, payload)
            if after is None:
                page_query = dict(query)
            elif query:
                page_query = {"$and": [query, after]}
            else:
                page_query = after
            rows = await self.find(
                collection, page_query, sort=fields, limit=batch_size
            )
            if not rows:
                return
            for row in rows:
                payload = _keyset_payload(row, fields)
                yield row
            if len(rows) < batch_size:
                return

    async def count_incident_edges(
        self, collection: str, node_ids: List[str]
    ) -> Dict[str, int]:
        """Count requested edge endpoints without escaping this transaction."""
        counts = dict.fromkeys(node_ids, 0)
        if not counts:
            return counts
        iterator = self.find_iter(
            collection,
            {
                "$or": [
                    {"source": {"$in": list(counts)}},
                    {"target": {"$in": list(counts)}},
                ]
            },
        )
        async for edge in iterator:
            for node_id in {
                value
                for value in (edge.get("source"), edge.get("target"))
                if isinstance(value, str)
            }:
                if node_id in counts:
                    counts[node_id] += 1
        return counts

    @abstractmethod
    async def commit(self) -> None:
        """Commit this transaction."""
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback this transaction."""
        pass


class MongoDBTransaction(Transaction):
    """MongoDB transaction backed by a Motor client session.

    Requires a MongoDB replica set (even a single-node replica set).
    """

    def __init__(self, transaction_id: str, session, db):
        """Initialize MongoDB transaction.

        Args:
            transaction_id: Unique identifier for this transaction
            session: Motor ``AsyncIOMotorClientSession``
            db: Motor ``AsyncIOMotorDatabase``
        """
        super().__init__(transaction_id)
        self.session = session
        self._db = db
        self.is_active = True

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record within this MongoDB transaction."""
        if "_id" not in data and "id" in data:
            data["_id"] = data["id"]
        coll = self._db[collection]
        await coll.replace_one(
            {"_id": data["_id"]},
            data,
            upsert=True,
            session=self.session,
        )
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID within this MongoDB transaction."""
        coll = self._db[collection]
        return await coll.find_one({"_id": id}, session=self.session)

    async def delete(self, collection: str, id: str) -> bool:
        """Delete a record within this MongoDB transaction."""
        coll = self._db[collection]
        result = await coll.delete_one({"_id": id}, session=self.session)
        return result.deleted_count > 0

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find records matching query within this MongoDB transaction."""
        coll = self._db[collection]
        cursor = coll.find(query, session=self.session)
        if sort:
            cursor = cursor.sort(sort)
        if limit is not None:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=None)

    async def commit(self) -> None:
        """Commit this MongoDB transaction."""
        if self.is_active and not self.is_committed and not self.is_rolled_back:
            await self.session.commit_transaction()
            self.is_active = False
            self.is_committed = True

    async def rollback(self) -> None:
        """Roll back this MongoDB transaction."""
        if self.is_active and not self.is_committed and not self.is_rolled_back:
            await self.session.abort_transaction()
            self.is_active = False
            self.is_rolled_back = True


@asynccontextmanager
async def transaction_context(database, transaction_id: Optional[str] = None):
    """Context manager for database transactions.

    Yields a ``Transaction`` when the database supports it, or ``None``
    when transactions are unavailable. Callers requiring atomic writes must
    reject the unavailable case. Cancellation rolls back just like an error.

    Args:
        database: Database instance
        transaction_id: Optional transaction ID

    Yields:
        Transaction object or None
    """
    if not hasattr(database, "begin_transaction"):
        yield None
        return

    transaction = await database.begin_transaction()
    if transaction is None:
        yield None
        return

    try:
        yield transaction
        await database.commit_transaction(transaction)
    except BaseException:
        await database.rollback_transaction(transaction)
        raise


__all__ = [
    "Transaction",
    "MongoDBTransaction",
    "transaction_context",
]
