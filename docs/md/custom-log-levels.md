# Custom Log Levels in jvspatial

## Overview

jvspatial's logging system supports custom log levels beyond Python's standard levels (DEBUG, INFO, WARNING, ERROR, CRITICAL). This allows you to categorize logs with domain-specific severity levels such as AUDIT, SECURITY, TRACE, BUSINESS_EVENT, or any custom level that fits your application's needs.

This feature is part of the [Database Logging Service](logging-service.md) and works seamlessly with the DBLogHandler for automatic database persistence.

## Why Use Custom Log Levels?

Custom log levels provide several benefits:

1. **Domain-Specific Categorization**: Group logs by business domain (e.g., AUDIT for compliance, SECURITY for security events)
2. **Flexible Filtering**: Query and filter logs by custom categories in the database
3. **Better Observability**: Separate application concerns without mixing them with standard error/info logs
4. **Compliance**: Track specific events required for audit trails or regulatory compliance
5. **Granular Control**: Configure which custom levels to capture in the database

## Quick Start

### Using the Pre-registered CUSTOM Level

jvspatial pre-registers a `CUSTOM` level at level 25 (between INFO=20 and WARNING=30):

```python
import logging
from jvspatial.logging import initialize_logging_database, CUSTOM_LEVEL_NUMBER

# Initialize database logging to capture CUSTOM level
initialize_logging_database(
    log_levels={CUSTOM_LEVEL_NUMBER, logging.ERROR, logging.CRITICAL}
)

# Use with standard logging
logger = logging.getLogger(__name__)
logger.custom("This is a custom log message", extra={
    "event_code": "custom_event",
    "details": {"key": "value"}
})

# Use with JVSpatialLogger
from jvspatial.logging import get_logger
jv_logger = get_logger(__name__)
jv_logger.custom("Custom log with context", user_id="user_123")

# Use with logging service
from jvspatial.logging import get_logging_service
service = get_logging_service()
await service.log_custom(
    event_code="custom_event",
    message="Custom event message",
    details={"operation": "data_export"}
)
```

## Registering Custom Log Levels

### Basic Registration

Register your own custom log levels with `add_custom_log_level()`:

```python
from jvspatial.logging import add_custom_log_level

# Add AUDIT level between WARNING (30) and ERROR (40)
AUDIT = add_custom_log_level("AUDIT", 35, "audit")

# Add SECURITY level between ERROR (40) and CRITICAL (50)
SECURITY = add_custom_log_level("SECURITY", 45, "security")

# Add TRACE level below DEBUG (10)
TRACE = add_custom_log_level("TRACE", 5, "trace")
```

### Parameters

- **level_name** (str): Name of the level (e.g., "AUDIT", "SECURITY")
- **level_number** (int): Numeric severity value (see level guidelines below)
- **method_name** (str, optional): Method name to add to Logger class (defaults to level_name.lower())

### Level Number Guidelines

Standard Python log levels:

```
CRITICAL:  50  - System-wide critical failures
ERROR:     40  - Error conditions
WARNING:   30  - Warning conditions
INFO:      20  - Informational messages
DEBUG:     10  - Debug information
NOTSET:     0  - Not set
```

Suggested custom levels:

```
CRITICAL:  50  - System-wide critical failures
SECURITY:  45  - Security-related events (custom)
ERROR:     40  - Error conditions
AUDIT:     35  - Audit trail events (custom)
WARNING:   30  - Warning conditions
CUSTOM:    25  - General custom events (pre-registered)
INFO:      20  - Informational messages
DEBUG:     10  - Debug information
TRACE:      5  - Detailed trace information (custom)
NOTSET:     0  - Not set
```

## Using Custom Log Levels

### With Standard Python Logging

Once registered, custom levels work like standard levels:

```python
import logging
from jvspatial.logging import add_custom_log_level

# Register custom level
AUDIT = add_custom_log_level("AUDIT", 35)

# Use it
logger = logging.getLogger(__name__)
logger.audit("User action audited", extra={
    "event_code": "user_action",
    "user_id": "user_123",
    "action": "data_export",
    "details": {"records": 1000}
})
```

