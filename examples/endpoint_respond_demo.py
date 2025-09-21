"""Example demonstrating the new endpoint.response() pattern for jvspatial endpoints.

This example shows how to use the semantic endpoint response system with the
existing @walker_endpoint and @endpoint decorators, which now automatically inject
an 'endpoint' helper for flexible HTTP response creation.
"""

from typing import Any, Dict, Optional

from jvspatial.api.endpoint_router import EndpointField
from jvspatial.api.server import create_server, endpoint, walker_endpoint
from jvspatial.core.entities import Node, Walker


# Walker endpoint examples using @walker_endpoint with endpoint.response()
@walker_endpoint("/walker/users")
class UserWalker(Walker):
    """Example walker demonstrating the endpoint.response() pattern.

    The @walker_endpoint decorator now automatically injects an 'endpoint'
    helper (self.endpoint) that provides semantic response methods.
    """

    user_id: Optional[str] = EndpointField(
        default=None, description="ID of the user to retrieve"
    )
    include_profile: bool = EndpointField(
        default=False, description="Whether to include full profile information"
    )

    async def visit_user(self, node: Node) -> Any:
        """Visit a user node and return user data using self.endpoint.response()."""
        if not node.data:
            # Use self.endpoint.not_found() for 404 responses
            return self.endpoint.not_found(
                message="User not found", details={"user_id": self.user_id}
            )

        user_data = node.data.copy()

        # Simulate authorization check
        if user_data.get("private") and not self.include_profile:
            return self.endpoint.forbidden(
                message="Insufficient permissions to view user details",
                details={"required_permission": "view_profile"},
            )

        # Process data based on include_profile flag
        if not self.include_profile:
            # Remove sensitive fields for basic view
            user_data.pop("email", None)
            user_data.pop("phone", None)

        # Return successful response with user data
        return self.endpoint.success(
            data=user_data, message="User retrieved successfully"
        )

    async def visit_admin_user(self, node: Node) -> Any:
        """Visit an admin user node with custom response handling."""
        if not node.data:
            return self.endpoint.not_found("Admin user not found")

        admin_data = node.data.copy()
        admin_data["role"] = "admin"
        admin_data["permissions"] = ["read", "write", "admin"]

        # Use self.endpoint.response() with custom status and headers
        return self.endpoint.response(
            content={
                "data": admin_data,
                "message": "Admin user retrieved",
                "timestamp": "2025-09-21T06:28:17Z",
            },
            status_code=200,
            headers={"X-User-Role": "admin", "X-Admin-Access": "granted"},
        )


@walker_endpoint("/walker/users/create", methods=["POST"])
class CreateUserWalker(Walker):
    """Walker for creating new users using self.endpoint.created()."""

    username: str = EndpointField(description="Username for the new user")
    email: str = EndpointField(description="Email address for the new user")
    full_name: Optional[str] = EndpointField(
        default=None, description="Full name of the user"
    )

    async def visit_user_collection(self, node: Node) -> Any:
        """Create a new user in the collection."""
        # Simulate validation
        if self.username in ["admin", "root", "system"]:
            return self.endpoint.conflict(
                message="Username is reserved",
                details={
                    "username": self.username,
                    "reserved_usernames": ["admin", "root", "system"],
                },
            )

        # Simulate email validation
        if "@" not in self.email:
            return self.endpoint.unprocessable_entity(
                message="Invalid email format",
                details={"email": self.email, "required_format": "user@domain.com"},
            )

        # Create new user data
        user_data = {
            "id": f"user_{self.username}",
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name or self.username.title(),
            "created_at": "2025-09-21T06:28:17Z",
            "status": "active",
        }

        # Return created response (201 status)
        return self.endpoint.created(
            data=user_data,
            message="User created successfully",
            headers={"Location": f"/users/{user_data['id']}"},
        )


# Function endpoint examples using @endpoint decorator
@endpoint("/function/health")
async def health_check(endpoint) -> Any:
    """Simple health check endpoint using @endpoint decorator.

    The @endpoint decorator automatically injects the 'endpoint' parameter
    for function-based endpoints.
    """
    return endpoint.success(
        data={"status": "healthy", "version": "1.0.0"}, message="Service is running"
    )


@endpoint("/function/users/{user_id}/status", methods=["PUT"])
async def update_user_status(user_id: str, status: str, endpoint) -> Any:
    """Update user status using @endpoint decorator with validation."""
    # Simulate validation
    valid_statuses = ["active", "inactive", "suspended"]
    if status not in valid_statuses:
        return endpoint.bad_request(
            message="Invalid status value",
            details={"provided": status, "valid_options": valid_statuses},
        )

    # Simulate user lookup
    if user_id.startswith("invalid_"):
        return endpoint.not_found(
            message="User not found", details={"user_id": user_id}
        )

    # Simulate status update
    user_data = {"id": user_id, "status": status, "updated_at": "2025-09-21T06:28:17Z"}

    return endpoint.success(data=user_data, message=f"User status updated to {status}")


