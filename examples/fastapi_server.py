"""
FastAPI Server Example using jvspatial

This example demonstrates a complete FastAPI application using jvspatial for:
- Agent management with spatial capabilities
- Location-based services
- Graph traversal via REST endpoints
- Real-time agent tracking and interaction

Run with: uvicorn fastapi_server:app --reload
Access docs at: http://localhost:8000/docs
"""

import math
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from jvspatial.api.endpoint.router import EndpointField, EndpointRouter
from jvspatial.core.entities import Node, Root, Walker, on_exit, on_visit


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers using Haversine formula."""
    earth_radius = 6371  # Earth's radius in kilometers
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius * c


async def find_nearby_agents(
    latitude: float, longitude: float, radius_km: float = 10.0
) -> List["Agent"]:
    """Find agents within a specified radius of coordinates."""
    all_agents = await Agent.all()
    nearby = []

    for agent in all_agents:
        if hasattr(agent, "latitude") and hasattr(agent, "longitude"):
            distance = calculate_distance(
                latitude, longitude, agent.latitude, agent.longitude
            )
            if distance <= radius_km:
                nearby.append(agent)
    return nearby


# Set up JSON database for this example
os.environ["JVSPATIAL_DB_TYPE"] = "json"
os.environ["JVSPATIAL_JSONDB_PATH"] = "jvdb/examples"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events"""
    # Startup
    print("🚀 Starting jvspatial Agent Management API...")

    # Ensure root node exists
    try:
        # Root.get() has an optional id parameter that is ignored - Root is a singleton
        root = await Root.get()  # type: ignore[call-arg]
        if not root:
            raise RuntimeError("Failed to initialize root node")
        print(f"✅ Root node initialized: {root.id}")

        # Create sample organization if none exist
        orgs = await Organization.all()
        if not orgs:
            sample_org = await Organization.create(
                name="Acme Corp",
                type="company",
                headquarters_lat=40.7128,
                headquarters_lon=-74.0060,
            )
            await root.connect(sample_org)
            print(f"✅ Sample organization created: {sample_org.name}")

            # Create 3 sample agents
            agents = []
            for i in range(1, 4):
                agent = await Agent.create(
                    name=f"Agent {i}",
                    agent_type=["field", "analyst", "manager"][i - 1],
                    latitude=40.7128 + (i * 0.01),
                    longitude=-74.0060 + (i * 0.01),
                    skills=["surveillance", "analysis", "logistics"][:i],
                    status="active",
                )
                await sample_org.connect(agent)
                agents.append(agent)
                print(f"🕵️  Sample agent created: {agent.name}")

            # Create 3 sample missions
            for i in range(1, 4):
                mission = await Mission.create(
                    title=f"Mission {i}",
                    description=f"Critical mission #{i}",
                    target_lat=40.7128 + (i * 0.1),
                    target_lon=-74.0060 + (i * 0.1),
                    priority=["low", "medium", "high"][i - 1],
                    status="active",
                )
                await root.connect(mission)
                await mission.connect(agents[i - 1])
                print(f"🎯 Sample mission created: {mission.title}")

            # Verify connections
            print("\n🔗 Relationship Verification:")
            org_agents = await sample_org.connected_nodes(Agent)
            print(f"Organization '{sample_org.name}' has {len(org_agents)} agents")

            all_missions = await Mission.all()
            for mission in all_missions:
                mission_agents = await mission.connected_nodes(Agent)
                print(
                    f"Mission '{mission.title}' has {len(mission_agents)} assigned agents"
                )

    except Exception as e:
        print(f"❌ Startup error: {e}")

    yield  # Application is running

    # Shutdown
    print("🛑 Shutting down jvspatial Agent Management API...")


# FastAPI app setup
app = FastAPI(
    title="jvspatial Agent Management API",
    description="An agent management system built with jvspatial",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# EndpointRouter for jvspatial endpoints
api = EndpointRouter()


# Custom exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "detail": str(exc)}
    )


# ====================== NODE DEFINITIONS ======================


class Organization(Node):
    """Organization node for grouping agents"""

    name: str
    type: str = "company"  # company, government, ngo
    headquarters_lat: float = 0.0
    headquarters_lon: float = 0.0


class Agent(Node):
    """Individual agent with spatial and status properties"""

    name: str
    agent_type: str = "field"  # field, analyst, manager
    status: str = "active"  # active, inactive, mission
    latitude: float = 0.0
    longitude: float = 0.0
    last_contact: Optional[str] = None
    skills: List[str] = Field(default_factory=list)


