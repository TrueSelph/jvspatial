"""Dynamic Scheduler Example

This example demonstrates advanced scheduler features including:
1. Dynamic task registration
2. Task dependencies
3. Runtime task configuration
4. Task chaining
5. Event-driven scheduling
6. Error handling and retries

The example simulates a data processing pipeline with multiple stages,
showing how to coordinate dependent tasks and handle failures gracefully.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, cast

from jvspatial.api import Server, endpoint

try:
    from jvspatial.api.integrations.scheduler.decorators import on_schedule
except ImportError:
    on_schedule = None
from jvspatial.core import Object

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Data models
class DataJob(Object):
    """Data processing job record."""

    job_type: str = ""  # collect, process, analyze, report
    status: str = "pending"
    input_data: Optional[str] = None
    output_data: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    @classmethod
    def _get_top_level_fields(cls) -> set:
        """Return all fields that are stored at top level in the database."""
        return {
            "job_type",
            "status",
            "input_data",
            "output_data",
            "started_at",
            "completed_at",
            "error_message",
            "retry_count",
            "max_retries",
        }


# Task stages
@on_schedule("every 5 minutes", task_id="data_collector")
async def collect_data():
    """Simulated data collection task."""
    logger.info("📥 Starting data collection...")

    job = None

    try:
        # Create a new job record
        job = await DataJob.create(
            job_type="collect",
            status="running",
            started_at=datetime.now(),
        )

        # Simulate data collection
        await asyncio.sleep(2)
        job.output_data = "collected_data_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        job.status = "completed"
        job.completed_at = datetime.now()
        await job.save()

        logger.info(f"✅ Data collection completed: {job.output_data}")
        return job.output_data

    except Exception as e:
        if job:
            job.status = "failed"
            job.error_message = str(e)
            await job.save()
        logger.error(f"❌ Data collection failed: {e}")
        raise


@on_schedule(
    "every 5 minutes",
    task_id="data_processor",
)
async def process_data():
    """Process collected data with retry support."""
    logger.info("⚙️ Starting data processing...")

    # Find completed collection jobs
    collection_jobs = await DataJob.find({"job_type": "collect", "status": "completed"})

    for collection_job in collection_jobs:
        if not collection_job.output_data:
            continue

        # Check if already processed
        existing_list = await DataJob.find(
            {
                "job_type": "process",
                "input_data": collection_job.output_data,
            }
        )
        if existing_list:
            continue

        job = None
        try:
            # Create processing job
            job = await DataJob.create(
                job_type="process",
                status="running",
                input_data=collection_job.output_data,
                started_at=datetime.now(),
            )

            # Simulate processing
            await asyncio.sleep(3)
            if job.retry_count == 0 and datetime.now().second % 3 == 0:
                # Simulate occasional first-try failures
                raise Exception("Simulated processing error")

            job.output_data = f"processed_{job.input_data}"
            job.status = "completed"
            job.completed_at = datetime.now()
            await job.save()

            logger.info(f"✅ Data processing completed: {job.output_data}")

        except Exception as e:
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.retry_count += 1
                if job.retry_count < job.max_retries:
                    job.status = "pending"  # Will be retried
                await job.save()

            logger.error(f"❌ Processing failed: {e}")
            if job and job.retry_count >= job.max_retries:
                logger.error(f"🔴 Max retries ({job.max_retries}) reached")
            raise


@on_schedule(
    "every 10 minutes",
    task_id="data_analyzer",
)
async def analyze_data():
    """Analyze processed data and generate insights."""
    logger.info("🔍 Starting data analysis...")

    # Find completed processing jobs
    process_jobs = await DataJob.find({"job_type": "process", "status": "completed"})

    for process_job in process_jobs:
        if not process_job.output_data:
            continue

        # Check if already analyzed
        existing_list = await DataJob.find(
            {
                "job_type": "analyze",
                "input_data": process_job.output_data,
            }
        )
        if existing_list:
            continue

        job = None
        try:
            # Create analysis job
            job = await DataJob.create(
                job_type="analyze",
                status="running",
                input_data=process_job.output_data,
                started_at=datetime.now(),
            )

            # Simulate analysis
            await asyncio.sleep(2)
            job.output_data = f"analysis_{job.input_data}"
            job.status = "completed"
            job.completed_at = datetime.now()
            await job.save()

            logger.info(f"✅ Data analysis completed: {job.output_data}")

        except Exception as e:
            if job:
                job.status = "failed"
                job.error_message = str(e)
                await job.save()
            logger.error(f"❌ Analysis failed: {e}")
            raise


@on_schedule(
    "every 15 minutes",
    task_id="report_generator",
)
async def generate_report():
    """Generate reports from analyzed data."""
    logger.info("📊 Starting report generation...")

    # Find completed analysis jobs
    analysis_jobs = await DataJob.find({"job_type": "analyze", "status": "completed"})

    # Group by date for reporting
    for analysis_job in analysis_jobs:
        if not analysis_job.output_data:
            continue

        # Check if already reported
        existing_list = await DataJob.find(
            {
                "job_type": "report",
                "input_data": analysis_job.output_data,
            }
        )
        if existing_list:
            continue

        job = None
        try:
            # Create report job
            job = await DataJob.create(
                job_type="report",
                status="running",
                input_data=analysis_job.output_data,
                started_at=datetime.now(),
            )

            # Simulate report generation
            await asyncio.sleep(1)
            job.output_data = f"report_{job.input_data}"
            job.status = "completed"
            job.completed_at = datetime.now()
            await job.save()

            logger.info(f"✅ Report generation completed: {job.output_data}")

        except Exception as e:
            if job:
                job.status = "failed"
                job.error_message = str(e)
                await job.save()
            logger.error(f"❌ Report generation failed: {e}")
            raise


# Add monitoring endpoints
@endpoint("/api/scheduler/jobs/stats", methods=["GET"])
async def get_job_statistics() -> Dict:
    """Get statistics about data processing jobs."""
    stats: Dict[str, Any] = {
        "total": 0,
        "by_type": {},
        "by_status": {},
        "error_rate": 0.0,
        "average_duration": {},
    }

    # Get all jobs
    jobs = await DataJob.all()
    stats["total"] = len(jobs)

    # Calculate statistics
    completed_jobs = 0
    failed_jobs = 0
    durations: Dict[str, List[float]] = {}

    for job in jobs:
        # Count by type
        by_type = cast(Dict[str, int], stats["by_type"])
        if job.job_type not in by_type:
            by_type[job.job_type] = 0
        by_type[job.job_type] += 1

        # Count by status
        by_status = cast(Dict[str, int], stats["by_status"])
        if job.status not in by_status:
            by_status[job.status] = 0
        by_status[job.status] += 1

        # Track success/failure
        if job.status == "completed":
            completed_jobs += 1
        elif job.status == "failed":
            failed_jobs += 1

        # Calculate duration for completed jobs
        if job.status == "completed" and job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            job_durations = durations.get(job.job_type, [])
            durations[job.job_type] = job_durations
            job_durations.append(duration)

    # Calculate error rate
    total_finished = completed_jobs + failed_jobs
    if total_finished > 0:
        stats["error_rate"] = round(failed_jobs / total_finished * 100, 2)

    # Calculate average durations
    for job_type, duration_list in durations.items():
        if duration_list:
            avg_durations = cast(Dict[str, float], stats["average_duration"])
            avg_durations[job_type] = round(sum(duration_list) / len(duration_list), 2)

    return {
        "timestamp": datetime.now().isoformat(),
        "statistics": stats,
    }


# Create and configure server
server = Server(
    title="Dynamic Scheduler Demo",
    description="Advanced scheduler features demonstration",
    version="1.0.0",
    scheduler_enabled=True,
    scheduler_interval=1,  # Check every second
    db_type="json",  # Use JSON file storage for demo
)


@server.on_startup
async def cleanup_old_data():
    """Remove old job records on startup."""
    try:
        cutoff = datetime.now() - timedelta(hours=24)
        old_jobs = await DataJob.find(
            {"context.completed_at": {"$lt": cutoff.timestamp()}}
        )
        for job in old_jobs:
            await job.delete()
        logger.info(f"🧹 Cleaned up {len(old_jobs)} old job records")
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")


if __name__ == "__main__":
    print("🚀 Starting Dynamic Scheduler Demo")
    print("\nFeatures demonstrated:")
    print("• Dynamic task scheduling")
    print("• Task dependencies and chaining")
    print("• Automatic retries")
    print("• Job tracking and persistence")
    print("• Error handling patterns")
    print("• Performance monitoring")
    print("\nEndpoints:")
    print("📊 Job Statistics: http://localhost:8000/api/scheduler/jobs/stats")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("\nPress Ctrl+C to exit")

    server.run(port=8000, reload=False)
