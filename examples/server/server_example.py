"""Example demonstrating jvspatial API server features.

This example shows:
1. Server setup and configuration
2. FastAPI integration with walkers
3. Endpoint response handling
4. Error handling
5. Middleware integration
6. API documentation
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel

from jvspatial.api import Server
from jvspatial.api.auth.decorators import auth_endpoint, auth_walker_endpoint
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core.entities import Node, Walker


# Data models
class TaskStatus(str, Enum):
    """Task status values."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(Node):
    """Task node with workflow status."""

    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = datetime.now()
    updated_at: Optional[datetime] = None
    assigned_to: Optional[str] = None  # User ID
    priority: int = 0
    tags: List[str] = []

    async def update_status(self, status: TaskStatus):
        """Update task status with timestamp."""
        self.status = status
        self.updated_at = datetime.now()
        await self.save()


class TaskFilter(BaseModel):
    """Task filter parameters."""

    status: Optional[TaskStatus] = None
    assigned_to: Optional[str] = None
    tags: Optional[List[str]] = None
    min_priority: Optional[int] = None


# API endpoint for basic task operations
@auth_endpoint("/api/tasks", methods=["POST"])
async def create_task(
    title: str, description: str, priority: int = 0, tags: List[str] = [], endpoint=None
):
    """Create a new task.

    Args:
        title: Task title
        description: Task description
        priority: Task priority (0-100)
        tags: List of task tags
    """
    # Validate priority
    if priority < 0 or priority > 100:
        return endpoint.bad_request(
            message="Invalid priority",
            details={"priority": "Must be between 0 and 100"},
        )

    # Create task
    task = await Task.create(
        title=title,
        description=description,
        priority=priority,
        tags=tags,
        created_at=datetime.now(),
    )

    return endpoint.created(
        data={
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "created_at": task.created_at.isoformat(),
        },
        message="Task created successfully",
    )


@auth_endpoint("/api/tasks/{task_id}", methods=["GET"])
async def get_task(task_id: str, endpoint):
    """Get task details.

    Args:
        task_id: Task ID
    """
    task = await Task.get(task_id)
    if not task:
        return endpoint.not_found(
            message="Task not found", details={"task_id": task_id}
        )

    return endpoint.success(
        data={
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "tags": task.tags,
            "assigned_to": task.assigned_to,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
    )


# Walker for task management
@auth_walker_endpoint("/api/tasks/process", methods=["POST"])
class TaskProcessor(Walker):
    """Process tasks based on criteria."""

    filter_criteria: TaskFilter = EndpointField(
        default=TaskFilter(), description="Task filtering criteria"
    )

    auto_assign: bool = EndpointField(
        default=False, description="Automatically assign unassigned tasks"
    )

    update_status: Optional[TaskStatus] = EndpointField(
        default=None, description="Update matching tasks to this status"
    )

    def __init__(
        self,
        filter_criteria: TaskFilter = TaskFilter(),
        auto_assign: bool = False,
        update_status: Optional[TaskStatus] = None,
    ):
        """Initialize task processor.

        Args:
            filter_criteria: Task filtering criteria
            auto_assign: Whether to auto-assign unassigned tasks
            update_status: Status to update matching tasks to
        """
        super().__init__()
        self.filter_criteria = filter_criteria
        self.auto_assign = auto_assign
        self.update_status = update_status
        self._processed = 0

    async def on_start(self):
        """Begin task processing."""
        # Build query from filter criteria
        query = {}
        if self.filter_criteria.status:
            query["status"] = self.filter_criteria.status
        if self.filter_criteria.assigned_to:
            query["assigned_to"] = self.filter_criteria.assigned_to
        if self.filter_criteria.tags:
            query["tags"] = {"$in": self.filter_criteria.tags}
        if self.filter_criteria.min_priority is not None:
            query["priority"] = {"$gte": self.filter_criteria.min_priority}

        # Get matching tasks
        tasks = await Task.all(**query)
        if not tasks:
            self.report({"message": "No matching tasks found"})
            return

        # Process tasks
        for task in tasks:
            await self.visit(task)

    async def on_visit(self, here: Task):
        """Process each matching task."""
        changes = False

        # Auto-assign if needed
        if self.auto_assign and not here.assigned_to:
            here.assigned_to = self.endpoint.current_user.id
            changes = True

        # Update status if requested
        if self.update_status and here.status != self.update_status:
            await here.update_status(self.update_status)
            changes = True

        if changes:
            await here.save()

        self._processed += 1
        self.report(
            {
                "processed_task": {
                    "id": here.id,
                    "title": here.title,
                    "status": here.status,
                    "assigned_to": here.assigned_to,
                }
            }
        )

    async def on_finish(self):
        """Summarize processing results."""
        self.report(
            {
                "summary": {
                    "tasks_processed": self._processed,
                    "filter_criteria": self.filter_criteria.model_dump(),
                    "auto_assign": self.auto_assign,
                    "status_update": self.update_status,
                }
            }
        )


# Create server with custom error handling
def create_server():
    """Create and configure the API server."""
    server = Server(
        title="Task Management API",
        description="Example API demonstrating jvspatial features",
        version="1.0.0",
    )

    # Add custom error handler
    @server.exception_handler(ValueError)
    async def value_error_handler(request, exc):
        return {"status": 400, "message": str(exc), "error_type": "ValueError"}

    # Add custom middleware for request logging
    @server.middleware("http")
    async def log_requests(request, call_next):
        path = request.url.path
        method = request.method
        print(f"Request: {method} {path}")

        response = await call_next(request)

        status = response.status_code
        print(f"Response: {status} - {method} {path}")
        return response

    return server


async def create_sample_data():
    """Create sample tasks."""
    # Create some tasks with different statuses
    await Task.create(
        title="Implement login",
        description="Add user authentication",
        status=TaskStatus.COMPLETED,
        priority=90,
        tags=["auth", "security"],
    )

    await Task.create(
        title="Add file upload",
        description="Implement file upload feature",
        status=TaskStatus.IN_PROGRESS,
        priority=80,
        tags=["storage", "api"],
    )

    await Task.create(
        title="Write docs",
        description="Create API documentation",
        status=TaskStatus.PENDING,
        priority=70,
        tags=["docs"],
    )


async def cleanup_data():
    """Remove sample data."""
    tasks = await Task.all()
    for task in tasks:
        await task.delete()


async def main():
    """Run the server example."""
    print("Setting up server...")
    server = create_server()

    print("Creating sample data...")
    await cleanup_data()
    await create_sample_data()

    print("\nServer configured with:")
    print("- Custom error handling")
    print("- Request logging middleware")
    print("- API documentation")

    print("\nAvailable endpoints:")
    print("POST /api/tasks - Create task")
    print("GET  /api/tasks/{id} - Get task")
    print("POST /api/tasks/process - Process tasks")

    print("\nAPI docs available at:")
    print("http://localhost:8000/docs")

    print("\nStarting server...")
    server.run()


if __name__ == "__main__":
    # Setup and initialize the server
    server = create_server()

    # Create sample data synchronously using asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(cleanup_data())
    loop.run_until_complete(create_sample_data())

    print("\nServer configured with:")
    print("- Custom error handling")
    print("- Request logging middleware")
    print("- API documentation")

    print("\nAvailable endpoints:")
    print("POST /api/tasks - Create task")
    print("GET  /api/tasks/{id} - Get task")
    print("POST /api/tasks/process - Process tasks")

    print("\nAPI docs available at:")
    print("http://localhost:8000/docs")

    print("\nStarting server...")
    # Run server directly
    server.run(host="0.0.0.0", port=8000, reload=False)
