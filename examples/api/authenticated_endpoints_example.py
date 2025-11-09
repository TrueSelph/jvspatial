"""Authenticated CRUD API Example

This example demonstrates a realistic CRUD API using the unified @endpoint decorator
with both functions and Walker classes. It showcases proper authentication, authorization,
response schemas, and real-world API patterns using the persistence layer.

Usage:
    python authenticated_endpoints_example.py
    Then visit http://localhost:8000/docs to see the Swagger UI

Key Features:
- Complete CRUD operations for Users and Products
- Proper authentication and authorization
- Realistic response schemas with examples
- Permission-based access control
- Automatic OpenAPI schema generation
- Walker-based complex operations
- Real persistence using the graph database
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from jvspatial.api import Server, endpoint
from jvspatial.api.decorators import EndpointField
from jvspatial.api.endpoints.response import (
    ResponseField,
    error_response,
    response_schema,
    success_response,
)
from jvspatial.core import Node, Walker

# =============================================================================
# DATA MODELS
# =============================================================================


class UserNode(Node):
    """User node in the graph database."""

    name: str = ""
    email: str = ""
    role: str = "user"
    department: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login: Optional[str] = None


class ProductNode(Node):
    """Product node in the graph database."""

    name: str = ""
    price: float = 0.0
    category: str = ""
    stock: int = 0
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# =============================================================================
# SERVER SETUP
# =============================================================================

# Create server with authentication enabled
server = Server(
    title="Authenticated CRUD API Example",
    description="Realistic CRUD API showcasing @endpoint decorator with authentication and response schemas",
    version="1.0.0",
    host="127.0.0.1",
    port=8000,
    # Database configuration
    db_type="json",
    db_path="./jvdb",
    # Enable authentication
    auth_enabled=True,
    jwt_auth_enabled=True,
    jwt_secret="demo-secret-key-2024",  # pragma: allowlist secret
    jwt_expire_minutes=60,
)

# Server is automatically set as current server upon instantiation

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

# Note: Authentication endpoints are automatically registered by the server
# when auth_enabled=True. These are provided by the jvspatial library:
# - POST /auth/register (user registration)
# - POST /auth/login (user login)
# - POST /auth/logout (user logout)

# =============================================================================
# SYSTEM ENDPOINTS
# =============================================================================


@endpoint(
    "/health",
    methods=["GET"],
    response=success_response(
        data={
            "status": ResponseField(
                field_type=str,
                description="Health status of the service",
                example="healthy",
            ),
            "timestamp": ResponseField(
                field_type=str,
                description="Current timestamp",
                example="2024-01-01T00:00:00Z",
            ),
            "version": ResponseField(
                field_type=str, description="Service version", example="1.0.0"
            ),
            "uptime": ResponseField(
                field_type=str, description="Service uptime", example="2d 14h 32m"
            ),
        }
    ),
)
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "uptime": "2d 14h 32m",
    }


# =============================================================================
# USER MANAGEMENT ENDPOINTS
# =============================================================================


@endpoint(
    "/users",
    methods=["GET"],
    auth=True,
    permissions=["read_users"],
    response=success_response(
        data={
            "users": ResponseField(
                field_type=List[Dict[str, Any]],
                description="List of users",
                example=[
                    {
                        "id": "1",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "role": "user",
                    },
                    {
                        "id": "2",
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                        "role": "admin",
                    },
                ],
            ),
            "total": ResponseField(
                field_type=int, description="Total number of users", example=2
            ),
            "page": ResponseField(
                field_type=int, description="Current page number", example=1
            ),
            "per_page": ResponseField(
                field_type=int, description="Number of users per page", example=10
            ),
            "total_pages": ResponseField(
                field_type=int, description="Total number of pages", example=5
            ),
            "has_previous": ResponseField(
                field_type=bool,
                description="Whether there's a previous page",
                example=False,
            ),
            "has_next": ResponseField(
                field_type=bool, description="Whether there's a next page", example=True
            ),
            "previous_page": ResponseField(
                field_type=Optional[int], description="Previous page number", example=None  # type: ignore[arg-type]
            ),
            "next_page": ResponseField(
                field_type=Optional[int], description="Next page number", example=2  # type: ignore[arg-type]
            ),
        }
    ),
)
async def list_users(
    page: int = 1,
    per_page: int = 10,
    search: Optional[str] = None,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """List all users with pagination and filtering."""
    from jvspatial.core.pager import ObjectPager

    # Build filters for pagination
    filters = {}
    if role:
        filters["context.role"] = role

    # Create pager with filters
    pager = ObjectPager(UserNode, page_size=per_page, filters=filters)

    # Get the requested page
    users: List[Any] = await pager.get_page(page=page)

    # Apply text search if provided (post-filter on results)
    if search:
        search_lower = search.lower()
        users = [
            u
            for u in users
            if search_lower in u.name.lower() or search_lower in u.email.lower()
        ]

    # Convert to dictionaries using export
    users_list = [u.export(exclude={"updated_at", "last_login"}) for u in users]

    # Get pagination info from pager
    pagination_info = pager.to_dict()

    return {
        "users": users_list,
        "total": pagination_info["total_items"],
        "page": pagination_info["current_page"],
        "per_page": pagination_info["page_size"],
        "total_pages": pagination_info["total_pages"],
        "has_previous": pagination_info["has_previous"],
        "has_next": pagination_info["has_next"],
        "previous_page": pagination_info["previous_page"],
        "next_page": pagination_info["next_page"],
    }


@endpoint(
    "/users",
    methods=["POST"],
    auth=True,
    permissions=["create_users"],
    response=success_response(
        data={
            "user": ResponseField(
                field_type=Dict[str, Any],
                description="Created user information",
                example={
                    "id": "4",
                    "name": "New User",
                    "email": "new@example.com",
                    "role": "user",
                    "created_at": "2024-01-04T00:00:00Z",
                },
            ),
            "message": ResponseField(
                field_type=str,
                description="Success message",
                example="User created successfully",
            ),
        }
    ),
)
async def create_user(
    name: str, email: str, role: str = "user", department: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new user."""
    # Check if user with this email already exists using entity-centric approach
    existing = await UserNode.find(email=email)
    if existing:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409, detail="User with this email already exists"
        )

    # Create new user node using entity-centric approach
    user = await UserNode.create(
        name=name,
        email=email,
        role=role,
        department=department,
        created_at=datetime.now().isoformat(),
    )

    return {
        "user": user.export(),
        "message": "User created successfully",
    }


