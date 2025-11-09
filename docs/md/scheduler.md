# jvspatial Scheduler Integration

A lightweight, optional scheduler service for jvspatial that integrates seamlessly with the Server class using the `schedule` package. Designed following jvspatial's entity-centric patterns with MongoDB-style queries and comprehensive error handling.

## Features

- **Simple Scheduling**: Use `@on_schedule` decorator for intuitive task scheduling
- **Entity-Centric**: Creates Node entities for job tracking and metrics
- **MongoDB Queries**: Full support for complex filtering and aggregation
- **FastAPI Integration**: Seamless integration with jvspatial Server
- **Background Execution**: Thread-based execution with concurrency control
- **Rich Monitoring**: Built-in APIs for status, metrics, and job history
- **Error Handling**: Comprehensive error tracking with retry mechanisms
- **Type Safe**: Full type annotations and Pydantic validation

## Installation

```bash
# Install with scheduler support
pip install jvspatial[scheduler]

# Or install the schedule package separately
pip install schedule>=1.2.0 psutil python-dotenv
```

## Quick Start

### 1. Define Node Entities (Entity-Centric Pattern)

```python
from jvspatial.core import Node
from jvspatial.api.scheduler import on_schedule
from datetime import datetime
from typing import Optional

# Define entities for job tracking
class ScheduledJob(Object):
    """Entity representing scheduled job execution records."""
    job_name: str = ""
    execution_time: datetime = datetime.now()
    status: str = "pending"  # pending, completed, failed
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None

class SystemMetrics(Object):
    """Entity for system metrics collection."""
    timestamp: datetime = datetime.now()
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    active_jobs: int = 0
```

### 2. Create Scheduled Functions

```python
# Basic scheduled function with entity creation
@on_schedule("every 30 minutes", description="System cleanup with job tracking")
async def cleanup_system() -> None:
    """Clean up system and create job record."""
    start_time = datetime.now()

    try:
        # Perform cleanup logic
        cleanup_count = perform_cleanup_work()

        # Create success record
        await ScheduledJob.create(
            job_name="system_cleanup",
            execution_time=start_time,
            status="completed",
            duration_seconds=(datetime.now() - start_time).total_seconds()
        )

print(f"Cleanup completed: {cleanup_count} items processed")

    except Exception as e:
        # Create error record
        await ScheduledJob.create(
            job_name="system_cleanup",
            execution_time=start_time,
            status="failed",
            error_message=str(e),
            duration_seconds=(datetime.now() - start_time).total_seconds()
        )
        raise

# Async function with MongoDB-style queries
@on_schedule("every 5 minutes", retry_count=2, description="Collect system metrics")
async def collect_metrics() -> None:
    """Collect system metrics with entity queries."""
    import psutil

    # Get system metrics
    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()

    # Count active jobs using MongoDB-style query
    active_jobs_list = await ScheduledJob.find({
        "context.status": {"$in": ["pending", "running"]}
    })
    active_jobs = len(active_jobs_list)

    # Create metrics record
    await SystemMetrics.create(
        timestamp=datetime.now(),
        cpu_usage=cpu_percent,
        memory_usage=memory.percent,
        active_jobs=active_jobs
    )

print(f"Metrics: CPU {cpu_percent:.1f}%, Memory {memory.percent:.1f}%")
```

### 3. Server Integration with Monitoring APIs

