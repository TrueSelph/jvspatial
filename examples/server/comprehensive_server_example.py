#!/usr/bin/env python3
"""Comprehensive Server Example

This example demonstrates a complete jvspatial server implementation that combines:
1. Server setup and configuration
2. FastAPI integration
3. Database initialization
4. Entity models (Objects and Nodes)
5. Graph traversal via Walkers
6. Advanced routing patterns
7. Error handling and middleware
8. Authentication and webhooks
9. Startup/shutdown hooks
10. Health checks and monitoring

The example implements a task and agent management system with:
- Task tracking and assignment
- Agent location and status management
- Team organization
- Location-based services
- Real-time monitoring
- Graph-based analytics

Run with: python comprehensive_server_example.py
Access docs at: http://localhost:8000/docs
"""

import asyncio
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from jvspatial.api import Server, auth_endpoint, create_server, webhook_endpoint
from jvspatial.api.endpoint import EndpointField
from jvspatial.core import Node, Root, Walker, on_exit, on_visit

# ====================== DATA MODELS ======================


class TaskStatus(str, Enum):
    """Task status values."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(str, Enum):
    """Task priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRole(str, Enum):
    """Agent role types."""

    FIELD = "field"
    ANALYST = "analyst"
    MANAGER = "manager"
    SPECIALIST = "specialist"


class AgentStatus(str, Enum):
    """Agent status values."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ON_MISSION = "on_mission"
    OFFLINE = "offline"


class Location(Node):
    """Geographic location with spatial properties."""

    name: str
    latitude: float
    longitude: float
    location_type: str = "poi"  # poi, landmark, facility, hazard
    description: str = ""
    elevation: float = 0.0
    security_level: str = "low"  # low, medium, high, classified


class Team(Node):
    """Team organization for grouping agents."""

    name: str
    team_type: str = "field"  # field, analysis, operations
    headquarters_lat: float = 0.0
    headquarters_lon: float = 0.0
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)


class Agent(Node):
    """Agent with location tracking and capabilities."""

    name: str
    role: AgentRole = AgentRole.FIELD
    status: AgentStatus = AgentStatus.ACTIVE

    # Location tracking
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.now)

    # Capabilities
    skills: List[str] = Field(default_factory=list)
    max_range_km: float = 100.0
    max_speed_kmh: float = 50.0

    # Status
    battery_level: float = 100.0
    last_contact: Optional[datetime] = None


class Task(Node):
    """Task or mission assignment."""

    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL

    # Target location
    target_lat: float = 0.0
    target_lon: float = 0.0
    radius_km: float = 1.0

    # Timing
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    estimated_duration_hours: float = 1.0

    # Assignment
    assigned_team: Optional[str] = None  # Team ID
    assigned_agents: List[str] = Field(default_factory=list)  # Agent IDs


# ====================== UTILITY FUNCTIONS ======================


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometers using Haversine formula."""
    R = 6371  # Earth's radius in kilometers
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ====================== WALKER ENDPOINTS ======================


