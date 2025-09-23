#!/usr/bin/env python3
"""
Authentication Demo for jvspatial

This comprehensive example demonstrates all aspects of the jvspatial authentication system:
- User registration and login with JWT tokens
- API key authentication for services
- Role-based access control (RBAC)
- Spatial permissions and region-based access control
- Different endpoint protection levels
- Real-world usage patterns

Run this example:
    python examples/auth_demo.py

Then visit:
    - http://localhost:8000/docs - Interactive API documentation
    - http://localhost:8000/auth-demo - Demo dashboard with examples
"""

import asyncio
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from jvspatial.api import create_server, endpoint, walker_endpoint
from jvspatial.api.auth import (
    APIKey,
    AuthenticationMiddleware,
    Session,
    User,
    admin_endpoint,
    auth_endpoint,
    auth_walker_endpoint,
    configure_auth,
    get_current_user,
)
from jvspatial.api.endpoint_router import EndpointField
from jvspatial.core import Root
from jvspatial.core.entities import Node, Walker, on_visit

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== SPATIAL DATA MODELS ====================


class City(Node):
    """City node with spatial and demographic data."""

    name: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    population: int = 0
    region: str = ""  # For region-based access control
    country: str = ""


class Highway(Node):
    """Highway node connecting cities."""

    name: str = ""
    length_km: float = 0.0
    speed_limit: int = 65
    toll_road: bool = False
    region: str = ""


class PointOfInterest(Node):
    """Points of interest in cities."""

    name: str = ""
    category: str = ""  # restaurant, hotel, attraction, etc.
    latitude: float = 0.0
    longitude: float = 0.0
    rating: float = 0.0
    city_id: str = ""


# ==================== AUTHENTICATION CONFIGURATION ====================


def setup_authentication():
    """Configure authentication with comprehensive settings."""

    # Generate a secure secret key for demo (use env var in production)
    jwt_secret = secrets.token_urlsafe(32)

    configure_auth(
        # JWT Configuration
        jwt_secret_key=jwt_secret,
        jwt_algorithm="HS256",
        jwt_expiration_hours=24,
        jwt_refresh_expiration_days=7,  # Shorter for demo
        # API Key Configuration
        api_key_header="X-API-Key",  # pragma: allowlist secret
        api_key_query_param="api_key",  # pragma: allowlist secret
        # Rate Limiting
        rate_limit_enabled=True,
        default_rate_limit_per_hour=100,  # Lower for demo
        # Security (relaxed for demo)
        require_https=False,
        session_cookie_secure=False,
        session_cookie_httponly=True,
    )

    logger.info("🔐 Authentication configured with JWT and API key support")


# ==================== SERVER SETUP ====================

# Create server with authentication
server = create_server(
    title="jvspatial Authentication Demo",
    description="Comprehensive authentication demo with spatial data",
    version="1.0.0",
    debug=True,
    db_type="json",
    db_path="jvdb/auth_demo",
)

# Setup authentication
setup_authentication()

# Add authentication middleware
if server.app is not None:
    server.app.add_middleware(AuthenticationMiddleware)

# ==================== DEMO DATA INITIALIZATION ====================