```python
from jvspatial.api import Server, endpoint
from jvspatial.api.scheduler import register_scheduled_tasks
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment configuration (jvspatial pattern)
load_dotenv()

# Create server with scheduler enabled
server = Server(
    title="My Scheduled App",
    description="Application with integrated scheduler",
    version="1.0.0",
    scheduler_enabled=True,
    scheduler_interval=1,  # Check every second
    scheduler_timezone="UTC",
    # Development settings
    debug=True,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Register all decorated scheduled tasks
if hasattr(server, 'scheduler_service') and server.scheduler_service:
    register_scheduled_tasks(server.scheduler_service)
print("Scheduled tasks registered")

# Add monitoring endpoints following jvspatial patterns
@endpoint("/api/scheduler/status", methods=["GET"])
async def get_scheduler_status() -> Dict[str, Any]:
    """Get scheduler status with entity-centric job statistics."""
    if not hasattr(server, 'scheduler_service') or not server.scheduler_service:
        return {"error": "Scheduler not available", "status": "disabled"}

    # Get scheduler status
    status = server.scheduler_service.get_status()

    # Get job statistics using entity queries
    total_jobs_list = await ScheduledJob.find({})
    total_jobs = len(total_jobs_list)

    completed_jobs_list = await ScheduledJob.find({"context.status": "completed"})
    completed_jobs = len(completed_jobs_list)

    failed_jobs_list = await ScheduledJob.find({"context.status": "failed"})
    failed_jobs = len(failed_jobs_list)

    return {
        "scheduler": status,
        "job_statistics": {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "success_rate": (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0
        },
        "timestamp": datetime.now().isoformat()
    }

@endpoint("/api/scheduler/jobs/recent", methods=["GET"])
async def get_recent_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    hours: int = 24
) -> Dict[str, Any]:
    """Get recent job executions with MongoDB-style filtering."""
    # Build query with proper MongoDB syntax
    cutoff_time = datetime.now().timestamp() - (hours * 3600)
    query = {"context.execution_time": {"$gte": cutoff_time}}

    if status:
        query["context.status"] = status

    # Execute entity-centric query
    recent_jobs = await ScheduledJob.find(query)
    sorted_jobs = sorted(recent_jobs, key=lambda x: x.execution_time, reverse=True)[:limit]

    return {
        "jobs": [
            {
                "id": job.id,
                "job_name": job.job_name,
                "status": job.status,
                "execution_time": job.execution_time.isoformat(),
                "duration_seconds": job.duration_seconds,
                "error_message": job.error_message
            }
            for job in sorted_jobs
        ],
        "total_found": len(recent_jobs),
        "filters": {"status": status, "hours_back": hours}
    }

# Run the server
if __name__ == "__main__":
    server.run(host="0.0.0.0", port=8000)
```

### 4. Usage Examples

After running the server, you can monitor scheduled jobs:

```bash
# Get scheduler status and statistics
curl http://localhost:8000/api/scheduler/status

# Get recent job executions
curl http://localhost:8000/api/scheduler/jobs/recent

# Get only failed jobs from last 6 hours
curl "http://localhost:8000/api/scheduler/jobs/recent?status=failed&hours=6&limit=20"
```

## API Reference

### `@on_schedule(schedule, **options)` Decorator

The main decorator for scheduling functions with comprehensive configuration options.

**Parameters:**
- `schedule` (str): Schedule specification using natural language
- `task_id` (str, optional): Unique identifier (defaults to `module.function_name`)
- `enabled` (bool): Enable task by default (default: `True`)
- `max_concurrent` (int): Maximum concurrent executions (default: `1`)
- `timeout_seconds` (int, optional): Task timeout in seconds
- `retry_count` (int): Number of retries on failure (default: `0`)
- `description` (str, optional): Human-readable task description

**Schedule Format Examples:**
```python
# Time intervals
@on_schedule("every 30 seconds")
@on_schedule("every 5 minutes")
@on_schedule("every 2 hours")

# Daily scheduling
@on_schedule("daily at 14:30")
@on_schedule("every day at 09:00")

# Weekly scheduling
@on_schedule("weekly")
@on_schedule("weekly on monday")
@on_schedule("every monday at 09:00")
@on_schedule("every friday at 17:00")

# Range scheduling
@on_schedule("every 5 to 10 minutes")  # Random interval
```

### Configuration Examples

```python
# Basic task
@on_schedule("every 1 hour", description="Hourly cleanup")
async def cleanup_task():
    pass

# Advanced configuration
@on_schedule(
    "every 30 minutes",
    task_id="data_processor",
    max_concurrent=2,
    timeout_seconds=300,
    retry_count=3,
    description="Process pending data with retries"
)
async def process_data():
    pass

# Walker execution pattern
@on_schedule("every 15 minutes", description="Execute data processing walker")
async def execute_data_walker():
    """Schedule walker execution with job tracking."""
    from myapp.walkers import DataProcessingWalker

    start_time = datetime.now()
    try:
        # Execute walker
        walker = DataProcessingWalker()
        result = await walker.spawn()

        # Create success record
        await ScheduledJob.create(
            job_name="data_walker",
            execution_time=start_time,
            status="completed",
            duration_seconds=(datetime.now() - start_time).total_seconds()
        )

    except Exception as e:
        # Create error record
        await ScheduledJob.create(
            job_name="data_walker",
            execution_time=start_time,
            status="failed",
            error_message=str(e)
        )
        raise
```