### With JVSpatialLogger

JVSpatialLogger includes a pre-registered `custom()` method:

```python
from jvspatial.logging import get_logger

logger = get_logger(__name__)
logger.custom(
    "Custom event occurred",
    event_code="custom_operation",
    user_id="user_456",
    session_id="session_789"
)
```

For other custom levels, use the underlying logger:

```python
from jvspatial.logging import get_logger, add_custom_log_level

AUDIT = add_custom_log_level("AUDIT", 35)

jv_logger = get_logger(__name__)
# Access the underlying logger for custom levels
jv_logger.logger.audit("Audit event", extra={"user_id": "user_123"})
```

### With BaseLoggingService

The logging service provides direct database logging:

```python
from jvspatial.logging import get_logging_service

service = get_logging_service()

# Use log_custom() for CUSTOM level
await service.log_custom(
    event_code="custom_event",
    message="Custom event message",
    path="/api/custom",
    method="POST",
    details={"operation": "process_data", "duration": 1.5},
    user_id="user_789",
    tenant_id="tenant_abc"
)

# Use log_error() with log_level parameter for any custom level
await service.log_error(
    event_code="audit_event",
    message="Audit trail entry",
    log_level="AUDIT",
    details={"action": "config_change", "changed_by": "admin_123"}
)

await service.log_error(
    event_code="security_event",
    message="Security policy violation",
    log_level="SECURITY",
    details={"violation_type": "unauthorized_access"}
)
```

## Configuring Database Logging

### Capturing Custom Levels

Include custom levels in the `log_levels` parameter when initializing the database handler:

```python
import logging
from jvspatial.logging import (
    initialize_logging_database,
    add_custom_log_level,
    CUSTOM_LEVEL_NUMBER
)

# Register custom levels
AUDIT = add_custom_log_level("AUDIT", 35)
SECURITY = add_custom_log_level("SECURITY", 45)

# Initialize database logging to capture custom levels
initialize_logging_database(
    database_name="logs",
    enabled=True,
    log_levels={
        CUSTOM_LEVEL_NUMBER,  # Pre-registered CUSTOM level
        AUDIT,                # Custom AUDIT level
        SECURITY,             # Custom SECURITY level
        logging.ERROR,        # Standard ERROR level
        logging.CRITICAL      # Standard CRITICAL level
    }
)
```

### Using Environment Variables

Configure custom levels via environment variables:

```bash
# Comma-separated list of log levels to capture
export JVSPATIAL_DB_LOGGING_LEVELS="CUSTOM,AUDIT,SECURITY,ERROR,CRITICAL"
```

Then in your code:

```python
from jvspatial.logging import initialize_logging_database, add_custom_log_level

# Register custom levels first
add_custom_log_level("AUDIT", 35)
add_custom_log_level("SECURITY", 45)

# Initialize with config from environment
initialize_logging_database()
```

## Querying Custom Level Logs

### Query by Log Level

Retrieve logs by custom level from the database:

```python
from jvspatial.logging import get_logging_service

service = get_logging_service()

# Get all CUSTOM level logs
custom_logs = await service.get_error_logs(log_level="CUSTOM")

# Get all AUDIT level logs
audit_logs = await service.get_error_logs(log_level="AUDIT")

# Get all SECURITY level logs
security_logs = await service.get_error_logs(log_level="SECURITY")
```

### Combine with Other Filters

Custom levels work with all query filters:

```python
from datetime import datetime, timedelta
from jvspatial.logging import get_logging_service

service = get_logging_service()

# Get AUDIT logs from the last 24 hours
audit_logs = await service.get_error_logs(
    log_level="AUDIT",
    start_time=datetime.now() - timedelta(hours=24),
    page=1,
    page_size=50
)

# Get SECURITY logs for a specific path
security_logs = await service.get_error_logs(
    log_level="SECURITY",
    path="/api/admin",
    page=1,
    page_size=100
)

# Get CUSTOM logs with specific event code
custom_logs = await service.get_error_logs(
    log_level="CUSTOM",
    event_code="custom_operation"
)
```