@endpoint("/function/admin/reset", methods=["POST"])
async def admin_reset(confirm: bool, endpoint) -> Any:
    """Admin reset endpoint demonstrating error responses."""
    if not confirm:
        return endpoint.bad_request(
            message="Confirmation required for reset operation",
            details={"required_parameter": "confirm=true"},
        )

    # Simulate authorization check (would normally check JWT, API key, etc.)
    return endpoint.unauthorized(
        message="Admin credentials required",
        details={"required_role": "admin", "auth_method": "bearer_token"},
    )


# Example with custom response handling using endpoint.response()
@endpoint("/function/data/export", methods=["GET"])
async def export_data(format: str, endpoint) -> Any:
    """Export data with custom response format using endpoint.response()."""
    supported_formats = ["json", "csv", "xml"]

    if format not in supported_formats:
        return endpoint.error(
            message="Unsupported export format",
            status_code=406,  # Not Acceptable
            details={
                "requested_format": format,
                "supported_formats": supported_formats,
            },
        )

    # Simulate data export
    export_data = {
        "format": format,
        "records": 1500,
        "export_id": "exp_20250921_062817",
        "download_url": f"/downloads/export_{format}_20250921.{format}",
    }

    # Use flexible endpoint.response() with custom headers
    return endpoint.response(
        content={"data": export_data, "message": f"Data exported in {format} format"},
        status_code=200,
        headers={
            "Content-Type": "application/json",
            "X-Export-Format": format,
            "X-Record-Count": "1500",
        },
    )


# Example showing no-content response
@endpoint("/function/cache/clear", methods=["DELETE"])
async def clear_cache(endpoint) -> Any:
    """Clear cache endpoint returning 204 No Content."""
    # Simulate cache clearing operation
    return endpoint.no_content(headers={"X-Cache-Status": "cleared"})


# Example of a mixed walker that shows different response patterns
@walker_endpoint("/walker/analytics")
class AnalyticsWalker(Walker):
    """Walker showing various endpoint response patterns."""

    metric_type: str = EndpointField(
        description="Type of analytics metric to retrieve",
        examples=["users", "sessions", "pageviews"],
    )
    days: int = EndpointField(
        default=7, description="Number of days to include in analytics"
    )

    async def visit_analytics_node(self, node: Node) -> Any:
        """Generate analytics data with various response patterns."""
        if self.days < 1 or self.days > 365:
            return self.endpoint.bad_request(
                message="Invalid days parameter",
                details={"days": self.days, "valid_range": "1-365"},
            )

        if self.metric_type not in ["users", "sessions", "pageviews"]:
            return self.endpoint.error(
                message="Unknown metric type",
                status_code=422,
                details={"metric_type": self.metric_type},
            )

        # Simulate analytics data generation
        analytics_data = {
            "metric_type": self.metric_type,
            "period_days": self.days,
            "total": 15000,
            "daily_average": 15000 // self.days,
            "generated_at": "2025-09-21T06:28:17Z",
        }

        return self.endpoint.success(
            data=analytics_data, message=f"Analytics for {self.metric_type} retrieved"
        )


# Function endpoint with complex error handling
@endpoint("/function/batch/process", methods=["POST"])
async def batch_process(items: list, validate: bool, endpoint) -> Any:
    """Batch processing endpoint with detailed error handling."""
    if not items:
        return endpoint.bad_request(
            message="Items list cannot be empty",
            details={"items_count": len(items), "minimum_required": 1},
        )

    if len(items) > 100:
        return endpoint.error(
            message="Too many items in batch",
            status_code=413,  # Payload Too Large
            details={"items_count": len(items), "maximum_allowed": 100},
        )

    # Simulate processing
    if validate:
        # Simulate validation errors
        invalid_items = [item for item in items if not isinstance(item, dict)]
        if invalid_items:
            return endpoint.unprocessable_entity(
                message="Invalid items found in batch",
                details={
                    "invalid_items": len(invalid_items),
                    "total_items": len(items),
                    "error": "All items must be objects",
                },
            )

    # Simulate successful batch processing
    result = {
        "processed": len(items),
        "successful": len(items) - 1,  # Simulate one failure
        "failed": 1,
        "batch_id": "batch_20250921_062817",
        "status": "completed",
    }

    return endpoint.success(
        data=result,
        message="Batch processing completed",
        headers={"X-Batch-ID": result["batch_id"]},
    )