### MongoDB-Style Query Examples

```python
# Complex job queries in scheduled functions
@on_schedule("every 10 minutes")
async def analyze_job_patterns():
    """Analyze job execution patterns using entity queries."""

    # Find recent failed jobs
    recent_failures = await ScheduledJob.find({
        "$and": [
            {"context.status": "failed"},
            {"context.execution_time": {"$gte": datetime.now().timestamp() - 3600}}
        ]
    })

    # Find jobs by pattern
    cleanup_jobs = await ScheduledJob.find({
        "context.job_name": {"$regex": "cleanup", "$options": "i"}
    })

    # Count jobs by status
    completed_list = await ScheduledJob.find({"context.status": "completed"})
    failed_list = await ScheduledJob.find({"context.status": "failed"})
    total_list = await ScheduledJob.find({})

    job_counts = {
        "completed": len(completed_list),
        "failed": len(failed_list),
        "total": len(total_list)
    }

    # Find slow jobs
    slow_jobs = await ScheduledJob.find({
        "context.duration_seconds": {"$gt": 300}  # > 5 minutes
    })
```

## Advanced Examples

### Dynamic Scheduling with Conditional Logic

```python
@on_schedule("every 1 hour", description="Adaptive data processing")
async def adaptive_processor():
    """Adjust processing frequency based on system load."""

    # Get recent system metrics
    metrics_list = await SystemMetrics.find({
        "$and": [
            {"context.timestamp": {"$gte": datetime.now().timestamp() - 300}},
            {"context.metric_type": "cpu_usage"}
        ]
    })
    metrics = metrics_list[0] if metrics_list else None

    if metrics and metrics.value > 80:
        logger.warning("🔥 High CPU usage detected, skipping intensive processing")
        return

    # Check for recent failures
    recent_failures_list = await ScheduledJob.find({
        "$and": [
            {"context.status": "failed"},
            {"context.execution_time": {"$gte": datetime.now().timestamp() - 3600}}
        ]
    })
    recent_failures = len(recent_failures_list)

    if recent_failures > 5:
        logger.error("⚠️ Too many recent failures, pausing processing")
        await create_alert("High failure rate detected")
        return

    # Execute processing
    await process_data_batch()


@on_schedule("every 5 minutes", description="System health monitoring")
async def system_health_check():
    """Monitor system health and create alerts."""
    import psutil

    # Collect system metrics
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    disk_info = psutil.disk_usage('/')

    # Store metrics
    timestamp = datetime.now()

    await SystemMetrics.create(
        metric_type="cpu_usage",
        value=cpu_percent,
        timestamp=timestamp
    )

    await SystemMetrics.create(
        metric_type="memory_usage",
        value=memory_info.percent,
        timestamp=timestamp
    )

    await SystemMetrics.create(
        metric_type="disk_usage",
        value=disk_info.percent,
        timestamp=timestamp
    )

    # Check thresholds and create alerts
    if cpu_percent > 90:
        logger.critical("🚨 CPU usage critical: {cpu_percent}%")
        await create_alert("Critical CPU usage", {"cpu_percent": cpu_percent})

    if memory_info.percent > 85:
        logger.warning("⚠️ Memory usage high: {memory_info.percent}%")
        await create_alert("High memory usage", {"memory_percent": memory_info.percent})


@on_schedule("daily at 02:00", description="Cleanup old records")
async def cleanup_old_records():
    """Clean up old job records and metrics."""

    # Calculate cutoff dates
    now = datetime.now()
    job_cutoff = now - timedelta(days=30)  # Keep 30 days of job records
    metrics_cutoff = now - timedelta(days=7)  # Keep 7 days of metrics

    # Delete old job records
    old_jobs = await ScheduledJob.delete_many({
        "context.execution_time": {"$lt": job_cutoff.timestamp()}
    })

    # Delete old metrics
    old_metrics = await SystemMetrics.delete_many({
        "context.timestamp": {"$lt": metrics_cutoff.timestamp()}
    })

    logger.info(f"🧹 Cleanup completed: {old_jobs.deleted_count} jobs, {old_metrics.deleted_count} metrics")

    # Record cleanup job
    await ScheduledJob.create(
        job_name="cleanup_old_records",
        execution_time=now,
        status="completed",
        metadata={
            "deleted_jobs": old_jobs.deleted_count,
            "deleted_metrics": old_metrics.deleted_count
        }
    )


async def create_alert(message: str, metadata: dict = None):
    """Create system alert record."""
    from myapp.entities import Alert

    await Alert.create(
        message=message,
        timestamp=datetime.now(),
        severity="warning",
        metadata=metadata or {}
    )
```