@server.on_startup
async def initialize_demo_data():
    """Initialize demo data including users, spatial data, and API keys."""
    logger.info("🚀 Initializing authentication demo data...")

    try:
        # Create root node if it doesn't exist
        root = await Root.get()
        if not root:
            root = await Root.create()

        # Check if demo data already exists
        existing_users = await User.find(
            {"context.username": {"$in": ["demo_admin", "demo_user", "regional_user"]}}
        )
        if existing_users:
            logger.info("📋 Demo data already exists, skipping initialization")
            return

        # === Create Demo Users ===

        # 1. Admin User
        admin_user = await User.create(
            username="demo_admin",
            email="admin@demo.com",
            password_hash=User.hash_password("admin123"),
            is_admin=True,
            is_active=True,
            roles=["admin", "superuser"],
            permissions=["all"],
            allowed_regions=[],  # Admin can access all regions
            allowed_node_types=[],  # Admin can access all node types
            max_traversal_depth=50,
            rate_limit_per_hour=10000,
        )
        logger.info(f"👑 Created admin user: {admin_user.username}")

        # 2. Standard User with Basic Permissions
        standard_user = await User.create(
            username="demo_user",
            email="user@demo.com",
            password_hash=User.hash_password("user123"),
            is_admin=False,
            is_active=True,
            roles=["user", "viewer"],
            permissions=["read_spatial_data", "read_reports"],
            allowed_regions=["north_america", "europe"],
            allowed_node_types=["City", "PointOfInterest"],
            max_traversal_depth=10,
            rate_limit_per_hour=1000,
        )
        logger.info(f"👤 Created standard user: {standard_user.username}")

        # 3. Regional Analyst with Spatial Restrictions
        regional_user = await User.create(
            username="regional_user",
            email="regional@demo.com",
            password_hash=User.hash_password("regional123"),
            is_admin=False,
            is_active=True,
            roles=["analyst", "regional_viewer"],
            permissions=["read_spatial_data", "analyze_data", "export_reports"],
            allowed_regions=["north_america"],  # Only North America
            allowed_node_types=["City", "Highway"],  # No POIs
            max_traversal_depth=15,
            rate_limit_per_hour=2000,
        )
        logger.info(f"🗺️ Created regional user: {regional_user.username}")

        # === Create API Keys ===

        # API Key for data export service
        export_api_key = await APIKey.create(
            name="Data Export Service",
            key_id="export-service-key",
            key_hash=APIKey.hash_key("demo-export-key-12345"),
            user_id=admin_user.id,
            allowed_endpoints=["/api/export/*", "/public/cities"],
            rate_limit_per_hour=5000,
            expires_at=datetime.now() + timedelta(days=365),
        )
        logger.info(f"🔑 Created API key: {export_api_key.name}")

        # === Create Spatial Demo Data ===

        # North American Cities
        new_york = await City.create(
            name="New York",
            latitude=40.7128,
            longitude=-74.0060,
            population=8400000,
            region="north_america",
            country="USA",
        )

        chicago = await City.create(
            name="Chicago",
            latitude=41.8781,
            longitude=-87.6298,
            population=2700000,
            region="north_america",
            country="USA",
        )

        # European Cities
        london = await City.create(
            name="London",
            latitude=51.5074,
            longitude=-0.1278,
            population=9000000,
            region="europe",
            country="UK",
        )

        paris = await City.create(
            name="Paris",
            latitude=48.8566,
            longitude=2.3522,
            population=2200000,
            region="europe",
            country="France",
        )

        # Asian Cities (restricted region for demo)
        tokyo = await City.create(
            name="Tokyo",
            latitude=35.6762,
            longitude=139.6503,
            population=14000000,
            region="asia",
            country="Japan",
        )

        # Highways
        highway_95 = await Highway.create(
            name="Interstate 95",
            length_km=3088,
            speed_limit=75,
            toll_road=True,
            region="north_america",
        )

        m25 = await Highway.create(
            name="M25 London Orbital",
            length_km=188,
            speed_limit=112,  # km/h
            toll_road=False,
            region="europe",
        )

        # Points of Interest
        statue_of_liberty = await PointOfInterest.create(
            name="Statue of Liberty",
            category="attraction",
            latitude=40.6892,
            longitude=-74.0445,
            rating=4.5,
            city_id=new_york.id,
        )

        tower_bridge = await PointOfInterest.create(
            name="Tower Bridge",
            category="attraction",
            latitude=51.5055,
            longitude=-0.0754,
            rating=4.3,
            city_id=london.id,
        )

        # Connect spatial data to root
        await root.connect(new_york)
        await root.connect(chicago)
        await root.connect(london)
        await root.connect(paris)
        await root.connect(tokyo)
        await root.connect(highway_95)
        await root.connect(m25)
        await root.connect(statue_of_liberty)
        await root.connect(tower_bridge)

        logger.info("🌍 Created spatial demo data with regional restrictions")
        logger.info("✅ Demo initialization complete!")

    except Exception as e:
        logger.error(f"❌ Failed to initialize demo data: {e}")


# ==================== PUBLIC ENDPOINTS ====================


@endpoint("/auth-demo", methods=["GET"])
async def demo_dashboard():
    """Demo dashboard with authentication examples."""
    return {
        "title": "jvspatial Authentication Demo",
        "description": "Comprehensive authentication system demo",
        "endpoints": {
            "public": {
                "info": "GET /public/info",
                "cities": "GET /public/cities",
                "search": "POST /public/search",
            },
            "authenticated": {
                "profile": "GET /auth/profile",
                "protected_data": "GET /protected/data",
                "spatial_query": "POST /protected/spatial-query",
                "reports": "GET /protected/reports",
            },
            "admin": {
                "users": "GET /admin/users",
                "system_info": "GET /admin/system-info",
            },
        },
        "demo_accounts": {
            "admin": {
                "username": "demo_admin",
                "password": "admin123",  # pragma: allowlist secret
                "permissions": "Full admin access",
            },
            "user": {
                "username": "demo_user",
                "password": "user123",  # pragma: allowlist secret
                "permissions": "Read access to North America and Europe",
            },
            "regional": {
                "username": "regional_user",
                "password": "regional123",  # pragma: allowlist secret
                "permissions": "Analyst access limited to North America",
            },
        },
        "api_keys": {
            "export_service": {
                "key": "demo-export-key-12345",
                "usage": "Add header: X-API-Key: demo-export-key-12345",
            }
        },
        "authentication_flow": [
            "1. POST /auth/login with username/password",
            "2. Use returned access_token in Authorization: Bearer <token>",
            "3. Access protected endpoints with token",
            "4. Refresh token with POST /auth/refresh",
        ],
    }


