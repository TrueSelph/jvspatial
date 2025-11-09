"""
Simple Dynamic Registration Example

This example shows the basic patterns developers will use when building
applications with jvspatial's dynamic registration capabilities.

Use cases demonstrated:
- Creating a shared server instance
- Registering walkers from different modules
- Using the server across multiple files
- Simple package-style development

Run with: python simple_dynamic_example.py
"""

import asyncio
from datetime import datetime
from typing import Optional

from jvspatial.api import create_server, endpoint
from jvspatial.api.endpoint.decorators import EndpointField
from jvspatial.core.decorators import on_visit
from jvspatial.core.entities import Node, Root, Walker

# ====================== DATA MODELS ======================


class User(Node):
    """Simple user model."""

    name: str
    email: str
    role: str = "user"
    active: bool = True


# ====================== SERVER SETUP ======================

# Create the main application server - this becomes the default server
server = create_server(
    title="Simple Dynamic API",
    description="Example of dynamic endpoint registration patterns",
    version="1.0.0",
    debug=True,
    db_type="json",
    db_path="./jvdb",
)

print(f"📋 Server created: {server.config.title}")


# ====================== MAIN APPLICATION ENDPOINTS ======================


@endpoint("/users/create")
class CreateUser(Walker):
    """Create a new user - registered directly with server instance."""

    name: str = EndpointField(
        description="User full name", min_length=2, max_length=100
    )

    email: str = EndpointField(
        description="User email address", pattern=r"^[^@]+@[^@]+\.[^@]+$"
    )

    role: str = EndpointField(
        default="user", description="User role", examples=["user", "admin", "moderator"]
    )

    @on_visit(Root)
    async def create_user(self, here):
        try:
            user = await User.create(name=self.name, email=self.email, role=self.role)

            await here.connect(user)

            return self.endpoint.created(
                data={
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role,
                    "created_at": datetime.now().isoformat(),
                },
                message="User created successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Failed to create user",
                status_code=500,
                details={"error": str(e)},
            )


# ====================== PACKAGE-STYLE ENDPOINTS ======================
# These would typically be in separate files/packages


@endpoint("/users/search")
class SearchUsers(Walker):
    """Search users - registered to default server from package."""

    role: Optional[str] = EndpointField(
        default=None,
        description="Filter by user role",
        examples=["user", "admin", "moderator"],
    )

    active_only: bool = EndpointField(
        default=True, description="Only return active users"
    )

    @on_visit(Root)
    async def search_users(self, here):
        try:
            # RECOMMENDED: Use entity-centric find with MongoDB-style queries
            query = {}
            if self.role:
                query["context.role"] = self.role
            if self.active_only:
                query["context.active"] = True

            filtered_users_entities = await User.find(query)

            filtered_users = [
                {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": user.role,
                    "active": user.active,
                }
                for user in filtered_users_entities
            ]

            return self.endpoint.success(
                data={
                    "users": filtered_users,
                    "count": len(filtered_users),
                    "filters": {"role": self.role, "active_only": self.active_only},
                },
                message="Users retrieved successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Search failed", status_code=500, details={"error": str(e)}
            )


@endpoint("/users/update")
class UpdateUser(Walker):
    """Update user information - another package-style endpoint."""

    user_id: str = EndpointField(description="User ID to update")

    name: Optional[str] = EndpointField(
        default=None, description="New user name", min_length=2, max_length=100
    )

    role: Optional[str] = EndpointField(
        default=None,
        description="New user role",
        examples=["user", "admin", "moderator"],
    )

    active: Optional[bool] = EndpointField(default=None, description="Active status")

    @on_visit(Root)
    async def update_user(self, here):
        try:
            user = await User.get(self.user_id)
            if not user:
                return self.endpoint.not_found(
                    message="User not found", details={"user_id": self.user_id}
                )

            # Update fields if provided
            updates = {}
            if self.name is not None:
                user.name = self.name
                updates["name"] = self.name
            if self.role is not None:
                user.role = self.role
                updates["role"] = self.role
            if self.active is not None:
                user.active = self.active
                updates["active"] = self.active

            await user.save()

            return self.endpoint.success(
                data={
                    "user_id": user.id,
                    "updated_fields": updates,
                    "current_state": {
                        "name": user.name,
                        "email": user.email,
                        "role": user.role,
                        "active": user.active,
                    },
                    "updated_at": datetime.now().isoformat(),
                },
                message="User updated successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Update failed", status_code=500, details={"error": str(e)}
            )