class Mission(Node):
    """Mission node representing tasks or objectives"""

    title: str
    description: str
    status: str = "planned"  # planned, active, completed, failed
    priority: str = "medium"  # low, medium, high, critical
    target_lat: float = 0.0
    target_lon: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    deadline: Optional[str] = None


class Location(Node):
    """Points of interest or strategic locations"""

    name: str
    location_type: str = "poi"  # poi, safe_house, checkpoint, target
    latitude: float
    longitude: float
    description: str = ""
    security_level: str = "low"  # low, medium, high, classified


# ====================== WALKER ENDPOINTS ======================


@api.endpoint("/agents", methods=["POST"])
class CreateAgent(Walker):
    """
    Create a new agent in the system

    Example request body:
    {
        "name": "James Bond",
        "agent_type": "field",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "skills": ["combat", "surveillance"],
        "organization_id": "org_12345"
    }

    Responses:
    201: Returns created agent details
    400: Invalid input data format
    500: Internal server error
    """

    name: str = EndpointField(
        description="Full name of the agent",
        examples=["James Bond", "Aria Blake", "Marcus Cole"],
        min_length=2,
        max_length=100,
    )

    agent_type: str = EndpointField(
        default="field",
        description="Agent role type",
        examples=["field", "analyst", "manager"],
        pattern=r"^(field|analyst|manager)$",
    )

    # Grouped location parameters
    latitude: float = EndpointField(
        default=0.0,
        endpoint_group="location",
        description="Agent's initial latitude coordinate",
        examples=[40.7128, 51.5074, -33.8688],
        ge=-90.0,
        le=90.0,
    )

    longitude: float = EndpointField(
        default=0.0,
        endpoint_group="location",
        description="Agent's initial longitude coordinate",
        examples=[-74.0060, -0.1278, 151.2093],
        ge=-180.0,
        le=180.0,
    )

    skills: List[str] = EndpointField(
        default_factory=list,
        description="List of agent skills and specializations",
        examples=[
            ["surveillance", "combat"],
            ["analysis", "linguistics"],
            ["logistics", "medical"],
        ],
    )

    organization_id: Optional[str] = EndpointField(
        default=None,
        description="Optional organization ID to assign agent to",
        examples=["n:Organization:org12345", "org_12345", "acme_corp"],
        pattern=r"^[a-zA-Z0-9_:-]+$",  # Allow colons for jvspatial IDs
    )

    @on_visit(Root)
    async def create_agent(self, here):
        try:
            # Create the agent
            agent = await Agent.create(
                name=self.name,
                agent_type=self.agent_type,
                latitude=self.latitude,
                longitude=self.longitude,
                skills=self.skills,
                last_contact=datetime.now().isoformat(),
            )

            # Connect to root
            await here.connect(agent)

            # Connect to organization if provided
            # Build response data
            response_data = {
                "agent_id": agent.id,
                "name": agent.name,
                "status": "created",
                "coordinates": [agent.latitude, agent.longitude],
                "timestamp": datetime.now().isoformat(),
            }

            if self.organization_id:
                org = await Organization.get(self.organization_id)
                if org:
                    await org.connect(agent)
                    response_data["organization"] = org.name

            return self.endpoint.success(
                data=response_data, message="Agent created successfully"
            )

        except Exception as e:
            return self.endpoint.error(
                message="Failed to create agent", details={"error": str(e)}
            )