@endpoint("/public/info", methods=["GET"])
async def public_info():
    """Public endpoint - no authentication required."""
    return {
        "message": "This is public information",
        "service": "jvspatial Authentication Demo",
        "version": "1.0.0",
        "authentication": "Not required for this endpoint",
        "timestamp": datetime.now().isoformat(),
    }


@endpoint("/public/cities", methods=["GET"])
async def public_cities_list():
    """Public endpoint to list all cities (for demo purposes)."""
    try:
        cities = await City.all()
        return {
            "message": "Public city list",
            "authentication": "Not required",
            "total_cities": len(cities),
            "cities": [
                {
                    "id": city.id,
                    "name": city.name,
                    "country": city.country,
                    "region": city.region,
                    "population": city.population,
                }
                for city in cities[:10]  # Limit for demo
            ],
        }
    except Exception as e:
        return {"error": f"Failed to fetch cities: {e}"}


@walker_endpoint("/public/search", methods=["POST"])
class PublicSearch(Walker):
    """Public search walker - no authentication required."""

    query: str = EndpointField(
        description="Search query for city names",
        examples=["New York", "London", "Tokyo"],
    )

    limit: int = EndpointField(
        default=5, description="Maximum number of results", ge=1, le=20
    )

    @on_visit(City)
    async def search_cities(self, here: City):
        if self.query.lower() in here.name.lower():
            # Get current report to check results count
            current_report = self.get_report()
            results_count = sum(
                1 for item in current_report if isinstance(item, dict) and "id" in item
            )

            if results_count < self.limit:
                self.report(
                    {
                        "id": here.id,
                        "name": here.name,
                        "country": here.country,
                        "region": here.region,
                        "population": here.population,
                        "coordinates": [here.latitude, here.longitude],
                    }
                )


# ==================== AUTHENTICATED ENDPOINTS ====================


@auth_endpoint("/protected/data", methods=["GET"])
async def protected_data(request: Request):
    """Protected endpoint requiring authentication."""
    current_user = get_current_user(request)
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "message": "This is protected data",
        "authentication": "Required - JWT token",
        "user": {
            "username": current_user.username,
            "email": current_user.email,
            "roles": current_user.roles,
            "permissions": current_user.permissions,
        },
        "timestamp": datetime.now().isoformat(),
    }


@auth_endpoint("/protected/reports", methods=["GET"], permissions=["read_reports"])
async def protected_reports(request: Request):
    """Protected endpoint requiring specific permission."""
    current_user = get_current_user(request)
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "message": "Protected reports data",
        "authentication": "Required - JWT token + read_reports permission",
        "user": current_user.username,
        "reports": [
            {"id": 1, "name": "Monthly Spatial Analysis", "status": "available"},
            {"id": 2, "name": "Regional Demographics", "status": "available"},
            {"id": 3, "name": "Traffic Patterns", "status": "processing"},
        ],
        "timestamp": datetime.now().isoformat(),
    }