@auth_endpoint("/api/tasks/create", methods=["POST"])
class CreateTask(Walker):
    """Create a new task with optional agent assignments."""

    title: str = EndpointField(
        description="Task title",
        examples=["Perimeter patrol", "Critical data retrieval"],
        min_length=3,
        max_length=100,
    )

    description: str = EndpointField(
        description="Task description",
        examples=["Patrol the facility perimeter every 30 minutes"],
        min_length=10,
        max_length=1000,
    )

    priority: TaskPriority = EndpointField(
        default=TaskPriority.NORMAL, description="Task priority level"
    )

    # Grouped location parameters
    target_lat: float = EndpointField(
        endpoint_group="location",
        description="Target latitude",
        examples=[40.7128, 51.5074],
        ge=-90.0,
        le=90.0,
    )

    target_lon: float = EndpointField(
        endpoint_group="location",
        description="Target longitude",
        examples=[-74.0060, -0.1278],
        ge=-180.0,
        le=180.0,
    )

    radius_km: float = EndpointField(
        endpoint_group="location",
        default=1.0,
        description="Operation radius in kilometers",
        examples=[1.0, 5.0, 10.0],
        gt=0.0,
        le=100.0,
    )

    # Grouped assignment parameters
    team_id: Optional[str] = EndpointField(
        default=None,
        endpoint_group="assignment",
        description="Team ID to assign task to",
        examples=["team_alpha", "team_bravo"],
    )

    agent_ids: List[str] = EndpointField(
        default_factory=list,
        endpoint_group="assignment",
        description="List of agent IDs to assign",
        examples=[["agent_1", "agent_2"], ["field_007"]],
    )

    auto_assign: bool = EndpointField(
        default=False,
        endpoint_group="assignment",
        description="Automatically assign nearby available agents",
    )

    deadline: Optional[datetime] = EndpointField(
        default=None,
        description="Task deadline",
        examples=[datetime.now() + timedelta(hours=24)],
    )

    @on_visit(Root)
    async def create_task(self, here: Root):
        """Create task and handle assignments."""
        try:
            # Create task
            task = await Task.create(
                title=self.title,
                description=self.description,
                status=TaskStatus.PENDING,
                priority=self.priority,
                target_lat=self.target_lat,
                target_lon=self.target_lon,
                radius_km=self.radius_km,
                deadline=self.deadline,
                created_at=datetime.now(),
            )

            # Connect to root
            await here.connect(task)

            assigned_agents = []

            # Assign to team if specified
            if self.team_id:
                team = await Team.get(self.team_id)
                if team:
                    await team.connect(task)
                    task.assigned_team = team.id
                    await task.save()

            # Assign specific agents
            for agent_id in self.agent_ids:
                agent = await Agent.get(agent_id)
                if agent and agent.status == AgentStatus.ACTIVE:
                    await task.connect(agent)
                    agent.status = AgentStatus.ON_MISSION
                    await agent.save()
                    task.assigned_agents.append(agent.id)
                    assigned_agents.append(
                        {
                            "id": agent.id,
                            "name": agent.name,
                            "role": agent.role,
                            "assignment_type": "manual",
                        }
                    )

            # Auto-assign nearby agents if requested
            if self.auto_assign:
                available_agents = await Agent.find(
                    {
                        "context.status": AgentStatus.ACTIVE,
                        "context.id": {"$nin": self.agent_ids},
                    }
                )

                for agent in available_agents:
                    # Calculate distance to task target
                    distance = calculate_distance(
                        self.target_lat,
                        self.target_lon,
                        agent.latitude,
                        agent.longitude,
                    )

                    # Assign if within range
                    if distance <= agent.max_range_km:
                        await task.connect(agent)
                        agent.status = AgentStatus.ON_MISSION
                        await agent.save()
                        task.assigned_agents.append(agent.id)
                        assigned_agents.append(
                            {
                                "id": agent.id,
                                "name": agent.name,
                                "role": agent.role,
                                "assignment_type": "auto",
                                "distance_km": round(distance, 2),
                            }
                        )

            # Update task with assignments
            await task.save()

            return self.endpoint.created(
                data={
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "priority": task.priority,
                    "location": {
                        "target": [task.target_lat, task.target_lon],
                        "radius_km": task.radius_km,
                    },
                    "team_id": task.assigned_team,
                    "assigned_agents": assigned_agents,
                    "created_at": task.created_at.isoformat(),
                },
                message="Task created successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Failed to create task",
                status_code=500,
                details={"error": str(e)},
            )


