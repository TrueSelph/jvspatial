"""Example demonstrating custom log levels in jvspatial logging.

This example shows how to:
1. Register custom log levels
2. Use custom levels with standard Python logging
3. Use custom levels with JVSpatialLogger
4. Configure DBLogHandler to capture custom levels
5. Query custom level logs from the database
"""

import asyncio
import logging
from datetime import datetime, timezone

# Import jvspatial logging components
from jvspatial.logging import (
    CUSTOM_LEVEL_NUMBER,
    add_custom_log_level,
    get_custom_levels,
    get_logger,
    get_logging_service,
    initialize_logging_database,
    install_db_log_handler,
)


async def main():
    """Demonstrate custom log levels."""

    print("=" * 80)
    print("Custom Log Levels Example")
    print("=" * 80)

    # 1. The CUSTOM level is pre-registered at level 25 (between INFO=20 and WARNING=30)
    print(f"\n1. Pre-registered CUSTOM level: {CUSTOM_LEVEL_NUMBER}")
    print(f"   Standard levels for reference:")
    print(f"   - DEBUG: {logging.DEBUG}")
    print(f"   - INFO: {logging.INFO}")
    print(f"   - CUSTOM: {CUSTOM_LEVEL_NUMBER}")
    print(f"   - WARNING: {logging.WARNING}")
    print(f"   - ERROR: {logging.ERROR}")
    print(f"   - CRITICAL: {logging.CRITICAL}")

    # 2. Register additional custom log levels
    print("\n2. Registering additional custom log levels:")

    # TRACE level (below DEBUG)
    TRACE = add_custom_log_level("TRACE", 5, "trace")
    print(f"   - TRACE: {TRACE}")

    # AUDIT level (between WARNING and ERROR)
    AUDIT = add_custom_log_level("AUDIT", 35, "audit")
    print(f"   - AUDIT: {AUDIT}")

    # SECURITY level (between ERROR and CRITICAL)
    SECURITY = add_custom_log_level("SECURITY", 45, "security")
    print(f"   - SECURITY: {SECURITY}")

    print(f"\n   All custom levels: {get_custom_levels()}")

    # 3. Initialize logging database
    print("\n3. Initializing logging database...")
    initialize_logging_database(
        database_name="logs",
        enabled=True,
        # Capture CUSTOM, AUDIT, SECURITY, ERROR, and CRITICAL levels
        log_levels={
            CUSTOM_LEVEL_NUMBER,
            AUDIT,
            SECURITY,
            logging.ERROR,
            logging.CRITICAL,
        },
    )
    print("   Database logging initialized")

    # 4. Use custom levels with standard Python logging
    print("\n4. Logging with standard Python logger:")
    std_logger = logging.getLogger(__name__)

    # These will be captured by DBLogHandler
    std_logger.custom("Custom level log via standard logger")
    std_logger.audit(
        "User action audited",
        extra={
            "event_code": "user_action",
            "details": {"action": "data_export", "user_id": "user_123"},
        },
    )
    std_logger.security(
        "Security event detected",
        extra={
            "event_code": "security_alert",
            "details": {"ip": "192.168.1.1", "threat_level": "medium"},
        },
    )

    # This won't be captured (below configured levels)
    std_logger.trace("Trace level log (not captured)")
    std_logger.info("Info level log (not captured)")

    print("   Logged CUSTOM, AUDIT, and SECURITY events")

    # 5. Use custom levels with JVSpatialLogger
    print("\n5. Logging with JVSpatialLogger:")
    jv_logger = get_logger(__name__)

    jv_logger.custom(
        "Custom event with context",
        event_code="custom_operation",
        user_id="user_456",
        session_id="session_789",
    )
    print("   Logged custom event with context")

    # 6. Use BaseLoggingService.log_custom() directly
    print("\n6. Logging with BaseLoggingService:")
    logging_service = get_logging_service()

    await logging_service.log_custom(
        event_code="custom_event",
        message="Custom event via logging service",
        path="/api/custom",
        method="POST",
        details={
            "operation": "process_data",
            "duration": 1.5,
            "items_processed": 100,
        },
        user_id="user_789",
        tenant_id="tenant_abc",
    )
    print("   Logged custom event via service")

    # 7. Log with any custom level using log_error with log_level parameter
    await logging_service.log_error(
        event_code="audit_event",
        message="Audit trail entry",
        log_level="AUDIT",
        details={"action": "config_change", "changed_by": "admin_123"},
    )
    print("   Logged AUDIT event via service")

    await logging_service.log_error(
        event_code="security_event",
        message="Security policy violation",
        log_level="SECURITY",
        details={"violation_type": "unauthorized_access", "user": "user_999"},
    )
    print("   Logged SECURITY event via service")

    # Wait a moment for async logging to complete
    await asyncio.sleep(0.5)

    # 8. Query custom level logs
    print("\n8. Querying custom level logs:")

    # Query all CUSTOM level logs
    custom_logs = await logging_service.get_error_logs(
        log_level="CUSTOM",
        page=1,
        page_size=10,
    )
    print(f"\n   CUSTOM level logs: {custom_logs['pagination']['total']} found")
    for log in custom_logs["errors"]:
        print(f"   - {log['event_code']}: {log['message']}")

    # Query all AUDIT level logs
    audit_logs = await logging_service.get_error_logs(
        log_level="AUDIT",
        page=1,
        page_size=10,
    )
    print(f"\n   AUDIT level logs: {audit_logs['pagination']['total']} found")
    for log in audit_logs["errors"]:
        print(f"   - {log['event_code']}: {log['message']}")

    # Query all SECURITY level logs
    security_logs = await logging_service.get_error_logs(
        log_level="SECURITY",
        page=1,
        page_size=10,
    )
    print(f"\n   SECURITY level logs: {security_logs['pagination']['total']} found")
    for log in security_logs["errors"]:
        print(f"   - {log['event_code']}: {log['message']}")

    print("\n" + "=" * 80)
    print("Example completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    # Configure console logging to show all levels
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    # Run the example
    asyncio.run(main())
