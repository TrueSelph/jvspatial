"""Simplified MongoDB database implementation.

Index creation
    By default, index creation uses background mode to avoid blocking database operations.
    This allows the database to remain operational during index creation, which is especially
    important for large collections. Background index creation is slower but non-blocking.
    Pass ``background=False`` to ``create_index()`` for foreground (blocking) builds.

    When ``create_index`` fails with MongoDB error **85** (IndexOptionsConflict — same index
    name, different options) or **86** (IndexKeySpecsConflict — same key pattern, different
    name), this implementation drops the conflicting index and retries, so schema changes
    in code can migrate existing databases without manual ``dropIndex`` steps.

    ``drop_deprecated_indexes(deprecated)`` removes named indexes listed by collection
    (e.g. orphan names from earlier releases). Host applications may call it during
    startup along with ``GraphContext.ensure_indexes`` for their entity types.
"""

import contextlib
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, Union

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import (
    ConnectionFailure,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from jvspatial.db.database import Database
from jvspatial.exceptions import DatabaseError
from jvspatial.utils.retry import retry_async

logger = logging.getLogger(__name__)


def _is_connection_error(exc: BaseException) -> bool:
    """Return True if the exception indicates a connection/network error worth retrying."""
    if isinstance(exc, (ConnectionFailure, ServerSelectionTimeoutError)):
        return True
    msg = str(exc).lower()
    return "connection closed" in msg or "connection refused" in msg


def _is_retryable_mongo_error(exc: BaseException) -> bool:
    """Predicate used by the shared retry helper for Mongo ops.

    Captures both the existing ``PyMongoError`` connection-error
    detection and the "Event loop is closed" ``RuntimeError`` we see
    when Motor reuses a stale loop reference across requests.
    """
    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        return "event loop is closed" in msg or "closed" in msg
    if isinstance(exc, PyMongoError):
        return _is_connection_error(exc)
    return False


class MongoDB(Database):
    """Simplified MongoDB-based database implementation."""

    # Advertised capability. The adapter implements the transactional API;
    # the deployment must be a replica set (even single-node) for the
    # actual ``begin_transaction()`` call to succeed at runtime.
    supports_transactions: bool = True

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        db_name: str = "jvdb",
        max_pool_size: Optional[int] = None,
        min_pool_size: Optional[int] = None,
    ) -> None:
        """Initialize MongoDB database.

        Args:
            uri: MongoDB connection URI
            db_name: Database name
            max_pool_size: Maximum connections in pool (default: 10, Lambda-friendly)
            min_pool_size: Minimum connections in pool (default: 0, Lambda-friendly)
        """
        self.uri = uri
        self.db_name = db_name
        from jvspatial.env import env

        self.max_pool_size = (
            max_pool_size
            if max_pool_size is not None
            else (env("JVSPATIAL_MONGODB_MAX_POOL_SIZE", parse=int) or 10)
        )
        self.min_pool_size = (
            min_pool_size
            if min_pool_size is not None
            else (env("JVSPATIAL_MONGODB_MIN_POOL_SIZE", parse=int) or 0)
        )
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._created_indexes: Dict[str, Set[str]] = (
            {}
        )  # collection -> set of index names

    async def _ensure_connected(self) -> None:
        """Ensure database connection is established.

        This method handles event loop changes by detecting when the client
        was created with a different (or closed) event loop and recreating
        the connection as needed.
        """
        import asyncio

        # Early return if both client and db are already set (common in tests)
        if self._client is not None and self._db is not None:
            # Detect if this is a mock object (for testing) - if so, skip validation
            is_mock = (
                hasattr(self._client, "__class__")
                and hasattr(self._client.__class__, "__module__")
                and "mock" in self._client.__class__.__module__.lower()
            ) or type(self._client).__name__ in ("MagicMock", "Mock", "AsyncMock")

            # For mocks, always preserve the connection
            if is_mock:
                return

        # Check if client exists and event loop is still valid
        if self._client is not None:
            # Detect if this is a mock object (for testing) - mocks typically have __class__.__module__ == 'unittest.mock'
            # or are instances of MagicMock/Mock. Skip event loop validation for mocks.
            is_mock = (
                hasattr(self._client, "__class__")
                and hasattr(self._client.__class__, "__module__")
                and "mock" in self._client.__class__.__module__.lower()
            ) or type(self._client).__name__ in ("MagicMock", "Mock", "AsyncMock")

            if not is_mock:
                try:
                    # Get the current running event loop
                    current_loop = asyncio.get_running_loop()

                    # Check if the client's event loop is still valid
                    # Motor stores the loop in _io_loop attribute
                    if hasattr(self._client, "_io_loop"):
                        client_loop = self._client._io_loop
                        # If loops don't match or client loop is closed, recreate
                        if client_loop is not current_loop:
                            # Different event loop - need to recreate client
                            logger.debug(
                                "MongoDB client created with different event loop, recreating connection"
                            )
                            with contextlib.suppress(Exception):
                                self._client.close()  # Ignore errors when closing invalid client
                            self._client = None
                            self._db = None
                        elif (
                            hasattr(client_loop, "is_closed")
                            and client_loop.is_closed()
                        ):
                            # Event loop is closed - recreate client
                            logger.debug(
                                "MongoDB client event loop is closed, recreating connection"
                            )
                            with contextlib.suppress(Exception):
                                self._client.close()  # Ignore errors when closing invalid client
                            self._client = None
                            self._db = None
                except RuntimeError:
                    # No running event loop - this shouldn't happen in async context
                    # but if it does, only recreate if not a mock (mocks should be preserved)
                    if not is_mock:
                        logger.debug(
                            "No running event loop detected, recreating MongoDB connection"
                        )
                        if self._client:
                            with contextlib.suppress(Exception):
                                self._client.close()  # Ignore errors when closing invalid client
                        self._client = None
                        self._db = None
            # If it's a mock, preserve the existing connection

        # Create new client if needed (but not if we have a mock)
        if self._client is None:
            self._client = AsyncIOMotorClient(
                self.uri,
                maxPoolSize=self.max_pool_size,
                minPoolSize=self.min_pool_size,
                maxIdleTimeMS=60000,  # Close idle connections before DocumentDB timeout
            )
            self._db = self._client[self.db_name]

        # Ensure _db is set if client exists but _db is None (shouldn't happen, but be defensive)
        if self._client is not None and self._db is None:
            self._db = self._client[self.db_name]

    def _drop_connection_on_retry(
        self, exc: BaseException, attempt: int, sleep_for: float
    ) -> None:
        """``on_retry`` hook that resets the cached client/db.

        Called by :func:`retry_async` between failed attempts. The
        next call to :meth:`_ensure_connected` (which the operation
        re-runs at the top) will re-establish the connection.
        """
        logger.debug(
            "MongoDB op retry %d after %s; resetting client (sleep=%.3fs)",
            attempt,
            type(exc).__name__,
            sleep_for,
        )
        self._client = None
        self._db = None

    async def _run_with_reconnect(
        self, op_name: str, coro_factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Execute ``coro_factory()`` with one reconnect-on-fail retry.

        Any non-retryable exception is wrapped in
        :class:`DatabaseError`. Retry semantics match the previous
        per-method implementations: 2 attempts total (one original +
        one retry), connection state reset between them.
        """
        try:
            return await retry_async(
                coro_factory,
                retry_on=_is_retryable_mongo_error,
                max_attempts=2,
                base_delay=0.0,
                max_delay=0.0,
                jitter=False,
                on_retry=self._drop_connection_on_retry,
            )
        except (RuntimeError, PyMongoError) as e:
            raise DatabaseError(f"MongoDB {op_name} error: {e}") from e

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database."""
        # Ensure record has an ID before we hand the closure to the
        # retry helper so the second attempt sees the same payload.
        if "_id" not in data and "id" not in data:
            import uuid

            uuid_obj = uuid.uuid4()
            # Handle both real UUID objects and mocks (for testing)
            if hasattr(uuid_obj, "hex"):
                hex_value = getattr(uuid_obj, "hex", None)
                if hex_value and isinstance(hex_value, str):
                    data["_id"] = hex_value
                else:
                    data["_id"] = str(uuid_obj)
            else:
                data["_id"] = str(uuid_obj)
        elif "id" in data and "_id" not in data:
            data["_id"] = data["id"]

        async def _save_op() -> Dict[str, Any]:
            await self._ensure_connected()
            if self._db is None:
                raise DatabaseError("MongoDB database connection not established")
            collection_obj = self._db[collection]
            await collection_obj.replace_one({"_id": data["_id"]}, data, upsert=True)
            return data

        return await self._run_with_reconnect("save", _save_op)

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""

        async def _get_op() -> Optional[Dict[str, Any]]:
            await self._ensure_connected()
            if self._db is None:
                raise DatabaseError("MongoDB database connection not established")
            collection_obj = self._db[collection]
            return await collection_obj.find_one({"_id": id})

        return await self._run_with_reconnect("get", _get_op)

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""

        async def _delete_op() -> None:
            await self._ensure_connected()
            if self._db is None:
                raise DatabaseError("MongoDB database connection not established")
            collection_obj = self._db[collection]
            await collection_obj.delete_one({"_id": id})

        await self._run_with_reconnect("delete", _delete_op)

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find records matching a query."""

        async def _find_op() -> List[Dict[str, Any]]:
            await self._ensure_connected()
            if self._db is None:
                raise DatabaseError("MongoDB database connection not established")
            collection_obj = self._db[collection]
            cursor = collection_obj.find(query)
            if sort:
                cursor = cursor.sort(sort)
            if limit is not None:
                cursor = cursor.limit(limit)
            return await cursor.to_list(length=None)

        return await self._run_with_reconnect("find", _find_op)

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Bulk fetch via a single ``find({"_id": {"$in": ids}})``.

        Returns ``{id: record}`` for ids that exist; missing ids are
        absent from the result. De-duplicates the input id list.
        """
        if not ids:
            return {}
        await self._ensure_connected()
        if self._db is None:
            raise DatabaseError("MongoDB database connection not established")
        unique_ids = list(dict.fromkeys(ids))
        try:
            collection_obj = self._db[collection]
            cursor = collection_obj.find({"_id": {"$in": unique_ids}})
            docs = await cursor.to_list(length=None)
        except (RuntimeError, PyMongoError) as e:
            # Reuse the existing reconnect-on-stale pattern by deferring
            # to the base class default if the wire fails. The base
            # falls back to N serial get() calls which themselves
            # already handle reconnect.
            if isinstance(e, RuntimeError) and "closed" not in str(e).lower():
                raise DatabaseError(f"MongoDB find_many error: {e}") from e
            if isinstance(e, PyMongoError) and not _is_connection_error(e):
                raise DatabaseError(f"MongoDB find_many error: {e}") from e
            self._client = None
            self._db = None
            await self._ensure_connected()
            if self._db is None:
                raise DatabaseError(
                    "Failed to establish MongoDB connection after retry"
                )
            collection_obj = self._db[collection]
            cursor = collection_obj.find({"_id": {"$in": unique_ids}})
            docs = await cursor.to_list(length=None)
        return {str(doc["_id"]): doc for doc in docs}

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Bulk write via ``bulk_write`` with ``ordered=False``.

        Partial successes are reported -- a single record's failure
        does not block the rest of the batch. Returns the number of
        records the server reported as either upserted or modified.
        """
        if not records:
            return 0
        for r in records:
            if "id" not in r:
                raise ValueError(
                    "bulk_save requires every record to have an 'id' field"
                )
        await self._ensure_connected()
        if self._db is None:
            raise DatabaseError("MongoDB database connection not established")

        from pymongo import ReplaceOne

        ops = []
        for r in records:
            doc = dict(r)
            if "_id" not in doc:
                doc["_id"] = doc["id"]
            ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))

        try:
            collection_obj = self._db[collection]
            result = await collection_obj.bulk_write(ops, ordered=False)
        except PyMongoError as e:
            if _is_connection_error(e):
                self._client = None
                self._db = None
                await self._ensure_connected()
                if self._db is None:
                    raise DatabaseError(
                        "Failed to establish MongoDB connection after retry"
                    )
                collection_obj = self._db[collection]
                result = await collection_obj.bulk_write(ops, ordered=False)
            else:
                raise DatabaseError(f"MongoDB bulk_save error: {e}") from e
        # ``upserted_count`` covers brand-new docs, ``matched_count``
        # covers existing docs we replaced (whether the bytes changed
        # or not). Sum is the total "successfully persisted" count.
        upserted = int(getattr(result, "upserted_count", 0) or 0)
        matched = int(getattr(result, "matched_count", 0) or 0)
        return upserted + matched

    async def find_one_and_delete(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Atomically find and delete the first record matching a query.

        Uses MongoDB native find_one_and_delete for atomicity. Returns the
        deleted document if found, None otherwise. Useful for work claiming
        (e.g., batch processing) where only one consumer should succeed.
        """
        await self._ensure_connected()

        if self._db is None:
            raise DatabaseError("MongoDB database connection not established")

        try:
            collection_obj = self._db[collection]
            return await collection_obj.find_one_and_delete(query)
        except RuntimeError as e:
            if "Event loop is closed" in str(e) or "closed" in str(e).lower():
                logger.debug(
                    "Event loop closed during operation, recreating MongoDB connection"
                )
                self._client = None
                self._db = None
                await self._ensure_connected()
                if self._db is None:
                    raise DatabaseError(
                        "Failed to establish MongoDB connection after retry"
                    )
                collection_obj = self._db[collection]
                return await collection_obj.find_one_and_delete(query)
            raise DatabaseError(f"MongoDB find_one_and_delete error: {e}") from e
        except PyMongoError as e:
            if _is_connection_error(e):
                logger.debug(
                    "MongoDB connection error during find_one_and_delete, recreating and retrying: %s",
                    e,
                )
                self._client = None
                self._db = None
                await self._ensure_connected()
                if self._db is None:
                    raise DatabaseError(
                        "Failed to establish MongoDB connection after retry"
                    )
                collection_obj = self._db[collection]
                return await collection_obj.find_one_and_delete(query)
            raise DatabaseError(f"MongoDB find_one_and_delete error: {e}") from e

    async def count(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count records using MongoDB's native count_documents / estimated_document_count.

        This is an O(1) server-side operation rather than the base-class
        ``find + len`` fallback.
        """
        await self._ensure_connected()
        if self._db is None:
            raise DatabaseError("MongoDB database connection not established")
        q = query or {}
        try:
            collection_obj = self._db[collection]
            if not q:
                # estimated_document_count is the fastest path for full counts.
                return await collection_obj.estimated_document_count()
            return await collection_obj.count_documents(q)
        except PyMongoError as e:
            if _is_connection_error(e):
                logger.debug(
                    "MongoDB connection error during count, recreating and retrying: %s",
                    e,
                )
                self._client = None
                self._db = None
                await self._ensure_connected()
                if self._db is None:
                    raise DatabaseError(
                        "Failed to establish MongoDB connection after retry"
                    )
                collection_obj = self._db[collection]
                if not q:
                    return await collection_obj.estimated_document_count()
                return await collection_obj.count_documents(q)
            raise DatabaseError(f"MongoDB count error: {e}") from e

    async def find_one_and_update(
        self,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Atomically find and update the first record matching a query.

        Uses MongoDB native find_one_and_update with ReturnDocument.AFTER.
        Supports update operators: $push, $set, $setOnInsert, etc. Returns the
        updated document (or the newly created document when upsert=True).
        """
        from pymongo import ReturnDocument

        await self._ensure_connected()

        if self._db is None:
            raise DatabaseError("MongoDB database connection not established")

        try:
            collection_obj = self._db[collection]
            return await collection_obj.find_one_and_update(
                query,
                update,
                upsert=upsert,
                return_document=ReturnDocument.AFTER,
            )
        except RuntimeError as e:
            if "Event loop is closed" in str(e) or "closed" in str(e).lower():
                logger.debug(
                    "Event loop closed during operation, recreating MongoDB connection"
                )
                self._client = None
                self._db = None
                await self._ensure_connected()
                if self._db is None:
                    raise DatabaseError(
                        "Failed to establish MongoDB connection after retry"
                    )
                collection_obj = self._db[collection]
                return await collection_obj.find_one_and_update(
                    query,
                    update,
                    upsert=upsert,
                    return_document=ReturnDocument.AFTER,
                )
            raise DatabaseError(f"MongoDB find_one_and_update error: {e}") from e
        except PyMongoError as e:
            if _is_connection_error(e):
                logger.debug(
                    "MongoDB connection error during find_one_and_update, "
                    "recreating and retrying: %s",
                    e,
                )
                self._client = None
                self._db = None
                await self._ensure_connected()
                if self._db is None:
                    raise DatabaseError(
                        "Failed to establish MongoDB connection after retry"
                    )
                collection_obj = self._db[collection]
                return await collection_obj.find_one_and_update(
                    query,
                    update,
                    upsert=upsert,
                    return_document=ReturnDocument.AFTER,
                )
            raise DatabaseError(f"MongoDB find_one_and_update error: {e}") from e

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
            **kwargs: Additional MongoDB-specific options (e.g., expireAfterSeconds for TTL indexes).
                     By default, background=True is used for non-blocking index creation.
                     Pass background=False to use foreground (blocking) index creation.

        Raises:
            DatabaseError: If index creation fails
        """
        await self._ensure_connected()

        if self._db is None:
            raise DatabaseError("MongoDB database connection not established")

        try:
            collection_obj = self._db[collection]

            # Initialize index tracking for this collection if needed
            if collection not in self._created_indexes:
                self._created_indexes[collection] = set()

            kwargs = dict(kwargs)
            # Custom index name (e.g. from @compound_index name=) so partial indexes
            # do not collide with legacy auto-generated names in MongoDB.
            name_override = kwargs.pop("name", None)

            # Build index specification
            if isinstance(field_or_fields, str):
                # Single field index
                index_spec = [(field_or_fields, 1)]
                index_name = name_override or f"{field_or_fields}_1"
            else:
                # Compound index
                index_spec = field_or_fields
                if name_override:
                    index_name = name_override
                else:
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

            # Use background index creation by default to avoid blocking operations
            # This allows the database to remain operational during index creation
            # Can be overridden by passing background=False in kwargs
            index_options["background"] = kwargs.get("background", True)

            # Add any other MongoDB-specific options
            for key, value in kwargs.items():
                if key not in ("expireAfterSeconds", "background"):  # Already handled
                    index_options[key] = value

            # Create the index, auto-dropping if options have changed since last run
            try:
                await collection_obj.create_index(
                    index_spec, name=index_name, **index_options
                )
            except OperationFailure as e:
                if e.code == 85:  # IndexOptionsConflict: same name, different options
                    logger.info(
                        f"Index '{index_name}' on '{collection}' exists with "
                        f"different options; dropping and recreating"
                    )
                    try:
                        await collection_obj.drop_index(index_name)
                    except OperationFailure as drop_err:
                        if drop_err.code != 27:  # 27 = IndexNotFound — already gone
                            raise DatabaseError(
                                f"MongoDB index drop error: {drop_err}"
                            ) from drop_err
                    await collection_obj.create_index(
                        index_spec, name=index_name, **index_options
                    )
                elif (
                    e.code == 86
                ):  # IndexKeySpecsConflict: same key pattern, different name
                    # The conflicting index has the same key pattern but a different
                    # name. Scan index_information() to find it and drop by actual name.
                    existing_indexes = await collection_obj.index_information()
                    spec_keys = [(f, d) for f, d in index_spec]
                    conflicting_name = None
                    for ex_name, ex_info in existing_indexes.items():
                        ex_keys = list(ex_info.get("key", {}).items())
                        if ex_keys == spec_keys and ex_name != index_name:
                            conflicting_name = ex_name
                            break
                    if conflicting_name:
                        logger.info(
                            f"Index '{conflicting_name}' on '{collection}' has the "
                            f"same key pattern as '{index_name}'; replacing with "
                            f"updated definition"
                        )
                        await collection_obj.drop_index(conflicting_name)
                    else:
                        logger.warning(
                            f"IndexKeySpecsConflict for '{index_name}' on "
                            f"'{collection}' but no conflicting index found by key "
                            f"scan; attempting create anyway"
                        )
                    await collection_obj.create_index(
                        index_spec, name=index_name, **index_options
                    )
                else:
                    raise DatabaseError(f"MongoDB index creation error: {e}") from e

            # Track that we created this index
            self._created_indexes[collection].add(index_name)

            logger.debug(
                f"Created index '{index_name}' on collection '{collection}' "
                f"(unique={unique}, options={index_options})"
            )

        except PyMongoError as e:
            raise DatabaseError(f"MongoDB index creation error: {e}") from e

    async def begin_transaction(self):
        """Start a MongoDB transaction (requires replica set).

        Returns a ``MongoDBTransaction`` whose session is bound to a
        ``start_transaction`` call.  If the deployment does not support
        transactions (standalone / DocumentDB without transactions), the
        returned object will be ``None`` and callers should fall back to
        non-transactional writes.
        """
        from jvspatial.db.transaction import MongoDBTransaction

        await self._ensure_connected()
        if self._client is None or self._db is None:
            return None
        try:
            import uuid

            session = await self._client.start_session()
            session.start_transaction()
            return MongoDBTransaction(str(uuid.uuid4()), session, self._db)
        except Exception:
            logger.debug("Transactions not available on this deployment", exc_info=True)
            return None

    async def commit_transaction(self, txn) -> None:
        """Commit the given transaction and end its session."""
        if txn is not None:
            await txn.commit()
            txn.session.end_session()

    async def rollback_transaction(self, txn) -> None:
        """Roll back the given transaction and end its session."""
        if txn is not None:
            await txn.rollback()
            txn.session.end_session()

    async def drop_deprecated_indexes(self, deprecated: Dict[str, List[str]]) -> None:
        """Drop indexes that have been removed or renamed in code.

        Silently skips indexes that no longer exist (IndexNotFound). Any other
        error is logged as a warning so that startup can continue.

        Args:
            deprecated: Mapping of collection name to list of index names to drop.
                        Example: ``{"node": ["conv_id_only", "context.session_id_1"]}``
        """
        await self._ensure_connected()
        if self._db is None:
            return
        for collection, names in deprecated.items():
            coll = self._db[collection]
            for name in names:
                try:
                    await coll.drop_index(name)
                    logger.info(f"Dropped deprecated index '{name}' on '{collection}'")
                except OperationFailure as ex:
                    if ex.code == 27:  # IndexNotFound — already removed, fine
                        pass
                    else:
                        logger.warning(
                            f"Could not drop deprecated index '{name}' on "
                            f"'{collection}': {ex}"
                        )

    async def close(self) -> None:
        """Close the database connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._created_indexes.clear()
