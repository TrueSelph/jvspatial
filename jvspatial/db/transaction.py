"""Transaction support for database operations.

This module provides transaction management for ACID operations across
different database implementations.
"""

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional


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
        self, collection: str, query: Dict[str, Any]
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
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching query within this MongoDB transaction."""
        coll = self._db[collection]
        cursor = coll.find(query, session=self.session)
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


class JsonDBTransaction(Transaction):
    """JsonDB transaction implementation (no-op for file-based storage)."""

    def __init__(self, database):
        """Initialize JsonDB transaction.

        Args:
            database: JsonDB instance
        """
        import uuid

        super().__init__(str(uuid.uuid4()))
        self.database = database
        self.is_active = True
        # JsonDB doesn't support true transactions, so we simulate them

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record within this JsonDB transaction (simulated)."""
        # For JsonDB, we just delegate to the database since it doesn't support transactions
        return await self.database.save(collection, data)

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID within this JsonDB transaction (simulated)."""
        # For JsonDB, we just delegate to the database since it doesn't support transactions
        return await self.database.get(collection, id)

    async def delete(self, collection: str, id: str) -> bool:
        """Delete a record within this JsonDB transaction (simulated)."""
        # For JsonDB, we just delegate to the database since it doesn't support transactions
        return await self.database.delete(collection, id)

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching query within this JsonDB transaction (simulated)."""
        # For JsonDB, we just delegate to the database since it doesn't support transactions
        return await self.database.find(collection, query)

    async def commit(self) -> None:
        """Commit this JsonDB transaction (simulated)."""
        if self.is_active and not self.is_committed and not self.is_rolled_back:
            self.is_active = False
            self.is_committed = True

    async def rollback(self) -> None:
        """Rollback this JsonDB transaction (simulated)."""
        if self.is_active and not self.is_committed and not self.is_rolled_back:
            self.is_active = False
            self.is_rolled_back = True


class JSONTransaction(Transaction):
    """JSON database transaction implementation (no-op for file-based storage)."""

    def __init__(self, transaction_id: str):
        """Initialize JSON transaction.

        Args:
            transaction_id: Unique identifier for this transaction
        """
        super().__init__(transaction_id)
        self.is_active = True
        # JSON database doesn't support true transactions, so we simulate them

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record within this JSON transaction (simulated)."""
        # For JSON database, we just track operations but don't implement true transactions
        raise NotImplementedError("JSON transaction save not implemented")

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID within this JSON transaction (simulated)."""
        # For JSON database, we just track operations but don't implement true transactions
        raise NotImplementedError("JSON transaction get not implemented")

    async def delete(self, collection: str, id: str) -> bool:
        """Delete a record within this JSON transaction (simulated)."""
        # For JSON database, we just track operations but don't implement true transactions
        raise NotImplementedError("JSON transaction delete not implemented")

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching query within this JSON transaction (simulated)."""
        # For JSON database, we just track operations but don't implement true transactions
        raise NotImplementedError("JSON transaction find not implemented")

    async def commit(self) -> None:
        """Commit this JSON transaction (simulated)."""
        if self.is_active and not self.is_committed and not self.is_rolled_back:
            self.is_active = False
            self.is_committed = True

    async def rollback(self) -> None:
        """Rollback this JSON transaction (simulated)."""
        if self.is_active and not self.is_committed and not self.is_rolled_back:
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
    "JSONTransaction",
    "transaction_context",
]