### Response Format

The query returns logs with pagination:

```python
{
    "errors": [
        {
            "log_id": "...",
            "status_code": 200,
            "event_code": "audit_event",
            "message": "User action audited",
            "path": "/api/users",
            "method": "POST",
            "logged_at": "2025-01-02T12:00:00Z",
            "log_data": {
                "message": "User action audited",
                "log_level": "AUDIT",
                "details": {"action": "data_export"},
                "user_id": "user_123"
            }
        },
        ...
    ],
    "pagination": {
        "page": 1,
        "page_size": 50,
        "total": 100,
        "total_pages": 2
    }
}
```

## Utility Functions

### `add_custom_log_level(level_name, level_number, method_name=None)`

Register a new custom log level.

```python
from jvspatial.logging import add_custom_log_level

AUDIT = add_custom_log_level("AUDIT", 35, "audit")
# Returns: 35
# Adds logging.AUDIT = 35 and logger.audit() method
```

### `get_custom_levels()`

Get all registered custom log levels.

```python
from jvspatial.logging import get_custom_levels

levels = get_custom_levels()
# Returns: {'CUSTOM', 'AUDIT', 'SECURITY', 'TRACE'}
```

### `is_custom_level(level_name)`

Check if a log level is a custom level.

```python
from jvspatial.logging import is_custom_level

is_custom_level("CUSTOM")   # True
is_custom_level("AUDIT")    # True (if registered)
is_custom_level("ERROR")    # False (standard level)
```

### `CUSTOM_LEVEL_NUMBER`

The pre-registered CUSTOM level number (25).

```python
from jvspatial.logging import CUSTOM_LEVEL_NUMBER
import logging

print(CUSTOM_LEVEL_NUMBER)  # 25
print(logging.CUSTOM)       # 25
```

## Best Practices

### 1. Choose Meaningful Names

Use names that reflect your application's domain:

```python
# Good
add_custom_log_level("AUDIT", 35)
add_custom_log_level("SECURITY", 45)
add_custom_log_level("BUSINESS_EVENT", 25)
add_custom_log_level("COMPLIANCE", 38)

# Avoid
add_custom_log_level("CUSTOM1", 25)
add_custom_log_level("LEVEL_X", 35)
```

### 2. Document Your Levels

Document what each custom level means:

```python
# audit_logging.py
"""Audit logging for compliance tracking.

AUDIT Level (35): Records user actions and system changes for audit trails.
Used for compliance with SOC2, HIPAA, and internal policies.
"""

from jvspatial.logging import add_custom_log_level

AUDIT = add_custom_log_level("AUDIT", 35, "audit")
```

### 3. Be Consistent

Use the same custom levels across your application:

```python
# config/logging_levels.py
"""Centralized custom log level definitions."""

from jvspatial.logging import add_custom_log_level

# Register all custom levels in one place
TRACE = add_custom_log_level("TRACE", 5)
CUSTOM = 25  # Pre-registered
AUDIT = add_custom_log_level("AUDIT", 35)
SECURITY = add_custom_log_level("SECURITY", 45)

__all__ = ["TRACE", "CUSTOM", "AUDIT", "SECURITY"]
```

Then import from this module everywhere:

```python
from config.logging_levels import AUDIT, SECURITY
```

### 4. Configure Capture Selectively

Only capture the levels you need:

```python
# Development: Capture everything
initialize_logging_database(
    log_levels={TRACE, CUSTOM, AUDIT, SECURITY, ERROR, CRITICAL}
)

# Production: Capture important events only
initialize_logging_database(
    log_levels={AUDIT, SECURITY, ERROR, CRITICAL}
)
```

### 5. Use Appropriate Severity

Place custom levels appropriately in the severity hierarchy:

