"""Simplified MongoDB database implementation."""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from jvspatial.db.database import Database
from jvspatial.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class MongoDB(Database):
    """Simplified MongoDB-based database implementation."""

    def __init__(
        self, uri: str = "mongodb://localhost:27017", db_name: str = "jvdb"
    ) -> None:
        """Initialize MongoDB database.

        Args:
            uri: MongoDB connection URI
            db_name: Database name
        """
        self.uri = uri
        self.db_name = db_name
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._created_indexes: Dict[str, Set[str]] = (
            {}
        )  # collection -> set of index names

    async def _ensure_connected(self) -> None:
        """Ensure database connection is established."""
        if self._client is None:
            self._client = AsyncIOMotorClient(self.uri)
            self._db = self._client[self.db_name]

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database."""
        await self._ensure_connected()

        # Ensure record has an ID
        if "_id" not in data and "id" not in data:
            import uuid

            data["_id"] = str(uuid.uuid4())
        elif "id" in data and "_id" not in data:
            data["_id"] = data["id"]

        try:
            collection_obj = self._db[collection]
            await collection_obj.replace_one({"_id": data["_id"]}, data, upsert=True)
            return data
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB save error: {e}") from e

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        await self._ensure_connected()

        try:
            collection_obj = self._db[collection]
            result = await collection_obj.find_one({"_id": id})
            return result
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB get error: {e}") from e

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        await self._ensure_connected()

        try:
            collection_obj = self._db[collection]
            await collection_obj.delete_one({"_id": id})
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB delete error: {e}") from e

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query."""
        await self._ensure_connected()

        try:
            collection_obj = self._db[collection]
            cursor = collection_obj.find(query)
            results = await cursor.to_list(length=None)
            return results
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB find error: {e}") from e

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Create an index on the specified field(s).

        Args:
            collection: Collection name
            field_or_fields: Single field name (str) or list of (field_name, direction) tuples for compound indexes
            unique: Whether the index should enforce uniqueness
            **kwargs: Additional MongoDB-specific options (e.g., expireAfterSeconds for TTL indexes)

        Raises:
            DatabaseError: If index creation fails
        """
        await self._ensure_connected()

        try:
            collection_obj = self._db[collection]

            # Initialize index tracking for this collection if needed
            if collection not in self._created_indexes:
                self._created_indexes[collection] = set()

            # Build index specification
            if isinstance(field_or_fields, str):
                # Single field index
                index_spec = [(field_or_fields, 1)]
                index_name = f"{field_or_fields}_1"
            else:
                # Compound index
                index_spec = field_or_fields
                index_name = "_".join(
                    f"{field}_{direction}" for field, direction in index_spec
                )

            # Check if index already exists
            if index_name in self._created_indexes[collection]:
                return  # Index already created

            # Build index options
            index_options: Dict[str, Any] = {}
            if unique:
                index_options["unique"] = True
            if "expireAfterSeconds" in kwargs:
                index_options["expireAfterSeconds"] = kwargs["expireAfterSeconds"]
            # Add any other MongoDB-specific options
            for key, value in kwargs.items():
                if key not in ("expireAfterSeconds",):  # Already handled
                    index_options[key] = value

            # Create the index
            await collection_obj.create_index(
                index_spec, name=index_name, **index_options
            )

            # Track that we created this index
            self._created_indexes[collection].add(index_name)

            logger.debug(
                f"Created index '{index_name}' on collection '{collection}' "
                f"(unique={unique}, options={index_options})"
            )

        except PyMongoError as e:
            raise DatabaseError(f"MongoDB index creation error: {e}") from e

    async def close(self) -> None:
        """Close the database connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._created_indexes.clear()
