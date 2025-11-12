"""DynamoDB database implementation for AWS Lambda serverless deployments."""

import json
from typing import Any, Dict, List, Optional

try:
    import aioboto3
    from botocore.exceptions import ClientError

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False
    aioboto3 = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment, misc]

from jvspatial.db.database import Database
from jvspatial.exceptions import DatabaseError


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

    async def _get_session(self) -> Any:
        """Get or create aioboto3 session.

        Returns:
            aioboto3 session
        """
        if self._session is None:
            self._session = aioboto3.Session()
        return self._session

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

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

        Returns:
            List of matching records

        Note:
            DynamoDB querying is limited. This implementation:
            - Returns all records in the collection if query is empty
            - Performs client-side filtering for simple equality queries
            - For complex queries, consider using DynamoDB query/scan operations
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
                # Scan all items in the collection
                response = await client.scan(
                    TableName=table_name,
                    FilterExpression="collection = :collection",
                    ExpressionAttributeValues={":collection": {"S": collection}},
                )

                results = []
                for item in response.get("Items", []):
                    # Deserialize data from JSON string
                    data = json.loads(item["data"]["S"])

                    # Client-side filtering for simple queries
                    if not query:
                        results.append(data)
                    else:
                        # Simple equality matching
                        match = True
                        for key, value in query.items():
                            if data.get(key) != value:
                                match = False
                                break
                        if match:
                            results.append(data)

                # Handle pagination if needed
                while "LastEvaluatedKey" in response:
                    response = await client.scan(
                        TableName=table_name,
                        FilterExpression="collection = :collection",
                        ExpressionAttributeValues={":collection": {"S": collection}},
                        ExclusiveStartKey=response["LastEvaluatedKey"],
                    )
                    for item in response.get("Items", []):
                        data = json.loads(item["data"]["S"])
                        if not query:
                            results.append(data)
                        else:
                            match = True
                            for key, value in query.items():
                                if data.get(key) != value:
                                    match = False
                                    break
                            if match:
                                results.append(data)

                return results
        except ClientError as e:
            raise DatabaseError(f"DynamoDB find error: {e}") from e

    async def close(self) -> None:
        """Close the database connection."""
        # Clear table cache
        self._tables_created.clear()
        self._session = None
