"""Walker Error Handling Example

Demonstrates error handling for walkers in jvspatial, including:
- Walker execution errors
- Timeout handling
- Node processing errors
- Reporting and recovery strategies
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from pydantic import Field

from jvspatial.core import Node, Root, Walker, on_visit
from jvspatial.exceptions import (
    WalkerExecutionError,
    WalkerTimeoutError,
)


# Define example entities
class Task(Node):
    """Task entity for walker processing."""

    title: str
    status: str = "pending"
    priority: int = Field(1, ge=1, le=5)
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)


class TaskProcessor(Walker):
    """Walker that processes tasks with error handling."""

    timeout_seconds: int = Field(60, description="Maximum execution time in seconds")
    fail_fast: bool = Field(False, description="Whether to stop on first error")

    @on_visit(Task)
    async def process_task(self, here: Task):
        """Process individual task with error handling."""
        try:
            # Simulate external service call
            await self.process_task_with_external_service(here)

            # Update task status
            here.status = "completed"
            await here.save()

            # Report success
            await self.report(
                {
                    "task_completed": {
                        "id": here.id,
                        "title": here.title,
                        "processing_time": "1s",
                    }
                }
            )

        except Exception as e:
            error_report = {
                "error": str(e),
                "task_id": here.id,
                "task_title": here.title,
            }

            await self.report({"task_error": error_report})

            if self.fail_fast:
                raise WalkerExecutionError(
                    walker_class=self.__class__.__name__,
                    reason=f"Task processing failed: {e}",
                    details=error_report,
                )

    async def process_task_with_external_service(self, task: Task):
        """Simulate external service processing with potential failures."""
        # Simulate random processing issues
        if task.priority > 3:
            # Simulate timeout for high-priority tasks
            await asyncio.sleep(2)
            raise WalkerTimeoutError(
                walker_class=self.__class__.__name__,
                timeout_seconds=2,
                details={"task_id": task.id, "task_title": task.title},
            )
        elif task.status == "failed":
            # Simulate processing error
            raise WalkerExecutionError(
                walker_class=self.__class__.__name__,
                reason="Task processing failed",
                details={"node_id": task.id, "node_type": "Task"},
            )
        else:
            # Simulate successful processing
            await asyncio.sleep(1)


class SafeTaskWalker(Walker):
    """Walker with comprehensive error handling and recovery."""

    max_retries: int = Field(3, description="Maximum retry attempts per node")
    retry_delay: float = Field(1.0, description="Delay between retries in seconds")

    def __init__(self, **data):
        super().__init__(**data)
        self.error_count = 0
        self.success_count = 0
        self.retry_count = 0

    @on_visit(Task)
    async def visit_task(self, here: Task):
        """Process task with retry logic."""
        retries = 0
        while retries < self.max_retries:
            try:
                if retries > 0:
                    print(
                        f"🔄 Retry {retries}/{self.max_retries} for task: {here.title}"
                    )
                    await asyncio.sleep(self.retry_delay)

                await self.process_task_safely(here)
                self.success_count += 1
                break

            except Exception as e:
                retries += 1
                self.retry_count += 1

                if retries == self.max_retries:
                    self.error_count += 1
                    await self.report(
                        {
                            "permanent_failure": {
                                "task_id": here.id,
                                "error": str(e),
                                "retries": retries,
                            }
                        }
                    )
                else:
                    await self.report(
                        {
                            "retry_attempt": {
                                "task_id": here.id,
                                "attempt": retries,
                                "error": str(e),
                            }
                        }
                    )

    async def process_task_safely(self, task: Task):
        """Safe task processing with various error checks."""
        # Validate task state
        if task.status == "completed":
            await self.report(
                {"task_skipped": {"id": task.id, "reason": "already completed"}}
            )
            return

        # Check due date
        if task.due_date and task.due_date < datetime.now():
            await self.report(
                {"task_warning": {"id": task.id, "message": "Task is overdue"}}
            )

        # Process task
        try:
            # Simulate processing
            await asyncio.sleep(0.5)

            # Update task
            task.status = "completed"
            await task.save()

            await self.report(
                {
                    "task_success": {
                        "id": task.id,
                        "title": task.title,
                        "completion_time": datetime.now().isoformat(),
                    }
                }
            )

        except Exception as e:
            raise WalkerExecutionError(
                walker_class=self.__class__.__name__,
                reason=f"Failed to process task: {e}",
                details={"node_id": task.id, "node_type": "Task", "title": task.title},
            )


async def create_sample_tasks():
    """Create sample tasks for demonstration."""
    root = await Root.get()

    tasks = [
        {
            "title": "High priority task",
            "priority": 5,
            "due_date": datetime.now() + timedelta(hours=1),
        },
        {"title": "Failed task", "status": "failed", "priority": 2},
        {"title": "Normal task", "priority": 3},
        {
            "title": "Overdue task",
            "priority": 4,
            "due_date": datetime.now() - timedelta(days=1),
        },
    ]

    created_tasks = []
    for task_data in tasks:
        task = await Task.create(**task_data)
        await root.connect(task)
        created_tasks.append(task)

    return created_tasks


async def demonstrate_basic_error_handling():
    """Demonstrate basic walker error handling."""
    print("\n🚶 Demonstrating basic walker error handling:")

    try:
        root = await Root.get()
        walker = TaskProcessor(timeout_seconds=5)
        await walker.spawn(root)

        report = await walker.get_report()
        completed = [r for r in report if "task_completed" in r]
        errors = [r for r in report if "task_error" in r]

        print(f"✅ Completed tasks: {len(completed)}")
        print(f"❌ Failed tasks: {len(errors)}")

        if errors:
            print("\nError details:")
            for error in errors:
                print(f"  • Task: {error['task_error']['task_title']}")
                print(f"    Error: {error['task_error']['error']}")

    except WalkerTimeoutError as e:
        print(f"❌ Walker timed out: {e.message}")
        print(f"  • Timeout: {e.timeout_seconds}s")

        # Access partial results
        partial_report = await walker.get_report()
        print(f"  • Processed {len(partial_report)} tasks before timeout")

    except WalkerExecutionError as e:
        print(f"❌ Walker execution failed: {e.message}")
        if e.details:
            print(f"  • Details: {e.details}")


async def demonstrate_safe_walker():
    """Demonstrate comprehensive error handling with SafeTaskWalker."""
    print("\n🛡️  Demonstrating safe walker with retries:")

    try:
        root = await Root.get()
        walker = SafeTaskWalker(max_retries=3, retry_delay=0.5)
        await walker.spawn(root)

        print("\nExecution summary:")
        print(f"✅ Successful tasks: {walker.success_count}")
        print(f"❌ Failed tasks: {walker.error_count}")
        print(f"🔄 Total retries: {walker.retry_count}")

        report = await walker.get_report()
        permanent_failures = [r for r in report if "permanent_failure" in r]

        if permanent_failures:
            print("\nPermanent failures:")
            for failure in permanent_failures:
                print(f"  • Task ID: {failure['permanent_failure']['task_id']}")
                print(f"    Error: {failure['permanent_failure']['error']}")

    except Exception as e:
        print(f"❌ Unexpected error in safe walker: {e}")


async def main():
    """Run walker error handling demonstrations."""
    print("🚀 Walker Error Handling Example")
    print("==============================")

    try:
        # Create sample data
        print("\n📝 Creating sample tasks...")
        await create_sample_tasks()

        # Run demonstrations
        await demonstrate_basic_error_handling()
        await demonstrate_safe_walker()

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

    print("\n✨ Example completed!")


if __name__ == "__main__":
    asyncio.run(main())