### Error Handling and Recovery Patterns

```python
@on_schedule(
    "every 30 minutes",
    retry_count=3,
    timeout_seconds=600,
    description="Resilient data sync with automatic recovery"
)
async def resilient_data_sync():
    """Data synchronization with comprehensive error handling."""

    sync_id = str(uuid.uuid4())
    start_time = datetime.now()

    try:
logger.info(f"Starting data sync {sync_id}")

        # Check for existing sync operations
        existing_sync_list = await ScheduledJob.find({
            "$and": [
                {"context.job_name": "resilient_data_sync"},
                {"context.status": "running"},
                {"context.execution_time": {"$gte": (datetime.now() - timedelta(hours=1)).timestamp()}}
            ]
        })
        existing_sync = existing_sync_list[0] if existing_sync_list else None

        if existing_sync:
logger.warning(f"Sync already running, skipping {sync_id}")
            return

        # Create running job record
        job_record = await ScheduledJob.create(
            job_name="resilient_data_sync",
            execution_time=start_time,
            status="running",
            metadata={"sync_id": sync_id}
        )

        # Execute sync operations
        results = await perform_data_sync()

        # Update success record
        await ScheduledJob.update_one(
            {"_id": job_record.id},
            {
                "$set": {
                    "context.status": "completed",
                    "context.duration_seconds": (datetime.now() - start_time).total_seconds(),
                    "context.metadata.results": results
                }
            }
        )

logger.info(f"Data sync {sync_id} completed successfully")

    except asyncio.TimeoutError:
logger.error(f"Data sync {sync_id} timed out")
        await update_job_status(job_record.id, "timeout", str(e))
        raise

    except Exception as e:
logger.error(f"Data sync {sync_id} failed: {str(e)}")
        await update_job_status(job_record.id, "failed", str(e))

        # Check failure patterns for circuit breaker
        recent_failures_list = await ScheduledJob.find({
            "$and": [
                {"context.job_name": "resilient_data_sync"},
                {"context.status": {"$in": ["failed", "timeout"]}},
                {"context.execution_time": {"$gte": (datetime.now() - timedelta(hours=2)).timestamp()}}
            ]
        })
        recent_failures = len(recent_failures_list)

        if recent_failures >= 3:
logger.critical("Circuit breaker activated for data sync")
            await create_alert(
                "Data sync circuit breaker activated",
                {"failure_count": recent_failures}
            )

        raise


async def update_job_status(job_id: str, status: str, error_message: str = None):
    """Update job record with final status."""
    update_data = {
        "$set": {
            "context.status": status,
            "context.completed_at": datetime.now().timestamp()
        }
    }

    if error_message:
        update_data["$set"]["context.error_message"] = error_message

    await ScheduledJob.update_one({"_id": job_id}, update_data)


async def perform_data_sync() -> dict:
    """Simulate data synchronization operation."""
    await asyncio.sleep(2)  # Simulate work
    return {
        "records_processed": 1000,
        "records_updated": 150,
        "errors": 0
    }
```

## Best Practices

### 1. **Use Entity-Centric Design**

Always leverage jvspatial's Node entities for structured data storage and retrieval:

```python
# Good: Use entities for structured data
class JobResult(Object):
    job_name: str
    execution_time: datetime
    status: str
    results: dict = {}
    error_message: Optional[str] = None

@on_schedule("every 30 minutes")
async def process_with_entities():
    result = await JobResult.create(
        job_name="data_processor",
        execution_time=datetime.now(),
        status="running"
    )
    # Process and update...

# Bad: Direct database operations or unstructured storage
```

