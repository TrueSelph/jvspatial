"""
jvspatial Server Class Demo

This example demonstrates the powerful Server class from jvspatial, showing
how to create a clean, object-oriented API for spatial data management.

Features demonstrated:
- Simple server setup with automatic database initialization
- Spatial node types (Location, Agent, Mission)
- Walker endpoints for complex business logic
- Custom routes for simple operations
- Middleware and exception handling
- Startup/shutdown hooks
- Health checks and monitoring

Run with: python server_demo.py
Access docs at: http://localhost:8000/docs
"""

import asyncio
import math
from datetime import datetime
from typing import List, Optional

from fastapi.responses import JSONResponse
from pydantic import Field

from jvspatial.api.endpoint.router import EndpointField

# Import the new Server class
from jvspatial.api.server import Server, create_server
from jvspatial.core.entities import Node, Root, Walker, on_exit, on_visit

# ====================== NODE TYPES ======================


class Location(Node):
    """Represents a geographic location with spatial properties."""

    name: str
    latitude: float
    longitude: float
    location_type: str = "poi"  # poi, landmark, facility, hazard
    description: str = ""
    elevation: float = 0.0


class Agent(Node):
    """Represents a mobile agent with location and capabilities."""

    name: str
    agent_type: str = "mobile"  # mobile, stationary, aerial, marine
    status: str = "active"  # active, inactive, maintenance, mission

    # Spatial properties
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0

    # Agent capabilities
    max_speed_kmh: float = 50.0
    range_km: float = 100.0
    capabilities: List[str] = Field(default_factory=list)

    # Status tracking
    last_update: Optional[str] = None
    battery_level: float = 100.0


class Mission(Node):
    """Represents a mission or task with objectives and assignments."""

    title: str
    description: str
    priority: str = "normal"  # low, normal, high, critical
    status: str = "planned"  # planned, active, completed, failed, cancelled

    # Mission area
    target_latitude: float = 0.0
    target_longitude: float = 0.0
    area_radius_km: float = 1.0

    # Timing
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    deadline: Optional[str] = None
    estimated_duration_hours: float = 1.0