@auth_endpoint("/api/agents/nearby", methods=["POST"])
class FindNearbyAgents(Walker):
    """Find agents within a specified radius."""

    # Search parameters
    latitude: float = EndpointField(
        description="Search center latitude",
        examples=[40.7128, 51.5074],
        ge=-90.0,
        le=90.0,
    )

    longitude: float = EndpointField(
        description="Search center longitude",
        examples=[-74.0060, -0.1278],
        ge=-180.0,
        le=180.0,
    )

    radius_km: float = EndpointField(
        default=10.0,
        description="Search radius in kilometers",
        examples=[5.0, 10.0, 25.0],
        gt=0.0,
        le=1000.0,
    )

    # Filter parameters
    role: Optional[AgentRole] = EndpointField(
        default=None, description="Filter by agent role"
    )

    status: Optional[AgentStatus] = EndpointField(
        default=None, description="Filter by agent status"
    )

    skills: Optional[List[str]] = EndpointField(
        default=None,
        description="Required skills (all must match)",
        examples=[["surveillance"], ["combat", "stealth"]],
    )

    team_id: Optional[str] = EndpointField(
        default=None, description="Filter by team assignment", examples=["team_alpha"]
    )

    @on_visit(Root)
    async def find_agents(self, here: Root):
        """Find and filter nearby agents."""
        try:
            # Start with base query
            query: Dict[str, Any] = {}

            # Add filters
            if self.role:
                query["context.role"] = self.role.value
            if self.status:
                query["context.status"] = self.status.value
            if self.skills:
                query["context.skills"] = {"$all": self.skills}

            # Get agents matching filters
            agents = await Agent.find(query)
            nearby_agents = []

            for agent in agents:
                # Calculate distance
                distance = calculate_distance(
                    self.latitude, self.longitude, agent.latitude, agent.longitude
                )

                if distance <= self.radius_km:
                    # Get team info if requested
                    team_info = None
                    if self.team_id:
                        agent_teams = await agent.nodes(node=[Team])
                        for team in agent_teams:
                            if team.id == self.team_id:
                                team_info = {
                                    "id": team.id,
                                    "name": team.name,
                                    "type": team.team_type,
                                }
                                break
                        if not team_info:
                            continue  # Skip if not in requested team

                    nearby_agents.append(
                        {
                            "id": agent.id,
                            "name": agent.name,
                            "role": agent.role,
                            "status": agent.status,
                            "location": {
                                "coordinates": [agent.latitude, agent.longitude],
                                "distance_km": round(distance, 2),
                            },
                            "capabilities": {
                                "skills": agent.skills,
                                "max_range_km": agent.max_range_km,
                                "battery_level": agent.battery_level,
                            },
                            "team": team_info,
                            "last_contact": (
                                agent.last_contact.isoformat()
                                if agent.last_contact
                                else None
                            ),
                        }
                    )

            # Sort by distance
            nearby_agents.sort(key=lambda x: x["location"]["distance_km"])

            return self.endpoint.success(
                data={
                    "search_center": [self.latitude, self.longitude],
                    "radius_km": self.radius_km,
                    "filters_applied": {
                        "role": self.role,
                        "status": self.status,
                        "skills": self.skills,
                        "team_id": self.team_id,
                    },
                    "agents_found": len(nearby_agents),
                    "agents": nearby_agents,
                },
                message="Search completed successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Search failed", status_code=500, details={"error": str(e)}
            )