@api.endpoint("/agents/nearby", methods=["POST"])
class FindNearbyAgents(Walker):
    """Find agents within a specified radius"""

    # Grouped search parameters
    latitude: float = EndpointField(
        endpoint_group="search_center",
        description="Latitude of search center point",
        examples=[40.7128, 51.5074, -33.8688],
        ge=-90.0,
        le=90.0,
    )

    longitude: float = EndpointField(
        endpoint_group="search_center",
        description="Longitude of search center point",
        examples=[-74.0060, -0.1278, 151.2093],
        ge=-180.0,
        le=180.0,
    )

    radius_km: float = EndpointField(
        default=10.0,
        endpoint_group="search_center",
        description="Search radius in kilometers",
        examples=[5.0, 10.0, 25.0],
        gt=0.0,
        le=1000.0,
    )

    # Grouped filter parameters
    agent_type: Optional[str] = EndpointField(
        default=None,
        endpoint_group="filters",
        description="Filter by agent type",
        examples=["field", "analyst", "manager"],
    )

    status: Optional[str] = EndpointField(
        default=None,
        endpoint_group="filters",
        description="Filter by agent status",
        examples=["active", "inactive", "mission"],
    )

    @on_visit(Root)
    async def find_agents(self, here):
        try:
            # Find nearby agents using custom spatial logic
            all_agents = await Agent.all()
            nearby_agents = []

            for agent in all_agents:
                if hasattr(agent, "latitude") and hasattr(agent, "longitude"):
                    distance = calculate_distance(
                        self.latitude, self.longitude, agent.latitude, agent.longitude
                    )
                    if distance <= self.radius_km:
                        nearby_agents.append(agent)

            # Apply filters
            filtered_agents = nearby_agents
            if self.agent_type:
                filtered_agents = [
                    a for a in filtered_agents if a.agent_type == self.agent_type
                ]
            if self.status:
                filtered_agents = [
                    a for a in filtered_agents if a.status == self.status
                ]

            # Format response
            agents_data = []
            for agent in filtered_agents:
                agents_data.append(
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "type": agent.agent_type,
                        "status": agent.status,
                        "coordinates": [agent.latitude, agent.longitude],
                        "skills": agent.skills,
                        "last_contact": agent.last_contact,
                    }
                )

            return self.endpoint.success(
                data={
                    "agents": agents_data,
                    "count": len(agents_data),
                    "search_center": [self.latitude, self.longitude],
                    "radius_km": self.radius_km,
                },
                message="Search completed successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Search failed", details={"error": str(e)}
            )


@api.endpoint("/missions", methods=["POST"])
class CreateMission(Walker):
    """
    Create a new mission and optionally assign agents

    Example request body:
    {
        "title": "Operation Phoenix",
        "description": "High-priority extraction mission",
        "priority": "high",
        "target_location": {
            "target_lat": 40.7128,
            "target_lon": -74.0060
        },
        "deadline": "2025-12-31T23:59:59Z",
        "assignment": {
            "assigned_agent_ids": ["agent_1", "agent_2"],
            "auto_assign_radius": 25.0
        }
    }

    Responses:
    201: Returns mission details with assigned agents
    400: Invalid coordinates or agent IDs
    500: Internal server error
    """

    title: str = EndpointField(
        description="Mission title or codename",
        examples=["Operation Phoenix", "Shadow Protocol", "Blue Moon"],
        min_length=3,
        max_length=100,
    )

    description: str = EndpointField(
        description="Detailed mission description and objectives",
        examples=["High-priority extraction mission", "Covert surveillance operation"],
        min_length=10,
        max_length=1000,
    )

    priority: str = EndpointField(
        default="medium",
        description="Mission priority level",
        examples=["low", "medium", "high", "critical"],
        pattern=r"^(low|medium|high|critical)$",
    )

    # Grouped target location
    target_lat: float = EndpointField(
        endpoint_group="target_location",
        description="Target latitude coordinate",
        examples=[40.7128, 51.5074, -33.8688],
        ge=-90.0,
        le=90.0,
    )

    target_lon: float = EndpointField(
        endpoint_group="target_location",
        description="Target longitude coordinate",
        examples=[-74.0060, -0.1278, 151.2093],
        ge=-180.0,
        le=180.0,
    )

    deadline: Optional[str] = EndpointField(
        default=None,
        description="Mission deadline in ISO 8601 format",
        examples=["2025-12-31T23:59:59Z", "2025-06-15T12:00:00Z"],
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
    )

    # Grouped assignment parameters
    assigned_agent_ids: List[str] = EndpointField(
        default_factory=list,
        endpoint_group="assignment",
        description="List of specific agent IDs to assign to mission",
        examples=[["agent_1", "agent_2"], ["field_agent_007"]],
    )

    auto_assign_radius: Optional[float] = EndpointField(
        default=None,
        endpoint_group="assignment",
        description="Radius in km to auto-assign nearby available agents",
        examples=[25.0, 50.0, 100.0],
        gt=0.0,
        le=1000.0,
    )

    @on_visit(Root)
    async def create_mission(self, here):
        try:
            # Create the mission
            mission = await Mission.create(
                title=self.title,
                description=self.description,
                priority=self.priority,
                target_lat=self.target_lat,
                target_lon=self.target_lon,
                deadline=self.deadline,
            )

            # Connect to root
            await here.connect(mission)

            assigned_agents = []

            # Assign specific agents
            for agent_id in self.assigned_agent_ids:
                agent = await Agent.get(agent_id)
                if agent:
                    await mission.connect(agent)
                    agent.status = "mission"
                    await agent.save()
                    assigned_agents.append(
                        {"id": agent.id, "name": agent.name, "type": "explicit"}
                    )

            # Auto-assign nearby agents if requested
            if self.auto_assign_radius:
                # Find nearby agents using custom spatial logic
                all_agents = await Agent.all()
                nearby_agents = []

                for agent in all_agents:
                    if hasattr(agent, "latitude") and hasattr(agent, "longitude"):
                        distance = calculate_distance(
                            self.target_lat,
                            self.target_lon,
                            agent.latitude,
                            agent.longitude,
                        )
                        if distance <= self.auto_assign_radius:
                            nearby_agents.append(agent)

                for agent in nearby_agents:
                    if (
                        agent.status == "active"
                        and agent.id not in self.assigned_agent_ids
                    ):
                        await mission.connect(agent)
                        agent.status = "mission"
                        await agent.save()
                        assigned_agents.append(
                            {
                                "id": agent.id,
                                "name": agent.name,
                                "type": "auto_assigned",
                            }
                        )

            return self.endpoint.success(
                data={
                    "mission_id": mission.id,
                    "title": mission.title,
                    "status": "created",
                    "target_coordinates": [mission.target_lat, mission.target_lon],
                    "assigned_agents": assigned_agents,
                    "priority": mission.priority,
                    "timestamp": datetime.now().isoformat(),
                },
                message="Mission created successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Failed to create mission", details={"error": str(e)}
            )


