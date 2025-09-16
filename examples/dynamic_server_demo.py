#!/usr/bin/env python3
"""
Dynamic Runtime Registration Demo

This example demonstrates the advanced capabilities of the jvspatial Server class
for dynamic endpoint registration, runtime package discovery, and shared server
instances that can be used across modules.

Features demonstrated:
- Dynamic walker registration after server startup
- Runtime package discovery and endpoint registration
- Shared server instances across modules
- Package-based walker development pattern
- Hot-reloading of endpoints without server restart

Run with: python dynamic_server_demo.py
Then while running, install a package with walkers to see dynamic registration
"""

import asyncio
import os
import threading
import time
from datetime import datetime
from typing import List, Optional

from pydantic import Field

from jvspatial.api import Server, create_server, get_default_server, walker_endpoint
from jvspatial.api.endpoint_router import EndpointField
from jvspatial.core.entities import Node, Root, Walker, on_exit, on_visit

# ====================== NODE TYPES ======================


class Task(Node):
    """Represents a task or work item."""

    title: str
    description: str
    priority: str = "medium"  # low, medium, high, critical
    status: str = "pending"  # pending, in_progress, completed, cancelled
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    assigned_to: Optional[str] = None


class WorkItem(Node):
    """Represents a work item with completion tracking."""

    name: str
    work_type: str = "general"  # general, analysis, development, testing
    estimated_hours: float = 1.0
    actual_hours: float = 0.0
    completion_percentage: float = 0.0


# ====================== SERVER SETUP ======================

# Create server with enhanced configuration
server = create_server(
    title="Dynamic Task Management API",
    description="Advanced task management with dynamic endpoint registration",
    version="2.0.0",
    debug=True,
    db_type="json",
    db_path="jvdb/dynamic_demo",
)

print(f"✅ Server created and set as default: {server.config.title}")

# Register our node types
server.add_node_type(Task)
server.add_node_type(WorkItem)

# Enable package discovery with custom patterns
server.enable_package_discovery(
    enabled=True, patterns=["*_tasks", "*_workflows", "task_*", "demo_*"]
)


# ====================== STARTUP HOOKS ======================


@server.on_startup
async def initialize_sample_tasks():
    """Create sample data on startup."""
    print("🔄 Initializing sample task data...")

    tasks = [
        await Task.create(
            title="System Analysis",
            description="Analyze current system architecture",
            priority="high",
            status="pending",
        ),
        await Task.create(
            title="API Development",
            description="Develop REST API endpoints",
            priority="medium",
            status="in_progress",
            assigned_to="developer_1",
        ),
        await Task.create(
            title="Testing & QA",
            description="Comprehensive testing of new features",
            priority="high",
            status="pending",
        ),
    ]

    work_items = [
        await WorkItem.create(
            name="Database Schema Design",
            work_type="development",
            estimated_hours=8.0,
            completion_percentage=75.0,
            actual_hours=6.5,
        ),
        await WorkItem.create(
            name="Performance Testing",
            work_type="testing",
            estimated_hours=4.0,
            completion_percentage=25.0,
            actual_hours=1.0,
        ),
    ]

    # Connect to root
    root = await Root.get()  # type: ignore[call-arg]
    for task in tasks:
        await root.connect(task)
    for work_item in work_items:
        await root.connect(work_item)

    print(f"✅ Created {len(tasks)} tasks and {len(work_items)} work items")


# ====================== INITIAL WALKER ENDPOINTS ======================


@server.walker("/tasks/create")
class CreateTask(Walker):
    """Create a new task."""

    title: str = EndpointField(
        description="Task title",
        examples=["Fix login bug", "Update documentation"],
        min_length=3,
        max_length=200,
    )

    description: str = EndpointField(description="Task description", max_length=1000)

    priority: str = EndpointField(
        default="medium",
        description="Task priority level",
        examples=["low", "medium", "high", "critical"],
        pattern=r"^(low|medium|high|critical)$",
    )

    assigned_to: Optional[str] = EndpointField(
        default=None, description="User assigned to the task"
    )

    @on_visit(Root)
    async def create_task(self, here):
        try:
            task = await Task.create(
                title=self.title,
                description=self.description,
                priority=self.priority,
                assigned_to=self.assigned_to,
            )

            await here.connect(task)

            self.response = {
                "status": "success",
                "task_id": task.id,
                "title": task.title,
                "priority": task.priority,
                "created_at": task.created_at,
            }

        except Exception as e:
            self.response = {
                "status": "error",
                "error": f"Failed to create task: {str(e)}",
            }


