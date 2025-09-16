# Examples

The `examples/` directory contains complete working examples:

## Agent Management Hierarchy (`agent_graph.py`)

### Example Overview
Demonstrates a hierarchical agent management system with:
- Parent-child relationships between organizational units
- Spatial indexing of agent locations
- Lifecycle hooks for agent activation/deactivation
- Redis-backed persistence layer

### Key Features Demonstrated
**Hierarchical Organization**
`App → Agents → Departments → Teams → Individual Agents`
_(Implements [Composite Pattern](https://refactoring.guru/design-patterns/composite))_

**Geospatial Properties**
- Automatic coordinate validation using `GeoPoint` class
- Spatial queries within radius (see [API Reference](#spatial-queries))

**Session Management**
- Redis-backed connection pooling
- JWT authentication flows

### Implementation Details
```python
class TravelAgent(Agent):
    def __init__(self, latitude, longitude):
        self.geo = GeoPoint(latitude)  # Using GeoPoint from core spatial library
        self.routing = OSRMClient()    # Interface with OSRM routing engine

    async def plan_route(self, destination):
        """Calculate route using async HTTP client"""
        return await self.routing.get_route(self.geo, destination)
```

### Running the Example
```bash
# Initialize database schema and seed data
cd jvspatial
python examples/agent_graph.py --init-db

# Start the agent coordination service
uvicorn agent_coordinator:app --port 8000
```

### Sample Output & Analysis
```json
{
  "status": "active",          // Current agent state
  "hierarchy": "root/...",     // Organizational path
  "location": "37.7749,...",   // WGS84 coordinates
  "connections": ["..."]       // Active network peers
}
```
- Multi-level hierarchy: App → Agents → Departments → Teams → Individual Agents
- Geospatial properties with automatic coordinate validation
- Lifecycle hooks for node creation/activation
- Redis-backed persistence and session management

**Example code snippet**:
```python
class TravelAgent(Agent):
    def __init__(self, latitude, longitude):
        self.geo = GeoPoint(latitude, longitude)
        self.routing = OSRMClient()

    async def plan_route(self, destination):
        return await self.routing.get_route(self.geo, destination)
```

**Expected output**:
```json
{
  "status": "active",
  "hierarchy": "root/agents/west-coast/sales-team",
  "location": "37.7749,-122.4194",
  "connections": ["dispatch", "logging"]
}
```

## Geospatial Travel System (`travel_graph.py`)

### Example Overview
Real-time multi-modal transportation system featuring:
- OSRM routing engine integration
- Dynamic geofence management
- Emergency rerouting capabilities
- Timezone-aware scheduling

### Key Features Demonstrated
**Multi-modal Transport**
Supports air/sea/rail/road with fallback strategies
```python
class TransportMode(Enum):
    AIR = auto()
    SEA = auto()
    RAIL = auto()
    ROAD = auto()
```

**Real-time Routing**
`OSRMClient().get_route()` with traffic-aware updates
_(See [Routing API](#routing-api) for endpoint details)_

**Proximity Monitoring**
- Configurable geofence radii (default: 50km)
- Automated alerts via `GeoFenceMonitor`

### Implementation Details
```python
def calculate_route(origin: GeoPoint, destination: GeoPoint):
    """Uses OSRM's match service with fallback to offline calculations"""
    try:
        return OSRMClient.get_route(origin, destination)
    except OSRMError:
        return fallback_routing(origin, destination)
```

### Running the Example
```bash
# Interactive mode with sample data
cd jvspatial
python examples/travel_graph.py
```

### Sample Output & Analysis
```json
{
  "route_type": "AIR",
  "distance_km": 5837.2,
  "duration_hrs": 7.5,
  "advisory": "Storm warning: North Atlantic",  // From WeatherService integration
  "alternatives": ["SEA", "RAIL_COMBO"]
}
```
_Output demonstrates automatic weather integration using `WeatherService.check_conditions()`_

## REST API Integration (`fastapi_server.py`)

### Example Overview
Production-grade API implementation showcasing:
- JWT authentication workflows
- Rate-limited endpoints
- Async database operations
- OpenAPI documentation

### Key Features Demonstrated
**Security Layer**
- Role-based access control (RBAC)
- Token refresh mechanism
- HMAC-signed requests

**Performance Optimizations**
```python
@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    """Async database session per request"""
    async with AsyncSessionLocal() as session:
        request.state.db = session
        return await call_next(request)
```

**Documentation**
- Auto-generated Swagger UI at `/docs`
- JSON schema validation
- Example request/response models

### Running the Example
```bash
# Start development server with hot reload
cd jvspatial
python examples/fastapi_server.py

# Generate client SDK from OpenAPI spec
python -m openapi_python_client generate --path http://localhost:8002/openapi.json
```

### Sample Request & Response
```http
GET /api/v1/agents/9c144d58-bd7b-4f78-9e28-61256a3d9422/location
Authorization: Bearer <JWT_TOKEN>

{
  "coordinates": {
    "type": "Point",
    "coordinates": [-122.4194, 37.7749]
  },
  "last_updated": "2025-09-16T14:50:00Z"
}
```
_Response demonstrates GeoJSON formatting and ISO 8601 timestamps_