@api.endpoint("/agents/{agent_id}/status", methods=["POST"])
class UpdateAgentStatus(Walker):
    """Update an agent's status and location"""

    agent_id: str = EndpointField(
        description="Unique identifier of the agent to update",
        examples=["n:Agent:e928b2fd8478401c85e3ebdd", "agent_007", "field_agent_1"],
        pattern=r"^[a-zA-Z0-9_:-]+$",  # Allow colons for jvspatial IDs
    )

    status: Optional[str] = EndpointField(
        default=None,
        description="New status for the agent",
        examples=["active", "inactive", "mission", "offline"],
        pattern=r"^(active|inactive|mission|offline)$",
    )

    # Grouped location update
    latitude: Optional[float] = EndpointField(
        default=None,
        endpoint_group="location_update",
        description="Updated latitude coordinate",
        examples=[40.7128, 51.5074],
        ge=-90.0,
        le=90.0,
    )

    longitude: Optional[float] = EndpointField(
        default=None,
        endpoint_group="location_update",
        description="Updated longitude coordinate",
        examples=[-74.0060, -0.1278],
        ge=-180.0,
        le=180.0,
    )

    @on_visit(Root)
    async def update_agent(self, here):
        try:
            agent = await Agent.get(self.agent_id)
            if not agent:
                return self.endpoint.not_found(
                    message="Agent not found", details={"agent_id": self.agent_id}
                )

            # Update fields
            if self.status:
                agent.status = self.status
            if self.latitude is not None:
                agent.latitude = self.latitude
            if self.longitude is not None:
                agent.longitude = self.longitude

            agent.last_contact = datetime.now().isoformat()
            await agent.save()

            return self.endpoint.success(
                data={
                    "agent_id": agent.id,
                    "name": agent.name,
                    "status": agent.status,
                    "coordinates": [agent.latitude, agent.longitude],
                    "last_contact": agent.last_contact,
                    "timestamp": datetime.now().isoformat(),
                },
                message="Agent updated successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Update failed", details={"error": str(e)}
            )


