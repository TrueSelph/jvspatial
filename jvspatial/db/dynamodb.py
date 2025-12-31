"""DynamoDB database implementation for AWS Lambda serverless deployments."""

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    import aioboto3
    from botocore.exceptions import ClientError

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False
    aioboto3 = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment, misc]

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
                "aioboto3 is required for DynamoDB support. Install it with: pip install aioboto3"
            )

        self.table_name = table_name
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

        # DynamoDB session will be created on first use
        self._session: Optional[Any] = None
        self._tables_created: Dict[str, bool] = {}  # Track which tables we've created
        # Track indexed fields per collection: {collection: {field_path: {"gsi_name": str, "unique": bool, "direction": int}}}
        self._indexed_fields: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Track GSI names per collection to avoid duplicate creation
        self._gsi_names: Dict[str, Set[str]] = {}

    async def _get_session(self) -> Any:
        """Get or create aioboto3 session.

        Returns:
            aioboto3 session
        """
        if self._session is None:
            self._session = aioboto3.Session()
        return self._session

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

        if full_table_name not in self._tables_created:
            session = await self._get_session()
            dynamodb_kwargs: Dict[str, Any] = {"region_name": self.region_name}
            if self.endpoint_url:
                dynamodb_kwargs["endpoint_url"] = self.endpoint_url
            if self.aws_access_key_id:
                dynamodb_kwargs["aws_access_key_id"] = self.aws_access_key_id
            if self.aws_secret_access_key:
                dynamodb_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

            async with session.client("dynamodb", **dynamodb_kwargs) as client:
                # Check if table exists
                try:
                    await client.describe_table(TableName=full_table_name)
                    # Discover existing GSIs
                    await self._discover_existing_indexes(
                        client, full_table_name, collection
                    )
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

            self._tables_created[full_table_name] = True

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
        session = await self._get_session()

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

        dynamodb_kwargs: Dict[str, Any] = {"region_name": self.region_name}
        if self.endpoint_url:
            dynamodb_kwargs["endpoint_url"] = self.endpoint_url
        if self.aws_access_key_id:
            dynamodb_kwargs["aws_access_key_id"] = self.aws_access_key_id
        if self.aws_secret_access_key:
            dynamodb_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        try:
            async with session.client("dynamodb", **dynamodb_kwargs) as client:
                await client.put_item(TableName=table_name, Item=item)
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
        session = await self._get_session()

        dynamodb_kwargs: Dict[str, Any] = {"region_name": self.region_name}
        if self.endpoint_url:
            dynamodb_kwargs["endpoint_url"] = self.endpoint_url
        if self.aws_access_key_id:
            dynamodb_kwargs["aws_access_key_id"] = self.aws_access_key_id
        if self.aws_secret_access_key:
            dynamodb_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        try:
            async with session.client("dynamodb", **dynamodb_kwargs) as client:
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
        session = await self._get_session()

        dynamodb_kwargs: Dict[str, Any] = {"region_name": self.region_name}
        if self.endpoint_url:
            dynamodb_kwargs["endpoint_url"] = self.endpoint_url
        if self.aws_access_key_id:
            dynamodb_kwargs["aws_access_key_id"] = self.aws_access_key_id
        if self.aws_secret_access_key:
            dynamodb_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        try:
            async with session.client("dynamodb", **dynamodb_kwargs) as client:
                await client.delete_item(
                    TableName=table_name,
                    Key={"collection": {"S": collection}, "id": {"S": id}},
                )
        except ClientError as e:
            raise DatabaseError(f"DynamoDB delete error: {e}") from e

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

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Optimizes queries by using Global Secondary Indexes (GSI) when available.
        Falls back to table scan for complex queries or when no index matches.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

        Returns:
            List of matching records

        Note:
            - Uses GSI query() for simple equality queries on indexed fields
            - Falls back to scan() for complex queries or unindexed fields
            - All queries are transparent - same API, better performance
        """
        table_name = await self._ensure_table_exists(collection)
        session = await self._get_session()

        dynamodb_kwargs: Dict[str, Any] = {"region_name": self.region_name}
        if self.endpoint_url:
            dynamodb_kwargs["endpoint_url"] = self.endpoint_url
        if self.aws_access_key_id:
            dynamodb_kwargs["aws_access_key_id"] = self.aws_access_key_id
        if self.aws_secret_access_key:
            dynamodb_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        try:
            async with session.client("dynamodb", **dynamodb_kwargs) as client:
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

                        # Query using GSI
                        # Use expression attribute names to handle special characters
                        attr_name_placeholder = f"#{attr_name.replace('_', '')}"
                        response = await client.query(
                            TableName=table_name,
                            IndexName=gsi_match["gsi_name"],
                            KeyConditionExpression=f"{attr_name_placeholder} = :val",
                            ExpressionAttributeNames={attr_name_placeholder: attr_name},
                            ExpressionAttributeValues={":val": value_attr},
                        )

                        results = []
                        for item in response.get("Items", []):
                            # Deserialize data from JSON string
                            data = json.loads(item["data"]["S"])
                            # Apply additional query filters if any
                            remaining_query = {
                                k: v
                                for k, v in query.items()
                                if k != gsi_match["field_path"]
                            }
                            if not remaining_query or QueryEngine.match(
                                data, remaining_query
                            ):
                                results.append(data)

                        # Handle pagination
                        while "LastEvaluatedKey" in response:
                            response = await client.query(
                                TableName=table_name,
                                IndexName=gsi_match["gsi_name"],
                                KeyConditionExpression=f"{attr_name_placeholder} = :val",
                                ExpressionAttributeNames={
                                    attr_name_placeholder: attr_name
                                },
                                ExpressionAttributeValues={":val": value_attr},
                                ExclusiveStartKey=response["LastEvaluatedKey"],
                            )

                            for item in response.get("Items", []):
                                data = json.loads(item["data"]["S"])
                                remaining_query = {
                                    k: v
                                    for k, v in query.items()
                                    if k != gsi_match["field_path"]
                                }
                                if not remaining_query or QueryEngine.match(
                                    data, remaining_query
                                ):
                                    results.append(data)

                        logger.debug(
                            f"Used GSI '{gsi_match['gsi_name']}' for query on '{gsi_match['field_path']}'"
                        )
                        return results

                    except ClientError as e:
                        # If GSI query fails, fall back to scan
                        logger.warning(
                            f"GSI query failed, falling back to scan: {e}",
                            exc_info=True,
                        )

                # Fall back to scan for complex queries or when no index matches
                response = await client.scan(
                    TableName=table_name,
                    FilterExpression="#coll = :collection_val",
                    ExpressionAttributeNames={"#coll": "collection"},
                    ExpressionAttributeValues={":collection_val": {"S": collection}},
                )

                results = []

                for item in response.get("Items", []):
                    # Deserialize data from JSON string
                    data = json.loads(item["data"]["S"])

                    # Use QueryEngine for proper operator support ($or, $and, etc.)
                    if not query or QueryEngine.match(data, query):
                        results.append(data)

                # Handle pagination if needed
                while "LastEvaluatedKey" in response:
                    response = await client.scan(
                        TableName=table_name,
                        FilterExpression="#coll = :collection_val",
                        ExpressionAttributeNames={"#coll": "collection"},
                        ExpressionAttributeValues={
                            ":collection_val": {"S": collection}
                        },
                        ExclusiveStartKey=response["LastEvaluatedKey"],
                    )

                    for item in response.get("Items", []):
                        data = json.loads(item["data"]["S"])
                        if not query:
                            results.append(data)
                        else:
                            if QueryEngine.match(data, query):
                                results.append(data)

                return results
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
    ) -> None:
        """Update DynamoDB table to add a Global Secondary Index.

        Args:
            client: DynamoDB client
            table_name: Table name
            gsi_name: GSI name
            attribute_definitions: List of attribute definitions needed for the GSI
            key_schema: Key schema for the GSI
            unique: Whether the index should be unique (handled at application level)

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

            # Wait for index to become active
            await self._wait_for_index_active(client, table_name, gsi_name)

            logger.info(
                f"GSI '{gsi_name}' created successfully on table '{table_name}'"
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceInUseException":
                # Table is already being updated, wait and retry
                logger.warning(
                    f"Table '{table_name}' is being updated, waiting for completion..."
                )
                import asyncio

                await asyncio.sleep(5)
                # Retry once
                try:
                    await client.update_table(**update_params)
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
            **kwargs: Additional options (e.g., "name" for compound indexes)

        Raises:
            DatabaseError: If index creation fails
        """
        table_name = await self._ensure_table_exists(collection)
        session = await self._get_session()

        # Initialize collections in registry if needed
        if collection not in self._indexed_fields:
            self._indexed_fields[collection] = {}
        if collection not in self._gsi_names:
            self._gsi_names[collection] = set()

        dynamodb_kwargs: Dict[str, Any] = {"region_name": self.region_name}
        if self.endpoint_url:
            dynamodb_kwargs["endpoint_url"] = self.endpoint_url
        if self.aws_access_key_id:
            dynamodb_kwargs["aws_access_key_id"] = self.aws_access_key_id
        if self.aws_secret_access_key:
            dynamodb_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        try:
            async with session.client("dynamodb", **dynamodb_kwargs) as client:
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
        # Clear table cache and index registry
        self._tables_created.clear()
        self._indexed_fields.clear()
        self._gsi_names.clear()
        self._session = None