@auth_walker_endpoint(
    "/protected/spatial-query", methods=["POST"], permissions=["read_spatial_data"]
)
class ProtectedSpatialQuery(Walker):
    """Protected spatial query walker with region-based access control."""

    region: str = EndpointField(
        description="Target region to query",
        examples=["north_america", "europe", "asia"],
    )

    node_type: str = EndpointField(
        default="City",
        description="Type of nodes to query",
        examples=["City", "Highway", "PointOfInterest"],
    )

    @on_visit(Node)
    async def spatial_query(self, here: Node):
        current_user = get_current_user(self.request)
        if current_user is None:
            self.report({"error": "Not authenticated"})
            return

        # Check if user can access this region
        if not current_user.can_access_region(self.region):
            self.report(
                {
                    "error": "Access denied to region",
                    "region": self.region,
                    "user_allowed_regions": current_user.allowed_regions,
                    "message": "Your account doesn't have access to this region",
                }
            )
            return

        # Check if user can access this node type
        node_type_name = self.node_type
        if not current_user.can_access_node_type(node_type_name):
            self.report(
                {
                    "error": "Access denied to node type",
                    "node_type": node_type_name,
                    "user_allowed_types": current_user.allowed_node_types,
                    "message": "Your account doesn't have access to this node type",
                }
            )
            return

        # Report query metadata once
        current_report = self.get_report()
        if not any(
            isinstance(item, dict) and "query" in item for item in current_report
        ):
            self.report(
                {
                    "query": {"region": self.region, "node_type": self.node_type},
                    "user": current_user.username,
                    "authentication": "JWT token + read_spatial_data permission",
                    "spatial_permissions": {
                        "allowed_regions": current_user.allowed_regions,
                        "allowed_node_types": current_user.allowed_node_types,
                        "max_traversal_depth": current_user.max_traversal_depth,
                    },
                }
            )

        # Query based on node type
        if self.node_type == "City" and isinstance(here, City):
            if here.region == self.region:
                self.report(
                    {
                        "id": here.id,
                        "name": here.name,
                        "type": "City",
                        "region": here.region,
                        "population": here.population,
                        "coordinates": [here.latitude, here.longitude],
                    }
                )

        elif self.node_type == "Highway" and isinstance(here, Highway):
            if here.region == self.region:
                self.report(
                    {
                        "id": here.id,
                        "name": here.name,
                        "type": "Highway",
                        "region": here.region,
                        "length_km": here.length_km,
                        "speed_limit": here.speed_limit,
                    }
                )

        elif self.node_type == "PointOfInterest" and isinstance(here, PointOfInterest):
            # For POIs, check the city's region
            try:
                city = await City.get(here.city_id) if here.city_id else None
                if city and city.region == self.region:
                    self.report(
                        {
                            "id": here.id,
                            "name": here.name,
                            "type": "PointOfInterest",
                            "category": here.category,
                            "rating": here.rating,
                            "coordinates": [here.latitude, here.longitude],
                        }
                    )
            except:
                pass  # Skip if city not found


@auth_walker_endpoint(
    "/protected/analysis",
    methods=["POST"],
    permissions=["analyze_data"],
    roles=["analyst", "admin"],
)
class ProtectedAnalysis(Walker):
    """Advanced analysis requiring both permissions and roles."""

    analysis_type: str = EndpointField(
        default="demographic",
        description="Type of analysis to perform",
        examples=["demographic", "traffic", "economic"],
    )

    @on_visit(City)
    async def analyze_cities(self, here: City):
        current_user = get_current_user(self.request)
        if current_user is None:
            self.report({"error": "Not authenticated"})
            return

        # Report analysis metadata once
        current_report = self.get_report()
        if not any(
            isinstance(item, dict) and "analysis_type" in item
            for item in current_report
        ):
            self.report(
                {
                    "analysis_type": self.analysis_type,
                    "user": current_user.username,
                    "authentication": "JWT token + analyze_data permission + analyst/admin role",
                }
            )

        # Check region access
        if not current_user.can_access_region(here.region):
            pass  # Skip inaccessible regions
        else:
            # Perform analysis based on type
            if self.analysis_type == "demographic":
                analysis_result = {
                    "city": here.name,
                    "region": here.region,
                    "population": here.population,
                    "population_category": (
                        "large"
                        if here.population > 5000000
                        else "medium" if here.population > 1000000 else "small"
                    ),
                    "analysis": f"Demographic analysis for {here.name}",
                }
            else:
                analysis_result = {
                    "city": here.name,
                    "region": here.region,
                    "analysis": f"{self.analysis_type.title()} analysis for {here.name}",
                    "status": "completed",
                }

            self.report(analysis_result)


# ==================== ADMIN-ONLY ENDPOINTS ====================


@admin_endpoint("/admin/users", methods=["GET"])
async def admin_list_users(request: Request):
    """Admin endpoint to list all users."""
    current_user = get_current_user(request)
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        all_users = await User.all()

        return {
            "message": "User management - Admin access only",
            "authentication": "JWT token + admin role required",
            "admin_user": current_user.username,
            "total_users": len(all_users),
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_admin": user.is_admin,
                    "roles": user.roles,
                    "permissions": user.permissions,
                    "allowed_regions": user.allowed_regions,
                    "last_login": (
                        user.last_login.isoformat() if user.last_login else None
                    ),
                    "login_count": user.login_count,
                }
                for user in all_users
            ],
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch users: {e}")


