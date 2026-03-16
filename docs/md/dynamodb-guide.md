# DynamoDB Setup Guide

jvspatial supports Amazon DynamoDB as a database backend for scalable, serverless graph storage.

## Prerequisites

- **aioboto3**: `pip install aioboto3>=12.0.0`
- AWS credentials (IAM role, environment variables, or ~/.aws/credentials)

## Quick Setup

### Server Configuration

```python
from jvspatial.api import Server

server = Server(
    title="My API",
    db_type="dynamodb",
    dynamodb_table_name="jvspatial",
    dynamodb_region="us-east-1",
)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JVSPATIAL_DB_TYPE` | `json` | Set to `dynamodb` |
| `JVSPATIAL_DYNAMODB_TABLE_NAME` | `jvspatial` | DynamoDB table name |
| `JVSPATIAL_DYNAMODB_REGION` | `us-east-1` | AWS region |
| `JVSPATIAL_DYNAMODB_ENDPOINT_URL` | — | For local DynamoDB (e.g. `http://localhost:8000`) |
| `JVSPATIAL_DYNAMODB_ACCESS_KEY_ID` | — | AWS access key (optional if using IAM role) |
| `JVSPATIAL_DYNAMODB_SECRET_ACCESS_KEY` | — | AWS secret key (optional if using IAM role) |

### Programmatic Setup

```python
from jvspatial.db import create_database, get_database_manager
from jvspatial.core.context import GraphContext

db = create_database(
    db_type="dynamodb",
    table_name="my-jvspatial-table",
    region_name="us-east-1",
    endpoint_url=None,  # Use for local DynamoDB
    aws_access_key_id=None,
    aws_secret_access_key=None,
)

manager = get_database_manager()
manager.set_prime_database(db)
ctx = GraphContext(database=db)
```

## Local Development

For local testing with DynamoDB Local or LocalStack:

```python
db = create_database(
    db_type="dynamodb",
    table_name="jvspatial",
    region_name="us-east-1",
    endpoint_url="http://localhost:8000",
)
```

## Index Creation

By default, indexes are **not** created automatically. To enable:

```bash
export JVSPATIAL_AUTO_CREATE_INDEXES=true
```

To wait for Global Secondary Indexes to become active (adds startup delay):

```bash
export JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX=true
```

## See Also

- [Graph Context](graph-context.md) - Database management
- [Environment Configuration](environment-configuration.md) - Full env reference
