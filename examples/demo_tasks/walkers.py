"""
Walker implementations for demo_tasks package.

These walkers demonstrate how package developers can create
installable walkers with proper endpoint configuration.
"""

from datetime import datetime
from typing import List, Optional

from jvspatial.api import walker_endpoint
from jvspatial.api.endpoint_router import EndpointField
from jvspatial.core.entities import Root, Walker, on_visit


@walker_endpoint("/tasks/reports/generate")
class TaskReportGenerator(Walker):
    """Generate comprehensive task reports."""

    report_type: str = EndpointField(
        default="summary",
        description="Type of report to generate",
        examples=["summary", "detailed", "performance", "timeline"],
        pattern=r"^(summary|detailed|performance|timeline)$",
    )

    format: str = EndpointField(
        default="json",
        description="Report output format",
        examples=["json", "csv", "html"],
        pattern=r"^(json|csv|html)$",
    )

    include_completed: bool = EndpointField(
        default=True, description="Include completed tasks in report"
    )

    date_from: Optional[str] = EndpointField(
        default=None,
        description="Start date for report (ISO format)",
        examples=["2025-01-01", "2025-09-16"],
    )

    date_to: Optional[str] = EndpointField(
        default=None,
        description="End date for report (ISO format)",
        examples=["2025-12-31", "2025-09-30"],
    )

    @on_visit(Root)
    async def generate_report(self, here):
        """Generate the requested report."""
        try:
            # Import Task model from the main application
            # In a real package, you'd define your own models or import them properly
            from examples.dynamic_server_demo import Task

            tasks = await Task.all()

            # Filter tasks based on criteria
            filtered_tasks = []
            for task in tasks:
                # Apply completion filter
                if not self.include_completed and task.status == "completed":
                    continue

                # Apply date filters (simplified - in real implementation would parse dates)
                filtered_tasks.append(task)

            # Generate report based on type
            if self.report_type == "summary":
                report_data = {
                    "total_tasks": len(filtered_tasks),
                    "status_breakdown": {},
                    "priority_breakdown": {},
                    "assigned_vs_unassigned": {
                        "assigned": sum(1 for t in filtered_tasks if t.assigned_to),
                        "unassigned": sum(
                            1 for t in filtered_tasks if not t.assigned_to
                        ),
                    },
                }

                # Status and priority breakdowns
                for task in filtered_tasks:
                    status = task.status
                    priority = task.priority
                    report_data["status_breakdown"][status] = (
                        report_data["status_breakdown"].get(status, 0) + 1
                    )
                    report_data["priority_breakdown"][priority] = (
                        report_data["priority_breakdown"].get(priority, 0) + 1
                    )

            elif self.report_type == "detailed":
                report_data = {
                    "tasks": [
                        {
                            "id": task.id,
                            "title": task.title,
                            "description": task.description,
                            "priority": task.priority,
                            "status": task.status,
                            "assigned_to": task.assigned_to,
                            "created_at": task.created_at,
                        }
                        for task in filtered_tasks
                    ]
                }

            elif self.report_type == "performance":
                # Calculate performance metrics
                by_assignee = {}
                for task in filtered_tasks:
                    if task.assigned_to:
                        assignee = task.assigned_to
                        if assignee not in by_assignee:
                            by_assignee[assignee] = {"total": 0, "completed": 0}
                        by_assignee[assignee]["total"] += 1
                        if task.status == "completed":
                            by_assignee[assignee]["completed"] += 1

                # Calculate completion rates
                for assignee, stats in by_assignee.items():
                    stats["completion_rate"] = (
                        stats["completed"] / stats["total"] if stats["total"] > 0 else 0
                    )

                report_data = {"performance_by_assignee": by_assignee}

            else:  # timeline
                report_data = {"message": "Timeline reports not yet implemented"}

            # Format response
            self.response = {
                "status": "success",
                "report_type": self.report_type,
                "format": self.format,
                "generated_at": datetime.now().isoformat(),
                "filters": {
                    "include_completed": self.include_completed,
                    "date_from": self.date_from,
                    "date_to": self.date_to,
                },
                "data": report_data,
            }

        except Exception as e:
            self.response = {
                "status": "error",
                "error": f"Report generation failed: {str(e)}",
            }


