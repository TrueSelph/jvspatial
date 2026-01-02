# Database Logging Service

The jvspatial database logging service automatically saves log records to a separate database with configurable log levels. Simply use the standard Python logger with optional `details` - no complex setup required.

## Overview

The logging service consists of:

1. **DBLog Model** - Base object model for storing log information with indexing
2. **DBLogHandler** - Logging handler that intercepts log records at configurable levels
3. **Automatic Installation** - Handler is installed when database is initialized
4. **Console Error Patching** - Catches uncaught exceptions via `sys.excepthook`
5. **Authenticated API Endpoints** - Query logs via REST API with pagination and filtering
6. **Custom Log Levels** - Support for domain-specific log levels (AUDIT, SECURITY, CUSTOM, etc.)

See also: [Custom Log Levels](custom-log-levels.md) for detailed information on using custom log levels.

## Quick Start

### Basic Usage

Just initialize the logging database and start logging:

```python
from jvspatial.logging import initialize_logging_database
import logging

# Initialize logging database (automatically installs DBLogHandler)
initialize_logging_database()

# Use the standard logger - logs are automatically saved to database
logger = logging.getLogger(__name__)
logger.error("Database connection failed")
logger.warning("Configuration issue detected")
logger.info("User logged in")
```

### With Details and Agent ID

Add log details and agent_id for cross-referencing:

```python
logger.error(
    "Validation failed",
    extra={
        "details": {"field": "email", "value": "invalid"},
        "status_code": 422,
        "error_code": "validation_error",
        "path": "/api/users",
        "method": "POST",
        "agent_id": "agent_456"  # For cross-referencing
    }
)
```

### With Exception

Include exception traceback:

```python
try:
    risky_operation()
except Exception:
    logger.error("Operation failed", exc_info=True)
```

### With Custom Log Levels

Use custom log levels for domain-specific categorization:

```python
from jvspatial.logging import add_custom_log_level, initialize_logging_database
import logging

# Register custom level
AUDIT = add_custom_log_level("AUDIT", 35)

# Initialize with custom level
initialize_logging_database(
    log_levels={AUDIT, logging.ERROR, logging.CRITICAL}
)

# Use custom level
logger.audit("User action performed", extra={"user_id": "user_123"})
```

See [Custom Log Levels](custom-log-levels.md) for complete documentation.

## Configuration

### Log Levels

Configure which log levels to capture (default: ERROR, CRITICAL):

```bash
# Capture ERROR and CRITICAL only (default)
JVSPATIAL_DB_LOGGING_LEVELS=ERROR,CRITICAL

# Capture all levels
JVSPATIAL_DB_LOGGING_LEVELS=DEBUG,INFO,WARNING,ERROR,CRITICAL

# Capture warnings and above
JVSPATIAL_DB_LOGGING_LEVELS=WARNING,ERROR,CRITICAL
```

### Enable/Disable Logging

```bash
# Enable database logging (default)
JVSPATIAL_DB_LOGGING_ENABLED=true

# Disable database logging
JVSPATIAL_DB_LOGGING_ENABLED=false
```

### Database Name

```bash
# Database name (default: logs)
JVSPATIAL_DB_LOGGING_DB_NAME=logs
```

### API Endpoints

```bash
# Enable API endpoints (default)
JVSPATIAL_DB_LOGGING_API_ENABLED=true

# Disable API endpoints
JVSPATIAL_DB_LOGGING_API_ENABLED=false
```

### Database Configuration

```bash
# Database type (json, sqlite, mongodb, dynamodb)
JVSPATIAL_LOG_DB_TYPE=json

# For JSON database
JVSPATIAL_LOG_DB_PATH=./jvspatial_logs

# For SQLite database
JVSPATIAL_LOG_DB_PATH=./logs/jvspatial_logs.db

# For MongoDB
JVSPATIAL_LOG_DB_URI=mongodb://localhost:27017
JVSPATIAL_LOG_DB_NAME=jvspatial_logs

# For DynamoDB
JVSPATIAL_LOG_DB_TABLE_NAME=jvspatial_logs
JVSPATIAL_LOG_DB_REGION=us-east-1
```

### Programmatic Configuration

```python
from jvspatial.logging import initialize_logging_database
import logging

# Custom configuration
initialize_logging_database(
    enabled=True,
    log_levels={logging.WARNING, logging.ERROR, logging.CRITICAL},
    database_name="logs",
    enable_api_endpoints=True
)

# Disable logging
initialize_logging_database(enabled=False)
```

## Console Error Patching

The service automatically patches `sys.excepthook` to catch uncaught exceptions:

```python
# Uncaught exceptions are automatically logged at CRITICAL level
raise ValueError("This will be caught and logged!")
```

The exception hook:
- Logs uncaught exceptions at CRITICAL level
- Includes full traceback
- Skips KeyboardInterrupt (allows Ctrl+C)
- Calls original hook after logging

## API Endpoints

### Query Logs

```http
GET /api/logs?category=ERROR&page=1&page_size=50
```

**Authentication Required**: Yes

**Query Parameters:**
- `category` (optional): Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL, or custom levels)
- `start_date` (optional): ISO format start date (e.g., `2024-01-01T00:00:00Z`)
- `end_date` (optional): ISO format end date
- `agent_id` (optional): Filter by agent_id for cross-referencing
- `page` (optional, default: 1): Page number
- `page_size` (optional, default: 50, max: 200): Items per page

**Response:**
```json
{
  "logs": [
    {
      "log_id": "log_123",
      "log_level": "ERROR",
      "status_code": 500,
      "error_code": "internal_error",
      "message": "Database connection failed",
      "path": "/api/users",
      "method": "POST",
      "agent_id": "agent_456",
      "logged_at": "2024-01-15T10:30:00Z",
      "error_data": {
        "message": "Database connection failed",
        "log_level": "ERROR",
        "details": {...}
      }
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total": 100,
    "total_pages": 2
  }
}
```

**Examples:**

```bash
# Get all ERROR logs
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/logs?category=ERROR"

# Get logs for specific agent
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/logs?agent_id=agent_123"

# Get logs in date range
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/logs?start_date=2024-01-01T00:00:00Z&end_date=2024-01-31T23:59:59Z"

# Combined filters
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/logs?category=ERROR&agent_id=agent_123&page=1&page_size=50"

# Query custom log levels
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/logs?category=INTERACTION"
```

## Custom Log Levels

jvspatial supports custom log levels for domain-specific categorization. Use custom levels like AUDIT, SECURITY, INTERACTION, or any level that fits your application's needs.

**Quick Example:**
```python
from jvspatial.logging import add_custom_log_level, initialize_logging_database
import logging

# Register custom level
AUDIT = add_custom_log_level("AUDIT", 35)

# Initialize with custom level
initialize_logging_database(log_levels={AUDIT, logging.ERROR, logging.CRITICAL})

# Use it
logger = logging.getLogger(__name__)
logger.audit("User action performed", extra={"user_id": "user_123"})
```

For complete documentation on custom log levels, see [Custom Log Levels](custom-log-levels.md).

## Related Documentation

- [Custom Log Levels](custom-log-levels.md) - Complete guide to using custom log levels
- [Error Handling](error-handling.md) - Error handling patterns
- [REST API](rest-api.md) - API documentation