# Example showing the flexibility of endpoint.response() for custom scenarios
@endpoint("/function/custom/challenge", methods=["GET"])
async def custom_challenge(difficulty: str, endpoint) -> Any:
    """Custom endpoint demonstrating full flexibility of endpoint.response()."""

    challenge_data = {
        "difficulty": difficulty,
        "challenge_id": f"challenge_{difficulty}_20250921",
        "created_at": "2025-09-21T06:28:17Z",
    }

    # Custom logic based on difficulty
    if difficulty == "easy":
        return endpoint.response(
            content={
                "message": "Easy challenge created",
                "data": challenge_data,
                "hints": ["Start simple", "Take your time"],
            },
            status_code=200,
            headers={"X-Challenge-Level": "1", "X-Time-Limit": "3600"},  # 1 hour
        )
    elif difficulty == "hard":
        return endpoint.response(
            content={
                "message": "Hard challenge created",
                "data": challenge_data,
                "warnings": ["Time limit enforced", "No hints available"],
            },
            status_code=201,  # Created for hard challenges
            headers={"X-Challenge-Level": "5", "X-Time-Limit": "1800"},  # 30 minutes
        )
    elif difficulty == "extreme":
        return endpoint.response(
            content={
                "message": "Extreme challenge created",
                "data": challenge_data,
                "disclaimers": ["Success rate: 5%", "Attempts are limited"],
            },
            status_code=202,  # Accepted for extreme challenges
            headers={
                "X-Challenge-Level": "10",
                "X-Time-Limit": "900",  # 15 minutes
                "X-Attempts-Allowed": "3",
            },
        )
    else:
        return endpoint.bad_request(
            message="Invalid difficulty level",
            details={
                "provided": difficulty,
                "valid_options": ["easy", "hard", "extreme"],
            },
        )


if __name__ == "__main__":
    # Create server instance to register endpoints
    server = create_server(
        title="Endpoint Response Demo API",
        description="Demonstrating the endpoint.response() pattern",
        version="1.0.0",
        debug=True,
    )

    print("Enhanced endpoint.response() pattern examples:")
    print("==============================================")
    print()
    print("Walker endpoints (@walker_endpoint):")
    print(
        "  POST /walker/users                - Get user with self.endpoint.response()"
    )
    print(
        "  POST /walker/users/create         - Create user with self.endpoint.created()"
    )
    print(
        "  POST /walker/analytics            - Analytics with self.endpoint.success()"
    )
    print()
    print("Function endpoints (@endpoint):")
    print("  POST /function/health             - Health check with endpoint.success()")
    print("  PUT  /function/users/{id}/status  - Update with validation using endpoint")
    print(
        "  POST /function/admin/reset        - Admin endpoint with endpoint.unauthorized()"
    )
    print(
        "  GET  /function/data/export        - Custom response with endpoint.response()"
    )
    print("  DELETE /function/cache/clear      - No content with endpoint.no_content()")
    print("  POST /function/batch/process      - Complex batch processing with errors")
    print(
        "  GET  /function/custom/challenge   - Full flexibility with endpoint.response()"
    )
    print()
    print("Key features:")
    print("  • @walker_endpoint injects 'self.endpoint' helper into walker instances")
    print("  • @endpoint injects 'endpoint' parameter into function parameters")
    print("  • Semantic methods: .success(), .error(), .created(), .not_found(), etc.")
    print("  • Flexible .response() for custom status codes, headers, and content")
    print("  • Uses EndpointField for walker field configuration")
    print("  • Maintains existing jvspatial patterns and decorator names")
    print("  • Works with existing server discovery and registration")
    print()
    print("Available endpoint methods:")
    print("  • endpoint.response(content, status_code, headers) - Flexible response")
    print("  • endpoint.success(data, message, headers)       - 200 OK")
    print("  • endpoint.created(data, message, headers)       - 201 Created")
    print("  • endpoint.no_content(headers)                   - 204 No Content")
    print("  • endpoint.bad_request(message, details, headers) - 400 Bad Request")
    print("  • endpoint.unauthorized(message, details, headers) - 401 Unauthorized")
    print("  • endpoint.forbidden(message, details, headers)  - 403 Forbidden")
    print("  • endpoint.not_found(message, details, headers)  - 404 Not Found")
    print("  • endpoint.conflict(message, details, headers)   - 409 Conflict")
    print("  • endpoint.unprocessable_entity(message, details, headers) - 422")
    print("  • endpoint.error(message, status_code, details, headers) - Custom error")
    print()
    print("Usage pattern:")
    print("  return self.endpoint.success(data=result)       # In walkers")
    print("  return endpoint.created(data=new_item)          # In functions")
    print("  return endpoint.response(content, status=202)   # Custom responses")
    print()
    print("Start the server with: server.run(host='127.0.0.1', port=8000)")