@walker_endpoint("/tasks/bulk/update")
class TaskBulkUpdater(Walker):
    """Perform bulk operations on multiple tasks."""

    task_ids: List[str] = EndpointField(
        description="List of task IDs to update",
        examples=[["task1", "task2"], ["n:Task:abc123", "n:Task:def456"]],
    )

    operation: str = EndpointField(
        description="Bulk operation to perform",
        examples=["update_status", "update_priority", "assign", "unassign"],
        pattern=r"^(update_status|update_priority|assign|unassign)$",
    )

    # Operation-specific parameters
    new_status: Optional[str] = EndpointField(
        default=None,
        description="New status (for update_status operation)",
        examples=["pending", "in_progress", "completed", "cancelled"],
    )

    new_priority: Optional[str] = EndpointField(
        default=None,
        description="New priority (for update_priority operation)",
        examples=["low", "medium", "high", "critical"],
    )

    assignee: Optional[str] = EndpointField(
        default=None, description="User to assign tasks to (for assign operation)"
    )

    @on_visit(Root)
    async def bulk_update(self, here):
        """Perform the bulk update operation."""
        try:
            from examples.dynamic_server_demo import Task

            updated_tasks = []
            failed_tasks = []

            for task_id in self.task_ids:
                try:
                    task = await Task.get(task_id)
                    if not task:
                        failed_tasks.append({"id": task_id, "error": "Task not found"})
                        continue

                    # Perform the requested operation
                    if self.operation == "update_status" and self.new_status:
                        old_status = task.status
                        task.status = self.new_status
                        await task.save()
                        updated_tasks.append(
                            {
                                "id": task.id,
                                "title": task.title,
                                "operation": "status_updated",
                                "old_value": old_status,
                                "new_value": self.new_status,
                            }
                        )

                    elif self.operation == "update_priority" and self.new_priority:
                        old_priority = task.priority
                        task.priority = self.new_priority
                        await task.save()
                        updated_tasks.append(
                            {
                                "id": task.id,
                                "title": task.title,
                                "operation": "priority_updated",
                                "old_value": old_priority,
                                "new_value": self.new_priority,
                            }
                        )

                    elif self.operation == "assign" and self.assignee:
                        old_assignee = task.assigned_to
                        task.assigned_to = self.assignee
                        await task.save()
                        updated_tasks.append(
                            {
                                "id": task.id,
                                "title": task.title,
                                "operation": "assigned",
                                "old_value": old_assignee,
                                "new_value": self.assignee,
                            }
                        )

                    elif self.operation == "unassign":
                        old_assignee = task.assigned_to
                        task.assigned_to = None
                        await task.save()
                        updated_tasks.append(
                            {
                                "id": task.id,
                                "title": task.title,
                                "operation": "unassigned",
                                "old_value": old_assignee,
                                "new_value": None,
                            }
                        )

                    else:
                        failed_tasks.append(
                            {
                                "id": task_id,
                                "error": f"Invalid operation or missing parameters for {self.operation}",
                            }
                        )

                except Exception as task_error:
                    failed_tasks.append(
                        {
                            "id": task_id,
                            "error": f"Failed to update task: {str(task_error)}",
                        }
                    )

            self.response = {
                "status": "success" if not failed_tasks else "partial",
                "operation": self.operation,
                "updated_tasks": updated_tasks,
                "failed_tasks": failed_tasks,
                "summary": {
                    "total_requested": len(self.task_ids),
                    "successful": len(updated_tasks),
                    "failed": len(failed_tasks),
                },
                "updated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            self.response = {
                "status": "error",
                "error": f"Bulk update failed: {str(e)}",
            }


