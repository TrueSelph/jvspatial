"""Database abstraction layer for spatial graph persistence."""

from abc import ABC, abstractmethod
from typing import List, Optional


class Database(ABC):
    """Abstract base class for database adapters."""

    @abstractmethod
    async def save(self: "Database", collection: str, data: dict) -> dict:
        """Save a record to the database.

        Args:
            collection: Collection name
            data: Record data

        Returns:
            Saved record
        """

    @abstractmethod
    async def get(self: "Database", collection: str, id: str) -> Optional[dict]:
        """Retrieve a record by ID.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data or None if not found
        """

    @abstractmethod
    async def delete(self: "Database", collection: str, id: str) -> None:
        """Delete a record by ID.

        Args:
            collection: Collection name
            id: Record ID
        """

    @abstractmethod
    async def find(self: "Database", collection: str, query: dict) -> List[dict]:
        """Find records matching a query.

        Args:
            collection: Collection name
            query: Query parameters

        Returns:
            List of matching records
        """
