# Environment Configuration

This guide provides comprehensive information about configuring jvspatial using environment variables.

## Table of Contents

- [Overview](#overview)
- [Environment Variables Reference](#environment-variables-reference)
- [Configuration Methods](#configuration-methods)
- [Database-Specific Configuration](#database-specific-configuration)
- [Deployment Scenarios](#deployment-scenarios)
- [Environment Variable Priority](#environment-variable-priority)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

## Overview

jvspatial uses environment variables to configure database connections, file paths, and other runtime settings. This approach provides flexibility for different deployment environments without requiring code changes.

### Key Benefits

- **Environment-specific configuration**: Different settings for development, testing, and production
- **Security**: Keep sensitive information (passwords, URIs) out of source code
- **Flexibility**: Easy runtime configuration changes
- **Container-friendly**: Works seamlessly with Docker and Kubernetes

## Environment Variables Reference

### Core Database Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_DB_TYPE` | string | `json` | Database backend to use (`json`, `sqlite`, `mongodb`) |

### JSON Database Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_JSONDB_PATH` | string | `jvdb` | Base directory path for JSON database files |
| `JVSPATIAL_DB_PATH` | string | — | Generic path for JSON/SQLite when using env-only config. Server config (`db_path`) overrides env when both are set. |

### SQLite Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_SQLITE_PATH` | string | `jvdb/sqlite/jvspatial.db` | SQLite database file location (directories are created automatically) |
| `JVSPATIAL_DB_PATH` | string | — | Alternative; used when `db_type` is sqlite and no explicit path is set. Server config overrides env. |

### MongoDB Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_MONGODB_URI` | string | `mongodb://localhost:27017` | MongoDB connection URI |
| `JVSPATIAL_MONGODB_DB_NAME` | string | `jvdb` | MongoDB database name |
| `JVSPATIAL_MONGODB_MAX_POOL_SIZE` | integer | `10` | Maximum connections in pool (Lambda-friendly default) |
| `JVSPATIAL_MONGODB_MIN_POOL_SIZE` | integer | `0` | Minimum connections in pool (Lambda-friendly default) |

When the API Server initializes the prime MongoDB connection (`db_type=mongodb`), each of **`JVSPATIAL_MONGODB_URI`** and **`JVSPATIAL_MONGODB_DB_NAME`** is resolved independently. If the variable is **set** in the process environment and its value is **non-empty** after trimming, it overrides the corresponding Server config field (`database.db_connection_string` or `database.db_database_name`). If the variable is **unset** (`os.getenv` returns `None`), or set but **blank** after trimming, that field falls back to config, then to the defaults in this table (`mongodb://localhost:27017` and `jvdb`). This lets Lambda and other hosts set Mongo in env while app config still applies when those keys are not set.

### Performance & Caching Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_CACHE_BACKEND` | string | auto | Cache backend to use: `memory`, `redis`, or `layered`. Auto-detected based on Redis URL availability. |
| `JVSPATIAL_CACHE_SIZE` | integer | `1000` | Number of entities to cache in memory (for memory backend or L1 in layered cache). |
| `JVSPATIAL_L1_CACHE_SIZE` | integer | `500` | Size of L1 (memory) cache when using layered caching. |
| `JVSPATIAL_REDIS_URL` | string | `redis://localhost:6379` | Redis connection URL for redis/layered cache backends. |
| `JVSPATIAL_REDIS_TTL` | integer | `3600` | Time-to-live in seconds for Redis cache entries. |

See the [Caching Documentation](caching.md) for detailed information about cache backends and configuration.

### Serverless Mode Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SERVERLESS_MODE` | boolean | auto | Force serverless-safe runtime behavior. When unset, auto-detects AWS Lambda (`AWS_LAMBDA_RUNTIME_API` / `AWS_LAMBDA_FUNCTION_NAME`) and other common serverless runtimes. |
| `JVSPATIAL_DEFERRED_INVOKE_DISABLED` | boolean | `false` | When true, `register_deferred_invoke_route` does not mount `POST …/_internal/deferred`. |
| `JVSPATIAL_DEFERRED_INVOKE_SECRET` | string | _(empty)_ | When set, deferred-invoke HTTP requests must send this value via `X-JVSPATIAL-Deferred-Authorize` or `Authorization: Bearer …`. |
| `JVSPATIAL_WORK_CLAIM_STALE_SECONDS` | float | `600` | Default TTL for work-claim leases (`claim_record`). After this many seconds another worker can re-claim the document. |

Use `is_serverless_mode()` from `jvspatial` or `jvspatial.runtime.serverless` to check at runtime. With no argument, `is_serverless_mode()` uses `get_current_server().config` when the server context is set (see serverless-mode docs):

```python
from jvspatial import is_serverless_mode

if is_serverless_mode():
    await some_coro()
else:
    asyncio.create_task(some_coro())
```

`BACKGROUND_PROCESSING` is removed. Runtime behavior is derived from serverless mode only.

### Text Normalization Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_TEXT_NORMALIZATION_ENABLED` | boolean | `true` | Enable automatic Unicode to ASCII text normalization when persisting data to the database. Converts smart quotes, dashes, and other Unicode characters to ASCII equivalents to prevent encoding issues. |

**Text Normalization** automatically converts Unicode characters to ASCII equivalents when saving entities to the database. This prevents encoding issues with characters like smart quotes (`\u2019` → `'`), em dashes (`\u2014` → `-`), and other Unicode punctuation.

**Examples of normalized characters:**
- Smart quotes: `"Here's"` → `"Here's"`
- Em/en dashes: `"text—dash"` → `"text-dash"`
- Ellipsis: `"text…"` → `"text..."`
- Various Unicode spaces → regular space
- Diacritics: `"café"` → `"cafe"`

Normalization is applied recursively to all string values in nested dictionaries and lists, while preserving non-string types (numbers, booleans, etc.).

To disable text normalization:
```bash
export JVSPATIAL_TEXT_NORMALIZATION_ENABLED=false
```

### Authentication & Bootstrap Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_JWT_SECRET_KEY` | string | — | JWT secret (required when auth enabled). Must be cryptographically secure, 32+ chars. |
| `JVSPATIAL_API_PREFIX` | string | `/api` | URL prefix for API routes. Auth endpoints become `{prefix}/auth/...`. Affects exempt path expansion. |
| `ADMIN_EMAIL` | string | — | Admin email for bootstrap. When set with `ADMIN_PASSWORD`, creates an admin user on first run. Pass to `auth.bootstrap_admin_email`. |
| `ADMIN_PASSWORD` | string | — | Admin password for bootstrap (min 6 chars). Pass to `auth.bootstrap_admin_password`. |
| `ADMIN_NAME` | string | — | Admin display name for bootstrap. Defaults to email. Pass to `auth.bootstrap_admin_name`. |

Example usage in Server config:

```python
import os

server = Server(
    auth=dict(
        auth_enabled=True,
        jwt_secret=os.getenv("JVSPATIAL_JWT_SECRET_KEY"),
        bootstrap_admin_email=os.getenv("ADMIN_EMAIL"),
        bootstrap_admin_password=os.getenv("ADMIN_PASSWORD"),
        bootstrap_admin_name=os.getenv("ADMIN_NAME"),
    ),
)
```

## Configuration Methods

### 1. Environment Variables

Set variables directly in your shell:

```bash
export JVSPATIAL_DB_TYPE=mongodb
export JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
export JVSPATIAL_MONGODB_DB_NAME=my_spatial_db

# SQLite example
export JVSPATIAL_DB_TYPE=sqlite
export JVSPATIAL_SQLITE_PATH=/var/data/jvspatial/app.db
```

### 2. .env Files

Create a `.env` file in your project root:

```env
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
JVSPATIAL_MONGODB_DB_NAME=my_spatial_db
```

Load it in your Python application:

```python
from dotenv import load_dotenv
load_dotenv()

# jvspatial will automatically use the environment variables
from jvspatial.core import GraphContext
ctx = GraphContext()  # Uses environment configuration
```

### 3. Runtime Configuration

Override environment variables programmatically:

```python
import os
from jvspatial.db import create_database

# Set environment variable at runtime
os.environ['JVSPATIAL_DB_TYPE'] = 'mongodb'

# Or pass configuration directly
db = create_database('mongodb',
                  uri='mongodb://localhost:27017',
                  db_name='custom_db')
```

## Database-Specific Configuration

### JSON Database

The JSON database stores data in local files and is ideal for development, testing, and small-scale applications.

#### Configuration

```env
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=./jvdb
```

#### Path Examples

```bash
# Relative paths (relative to application working directory)
JVSPATIAL_JSONDB_PATH=./jvdb
JVSPATIAL_JSONDB_PATH=../shared/db

# Absolute paths
JVSPATIAL_JSONDB_PATH=/var/lib/jvspatial
JVSPATIAL_JSONDB_PATH=/home/user/spatial_data

# Home directory paths
JVSPATIAL_JSONDB_PATH=~/spatial_db_data
```

#### Directory Structure

The JSON database creates the following structure:

```
{JVSPATIAL_JSONDB_PATH}/
├── node/
│   ├── user_123.json
│   └── city_456.json
├── edge/
│   └── highway_789.json
├── walker/
│   └── processor_abc.json
└── object/
    └── metadata_def.json
```

### MongoDB Database

MongoDB provides scalable, production-ready persistence with advanced querying capabilities.

#### Basic Configuration

```env
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial_production
```

#### Authentication

```env
JVSPATIAL_MONGODB_URI=mongodb://username:password@localhost:27017
```

#### MongoDB Atlas (Cloud)

```env
JVSPATIAL_MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
JVSPATIAL_MONGODB_DB_NAME=production_spatial_db
```

#### Replica Set

```env
JVSPATIAL_MONGODB_URI=mongodb://host1:27017,host2:27017,host3:27017/?replicaSet=myReplicaSet
```

#### Advanced Connection Options

```env
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017/?maxPoolSize=20&minPoolSize=5&connectTimeoutMS=30000
```

#### Lambda / DocumentDB

For AWS Lambda with Amazon DocumentDB, use connection settings that avoid stale connections after idle periods. The MongoDB layer retries once on connection errors and uses Lambda-friendly pool defaults.

**Recommended environment variables:**

```env
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://docdb-host:27017/?tls=true&tlsCAFile=global-bundle.pem&maxIdleTimeMS=60000&connectTimeoutMS=20000&serverSelectionTimeoutMS=20000
JVSPATIAL_MONGODB_DB_NAME=your_db
JVSPATIAL_MONGODB_MIN_POOL_SIZE=0
JVSPATIAL_MONGODB_MAX_POOL_SIZE=10
```

**URI options:**
- `maxIdleTimeMS=60000` – Close idle connections before DocumentDB timeout
- `connectTimeoutMS=20000` – Connection establishment timeout
- `serverSelectionTimeoutMS=20000` – Server selection timeout
- `tls=true` and `tlsCAFile` – Required for DocumentDB

**Pool settings:** `minPoolSize=0` avoids maintaining idle connections; `maxPoolSize=10` keeps the pool small for serverless.

## Deployment Scenarios

### Development Environment

```env
# .env.development
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=./jvdb/dev
```

### Testing Environment

```env
# .env.test
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=./jvdb/test
```

### Staging Environment

```env
# .env.staging
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://staging-mongo:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial_staging
```

### Production Environment

```env
# .env.production
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb+srv://prod_user:secure_password@production-cluster.mongodb.net/
JVSPATIAL_MONGODB_DB_NAME=jvspatial_production
```

### Docker Environment

```env
# .env.docker
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://mongo_container:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial_docker
```

### Kubernetes Environment

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: jvspatial-config
data:
  JVSPATIAL_DB_TYPE: "mongodb"
  JVSPATIAL_MONGODB_DB_NAME: "jvspatial_k8s"
---
apiVersion: v1
kind: Secret
metadata:
  name: jvspatial-secrets
type: Opaque
stringData:
  JVSPATIAL_MONGODB_URI: "mongodb+srv://user:password@cluster.mongodb.net/"
```

## Server Config vs Environment

When using `Server(db_type=..., db_path=...)`, the Server configuration **overrides** environment variables. Environment variables apply when no explicit config is passed (e.g. when using `create_database()` directly or when Server is configured via env-only).

## Path Resolution

Relative `db_path` values resolve against the **current working directory** (cwd). When the app runs from different directories (e.g. project root vs `backend/`), the path can point to different locations.

**Options:**
- **Absolute paths**: Use `/var/data/jvdb` or `os.path.abspath("track75_db")` in production.
- **`db_path_resolve="app"`**: Resolve relative paths against the directory of the module that instantiated `Server`:
  ```python
  server = Server(
      db_type="json",
      db_path="track75_db",
      db_path_resolve="app",
      auth=dict(auth_enabled=True, jwt_secret="..."),
  )
  ```

## Environment Variable Priority

Environment variables are resolved in the following order (highest to lowest priority):

1. **Server config** - `Server(db_path="...")` overrides env
2. **Runtime environment variables** - Set directly in the process environment
3. **System environment variables** - Set at the OS level
4. **Default values** - Built-in defaults in the library

### Example Priority Resolution

```python
import os
from jvspatial.db import create_database

# 1. System/shell environment (lowest priority)
# export JVSPATIAL_DB_TYPE=json

# 2. Runtime override (highest priority)
os.environ['JVSPATIAL_DB_TYPE'] = 'mongodb'

# Result: Uses 'mongodb' (runtime override wins)
db = create_database(os.getenv("JVSPATIAL_DB_TYPE", "json"))
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Failures

**Issue**: MongoDB connection errors

```
RuntimeError: Failed to connect to MongoDB: ...
```

**Solutions**:
- Verify MongoDB is running: `mongosh mongodb://localhost:27017`
- Check URI format and credentials
- Ensure network connectivity
- Verify firewall/security group settings

#### 2. File Permission Errors (JSON Database)

**Issue**: Cannot write to JSON database path

```
PermissionError: [Errno 13] Permission denied: './jvdb'
```

**Solutions**:
- Check directory permissions: `ls -la ./jvdb`
- Create directory with proper permissions: `mkdir -p ./jvdb && chmod 755 ./jvdb`
- Use absolute paths in production
- Ensure application user has write access

#### 3. Environment Variable Not Loaded

**Issue**: Configuration not being applied

**Solutions**:
- Verify environment variable is set: `echo $JVSPATIAL_DB_TYPE`
- Check .env file loading: ensure `load_dotenv()` is called
- Verify variable names (case-sensitive)
- Check for typos in variable names

#### 4. Path Resolution Issues

**Issue**: Relative paths not resolving correctly

**Solutions**:
- Use absolute paths in production
- Check current working directory: `os.getcwd()`
- Use `os.path.abspath()` for path resolution

### Debug Configuration

Enable debug logging to troubleshoot configuration issues:

```python
import logging
import os
from jvspatial.db import create_database

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Check current configuration
print(f"DB_TYPE: {os.getenv('JVSPATIAL_DB_TYPE', 'not set')}")
print(f"MONGODB_URI: {os.getenv('JVSPATIAL_MONGODB_URI', 'not set')}")
print(f"JSONDB_PATH: {os.getenv('JVSPATIAL_JSONDB_PATH', 'not set')}")

# Test database connection
try:
    db = create_database(os.getenv("JVSPATIAL_DB_TYPE", "json"))
    print(f"Successfully created database: {db.__class__.__name__}")
except Exception as e:
    print(f"Database creation failed: {e}")
```

## Best Practices

### Security

1. **Never commit .env files** with real credentials to version control
2. **Use strong passwords** for database authentication
3. **Restrict network access** in production environments
4. **Use secrets management** systems in production (AWS Secrets Manager, Azure Key Vault, etc.)
5. **Rotate credentials** regularly

### Configuration Management

1. **Use different .env files** for different environments
2. **Document environment variables** in your project README
3. **Validate configuration** at application startup
4. **Provide sensible defaults** for development environments
5. **Use absolute paths** in production deployments

### Development Workflow

1. **Copy .env.example to .env** for new projects
2. **Use JSON database** for local development
3. **Use MongoDB** for staging and production
4. **Keep .env files** in .gitignore
5. **Document required variables** for team members

### Production Deployment

1. **Use MongoDB** for scalability and reliability
2. **Set up monitoring** for database connections
3. **Use connection pooling** (configured via URI parameters)
4. **Implement backup strategies** for data persistence
5. **Use secrets management** instead of plain text credentials

### Example Production Setup

```python
# production_config.py
import os
from jvspatial.db import create_database, get_database_manager
from jvspatial.core.context import GraphContext

def configure_production():
    """Configure jvspatial for production environment."""

    # Validate required environment variables
    required_vars = [
        'JVSPATIAL_MONGODB_URI',
        'JVSPATIAL_MONGODB_DB_NAME'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {missing_vars}")

    # Test database connection (uses env vars: JVSPATIAL_DB_TYPE, JVSPATIAL_MONGODB_URI, etc.)
    try:
        db = create_database(
            db_type=os.getenv("JVSPATIAL_DB_TYPE", "mongodb"),
            uri=os.getenv("JVSPATIAL_MONGODB_URI"),
            db_name=os.getenv("JVSPATIAL_MONGODB_DB_NAME"),
        )
        manager = get_database_manager()
        manager.set_prime_database(db)
        test_ctx = GraphContext(database=db)
        print("Production database configuration successful")
        return test_ctx
    except Exception as e:
        raise RuntimeError(f"Production database configuration failed: {e}")

# Usage
if __name__ == "__main__":
    ctx = configure_production()
```

This configuration approach ensures reliable, secure, and maintainable deployments across different environments.