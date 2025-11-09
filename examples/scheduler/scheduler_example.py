"""Example usage of the jvspatial scheduler integration.

This example demonstrates how to integrate the scheduler service with
a jvspatial Server and use the @on_schedule decorator to schedule tasks.

Follows jvspatial patterns from QUICKSTART.md including:
- Entity-centric design
- Proper endpoint decorators
- MongoDB-style queries
- Type annotations
- Error handling
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import jvspatial Server and endpoint decorator
from jvspatial.api import Server, endpoint

# Import scheduler components (will handle optional dependency gracefully)
try:
    from jvspatial.api.integrations.scheduler.decorators import (
        on_schedule,
        register_scheduled_tasks,
    )
    from jvspatial.api.integrations.scheduler.models import (
        ScheduledTask,
        SchedulerConfig,
    )
    from jvspatial.api.integrations.scheduler.scheduler import (
        SCHEDULE_AVAILABLE,
        SchedulerService,
    )
except ImportError:
    SCHEDULE_AVAILABLE = False
    on_schedule = None  # type: ignore[assignment,misc]
    register_scheduled_tasks = None  # type: ignore[assignment,misc]
    SchedulerConfig = None  # type: ignore[assignment,misc]
    SchedulerService = None  # type: ignore[assignment,misc]
    ScheduledTask = None  # type: ignore[assignment,misc]
from jvspatial.core import Object

# Configure logging to see scheduler activity
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define Node entities following jvspatial patterns
class ScheduledJob(Object):
    """Object representing a scheduled job execution record."""

    job_name: str = ""
    execution_time: datetime = datetime.now()
    status: str = "pending"  # pending, completed, failed
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None

    @classmethod
    def _get_top_level_fields(cls) -> set:
        """Return all fields that are stored at top level in the database."""
        return {
            "job_name",
            "execution_time",
            "status",
            "duration_seconds",
            "error_message",
        }


class SystemMetrics(Object):
    """Object representing system metrics snapshot."""

    timestamp: datetime = datetime.now()
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    active_connections: int = 0


# Example 1: Basic scheduled function with entity persistence
@on_schedule("every 30 seconds", description="Log current time and create job record")
async def log_current_time() -> None:
    """Log the current time and create a job record every 30 seconds.

    Follows jvspatial entity-centric patterns by creating Node records.
    """
    current_time = datetime.now()
    logger.info(f"⏰ Current time: {current_time}")

    # Create entity record using jvspatial entity-centric pattern
    job_record = await ScheduledJob.create(
        job_name="time_logger",
        execution_time=current_time,
        status="completed",
        duration_seconds=0.1,
    )

    logger.info(f"📝 Created job record: {job_record.id}")


# Example 2: Async scheduled function with MongoDB-style queries
@on_schedule(
    "every 2 minutes",
    task_id="async_cleanup",
    max_concurrent=1,
    timeout_seconds=60,
    retry_count=2,
    description="Async cleanup task with entity queries",
)
async def async_cleanup_task() -> None:
    """Perform cleanup using entity-centric queries.

    Demonstrates MongoDB-style query patterns from QUICKSTART.md.
    """
    start_time = datetime.now()
    logger.info("🧹 Starting async cleanup task...")

    try:
        # Use MongoDB-style queries to find old job records
        cutoff_time = datetime.now().timestamp() - (24 * 3600)  # 24 hours ago
        old_jobs = await ScheduledJob.find(
            {
                "$and": [
                    {"context.status": "completed"},
                    {"context.execution_time": {"$lt": cutoff_time}},
                ]
            }
        )

        # Clean up old completed jobs
        cleanup_count = 0
        for job in old_jobs[:10]:  # Limit to 10 per run
            await job.delete()
            cleanup_count += 1

        duration = (datetime.now() - start_time).total_seconds()

        # Create completion record
        await ScheduledJob.create(
            job_name="cleanup_task",
            execution_time=start_time,
            status="completed",
            duration_seconds=duration,
        )

        logger.info(
            f"✅ Cleanup completed: removed {cleanup_count} old records in {duration:.2f}s"
        )

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = str(e)

        # Create error record
        await ScheduledJob.create(
            job_name="cleanup_task",
            execution_time=start_time,
            status="failed",
            duration_seconds=duration,
            error_message=error_msg,
        )

        logger.error(f"❌ Cleanup failed: {error_msg}")
        raise


# Example 3: System metrics collection with error handling
@on_schedule("every 5 minutes", retry_count=2, description="Collect system metrics")
async def collect_system_metrics() -> None:
    """Collect and store system metrics with comprehensive error handling.

    Demonstrates proper error handling patterns from QUICKSTART.md.
    """
    import random

    import psutil

    start_time = datetime.now()

    try:
        # Collect system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Count active scheduled jobs (entity-centric query)
        active_jobs_list = await ScheduledJob.find(
            {"context.status": {"$in": ["pending", "running"]}}
        )
        active_jobs = len(active_jobs_list)

        # Create metrics record
        metrics = await SystemMetrics.create(
            timestamp=start_time,
            cpu_usage=cpu_percent,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            active_connections=active_jobs,
        )

        # Create job completion record
        duration = (datetime.now() - start_time).total_seconds()
        await ScheduledJob.create(
            job_name="metrics_collector",
            execution_time=start_time,
            status="completed",
            duration_seconds=duration,
        )

        logger.info(
            f"📊 Metrics collected: CPU {cpu_percent:.1f}%, Memory {memory.percent:.1f}%, Disk {disk.percent:.1f}%"
        )

        # Simulate occasional failures for demonstration
        if random.random() < 0.1:  # 10% failure rate
            raise Exception("Simulated metrics collection failure")

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        error_msg = str(e)

        # Create error record following error handling patterns
        await ScheduledJob.create(
            job_name="metrics_collector",
            execution_time=start_time,
            status="failed",
            duration_seconds=duration,
            error_message=error_msg,
        )

        logger.error(f"❌ Metrics collection failed: {error_msg}")
        raise


def create_scheduler_server() -> Server:
    """Create a jvspatial Server with scheduler integration.

    Follows jvspatial QUICKSTART patterns for server setup with:
    - Proper server configuration
    - Environment-based database configuration
    - Scheduler integration
    - CORS and documentation setup
    """
    if not SCHEDULE_AVAILABLE:
        logger.error("❌ Schedule package not available - cannot run scheduler example")
        raise ImportError("Please install: pip install schedule>=1.2.0")

    # Create jvspatial server following QUICKSTART patterns
    server = Server(
        title="JVspatial Scheduler Integration Example",
        description="Demonstrates scheduler integration with entity-centric patterns",
        version="1.0.0",
        host="0.0.0.0",
        port=8000,
        debug=True,  # Enable for development
        # Scheduler configuration
        scheduler_enabled=True,
        scheduler_interval=1,  # Check every second for pending jobs
        scheduler_timezone="UTC",
        # API documentation
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Register all decorated tasks with the scheduler in a startup hook
    # Note: scheduler_service needs to be manually initialized if not automatically created
    @server.on_startup
    async def register_scheduler_tasks():
        """Register scheduled tasks on server startup."""
        if hasattr(server, "scheduler_service") and server.scheduler_service:
            await register_scheduled_tasks(server.scheduler_service)
            logger.info("✅ Scheduled tasks registered with server")
        else:
            logger.warning(
                "⚠️  Server scheduler service not available - tasks may not be registered automatically"
            )
            logger.info("💡 You may need to manually initialize the scheduler service")

    # Add monitoring endpoints following jvspatial QUICKSTART patterns

    @endpoint("/api/scheduler/status", methods=["GET"])
    async def get_scheduler_status() -> Dict[str, Any]:
        """Get current scheduler status with entity-centric data.

        Returns:
            Dictionary containing scheduler status and job statistics
        """
        if not hasattr(server, "scheduler_service") or not server.scheduler_service:
            return {"error": "Scheduler service not available", "status": "disabled"}

        # Get scheduler status
        status = server.scheduler_service.get_status()

        # Get job statistics using entity-centric queries
        total_jobs_list = await ScheduledJob.find()
        total_jobs = len(total_jobs_list)
        completed_jobs_list = await ScheduledJob.find({"context.status": "completed"})
        completed_jobs = len(completed_jobs_list)
        failed_jobs_list = await ScheduledJob.find({"context.status": "failed"})
        failed_jobs = len(failed_jobs_list)

        # Recent jobs (last 24 hours)
        recent_cutoff = datetime.now().timestamp() - (24 * 3600)
        recent_jobs_list = await ScheduledJob.find(
            {"context.execution_time": {"$gte": recent_cutoff}}
        )
        recent_jobs = len(recent_jobs_list)

        return {
            "scheduler": status,
            "job_statistics": {
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "recent_jobs_24h": recent_jobs,
                "success_rate": (
                    (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0
                ),
            },
            "timestamp": datetime.now().isoformat(),
        }

    @endpoint("/api/scheduler/tasks", methods=["GET"])
    async def get_scheduled_tasks() -> Dict[str, Any]:
        """Get list of scheduled tasks with execution history.

        Returns:
            Dictionary containing task list and metadata
        """
        if not hasattr(server, "scheduler_service") or not server.scheduler_service:
            return {"tasks": [], "error": "Scheduler service not available"}

        tasks = server.scheduler_service.list_tasks()

        task_data = []
        for task in tasks:
            # Get recent executions for this task using MongoDB-style query
            recent_executions = await ScheduledJob.find(
                {
                    "$and": [
                        {"context.job_name": task.task_id},
                        {
                            "context.execution_time": {
                                "$gte": datetime.now().timestamp() - 3600
                            }
                        },  # Last hour
                    ]
                }
            )

            task_info = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "schedule": task.schedule.schedule_spec,
                "enabled": task.enabled,
                "description": task.description,
                "last_execution": task.last_execution,
                "next_execution": task.next_execution,
                "execution_count": task.execution_count,
                "success_count": task.success_count,
                "failure_count": task.failure_count,
                "recent_executions": len(recent_executions),
            }
            task_data.append(task_info)

        return {
            "tasks": task_data,
            "total_tasks": len(task_data),
            "enabled_tasks": len([t for t in task_data if t["enabled"]]),
            "timestamp": datetime.now().isoformat(),
        }

    @endpoint("/api/scheduler/jobs/recent", methods=["GET"])
    async def get_recent_jobs(
        status: Optional[str] = None, limit: int = 50, hours: int = 24
    ) -> Dict[str, Any]:
        """Get recent job executions with filtering.

        Args:
            status: Filter by job status (completed, failed, pending)
            limit: Maximum number of jobs to return
            hours: Hours back to search

        Returns:
            Dictionary containing recent job executions
        """
        # Build MongoDB-style query
        cutoff_time = datetime.now().timestamp() - (hours * 3600)
        query: Dict[str, Any] = {"context.execution_time": {"$gte": cutoff_time}}

        if status:
            query["context.status"] = status

        # Get recent jobs with entity-centric query
        recent_jobs = await ScheduledJob.find(query)

        # Sort by execution time (most recent first) and limit
        sorted_jobs = sorted(recent_jobs, key=lambda x: x.execution_time, reverse=True)[
            :limit
        ]

        job_data = [
            {
                "id": job.id,
                "job_name": job.job_name,
                "status": job.status,
                "execution_time": job.execution_time.isoformat(),
                "duration_seconds": job.duration_seconds,
                "error_message": job.error_message,
            }
            for job in sorted_jobs
        ]

        return {
            "jobs": job_data,
            "total_found": len(recent_jobs),
            "returned": len(job_data),
            "filters": {"status": status, "hours_back": hours, "limit": limit},
            "timestamp": datetime.now().isoformat(),
        }

    @endpoint("/api/scheduler/tasks/{task_id}/toggle", methods=["POST"])
    async def toggle_task(task_id: str, enable: bool = True) -> Dict[str, Any]:
        """Enable or disable a scheduled task.

        Args:
            task_id: ID of the task to toggle
            enable: True to enable, False to disable

        Returns:
            Dictionary containing operation result
        """
        if not hasattr(server, "scheduler_service") or not server.scheduler_service:
            return {"error": "Scheduler service not available", "success": False}

        try:
            if enable:
                success = server.scheduler_service.enable_task(task_id)
                action = "enabled"
            else:
                success = server.scheduler_service.disable_task(task_id)
                action = "disabled"

            if success:
                return {
                    "success": True,
                    "message": f"Task {task_id} {action} successfully",
                    "task_id": task_id,
                    "enabled": enable,
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                return {
                    "success": False,
                    "error": f"Task {task_id} not found",
                    "task_id": task_id,
                }

        except Exception as e:
            logger.error(f"Error toggling task {task_id}: {e}")
            return {
                "success": False,
                "error": f"Failed to toggle task: {str(e)}",
                "task_id": task_id,
            }

    @endpoint("/api/health", methods=["GET"])
    async def health_check() -> Dict[str, Any]:
        """Comprehensive health check with entity statistics.

        Returns:
            Dictionary containing health status and system metrics
        """
        try:
            # Check scheduler status
            scheduler_status = {
                "available": hasattr(server, "scheduler_service")
                and server.scheduler_service is not None,
                "running": False,
            }

            if scheduler_status["available"]:
                scheduler_status["running"] = server.scheduler_service.is_running  # type: ignore[attr-defined]

            # Get entity counts for health metrics
            job_list = await ScheduledJob.find()
            job_count = len(job_list)
            metrics_list = await SystemMetrics.find()
            metrics_count = len(metrics_list)

            # Recent activity check
            recent_cutoff = datetime.now().timestamp() - 3600  # 1 hour
            recent_activity_list = await ScheduledJob.find(
                {"context.execution_time": {"$gte": recent_cutoff}}
            )
            recent_activity = len(recent_activity_list)

            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "scheduler": scheduler_status,
                "database": {
                    "connected": True,  # If we got here, DB is working
                    "entities": {
                        "scheduled_jobs": job_count,
                        "system_metrics": metrics_count,
                    },
                },
                "activity": {
                    "recent_jobs_1h": recent_activity,
                    "healthy": recent_activity > 0 or job_count == 0,
                },
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    return server


def main() -> None:
    """Run the scheduler example application following jvspatial patterns.

    Demonstrates:
    - Environment-based configuration
    - Proper server startup
    - Error handling patterns
    - Logging with emojis
    """
    try:
        # Load environment variables (QUICKSTART pattern)
        from dotenv import load_dotenv

        load_dotenv()  # Load .env file for database configuration

        server = create_scheduler_server()

        logger.info("🎆 Starting JVspatial Scheduler Example...")
        logger.info(f"📚 API Documentation: http://localhost:8000/docs")
        logger.info(f"📈 Scheduler Status: http://localhost:8000/api/scheduler/status")
        logger.info(f"📝 Task List: http://localhost:8000/api/scheduler/tasks")
        logger.info(f"❤️‍🩹  Health Check: http://localhost:8000/api/health")
        logger.info(f"📅 Recent Jobs: http://localhost:8000/api/scheduler/jobs/recent")

        # Run the server following QUICKSTART patterns
        server.run(
            host="0.0.0.0", port=8000, reload=True  # Auto-reload for development
        )

    except ImportError as e:
        logger.error(f"❌ Required dependencies not available: {e}")
        logger.info("ℹ️ You can install missing dependencies with:")
        logger.info("   pip install schedule>=1.2.0 psutil python-dotenv")
        logger.info(
            "💬 You can still test the scheduler functionality programmatically"
        )

        # Run a simple test without Server
        asyncio.run(test_scheduler_without_server())

    except Exception as e:
        logger.error(f"❌ Server startup failed: {e}")
        raise


async def test_scheduler_without_server() -> None:
    """Test scheduler functionality without Server using entity-centric patterns.

    Demonstrates:
    - Direct scheduler service usage
    - Entity-centric data access
    - Proper async patterns
    - Comprehensive logging
    """
    if not SCHEDULE_AVAILABLE:
        logger.error("❌ Schedule package not available")
        return

    logger.info("🧪 Testing scheduler without Server (programmatic mode)...")

    try:
        # Import here to avoid issues if not available
        from jvspatial.api.integrations.scheduler.models import SchedulerConfig
        from jvspatial.api.integrations.scheduler.scheduler import SchedulerService

        # Create and configure scheduler following QUICKSTART patterns
        config = SchedulerConfig(
            enabled=True, interval=1, timezone="UTC", max_concurrent_tasks=5
        )
        scheduler_service = SchedulerService(config=config)

        # Register decorated tasks
        await register_scheduled_tasks(scheduler_service)

        # Start scheduler
        scheduler_service.start()

        logger.info("✅ Scheduler started successfully")
        logger.info(f"📝 Registered tasks: {len(scheduler_service.list_tasks())}")

        # Display task information
        tasks = scheduler_service.list_tasks()
        for task in tasks:
            logger.info(
                f"   • {task.task_id}: {task.description} ({task.schedule.schedule_spec})"
            )

        # Monitor scheduler activity
        start_time = datetime.now()
        logger.info("📊 Monitoring scheduler activity for 30 seconds...")
        logger.info("⏹️  Press Ctrl+C to stop early")

        # Run for a limited time with periodic status updates
        import time

        for i in range(30):
            time.sleep(1)

            # Show status every 10 seconds
            if (i + 1) % 10 == 0:
                status = scheduler_service.get_status()
                logger.info(
                    f"📊 Status at {i+1}s: "
                    f"{status.get('total_executions', 0)} executions, "
                    f"{status.get('running_tasks', 0)} running tasks"
                )

                # Show recent job count using entity queries
                recent_cutoff = datetime.now().timestamp() - 300  # 5 minutes
                try:
                    recent_jobs_list = await ScheduledJob.find(
                        {"context.execution_time": {"$gte": recent_cutoff}}
                    )
                    recent_jobs = len(recent_jobs_list)
                    logger.info(f"📋 Recent jobs (5min): {recent_jobs}")
                except Exception as e:
                    logger.debug(f"Could not query job entities: {e}")

        # Final statistics
        final_status = scheduler_service.get_status()
        runtime = (datetime.now() - start_time).total_seconds()

        logger.info("🏁 Final Results:")
        logger.info(f"   • Runtime: {runtime:.1f} seconds")
        logger.info(f"   • Total executions: {final_status.get('total_executions', 0)}")
        logger.info(f"   • Success rate: {final_status.get('success_rate', 0):.1%}")

        # Show entity counts if available
        try:
            job_list = await ScheduledJob.find()
            job_count = len(job_list)
            metrics_list = await SystemMetrics.find()
            metrics_count = len(metrics_list)
            logger.info(f"   • Job records created: {job_count}")
            logger.info(f"   • Metrics records: {metrics_count}")
        except Exception as e:
            logger.debug(f"Could not query final entity counts: {e}")

    except KeyboardInterrupt:
        logger.info("⏹️  Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise
    finally:
        logger.info("🛑 Stopping scheduler...")
        if "scheduler_service" in locals():
            scheduler_service.stop()
        logger.info("✅ Scheduler stopped successfully")


if __name__ == "__main__":
    main()