@api.endpoint("/analytics/overview", methods=["POST"])
class SystemOverview(Walker):
    """Get system overview and analytics"""

    # Optional parameters for filtering and customization
    include_locations: bool = EndpointField(
        default=True,
        description="Include agent location data in the response",
        examples=[True, False],
    )

    include_inactive: bool = EndpointField(
        default=False,
        description="Include inactive agents in the statistics",
        examples=[True, False],
    )

    agent_type_filter: Optional[str] = EndpointField(
        default=None,
        description="Filter statistics to specific agent type",
        examples=["field", "analyst", "manager"],
        pattern=r"^(field|analyst|manager)$",
    )

    @on_visit(Root)
    async def analyze_system(self, here):
        try:
            # Get all nodes
            all_agents = await Agent.all()
            all_missions = await Mission.all()
            all_organizations = await Organization.all()

            # Apply agent type filter if specified
            if self.agent_type_filter:
                all_agents = [
                    a for a in all_agents if a.agent_type == self.agent_type_filter
                ]

            # Apply inactive filter if specified
            if not self.include_inactive:
                all_agents = [a for a in all_agents if a.status != "inactive"]

            # Agent analytics
            agent_stats = {
                "total": len(all_agents),
                "by_status": {},
                "by_type": {},
            }

            # Include locations only if requested
            if self.include_locations:
                agent_stats["active_locations"] = []

            for agent in all_agents:
                # Status breakdown
                status = agent.status
                agent_stats["by_status"][status] = (
                    agent_stats["by_status"].get(status, 0) + 1
                )

                # Type breakdown
                agent_type = agent.agent_type
                agent_stats["by_type"][agent_type] = (
                    agent_stats["by_type"].get(agent_type, 0) + 1
                )

                # Active locations (only if requested)
                if (
                    self.include_locations
                    and agent.status in ["active", "mission"]
                    and (agent.latitude != 0 or agent.longitude != 0)
                ):
                    agent_stats["active_locations"].append(
                        {
                            "id": agent.id,
                            "name": agent.name,
                            "coordinates": [agent.latitude, agent.longitude],
                        }
                    )

            # Mission analytics
            mission_stats = {
                "total": len(all_missions),
                "by_status": {},
                "by_priority": {},
            }

            for mission in all_missions:
                # Status breakdown
                status = mission.status
                mission_stats["by_status"][status] = (
                    mission_stats["by_status"].get(status, 0) + 1
                )

                # Priority breakdown
                priority = mission.priority
                mission_stats["by_priority"][priority] = (
                    mission_stats["by_priority"].get(priority, 0) + 1
                )

            return self.endpoint.success(
                data={
                    "system_status": "operational",
                    "agents": agent_stats,
                    "missions": mission_stats,
                    "organizations": {"total": len(all_organizations)},
                    "last_updated": datetime.now().isoformat(),
                },
                message="Analytics completed successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Analytics failed", details={"error": str(e)}
            )


# ====================== STANDARD REST ENDPOINTS ======================


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "jvspatial Agent Management API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "create_agent": "POST /agents",
            "find_nearby": "POST /agents/nearby",
            "create_mission": "POST /missions",
            "update_agent": "POST /agents/{agent_id}/status",
            "analytics": "POST /analytics/overview",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connectivity
        root = await Root.get()  # type: ignore[call-arg]
        if not root:
            raise RuntimeError("Root node not available")
        return {
            "status": "healthy",
            "database": "connected",
            "root_node": root.id,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
        )


@app.get("/agents")
async def list_agents(limit: int = 100, agent_type: Optional[str] = None):
    """List all agents with optional filtering"""
    try:
        agents = await Agent.all()

        if agent_type:
            agents = [a for a in agents if a.agent_type == agent_type]

        agents = agents[:limit]

        return {
            "agents": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "type": agent.agent_type,
                    "status": agent.status,
                    "coordinates": [agent.latitude, agent.longitude],
                    "last_contact": agent.last_contact,
                }
                for agent in agents
            ],
            "count": len(agents),
            "total_available": len(await Agent.all()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/missions")
async def list_missions(limit: int = 100, status: Optional[str] = None):
    """List all missions with optional filtering"""
    try:
        missions = await Mission.all()

        if status:
            missions = [m for m in missions if m.status == status]

        missions = missions[:limit]

        return {
            "missions": [
                {
                    "id": mission.id,
                    "title": mission.title,
                    "status": mission.status,
                    "priority": mission.priority,
                    "target_coordinates": [mission.target_lat, mission.target_lon],
                    "created_at": mission.created_at,
                }
                for mission in missions
            ],
            "count": len(missions),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Include the graph API router
app.include_router(api.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    print("🔧 Development server starting...")
    print("📖 API docs available at: http://localhost:8003/docs")
    print("🔄 ReDoc available at: http://localhost:8003/redoc")

    uvicorn.run(
        "fastapi_server:app", host="0.0.0.0", port=8003, reload=False, log_level="info"
    )
