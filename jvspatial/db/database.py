"""Simplified database interface focusing on essential CRUD operations.

This module provides a streamlined database interface that removes
unnecessary complexity while maintaining core functionality.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class Database(ABC):
    """Simplified abstract base class for database adapters.

    Provides essential CRUD operations without complex transaction support
    or MongoDB-style query methods. Focuses on core functionality.

    All implementations must support:
    - Basic CRUD operations (save, get, delete, find)
    - Collection-based data organization
    - Simple query operations with dict-based filters
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
