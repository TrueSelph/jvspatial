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

### SQLite Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_SQLITE_PATH` | string | `jvdb/sqlite/jvspatial.db` | SQLite database file location (directories are created automatically) |

### MongoDB Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_MONGODB_URI` | string | `mongodb://localhost:27017` | MongoDB connection URI |
| `JVSPATIAL_MONGODB_DB_NAME` | string | `jvdb` | MongoDB database name |

### Performance & Caching Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JVSPATIAL_CACHE_BACKEND` | string | auto | Cache backend to use: `memory`, `redis`, or `layered`. Auto-detected based on Redis URL availability. |
| `JVSPATIAL_CACHE_SIZE` | integer | `1000` | Number of entities to cache in memory (for memory backend or L1 in layered cache). |
| `JVSPATIAL_L1_CACHE_SIZE` | integer | `500` | Size of L1 (memory) cache when using layered caching. |
| `JVSPATIAL_REDIS_URL` | string | `redis://localhost:6379` | Redis connection URL for redis/layered cache backends. |
| `JVSPATIAL_REDIS_TTL` | integer | `3600` | Time-to-live in seconds for Redis cache entries. |

See the [Caching Documentation](caching.md) for detailed information about cache backends and configuration.

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
from jvspatial.db.factory import get_database

# Set environment variable at runtime
os.environ['JVSPATIAL_DB_TYPE'] = 'mongodb'

# Or pass configuration directly
db = get_database('mongodb',
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

## Environment Variable Priority

Environment variables are resolved in the following order (highest to lowest priority):

1. **Runtime environment variables** - Set directly in the process environment
2. **System environment variables** - Set at the OS level
3. **Default values** - Built-in defaults in the library

### Example Priority Resolution

```python
import os
from jvspatial.db.factory import get_database

# 1. System/shell environment (lowest priority)
# export JVSPATIAL_DB_TYPE=json

# 2. Runtime override (highest priority)
os.environ['JVSPATIAL_DB_TYPE'] = 'mongodb'

# Result: Uses 'mongodb' (runtime override wins)
db = get_database()
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
from jvspatial.db.factory import get_database

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Check current configuration
print(f"DB_TYPE: {os.getenv('JVSPATIAL_DB_TYPE', 'not set')}")
print(f"MONGODB_URI: {os.getenv('JVSPATIAL_MONGODB_URI', 'not set')}")
print(f"JSONDB_PATH: {os.getenv('JVSPATIAL_JSONDB_PATH', 'not set')}")

# Test database connection
try:
    db = get_database()
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
from jvspatial.db.factory import get_database, set_default_database
from jvspatial.core import GraphContext

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

    # Set MongoDB as default
    set_default_database('mongodb')

    # Test database connection
    try:
        db = get_database()
        # Perform a simple test operation
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