# ====================== UTILITY FUNCTIONS ======================


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates using Haversine formula."""
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


# ====================== SERVER SETUP ======================

# Create server with configuration
server = create_server(
    title="Spatial Management API",
    description="Advanced spatial data management using jvspatial Server class",
    version="2.0.0",
    debug=True,  # Enable for development
    db_type="json",  # Use JSON database
    db_path="jvdb/server_demo",  # Database storage path
)

# Register our node types (for documentation/organization)
server.add_node_type(Location)
server.add_node_type(Agent)
server.add_node_type(Mission)


# ====================== STARTUP/SHUTDOWN HOOKS ======================


@server.on_startup
async def initialize_sample_data():
    """Create some sample data on startup."""
    print("🔄 Initializing sample spatial data...")

    # Create sample locations
    locations = [
        await Location.create(
            name="Central Command",
            latitude=40.7128,
            longitude=-74.0060,
            location_type="facility",
            description="Main command and control center",
            elevation=10.0,
        ),
        await Location.create(
            name="Patrol Zone Alpha",
            latitude=40.7500,
            longitude=-74.0500,
            location_type="poi",
            description="Primary patrol area",
            elevation=5.0,
        ),
        await Location.create(
            name="Emergency Beacon",
            latitude=40.6892,
            longitude=-74.0445,
            location_type="landmark",
            description="Emergency response beacon location",
            elevation=15.0,
        ),
    ]

    # Create sample agents
    agents = [
        await Agent.create(
            name="Agent Alpha",
            agent_type="mobile",
            latitude=40.7200,
            longitude=-74.0100,
            max_speed_kmh=60.0,
            range_km=150.0,
            capabilities=["surveillance", "reconnaissance", "communication"],
            last_update=datetime.now().isoformat(),
        ),
        await Agent.create(
            name="Drone Beta",
            agent_type="aerial",
            latitude=40.7400,
            longitude=-74.0300,
            altitude=100.0,
            max_speed_kmh=80.0,
            range_km=50.0,
            capabilities=["aerial_survey", "monitoring", "photography"],
            battery_level=85.0,
            last_update=datetime.now().isoformat(),
        ),
    ]

    # Create sample mission
    mission = await Mission.create(
        title="Operation Watchdog",
        description="Routine surveillance mission in the metropolitan area",
        priority="normal",
        target_latitude=40.7350,
        target_longitude=-74.0250,
        area_radius_km=5.0,
        estimated_duration_hours=4.0,
        deadline=(datetime.now().replace(hour=23, minute=59, second=59).isoformat()),
    )

    # Connect entities to root
    root = await Root.get()  # type: ignore[call-arg]
    for location in locations:
        await root.connect(location)
    for agent in agents:
        await root.connect(agent)
        await mission.connect(agent)  # Assign agents to mission
    await root.connect(mission)

    print(f"✅ Created {len(locations)} locations, {len(agents)} agents, and 1 mission")


@server.on_shutdown
async def cleanup():
    """Cleanup tasks on shutdown."""
    print("🧹 Performing cleanup tasks...")


# ====================== MIDDLEWARE ======================


@server.middleware("http")
async def log_requests(request, call_next):
    """Log all requests."""
    start_time = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start_time).total_seconds()
    print(
        f"🔍 {request.method} {request.url} - {response.status_code} ({duration:.3f}s)"
    )
    return response


# ====================== WALKER ENDPOINTS ======================


@server.walker("/locations/create")
class CreateLocation(Walker):
    """Create a new location with spatial properties."""

    name: str = EndpointField(
        description="Location name",
        examples=["Central Park", "Brooklyn Bridge", "Times Square"],
        min_length=2,
        max_length=100,
    )

    latitude: float = EndpointField(
        description="Latitude coordinate",
        examples=[40.7128, 40.6892, 40.7589],
        ge=-90.0,
        le=90.0,
    )

    longitude: float = EndpointField(
        description="Longitude coordinate",
        examples=[-74.0060, -74.0445, -73.9851],
        ge=-180.0,
        le=180.0,
    )

    location_type: str = EndpointField(
        default="poi",
        description="Type of location",
        examples=["poi", "landmark", "facility", "hazard"],
    )

    description: str = EndpointField(
        default="", description="Location description", max_length=500
    )

    elevation: float = EndpointField(
        default=0.0, description="Elevation in meters", examples=[0.0, 10.5, 100.0]
    )

    @on_visit(Root)
    async def create_location(self, here):
        try:
            location = await Location.create(
                name=self.name,
                latitude=self.latitude,
                longitude=self.longitude,
                location_type=self.location_type,
                description=self.description,
                elevation=self.elevation,
            )

            await here.connect(location)

            return self.endpoint.created(
                data={
                    "location_id": location.id,
                    "name": location.name,
                    "coordinates": [location.latitude, location.longitude],
                    "type": location.location_type,
                    "elevation": location.elevation,
                    "timestamp": datetime.now().isoformat(),
                },
                message="Location created successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Failed to create location",
                status_code=500,
                details={"error": str(e)},
            )


@server.walker("/agents/nearby")
class FindNearbyAgents(Walker):
    """Find agents within a specified radius of coordinates."""

    latitude: float = EndpointField(
        description="Search center latitude",
        examples=[40.7128, 40.6892],
        ge=-90.0,
        le=90.0,
    )

    longitude: float = EndpointField(
        description="Search center longitude",
        examples=[-74.0060, -74.0445],
        ge=-180.0,
        le=180.0,
    )

    radius_km: float = EndpointField(
        default=10.0,
        description="Search radius in kilometers",
        examples=[5.0, 10.0, 25.0],
        gt=0.0,
        le=500.0,
    )

    agent_type: Optional[str] = EndpointField(
        default=None,
        description="Filter by agent type",
        examples=["mobile", "aerial", "marine", "stationary"],
    )

    include_inactive: bool = EndpointField(
        default=False, description="Include inactive agents in results"
    )

    @on_visit(Root)
    async def find_agents(self, here):
        try:
            all_agents = await Agent.all()
            nearby_agents = []

            for agent in all_agents:
                # Skip inactive agents unless requested
                if not self.include_inactive and agent.status == "inactive":
                    continue

                # Filter by agent type if specified
                if self.agent_type and agent.agent_type != self.agent_type:
                    continue

                # Calculate distance
                distance = calculate_distance(
                    self.latitude, self.longitude, agent.latitude, agent.longitude
                )

                if distance <= self.radius_km:
                    nearby_agents.append(
                        {
                            "id": agent.id,
                            "name": agent.name,
                            "type": agent.agent_type,
                            "status": agent.status,
                            "coordinates": [agent.latitude, agent.longitude],
                            "distance_km": round(distance, 2),
                            "capabilities": agent.capabilities,
                            "battery_level": agent.battery_level,
                            "last_update": agent.last_update,
                        }
                    )

            # Sort by distance
            nearby_agents.sort(key=lambda x: x["distance_km"])

            return self.endpoint.success(
                data={
                    "search_center": [self.latitude, self.longitude],
                    "radius_km": self.radius_km,
                    "agent_count": len(nearby_agents),
                    "agents": nearby_agents,
                },
                message="Nearby agents retrieved successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Search failed", status_code=500, details={"error": str(e)}
            )


@server.walker("/missions/assign")
class AssignMission(Walker):
    """Assign agents to a mission based on proximity and capabilities."""

    mission_id: str = EndpointField(
        description="Mission ID to assign agents to",
        examples=["n:Mission:abc123", "mission_001"],
    )

    max_agents: int = EndpointField(
        default=5, description="Maximum number of agents to assign", ge=1, le=50
    )

    required_capabilities: List[str] = EndpointField(
        default_factory=list,
        description="Required agent capabilities",
        examples=[["surveillance"], ["reconnaissance", "communication"]],
    )

    max_distance_km: float = EndpointField(
        default=50.0,
        description="Maximum distance from mission target",
        gt=0.0,
        le=1000.0,
    )

    @on_visit(Root)
    async def assign_mission(self, here):
        try:
            # Get the mission
            mission = await Mission.get(self.mission_id)
            if not mission:
                return self.endpoint.not_found(
                    message="Mission not found", details={"mission_id": self.mission_id}
                )

            # Find suitable agents
            all_agents = await Agent.all()
            suitable_agents = []

            for agent in all_agents:
                # Only consider active agents
                if agent.status != "active":
                    continue

                # Check distance to mission target
                distance = calculate_distance(
                    mission.target_latitude,
                    mission.target_longitude,
                    agent.latitude,
                    agent.longitude,
                )

                if distance > self.max_distance_km:
                    continue

                # Check required capabilities
                if self.required_capabilities:
                    if not all(
                        cap in agent.capabilities for cap in self.required_capabilities
                    ):
                        continue

                suitable_agents.append((agent, distance))

            # Sort by distance and take the best candidates
            suitable_agents.sort(key=lambda x: x[1])
            selected_agents = suitable_agents[: self.max_agents]

            # Assign agents to mission
            assigned_agents = []
            for agent, distance in selected_agents:
                await mission.connect(agent)
                agent.status = "mission"
                await agent.save()

                assigned_agents.append(
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "type": agent.agent_type,
                        "distance_km": round(distance, 2),
                        "capabilities": agent.capabilities,
                    }
                )

            return self.endpoint.success(
                data={
                    "mission_id": mission.id,
                    "mission_title": mission.title,
                    "assigned_count": len(assigned_agents),
                    "assigned_agents": assigned_agents,
                    "mission_target": [
                        mission.target_latitude,
                        mission.target_longitude,
                    ],
                },
                message="Agents assigned to mission successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Assignment failed", status_code=500, details={"error": str(e)}
            )


# ====================== CUSTOM ROUTES ======================


@server.route("/stats", methods=["GET"])
async def get_system_stats():
    """Get system statistics."""
    try:
        locations = await Location.all()
        agents = await Agent.all()
        missions = await Mission.all()

        # Agent status breakdown
        agent_status = {}
        for agent in agents:
            agent_status[agent.status] = agent_status.get(agent.status, 0) + 1

        # Mission status breakdown
        mission_status = {}
        for mission in missions:
            mission_status[mission.status] = mission_status.get(mission.status, 0) + 1

        return {
            "system": "Spatial Management API",
            "timestamp": datetime.now().isoformat(),
            "statistics": {
                "locations": {
                    "total": len(locations),
                    "types": list(set(loc.location_type for loc in locations)),
                },
                "agents": {
                    "total": len(agents),
                    "by_status": agent_status,
                    "types": list(set(agent.agent_type for agent in agents)),
                },
                "missions": {"total": len(missions), "by_status": mission_status},
            },
        }
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Stats failed: {str(e)}"}
        )


@server.route("/locations", methods=["GET"])
async def list_locations(limit: int = 100):
    """List all locations."""
    try:
        locations = await Location.all()
        locations = locations[:limit]

        return {
            "locations": [
                {
                    "id": loc.id,
                    "name": loc.name,
                    "type": loc.location_type,
                    "coordinates": [loc.latitude, loc.longitude],
                    "elevation": loc.elevation,
                    "description": loc.description,
                }
                for loc in locations
            ],
            "count": len(locations),
        }
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to list locations: {str(e)}"}
        )


# ====================== EXCEPTION HANDLERS ======================


@server.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested resource was not found",
            "path": str(request.url),
        },
    )


# ====================== MAIN EXECUTION ======================

if __name__ == "__main__":
    print("🌟 jvspatial Server Class Demo")
    print("=" * 50)
    print("This demo shows the power of the jvspatial Server class")
    print("for building sophisticated spatial data management APIs.")
    print()
    print("Features demonstrated:")
    print("• Object-oriented server configuration")
    print("• Automatic database initialization")
    print("• Spatial node types and relationships")
    print("• Walker-based business logic endpoints")
    print("• Custom routes for simple operations")
    print("• Middleware and exception handling")
    print("• Startup/shutdown lifecycle hooks")
    print("• Health monitoring and statistics")
    print()
    print("🔧 Starting server...")
    print("📖 API docs: http://localhost:8000/docs")
    print("📊 Stats: http://localhost:8000/stats")
    print("🏥 Health: http://localhost:8000/health")
    print()

    # Run the server
    server.run(
        host="127.0.0.1", port=8000, reload=False  # Disable reload for stable examples
    )