@walker_endpoint("/tasks/notifications/send")
class TaskNotificationSender(Walker):
    """Send notifications for task-related events."""

    notification_type: str = EndpointField(
        description="Type of notification to send",
        examples=[
            "assignment",
            "deadline_reminder",
            "status_change",
            "priority_change",
        ],
        pattern=r"^(assignment|deadline_reminder|status_change|priority_change)$",
    )

    task_ids: List[str] = EndpointField(
        description="Task IDs to send notifications for",
        examples=[["task1"], ["n:Task:abc123", "n:Task:def456"]],
    )

    recipients: Optional[List[str]] = EndpointField(
        default=None,
        description="Specific recipients (if None, will determine based on task assignments)",
        examples=[["user1", "user2"], ["admin@example.com"]],
    )

    message: Optional[str] = EndpointField(
        default=None,
        description="Custom message to include in notification",
        max_length=500,
    )

    notification_method: str = EndpointField(
        default="email",
        description="Method to send notification",
        examples=["email", "sms", "push", "webhook"],
        pattern=r"^(email|sms|push|webhook)$",
    )

    @on_visit(Root)
    async def send_notifications(self, here):
        """Send notifications for the specified tasks."""
        try:
            from examples.dynamic_server_demo import Task

            sent_notifications = []
            failed_notifications = []

            for task_id in self.task_ids:
                try:
                    task = await Task.get(task_id)
                    if not task:
                        failed_notifications.append(
                            {"task_id": task_id, "error": "Task not found"}
                        )
                        continue

                    # Determine recipients
                    notification_recipients = self.recipients or []
                    if not notification_recipients and task.assigned_to:
                        notification_recipients = [task.assigned_to]

                    if not notification_recipients:
                        failed_notifications.append(
                            {
                                "task_id": task_id,
                                "error": "No recipients specified and task not assigned",
                            }
                        )
                        continue

                    # Generate notification content
                    if self.notification_type == "assignment":
                        subject = f"Task Assigned: {task.title}"
                        body = f"You have been assigned to task '{task.title}' with priority {task.priority}."
                    elif self.notification_type == "deadline_reminder":
                        subject = f"Deadline Reminder: {task.title}"
                        body = (
                            f"Reminder: Task '{task.title}' has an upcoming deadline."
                        )
                    elif self.notification_type == "status_change":
                        subject = f"Task Status Updated: {task.title}"
                        body = f"Task '{task.title}' status changed to {task.status}."
                    elif self.notification_type == "priority_change":
                        subject = f"Task Priority Updated: {task.title}"
                        body = (
                            f"Task '{task.title}' priority changed to {task.priority}."
                        )
                    else:
                        subject = f"Task Notification: {task.title}"
                        body = f"Task '{task.title}' requires your attention."

                    # Add custom message if provided
                    if self.message:
                        body += f"\n\nAdditional message: {self.message}"

                    # Simulate sending notification
                    # In a real implementation, this would integrate with actual notification services
                    notification_result = {
                        "task_id": task.id,
                        "task_title": task.title,
                        "notification_type": self.notification_type,
                        "method": self.notification_method,
                        "recipients": notification_recipients,
                        "subject": subject,
                        "body": body,
                        "sent_at": datetime.now().isoformat(),
                        "status": "sent",  # Simulated success
                    }

                    sent_notifications.append(notification_result)

                except Exception as task_error:
                    failed_notifications.append(
                        {
                            "task_id": task_id,
                            "error": f"Failed to send notification: {str(task_error)}",
                        }
                    )

            self.response = {
                "status": "success" if not failed_notifications else "partial",
                "notification_type": self.notification_type,
                "method": self.notification_method,
                "sent_notifications": sent_notifications,
                "failed_notifications": failed_notifications,
                "summary": {
                    "total_requested": len(self.task_ids),
                    "successful": len(sent_notifications),
                    "failed": len(failed_notifications),
                },
                "processed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            self.response = {
                "status": "error",
                "error": f"Notification sending failed: {str(e)}",
            }