### 2. **Implement Proper Error Handling**

```python
@on_schedule(
    "every 15 minutes",
    retry_count=2,
    timeout_seconds=300,
    description="Robust task with proper error handling"
)
async def robust_task():
    start_time = datetime.now()
    job_id = None

    try:
        # Create job tracking record
        job_record = await ScheduledJob.create(
            job_name="robust_task",
            execution_time=start_time,
            status="running"
        )
        job_id = job_record.id

        # Execute business logic
        result = await execute_business_logic()

        # Update success
        await ScheduledJob.update_one(
            {"_id": job_id},
            {"$set": {"context.status": "completed", "context.result": result}}
        )

logger.info(f"Task completed successfully")

    except Exception as e:
        # Update failure record
        if job_id:
            await ScheduledJob.update_one(
                {"_id": job_id},
                {"$set": {"context.status": "failed", "context.error_message": str(e)}}
            )

logger.error(f"Task failed: {str(e)}")
        raise  # Re-raise for scheduler retry logic
```

### 3. **Use MongoDB-Style Queries Effectively**

```python
# Complex queries with proper indexing considerations
@on_schedule("every 5 minutes")
async def monitor_system():
    # Query with time-based filtering (ensure timestamp indexes)
    recent_jobs = await ScheduledJob.find({
        "$and": [
            {"context.execution_time": {"$gte": datetime.now().timestamp() - 3600}},
            {"context.status": {"$in": ["failed", "timeout"]}}
        ]
    })

    # Aggregation for metrics
    failure_rate = await ScheduledJob.aggregate([
        {"$match": {"context.execution_time": {"$gte": datetime.now().timestamp() - 86400}}},
        {"$group": {
            "_id": "$context.status",
            "count": {"$sum": 1}
        }}
    ])
```

### 4. **Implement Circuit Breaker Pattern**

```python
@on_schedule("every 10 minutes", description="Task with circuit breaker")
async def task_with_circuit_breaker():
    # Check recent failures
    failure_list = await ScheduledJob.find({
        "$and": [
            {"context.job_name": "task_with_circuit_breaker"},
            {"context.status": "failed"},
            {"context.execution_time": {"$gte": (datetime.now() - timedelta(hours=1)).timestamp()}}
        ]
    })
    failure_count = len(failure_list)

    if failure_count >= 3:
        logger.warning("🔒 Circuit breaker open, skipping execution")
        return

    # Execute task logic...
```

### 5. **Use Descriptive Logging with Emoji**

Follow jvspatial's logging conventions for better visibility:

```python
@on_schedule("every 1 hour", description="Data cleanup task")
async def cleanup_task():
    logger.info("🧹 Starting cleanup process")

    try:
        deleted_count = await cleanup_old_data()
        logger.info(f"✅ Cleanup completed: {deleted_count} records removed")

    except Exception as e:
        logger.error(f"❌ Cleanup failed: {str(e)}")
        logger.critical(f"🚨 Critical cleanup failure requires attention")
        raise
```

## Tips

### Performance Optimization

- **Use proper indexes**: Ensure timestamp and status fields are indexed for query performance
- **Batch operations**: Process data in batches to avoid memory issues
- **Async operations**: Always use async/await for I/O operations
- **Connection pooling**: Let jvspatial handle database connection pooling

### Monitoring and Alerting

- **Track execution metrics**: Record duration, success rate, and error patterns
- **Set up alerting**: Use entity-based alerting for failure thresholds
- **Dashboard integration**: Query scheduler data for operational dashboards
- **Health checks**: Implement scheduled health checks for critical services

### Development Workflow

- **Test scheduling logic**: Write unit tests for scheduled functions
- **Use development schedules**: Use shorter intervals during development
- **Mock external dependencies**: Test scheduler logic independently
- **Graceful degradation**: Handle external service failures gracefully

### Production Deployment

- **Resource limits**: Configure appropriate timeout and concurrency limits
- **Monitoring**: Set up comprehensive logging and monitoring
- **Backup strategies**: Implement backup for critical scheduled data
- **Rollback plans**: Have rollback strategies for scheduler updates