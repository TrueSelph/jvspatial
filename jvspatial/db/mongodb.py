"""MongoDB database implementation for spatial graph persistence."""

import asyncio
import contextlib
import os
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from jvspatial.db.database import Database, VersionConflictError


class MongoDB(Database):
    """MongoDB-based database implementation.

    Provides async MongoDB persistence for graph data with connection pooling,
    versioning support, and performance monitoring integration.
    """

    _client: Optional[AsyncIOMotorClient] = None
    _db = None
    _lock = asyncio.Lock()

    def __init__(self, **kwargs: Any) -> None:
        """Initialize MongoDB database.

        Args:
            **kwargs: MongoDB connection parameters (passed to AsyncIOMotorClient)
        """
        self._connection_kwargs = kwargs

    async def get_db(self) -> Any:
        """Get database instance with thread-safe initialization.

        Returns:
            MongoDB database instance

        Raises:
            RuntimeError: If connection cannot be established
        """
        if self._client is None:
            async with self._lock:
                if self._client is None:  # Double-check locking
                    try:
                        uri = self._connection_kwargs.get("uri") or os.getenv(
                            "JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"
                        )
                        db_name = self._connection_kwargs.get("db_name") or os.getenv(
                            "JVSPATIAL_MONGODB_DB_NAME", "jvspatial_db"
                        )

                        # Set default connection parameters if not provided
                        connection_params = {
                            "maxPoolSize": 10,
                            "minPoolSize": 5,
                            "connectTimeoutMS": 30000,
                            "socketTimeoutMS": 30000,
                            **self._connection_kwargs,
                        }
                        # Remove our custom params that aren't for motor
                        connection_params.pop("uri", None)
                        connection_params.pop("db_name", None)

                        self._client = AsyncIOMotorClient(uri, **connection_params)
                        self._db = self._client.get_database(db_name)

                        # Test connection
                        await self._client.admin.command("ismaster")

                        # Create indexes on first connection
                        await self._create_indexes()

                    except Exception as e:
                        self._client = None
                        self._db = None
                        raise RuntimeError(f"Failed to connect to MongoDB: {e}") from e

        return self._db

    async def _create_indexes(self) -> None:
        """Create required indexes for optimal performance.

        Raises:
            RuntimeError: If index creation fails
        """
        if not self._db:
            return

        collections = ["node", "edge", "walker", "object"]

        try:
            for coll_name in collections:
                coll = self._db[coll_name]
                # Create index on id field (unique)
                await coll.create_index("id", unique=True)
                # Create compound index for versioning if supported
                with contextlib.suppress(DuplicateKeyError):
                    await coll.create_index([("id", 1), ("_version", 1)])
        except Exception as e:
            raise RuntimeError(f"Failed to create database indexes: {e}") from e

    async def _get_collection(self, collection: str) -> AsyncIOMotorCollection:
        """Get collection with connection pooling.

        Args:
            collection: Collection name

        Returns:
            MongoDB collection instance

        Raises:
            ValueError: If collection name is invalid
            RuntimeError: If database connection fails
        """
        if not collection or not collection.replace("_", "").isalnum():
            raise ValueError(f"Invalid collection name: {collection}")

        db = await self.get_db()
        return db[collection]

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save document to MongoDB.

        Args:
            collection: Collection name
            data: Document data

        Returns:
            Saved document

        Raises:
            KeyError: If document data lacks required 'id' field for updates
            VersionConflictError: If version conflict occurs during update
            RuntimeError: If save operation fails
        """
        # Import here to avoid circular imports
        try:
            from jvspatial.core.context import perf_monitor
        except ImportError:
            perf_monitor = None

        start_time = asyncio.get_event_loop().time()
        operation = "update" if "id" in data else "insert"

        try:
            coll = await self._get_collection(collection)

            if "id" in data:
                # Update existing document with versioning
                current_version = data.get("_version", 1)
                data_to_save = data.copy()
                data_to_save["_version"] = current_version + 1

                result = await coll.find_one_and_update(
                    {"id": data["id"], "_version": current_version},
                    {"$set": data_to_save},
                    return_document=ReturnDocument.AFTER,
                    upsert=True,
                )

                if not result:
                    raise VersionConflictError(
                        f"Version conflict for document {data['id']} in {collection}"
                    )

                output = dict(result)
            else:
                # Insert new document
                data_to_save = data.copy()
                data_to_save["_version"] = 1

                try:
                    result = await coll.insert_one(data_to_save)
                    if not data_to_save.get("id"):
                        data_to_save["id"] = str(result.inserted_id)
                    output = data_to_save
                except DuplicateKeyError as e:
                    raise RuntimeError(f"Duplicate document ID in {collection}") from e

            if perf_monitor:
                duration = asyncio.get_event_loop().time() - start_time
                perf_monitor.record_db_operation(
                    collection=collection,
                    operation=operation,
                    duration=duration,
                    doc_size=len(str(data)),
                    version_conflict=False,
                )

            return output

        except (VersionConflictError, RuntimeError):
            raise
        except PyMongoError as e:
            if perf_monitor:
                perf_monitor.record_db_error(collection, operation, str(e))
            raise RuntimeError(f"MongoDB operation failed: {e}") from e
        except Exception as e:
            if perf_monitor:
                perf_monitor.record_db_error(collection, operation, str(e))
            raise RuntimeError(f"Unexpected error during save: {e}") from e

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID.

        Args:
            collection: Collection name
            id: Document ID

        Returns:
            Document data or None if not found
        """
        try:
            coll = await self._get_collection(collection)
            result = await coll.find_one({"id": id})
            return dict(result) if result is not None else None
        except PyMongoError:
            return None  # Return None for any database errors during get

    async def delete(self, collection: str, id: str) -> None:
        """Delete document by ID.

        Args:
            collection: Collection name
            id: Document ID
        """
        try:
            coll = await self._get_collection(collection)
            await coll.delete_one({"id": id})
        except PyMongoError:
            # Silently ignore deletion errors - document may not exist or be locked
            pass

    async def clean(self) -> None:
        """Delete edges that reference non-existent nodes.

        This method finds all edges with invalid source/target references
        and removes them from the database.
        """
        try:
            node_coll = await self._get_collection("node")
            edge_coll = await self._get_collection("edge")

            # Get all valid node IDs
            node_ids = await node_coll.distinct("id")

            # Delete edges with invalid source or target references
            # Check both new format (top-level) and legacy format (in context)
            delete_result = await edge_coll.delete_many(
                {
                    "$or": [
                        {"source": {"$nin": node_ids}},
                        {"target": {"$nin": node_ids}},
                        {"context.source": {"$nin": node_ids}},
                        {"context.target": {"$nin": node_ids}},
                    ]
                }
            )

            # Log cleanup results if performance monitor is available
            try:
                from jvspatial.core.context import perf_monitor

                if perf_monitor and delete_result.deleted_count > 0:
                    perf_monitor.record_db_operation(
                        collection="edge",
                        operation="clean",
                        duration=0,  # Duration not tracked for cleanup
                        doc_size=delete_result.deleted_count,
                    )
            except ImportError:
                pass

        except PyMongoError:
            # Silently ignore cleanup errors - this is a maintenance operation
            pass

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find documents matching query.

        Args:
            collection: Collection name
            query: MongoDB-style query parameters (empty dict for all records)

        Returns:
            List of matching documents
        """
        try:
            coll = await self._get_collection(collection)
            # MongoDB can handle the query natively - no need for custom parsing
            return [dict(doc) async for doc in coll.find(query)]
        except PyMongoError:
            return []  # Return empty list on database errors

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find the first document matching a query - MongoDB native implementation.

        Args:
            collection: Collection name
            query: MongoDB-style query

        Returns:
            First matching document or None if not found
        """
        try:
            coll = await self._get_collection(collection)
            result = await coll.find_one(query)
            return dict(result) if result else None
        except PyMongoError:
            return None

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count documents matching a query - MongoDB native implementation.

        Args:
            collection: Collection name
            query: MongoDB-style query (empty dict for all records)

        Returns:
            Number of matching documents
        """
        if query is None:
            query = {}
        try:
            coll = await self._get_collection(collection)
            result = await coll.count_documents(query)
            return int(result)
        except PyMongoError:
            return 0

    async def distinct(
        self, collection: str, field: str, query: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """Get distinct values for a field - MongoDB native implementation.

        Args:
            collection: Collection name
            field: Field name (supports dot notation)
            query: Optional query to filter documents

        Returns:
            List of distinct values
        """
        if query is None:
            query = {}
        try:
            coll = await self._get_collection(collection)
            result = await coll.distinct(field, query)
            return list(result)
        except PyMongoError:
            return []

    async def update_one(
        self,
        collection: str,
        filter_query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Dict[str, Any]:
        """Update the first document matching the filter - MongoDB native implementation.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query
            update: Update operations (supports $set, $unset, $inc, etc.)
            upsert: Create document if it doesn't exist

        Returns:
            Result information
        """
        try:
            coll = await self._get_collection(collection)
            result = await coll.update_one(filter_query, update, upsert=upsert)
            return {
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "upserted_id": result.upserted_id,
            }
        except PyMongoError:
            return {"matched_count": 0, "modified_count": 0}

    async def update_many(
        self, collection: str, filter_query: Dict[str, Any], update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update all documents matching the filter - MongoDB native implementation.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query
            update: Update operations

        Returns:
            Result information
        """
        try:
            coll = await self._get_collection(collection)
            result = await coll.update_many(filter_query, update)
            return {
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
            }
        except PyMongoError:
            return {"matched_count": 0, "modified_count": 0}

    async def delete_one(
        self, collection: str, filter_query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delete the first document matching the filter - MongoDB native implementation.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query

        Returns:
            Result information
        """
        try:
            coll = await self._get_collection(collection)
            result = await coll.delete_one(filter_query)
            return {"deleted_count": result.deleted_count}
        except PyMongoError:
            return {"deleted_count": 0}

    async def delete_many(
        self, collection: str, filter_query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delete all documents matching the filter - MongoDB native implementation.

        Args:
            collection: Collection name
            filter_query: MongoDB-style filter query

        Returns:
            Result information
        """
        try:
            coll = await self._get_collection(collection)
            result = await coll.delete_many(filter_query)
            return {"deleted_count": result.deleted_count}
        except PyMongoError:
            return {"deleted_count": 0}