@endpoint(
    "/users/{user_id}",
    methods=["GET"],
    auth=True,
    permissions=["read_users"],
    response=success_response(
        data={
            "user": ResponseField(
                field_type=Dict[str, Any],
                description="User information",
                example={
                    "id": "1",
                    "name": "John Doe",
                    "email": "john@example.com",
                    "role": "user",
                    "created_at": "2024-01-01T00:00:00Z",
                },
            )
        }
    ),
)
async def get_user(user_id: str) -> Dict[str, Any]:
    """Get a specific user by ID."""
    # Retrieve user using entity-centric approach
    user = await UserNode.get(user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")

    return {"user": user.export()}


@endpoint(
    "/users/{user_id}",
    methods=["PUT"],
    auth=True,
    permissions=["update_users"],
    response=success_response(
        data={
            "user": ResponseField(
                field_type=Dict[str, Any],
                description="Updated user information",
                example={
                    "id": "1",
                    "name": "John Doe Updated",
                    "email": "john.updated@example.com",
                    "role": "user",
                    "updated_at": "2024-01-15T12:00:00Z",
                },
            ),
            "message": ResponseField(
                field_type=str,
                description="Success message",
                example="User updated successfully",
            ),
        }
    ),
)
async def update_user(
    user_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    department: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a user."""
    # Retrieve user using entity-centric approach
    user = await UserNode.get(user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")

    # Update fields if provided
    if name is not None:
        user.name = name
    if email is not None:
        # Check if email is already taken by another user
        existing = await UserNode.find(email=email)
        if existing and existing[0].id != user_id:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=409, detail="Email already in use by another user"
            )
        user.email = email
    if role is not None:
        user.role = role
    if department is not None:
        user.department = department

    user.updated_at = datetime.now().isoformat()

    # Save the updated user using entity-centric approach
    await user.save()

    return {
        "user": user.export(),
        "message": "User updated successfully",
    }


@endpoint(
    "/users/{user_id}",
    methods=["DELETE"],
    auth=True,
    permissions=["delete_users"],
    response=success_response(
        data={
            "message": ResponseField(
                field_type=str,
                description="Success message",
                example="User deleted successfully",
            ),
            "deleted_user_id": ResponseField(
                field_type=str, description="ID of the deleted user", example="1"
            ),
        }
    ),
)
async def delete_user(user_id: str) -> Dict[str, Any]:
    """Delete a user."""
    # Retrieve user using entity-centric approach
    user = await UserNode.get(user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")

    # Delete user using entity-centric approach
    await user.delete()

    return {"message": "User deleted successfully", "deleted_user_id": user_id}


# =============================================================================
# PRODUCT MANAGEMENT ENDPOINTS
# =============================================================================


@endpoint(
    "/products",
    methods=["GET"],
    auth=True,
    permissions=["read_products"],
    response=success_response(
        data={
            "products": ResponseField(
                field_type=List[Dict[str, Any]],
                description="List of products",
                example=[
                    {
                        "id": "1",
                        "name": "Laptop",
                        "price": 999.99,
                        "category": "Electronics",
                        "stock": 50,
                    },
                    {
                        "id": "2",
                        "name": "Book",
                        "price": 19.99,
                        "category": "Education",
                        "stock": 100,
                    },
                ],
            ),
            "total": ResponseField(
                field_type=int, description="Total number of products", example=2
            ),
            "page": ResponseField(
                field_type=int, description="Current page number", example=1
            ),
            "per_page": ResponseField(
                field_type=int, description="Number of products per page", example=10
            ),
            "total_pages": ResponseField(
                field_type=int, description="Total number of pages", example=1
            ),
            "has_previous": ResponseField(
                field_type=bool,
                description="Whether there's a previous page",
                example=False,
            ),
            "has_next": ResponseField(
                field_type=bool,
                description="Whether there's a next page",
                example=False,
            ),
            "previous_page": ResponseField(
                field_type=Optional[int],  # type: ignore[arg-type]
                description="Previous page number",
                example=None,
            ),
            "next_page": ResponseField(
                field_type=Optional[int], description="Next page number", example=None  # type: ignore[arg-type]
            ),
        }
    ),
)
async def list_products(
    page: int = 1,
    per_page: int = 10,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: bool = True,
) -> Dict[str, Any]:
    """List products with pagination and filtering."""
    from jvspatial.core.pager import ObjectPager

    # Build filters for pagination
    filters = {}
    if category:
        filters["context.category"] = category

    # Create pager with filters
    pager = ObjectPager(ProductNode, page_size=per_page, filters=filters)

    # Get the requested page
    products: List[Any] = await pager.get_page(page=page)

    # Apply price filters and stock filter (post-filter on results)
    if min_price is not None:
        products = [p for p in products if p.price >= min_price]
    if max_price is not None:
        products = [p for p in products if p.price <= max_price]
    if in_stock:
        products = [p for p in products if p.stock > 0]

    # Convert to dictionaries using export
    products_list = [p.export(exclude={"updated_at"}) for p in products]

    # Get pagination info from pager
    pagination_info = pager.to_dict()

    return {
        "products": products_list,
        "total": pagination_info["total_items"],
        "page": pagination_info["current_page"],
        "per_page": pagination_info["page_size"],
        "total_pages": pagination_info["total_pages"],
        "has_previous": pagination_info["has_previous"],
        "has_next": pagination_info["has_next"],
        "previous_page": pagination_info["previous_page"],
        "next_page": pagination_info["next_page"],
    }


@endpoint(
    "/products",
    methods=["POST"],
    auth=True,
    permissions=["create_products"],
    response=success_response(
        data={
            "product": ResponseField(
                field_type=Dict[str, Any],
                description="Created product information",
                example={
                    "id": "4",
                    "name": "New Product",
                    "price": 49.99,
                    "category": "General",
                    "stock": 25,
                    "created_at": "2024-01-04T00:00:00Z",
                },
            ),
            "message": ResponseField(
                field_type=str,
                description="Success message",
                example="Product created successfully",
            ),
        }
    ),
)
async def create_product(
    name: str,
    price: float,
    category: str,
    stock: int = 0,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new product."""
    # Create new product node using entity-centric approach
    product = await ProductNode.create(
        name=name,
        price=price,
        category=category,
        stock=stock,
        description=description,
        created_at=datetime.now().isoformat(),
    )

    return {
        "product": product.export(),
        "message": "Product created successfully",
    }


@endpoint(
    "/products/{product_id}",
    methods=["GET"],
    auth=True,
    permissions=["read_products"],
    response=success_response(
        data={
            "product": ResponseField(
                field_type=Dict[str, Any],
                description="Product information",
                example={
                    "id": "1",
                    "name": "Laptop",
                    "price": 999.99,
                    "category": "Electronics",
                    "stock": 50,
                    "created_at": "2024-01-01T00:00:00Z",
                },
            )
        }
    ),
)
async def get_product(product_id: str) -> Dict[str, Any]:
    """Get a specific product by ID."""
    # Retrieve product using entity-centric approach
    product = await ProductNode.get(product_id)
    if not product:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Product not found")

    return {"product": product.export()}


@endpoint(
    "/products/{product_id}",
    methods=["PUT"],
    auth=True,
    permissions=["update_products"],
    response=success_response(
        data={
            "product": ResponseField(
                field_type=Dict[str, Any],
                description="Updated product information",
                example={
                    "id": "1",
                    "name": "Laptop Updated",
                    "price": 1099.99,
                    "category": "Electronics",
                    "stock": 45,
                    "updated_at": "2024-01-15T12:00:00Z",
                },
            ),
            "message": ResponseField(
                field_type=str,
                description="Success message",
                example="Product updated successfully",
            ),
        }
    ),
)
async def update_product(
    product_id: str,
    name: Optional[str] = None,
    price: Optional[float] = None,
    category: Optional[str] = None,
    stock: Optional[int] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a product."""
    # Retrieve product using entity-centric approach
    product = await ProductNode.get(product_id)
    if not product:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Product not found")

    # Update fields if provided
    if name is not None:
        product.name = name
    if price is not None:
        product.price = price
    if category is not None:
        product.category = category
    if stock is not None:
        product.stock = stock
    if description is not None:
        product.description = description

    product.updated_at = datetime.now().isoformat()

    # Save the updated product using entity-centric approach
    await product.save()

    return {
        "product": product.export(),
        "message": "Product updated successfully",
    }


@endpoint(
    "/products/{product_id}",
    methods=["DELETE"],
    auth=True,
    permissions=["delete_products"],
    response=success_response(
        data={
            "message": ResponseField(
                field_type=str,
                description="Success message",
                example="Product deleted successfully",
            ),
            "deleted_product_id": ResponseField(
                field_type=str, description="ID of the deleted product", example="1"
            ),
        }
    ),
)
async def delete_product(product_id: str) -> Dict[str, Any]:
    """Delete a product."""
    # Retrieve product using entity-centric approach
    product = await ProductNode.get(product_id)
    if not product:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Product not found")

    # Delete product using entity-centric approach
    await product.delete()

    return {
        "message": "Product deleted successfully",
        "deleted_product_id": product_id,
    }


# =============================================================================
# ANALYTICS AND REPORTING WALKERS
# =============================================================================


@endpoint(
    "/analytics/users",
    methods=["POST"],
    auth=True,
    permissions=["read_analytics"],
    response=success_response(
        data={
            "analysis": ResponseField(
                field_type=Dict[str, Any],
                description="User analysis results",
                example={
                    "total_users": 150,
                    "active_users": 120,
                    "new_users_this_month": 25,
                    "departments": {
                        "engineering": 45,
                        "marketing": 30,
                        "sales": 40,
                        "support": 35,
                    },
                    "engagement_score": 8.5,
                },
            ),
            "insights": ResponseField(
                field_type=List[str],
                description="Key insights from the analysis",
                example=[
                    "High user engagement in engineering",
                    "Growth opportunity in sales",
                    "Support team needs more resources",
                ],
            ),
            "recommendations": ResponseField(
                field_type=List[str],
                description="Actionable recommendations",
                example=[
                    "Increase marketing budget",
                    "Hire more support staff",
                    "Implement user training program",
                ],
            ),
            "generated_at": ResponseField(
                field_type=str,
                description="Analysis generation timestamp",
                example="2024-01-15T14:30:00Z",
            ),
        }
    ),
)
class UserAnalyticsWalker(Walker):
    """Analyze user data and generate insights."""

    department: str = EndpointField(
        default="all",
        description="Department to analyze",
        examples=["engineering", "marketing", "sales", "support", "all"],
    )

    # These properties will automatically be exposed as endpoint parameters
    include_inactive: bool = True
    time_period: str = "30d"  # 7d, 30d, 90d, 1y
    analysis_depth: str = "comprehensive"  # basic, detailed, comprehensive
    include_predictions: bool = False

    async def analyze_users(self) -> Dict[str, Any]:
        """Analyze users and generate insights using real data."""
        # Query all users from database using entity-centric approach
        if self.department != "all":
            all_users = await UserNode.find(department=self.department)
        else:
            all_users = await UserNode.find()

        # Calculate statistics
        total_users = len(all_users)
        active_users = (
            total_users  # Assume all users are active if include_inactive is True
        )
        if not self.include_inactive:
            # Filter out users who haven't logged in recently
            # For this example, we'll consider users with last_login as active
            active_users = len([u for u in all_users if u.last_login])

        # Count by department
        departments: Dict[str, int] = {}
        for user in all_users:
            dept = user.department or "unassigned"
            departments[dept] = departments.get(dept, 0) + 1

        # Calculate new users based on time period
        now = datetime.now()
        cutoff_days = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365,
        }.get(self.time_period, 30)

        new_users = 0
        for user in all_users:
            if user.created_at:
                try:
                    created = datetime.fromisoformat(
                        user.created_at.replace("Z", "+00:00")
                    )
                    days_ago = (now - created.replace(tzinfo=None)).days
                    if days_ago <= cutoff_days:
                        new_users += 1
                except (ValueError, AttributeError):
                    pass

        # Generate insights
        insights = []
        if total_users > 0:
            insights.append(
                f"Total of {total_users} users in {'all departments' if self.department == 'all' else self.department}"
            )
            if active_users < total_users * 0.8:
                insights.append("Low user engagement detected")
            if new_users > total_users * 0.2:
                insights.append("High growth rate observed")
        else:
            insights.append("No users found in the database")

        # Recommendations
        recommendations = []
        if total_users > 0:
            if len(departments) < 3:
                recommendations.append("Consider diversifying departments")
            if active_users < total_users * 0.7:
                recommendations.append("Implement user engagement campaigns")
            if new_users < total_users * 0.1:
                recommendations.append("Increase user acquisition efforts")

        if self.include_predictions:
            insights.append(
                f"Predicted growth: {int(new_users * 1.15)} new users next period"
            )
            recommendations.append("Prepare infrastructure for user growth")

        return {
            "analysis": {
                "total_users": total_users,
                "active_users": active_users,
                "new_users_this_month": new_users,
                "departments": departments,
                "engagement_score": (
                    round(active_users / total_users * 10, 1) if total_users > 0 else 0
                ),
                "time_period": self.time_period,
                "analysis_depth": self.analysis_depth,
            },
            "insights": insights,
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat(),
        }


@endpoint(
    "/analytics/products",
    methods=["POST"],
    auth=True,
    permissions=["read_analytics"],
    response=success_response(
        data={
            "sales_summary": ResponseField(
                field_type=Dict[str, Any],
                description="Product sales summary",
                example={
                    "total_revenue": 125000.50,
                    "units_sold": 250,
                    "top_selling_category": "Electronics",
                    "average_order_value": 500.00,
                },
            ),
            "product_performance": ResponseField(
                field_type=List[Dict[str, Any]],
                description="Individual product performance",
                example=[
                    {
                        "product_id": "1",
                        "name": "Laptop",
                        "revenue": 50000.00,
                        "units_sold": 50,
                        "growth_rate": 15.5,
                    },
                    {
                        "product_id": "2",
                        "name": "Book",
                        "revenue": 2000.00,
                        "units_sold": 100,
                        "growth_rate": -5.2,
                    },
                ],
            ),
            "trends": ResponseField(
                field_type=List[str],
                description="Sales trends and patterns",
                example=[
                    "Electronics showing strong growth",
                    "Education category declining",
                    "Seasonal patterns detected",
                ],
            ),
            "generated_at": ResponseField(
                field_type=str,
                description="Analysis generation timestamp",
                example="2024-01-15T14:30:00Z",
            ),
        }
    ),
)
class ProductAnalyticsWalker(Walker):
    """Analyze product performance and sales data."""

    category: str = EndpointField(
        default="all",
        description="Product category to analyze",
        examples=["Electronics", "Education", "Clothing", "Home", "all"],
    )

    # These properties will automatically be exposed as endpoint parameters
    time_period: str = "30d"  # 7d, 30d, 90d, 1y
    include_trends: bool = True
    min_revenue: float = 0.0
    sort_by: str = "revenue"  # revenue, units_sold, growth_rate

    async def analyze_products(self) -> Dict[str, Any]:
        """Analyze product performance using real data."""
        # Query products from database using entity-centric approach
        if self.category != "all":
            all_products = await ProductNode.find(category=self.category)
        else:
            all_products = await ProductNode.find()

        # Calculate product performance (simulate revenue based on price and stock)
        # In a real system, you'd have actual sales data
        products = []
        for p in all_products:
            # Simulate revenue as price * (stock * 0.8) - assuming 80% sell-through
            revenue = p.price * (p.stock * 0.8)
            units_sold = int(p.stock * 0.8)
            # Simulate growth rate based on stock level (more stock = positive growth)
            growth_rate = (p.stock / 100.0) - 50.0 if p.stock > 0 else -10.0

            if revenue >= self.min_revenue:
                products.append(
                    {
                        "product_id": p.id,
                        "name": p.name,
                        "category": p.category,
                        "revenue": round(revenue, 2),
                        "units_sold": units_sold,
                        "growth_rate": round(growth_rate, 1),
                    }
                )

        # Sort products
        if self.sort_by == "revenue":
            products.sort(key=lambda x: x["revenue"], reverse=True)
        elif self.sort_by == "units_sold":
            products.sort(key=lambda x: x["units_sold"], reverse=True)
        elif self.sort_by == "growth_rate":
            products.sort(key=lambda x: x["growth_rate"], reverse=True)

        # Calculate totals
        total_revenue = sum(p["revenue"] for p in products)
        total_units = sum(p["units_sold"] for p in products)

        # Find top category
        category_revenue: Dict[str, float] = {}
        for p in products:
            cat = p["category"]
            category_revenue[cat] = category_revenue.get(cat, 0) + p["revenue"]
        top_category = (
            max(category_revenue.items(), key=lambda x: x[1])[0]
            if category_revenue
            else "N/A"
        )

        # Generate trends
        trends = []
        if self.include_trends:
            if total_revenue > 100000:
                trends.append("Strong overall revenue performance")
            if category_revenue.get("Electronics", 0) > total_revenue * 0.5:
                trends.append("Electronics category dominating sales")
            if len(products) > 10:
                trends.append("Large product catalog detected")
            if total_units > 500:
                trends.append("High sales volume")
            if not trends:
                trends.append("Standard sales patterns observed")

        return {
            "sales_summary": {
                "total_revenue": round(total_revenue, 2),
                "units_sold": total_units,
                "top_selling_category": top_category,
                "average_order_value": (
                    round(total_revenue / total_units, 2) if total_units > 0 else 0
                ),
                "time_period": self.time_period,
            },
            "product_performance": products,
            "trends": trends,
            "generated_at": datetime.now().isoformat(),
        }


@endpoint(
    "/reports/generate",
    methods=["POST"],
    auth=True,
    permissions=["read_reports"],
    response=success_response(
        data={
            "report": ResponseField(
                field_type=Dict[str, Any],
                description="Generated report information",
                example={
                    "report_id": "RPT-2024-001",
                    "title": "Monthly Sales Report",
                    "format": "pdf",
                    "pages": 15,
                    "file_size": "2.5MB",
                },
            ),
            "download_url": ResponseField(
                field_type=str,
                description="URL to download the report",
                example="/reports/download/RPT-2024-001.pdf",
            ),
            "expires_at": ResponseField(
                field_type=str,
                description="Report expiration timestamp",
                example="2024-02-15T14:30:00Z",
            ),
            "message": ResponseField(
                field_type=str,
                description="Success message",
                example="Report generated successfully",
            ),
        }
    ),
)
class ReportGeneratorWalker(Walker):
    """Generate various types of reports."""

    report_type: str = EndpointField(
        default="sales",
        description="Type of report to generate",
        examples=["sales", "users", "products", "financial", "custom"],
    )

    # These properties will automatically be exposed as endpoint parameters
    start_date: str = "2024-01-01"
    end_date: str = "2024-01-31"
    format: str = "pdf"  # pdf, excel, csv, json
    include_charts: bool = True
    include_details: bool = True
    email_report: bool = False

    async def generate_report(self) -> Dict[str, Any]:
        """Generate a report based on parameters."""
        # Query data based on report type using entity-centric approach
        if self.report_type == "sales":
            products = await ProductNode.find()
            data_count = len(products)
            pages = max(10, data_count // 5)
            file_size = f"{pages * 0.15:.1f}MB"
            title = "Monthly Sales Report"
        elif self.report_type == "users":
            users = await UserNode.find()
            data_count = len(users)
            pages = max(8, data_count // 10)
            file_size = f"{pages * 0.15:.1f}MB"
            title = "User Analytics Report"
        elif self.report_type == "products":
            products = await ProductNode.find()
            data_count = len(products)
            pages = max(12, data_count // 8)
            file_size = f"{pages * 0.15:.1f}MB"
            title = "Product Performance Report"
        else:
            pages = 10
            file_size = "1.8MB"
            title = f"{self.report_type.title()} Report"

        # Generate report ID
        report_id = f"RPT-{datetime.now().year}-{len([1, 2, 3]) + 1:03d}"

        # Calculate expiration (7 days from now)
        expires_at = datetime.now().replace(
            hour=23, minute=59, second=59, microsecond=0
        )
        expires_at = expires_at.replace(day=expires_at.day + 7)

        return {
            "report": {
                "report_id": report_id,
                "title": title,
                "format": self.format,
                "pages": pages,
                "file_size": file_size,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "include_charts": self.include_charts,
                "include_details": self.include_details,
            },
            "download_url": f"/reports/download/{report_id}.{self.format}",
            "expires_at": expires_at.isoformat(),
            "message": "Report generated successfully",
        }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("Authenticated CRUD API Example with jvspatial")
    print("=" * 80)
    print("This example demonstrates a realistic CRUD API using the unified")
    print(
        "@endpoint decorator with authentication, authorization, and response schemas."
    )
    print()
    print("Key Features:")
    print("  - Complete CRUD operations for Users and Products")
    print("  - Proper authentication and authorization")
    print("  - Realistic response schemas with examples")
    print("  - Permission-based access control")
    print("  - Walker-based analytics and reporting")
    print("  - Automatic OpenAPI schema generation")
    print("  - Real persistence using the graph database")
    print()
    print("System Endpoints:")
    print("  - GET  /health                    (system health check)")
    print()
    print("User Management (CRUD):")
    print("  - GET    /users                   (list users with pagination)")
    print("  - POST   /users                   (create user)")
    print("  - GET    /users/{id}              (get user by ID)")
    print("  - PUT    /users/{id}              (update user)")
    print("  - DELETE /users/{id}              (delete user)")
    print()
    print("Product Management (CRUD):")
    print("  - GET    /products                (list products with filtering)")
    print("  - POST   /products                (create product)")
    print("  - GET    /products/{id}           (get product by ID)")
    print("  - PUT    /products/{id}           (update product)")
    print("  - DELETE /products/{id}           (delete product)")
    print()
    print("Analytics & Reporting (Walkers):")
    print("  - POST /analytics/users           (user analytics with insights)")
    print("  - POST /analytics/products        (product performance analysis)")
    print("  - POST /reports/generate          (generate various reports)")
    print()
    print("Authentication endpoints:")
    print("  - POST /auth/register             (user registration)")
    print("  - POST /auth/login                (user login)")
    print("  - POST /auth/logout               (user logout)")
    print()
    print("Visit http://localhost:8000/docs to see the Swagger UI")
    print("=" * 80)

    # Start the server
    server.run()