@server.walker("/tasks/search")
class SearchTasks(Walker):
    """Search tasks with various filters."""

    status: Optional[str] = EndpointField(
        default=None,
        description="Filter by task status",
        examples=["pending", "in_progress", "completed"],
    )

    priority: Optional[str] = EndpointField(
        default=None,
        description="Filter by priority",
        examples=["low", "medium", "high", "critical"],
    )

    assigned_to: Optional[str] = EndpointField(
        default=None, description="Filter by assignee"
    )

    include_completed: bool = EndpointField(
        default=False, description="Include completed tasks in results"
    )

    @on_visit(Root)
    async def search_tasks(self, here):
        try:
            all_tasks = await Task.all()
            filtered_tasks = []

            for task in all_tasks:
                # Apply filters
                if self.status and task.status != self.status:
                    continue
                if self.priority and task.priority != self.priority:
                    continue
                if self.assigned_to and task.assigned_to != self.assigned_to:
                    continue
                if not self.include_completed and task.status == "completed":
                    continue

                filtered_tasks.append(
                    {
                        "id": task.id,
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority,
                        "status": task.status,
                        "assigned_to": task.assigned_to,
                        "created_at": task.created_at,
                    }
                )

            self.response = {
                "status": "success",
                "tasks": filtered_tasks,
                "count": len(filtered_tasks),
                "filters_applied": {
                    "status": self.status,
                    "priority": self.priority,
                    "assigned_to": self.assigned_to,
                    "include_completed": self.include_completed,
                },
            }

        except Exception as e:
            self.response = {"status": "error", "error": f"Search failed: {str(e)}"}


# ====================== CUSTOM ROUTES ======================


@server.route("/dashboard", methods=["GET"])
async def get_dashboard():
    """Get dashboard statistics."""
    try:
        tasks = await Task.all()
        work_items = await WorkItem.all()

        # Task statistics
        task_stats = {"total": len(tasks), "by_status": {}, "by_priority": {}}
        for task in tasks:
            task_stats["by_status"][task.status] = (
                task_stats["by_status"].get(task.status, 0) + 1
            )
            task_stats["by_priority"][task.priority] = (
                task_stats["by_priority"].get(task.priority, 0) + 1
            )

        # Work item statistics
        work_stats = {
            "total": len(work_items),
            "total_estimated_hours": sum(item.estimated_hours for item in work_items),
            "total_actual_hours": sum(item.actual_hours for item in work_items),
            "average_completion": (
                sum(item.completion_percentage for item in work_items) / len(work_items)
                if work_items
                else 0
            ),
        }

        return {
            "dashboard": "Task Management",
            "timestamp": datetime.now().isoformat(),
            "tasks": task_stats,
            "work_items": work_stats,
        }

    except Exception as e:
        return {"error": f"Dashboard failed: {str(e)}"}


@server.route("/endpoints/refresh", methods=["POST"])
async def refresh_endpoints():
    """Manually refresh and discover new endpoints."""
    try:
        count = server.refresh_endpoints()
        return {
            "status": "success",
            "message": f"Discovered {count} new endpoints",
            "count": count,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "error": f"Refresh failed: {str(e)}"}


# ====================== RUNTIME REGISTRATION DEMO ======================


def register_dynamic_endpoints():
    """Register additional endpoints after server startup."""

    # This simulates what would happen when a package is installed at runtime
    print("\n🔄 Registering dynamic endpoints...")

    # Dynamic Walker 1: Update Task Status
    class UpdateTaskStatus(Walker):
        """Update the status of a task."""

        task_id: str = EndpointField(description="Task ID to update")
        new_status: str = EndpointField(
            description="New status",
            examples=["pending", "in_progress", "completed", "cancelled"],
            pattern=r"^(pending|in_progress|completed|cancelled)$",
        )
        completion_notes: Optional[str] = EndpointField(
            default=None, description="Optional completion notes"
        )

        @on_visit(Root)
        async def update_status(self, here):
            try:
                task = await Task.get(self.task_id)
                if not task:
                    self.response = {"status": "error", "error": "Task not found"}
                    return

                old_status = task.status
                task.status = self.new_status
                await task.save()

                self.response = {
                    "status": "success",
                    "task_id": task.id,
                    "title": task.title,
                    "old_status": old_status,
                    "new_status": self.new_status,
                    "completion_notes": self.completion_notes,
                    "updated_at": datetime.now().isoformat(),
                }

            except Exception as e:
                self.response = {"status": "error", "error": f"Update failed: {str(e)}"}

    # Register the dynamic walker
    server.register_walker_class(
        UpdateTaskStatus, "/tasks/update-status", methods=["POST"]
    )

    # Dynamic Walker 2: Work Item Progress
    class UpdateWorkProgress(Walker):
        """Update work item progress."""

        work_item_id: str = EndpointField(description="Work item ID")
        completion_percentage: float = EndpointField(
            description="Completion percentage", ge=0.0, le=100.0
        )
        actual_hours: Optional[float] = EndpointField(
            default=None, description="Actual hours worked", ge=0.0
        )

        @on_visit(Root)
        async def update_progress(self, here):
            try:
                work_item = await WorkItem.get(self.work_item_id)
                if not work_item:
                    self.response = {"status": "error", "error": "Work item not found"}
                    return

                work_item.completion_percentage = self.completion_percentage
                if self.actual_hours is not None:
                    work_item.actual_hours = self.actual_hours

                await work_item.save()

                self.response = {
                    "status": "success",
                    "work_item_id": work_item.id,
                    "name": work_item.name,
                    "completion_percentage": work_item.completion_percentage,
                    "actual_hours": work_item.actual_hours,
                    "updated_at": datetime.now().isoformat(),
                }

            except Exception as e:
                self.response = {"status": "error", "error": f"Update failed: {str(e)}"}

    server.register_walker_class(
        UpdateWorkProgress, "/work-items/update-progress", methods=["POST"]
    )

    print("✅ Dynamic endpoints registered successfully!")