@admin_endpoint("/admin/system-info", methods=["GET"])
async def admin_system_info(request: Request):
    """Admin system information endpoint."""
    current_user = get_current_user(request)
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Get counts
        user_count = len(await User.all())
        city_count = len(await City.all())
        highway_count = len(await Highway.all())
        poi_count = len(await PointOfInterest.all())

        return {
            "message": "System information - Admin access only",
            "authentication": "JWT token + admin role required",
            "admin_user": current_user.username,
            "timestamp": datetime.now().isoformat(),
            "database": {"type": "json", "path": "jvdb/auth_demo"},
            "statistics": {
                "users": user_count,
                "cities": city_count,
                "highways": highway_count,
                "points_of_interest": poi_count,
            },
            "authentication_config": {
                "jwt_enabled": True,
                "api_key_enabled": True,
                "rate_limiting": True,
                "require_https": False,  # Demo setting
            },
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get system info: {e}")


# ==================== API KEY DEMONSTRATION ====================


@endpoint("/api/export/cities", methods=["GET"])
async def api_key_export_cities(request: Request):
    """Endpoint accessible via API key (demonstrates service authentication)."""

    # This endpoint will be accessible via API key due to middleware
    # Check if authenticated via API key
    api_key_user = getattr(request.state, "api_key_user", None)
    jwt_user = getattr(request.state, "current_user", None)

    auth_method = "Unknown"
    user_info = {}

    if api_key_user:
        auth_method = "API Key"
        user_info = {
            "api_key_name": api_key_user.get("name", "Unknown"),
            "key_id": api_key_user.get("key_id", "Unknown"),
        }
    elif jwt_user:
        if jwt_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        auth_method = "JWT Token"
        user_info = {"username": jwt_user.username, "roles": jwt_user.roles}

    try:
        cities = await City.all()

        return {
            "message": "City export data",
            "authentication_method": auth_method,
            "user_info": user_info,
            "export_timestamp": datetime.now().isoformat(),
            "total_cities": len(cities),
            "cities": [
                {
                    "id": city.id,
                    "name": city.name,
                    "country": city.country,
                    "region": city.region,
                    "population": city.population,
                    "coordinates": {
                        "latitude": city.latitude,
                        "longitude": city.longitude,
                    },
                }
                for city in cities
            ],
        }
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")


# ==================== DEMO UTILITIES ====================


@endpoint("/demo/reset-data", methods=["POST"])
async def reset_demo_data():
    """Reset demo data (for testing purposes)."""
    try:
        # Delete all demo data
        demo_users = await User.find(
            {"context.username": {"$in": ["demo_admin", "demo_user", "regional_user"]}}
        )
        for user in demo_users:
            await user.delete()

        cities = await City.all()
        for city in cities:
            await city.delete()

        highways = await Highway.all()
        for highway in highways:
            await highway.delete()

        pois = await PointOfInterest.all()
        for poi in pois:
            await poi.delete()

        api_keys = await APIKey.all()
        for key in api_keys:
            await key.delete()

        # Reinitialize
        await initialize_demo_data()

        return {
            "message": "Demo data reset successfully",
            "status": "success",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "message": "Failed to reset demo data",
            "error": str(e),
            "status": "error",
        }


# ==================== MAIN EXECUTION ====================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔐 JVSPATIAL AUTHENTICATION DEMO")
    print("=" * 60)
    print("\n📋 Demo Features:")
    print("   • JWT token authentication")
    print("   • API key authentication")
    print("   • Role-based access control (RBAC)")
    print("   • Spatial region permissions")
    print("   • Node type restrictions")
    print("   • Rate limiting")
    print("   • Multi-level endpoint protection")
    print("\n🔑 Demo Accounts:")
    print("   Admin:    demo_admin / admin123")
    print("   User:     demo_user / user123")
    print("   Regional: regional_user / regional123")
    print("\n🔐 API Key:")
    print("   Export Service: demo-export-key-12345")
    print("   (Use in header: X-API-Key: demo-export-key-12345)")
    print("\n🌐 Endpoints:")
    print("   Dashboard: http://localhost:8000/auth-demo")
    print("   API Docs:  http://localhost:8000/docs")
    print("   Login:     POST /auth/login")
    print("   Public:    GET /public/*")
    print("   Protected: GET /protected/*")
    print("   Admin:     GET /admin/*")
    print("\n" + "=" * 60)
    print("🚀 Starting server at http://localhost:8000")
    print("=" * 60 + "\n")

    # Run the server
    server.run(host="0.0.0.0", port=8000, reload=False)