@auth_endpoint("/api/analytics/overview", methods=["POST"])
class SystemOverview(Walker):
    """Generate system overview and analytics."""

    include_locations: bool = EndpointField(
        default=True, description="Include agent locations"
    )

    include_inactive: bool = EndpointField(
        default=False, description="Include inactive agents"
    )

    team_id: Optional[str] = EndpointField(default=None, description="Filter by team")

    @on_visit(Root)
    async def analyze_system(self, here: Root):
        """Generate system analytics."""
        try:
            # Get all nodes
            all_agents = await Agent.all()
            all_tasks = await Task.all()
            all_teams = await Team.all()

            # Apply team filter if specified
            if self.team_id:
                team = await Team.get(self.team_id)
                if team:
                    all_agents = [
                        agent
                        for agent in all_agents
                        if agent.id in (await team.nodes(node=[Agent]))
                    ]
                    all_tasks = [
                        task for task in all_tasks if task.assigned_team == team.id
                    ]

            # Filter inactive if specified
            if not self.include_inactive:
                all_agents = [
                    agent
                    for agent in all_agents
                    if agent.status != AgentStatus.INACTIVE
                ]

            # Calculate statistics
            agent_stats = {
                "total": len(all_agents),
                "by_status": {},
                "by_role": {},
                "skill_distribution": {},
            }

            # Track unique skills
            for agent in all_agents:
                # Status breakdown
                if isinstance(agent_stats["by_status"], dict):
                    agent_stats["by_status"][agent.status] = (
                        agent_stats["by_status"].get(agent.status, 0) + 1
                    )

                # Role breakdown
                if isinstance(agent_stats["by_role"], dict):
                    agent_stats["by_role"][agent.role] = (
                        agent_stats["by_role"].get(agent.role, 0) + 1
                    )

                # Skills breakdown
                if isinstance(agent_stats["skill_distribution"], dict):
                    for skill in agent.skills:
                        agent_stats["skill_distribution"][skill] = (
                            agent_stats["skill_distribution"].get(skill, 0) + 1
                        )

            # Add locations if requested
            if self.include_locations:
                agent_stats["active_locations"] = [
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "role": agent.role,
                        "coordinates": [agent.latitude, agent.longitude],
                        "last_contact": (
                            agent.last_contact.isoformat()
                            if agent.last_contact
                            else None
                        ),
                    }
                    for agent in all_agents
                    if agent.status in [AgentStatus.ACTIVE, AgentStatus.ON_MISSION]
                ]

            # Task statistics
            task_stats = {
                "total": len(all_tasks),
                "by_status": {},
                "by_priority": {},
                "completion_rate": 0.0,
            }

            completed_tasks = 0
            for task in all_tasks:
                # Status breakdown
                if isinstance(task_stats["by_status"], dict):
                    task_stats["by_status"][task.status] = (
                        task_stats["by_status"].get(task.status, 0) + 1
                    )

                # Priority breakdown
                if isinstance(task_stats["by_priority"], dict):
                    task_stats["by_priority"][task.priority] = (
                        task_stats["by_priority"].get(task.priority, 0) + 1
                    )

                if task.status == TaskStatus.COMPLETED:
                    completed_tasks += 1

            # Calculate completion rate
            if all_tasks:
                task_stats["completion_rate"] = round(
                    completed_tasks / len(all_tasks) * 100, 2
                )

            # Team statistics
            team_stats = {
                "total": len(all_teams),
                "by_type": {},
                "agent_distribution": {},
            }

            for team in all_teams:
                # Type breakdown
                if isinstance(team_stats["by_type"], dict):
                    team_stats["by_type"][team.team_type] = (
                        team_stats["by_type"].get(team.team_type, 0) + 1
                    )

                # Agent distribution
                if isinstance(team_stats["agent_distribution"], dict):
                    team_agents = await team.nodes(node=[Agent])
                    team_stats["agent_distribution"][team.id] = len(team_agents)

            return self.endpoint.success(
                data={
                    "timestamp": datetime.now().isoformat(),
                    "system_status": "operational",
                    "agents": agent_stats,
                    "tasks": task_stats,
                    "teams": team_stats,
                    "filter_applied": {
                        "team_id": self.team_id,
                        "include_inactive": self.include_inactive,
                    },
                },
                message="Analytics generated successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Analytics failed", status_code=500, details={"error": str(e)}
            )


# ====================== WEBHOOK ENDPOINTS ======================


from typing import Any, cast


