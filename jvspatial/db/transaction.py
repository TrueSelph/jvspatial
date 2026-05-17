"""Transaction support for database operations.

This module provides transaction management for ACID operations across
different database implementations.

Capability levels
-----------------
Different adapters offer different transaction guarantees:

* **Native (ACID).** ``MongoDBTransaction`` -- writes are atomic across
  collections, isolation is configurable, durability is guaranteed by
  the replica set's commit semantics.
* **Buffered (best-effort).** ``JsonDBTransaction(best_effort=True)`` --
  writes are buffered in memory and applied at commit time. Atomicity
  holds only against single-process readers and only if the process
  doesn't crash between the first and last individual write of the
  commit. Intended for testing, scripting, and local-dev workflows
  where the trade-off is acceptable.
* **None.** Calling ``JsonDBTransaction()`` (without ``best_effort=True``)
  raises :class:`NotImplementedError`. Callers can detect this via the
  ``Database.supports_transactions`` capability flag and fall back to
  non-transactional writes.
"""

import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

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


# Sentinel marking a buffered delete in JsonDBTransaction's pending map.
_TOMBSTONE = object()


class JsonDBTransaction(Transaction):
    """JsonDB transaction implementation.

    JsonDB cannot offer ACID transactions on top of bare files. Two modes
    are exposed and the caller picks which trade-off they want:

    Strict (default)
        Every operation raises :class:`NotImplementedError`. Use the
        :attr:`Database.supports_transactions` flag to detect this case
        before opening a transaction. This is the safe default and avoids
        the silent-no-op footgun the previous implementation had, where
        ``commit()`` returned successfully without any persisted writes.

    Buffered (``best_effort=True``)
        Writes and deletes are buffered in memory and applied at commit
        time. Reads served from the transaction see buffered values
        first, then fall through to the underlying database. This gives
        you basic read-your-writes semantics inside the transaction, but
        is **not** atomic across processes and **not** atomic if the
        process crashes between the first and last individual write of
        the commit. Use it for tests, scripts, and local-dev flows where
        that trade-off is acceptable.

    Args:
        database: JsonDB instance.
        best_effort: Opt in to the buffered-commit mode. Defaults to
            ``False`` (strict mode -- every operation raises).
    """

    def __init__(self, database, *, best_effort: bool = False):
        import uuid

        super().__init__(str(uuid.uuid4()))
        self.database = database
        self.best_effort = best_effort
        self.is_active = True
        # Pending writes/deletes keyed by (collection, id).
        # Value is either a dict (write) or _TOMBSTONE (delete).
        self._pending: Dict[Tuple[str, str], Any] = {}
        if best_effort:
            # Emit a once-per-process ExperimentalWarning so adopters know
            # this surface may change. See docs/md/stability.md.
            # Uses the public ``emit_experimental_once`` hook rather than
            # the underscore-prefixed implementation (audit §7.7).
            from jvspatial.utils.stability import emit_experimental_once

            emit_experimental_once(
                "JsonDBTransaction(best_effort=True)",
                "Buffered-commit semantics are weaker than ACID and the "
                "interface may evolve; track docs/md/stability.md.",
            )
            logger.debug(
                "JsonDBTransaction opened in best_effort mode -- "
                "writes are buffered until commit and are NOT atomic "
                "against process crashes mid-commit."
            )

    def _require_best_effort(self, op: str) -> None:
        if not self.best_effort:
            raise NotImplementedError(
                f"JsonDB does not support transactional {op}() natively. "
                "Pass best_effort=True to opt into buffered-commit "
                "semantics (see JsonDBTransaction docstring) or check "
                "Database.supports_transactions and fall back to "
                "non-transactional writes."
            )

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Buffer a save within this transaction (best_effort only)."""
        self._require_best_effort("save")
        if "id" not in data:
            raise ValueError("JsonDBTransaction.save requires data with an 'id' field")
        key = (collection, str(data["id"]))
        # Defensive copy so callers can't mutate buffered state.
        self._pending[key] = dict(data)
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Read with buffered overlay (best_effort only)."""
        self._require_best_effort("get")
        key = (collection, str(id))
        if key in self._pending:
            pending = self._pending[key]
            if pending is _TOMBSTONE:
                return None
            return dict(pending)
        return await self.database.get(collection, id)

    async def delete(self, collection: str, id: str) -> bool:
        """Buffer a delete within this transaction (best_effort only)."""
        self._require_best_effort("delete")
        self._pending[(collection, str(id))] = _TOMBSTONE
        return True

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find with buffered overlay (best_effort only).

        The underlying ``find`` is called and the results are then
        adjusted to reflect any pending writes/deletes for the same
        collection. This is intentionally simple -- callers needing
        sophisticated isolation should use a real transactional
        database.
        """
        self._require_best_effort("find")
        from jvspatial.db.database import finalize_find_results
        from jvspatial.db.query import QueryEngine

        underlying = await self.database.find(collection, query, sort=None, limit=None)

        merged: Dict[str, Dict[str, Any]] = {
            str(rec.get("id", rec.get("_id"))): rec for rec in underlying
        }

        for (col, rec_id), pending in self._pending.items():
            if col != collection:
                continue
            if pending is _TOMBSTONE:
                merged.pop(rec_id, None)
                continue
            if not query or QueryEngine.match(pending, query):
                merged[rec_id] = dict(pending)
            else:
                # The buffered version no longer matches -- remove it from
                # the result if it was present in the underlying read.
                merged.pop(rec_id, None)

        return finalize_find_results(list(merged.values()), sort=sort, limit=limit)

    async def commit(self) -> None:
        """Apply all buffered operations (best_effort) or no-op-finalize (strict).

        In strict mode, ``commit()`` simply marks the transaction
        completed -- there are no buffered operations because every
        write/read/delete already raised. In best_effort mode, the
        buffered operations are flushed to the underlying database.
        """
        if not (self.is_active and not self.is_committed and not self.is_rolled_back):
            return
        if self.best_effort:
            for (collection, rec_id), pending in self._pending.items():
                if pending is _TOMBSTONE:
                    await self.database.delete(collection, rec_id)
                else:
                    await self.database.save(collection, pending)
            self._pending.clear()
        self.is_active = False
        self.is_committed = True

    async def rollback(self) -> None:
        """Discard all buffered operations."""
        if not (self.is_active and not self.is_committed and not self.is_rolled_back):
            return
        self._pending.clear()
        self.is_active = False
        self.is_rolled_back = True


@asynccontextmanager
async def transaction_context(database, transaction_id: Optional[str] = None):
    """Context manager for database transactions.

    Yields a ``Transaction`` when the database supports it, or ``None``
    when transactions are unavailable (callers should fall back to
    non-transactional writes).

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
    except Exception:
        await database.rollback_transaction(transaction)
        raise


__all__ = [
    "Transaction",
    "MongoDBTransaction",
    "JsonDBTransaction",
    "transaction_context",
]
