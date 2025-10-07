# Walker Reporting and Event Systems

This guide covers the powerful reporting and event communication systems in jvspatial Walker classes that enable data collection, aggregation, and inter-walker coordination during graph traversal.

## Table of Contents

1. [Walker Reporting System](#walker-reporting-system)
2. [Walker Event System](#walker-event-system)
3. [Advanced Patterns](#advanced-patterns)
4. [Best Practices](#best-practices)
5. [API Reference](#api-reference)

## Walker Reporting System

The Walker reporting system allows you to collect and aggregate any data during graph traversal using a simple, direct approach. Reports are stored as lists that you can access immediately after traversal.

### Basic Reporting

```python
from jvspatial.core import Walker, on_visit, on_exit
import time

class DataCollectorWalker(Walker):
    """Walker that demonstrates basic reporting functionality."""

    def __init__(self):
        super().__init__()
        self.stats = {"processed": 0, "errors": 0}

    @on_visit('User')
    async def process_user(self, here: Node):
        """Process user nodes and report findings."""
        try:
            # Report individual data items
            self.report({
                "user_data": {
                    "id": here.id,
                    "name": here.name,
                    "department": here.department,
                    "processed_at": time.time()
                }
            })

            # Report simple values
            self.report(f"Processed user: {here.name}")

            # Report lists, numbers, any data type
            if hasattr(here, 'skills'):
                self.report(["user_skills", here.skills])

            self.stats["processed"] += 1

        except Exception as e:
            self.stats["errors"] += 1
            self.report({
                "error": {
                    "user_id": here.id,
                    "error_message": str(e),
                    "error_type": type(e).__name__
                }
            })

    @on_exit
    async def generate_final_report(self):
        """Generate summary when traversal completes."""
        current_report = self.get_report()

        self.report({
            "final_summary": {
                "total_report_items": len(current_report),
                "users_processed": self.stats["processed"],
                "errors_encountered": self.stats["errors"],
                "success_rate": (
                    self.stats["processed"] /
                    max(self.stats["processed"] + self.stats["errors"], 1)
                ) * 100
            }
        })

# Usage
walker = DataCollectorWalker()
result_walker = await walker.spawn()  # spawn() returns the walker instance

# Get all collected data as a simple list
report = result_walker.get_report()
print(f"Total items collected: {len(report)}")

# Process collected data
for item in report:
    if isinstance(item, dict) and "user_data" in item:
        user = item["user_data"]
        print(f"User: {user['name']} from {user['department']}")
    elif isinstance(item, str):
        print(f"Log: {item}")
    elif isinstance(item, list) and len(item) == 2 and item[0] == "user_skills":
        print(f"Skills found: {item[1]}")
```

### Advanced Reporting Patterns

#### Data Analysis and Aggregation

```python
class AnalyticsWalker(Walker):
    """Walker with advanced analytics reporting."""

    def __init__(self):
        super().__init__()
        self.metrics = {
            "departments": {},
            "performance_scores": [],
            "risk_assessments": []
        }

    @on_visit('Employee')
    async def analyze_employee(self, here: Node):
        """Analyze employee performance and report detailed findings."""

        # Perform analysis
        performance = await self.calculate_performance_score(here)
        risk_level = await self.assess_risk_level(here)

        # Track internal metrics
        dept = here.department or "unknown"
        self.metrics["departments"][dept] = self.metrics["departments"].get(dept, 0) + 1
        self.metrics["performance_scores"].append(performance)
        self.metrics["risk_assessments"].append(risk_level)

        # Report detailed analysis
        self.report({
            "employee_analysis": {
                "employee_id": here.id,
                "name": here.name,
                "department": dept,
                "performance_score": performance,
                "risk_level": risk_level,
                "analysis_timestamp": time.time(),
                "recommendations": await self.generate_recommendations(here, performance, risk_level)
            }
        })

        # Report alerts for high-risk employees
        if risk_level == "high":
            self.report({
                "alert": {
                    "type": "high_risk_employee",
                    "employee_id": here.id,
                    "employee_name": here.name,
                    "risk_factors": await self.identify_risk_factors(here)
                }
            })

    @on_visit('Project')
    async def analyze_project(self, here: Node):
        """Analyze project status and dependencies."""

        # Get project team
        team_members = await here.nodes(node=['Employee'])

        # Calculate project metrics
        team_size = len(team_members)
        avg_team_performance = sum(
            await self.calculate_performance_score(member)
            for member in team_members
        ) / max(team_size, 1)

        self.report({
            "project_analysis": {
                "project_id": here.id,
                "project_name": here.name,
                "team_size": team_size,
                "avg_team_performance": avg_team_performance,
                "project_status": here.status,
                "analysis_date": time.strftime("%Y-%m-%d")
            }
        })

    @on_exit
    async def generate_comprehensive_report(self):
        """Generate comprehensive analytics from all collected data."""

        # Get all reported data
        all_data = self.get_report()

        # Extract specific data types
        employee_analyses = [
            item for item in all_data
            if isinstance(item, dict) and "employee_analysis" in item
        ]

        project_analyses = [
            item for item in all_data
            if isinstance(item, dict) and "project_analysis" in item
        ]

        alerts = [
            item for item in all_data
            if isinstance(item, dict) and "alert" in item
        ]

        # Calculate aggregate metrics
        if employee_analyses:
            avg_performance = sum(
                ea["employee_analysis"]["performance_score"]
                for ea in employee_analyses
            ) / len(employee_analyses)

            risk_distribution = {}
            for ea in employee_analyses:
                risk = ea["employee_analysis"]["risk_level"]
                risk_distribution[risk] = risk_distribution.get(risk, 0) + 1
        else:
            avg_performance = 0
            risk_distribution = {}

        # Generate final comprehensive report
        self.report({
            "comprehensive_analytics": {
                "summary": {
                    "employees_analyzed": len(employee_analyses),
                    "projects_analyzed": len(project_analyses),
                    "alerts_generated": len(alerts),
                    "total_report_items": len(all_data)
                },
                "performance_metrics": {
                    "average_performance_score": round(avg_performance, 2),
                    "department_breakdown": dict(self.metrics["departments"]),
                    "risk_distribution": risk_distribution
                },
                "recommendations": await self.generate_organizational_recommendations(),
                "generated_at": time.time()
            }
        })

    async def calculate_performance_score(self, employee):
        """Calculate employee performance score."""
        # Simulate performance calculation
        import random
        return random.randint(60, 100)

    async def assess_risk_level(self, employee):
        """Assess employee risk level."""
        import random
        return random.choice(["low", "medium", "high"])

    async def generate_recommendations(self, employee, performance, risk):
        """Generate personalized recommendations."""
        recommendations = []
        if performance < 70:
            recommendations.append("Consider additional training")
        if risk == "high":
            recommendations.append("Schedule performance review")
        return recommendations

    async def identify_risk_factors(self, employee):
        """Identify specific risk factors."""
        return ["low performance", "frequent absences"]  # Simulated

    async def generate_organizational_recommendations(self):
        """Generate organization-wide recommendations."""
        recommendations = []

        # Analyze department distribution
        total_employees = sum(self.metrics["departments"].values())
        largest_dept = max(self.metrics["departments"], key=self.metrics["departments"].get, default="none")

        if largest_dept and self.metrics["departments"][largest_dept] / total_employees > 0.5:
            recommendations.append(f"Consider distributing workload from {largest_dept} department")

        # Analyze performance distribution
        if self.metrics["performance_scores"]:
            avg_perf = sum(self.metrics["performance_scores"]) / len(self.metrics["performance_scores"])
            if avg_perf < 75:
                recommendations.append("Organization-wide performance improvement program recommended")

        return recommendations
```

## Walker Event System

The event system enables real-time communication between walkers during concurrent traversal. Walkers can emit events and subscribe to events from other walkers.

### Basic Event Communication

```python
from jvspatial.core.events import on_emit
import asyncio

class AlertEmitterWalker(Walker):
    """Walker that detects issues and emits alerts."""

    def __init__(self):
        super().__init__()
        self.alerts_sent = 0

    @on_visit('ServerNode')
    async def monitor_server(self, here: Node):
        """Monitor server health and emit alerts."""

        # Check various health metrics
        if hasattr(here, 'cpu_usage') and here.cpu_usage > 85:
            await self.emit("cpu_alert", {
                "server_id": here.id,
                "cpu_usage": here.cpu_usage,
                "severity": "high" if here.cpu_usage > 95 else "medium",
                "timestamp": time.time(),
                "emitter_id": self.id
            })
            self.alerts_sent += 1
            self.report({"alert_sent": f"CPU alert for {here.id}"})

        if hasattr(here, 'memory_usage') and here.memory_usage > 90:
            await self.emit("memory_alert", {
                "server_id": here.id,
                "memory_usage": here.memory_usage,
                "severity": "critical",
                "timestamp": time.time(),
                "emitter_id": self.id
            })
            self.alerts_sent += 1
            self.report({"alert_sent": f"Memory alert for {here.id}"})

        if hasattr(here, 'disk_usage') and here.disk_usage > 95:
            await self.emit("disk_alert", {
                "server_id": here.id,
                "disk_usage": here.disk_usage,
                "severity": "critical",
                "timestamp": time.time(),
                "emitter_id": self.id
            })
            self.alerts_sent += 1
            self.report({"alert_sent": f"Disk alert for {here.id}"})

class AlertProcessorWalker(Walker):
    """Walker that receives and processes alerts from other walkers."""

    def __init__(self):
        super().__init__()
        self.alerts_processed = 0
        self.alert_counts = {"cpu_alert": 0, "memory_alert": 0, "disk_alert": 0}

    @on_emit("cpu_alert")
    async def handle_cpu_alert(self, event_data):
        """Handle CPU alerts from monitoring walkers."""
        self.alerts_processed += 1
        self.alert_counts["cpu_alert"] += 1

        # Process the alert
        action_taken = await self.take_cpu_action(event_data)

        self.report({
            "cpu_alert_processed": {
                "server_id": event_data.get("server_id"),
                "cpu_usage": event_data.get("cpu_usage"),
                "severity": event_data.get("severity"),
                "action_taken": action_taken,
                "processor_id": self.id,
                "processed_at": time.time()
            }
        })

    @on_emit("memory_alert")
    async def handle_memory_alert(self, event_data):
        """Handle memory alerts."""
        self.alerts_processed += 1
        self.alert_counts["memory_alert"] += 1

        action_taken = await self.take_memory_action(event_data)

        self.report({
            "memory_alert_processed": {
                "server_id": event_data.get("server_id"),
                "memory_usage": event_data.get("memory_usage"),
                "action_taken": action_taken,
                "processor_id": self.id
            }
        })

    @on_emit("disk_alert")
    async def handle_disk_alert(self, event_data):
        """Handle disk alerts."""
        self.alerts_processed += 1
        self.alert_counts["disk_alert"] += 1

        action_taken = await self.take_disk_action(event_data)

        self.report({
            "disk_alert_processed": {
                "server_id": event_data.get("server_id"),
                "disk_usage": event_data.get("disk_usage"),
                "action_taken": action_taken,
                "processor_id": self.id
            }
        })

    @on_exit
    async def generate_alert_summary(self):
        """Generate summary of all processed alerts."""
        self.report({
            "alert_processing_summary": {
                "total_alerts_processed": self.alerts_processed,
                "alert_breakdown": dict(self.alert_counts),
                "processor_id": self.id,
                "summary_generated_at": time.time()
            }
        })

    async def take_cpu_action(self, alert_data):
        """Take action for CPU alerts."""
        severity = alert_data.get("severity", "medium")
        if severity == "high":
            return "Initiated process cleanup and notification sent"
        else:
            return "Added to monitoring queue"

    async def take_memory_action(self, alert_data):
        """Take action for memory alerts."""
        return "Memory cleanup initiated and admin notified"

    async def take_disk_action(self, alert_data):
        """Take action for disk alerts."""
        return "Disk cleanup scheduled and capacity expansion requested"

class LoggingWalker(Walker):
    """Walker that logs all system events for audit purposes."""

    def __init__(self):
        super().__init__()
        self.events_logged = 0

    @on_emit("cpu_alert")
    @on_emit("memory_alert")
    @on_emit("disk_alert")
    async def log_system_alert(self, event_data):
        """Log all system alerts for audit trail."""
        self.events_logged += 1

        self.report({
            "audit_log": {
                "event_type": "system_alert",
                "server_id": event_data.get("server_id"),
                "alert_details": event_data,
                "logged_by": self.id,
                "log_timestamp": time.time()
            }
        })

    @on_exit
    async def generate_audit_summary(self):
        """Generate audit summary."""
        self.report({
            "audit_summary": {
                "total_events_logged": self.events_logged,
                "audit_walker_id": self.id,
                "audit_period_end": time.time()
            }
        })

# Example: Run coordinated monitoring system
async def run_monitoring_system():
    """Run a coordinated monitoring system with multiple walkers."""

    # Create walkers
    emitter = AlertEmitterWalker()
    processor = AlertProcessorWalker()
    logger = LoggingWalker()

    # Start all walkers concurrently
    tasks = [
        emitter.spawn(),
        processor.spawn(),
        logger.spawn()
    ]

    # Wait for all to complete
    completed_walkers = await asyncio.gather(*tasks)

    # Collect and analyze results
    emitter_report = emitter.get_report()
    processor_report = processor.get_report()
    logger_report = logger.get_report()

    print(f"Monitoring Results:")
    print(f"- Alerts sent: {emitter.alerts_sent}")
    print(f"- Alerts processed: {processor.alerts_processed}")
    print(f"- Events logged: {logger.events_logged}")
    print(f"- Total report items: {len(emitter_report) + len(processor_report) + len(logger_report)}")

    return {
        "emitter_report": emitter_report,
        "processor_report": processor_report,
        "logger_report": logger_report
    }

# Run the monitoring system
results = await run_monitoring_system()
```

### Advanced Event Patterns

#### Event-Driven Workflow Coordination

```python
class WorkflowCoordinatorWalker(Walker):
    """Walker that coordinates complex multi-step workflows."""

    def __init__(self):
        super().__init__()
        self.workflow_status = {}
        self.completed_workflows = []

    @on_visit('WorkflowNode')
    async def initiate_workflow(self, here: Node):
        """Initiate workflow processing."""
        workflow_id = here.id
        self.workflow_status[workflow_id] = "initiated"

        # Emit workflow start event
        await self.emit("workflow_started", {
            "workflow_id": workflow_id,
            "workflow_type": here.workflow_type,
            "coordinator_id": self.id,
            "start_time": time.time()
        })

        self.report({
            "workflow_initiated": {
                "workflow_id": workflow_id,
                "type": here.workflow_type
            }
        })

    @on_emit("workflow_step_complete")
    async def track_workflow_progress(self, event_data):
        """Track progress of workflow steps."""
        workflow_id = event_data.get("workflow_id")
        step_name = event_data.get("step_name")

        if workflow_id not in self.workflow_status:
            self.workflow_status[workflow_id] = "in_progress"

        self.report({
            "workflow_progress": {
                "workflow_id": workflow_id,
                "step_completed": step_name,
                "completed_by": event_data.get("processor_id"),
                "completion_time": event_data.get("completion_time")
            }
        })

    @on_emit("workflow_complete")
    async def handle_workflow_completion(self, event_data):
        """Handle workflow completion."""
        workflow_id = event_data.get("workflow_id")
        self.workflow_status[workflow_id] = "completed"
        self.completed_workflows.append(workflow_id)

        self.report({
            "workflow_completed": {
                "workflow_id": workflow_id,
                "total_steps": event_data.get("total_steps"),
                "duration": event_data.get("duration"),
                "success": event_data.get("success", True)
            }
        })

        # Emit summary if all workflows are done
        if len(self.completed_workflows) >= 3:  # Expecting 3 workflows
            await self.emit("all_workflows_complete", {
                "completed_count": len(self.completed_workflows),
                "coordinator_id": self.id
            })

class WorkflowProcessorWalker(Walker):
    """Walker that processes individual workflow steps."""

    def __init__(self, processor_name: str):
        super().__init__()
        self.processor_name = processor_name
        self.steps_processed = 0
        self.active_workflows = {}

    @on_emit("workflow_started")
    async def begin_processing(self, event_data):
        """Begin processing when workflow starts."""
        workflow_id = event_data.get("workflow_id")
        workflow_type = event_data.get("workflow_type")

        self.active_workflows[workflow_id] = {
            "type": workflow_type,
            "steps_completed": 0,
            "start_time": time.time()
        }

        # Start processing steps
        await self.process_workflow_steps(workflow_id, workflow_type)

    async def process_workflow_steps(self, workflow_id: str, workflow_type: str):
        """Process individual workflow steps."""

        # Define steps based on workflow type
        if workflow_type == "data_processing":
            steps = ["validate_data", "transform_data", "load_data"]
        elif workflow_type == "user_onboarding":
            steps = ["create_account", "send_welcome", "setup_permissions"]
        else:
            steps = ["step_1", "step_2", "step_3"]

        for step in steps:
            # Simulate step processing
            await asyncio.sleep(0.1)
            self.steps_processed += 1
            self.active_workflows[workflow_id]["steps_completed"] += 1

            # Report step completion
            self.report({
                "step_processed": {
                    "workflow_id": workflow_id,
                    "step_name": step,
                    "processor": self.processor_name,
                    "step_number": self.active_workflows[workflow_id]["steps_completed"]
                }
            })

            # Emit step completion event
            await self.emit("workflow_step_complete", {
                "workflow_id": workflow_id,
                "step_name": step,
                "processor_id": self.id,
                "completion_time": time.time()
            })

        # Workflow complete
        duration = time.time() - self.active_workflows[workflow_id]["start_time"]
        await self.emit("workflow_complete", {
            "workflow_id": workflow_id,
            "total_steps": len(steps),
            "duration": duration,
            "success": True,
            "processor_id": self.id
        })

        self.report({
            "workflow_completed": {
                "workflow_id": workflow_id,
                "processor": self.processor_name,
                "duration": duration,
                "steps_processed": len(steps)
            }
        })

# Example: Coordinated workflow processing
async def run_workflow_system():
    """Run coordinated workflow processing."""

    coordinator = WorkflowCoordinatorWalker()
    processors = [
        WorkflowProcessorWalker("processor_1"),
        WorkflowProcessorWalker("processor_2")
    ]

    # Start all walkers
    all_walkers = [coordinator] + processors
    tasks = [walker.spawn() for walker in all_walkers]

    # Wait for completion
    results = await asyncio.gather(*tasks)

    # Analyze results
    for walker in all_walkers:
        report = walker.get_report()
        print(f"Walker {walker.id}: {len(report)} report items")

    return [walker.get_report() for walker in all_walkers]
```

## Advanced Patterns

### Hierarchical Reporting

```python
class HierarchicalReportWalker(Walker):
    """Walker that creates hierarchical reports with nested data."""

    def __init__(self):
        super().__init__()
        self.department_data = {}
        self.employee_count = 0

    @on_visit('Department')
    async def process_department(self, here: Node):
        """Process department and collect employee data."""
        dept_id = here.id
        dept_name = here.name

        # Get all employees in this department
        employees = await here.nodes(node=['Employee'])

        dept_report = {
            "department_info": {
                "id": dept_id,
                "name": dept_name,
                "employee_count": len(employees),
                "employees": []
            }
        }

        # Process each employee
        for employee in employees:
            emp_data = {
                "id": employee.id,
                "name": employee.name,
                "position": getattr(employee, 'position', 'Unknown'),
                "salary": getattr(employee, 'salary', 0),
                "projects": []
            }

            # Get employee projects
            projects = await employee.nodes(node=['Project'])
            for project in projects:
                emp_data["projects"].append({
                    "id": project.id,
                    "name": project.name,
                    "status": getattr(project, 'status', 'Unknown')
                })

            dept_report["department_info"]["employees"].append(emp_data)
            self.employee_count += 1

        # Calculate department metrics
        if employees:
            avg_salary = sum(
                getattr(emp, 'salary', 0) for emp in employees
            ) / len(employees)
            dept_report["department_info"]["avg_salary"] = avg_salary

        # Report complete department data
        self.report(dept_report)

        # Store for cross-department analysis
        self.department_data[dept_id] = dept_report["department_info"]

    @on_exit
    async def generate_organization_report(self):
        """Generate organization-wide hierarchical report."""

        # Calculate organization metrics
        total_salary = sum(
            sum(emp["salary"] for emp in dept["employees"])
            for dept in self.department_data.values()
        )

        total_projects = sum(
            len(set(proj["id"] for emp in dept["employees"] for proj in emp["projects"]))
            for dept in self.department_data.values()
        )

        # Generate hierarchical organization report
        self.report({
            "organization_report": {
                "summary": {
                    "total_departments": len(self.department_data),
                    "total_employees": self.employee_count,
                    "total_salary_budget": total_salary,
                    "total_projects": total_projects,
                    "avg_employees_per_dept": self.employee_count / max(len(self.department_data), 1)
                },
                "departments": list(self.department_data.values()),
                "generated_at": time.time()
            }
        })
```

### Event-Driven Data Pipeline

```python
class DataPipelineWalker(Walker):
    """Walker that implements an event-driven data processing pipeline."""

    def __init__(self, pipeline_stage: str):
        super().__init__()
        self.pipeline_stage = pipeline_stage
        self.items_processed = 0
        self.processing_errors = []

    @on_emit("data_ready")
    async def process_pipeline_data(self, event_data):
        """Process data when it becomes available."""
        data_id = event_data.get("data_id")
        data_content = event_data.get("content")
        previous_stage = event_data.get("from_stage")

        try:
            # Process data based on pipeline stage
            processed_data = await self.process_for_stage(data_content)
            self.items_processed += 1

            self.report({
                "data_processed": {
                    "data_id": data_id,
                    "stage": self.pipeline_stage,
                    "previous_stage": previous_stage,
                    "processing_time": time.time(),
                    "processor_id": self.id
                }
            })

            # Emit processed data for next stage
            next_stage = self.get_next_stage()
            if next_stage:
                await self.emit("data_ready", {
                    "data_id": data_id,
                    "content": processed_data,
                    "from_stage": self.pipeline_stage,
                    "to_stage": next_stage
                })
            else:
                # Final stage - emit completion
                await self.emit("pipeline_complete", {
                    "data_id": data_id,
                    "final_content": processed_data,
                    "completed_by": self.id
                })

        except Exception as e:
            self.processing_errors.append({
                "data_id": data_id,
                "error": str(e),
                "stage": self.pipeline_stage
            })

            self.report({
                "processing_error": {
                    "data_id": data_id,
                    "error_message": str(e),
                    "failed_stage": self.pipeline_stage
                }
            })

    async def process_for_stage(self, data):
        """Process data according to current pipeline stage."""
        if self.pipeline_stage == "validate":
            # Validation logic
            return {"validated": True, "data": data}
        elif self.pipeline_stage == "transform":
            # Transformation logic
            return {"transformed": True, "data": data, "timestamp": time.time()}
        elif self.pipeline_stage == "enrich":
            # Enrichment logic
            return {"enriched": True, "data": data, "metadata": {"processed_by": self.id}}
        else:
            return data

    def get_next_stage(self):
        """Get the next stage in the pipeline."""
        stages = ["validate", "transform", "enrich"]
        try:
            current_index = stages.index(self.pipeline_stage)
            return stages[current_index + 1] if current_index + 1 < len(stages) else None
        except ValueError:
            return None

    @on_exit
    async def generate_stage_report(self):
        """Generate report for this pipeline stage."""
        self.report({
            "pipeline_stage_summary": {
                "stage": self.pipeline_stage,
                "items_processed": self.items_processed,
                "errors_encountered": len(self.processing_errors),
                "error_rate": len(self.processing_errors) / max(self.items_processed, 1) * 100,
                "processor_id": self.id
            }
        })

# Run data pipeline
async def run_data_pipeline():
    """Run a complete data processing pipeline."""

    # Create pipeline stages
    validator = DataPipelineWalker("validate")
    transformer = DataPipelineWalker("transform")
    enricher = DataPipelineWalker("enrich")

    # Start all stages
    tasks = [
        validator.spawn(),
        transformer.spawn(),
        enricher.spawn()
    ]

    # Inject initial data
    await validator.emit("data_ready", {
        "data_id": "data_001",
        "content": {"raw_data": "sample data"},
        "from_stage": "input",
        "to_stage": "validate"
    })

    # Wait for processing
    results = await asyncio.gather(*tasks)

    # Collect reports
    return {
        "validator_report": validator.get_report(),
        "transformer_report": transformer.get_report(),
        "enricher_report": enricher.get_report()
    }
```

## Best Practices

### 1. Reporting Best Practices

**Good Practices:**

```python
# Use clear, structured data
self.report({
    "user_processed": {
        "id": user.id,
        "name": user.name,
        "timestamp": time.time()
    }
})

# Report different data types as needed
self.report("Processing completed")
self.report(["error", "User not found", user.id])
self.report(42)  # Numbers, booleans, etc.

# Access reports after traversal
walker = MyWalker()
result_walker = await walker.spawn()
report = result_walker.get_report()
```

**Bad Practices:**

```python
# Avoid returning values from decorated methods
@on_visit('User')
async def process_user(self, here: Node):
    result = {"processed": True}
return result  # This won't work

# Don't try to modify the report list directly
walker._report.append(data)  # Use walker.report() instead

# Don't expect complex nested response structures
report = walker.get_report()
data = report["response"]["data"]  # Report is just a list
```

### 2. Event System Best Practices

**Good Practices:**

```python
# Use descriptive event names
await self.emit("user_validation_failed", event_data)
await self.emit("batch_processing_complete", event_data)

# Include relevant context in event data
await self.emit("alert", {
    "alert_type": "high_cpu",
    "server_id": server.id,
    "cpu_usage": 95.2,
    "timestamp": time.time(),
    "severity": "critical",
    "emitter_id": self.id
})

# Handle events selectively
@on_emit("critical_alert")
async def handle_critical_alerts_only(self, event_data):
    if event_data.get("severity") == "critical":
        self.report({"critical_alert_handled": event_data})
```

**Bad Practices:**

```python
# Don't use generic event names
await self.emit("event", data)  # ❌ Too generic
await self.emit("thing_happened", data)  # ❌ Not descriptive

# Don't emit events without useful data
await self.emit("user_processed", {})  # ❌ No useful information

# Don't return values from event handlers
@on_emit("some_event")
async def handle_event(self, event_data):
    return {"handled": True}  # ❌ Won't be used
```

### 3. Performance Considerations

```python
# Efficient reporting for large datasets
class EfficientWalker(Walker):
    def __init__(self):
        super().__init__()
        self.batch_size = 100
        self.current_batch = []

    @on_visit('DataNode')
    async def process_efficiently(self, here: Node):
        # Batch data instead of reporting individually
        self.current_batch.append({
            "id": here.id,
            "value": here.value
        })

        # Report in batches
        if len(self.current_batch) >= self.batch_size:
            self.report({
                "data_batch": {
                    "batch_size": len(self.current_batch),
                    "items": self.current_batch.copy()
                }
            })
            self.current_batch.clear()

    @on_exit
    async def report_remaining_batch(self):
        # Report any remaining items
        if self.current_batch:
            self.report({
                "final_batch": {
                    "batch_size": len(self.current_batch),
                    "items": self.current_batch
                }
            })
```

## API Reference

### Reporting Methods

#### `walker.report(data: Any) -> None`
Add any data to the walker's report list.

**Parameters:**
- `data`: Any serializable data (dict, list, string, number, boolean, None)

**Example:**
```python
walker.report({"user": "john", "processed": True})
walker.report("Processing completed")
walker.report([1, 2, 3, 4])
```

#### `walker.get_report() -> List[Any]`
Get the complete list of all reported items.

**Returns:**
- `List[Any]`: Direct list of all items added via `report()`

**Example:**
```python
report = walker.get_report()
for item in report:
    print(f"Reported item: {item}")
```

### Event Methods

#### `await walker.emit(event_name: str, payload: Any = None) -> None`
Emit an event to other walkers.

**Parameters:**
- `event_name`: String identifier for the event
- `payload`: Optional data to send with the event

**Example:**
```python
await walker.emit("user_processed", {
    "user_id": "123",
    "status": "complete"
})
```

#### `@on_emit(event_name: str)`
Decorator to handle specific events from other walkers.

**Parameters:**
- `event_name`: String identifier for events to handle

**Example:**
```python
@on_emit("user_processed")
async def handle_user_event(self, event_data):
    self.report({"received_event": event_data})
```

### Walker Lifecycle Methods

#### `@on_visit(target_type)`
Decorator for methods that execute when visiting specific node/edge types.

#### `@on_exit`
Decorator for methods that execute when walker completes traversal.

**Example:**
```python
@on_exit
async def generate_final_report(self):
    report_data = self.get_report()
    self.report({"final_summary": len(report_data)})
```

This comprehensive guide covers the full capabilities of the Walker reporting and event systems, enabling you to build sophisticated data collection and inter-walker communication patterns in your jvspatial applications.