@cast(
    Any,
    webhook_endpoint(
        "/webhook/agent-update/{key}",
        path_key_auth=True,
        hmac_secret="agent-update-secret",  # pragma: allowlist secret
        idempotency_ttl_hours=24,
    ),
)
async def agent_location_webhook(
    payload: dict, endpoint
) -> Union[JSONResponse, Dict[str, Any]]:  # type: ignore[call-arg,misc]
    """Process agent location and status updates.

    Webhook for receiving real-time agent updates from the field.
    """
    try:
        agent_id = payload.get("agent_id")
        if not agent_id:
            return endpoint.bad_request(message="Missing agent_id in payload")

        # Get agent
        agent = await Agent.get(agent_id)
        if not agent:
            return endpoint.not_found(
                message="Agent not found", details={"agent_id": agent_id}
            )

        # Update location if provided
        if "location" in payload:
            loc = payload["location"]
            agent.latitude = loc.get("latitude", agent.latitude)
            agent.longitude = loc.get("longitude", agent.longitude)
            agent.altitude = loc.get("altitude", agent.altitude)

        # Update status if provided
        if "status" in payload:
            agent.status = payload["status"]

        # Update battery if provided
        if "battery_level" in payload:
            agent.battery_level = payload["battery_level"]

        # Always update last_contact
        agent.last_contact = datetime.now()
        await agent.save()

        return endpoint.success(
            data={
                "agent_id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "location_updated": "location" in payload,
                "last_contact": agent.last_contact.isoformat(),
            },
            message="Agent updated successfully",
        )

    except Exception as e:
        # Always return 200 for webhooks
        print(f"Error processing agent update webhook: {e}")
        return endpoint.success(
            data={"status": "error_logged"},
            message="Update received but processing failed",
        )


# ====================== SERVER SETUP ======================

# Create server instance
server = Server(
    title="Task Management API",
    description="Advanced task and agent management system",
    version="1.0.0",
    debug=True,
)


# Add startup tasks
@server.on_startup
async def initialize_data():
    """Initialize sample data on startup."""
    print("🔄 Initializing sample data...")

    # Create sample team
    team = await Team.create(
        name="Alpha Team",
        team_type="field",
        headquarters_lat=40.7128,
        headquarters_lon=-74.0060,
    )

    # Create sample agents
    agents = []
    for i in range(3):
        agent = await Agent.create(
            name=f"Agent {i+1}",
            role=list(AgentRole)[i % len(AgentRole)],
            latitude=40.7128 + (i * 0.01),
            longitude=-74.0060 + (i * 0.01),
            skills=["surveillance", "analysis"][: i + 1],
            last_contact=datetime.now(),
        )
        agents.append(agent)
        await team.connect(agent)

    # Create sample task
    task = await Task.create(
        title="Initial Reconnaissance",
        description="Survey target area",
        priority=TaskPriority.HIGH,
        target_lat=40.7128,
        target_lon=-74.0060,
        deadline=datetime.now() + timedelta(hours=24),
    )

    # Connect to team
    await team.connect(task)

    print(f"✅ Created {len(agents)} agents and 1 task")


# Add shutdown tasks
@server.on_shutdown
async def cleanup():
    """Cleanup tasks on shutdown."""
    print("🧹 Performing cleanup tasks...")


# Add request logging middleware
@server.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing."""
    start_time = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start_time).total_seconds()

    print(
        f"🔍 {request.method} {request.url} - {response.status_code} ({duration:.3f}s)"
    )
    return response


# Add custom error handler
@server.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource does not exist",
            "path": str(request.url),
        },
    )


# ====================== MAIN ======================

if __name__ == "__main__":
    print("🚀 Starting Task Management API...")
    print("Features enabled:")
    print("• Real-time agent tracking")
    print("• Task management and assignment")
    print("• Team organization")
    print("• Location-based services")
    print("• System analytics")
    print("• Webhook integrations")
    print()
    print("📖 API docs: http://localhost:8000/docs")
    print("🏥 Health check: http://localhost:8000/health")
    print()

    # Run the server without reload since we're passing the app instance directly
    server.run(host="127.0.0.1", port=8000, reload=False)