```python
# Security events are serious (between ERROR and CRITICAL)
SECURITY = add_custom_log_level("SECURITY", 45)

# Audit events are important but not errors (between WARNING and ERROR)
AUDIT = add_custom_log_level("AUDIT", 35)

# Trace is for detailed debugging (below DEBUG)
TRACE = add_custom_log_level("TRACE", 5)
```

## Common Use Cases

### 1. Audit Trails

Track user actions for compliance:

```python
from jvspatial.logging import add_custom_log_level
import logging

AUDIT = add_custom_log_level("AUDIT", 35)

logger = logging.getLogger(__name__)

def export_data(user_id: str, data_type: str):
    # ... export logic ...

    logger.audit(
        f"User {user_id} exported {data_type}",
        extra={
            "event_code": "data_export",
            "user_id": user_id,
            "data_type": data_type,
            "records_exported": 1000,
            "details": {"format": "csv", "encrypted": True}
        }
    )
```

### 2. Security Events

Monitor security-related events:

```python
from jvspatial.logging import add_custom_log_level
import logging

SECURITY = add_custom_log_level("SECURITY", 45)

logger = logging.getLogger(__name__)

def check_access(user_id: str, resource: str):
    if not has_permission(user_id, resource):
        logger.security(
            f"Unauthorized access attempt: {user_id} -> {resource}",
            extra={
                "event_code": "unauthorized_access",
                "user_id": user_id,
                "resource": resource,
                "ip_address": get_client_ip(),
                "details": {"threat_level": "medium"}
            }
        )
        raise PermissionError("Access denied")
```

### 3. Business Events

Track important business events:

```python
from jvspatial.logging import CUSTOM_LEVEL_NUMBER, initialize_logging_database
import logging

# Use pre-registered CUSTOM level for business events
initialize_logging_database(log_levels={CUSTOM_LEVEL_NUMBER})

logger = logging.getLogger(__name__)

def process_order(order_id: str, amount: float):
    # ... order processing logic ...

    logger.custom(
        f"Order processed: {order_id}",
        extra={
            "event_code": "order_completed",
            "order_id": order_id,
            "amount": amount,
            "details": {"payment_method": "credit_card", "status": "success"}
        }
    )
```

### 4. Detailed Tracing

Add verbose tracing for debugging:

```python
from jvspatial.logging import add_custom_log_level
import logging

TRACE = add_custom_log_level("TRACE", 5)

logger = logging.getLogger(__name__)

def complex_algorithm(data):
    logger.trace("Starting algorithm", extra={"data_size": len(data)})

    # ... complex logic ...

    logger.trace("Algorithm completed", extra={"iterations": 100, "result": result})
    return result
```

## Examples

See the [examples/logging](../../examples/logging/) directory for complete examples:

- **[custom_log_levels_example.py](../../examples/logging/custom_log_levels_example.py)**: Comprehensive example showing all features
- **[test_custom_levels_import.py](../../examples/logging/test_custom_levels_import.py)**: Simple test verifying imports work

## API Reference

### Module: `jvspatial.logging.custom_levels`

#### `add_custom_log_level(level_name: str, level_number: int, method_name: Optional[str] = None) -> int`

Register a new custom log level with Python's logging system.

**Parameters:**
- `level_name` (str): Name of the log level (e.g., "AUDIT", "SECURITY")
- `level_number` (int): Numeric value for the level (1-50)
- `method_name` (str, optional): Method name to add to Logger class (defaults to level_name.lower())

**Returns:**
- int: The level number that was registered

**Raises:**
- `ValueError`: If level name already exists with a different number

**Example:**
```python
from jvspatial.logging import add_custom_log_level

AUDIT = add_custom_log_level("AUDIT", 35, "audit")
print(AUDIT)  # 35

import logging
print(logging.AUDIT)  # 35

logger = logging.getLogger(__name__)
logger.audit("Audit message")  # Works!
```

#### `get_custom_levels() -> Set[str]`

Get all registered custom log levels.

**Returns:**
- Set[str]: Set of custom level names

