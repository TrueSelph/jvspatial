"""Database abstraction layer for spatial graph persistence."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Database(ABC):
    """Abstract base class for database adapters.

    Provides a generic interface for different database implementations
    to support asynchronous graph-based persistence with objects, nodes, and edges.

    All implementations must support:
    - Async CRUD operations (save, get, delete, find)
    - Collection-based data organization
    - Query operations with dict-based filters
    - Cleanup operations for orphaned references
    """

    @abstractmethod
    async def clean(self) -> None:
        """Clean up orphaned edges with invalid node references.

        This method should identify and remove any edges that reference
        non-existent nodes (invalid source or target references).
        """
        pass

    @abstractmethod
    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Args:
            collection: Collection name
            data: Record data

        Returns:
            Saved record with any database-generated fields

        Raises:
            VersionConflictError: If a version conflict occurs during update
        """

    @abstractmethod
    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data or None if not found
        """

    @abstractmethod
    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID.

        Args:
            collection: Collection name
            id: Record ID
        """

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

    # MongoDB-style query methods with default implementations
    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find the first record matching a query.

        Args:
            collection: Collection name
            query: MongoDB-style query

        Returns:
            First matching record or None if not found
        """
        results = await self.find(collection, query)
        return results[0] if results else None

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records matching a query.

        Args:
            collection: Collection name
            query: MongoDB-style query (empty dict for all records)

        Returns:
            Number of matching records
        """
        if query is None:
            query = {}
        results = await self.find(collection, query)
        return len(results)

    async def distinct(
        self, collection: str, field: str, query: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """Get distinct values for a field.

        Args:
            collection: Collection name
            field: Field name (supports dot notation)
            query: Optional query to filter documents

        Returns:
            List of distinct values
        """
        if query is None:
            query = {}

        documents = await self.find(collection, query)
        values = set()

        for doc in documents:
            value = self._get_field_value(doc, field)
            if value is not None:
                # Handle lists by adding each element
                if isinstance(value, list):
                    values.update(value)
                else:
                    values.add(value)

        return list(values)

    async def update_one(
        self,
        collection: str,
        filter_query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Dict[str, Any]:
        """Update the first document matching the filter.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query
            update: Update operations (supports $set, $unset, $inc, etc.)
            upsert: Create document if it doesn't exist

        Returns:
            Result information
        """
        # Find the document to update
        document = await self.find_one(collection, filter_query)

        if not document:
            if upsert:
                # Create new document from filter query and update operations
                new_doc = self._apply_update_operations({}, update)
                # Merge filter conditions that aren't operators
                for key, value in filter_query.items():
                    if not key.startswith("$") and key not in new_doc:
                        new_doc[key] = value
                # Generate ID if not present
                if "id" not in new_doc:
                    import uuid

                    new_doc["id"] = str(uuid.uuid4())
                await self.save(collection, new_doc)
                return {
                    "matched_count": 0,
                    "modified_count": 0,
                    "upserted_id": new_doc["id"],
                }
            else:
                return {"matched_count": 0, "modified_count": 0}

        # Apply update operations
        updated_doc = self._apply_update_operations(document.copy(), update)
        await self.save(collection, updated_doc)

        return {"matched_count": 1, "modified_count": 1}

    async def update_many(
        self, collection: str, filter_query: Dict[str, Any], update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update all documents matching the filter.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query
            update: Update operations

        Returns:
            Result information
        """
        documents = await self.find(collection, filter_query)

        for _modified_count, doc in enumerate(documents, 1):
            updated_doc = self._apply_update_operations(doc.copy(), update)
            await self.save(collection, updated_doc)

        return {"matched_count": len(documents), "modified_count": len(documents)}

    async def delete_one(
        self, collection: str, filter_query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delete the first document matching the filter.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query

        Returns:
            Result information
        """
        document = await self.find_one(collection, filter_query)
        if document and "id" in document:
            await self.delete(collection, document["id"])
            return {"deleted_count": 1}
        return {"deleted_count": 0}

    async def delete_many(
        self, collection: str, filter_query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delete all documents matching the filter.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query

        Returns:
            Result information
        """
        documents = await self.find(collection, filter_query)
        deleted_count = 0

        for doc in documents:
            if "id" in doc:
                await self.delete(collection, doc["id"])
                deleted_count += 1

        return {"deleted_count": deleted_count}

    def _get_field_value(self, document: Dict[str, Any], field: str) -> Any:
        """Get value from document using dot notation."""
        if "." not in field:
            return document.get(field)

        keys = field.split(".")
        current: Any = document

        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                try:
                    current = current[int(key)]
                except (IndexError, ValueError):
                    return None
            else:
                return None

        return current

    def _apply_update_operations(
        self, document: Dict[str, Any], update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply MongoDB-style update operations to a document."""
        result = document.copy()

        for operator, operations in update.items():
            if operator == "$set":
                for field, value in operations.items():
                    self._set_field_value(result, field, value)
            elif operator == "$unset":
                for field in operations.keys():
                    self._unset_field_value(result, field)
            elif operator == "$inc":
                for field, increment in operations.items():
                    current = self._get_field_value(result, field) or 0
                    self._set_field_value(result, field, current + increment)
            elif operator == "$mul":
                for field, multiplier in operations.items():
                    current = self._get_field_value(result, field) or 0
                    self._set_field_value(result, field, current * multiplier)
            elif operator == "$push":
                for field, value in operations.items():
                    current = self._get_field_value(result, field)
                    if not isinstance(current, list):
                        current = []
                    current.append(value)
                    self._set_field_value(result, field, current)
            elif operator == "$pull":
                for field, value in operations.items():
                    current = self._get_field_value(result, field)
                    if isinstance(current, list):
                        current = [item for item in current if item != value]
                        self._set_field_value(result, field, current)

        return result

    def _set_field_value(
        self, document: Dict[str, Any], field: str, value: Any
    ) -> None:
        """Set field value using dot notation."""
        if "." not in field:
            document[field] = value
            return

        keys = field.split(".")
        current = document

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def _unset_field_value(self, document: Dict[str, Any], field: str) -> None:
        """Remove field using dot notation."""
        if "." not in field:
            document.pop(field, None)
            return

        keys = field.split(".")
        current = document

        for key in keys[:-1]:
            if key not in current:
                return
            current = current[key]

        if isinstance(current, dict):
            current.pop(keys[-1], None)


class VersionConflictError(Exception):
    """Raised when a document version conflict occurs during update."""

    pass