# ====================== PACKAGE-STYLE WALKER DEMO ======================


# This simulates what a package developer would do
@walker_endpoint("/tasks/analytics")
class TaskAnalytics(Walker):
    """Analyze task patterns and provide insights."""

    analysis_type: str = EndpointField(
        default="summary",
        description="Type of analysis to perform",
        examples=["summary", "trends", "performance", "workload"],
        pattern=r"^(summary|trends|performance|workload)$",
    )

    date_range_days: int = EndpointField(
        default=30, description="Number of days to analyze", ge=1, le=365
    )

    @on_visit(Root)
    async def analyze_tasks(self, here):
        try:
            tasks = await Task.all()

            if self.analysis_type == "summary":
                analysis = {
                    "total_tasks": len(tasks),
                    "status_distribution": {},
                    "priority_distribution": {},
                    "assigned_tasks": sum(1 for t in tasks if t.assigned_to),
                    "unassigned_tasks": sum(1 for t in tasks if not t.assigned_to),
                }

                for task in tasks:
                    status = task.status
                    priority = task.priority
                    analysis["status_distribution"][status] = (
                        analysis["status_distribution"].get(status, 0) + 1
                    )
                    analysis["priority_distribution"][priority] = (
                        analysis["priority_distribution"].get(priority, 0) + 1
                    )

            elif self.analysis_type == "workload":
                analysis = {"workload_by_assignee": {}}
                for task in tasks:
                    if task.assigned_to:
                        assignee = task.assigned_to
                        if assignee not in analysis["workload_by_assignee"]:
                            analysis["workload_by_assignee"][assignee] = {
                                "total": 0,
                                "pending": 0,
                                "in_progress": 0,
                                "completed": 0,
                            }
                        analysis["workload_by_assignee"][assignee]["total"] += 1
                        analysis["workload_by_assignee"][assignee][task.status] += 1

            else:
                analysis = {
                    "message": f"Analysis type '{self.analysis_type}' not yet implemented"
                }

            self.response = {
                "status": "success",
                "analysis_type": self.analysis_type,
                "date_range_days": self.date_range_days,
                "analysis": analysis,
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            self.response = {"status": "error", "error": f"Analysis failed: {str(e)}"}


# ====================== MONITORING AND MANAGEMENT ======================


def start_background_monitoring():
    """Start background monitoring for new packages."""

    def monitoring_loop():
        while True:
            time.sleep(30)  # Check every 30 seconds
            try:
                if server._is_running:
                    count = server.discover_and_register_packages()
                    if count > 0:
                        print(f"🔍 Background discovery: found {count} new endpoints")
            except Exception as e:
                print(f"⚠️ Background monitoring error: {e}")

    monitoring_thread = threading.Thread(target=monitoring_loop, daemon=True)
    monitoring_thread.start()
    print("🔍 Started background package monitoring")


# ====================== MAIN EXECUTION ======================

if __name__ == "__main__":
    print("🌟 Dynamic Runtime Registration Demo")
    print("=" * 60)
    print("This demo shows advanced jvspatial Server capabilities:")
    print("• Dynamic endpoint registration after server startup")
    print("• Runtime package discovery and registration")
    print("• Shared server instances across modules")
    print("• Package-based walker development")
    print("• Hot-reloading without server restart")
    print()

    # Start background monitoring
    start_background_monitoring()

    # Schedule dynamic endpoint registration after startup
    async def schedule_dynamic_registration():
        # Wait a bit after startup
        await asyncio.sleep(5)
        # Register additional endpoints dynamically
        register_dynamic_endpoints()

        # Show server info
        print(f"\n📊 Server Info:")
        print(f"  • Registered walkers: {len(server._registered_walker_classes)}")
        print(f"  • Custom routes: {len(server._custom_routes)}")
        print(
            f"  • Package discovery: {'enabled' if server._package_discovery_enabled else 'disabled'}"
        )
        print(f"  • Discovery patterns: {server._discovery_patterns}")

    # Add the scheduled task as a startup hook
    @server.on_startup
    async def schedule_registration():
        # Schedule the dynamic registration
        asyncio.create_task(schedule_dynamic_registration())

    print("🔧 Starting server with dynamic capabilities...")
    print("📖 API docs: http://127.0.0.1:8000/docs")
    print("📊 Dashboard: http://127.0.0.1:8000/dashboard")
    print("🔄 Refresh endpoints: POST http://127.0.0.1:8000/endpoints/refresh")
    print()
    print("💡 Try installing a package with walkers while the server is running!")
    print("💡 Use the /endpoints/refresh endpoint to manually discover new endpoints")
    print()

    # Run the server
    server.run(
        host="127.0.0.1",
        port=8000,
        reload=False,  # Disable uvicorn reload to see our dynamic registration
    )