**Example:**
```python
from jvspatial.logging import get_custom_levels, add_custom_log_level

add_custom_log_level("AUDIT", 35)
add_custom_log_level("SECURITY", 45)

levels = get_custom_levels()
print(levels)  # {'CUSTOM', 'AUDIT', 'SECURITY'}
```

#### `is_custom_level(level_name: str) -> bool`

Check if a log level is a custom level.

**Parameters:**
- `level_name` (str): Name of the level to check

**Returns:**
- bool: True if the level is a custom level, False otherwise

**Example:**
```python
from jvspatial.logging import is_custom_level, add_custom_log_level

add_custom_log_level("AUDIT", 35)

print(is_custom_level("CUSTOM"))   # True (pre-registered)
print(is_custom_level("AUDIT"))    # True (custom)
print(is_custom_level("ERROR"))    # False (standard)
print(is_custom_level("UNKNOWN"))  # False
```

#### `CUSTOM_LEVEL_NUMBER: int`

The pre-registered CUSTOM level number (25).

**Example:**
```python
from jvspatial.logging import CUSTOM_LEVEL_NUMBER
import logging

print(CUSTOM_LEVEL_NUMBER)  # 25
print(logging.CUSTOM)       # 25

logger = logging.getLogger(__name__)
logger.custom("Custom message")
```

### Module: `jvspatial.logging`

#### `JVSpatialLogger.custom(message: str, **context: Any) -> None`

Log a message at the CUSTOM level with structured context.

**Parameters:**
- `message` (str): Log message
- `**context` (Any): Additional context data

**Example:**
```python
from jvspatial.logging import get_logger

logger = get_logger(__name__)
logger.custom("Custom event", user_id="user_123", action="export")
```

#### `BaseLoggingService.log_custom(...) -> None`

Log a custom level message directly to the database.

**Parameters:**
- `event_code` (str): Machine-readable event identifier
- `message` (str): Human-readable log message
- `status_code` (Optional[int]): Optional HTTP status code
- `path` (str): Optional request path
- `method` (str): Optional HTTP method
- `details` (Optional[Dict[str, Any]]): Additional log details
- `**kwargs` (Any): Custom fields for extensions

**Example:**
```python
from jvspatial.logging import get_logging_service

service = get_logging_service()
await service.log_custom(
    event_code="custom_event",
    message="Custom event occurred",
    details={"key": "value"}
)
```

## Troubleshooting

### Custom Level Not Captured

If your custom level logs aren't appearing in the database:

1. **Check level is registered before initialization:**
```python
# Register BEFORE initializing database
AUDIT = add_custom_log_level("AUDIT", 35)
initialize_logging_database(log_levels={AUDIT})
```

2. **Verify level is included in log_levels:**
```python
import logging
initialize_logging_database(
    log_levels={AUDIT, logging.ERROR}  # Must include your custom level
)
```

3. **Check the level number is correct:**
```python
print(logging.getLevelName(AUDIT))  # Should print "AUDIT"
```

### Method Not Found on Logger

If `logger.custom()` or other custom methods don't exist:

1. **Verify level was registered:**
```python
from jvspatial.logging import get_custom_levels
print(get_custom_levels())  # Should include your level
```

2. **Check method name:**
```python
# Method name defaults to level_name.lower()
AUDIT = add_custom_log_level("AUDIT", 35)  # Adds logger.audit()

# Or specify custom method name
AUDIT = add_custom_log_level("AUDIT", 35, "log_audit")  # Adds logger.log_audit()
```

### Level Name Conflict

If you get "Log level already exists" error:

```python
# Check if level exists
import logging
try:
    level = logging.getLevelName("AUDIT")
    print(f"AUDIT already exists as: {level}")
except:
    # Level doesn't exist yet
    pass
```

## Additional Resources

- [Database Logging Service](logging-service.md) - Complete logging service documentation
- [Error Handling](error-handling.md) - Error handling patterns
- [Python Logging Documentation](https://docs.python.org/3/library/logging.html) - Official Python logging docs
- [Examples](../../examples/logging/) - Code examples