# ====================== RUNTIME REGISTRATION EXAMPLE ======================


def register_additional_endpoints():
    """Example of registering endpoints at runtime."""

    print("🔄 Registering additional endpoints dynamically...")

    class GetUserStats(Walker):
        """Get user statistics."""

        group_by: str = EndpointField(
            default="role",
            description="Group statistics by field",
            examples=["role", "active"],
            pattern=r"^(role|active)$",
        )

        @on_visit(Root)
        async def get_stats(self, here):
            try:
                # RECOMMENDED: Use entity-centric find and count operations
                if self.group_by == "role":
                    # Use count operations for better performance
                    admin_count = await User.count({"context.role": "admin"})
                    user_count = await User.count({"context.role": "user"})
                    moderator_count = await User.count({"context.role": "moderator"})

                    stats = {
                        "admin": admin_count,
                        "user": user_count,
                        "moderator": moderator_count,
                    }

                elif self.group_by == "active":
                    active_count = await User.count({"context.active": True})
                    inactive_count = await User.count({"context.active": False})
                    stats = {"active": active_count, "inactive": inactive_count}
                else:
                    return self.endpoint.bad_request(
                        message="Invalid group_by parameter",
                        details={"valid_options": ["role", "active"]},
                    )

                total_users = await User.count()

                return self.endpoint.success(
                    data={
                        "group_by": self.group_by,
                        "total_users": total_users,
                        "statistics": stats,
                        "generated_at": datetime.now().isoformat(),
                    },
                    message="Statistics generated successfully",
                )

            except Exception as e:
                return self.endpoint.error(
                    message="Stats generation failed",
                    status_code=500,
                    details={"error": str(e)},
                )

    # Register the endpoint dynamically
    server.register_walker_class(GetUserStats, "/users/stats", methods=["GET", "POST"])

    print("✅ Dynamic endpoint registered: /users/stats")


# ====================== CUSTOM ROUTES ======================


@endpoint("/info", methods=["GET"])
async def get_api_info():
    """Simple custom route for API information."""
    return {
        "api": "Simple Dynamic API",
        "version": "1.0.0",
        "features": [
            "Dynamic endpoint registration",
            "Package-style development",
            "Runtime endpoint addition",
            "Shared server instances",
        ],
        "endpoints": {
            "users": {
                "create": "POST /api/users/create",
                "search": "POST /api/users/search",
                "update": "POST /api/users/update",
                "stats": "GET|POST /api/users/stats (dynamic)",
            }
        },
        "timestamp": datetime.now().isoformat(),
    }


# ====================== STARTUP CONFIGURATION ======================


@server.on_startup
async def initialize_data():
    """Initialize sample data."""
    print("🔄 Initializing sample users...")

    sample_users = [
        await User.create(
            name="Alice Johnson", email="alice@example.com", role="admin"
        ),
        await User.create(name="Bob Smith", email="bob@example.com", role="user"),
        await User.create(
            name="Carol Williams", email="carol@example.com", role="moderator"
        ),
    ]

    root = await Root.get()  # type: ignore[call-arg]
    for user in sample_users:
        await root.connect(user)

    print(f"✅ Created {len(sample_users)} sample users")

    # Register additional endpoints after a short delay
    asyncio.create_task(delayed_registration())


async def delayed_registration():
    """Register additional endpoints after startup."""
    await asyncio.sleep(2)  # Wait 2 seconds
    register_additional_endpoints()


# ====================== MAIN EXECUTION ======================

if __name__ == "__main__":
    print("🌟 Simple Dynamic Registration Example")
    print("=" * 50)
    print("This example demonstrates common development patterns:")
    print("• Server instance registration with @endpoint")
    print("• Package-style registration with endpoint registry")
    print("• Runtime endpoint registration after server startup")
    print("• Shared server instances across modules")
    print()

    print("🔧 Starting server...")
    print("📖 API docs: http://127.0.0.1:8001/docs")
    print("ℹ️  API info: http://127.0.0.1:8001/info")
    print()
    print("💡 Watch the logs for dynamic endpoint registration!")
    print()

    # Run the server
    server.run(
        host="127.0.0.1",
        port=8001,
        reload=False,  # Disable reload to see our dynamic registration
    )
