"""
Example demonstrating authentication and authorization in jvspatial.

This example shows:
1. Setting up JWT authentication
2. API key authentication
3. Role-based access control (RBAC)
4. Protected endpoints
5. Permission-based access

Required environment variables:
JVSPATIAL_JWT_SECRET=your-secret-key
JVSPATIAL_JWT_ALGORITHM=HS256
JVSPATIAL_API_KEY=your-api-key
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from jvspatial.api import Server
from jvspatial.api.auth.decorators import (
    auth_endpoint,
    auth_walker_endpoint,
    require_authenticated_user,
)
from jvspatial.api.auth.middleware import get_current_user
from jvspatial.api.endpoint.types import APIResponse
from jvspatial.core import on_visit
from jvspatial.core.entities import Node, Walker

# Configure server - this will be initialized in main()
server = Server(
    title="Auth Example API",
    description="API demonstrating authentication and authorization",
    version="1.0.0",
    auth_enabled=True,
    jwt_auth_enabled=True,
    api_key_auth_enabled=True,
)


# Define our data models
class User(Node):
    """User with role-based permissions."""

    username: str = ""
    email: str = ""
    roles: List[str] = []
    is_active: bool = True
    last_login: Optional[datetime] = None


class Document(Node):
    """Document with access controls."""

    title: str = ""
    content: str = ""
    owner: str = ""  # User ID
    created_at: datetime = datetime.now()
    access_level: str = "public"  # public, private, restricted


# Walker for document access
@auth_walker_endpoint(
    "/api/documents/process", methods=["POST"], permissions=["read_documents"]
)
class DocumentProcessor(Walker):
    """Process documents with permission checks."""

    access_level: str = "public"

    @on_visit(Document)
    async def process_document(self, here: Document):
        """Process document if user has access."""
        current_user = await require_authenticated_user(self.endpoint.request)

        # Admin can access everything
        if "admin" in current_user.roles:
            self.report(
                {
                    "document": {
                        "id": here.id,
                        "title": here.title,
                        "content": here.content,
                        "access": "admin",
                    }
                }
            )
            return

        # Check access level
        if here.access_level == "private" and here.owner != current_user.id:
            # Skip private documents not owned by user
            self.skip()
            return

        if here.access_level == "restricted" and "manager" not in current_user.roles:
            # Skip restricted documents if not a manager
            self.skip()
            return

        # User has access - process document
        self.report(
            {
                "document": {
                    "id": here.id,
                    "title": here.title,
                    "content": here.content,
                    "access": here.access_level,
                }
            }
        )


# API endpoints
@auth_endpoint("/api/users/profile", methods=["GET"])
async def get_user_profile(endpoint) -> APIResponse:
    """Get current user's profile."""
    current_user = await require_authenticated_user(endpoint.request)
    user = await User.get(current_user.id)

    if not user:
        return endpoint.not_found(
            message="User profile not found", details={"user_id": current_user.id}
        )

    return endpoint.success(
        data={
            "username": user.username,
            "email": user.email,
            "roles": user.roles,
            "is_active": user.is_active,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }
    )


@auth_endpoint("/api/documents", methods=["POST"], permissions=["create_documents"])
async def create_document(
    title: str, content: str, access_level: str, endpoint
) -> APIResponse:
    """Create a new document."""
    current_user = await require_authenticated_user(endpoint.request)

    # Validate access level
    if access_level not in ["public", "private", "restricted"]:
        return endpoint.bad_request(
            message="Invalid access level",
            details={
                "provided": access_level,
                "allowed": ["public", "private", "restricted"],
            },
        )

    # Only admins/managers can create restricted documents
    if access_level == "restricted" and not any(
        role in current_user.roles for role in ["admin", "manager"]
    ):
        return endpoint.forbidden(
            message="Insufficient permissions to create restricted documents",
            details={"required_roles": ["admin", "manager"]},
        )

    # Create document
    doc = await Document.create(
        title=title,
        content=content,
        owner=current_user.id,
        access_level=access_level,
        created_at=datetime.now(),
    )

    return endpoint.created(
        data={
            "id": doc.id,
            "title": doc.title,
            "access_level": doc.access_level,
            "created_at": doc.created_at.isoformat(),
        },
        message="Document created successfully",
    )


async def create_sample_data():
    """Create sample users and documents."""
    # Create users with different roles
    admin = await User.create(
        username="admin", email="admin@example.com", roles=["admin"], is_active=True
    )

    manager = await User.create(
        username="manager",
        email="manager@example.com",
        roles=["manager"],
        is_active=True,
    )

    user = await User.create(
        username="user", email="user@example.com", roles=["user"], is_active=True
    )

    # Create documents with different access levels
    await Document.create(
        title="Public Document",
        content="This is viewable by anyone",
        owner=user.id,
        access_level="public",
    )

    await Document.create(
        title="Private Document",
        content="This is only viewable by the owner",
        owner=user.id,
        access_level="private",
    )

    await Document.create(
        title="Restricted Document",
        content="This is only viewable by managers and admins",
        owner=manager.id,
        access_level="restricted",
    )


async def cleanup_data():
    """Clean up sample data."""
    # Clean up users
    users = await User.all()
    for user in users:
        await user.delete()

    # Clean up documents
    docs = await Document.all()
    for doc in docs:
        await doc.delete()


def configure_server():
    """Configure the server with authentication settings."""
    global server

    # Load settings from environment (in a real app, use env vars)
    import os

    server.auth_config.update(
        jwt_secret_key=os.getenv("JVSPATIAL_JWT_SECRET", "your-secret-key"),
        jwt_algorithm=os.getenv("JVSPATIAL_JWT_ALGORITHM", "HS256"),
        jwt_expiration_hours=int(os.getenv("JVSPATIAL_JWT_EXPIRATION_HOURS", "24")),
        api_keys=os.getenv("JVSPATIAL_API_KEYS", "your-api-key").split(","),
    )

    return server


async def main():
    """Run the example."""
    print("Setting up server...")
    server = configure_server()

    print("Cleaning up old data...")
    await cleanup_data()

    print("Creating sample data...")
    await create_sample_data()

    print("\nServer configured with:")
    print("- JWT authentication")
    print("- API key authentication")
    print("- Role-based access control")
    print("- Permission-based endpoint protection")

    print("\nAvailable endpoints:")
    print("GET  /api/users/profile - Get current user profile (requires auth)")
    print("POST /api/documents - Create new document (requires auth + permissions)")
    print(
        "POST /api/documents/process - Process documents (requires auth + permissions)"
    )

    print("\nStarting server...")
    server.run()

    # Clean up will be handled by SIGINT/SIGTERM handlers
    print("\nServer stopped, cleaning up...")
    await cleanup_data()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
