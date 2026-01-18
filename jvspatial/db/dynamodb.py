"""DynamoDB database implementation for AWS Lambda serverless deployments.

Index Creation Behavior:
    By default, indexes are NOT created automatically. To enable automatic index creation,
    set the environment variable:

        JVSPATIAL_AUTO_CREATE_INDEXES=true

    When automatic index creation is enabled, indexes are created asynchronously and do NOT
    wait for Global Secondary Indexes (GSI) to become active by default, allowing immediate
    graph usage. Indexes will be available for queries once they become active (typically
    a few minutes).

    To enable waiting for index activation (when auto-create is enabled), set:

        JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX=true

    When set to true, the system will wait up to 5 minutes per index for activation before
    proceeding, which can cause significant delays during initialization.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    import aioboto3
    from botocore.exceptions import ClientError

    try:
        from aiobotocore.config import AioConfig as Config
    except ImportError:
        # Fallback to botocore.config.Config if aiobotocore.config not available
        from botocore.config import Config

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False
    aioboto3 = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment, misc]
    Config = None  # type: ignore[assignment, misc]

from jvspatial.db.database import Database
from jvspatial.db.query import QueryEngine
from jvspatial.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class DynamoDB(Database):
    """DynamoDB-based database implementation for serverless deployments.

    This implementation uses DynamoDB tables to store collections, with each
    collection mapped to a DynamoDB table. The table uses a composite key:
    - Partition key: collection name
    - Sort key: record ID

    Attributes:
        table_name: Base table name (default: "jvspatial")
        region_name: AWS region (default: "us-east-1")
        endpoint_url: Optional endpoint URL for local testing
        aws_access_key_id: Optional AWS access key
        aws_secret_access_key: Optional AWS secret key
    """

    def __init__(
        self,
        table_name: str = "jvspatial",
        region_name: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ) -> None:
        """Initialize DynamoDB database.

        Args:
            table_name: Base table name for storing data
            region_name: AWS region name
            endpoint_url: Optional endpoint URL for local DynamoDB testing
            aws_access_key_id: Optional AWS access key ID
            aws_secret_access_key: Optional AWS secret access key
        """
        if not _BOTO3_AVAILABLE:
            raise ImportError(
                "aioboto3 is required for DynamoDB support. "
                "Install it with: pip install -r requirements-serverless.txt "
                "or pip install aioboto3>=12.0.0"
            )

        self.table_name = table_name
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

        # Build DynamoDB client kwargs once for reuse
        self._dynamodb_kwargs: Dict[str, Any] = {"region_name": self.region_name}
        if self.endpoint_url:
            self._dynamodb_kwargs["endpoint_url"] = self.endpoint_url
        if self.aws_access_key_id:
            self._dynamodb_kwargs["aws_access_key_id"] = self.aws_access_key_id
        if self.aws_secret_access_key:
            self._dynamodb_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        # Configure connection pool for Lambda (optimal for serverless)
        # max_pool_connections: 10 is a good default for Lambda
        # Higher values don't help much in Lambda due to concurrency limits
        # Use standard retry mode instead of adaptive to avoid potential hanging issues
        config_kwargs = {
            "max_pool_connections": 10,
            "retries": {
                "max_attempts": 3,
                "mode": "standard",  # Standard mode is more reliable than adaptive
            },
        }
        # Try to add timeout parameters if supported
        try:
            config_kwargs["connect_timeout"] = 10
            config_kwargs["read_timeout"] = 30
        except Exception:
            pass  # If not supported, continue without them

        try:
            self._dynamodb_kwargs["config"] = Config(**config_kwargs)
        except Exception as e:
            # If config creation fails, use basic config
            logger.warning(
                f"Failed to create Config with advanced options: {e}. Using basic config."
            )
            self._dynamodb_kwargs["config"] = Config(
                max_pool_connections=10,
                retries={
                    "max_attempts": 3,
                    "mode": "standard",
                },
            )

        # DynamoDB session will be created on first use
        self._session: Optional[Any] = None
        # Persistent client for reuse across operations (critical for Lambda performance)
        self._client: Optional[Any] = None
        # Store the context manager so we can properly exit it on close
        self._client_context: Optional[Any] = None
        # Track the event loop the client was created in to detect loop changes
        self._client_event_loop: Optional[Any] = None
        self._client_lock = asyncio.Lock()
        self._tables_created: Dict[str, bool] = {}  # Track which tables we've created
        # Track indexed fields per collection: {collection: {field_path: {"gsi_name": str, "unique": bool, "direction": int}}}
        self._indexed_fields: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Track GSI names per collection to avoid duplicate creation
        self._gsi_names: Dict[str, Set[str]] = {}

    async def _close_aiohttp_session_directly(self) -> None:
        """Attempt to close the aiohttp session directly.

        This is used when the event loop is closed and we can't use __aexit__.
        """
        if self._client is None:
            return
        await self._close_aiohttp_session_from_client(
            self._client, asyncio.get_event_loop()
        )

    async def _close_aiohttp_session_from_client(self, client: Any, loop: Any) -> None:
        """Attempt to close the aiohttp session from a client reference.

        Note: This may not work if the session is tied to a closed event loop,
        but we try our best to clean up.
        """
        import contextlib

        with contextlib.suppress(Exception):
            # Access the aiohttp session through the aiobotocore client
            # AioEndpoint uses 'http_session' attribute (not '_client')
            if hasattr(client, "_endpoint"):
                endpoint = getattr(client, "_endpoint", None)
                if endpoint and hasattr(endpoint, "http_session"):
                    http_client = getattr(endpoint, "http_session", None)
                    if http_client and hasattr(http_client, "close"):
                        if asyncio.iscoroutinefunction(http_client.close):
                            with contextlib.suppress(
                                RuntimeError, AttributeError, asyncio.TimeoutError
                            ):
                                # Use timeout to prevent hanging
                                await asyncio.wait_for(http_client.close(), timeout=0.5)
                            # Loop is closed, session already closed, or timeout - try direct connector close
                            with contextlib.suppress(Exception):
                                if hasattr(http_client, "_connector"):
                                    connector = getattr(http_client, "_connector", None)
                                    if connector and hasattr(connector, "close"):
                                        # Close connector synchronously (it's not async)
                                        connector.close()
                        else:
                            http_client.close()

    async def _get_session(self) -> Any:
        """Get or create aioboto3 session.

        Returns:
            aioboto3 session
        """
        if self._session is None:
            self._session = aioboto3.Session()
        return self._session

    async def _get_client(self) -> Any:
        """Get or create persistent DynamoDB client.

        This method implements client reuse to avoid the overhead of creating
        a new client for every operation, which is critical for Lambda performance.

        If the event loop has changed (e.g., after bootstrap), the client is
        recreated to avoid "Event loop is closed" errors.

        Returns:
            DynamoDB client (reused across operations)
        """
        current_loop = asyncio.get_event_loop()

        # Check if client exists and is in the same event loop
        if (
            self._client is not None
            and self._client_event_loop is not None
            and (
                self._client_event_loop is not current_loop
                or self._client_event_loop.is_closed()
            )
        ):
            # If event loop has changed or closed, recreate the client
            # Close old client context if it exists
            # Try to close the aiohttp session even if the event loop is closed
            if self._client_context is not None:
                if not self._client_event_loop.is_closed():
                    try:
                        # Only try to close if we're still in the same event loop
                        old_loop = self._client_event_loop
                        if old_loop is current_loop:
                            await self._client_context.__aexit__(None, None, None)
                        else:
                            # Different loop - try to close aiohttp session directly
                            await self._close_aiohttp_session_directly()
                    except Exception as e:
                        logger.warning(
                            f"Error closing old client context: {e}", exc_info=True
                        )
                        # Try to close aiohttp session directly as fallback
                        import contextlib

                        with contextlib.suppress(Exception):
                            await self._close_aiohttp_session_directly()
            elif self._client_context is not None:
                # Loop is closed, can't await __aexit__
                # Try to close aiohttp session directly
                import contextlib

                with contextlib.suppress(Exception):
                    await self._close_aiohttp_session_directly()  # Best effort cleanup

                # Reset client state AFTER attempting to close
                old_client = self._client
                self._client = None
                self._client_context = None
                self._client_event_loop = None

                # If we still have the old client and couldn't close via context,
                # try to close the aiohttp session directly in the new event loop
                if old_client is not None and not current_loop.is_closed():
                    import contextlib

                    with contextlib.suppress(Exception):
                        await self._close_aiohttp_session_from_client(
                            old_client, current_loop
                        )

        if self._client is None:
            async with self._client_lock:
                # Double-check pattern to avoid race conditions
                if self._client is None:
                    session = await self._get_session()
                    # Create client resource - aioboto3 manages connection pooling
                    # We keep the client alive for the lifetime of the DynamoDB instance
                    self._client_context = session.client(
                        "dynamodb", **self._dynamodb_kwargs
                    )
                    try:
                        self._client = await self._client_context.__aenter__()
                        # Store the event loop this client was created in
                        self._client_event_loop = current_loop
                    except Exception as e:
                        logger.error(
                            f"Error during client initialization: {type(e).__name__}: {e}",
                            exc_info=True,
                        )
                        raise
        return self._client

    def _get_indexed_field_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Extract a value from nested JSON data using dot notation.

        Args:
            data: JSON data dictionary
            field_path: Field path using dot notation (e.g., "context.user_id")

        Returns:
            Field value or None if not found
        """
        keys = field_path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current

    def _extract_indexed_fields(
        self, data: Dict[str, Any], collection: str
    ) -> Dict[str, Any]:
        """Extract indexed field values from JSON data and prepare them as top-level attributes.

        Args:
            data: JSON data dictionary
            collection: Collection name

        Returns:
            Dictionary of top-level attributes to add to DynamoDB item
            Format: {"idx_context_user_id": {"S": "value"}, ...}
        """
        indexed_attrs: Dict[str, Any] = {}

        # Get indexed fields for this collection
        if collection not in self._indexed_fields:
            return indexed_attrs

        for field_path, _index_info in self._indexed_fields[collection].items():
            # Extract value from nested JSON
            value = self._get_indexed_field_value(data, field_path)

            if value is not None:
                # Convert field path to attribute name: "context.user_id" -> "idx_context_user_id"
                attr_name = f"idx_{field_path.replace('.', '_')}"

                # Convert value to DynamoDB format
                if isinstance(value, str):
                    indexed_attrs[attr_name] = {"S": value}
                elif isinstance(value, (int, float)):
                    indexed_attrs[attr_name] = {"N": str(value)}
                elif isinstance(value, bool):
                    indexed_attrs[attr_name] = {"BOOL": value}
                elif isinstance(value, (list, dict)):
                    # Complex types stored as JSON string
                    indexed_attrs[attr_name] = {"S": json.dumps(value, default=str)}
                else:
                    # Fallback to string
                    indexed_attrs[attr_name] = {"S": str(value)}

        return indexed_attrs

    async def _discover_existing_indexes(
        self, client: Any, table_name: str, collection: str
    ) -> None:
        """Discover existing GSIs on a table and populate the index registry.

        Args:
            client: DynamoDB client
            table_name: Table name
            collection: Collection name
        """
        try:
            response = await client.describe_table(TableName=table_name)
            gsis = response["Table"].get("GlobalSecondaryIndexes", [])

            if collection not in self._indexed_fields:
                self._indexed_fields[collection] = {}
            if collection not in self._gsi_names:
                self._gsi_names[collection] = set()

            for gsi in gsis:
                gsi_name = gsi["IndexName"]
                self._gsi_names[collection].add(gsi_name)

                # Try to infer field path from GSI name and key schema
                # GSI names like "gsi_idx_context_user_id" -> "context.user_id"
                key_schema = gsi.get("KeySchema", [])
                if key_schema:
                    # Get the partition key attribute name
                    partition_key_attr = key_schema[0]["AttributeName"]
                    # Convert back to field path: "idx_context_user_id" -> "context.user_id"
                    if partition_key_attr.startswith("idx_"):
                        field_path = partition_key_attr[4:].replace("_", ".")
                        if field_path not in self._indexed_fields[collection]:
                            self._indexed_fields[collection][field_path] = {
                                "gsi_name": gsi_name,
                                "unique": False,  # Can't determine from GSI
                                "direction": 1,
                                "attr_name": partition_key_attr,
                            }

        except ClientError:
            # If we can't discover indexes, that's okay - they'll be created when needed
            pass

    async def _ensure_table_exists(self, collection: str) -> str:
        """Ensure DynamoDB table exists for a collection.

        Args:
            collection: Collection name

        Returns:
            Full table name
        """
        # Use collection name as part of table name to avoid conflicts
        full_table_name = f"{self.table_name}_{collection}"

        # Early return if table already verified (cached)
        if full_table_name in self._tables_created:
            return full_table_name

        # Use persistent client
        client = await self._get_client()

        # Check if table exists
        try:
            await client.describe_table(TableName=full_table_name)
            # Discover existing GSIs
            await self._discover_existing_indexes(client, full_table_name, collection)
            # Cache table existence
            self._tables_created[full_table_name] = True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                # Table doesn't exist, create it
                try:
                    await client.create_table(
                        TableName=full_table_name,
                        KeySchema=[
                            {"AttributeName": "collection", "KeyType": "HASH"},
                            {"AttributeName": "id", "KeyType": "RANGE"},
                        ],
                        AttributeDefinitions=[
                            {
                                "AttributeName": "collection",
                                "AttributeType": "S",
                            },
                            {"AttributeName": "id", "AttributeType": "S"},
                        ],
                        BillingMode="PAY_PER_REQUEST",
                    )
                    # Wait for table to be created
                    waiter = client.get_waiter("table_exists")
                    await waiter.wait(TableName=full_table_name)
                    # Cache table creation
                    self._tables_created[full_table_name] = True
                except ClientError as create_error:
                    if (
                        create_error.response["Error"]["Code"]
                        != "ResourceInUseException"
                    ):
                        raise DatabaseError(
                            f"Failed to create DynamoDB table: {create_error}"
                        ) from create_error
            else:
                raise DatabaseError(f"DynamoDB error: {e}") from e

        return full_table_name

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Args:
            collection: Collection name
            data: Record data

        Returns:
            Saved record with any database-generated fields
        """
        # Ensure record has an ID
        if "id" not in data:
            import uuid

            data["id"] = str(uuid.uuid4())

        table_name = await self._ensure_table_exists(collection)

        # Prepare item for DynamoDB
        item = {
            "collection": {"S": collection},
            "id": {"S": data["id"]},
            "data": {
                "S": json.dumps(data, default=str)
            },  # Serialize data as JSON string
        }

        # Extract indexed fields and add as top-level attributes for GSI support
        indexed_attrs = self._extract_indexed_fields(data, collection)
        item.update(indexed_attrs)

        try:
            client = await self._get_client()
            # Add timeout to prevent hanging
            try:
                await asyncio.wait_for(
                    client.put_item(TableName=table_name, Item=item),
                    timeout=30.0,  # 30 second timeout
                )
            except asyncio.TimeoutError:
                raise DatabaseError(
                    f"DynamoDB save operation timed out for table: {table_name}"
                )
            return data
        except ClientError as e:
            raise DatabaseError(f"DynamoDB save error: {e}") from e

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data or None if not found
        """
        table_name = await self._ensure_table_exists(collection)

        try:
            client = await self._get_client()
            response = await client.get_item(
                TableName=table_name,
                Key={"collection": {"S": collection}, "id": {"S": id}},
            )
            if "Item" not in response:
                return None

            # Deserialize data from JSON string
            item = response["Item"]
            data = json.loads(item["data"]["S"])
            return data
        except ClientError as e:
            raise DatabaseError(f"DynamoDB get error: {e}") from e

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID.

        Args:
            collection: Collection name
            id: Record ID
        """
        table_name = await self._ensure_table_exists(collection)

        try:
            client = await self._get_client()
            await client.delete_item(
                TableName=table_name,
                Key={"collection": {"S": collection}, "id": {"S": id}},
            )
        except ClientError as e:
            raise DatabaseError(f"DynamoDB delete error: {e}") from e

    async def batch_get(self, collection: str, ids: List[str]) -> List[Dict[str, Any]]:
        """Retrieve multiple records by IDs using batch_get_item.

        This method efficiently retrieves multiple records in batches, handling
        DynamoDB's 100-item limit automatically. Batches are processed in parallel
        for better performance.

        Args:
            collection: Collection name
            ids: List of record IDs to retrieve

        Returns:
            List of retrieved records (may be fewer than requested if some don't exist)
        """
        if not ids:
            return []

        table_name = await self._ensure_table_exists(collection)
        client = await self._get_client()

        # DynamoDB batch_get_item has a limit of 100 items per request
        # Use 100 for maximum efficiency (was 25, which was too conservative)
        batch_size = 100

        # Split into batches
        batches = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]

        async def process_batch(batch_ids: List[str]) -> List[Dict[str, Any]]:
            """Process a single batch of IDs."""
            batch_results: List[Dict[str, Any]] = []

            # Prepare request items for this batch
            request_items = {
                table_name: {
                    "Keys": [
                        {"collection": {"S": collection}, "id": {"S": id}}
                        for id in batch_ids
                    ]
                }
            }

            try:
                # Execute batch get
                response = await client.batch_get_item(RequestItems=request_items)

                # Process responses
                items = response.get("Responses", {}).get(table_name, [])
                for item in items:
                    # Deserialize data from JSON string
                    data = json.loads(item["data"]["S"])
                    batch_results.append(data)

                # Handle unprocessed keys (should be rare with proper retry config)
                unprocessed = response.get("UnprocessedKeys", {})
                if unprocessed:
                    logger.debug(
                        f"Unprocessed keys in batch_get for collection '{collection}': {len(unprocessed.get(table_name, {}).get('Keys', []))}"
                    )
                    # Retry unprocessed keys once
                    retry_items = {table_name: unprocessed[table_name]}
                    retry_response = await client.batch_get_item(
                        RequestItems=retry_items
                    )
                    retry_items_list = retry_response.get("Responses", {}).get(
                        table_name, []
                    )
                    for item in retry_items_list:
                        data = json.loads(item["data"]["S"])
                        batch_results.append(data)

            except ClientError as e:
                raise DatabaseError(f"DynamoDB batch_get error: {e}") from e

            return batch_results

        # Process all batches in parallel for better performance
        if len(batches) > 1:
            batch_results = await asyncio.gather(
                *[process_batch(batch) for batch in batches]
            )
            # Flatten results
            results = [item for batch_result in batch_results for item in batch_result]
        else:
            # Single batch, no need for parallelization
            results = await process_batch(batches[0] if batches else [])

        return results

    async def batch_write(self, collection: str, items: List[Dict[str, Any]]) -> None:
        """Write multiple records using batch_write_item.

        This method efficiently writes multiple records in batches, handling
        DynamoDB's 25-item limit and unprocessed items automatically.
        Batches are processed in parallel for better performance.

        Args:
            collection: Collection name
            items: List of record dictionaries to write

        Raises:
            DatabaseError: If batch write fails after retries
        """
        if not items:
            return

        table_name = await self._ensure_table_exists(collection)
        client = await self._get_client()

        # Ensure all items have IDs
        import uuid

        for item in items:
            if "id" not in item:
                item["id"] = str(uuid.uuid4())

        # DynamoDB batch_write_item has a limit of 25 items per request
        batch_size = 25

        # Split into batches
        batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

        async def process_batch(batch_items: List[Dict[str, Any]]) -> None:
            """Process a single batch of items."""
            # Prepare write requests for this batch
            write_requests = []
            for item_data in batch_items:
                # Prepare item for DynamoDB
                dynamodb_item = {
                    "collection": {"S": collection},
                    "id": {"S": item_data["id"]},
                    "data": {
                        "S": json.dumps(item_data, default=str)
                    },  # Serialize data as JSON string
                }

                # Extract indexed fields and add as top-level attributes for GSI support
                indexed_attrs = self._extract_indexed_fields(item_data, collection)
                dynamodb_item.update(indexed_attrs)

                write_requests.append({"PutRequest": {"Item": dynamodb_item}})

            request_items = {table_name: write_requests}

            try:
                # Execute batch write
                response = await client.batch_write_item(RequestItems=request_items)

                # Handle unprocessed items with retry logic
                unprocessed = response.get("UnprocessedItems", {})
                max_retries = 3
                retry_count = 0

                while unprocessed and retry_count < max_retries:
                    retry_count += 1
                    logger.debug(
                        f"Retrying {len(unprocessed.get(table_name, []))} unprocessed items (attempt {retry_count}/{max_retries})"
                    )

                    # Wait before retry (exponential backoff)
                    await asyncio.sleep(0.1 * (2 ** (retry_count - 1)))

                    retry_response = await client.batch_write_item(
                        RequestItems=unprocessed
                    )
                    unprocessed = retry_response.get("UnprocessedItems", {})

                if unprocessed:
                    # Log warning but don't fail - some items may be throttled
                    logger.warning(
                        f"Some items remain unprocessed after {max_retries} retries for collection '{collection}': {len(unprocessed.get(table_name, []))}"
                    )

            except ClientError as e:
                raise DatabaseError(f"DynamoDB batch_write error: {e}") from e

        # Process all batches in parallel for better performance
        if len(batches) > 1:
            await asyncio.gather(*[process_batch(batch) for batch in batches])
        else:
            # Single batch, no need for parallelization
            await process_batch(batches[0] if batches else [])

    def _find_matching_gsi(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find a GSI that matches the query.

        Args:
            collection: Collection name
            query: Query parameters

        Returns:
            Dictionary with GSI info if match found, None otherwise
            Format: {"gsi_name": str, "field_path": str, "value": Any, "attr_name": str}
        """
        if collection not in self._indexed_fields:
            return None

        # Check for single-field index match (simple equality query)
        for field_path, index_info in self._indexed_fields[collection].items():
            if field_path in query:
                # Simple equality match
                value = query[field_path]
                # Skip complex queries (operators, etc.)
                if isinstance(value, dict):
                    continue
                return {
                    "gsi_name": index_info["gsi_name"],
                    "field_path": field_path,
                    "value": value,
                    "attr_name": index_info["attr_name"],
                }

        # Check for compound index match
        # For compound indexes, we'd need to match multiple fields
        # This is more complex and would require checking all fields in the index
        # For now, prioritize single-field indexes

        return None

    def _build_filter_expression(
        self, query: Dict[str, Any], collection: str
    ) -> tuple[Optional[str], Dict[str, str], Dict[str, Any]]:
        """Build DynamoDB FilterExpression from query for simple equality filters.

        This is a limited implementation that only handles simple equality filters
        on indexed fields. Complex queries still require client-side filtering.

        Args:
            query: Query parameters
            collection: Collection name

        Returns:
            Tuple of (FilterExpression, ExpressionAttributeNames, ExpressionAttributeValues)
            Returns (None, {}, {}) if query is too complex for FilterExpression
        """
        if not query or query.get("$or") or query.get("$and"):
            return None, {}, {}

        # Only handle simple equality filters on indexed fields
        filter_parts = []
        attr_names: Dict[str, str] = {}
        attr_values: Dict[str, Any] = {}
        attr_counter = 0

        for field_path, value in query.items():
            # Skip complex operators
            if isinstance(value, dict):
                continue

            # Check if this field is indexed
            if (
                collection in self._indexed_fields
                and field_path in self._indexed_fields[collection]
            ):
                index_info = self._indexed_fields[collection][field_path]
                attr_name = index_info["attr_name"]

                # Add to attribute names
                attr_name_placeholder = f"#attr{attr_counter}"
                attr_names[attr_name_placeholder] = attr_name

                # Convert value to DynamoDB format
                if isinstance(value, str):
                    value_attr = {"S": value}
                elif isinstance(value, (int, float)):
                    value_attr = {"N": str(value)}
                elif isinstance(value, bool):
                    value_attr = {"BOOL": value}  # type: ignore[dict-item]
                else:
                    value_attr = {"S": str(value)}

                # Add to attribute values
                value_placeholder = f":val{attr_counter}"
                attr_values[value_placeholder] = value_attr

                # Add filter condition
                filter_parts.append(f"{attr_name_placeholder} = {value_placeholder}")
                attr_counter += 1

        if not filter_parts:
            return None, {}, {}

        filter_expression = " AND ".join(filter_parts)
        return filter_expression, attr_names, attr_values

    async def find(
        self, collection: str, query: Dict[str, Any], limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Optimizes queries by using Global Secondary Indexes (GSI) when available.
        Falls back to table scan for complex queries or when no index matches.
        Uses FilterExpression where possible to push filtering to DynamoDB.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)
            limit: Optional maximum number of results to return

        Returns:
            List of matching records

        Note:
            - Uses GSI query() for simple equality queries on indexed fields
            - Uses FilterExpression to push simple filters to DynamoDB
            - Falls back to scan() for complex queries or unindexed fields
            - All queries are transparent - same API, better performance
        """
        table_name = await self._ensure_table_exists(collection)

        try:
            client = await self._get_client()
            # Try to use GSI if query matches an indexed field
            gsi_match = self._find_matching_gsi(collection, query)

            if gsi_match and not query.get("$or") and not query.get("$and"):
                # Use GSI query for simple equality queries
                try:
                    # Convert value to DynamoDB format
                    attr_name = gsi_match["attr_name"]
                    value = gsi_match["value"]

                    value_attr: Dict[str, Any]
                    if isinstance(value, str):
                        value_attr = {"S": value}
                    elif isinstance(value, (int, float)):
                        value_attr = {"N": str(value)}
                    elif isinstance(value, bool):
                        value_attr = {"BOOL": value}  # type: ignore[dict-item]
                    else:
                        value_attr = {"S": str(value)}

                    # Build FilterExpression for additional filters
                    remaining_query = {
                        k: v for k, v in query.items() if k != gsi_match["field_path"]
                    }
                    filter_expr, filter_attr_names, filter_attr_values = (
                        self._build_filter_expression(remaining_query, collection)
                    )

                    # Combine attribute names and values
                    expr_attr_names = {"#key": attr_name}
                    expr_attr_values = {":val": value_attr}
                    if filter_expr:
                        expr_attr_names.update(filter_attr_names)
                        expr_attr_values.update(filter_attr_values)

                    # Query using GSI with optional FilterExpression
                    query_params: Dict[str, Any] = {
                        "TableName": table_name,
                        "IndexName": gsi_match["gsi_name"],
                        "KeyConditionExpression": "#key = :val",
                        "ExpressionAttributeNames": expr_attr_names,
                        "ExpressionAttributeValues": expr_attr_values,
                    }
                    if limit:
                        query_params["Limit"] = limit
                    if filter_expr:
                        query_params["FilterExpression"] = filter_expr

                    response = await client.query(**query_params)

                    results = []
                    for item in response.get("Items", []):
                        # Deserialize data from JSON string
                        data = json.loads(item["data"]["S"])
                        # Only apply client-side filtering if FilterExpression wasn't used
                        if (
                            not filter_expr
                            and remaining_query
                            and not QueryEngine.match(data, remaining_query)
                        ):
                            continue
                        results.append(data)
                        if limit and len(results) >= limit:
                            break

                    # Handle pagination (only if limit not reached)
                    while "LastEvaluatedKey" in response and (
                        not limit or len(results) < limit
                    ):
                        query_params["ExclusiveStartKey"] = response["LastEvaluatedKey"]
                        if limit:
                            query_params["Limit"] = limit - len(results)
                        response = await client.query(**query_params)

                        for item in response.get("Items", []):
                            data = json.loads(item["data"]["S"])
                            if (
                                not filter_expr
                                and remaining_query
                                and not QueryEngine.match(data, remaining_query)
                            ):
                                continue
                            results.append(data)
                            if limit and len(results) >= limit:
                                break
                        if limit and len(results) >= limit:
                            break

                    logger.debug(
                        f"Used GSI '{gsi_match['gsi_name']}' for query on '{gsi_match['field_path']}'"
                    )
                    return results[:limit] if limit else results

                except ClientError as e:
                    # If GSI query fails, fall back to scan
                    logger.warning(
                        f"GSI query failed, falling back to scan: {e}",
                        exc_info=True,
                    )

            # Fall back to scan for complex queries or when no index matches
            # Build FilterExpression for simple equality filters
            filter_expr, filter_attr_names, filter_attr_values = (
                self._build_filter_expression(query, collection)
            )

            # Always include collection filter
            scan_attr_names = {"#coll": "collection"}
            scan_attr_values = {":collection_val": {"S": collection}}

            # Combine with query filters if available
            if filter_expr:
                scan_attr_names.update(filter_attr_names)
                scan_attr_values.update(filter_attr_values)
                # Combine collection filter with query filters
                combined_filter = f"#coll = :collection_val AND {filter_expr}"
            else:
                combined_filter = "#coll = :collection_val"

            scan_params: Dict[str, Any] = {
                "TableName": table_name,
                "FilterExpression": combined_filter,
                "ExpressionAttributeNames": scan_attr_names,
                "ExpressionAttributeValues": scan_attr_values,
            }
            if limit:
                scan_params["Limit"] = limit

            response = await client.scan(**scan_params)

            results = []
            for item in response.get("Items", []):
                # Deserialize data from JSON string
                data = json.loads(item["data"]["S"])

                # Only apply client-side filtering if FilterExpression wasn't used or query is complex
                if not filter_expr and query and not QueryEngine.match(data, query):
                    continue
                results.append(data)
                if limit and len(results) >= limit:
                    break

            # Handle pagination (only if limit not reached)
            while "LastEvaluatedKey" in response and (
                not limit or len(results) < limit
            ):
                scan_params["ExclusiveStartKey"] = response["LastEvaluatedKey"]
                if limit:
                    scan_params["Limit"] = limit - len(results)
                response = await client.scan(**scan_params)

                for item in response.get("Items", []):
                    data = json.loads(item["data"]["S"])
                    if not filter_expr and query and not QueryEngine.match(data, query):
                        continue
                    results.append(data)
                    if limit and len(results) >= limit:
                        break
                if limit and len(results) >= limit:
                    break

            return results[:limit] if limit else results
        except ClientError as e:
            raise DatabaseError(f"DynamoDB find error: {e}") from e

    async def _wait_for_index_active(
        self, client: Any, table_name: str, index_name: str, max_wait: int = 300
    ) -> None:
        """Wait for a GSI to become active.

        Args:
            client: DynamoDB client
            table_name: Table name
            index_name: GSI name
            max_wait: Maximum wait time in seconds (default: 5 minutes)

        Raises:
            DatabaseError: If index doesn't become active within max_wait time
        """
        import asyncio
        import time

        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                response = await client.describe_table(TableName=table_name)
                table = response["Table"]

                # Find the GSI
                for gsi in table.get("GlobalSecondaryIndexes", []):
                    if gsi["IndexName"] == index_name:
                        status = gsi["IndexStatus"]
                        if status == "ACTIVE":
                            logger.debug(f"GSI '{index_name}' is now active")
                            return
                        elif status == "CREATING":
                            logger.debug(
                                f"GSI '{index_name}' is still creating, waiting..."
                            )
                            await asyncio.sleep(2)
                            break
                        else:
                            raise DatabaseError(
                                f"GSI '{index_name}' is in unexpected state: {status}"
                            )
                else:
                    # GSI not found in table description
                    raise DatabaseError(f"GSI '{index_name}' not found in table")
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    raise DatabaseError(f"Table '{table_name}' not found") from e
                raise DatabaseError(f"Error checking GSI status: {e}") from e

        raise DatabaseError(
            f"GSI '{index_name}' did not become active within {max_wait} seconds"
        )

    async def _update_table_with_gsi(
        self,
        client: Any,
        table_name: str,
        gsi_name: str,
        attribute_definitions: List[Dict[str, str]],
        key_schema: List[Dict[str, str]],
        unique: bool = False,
        wait_for_active: bool = True,
    ) -> None:
        """Update DynamoDB table to add a Global Secondary Index.

        Args:
            client: DynamoDB client
            table_name: Table name
            gsi_name: GSI name
            attribute_definitions: List of attribute definitions needed for the GSI
            key_schema: Key schema for the GSI
            unique: Whether the index should be unique (handled at application level)
            wait_for_active: Whether to wait for the index to become active (default: True)

        Raises:
            DatabaseError: If table update fails
        """
        try:
            # First, check if GSI already exists and get existing attribute definitions
            try:
                response = await client.describe_table(TableName=table_name)
                table = response["Table"]
                existing_gsi_names = {
                    gsi["IndexName"] for gsi in table.get("GlobalSecondaryIndexes", [])
                }
                if gsi_name in existing_gsi_names:
                    logger.debug(
                        f"GSI '{gsi_name}' already exists on table '{table_name}'"
                    )
                    return

                # Get existing attribute definitions
                existing_attrs = {
                    attr["AttributeName"]: attr["AttributeType"]
                    for attr in table.get("AttributeDefinitions", [])
                }

                # Only add new attribute definitions
                new_attr_defs = [
                    attr
                    for attr in attribute_definitions
                    if attr["AttributeName"] not in existing_attrs
                ]

            except ClientError as e:
                if e.response["Error"]["Code"] != "ResourceNotFoundException":
                    raise
                new_attr_defs = attribute_definitions

            # Update table to add GSI
            update_params: Dict[str, Any] = {
                "TableName": table_name,
                "GlobalSecondaryIndexUpdates": [
                    {
                        "Create": {
                            "IndexName": gsi_name,
                            "KeySchema": key_schema,
                            "Projection": {"ProjectionType": "ALL"},
                        }
                    }
                ],
            }

            # Only add AttributeDefinitions if we have new ones
            if new_attr_defs:
                update_params["AttributeDefinitions"] = new_attr_defs

            await client.update_table(**update_params)
            logger.info(f"Started creating GSI '{gsi_name}' on table '{table_name}'")

            # Wait for index to become active if requested
            if wait_for_active:
                await self._wait_for_index_active(client, table_name, gsi_name)
                logger.info(
                    f"GSI '{gsi_name}' created successfully on table '{table_name}'"
                )
            else:
                logger.info(
                    f"GSI '{gsi_name}' creation initiated on table '{table_name}' "
                    f"(not waiting for activation - index will be available when active)"
                )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceInUseException":
                # Table is already being updated, wait and retry
                logger.warning(
                    f"Table '{table_name}' is being updated, waiting for completion..."
                )
                await asyncio.sleep(5)
                # Retry once
                try:
                    await client.update_table(**update_params)
                    if wait_for_active:
                        await self._wait_for_index_active(client, table_name, gsi_name)
                except ClientError as retry_error:
                    raise DatabaseError(
                        f"Failed to create GSI '{gsi_name}' after retry: {retry_error}"
                    ) from retry_error
            else:
                raise DatabaseError(f"Failed to create GSI '{gsi_name}': {e}") from e

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        wait_for_active: Optional[bool] = None,
        **kwargs: Any,
    ) -> None:
        """Create an index on the specified field(s) using DynamoDB Global Secondary Indexes.

        This implementation transparently:
        1. Extracts indexed fields from JSON data and stores them as top-level attributes
        2. Creates GSIs on those top-level attributes
        3. Optimizes queries to use GSIs when available

        Args:
            collection: Collection name
            field_or_fields: Single field name (str) or list of (field_name, direction) tuples
            unique: Whether the index should enforce uniqueness (handled at application level)
            wait_for_active: Whether to wait for index activation. If None, uses environment
                            variable JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX (default: False).
                            Set to True to wait for activation (may take several minutes per index).
            **kwargs: Additional options (e.g., "name" for compound indexes)

        Raises:
            DatabaseError: If index creation fails
        """
        # Determine whether to wait based on parameter or environment variable
        # Default is False to allow immediate graph usage (indexes created asynchronously)
        if wait_for_active is None:
            wait_for_active = (
                os.getenv("JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX", "false").lower()
                == "true"
            )
        table_name = await self._ensure_table_exists(collection)

        # Initialize collections in registry if needed
        if collection not in self._indexed_fields:
            self._indexed_fields[collection] = {}
        if collection not in self._gsi_names:
            self._gsi_names[collection] = set()

        try:
            client = await self._get_client()
            if isinstance(field_or_fields, str):
                # Single-field index
                field_path = field_or_fields
                attr_name = f"idx_{field_path.replace('.', '_')}"
                gsi_name = kwargs.get("name") or f"gsi_{attr_name}"

                # Check if already indexed
                if field_path in self._indexed_fields[collection]:
                    logger.debug(
                        f"Field '{field_path}' already indexed on collection '{collection}'"
                    )
                    return

                # Determine attribute type (default to String)
                # For now, assume all indexed fields are strings
                # Could be enhanced to detect type from sample data
                attribute_type = "S"

                # Create GSI with partition key on indexed field, sort key on id
                key_schema = [
                    {"AttributeName": attr_name, "KeyType": "HASH"},
                    {"AttributeName": "id", "KeyType": "RANGE"},
                ]

                # Attribute definitions needed for the GSI
                attribute_definitions = [
                    {"AttributeName": attr_name, "AttributeType": attribute_type},
                    {"AttributeName": "id", "AttributeType": "S"},
                ]

                await self._update_table_with_gsi(
                    client,
                    table_name,
                    gsi_name,
                    attribute_definitions,
                    key_schema,
                    unique,
                    wait_for_active,
                )

                # Track the index
                self._indexed_fields[collection][field_path] = {
                    "gsi_name": gsi_name,
                    "unique": unique,
                    "direction": 1,
                    "attr_name": attr_name,
                }
                self._gsi_names[collection].add(gsi_name)

                logger.info(
                    f"Created single-field index '{gsi_name}' on '{field_path}' "
                    f"for collection '{collection}'"
                )

            else:
                # Compound index
                fields = field_or_fields
                gsi_name = (
                    kwargs.get("name")
                    or f"gsi_{collection}_{'_'.join(f[0].replace('.', '_') for f in fields)}"
                )

                # Check if already indexed
                if gsi_name in self._gsi_names[collection]:
                    logger.debug(
                        f"Compound index '{gsi_name}' already exists on collection '{collection}'"
                    )
                    return

                # Build key schema and attribute definitions
                key_schema = []
                attribute_definitions = []
                field_paths = []

                for i, (field_path, _direction) in enumerate(fields):
                    attr_name = f"idx_{field_path.replace('.', '_')}"
                    field_paths.append(field_path)

                    if i == 0:
                        # First field is partition key
                        key_schema.append(
                            {"AttributeName": attr_name, "KeyType": "HASH"}
                        )
                    elif i == 1:
                        # Second field is sort key
                        key_schema.append(
                            {"AttributeName": attr_name, "KeyType": "RANGE"}
                        )
                    # Additional fields beyond 2 are not supported in DynamoDB GSI

                    attribute_definitions.append(
                        {"AttributeName": attr_name, "AttributeType": "S"}
                    )

                # Create GSI
                await self._update_table_with_gsi(
                    client,
                    table_name,
                    gsi_name,
                    attribute_definitions,
                    key_schema,
                    unique,
                    wait_for_active,
                )

                # Track the compound index
                for field_path in field_paths:
                    if field_path not in self._indexed_fields[collection]:
                        self._indexed_fields[collection][field_path] = {
                            "gsi_name": gsi_name,
                            "unique": unique,
                            "direction": 1,
                            "attr_name": f"idx_{field_path.replace('.', '_')}",
                        }
                self._gsi_names[collection].add(gsi_name)

                logger.info(
                    f"Created compound index '{gsi_name}' on fields {field_paths} "
                    f"for collection '{collection}'"
                )

        except ClientError as e:
            raise DatabaseError(f"DynamoDB index creation error: {e}") from e

    async def close(self) -> None:
        """Close the database connection."""
        # Close persistent client if it exists
        if self._client_context is not None:
            try:
                # Try to get current event loop
                try:
                    current_loop = asyncio.get_event_loop()
                except RuntimeError:
                    current_loop = None

                # Only try to close if we're in an active event loop
                if current_loop and not current_loop.is_closed():
                    # If the client was created in a different closed loop, we can't properly close it
                    if (
                        self._client_event_loop is not None
                        and self._client_event_loop is not current_loop
                        and self._client_event_loop.is_closed()
                    ):
                        # Try to close aiohttp session directly
                        import contextlib

                        with contextlib.suppress(Exception):
                            await self._close_aiohttp_session_directly()  # Best effort cleanup
                    else:
                        # Properly close the context manager with timeout
                        try:
                            await asyncio.wait_for(
                                self._client_context.__aexit__(None, None, None),
                                timeout=1.0,
                            )
                        except asyncio.TimeoutError:
                            # Timeout - try to close aiohttp session directly
                            logger.debug(
                                "Context manager close timed out, closing aiohttp session directly"
                            )
                            import contextlib

                            with contextlib.suppress(Exception):
                                await self._close_aiohttp_session_directly()
                else:
                    # No active loop, try to close aiohttp session directly
                    import contextlib

                    with contextlib.suppress(Exception):
                        await self._close_aiohttp_session_directly()  # Best effort cleanup
            except Exception as e:
                logger.warning(f"Error closing DynamoDB client: {e}", exc_info=True)
            finally:
                self._client = None
                self._client_context = None
                self._client_event_loop = None

        # Clear table cache and index registry
        self._tables_created.clear()
        self._indexed_fields.clear()
        self._gsi_names.clear()
        self._session = None
