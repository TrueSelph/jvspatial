#!/usr/bin/env python3
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
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from jvspatial.api.api import GraphAPI
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


async def find_nearby_agents(latitude: float, longitude: float, radius_km: float = 10.0) -> List["Agent"]:
    """Find agents within a specified radius of coordinates."""
    all_agents = await Agent.all()
    nearby = []
    
    for agent in all_agents:
        if hasattr(agent, 'latitude') and hasattr(agent, 'longitude'):
            distance = calculate_distance(latitude, longitude, agent.latitude, agent.longitude)
            if distance <= radius_km:
                nearby.append(agent)
    return nearby

# Set up JSON database for this example
os.environ["JVSPATIAL_DB_TYPE"] = "json"
os.environ["JVSPATIAL_JSONDB_PATH"] = "examples/data/json"

# FastAPI app setup
app = FastAPI(
    title="jvspatial Agent Management API",
    description="A spatial-aware agent management system built with jvspatial",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# GraphAPI for jvspatial endpoints
graph_api = GraphAPI()


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


# ====================== REQUEST/RESPONSE MODELS ======================


class AgentCreateRequest(BaseModel):
    name: str
    agent_type: str = "field"
    latitude: float = 0.0
    longitude: float = 0.0
    skills: List[str] = Field(default_factory=list)
    organization_id: Optional[str] = None


class MissionCreateRequest(BaseModel):
    title: str
    description: str
    priority: str = "medium"
    target_lat: float
    target_lon: float
    deadline: Optional[str] = None
    assigned_agent_ids: List[str] = Field(default_factory=list)


class LocationSearchRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 10.0
    location_type: Optional[str] = None


# ====================== WALKER ENDPOINTS ======================


@graph_api.endpoint("/agents", methods=["POST"])
class CreateAgent(Walker):
    """Create a new agent in the system"""

    name: str
    agent_type: str = "field"
    latitude: float = 0.0
    longitude: float = 0.0
    skills: List[str] = Field(default_factory=list)
    organization_id: Optional[str] = None

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
            if self.organization_id:
                org = await Organization.get(self.organization_id)
                if org:
                    await org.connect(agent)
                    self.response["organization"] = org.name

            self.response.update(
                {
                    "agent_id": agent.id,
                    "name": agent.name,
                    "status": "created",
                    "coordinates": [agent.latitude, agent.longitude],
                }
            )

        except Exception as e:
            self.response = {
                "error": f"Failed to create agent: {str(e)}",
                "status": "error",
            }

    @on_exit
    async def finalize(self):
        if "error" not in self.response:
            self.response["timestamp"] = datetime.now().isoformat()


@graph_api.endpoint("/agents/nearby", methods=["POST"])
class FindNearbyAgents(Walker):
    """Find agents within a specified radius"""

    latitude: float
    longitude: float
    radius_km: float = 10.0
    agent_type: Optional[str] = None
    status: Optional[str] = None

    @on_visit(Root)
    async def find_agents(self, here):
        try:
            # Find nearby agents using spatial query
            nearby_agents = await Agent.find_nearby(
                self.latitude, self.longitude, self.radius_km
            )

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

            self.response.update(
                {
                    "agents": agents_data,
                    "count": len(agents_data),
                    "search_center": [self.latitude, self.longitude],
                    "radius_km": self.radius_km,
                }
            )

        except Exception as e:
            self.response = {"error": f"Search failed: {str(e)}", "status": "error"}

    @on_exit
    async def finalize(self):
        if "error" not in self.response:
            self.response["status"] = "success"


@graph_api.endpoint("/missions", methods=["POST"])
class CreateMission(Walker):
    """Create a new mission and optionally assign agents"""

    title: str
    description: str
    priority: str = "medium"
    target_lat: float
    target_lon: float
    deadline: Optional[str] = None
    assigned_agent_ids: List[str] = Field(default_factory=list)
    auto_assign_radius: Optional[float] = None

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
                nearby_agents = await Agent.find_nearby(
                    self.target_lat, self.target_lon, self.auto_assign_radius
                )
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

            self.response.update(
                {
                    "mission_id": mission.id,
                    "title": mission.title,
                    "status": "created",
                    "target_coordinates": [mission.target_lat, mission.target_lon],
                    "assigned_agents": assigned_agents,
                    "priority": mission.priority,
                }
            )

        except Exception as e:
            self.response = {
                "error": f"Failed to create mission: {str(e)}",
                "status": "error",
            }

    @on_exit
    async def finalize(self):
        if "error" not in self.response:
            self.response["timestamp"] = datetime.now().isoformat()


@graph_api.endpoint("/agents/{agent_id}/status", methods=["POST"])
class UpdateAgentStatus(Walker):
    """Update an agent's status and location"""

    agent_id: str
    status: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @on_visit(Root)
    async def update_agent(self, here):
        try:
            agent = await Agent.get(self.agent_id)
            if not agent:
                self.response = {"error": "Agent not found", "status": "error"}
                return

            # Update fields
            if self.status:
                agent.status = self.status
            if self.latitude is not None:
                agent.latitude = self.latitude
            if self.longitude is not None:
                agent.longitude = self.longitude

            agent.last_contact = datetime.now().isoformat()
            await agent.save()

            self.response.update(
                {
                    "agent_id": agent.id,
                    "name": agent.name,
                    "status": agent.status,
                    "coordinates": [agent.latitude, agent.longitude],
                    "last_contact": agent.last_contact,
                }
            )

        except Exception as e:
            self.response = {"error": f"Update failed: {str(e)}", "status": "error"}

    @on_exit
    async def finalize(self):
        if "error" not in self.response:
            self.response["status"] = "updated"
            self.response["timestamp"] = datetime.now().isoformat()


@graph_api.endpoint("/analytics/overview", methods=["POST"])
class SystemOverview(Walker):
    """Get system overview and analytics"""

    @on_visit(Root)
    async def analyze_system(self, here):
        try:
            # Get all nodes
            all_agents = await Agent.all()
            all_missions = await Mission.all()
            all_organizations = await Organization.all()

            # Agent analytics
            agent_stats = {
                "total": len(all_agents),
                "by_status": {},
                "by_type": {},
                "active_locations": [],
            }

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

                # Active locations
                if agent.status in ["active", "mission"] and (
                    agent.latitude != 0 or agent.longitude != 0
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

            self.response.update(
                {
                    "system_status": "operational",
                    "agents": agent_stats,
                    "missions": mission_stats,
                    "organizations": {"total": len(all_organizations)},
                    "last_updated": datetime.now().isoformat(),
                }
            )

        except Exception as e:
            self.response = {"error": f"Analytics failed: {str(e)}", "status": "error"}

    @on_exit
    async def finalize(self):
        if "error" not in self.response:
            self.response["status"] = "success"


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
        root = await Root.get()
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
app.include_router(graph_api.router, prefix="/api/v1")

# ====================== STARTUP/SHUTDOWN EVENTS ======================


@app.on_event("startup")
async def startup_event():
    """Initialize the system on startup"""
    print("🚀 Starting jvspatial Agent Management API...")

    # Ensure root node exists
    try:
        root = await Root.get()
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

    except Exception as e:
        print(f"❌ Startup error: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("🛑 Shutting down jvspatial Agent Management API...")


if __name__ == "__main__":
    import uvicorn

    print("🔧 Development server starting...")
    print("📖 API docs available at: http://localhost:8000/docs")
    print("🔄 ReDoc available at: http://localhost:8000/redoc")

    uvicorn.run(
        "fastapi_server:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
