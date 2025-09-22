# Quickstart Guide for jvspatial

This document provides guidance for AI language models and developers working with the jvspatial library to ensure consistent, high-quality code generation and maintenance practices.

## 🎯 Core Philosophy

The jvspatial library emphasizes **clean, entity-centric design** with a unified MongoDB-style query interface that works seamlessly across different database backends (JSON, MongoDB, custom implementations).

## 🔧 Environment Setup

Before getting started with jvspatial development, configure your environment variables for proper database connectivity.

### Quick Setup

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the .env file** with your preferred configuration:
   ```env
   # Choose database backend
   JVSPATIAL_DB_TYPE=json              # or 'mongodb'

   # JSON database configuration (default)
   JVSPATIAL_JSONDB_PATH=./jvdb/dev    # Local file storage path

   # MongoDB configuration (if using MongoDB)
   # JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
   # JVSPATIAL_MONGODB_DB_NAME=jvspatial_dev
   ```

3. **Load environment variables** in your code:
   ```python
   from dotenv import load_dotenv
   load_dotenv()  # Load .env file

   # jvspatial automatically uses environment variables
   from jvspatial.core import GraphContext
   ctx = GraphContext()  # Uses configured database
   ```

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `JVSPATIAL_DB_TYPE` | `json` | Database backend (`json`, `mongodb`) |
| `JVSPATIAL_JSONDB_PATH` | `jvdb` | Directory for JSON database files |
| `JVSPATIAL_MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `JVSPATIAL_MONGODB_DB_NAME` | `jvspatial_db` | MongoDB database name |

### Configuration Examples

**Development (JSON Database):**
```env
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=./jvdb/dev
```

**Production (MongoDB):**
```env
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/
JVSPATIAL_MONGODB_DB_NAME=jvspatial_production
```

**Docker/Container Setup:**
```env
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://mongo_container:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial_docker
```

> **📖 For comprehensive environment configuration details, see:** [Environment Configuration Guide](docs/md/environment-configuration.md)

## 📝 Code Generation Preferences

### 1. Entity-Centric CRUD Syntax (PREFERRED)

**✅ DO: Use entity-centric syntax**
```python
# Entity creation
user = await User.create(name="Alice", email="alice@company.com")

# Entity retrieval
user = await User.get(user_id)
users = await User.find({"context.active": True})
active_users = await User.find_by(active=True)

# Entity updates
user.name = "Alice Johnson"
await user.save()

# Entity deletion
await user.delete()

# Counting and aggregation
count = await User.count({"context.department": "engineering"})
departments = await User.distinct("department")
```

**❌ AVOID: Direct GraphContext methods**
```python
# Discouraged - direct database access
db = get_database()
users = await db.find("node", {"name": "User"})
await db.create("node", user_data)
```

### 2. MongoDB-Style Query Interface

Always use the unified MongoDB-style query syntax with proper dot notation for nested fields:

```python
# Comparison operators
senior_users = await User.find({"context.age": {"$gte": 35}})
young_users = await User.find({"context.age": {"$lt": 30}})
non_admin_users = await User.find({"context.role": {"$ne": "admin"}})

# Logical operators
engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.active": True}
    ]
})

# OR conditions
senior_or_manager = await User.find({
    "$or": [
        {"context.age": {"$gte": 40}},
        {"context.role": "manager"}
    ]
})

# Array operations
tech_users = await User.find({"context.skills": {"$in": ["python", "javascript"]}})
non_tech_users = await User.find({"context.skills": {"$nin": ["python", "java"]}})

# Regular expressions with case-insensitive matching
johnson_family = await User.find({
    "context.name": {"$regex": "Johnson", "$options": "i"}
})

# Complex nested queries
active_senior_engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.age": {"$gte": 35}},
        {"context.active": True},
        {"context.skills": {"$in": ["python", "go", "rust"]}}
    ]
})

# Range queries
mid_career = await User.find({
    "context.experience_years": {
        "$gte": 3,
        "$lte": 10
    }
})

# Existence checks
users_with_github = await User.find({"context.github_profile": {"$exists": True}})
```

## 🔧 Code Quality Standards

### Linting and Formatting Requirements

All generated code must adhere to:

- **Black**: Code formatting (line length 88 chars)
- **Flake8**: PEP 8 compliance and error detection
- **mypy**: Type checking and annotations
- **isort**: Import sorting and organization

### Type Annotations

Always include proper type annotations:

```python
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from jvspatial.core import Node
from jvspatial.exceptions import NodeNotFoundError, ValidationError

class User(Node):
    name: str = ""
    email: str = ""
    age: int = 0
    roles: List[str] = []
    department: str = ""
    created_at: datetime = datetime.now()
    active: bool = True
    metadata: Dict[str, Any] = {}

async def find_users(department: str, active: bool = True) -> List[User]:
    """Find users by department with optional activity filter."""
    return await User.find({
        "context.department": department,
        "context.active": active
    })

async def get_user_by_id(user_id: str) -> Optional[User]:
    """Get user by ID, returning None if not found."""
    try:
        return await User.get(user_id)
    except NodeNotFoundError:
        return None

async def find_users_advanced(
    filters: Dict[str, Any],
    limit: Optional[int] = None,
    sort_by: Optional[str] = None
) -> List[User]:
    """Advanced user search with MongoDB-style filters."""
    query = {}

    # Build query with proper context prefixing
    for field, value in filters.items():
        if not field.startswith("context."):
            query[f"context.{field}"] = value
        else:
            query[field] = value

    users = await User.find(query)

    # Apply sorting if specified
    if sort_by:
        users.sort(key=lambda u: getattr(u, sort_by, 0))

    # Apply limit if specified
    if limit and len(users) > limit:
        users = users[:limit]

    return users
```

### Error Handling

Include appropriate error handling patterns:

```python
import logging
from jvspatial.exceptions import NodeNotFoundError, ValidationError, DatabaseError

logger = logging.getLogger(__name__)

# Basic error handling pattern
try:
    user = await User.get(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
except NodeNotFoundError:
    logger.warning(f"User {user_id} not found in database")
    return None
except DatabaseError as e:
    logger.error(f"Database error retrieving user {user_id}: {e}")
    raise
except Exception as e:
    logger.error(f"Unexpected error retrieving user {user_id}: {e}")
    raise

# Advanced error handling with context management
async def safe_user_operation(user_id: str, operation_data: Dict[str, Any]):
    """Perform user operations with comprehensive error handling."""
    try:
        # Validate input data
        if not user_id or not operation_data:
            raise ValidationError("User ID and operation data are required")

        # Retrieve user
        user = await User.get(user_id)
        if not user:
            raise NodeNotFoundError(f"User {user_id} not found")

        # Perform operation with transaction-like behavior
        original_data = user.model_dump()  # Backup for rollback

        try:
            # Update user data
            for field, value in operation_data.items():
                if hasattr(user, field):
                    setattr(user, field, value)
                else:
                    logger.warning(f"Ignoring unknown field: {field}")

            # Validate and save
            await user.validate()  # Custom validation if implemented
            await user.save()

            logger.info(f"Successfully updated user {user_id}")
            return user

        except ValidationError as e:
            # Rollback changes
            for field, value in original_data.items():
                setattr(user, field, value)
            logger.error(f"Validation failed for user {user_id}: {e}")
            raise

    except NodeNotFoundError:
        logger.warning(f"User {user_id} not found for operation")
        raise
    except ValidationError:
        logger.error(f"Validation error for user {user_id} operation")
        raise
    except DatabaseError as e:
        logger.error(f"Database error during user {user_id} operation: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during user {user_id} operation: {e}")
        raise RuntimeError(f"Operation failed for user {user_id}") from e

# Context manager for batch operations
class UserBatchProcessor:
    def __init__(self):
        self.success_count = 0
        self.error_count = 0
        self.errors: List[str] = []

    async def __aenter__(self):
        self.success_count = 0
        self.error_count = 0
        self.errors = []
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logger.error(f"Batch processing failed: {exc_val}")
        else:
            logger.info(
                f"Batch processing completed: {self.success_count} success, "
                f"{self.error_count} errors"
            )

    async def process_user(self, user_data: Dict[str, Any]):
        try:
            user = await User.create(**user_data)
            self.success_count += 1
            return user
        except Exception as e:
            self.error_count += 1
            error_msg = f"Failed to process user {user_data.get('email', 'unknown')}: {e}"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return None

# Usage example
async def batch_create_users(users_data: List[Dict[str, Any]]):
    async with UserBatchProcessor() as processor:
        results = []
        for user_data in users_data:
            result = await processor.process_user(user_data)
            results.append(result)
        return results
```

## 📄 Object Pagination with ObjectPager

The **ObjectPager** provides efficient, database-level pagination for any Object subclass (including Nodes, Edges, and custom objects) with filtering and ordering capabilities. It's designed for handling large datasets and UI integration.

### Quick Start

```python path=null start=null
from jvspatial.core.pager import ObjectPager, paginate_objects, paginate_by_field
from jvspatial.core import Node

class City(Node):
    name: str = ""
    population: int = 0
    state: str = ""

class User(Node):
    name: str = ""
    email: str = ""
    department: str = ""
    active: bool = True

# Simple pagination with convenience function
cities = await paginate_objects(City, page=1, page_size=20)
print(f"Found {len(cities)} cities on page 1")

# Pagination with filters
large_cities = await paginate_objects(
    City,
    page=1,
    page_size=10,
    filters={"context.population": {"$gt": 1_000_000}}
)

# Field-based pagination with ordering
populous_cities = await paginate_by_field(
    City,
    field="population",
    order="desc",  # Largest first
    page_size=15
)
```

### ObjectPager Class Usage

```python path=null start=null
async def advanced_pagination_example():
    """Demonstrate ObjectPager class with full features."""

    # Create pager with filters and ordering
    pager = ObjectPager(
        User,
        page_size=25,
        filters={"context.active": True},
        order_by="name",
        order_direction="asc"
    )

    # Get first page
    users_page1 = await pager.get_page(page=1)
    print(f"Page 1: {len(users_page1)} users")

    # Get pagination metadata for UI
    pagination_info = pager.to_dict()
    print(f"Total users: {pagination_info['total_items']}")
    print(f"Total pages: {pagination_info['total_pages']}")
    print(f"Has next page: {pagination_info['has_next']}")

    # Navigate pages
    if pager.has_next_page():
        users_page2 = await pager.next_page()
        print(f"Page 2: {len(users_page2)} users")

    # Add additional filters dynamically
    engineering_users = await pager.get_page(
        page=1,
        additional_filters={"context.department": "engineering"}
    )
    print(f"Engineering users: {len(engineering_users)}")

    return pager, pagination_info
```

### Batch Processing with Pagination

```python path=null start=null
async def process_large_dataset_example():
    """Process large datasets efficiently with pagination."""

    # Create pager for batch processing
    pager = ObjectPager(User, page_size=100)  # Larger batches for processing
    processed_count = 0

    print("Starting batch processing...")

    while True:
        # Get next batch of users
        users_batch = await pager.next_page()

        if not users_batch:
            print("No more users to process")
            break

        # Process batch
        print(f"Processing batch {pager.current_page}: {len(users_batch)} users")

        for user in users_batch:
            # Simulate processing (e.g., send emails, update records)
            await process_user(user)
            processed_count += 1

        print(f"Completed page {pager.current_page}, total processed: {processed_count}")

        # Optional: Add delay between batches
        # await asyncio.sleep(1.0)

    print(f"Batch processing complete: {processed_count} users processed")
    return processed_count

async def process_user(user: User):
    """Process individual user (mock implementation)."""
    # Update user's last processed timestamp
    user.data['last_processed'] = datetime.now().isoformat()
    await user.save()
```

### UI Integration Pattern

```python path=null start=null
class PaginationService:
    """Service for UI pagination integration."""

    def __init__(self):
        self.pagers = {}

    def create_pager(self, key: str, object_class, **kwargs):
        """Create and store pager for reuse."""
        self.pagers[key] = ObjectPager(object_class, **kwargs)
        return self.pagers[key]

    async def get_page_data(self, key: str, page: int = 1, additional_filters=None):
        """Get paginated data with metadata for UI consumption."""
        if key not in self.pagers:
            raise ValueError(f"Pager '{key}' not found")

        pager = self.pagers[key]
        objects = await pager.get_page(page, additional_filters)

        return {
            "data": [obj.model_dump() for obj in objects],
            "pagination": pager.to_dict(),
            "cached": pager.is_cached
        }

# Usage example
async def ui_pagination_example():
    """Example of pagination for UI/API integration."""
    service = PaginationService()

    # Setup pagers for different views
    service.create_pager(
        "cities",
        City,
        page_size=20,
        filters={"context.state": "CA"},
        order_by="population",
        order_direction="desc"
    )

    service.create_pager(
        "users",
        User,
        page_size=25,
        filters={"context.active": True}
    )

    # Get page data (as would be called from API endpoint)
    cities_response = await service.get_page_data("cities", page=1)

    print(f"API Response:")
    print(f"  Cities on page: {len(cities_response['data'])}")
    print(f"  Total cities: {cities_response['pagination']['total_items']}")
    print(f"  Total pages: {cities_response['pagination']['total_pages']}")
    print(f"  From cache: {cities_response['cached']}")

    return cities_response
```

### Complex Filtering Examples

```python path=null start=null
async def advanced_filtering_examples():
    """Demonstrate complex filtering patterns."""

    # Multi-condition filters
    complex_pager = ObjectPager(
        User,
        page_size=30,
        filters={
            "$and": [
                {"context.active": True},
                {"context.department": {"$in": ["engineering", "product"]}},
                {"context.email": {"$regex": "@company\.com$", "$options": "i"}}
            ]
        },
        order_by="name"
    )

    company_employees = await complex_pager.get_page()
    print(f"Active company employees: {len(company_employees)}")

    # Range filters for numeric data
    mid_size_cities_pager = ObjectPager(
        City,
        page_size=20,
        filters={
            "context.population": {
                "$gte": 50_000,
                "$lte": 500_000
            }
        },
        order_by="population",
        order_direction="desc"
    )

    mid_size_cities = await mid_size_cities_pager.get_page()
    print(f"Mid-size cities: {len(mid_size_cities)}")

    # Text search with pagination
    search_pager = ObjectPager(
        User,
        page_size=15,
        filters={
            "$or": [
                {"context.name": {"$regex": "john", "$options": "i"}},
                {"context.email": {"$regex": "john", "$options": "i"}}
            ]
        }
    )

    search_results = await search_pager.get_page()
    print(f"Search results for 'john': {len(search_results)}")

    return company_employees, mid_size_cities, search_results
```

### Best Practices

**✅ Recommended Patterns:**

```python path=null start=null
# Good: Use database-level filtering
filtered_pager = ObjectPager(
    City,
    filters={"context.population": {"$gt": 100_000}}
)
large_cities = await filtered_pager.get_page()

# Good: Appropriate page sizes for use case
ui_pager = ObjectPager(User, page_size=20)      # UI display
batch_pager = ObjectPager(User, page_size=100)  # Batch processing

# Good: Reuse pager instances for consistent state
pager = ObjectPager(City, page_size=25)
page1 = await pager.get_page(1)
page2 = await pager.next_page()  # Maintains pagination state

# Good: Use pagination metadata for UI
info = pager.to_dict()
if info['has_next']:
    show_next_button = True

# Good: Convenience functions for simple cases
cities = await paginate_objects(City, page=1, page_size=10)
sorted_users = await paginate_by_field(User, "name", order="asc")
```

**❌ Avoided Patterns:**

```python path=null start=null
# Bad: Python-level filtering (loads all data)
all_cities = await City.all()
large_cities = [c for c in all_cities if c.population > 100_000]  # Inefficient

# Bad: Page sizes too small or too large
tiny_pager = ObjectPager(City, page_size=1)     # Too many requests
huge_pager = ObjectPager(City, page_size=10_000) # Memory issues

# Bad: Creating new pager for each request
for page_num in range(1, 10):
    pager = ObjectPager(City, page_size=10)  # Recreates each time
    cities = await pager.get_page(page_num)

# Bad: Not checking pagination bounds
cities = await pager.get_page(999)  # Page may not exist

# Better: Check bounds first
if page_num <= pager.to_dict()['total_pages']:
    cities = await pager.get_page(page_num)
```

---

## 🔗 Webhook Integration and Handlers

The **jvspatial webhook system** provides secure, flexible webhook endpoints with built-in authentication, HMAC verification, idempotency keys, and automatic payload processing. Webhooks integrate seamlessly with the FastAPI server and support both function-based handlers and graph traversal processing.

### Webhook Architecture Overview

Webhooks in jvspatial are designed for:
- **Security**: Path-based authentication tokens, optional HMAC signature verification
- **Reliability**: Idempotency key support to handle duplicate deliveries
- **Flexibility**: JSON/XML/binary payload support with automatic parsing
- **Integration**: Full compatibility with existing authentication and permission systems
- **Processing**: Always return HTTP 200 for proper webhook etiquette

### Basic Webhook Endpoint Setup

```python path=null start=null
from fastapi import Request
from jvspatial.api.auth.decorators import webhook_endpoint
from jvspatial.api.auth.middleware import get_current_user
from typing import Dict, Any
import json

# Basic webhook handler function
@webhook_endpoint("/webhook/{route}/{auth_token}", methods=["POST"])
async def generic_webhook_handler(request: Request) -> Dict[str, Any]:
    """Generic webhook handler for multiple services.

    Processes webhooks from various sources using route-based dispatch.
    Middleware handles authentication, HMAC verification, and payload parsing.
    """
    # Access processed data from middleware
    raw_body = request.state.raw_body  # Original bytes
    content_type = request.state.content_type  # Content-Type header
    route = getattr(request.state, "webhook_route", "unknown")  # Route parameter
    current_user = get_current_user(request)  # Authenticated user

    # Parse payload based on content type
    processed_data = None
    if content_type == "application/json":
        try:
            processed_data = json.loads(raw_body)
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON payload"}
    else:
        # Handle other content types (XML, form data, binary)
        processed_data = {"raw_length": len(raw_body), "type": content_type}

    # Route-based processing
    if route == "stripe":
        return await process_stripe_webhook(processed_data, current_user)
    elif route == "github":
        return await process_github_webhook(processed_data, current_user)
    elif route == "slack":
        return await process_slack_webhook(processed_data, current_user)
    else:
        # Generic processing for unknown routes
        return {
            "status": "received",
            "route": route,
            "payload_type": content_type,
            "user_id": current_user.id if current_user else None
        }

# Service-specific webhook handlers
@webhook_endpoint("/webhook/stripe/{auth_token}", methods=["POST"])
async def stripe_webhook_handler(request: Request) -> Dict[str, Any]:
    """Dedicated Stripe webhook handler with event processing."""
    raw_body = request.state.raw_body
    current_user = get_current_user(request)

    try:
        event = json.loads(raw_body)
        event_type = event.get("type", "unknown")

        # Process different Stripe event types
        if event_type == "payment_intent.succeeded":
            await handle_successful_payment(event["data"]["object"], current_user)
        elif event_type == "customer.subscription.updated":
            await handle_subscription_update(event["data"]["object"], current_user)
        elif event_type == "invoice.payment_failed":
            await handle_payment_failure(event["data"]["object"], current_user)

        return {
            "status": "success",
            "event_type": event_type,
            "processed_at": datetime.now().isoformat()
        }

    except Exception as e:
        # Always return 200 for webhooks, log errors internally
        print(f"Stripe webhook processing error: {e}")
        return {"status": "received", "error": "Processing error logged"}

# Helper functions for webhook processing
async def process_stripe_webhook(data: Dict[str, Any], user) -> Dict[str, Any]:
    """Process Stripe webhook events."""
    event_type = data.get("type", "unknown")
    return {
        "status": "success",
        "message": f"Processed Stripe {event_type}",
        "user_id": user.id if user else None
    }

async def process_github_webhook(data: Dict[str, Any], user) -> Dict[str, Any]:
    """Process GitHub webhook events."""
    action = data.get("action", "unknown")
    repo_name = data.get("repository", {}).get("name", "unknown")
    return {
        "status": "success",
        "message": f"GitHub {action} on {repo_name}",
        "user_id": user.id if user else None
    }

async def process_slack_webhook(data: Dict[str, Any], user) -> Dict[str, Any]:
    """Process Slack webhook events."""
    event_type = data.get("type", "unknown")
    return {
        "status": "success",
        "message": f"Slack {event_type} processed",
        "user_id": user.id if user else None
    }
```

### Webhook Security and Authentication

Webhook endpoints require authentication tokens in the URL path and support additional security measures:

```python path=null start=null
# Webhook with permission requirements
@webhook_endpoint(
    "/webhook/admin/{route}/{auth_token}",
    methods=["POST"],
    permissions=["process_webhooks", "admin_access"],
    roles=["admin", "webhook_manager"]
)
async def admin_webhook_handler(request: Request) -> Dict[str, Any]:
    """Administrative webhook handler with strict permissions."""
    current_user = get_current_user(request)

    # User is guaranteed to have required permissions due to middleware
    return {
        "status": "success",
        "message": "Admin webhook processed",
        "admin_user": current_user.username,
        "permissions": current_user.permissions
    }

# HMAC signature verification (handled by middleware)
@webhook_endpoint("/webhook/secure/{service}/{auth_token}", methods=["POST"])
async def secure_webhook_handler(request: Request) -> Dict[str, Any]:
    """Webhook with HMAC signature verification.

    Middleware automatically verifies HMAC signatures when present.
    Configure HMAC secrets via environment variables or user settings.
    """
    # If this handler executes, HMAC verification passed (if configured)
    raw_body = request.state.raw_body
    hmac_verified = getattr(request.state, "hmac_verified", False)

    return {
        "status": "success",
        "message": "Secure webhook processed",
        "hmac_verified": hmac_verified,
        "payload_size": len(raw_body)
    }
```

### Graph Traversal Webhook Processing (Future Enhancement)

The architecture supports webhook processing through graph traversal using Walker classes:

```python path=null start=null
# NOTE: This functionality is planned for future release
# from jvspatial.api.auth.decorators import webhook_walker_endpoint
# from jvspatial.core import Walker, Node
# from jvspatial.decorators import on_visit

# @webhook_walker_endpoint("/webhook/process/{route}/{auth_token}", methods=["POST"])
# class WebhookProcessingWalker(Walker):
#     """Walker-based webhook processing with graph traversal."""
#
#     def __init__(self):
#         super().__init__()
#         self.webhook_data = None
#         self.processing_results = []
#
#     @on_visit("WebhookEvent")
#     async def process_webhook_event(self, here: Node):
#         """Process webhook events stored as graph nodes."""
#         # Access webhook data from request.state
#         payload = self.webhook_data
#
#         # Process event based on node data and webhook payload
#         result = await self.analyze_event(here, payload)
#         self.processing_results.append(result)
#
#         # Continue traversal to related events
#         related_events = await here.nodes(node=['WebhookEvent'])
#         await self.visit(related_events)
#
#     async def analyze_event(self, event_node: Node, payload: dict) -> dict:
#         """Analyze webhook event against stored data."""
#         return {
#             "event_id": event_node.id,
#             "payload_type": payload.get("type"),
#             "correlation_score": 0.95  # Example analysis result
#         }
```

### Idempotency and Duplicate Handling

Webhooks support idempotency keys to handle duplicate deliveries:

```python path=null start=null
@webhook_endpoint("/webhook/idempotent/{auth_token}", methods=["POST"])
async def idempotent_webhook_handler(request: Request) -> Dict[str, Any]:
    """Webhook handler with built-in idempotency support.

    Middleware automatically handles idempotency keys in headers:
    - Idempotency-Key header
    - X-Idempotency-Key header
    - Custom idempotency headers
    """
    # Access idempotency information from middleware
    idempotency_key = getattr(request.state, "idempotency_key", None)
    is_duplicate = getattr(request.state, "is_duplicate_request", False)

    if is_duplicate:
        # Return cached response for duplicate requests
        cached_response = getattr(request.state, "cached_response", {})
        return {
            "status": "success",
            "message": "Duplicate request, returning cached response",
            "idempotency_key": idempotency_key,
            "cached_result": cached_response
        }

    # Process new request
    raw_body = request.state.raw_body
    processed_result = await process_unique_webhook(json.loads(raw_body))

    return {
        "status": "success",
        "message": "New webhook processed",
        "idempotency_key": idempotency_key,
        "result": processed_result
    }

async def process_unique_webhook(payload: dict) -> dict:
    """Process a unique webhook payload."""
    # Simulate processing logic
    import time
    processing_start = time.time()

    # Your actual webhook processing logic here
    await asyncio.sleep(0.1)  # Simulate work

    return {
        "processed_at": processing_start,
        "data_processed": True,
        "payload_keys": list(payload.keys())
    }
```

### Server Integration and Middleware Setup

Webhook endpoints automatically integrate with the jvspatial server middleware stack:

```python path=null start=null
from jvspatial.api import Server
from jvspatial.api.auth.middleware import (
    AuthenticationMiddleware,
    WebhookMiddleware,
    HTTPSRedirectMiddleware
)

# Server setup with webhook middleware
server = Server(
    title="Webhook-Enabled Spatial API",
    description="API with secure webhook processing",
    version="1.0.0",
    host="0.0.0.0",
    port=8000
)

# Middleware stack (order matters)
server.add_middleware(HTTPSRedirectMiddleware)  # Force HTTPS
server.add_middleware(WebhookMiddleware)        # Webhook processing
server.add_middleware(AuthenticationMiddleware) # Authentication

# Webhook endpoints are automatically registered
# Access at: POST https://your-domain.com/webhook/{route}/{auth_token}

# Environment configuration for webhook security
# Set in .env file:
# WEBHOOK_HMAC_SECRET=your-secret-key
# WEBHOOK_HTTPS_REQUIRED=true
# WEBHOOK_IDEMPOTENCY_TTL=3600  # 1 hour cache
# WEBHOOK_MAX_PAYLOAD_SIZE=1048576  # 1MB limit

if __name__ == "__main__":
    server.run(port=8000)
```

### Webhook Testing and Development

```python path=null start=null
# Testing webhook handlers
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

@pytest.fixture
def test_webhook_request():
    """Create mock webhook request for testing."""
    request = MagicMock()
    request.state.raw_body = b'{"type": "test", "data": {"id": 123}}'
    request.state.content_type = "application/json"
    request.state.webhook_route = "test"
    request.state.current_user = MagicMock(id="user_123")
    request.state.hmac_verified = True
    request.state.idempotency_key = "test-key-123"
    return request

@pytest.mark.asyncio
async def test_webhook_processing(test_webhook_request):
    """Test webhook handler processing."""
    result = await generic_webhook_handler(test_webhook_request)

    assert result["status"] == "received"
    assert result["route"] == "test"
    assert result["user_id"] == "user_123"

# Development webhook testing with ngrok or similar
# 1. Start your jvspatial server locally
# 2. Use ngrok to expose: ngrok http 8000
# 3. Configure webhook URLs: https://abc123.ngrok.io/webhook/test/your-auth-token
# 4. Test with curl:
#    curl -X POST https://abc123.ngrok.io/webhook/test/your-token \
#         -H "Content-Type: application/json" \
#         -d '{"test": "data"}'
```

### Best Practices for Webhook Implementation

**✅ Recommended Patterns:**

```python path=null start=null
# Good: Always return 200 status for webhooks
@webhook_endpoint("/webhook/service/{auth_token}")
async def proper_webhook_handler(request: Request) -> Dict[str, Any]:
    try:
        # Process webhook
        result = await process_webhook_data(request.state.raw_body)
        return {"status": "success", "result": result}
    except Exception as e:
        # Log error but still return 200
        logger.error(f"Webhook processing failed: {e}")
        return {"status": "received", "error": "logged"}

# Good: Use route-based dispatch for multiple services
@webhook_endpoint("/webhook/{route}/{auth_token}")
async def multi_service_webhook(request: Request) -> Dict[str, Any]:
    route = getattr(request.state, "webhook_route", "unknown")

    handlers = {
        "stripe": process_stripe_webhook,
        "github": process_github_webhook,
        "slack": process_slack_webhook
    }

    handler = handlers.get(route, process_generic_webhook)
    return await handler(request)

# Good: Validate authentication token format
@webhook_endpoint("/webhook/{service}/{auth_token}")
async def secure_webhook_handler(request: Request) -> Dict[str, Any]:
    # Token validation is handled by middleware
    current_user = get_current_user(request)
    if not current_user:
        return {"status": "error", "message": "Invalid authentication"}

    return {"status": "success", "user_verified": True}
```

**❌ Avoided Patterns:**

```python path=null start=null
# Bad: Returning non-200 status codes
@webhook_endpoint("/webhook/bad/{auth_token}")
async def bad_webhook_handler(request: Request) -> Dict[str, Any]:
    try:
        process_webhook(request.state.raw_body)
    except Exception:
        # Don't do this - breaks webhook retry logic
        raise HTTPException(status_code=500, detail="Processing failed")

# Bad: Not handling authentication properly
@webhook_endpoint("/webhook/unsecure/{auth_token}")
async def unsecure_webhook_handler(request: Request) -> Dict[str, Any]:
    # Don't bypass authentication checks
    # Always use get_current_user() or require auth in decorator
    return {"status": "processed"}

# Bad: Not using middleware-processed data
@webhook_endpoint("/webhook/manual/{auth_token}")
async def manual_webhook_handler(request: Request) -> Dict[str, Any]:
    # Don't manually read request body - use request.state.raw_body
    # raw_body = await request.body()  # Wrong - middleware already processed

    # Use middleware-processed data instead
    raw_body = request.state.raw_body  # Correct
    return {"status": "processed"}
```

---

## 🔗 Webhook System Integration

JVspatial provides an advanced webhook system for handling external service integrations with enterprise-grade security, reliability, and developer experience. The webhook system supports modern decorators, automatic payload processing, HMAC verification, idempotency handling, and seamless authentication integration.

### Quick Webhook Setup

```python path=null start=null
from jvspatial.api.auth.decorators import webhook_endpoint
from jvspatial.api import Server

# Simple webhook handler
@webhook_endpoint("/webhook/payment")
async def payment_webhook(payload: dict, endpoint):
    """Process payment webhooks with automatic JSON parsing."""
    payment_id = payload.get("payment_id")
    amount = payload.get("amount")

    # Process payment logic here
    print(f"Processing payment {payment_id}: ${amount}")

    return endpoint.response(
        content={
            "status": "processed",
            "message": f"Payment {payment_id} processed successfully"
        }
    )

# Server automatically detects and configures webhook middleware
server = Server(title="My Webhook API")
server.run()  # Webhooks ready at /webhook/* paths
```

### Advanced Webhook Features

```python path=null start=null
# Webhook with full security features
@webhook_endpoint(
    "/webhook/stripe/{key}",
    path_key_auth=True,                    # API key in URL path
    hmac_secret="stripe-webhook-secret",   # HMAC signature verification
    idempotency_ttl_hours=48,              # Duplicate handling for 48h
    permissions=["process_payments"]       # RBAC permissions
)
async def secure_stripe_webhook(raw_body: bytes, content_type: str, endpoint):
    """Stripe webhook with comprehensive security."""
    import json

    if content_type == "application/json":
        payload = json.loads(raw_body.decode('utf-8'))
        event_type = payload.get("type", "unknown")

        if event_type == "payment_intent.succeeded":
            return endpoint.response(
                content={
                    "status": "processed",
                    "event_type": event_type,
                    "message": "Payment successful"
                }
            )

    return endpoint.response(content={"status": "received"})

# Multi-service webhook dispatcher
@webhook_endpoint("/webhook/{service}")
async def multi_service_webhook(payload: dict, service: str, endpoint):
    """Route webhooks based on service parameter."""
    handlers = {
        "stripe": process_stripe_event,
        "github": process_github_event,
        "slack": process_slack_event
    }

    handler = handlers.get(service, process_generic_event)
    result = await handler(payload)

    return endpoint.response(
        content={
            "status": "processed",
            "service": service,
            "result": result
        }
    )

# Helper functions
async def process_stripe_event(payload: dict) -> dict:
    return {"stripe_event": payload.get("type", "unknown")}

async def process_github_event(payload: dict) -> dict:
    return {"github_action": payload.get("action", "unknown")}

async def process_slack_event(payload: dict) -> dict:
    return {"slack_event": payload.get("event", {}).get("type", "unknown")}

async def process_generic_event(payload: dict) -> dict:
    return {"processed": True, "keys": list(payload.keys())}
```

### Walker-Based Webhook Processing

```python path=null start=null
# Future feature - Walker-based webhook processing
# @webhook_walker_endpoint("/webhook/location-update")
# class LocationUpdateWalker(Walker):
#     """Process location updates through graph traversal."""
#
#     def __init__(self, payload: dict):
#         super().__init__()
#         self.payload = payload
#         self.response = {"updated_locations": []}
#
#     @on_visit(Node)
#     async def update_location_data(self, here: Node):
#         locations = self.payload.get("locations", [])
#
#         for location_data in locations:
#             location_id = location_data.get("id")
#             coordinates = location_data.get("coordinates")
#
#             if location_id and coordinates:
#                 here.coordinates = coordinates
#                 await here.save()
#
#                 self.response["updated_locations"].append({
#                     "id": location_id,
#                     "coordinates": coordinates
#                 })
```

### Environment Configuration

Configure webhook behavior via environment variables:

```env
# Global webhook settings
JVSPATIAL_WEBHOOK_HMAC_SECRET=your-global-hmac-secret
JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE=5242880  # 5MB
JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL=3600      # 1 hour
JVSPATIAL_WEBHOOK_HTTPS_REQUIRED=true

# Service-specific secrets
JVSPATIAL_WEBHOOK_STRIPE_SECRET=whsec_stripe_secret_key
JVSPATIAL_WEBHOOK_GITHUB_SECRET=github_webhook_secret
```

### Testing Webhooks

```bash
# Basic webhook test
curl -X POST "http://localhost:8000/webhook/payment" \
  -H "Content-Type: application/json" \
  -d '{"payment_id": "pay_123", "amount": 99.99}'

# Webhook with path-based auth
curl -X POST "http://localhost:8000/webhook/stripe/key123:secret456" \
  -H "Content-Type: application/json" \
  -H "X-Signature: sha256=abc123..." \
  -d '{"type": "payment_intent.succeeded"}'

# With idempotency key
curl -X POST "http://localhost:8000/webhook/payment" \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: unique-123" \
  -d '{"payment_id": "pay_124"}'
```

### Webhook Best Practices

**✅ Recommended Patterns:**

```python path=null start=null
# Good: Always return 200 for webhook endpoints
@webhook_endpoint("/webhook/service")
async def proper_webhook(payload: dict, endpoint):
    try:
        result = await process_webhook_data(payload)
        return endpoint.response(content={"status": "success", "result": result})
    except Exception as e:
        # Log error but still return 200
        logger.error(f"Webhook processing failed: {e}")
        return endpoint.response(content={"status": "received", "error": "logged"})

# Good: Use route-based dispatch for multiple services
@webhook_endpoint("/webhook/{service}")
async def multi_service_webhook(payload: dict, service: str, endpoint):
    handlers = {
        "stripe": process_stripe,
        "github": process_github
    }

    handler = handlers.get(service, process_generic)
    return await handler(payload, endpoint)

# Good: Validate webhook signatures when available
@webhook_endpoint("/webhook/secure", hmac_secret="webhook-secret")
async def secure_webhook(raw_body: bytes, endpoint):
    # HMAC verification is automatic when secret is provided
    return endpoint.response(content={"status": "verified"})
```

**❌ Avoided Patterns:**

```python path=null start=null
# Bad: Returning non-200 status codes
@webhook_endpoint("/webhook/bad")
async def bad_webhook(payload: dict, endpoint):
    if payload.get("invalid"):
        # Don't do this - breaks webhook retry logic
        raise HTTPException(status_code=400, detail="Invalid payload")

# Bad: Not handling errors gracefully
@webhook_endpoint("/webhook/risky")
async def risky_webhook(payload: dict, endpoint):
    # Unhandled exceptions will return 500 - webhooks will retry
    result = dangerous_operation(payload)  # Might throw
    return endpoint.response(content={"result": result})

# Bad: Bypassing security features
@webhook_endpoint("/webhook/insecure")
async def insecure_webhook(request: Request, endpoint):
    # Don't manually read request body - use automatic payload injection
    raw_body = await request.body()  # Wrong - middleware already processed
    return endpoint.response(content={"status": "received"})
```

> **📖 For complete webhook documentation and advanced patterns:** [Webhook Architecture Guide](docs/md/webhook-architecture.md) | [Webhook Quickstart](docs/md/webhooks-quickstart.md)

---

## 🌐 API Integration with FastAPI Server

The **jvspatial API** provides seamless integration with FastAPI to expose your graph operations as REST endpoints. It supports flexible endpoint registration using decorators and automatic parameter model generation from Walker and function properties.

### Server Setup and Configuration

```python path=null start=null
from jvspatial.api import Server, ServerConfig, endpoint, walker_endpoint
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core import Node, Walker
from jvspatial.decorators import on_visit

# Basic server setup
server = Server(
    title="My Spatial API",
    description="Graph-based spatial data management API",
    version="1.0.0",
    host="0.0.0.0",
    port=8000,
    debug=True  # Enable for development
)

# Advanced server configuration
advanced_config = ServerConfig(
    title="Production Spatial API",
    description="Enterprise graph data API",
    version="2.0.0",
    host="0.0.0.0",
    port=8080,
    # Database configuration
    db_type="mongodb",
    db_connection_string="mongodb://localhost:27017",
    db_database_name="spatial_db",
    # CORS settings
    cors_enabled=True,
    cors_origins=["https://myapp.com", "http://localhost:3000"],
    # API documentation
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    log_level="info"
)

production_server = Server(config=advanced_config)
```

### @walker_endpoint Decorator for Walker Classes

The `@walker_endpoint` decorator automatically exposes Walker classes as API endpoints:

```python path=null start=null
from jvspatial.api import walker_endpoint
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core import Walker, Node
from jvspatial.decorators import on_visit
from typing import List, Optional

# Define your node types
class User(Node):
    name: str = ""
    email: str = ""
    department: str = ""
    active: bool = True

class City(Node):
    name: str = ""
    population: int = 0
    state: str = ""

# Walker with endpoint configuration using EndpointField
@walker_endpoint("/api/users/process", methods=["POST"])
class ProcessUser(Walker):
    """Process user data with graph traversal."""

    # Endpoint-exposed fields with configuration
    user_name: str = EndpointField(
        description="Name of the user to process",
        examples=["John Doe", "Jane Smith"],
        min_length=2,
        max_length=100
    )

    department: str = EndpointField(
        default="general",
        description="User department",
        examples=["engineering", "marketing", "sales"]
    )

    include_inactive: bool = EndpointField(
        default=False,
        description="Whether to include inactive users in processing"
    )

    # Field excluded from API endpoint
    internal_state: str = EndpointField(
        default="processing",
        exclude_endpoint=True  # Won't appear in API schema
    )

    # Optional configuration field
    max_connections: int = EndpointField(
        default=10,
        description="Maximum number of connections to traverse",
        ge=1,
        le=100
    )

    @on_visit("User")
    async def process_user(self, here: User):
        """Process user nodes during traversal.

        Args:
            here: The visited User node
        """
        # Check if user matches criteria
        if here.name == self.user_name:
            self.response["found_user"] = {
                "id": here.id,
                "name": here.name,
                "email": here.email,
                "department": here.department
            }

            # Find connected users in same department
            colleagues = await here.nodes(
                node=['User'],
                department=self.department,
                active=True if not self.include_inactive else None
            )

            self.response["colleagues"] = [
                {"name": u.name, "email": u.email}
                for u in colleagues[:self.max_connections]
            ]

    @on_visit("City")
    async def process_city_connection(self, here: City):
        """Process city connections if user has location data.

        Args:
            here: The visited City node
        """
        if "city_info" not in self.response:
            self.response["city_info"] = []

        self.response["city_info"].append({
            "name": here.name,
            "population": here.population,
            "state": here.state
        })

# Advanced walker with field grouping
@walker_endpoint("/api/analytics/user-report", methods=["POST"])
class UserAnalytics(Walker):
    """Generate user analytics reports."""

    # Grouped fields for better API organization
    report_type: str = EndpointField(
        description="Type of report to generate",
        examples=["summary", "detailed", "connections"],
        endpoint_group="report_config"
    )

    date_range: str = EndpointField(
        default="30d",
        description="Date range for report",
        examples=["7d", "30d", "90d", "1y"],
        endpoint_group="report_config"
    )

    include_inactive: bool = EndpointField(
        default=False,
        description="Include inactive users",
        endpoint_group="filters"
    )

    departments: List[str] = EndpointField(
        default_factory=list,
        description="Departments to include (empty = all)",
        examples=[["engineering", "product"], ["marketing"]],
        endpoint_group="filters"
    )

    @on_visit("User")
    async def analyze_user(self, here: User):
        """Analyze user data for report.

        Args:
            here: The visited User node
        """
        if "users_analyzed" not in self.response:
            self.response["users_analyzed"] = 0
            self.response["departments"] = {}

        # Filter by department if specified
        if self.departments and here.department not in self.departments:
            return

        # Filter by active status if needed
        if not self.include_inactive and not here.active:
            return

        self.response["users_analyzed"] += 1

        # Track department statistics
        dept = here.department
        if dept not in self.response["departments"]:
            self.response["departments"][dept] = 0
        self.response["departments"][dept] += 1
        }
```

### Enhanced Response Handling with endpoint.response()

The `@walker_endpoint` and `@endpoint` decorators now automatically inject semantic response helpers to make crafting HTTP responses clean and flexible:

**Walker Endpoints with self.endpoint:**

```python path=null start=null
@walker_endpoint("/api/users/profile", methods=["POST"])
class UserProfileWalker(Walker):
    """Walker demonstrating semantic response patterns."""

    user_id: str = EndpointField(description="User ID to retrieve")
    include_details: bool = EndpointField(
        default=False,
        description="Include detailed profile information"
    )

    @on_visit("User")
    async def get_user_profile(self, here: User):
        """Get user profile with semantic responses."""
        if here.id != self.user_id:
            return  # Continue traversal

        # User not found scenario
        if not here.data:
            return self.endpoint.not_found(
                message="User profile not found",
                details={"user_id": self.user_id}
            )

        # Authorization check
        if here.private and not self.include_details:
            return self.endpoint.forbidden(
                message="Insufficient permissions",
                details={"required_permission": "view_details"}
            )

        # Successful response
        profile_data = {
            "id": here.id,
            "name": here.name,
            "email": here.email
        }

        if self.include_details:
            profile_data["department"] = here.department
            profile_data["created_at"] = here.created_at

        return self.endpoint.success(
            data=profile_data,
            message="User profile retrieved successfully"
        )

@walker_endpoint("/api/users/create", methods=["POST"])
class CreateUserWalker(Walker):
    """Walker for creating users with proper HTTP status codes."""

    name: str = EndpointField(description="User name")
    email: str = EndpointField(description="User email")

    @on_visit("Root")
    async def create_user(self, here):
        """Create a new user with validation."""

        # Validation example
        if "@" not in self.email:
            return self.endpoint.unprocessable_entity(
                message="Invalid email format",
                details={"email": self.email}
            )

        # Check for conflicts
        existing_user = await User.find_one({"context.email": self.email})
        if existing_user:
            return self.endpoint.conflict(
                message="User with this email already exists",
                details={"email": self.email}
            )

        # Create user
        user = await User.create(
            name=self.name,
            email=self.email
        )

        # Return 201 Created with location header
        return self.endpoint.created(
            data={
                "id": user.id,
                "name": user.name,
                "email": user.email
            },
            message="User created successfully",
            headers={"Location": f"/api/users/{user.id}"}
        )
```

**Function Endpoints with endpoint parameter:**

```python path=null start=null
@endpoint("/api/health", methods=["GET"])
async def health_check(endpoint) -> Any:
    """Health check with semantic response."""
    return endpoint.success(
        data={"status": "healthy", "version": "1.0.0"},
        message="Service is running normally"
    )

@endpoint("/api/users/{user_id}/status", methods=["PUT"])
async def update_user_status(user_id: str, status: str, endpoint) -> Any:
    """Update user status with validation and error handling."""

    # Validation
    valid_statuses = ["active", "inactive", "suspended"]
    if status not in valid_statuses:
        return endpoint.bad_request(
            message="Invalid status value",
            details={"provided": status, "valid_options": valid_statuses}
        )

    # Find user
    user = await User.get(user_id)
    if not user:
        return endpoint.not_found(
            message="User not found",
            details={"user_id": user_id}
        )

    # Update status
    user.status = status
    await user.save()

    return endpoint.success(
        data={"id": user.id, "status": user.status},
        message=f"User status updated to {status}"
    )

@endpoint("/api/export", methods=["GET"])
async def export_data(format: str, endpoint) -> Any:
    """Export data with custom response formatting."""

    if format not in ["json", "csv", "xml"]:
        return endpoint.error(
            message="Unsupported export format",
            status_code=406,  # Not Acceptable
            details={"format": format, "supported": ["json", "csv", "xml"]}
        )

    # Generate export data
    export_data = {
        "format": format,
        "records": 1500,
        "export_id": "exp_20250921",
        "download_url": f"/downloads/export.{format}"
    }

    # Use flexible response() method for custom headers
    return endpoint.response(
        content={
            "data": export_data,
            "message": f"Export ready in {format} format"
        },
        status_code=200,
        headers={
            "X-Export-Format": format,
            "X-Record-Count": "1500"
        }
    )
```

**Available Response Methods:**

```python path=null start=null
# Success responses
endpoint.success(data=result, message="Success")           # 200 OK
endpoint.created(data=new_item, message="Created")         # 201 Created
endpoint.no_content()                                      # 204 No Content

# Error responses
endpoint.bad_request(message="Invalid input")              # 400 Bad Request
endpoint.unauthorized(message="Auth required")             # 401 Unauthorized
endpoint.forbidden(message="Access denied")                # 403 Forbidden
endpoint.not_found(message="Resource not found")           # 404 Not Found
endpoint.conflict(message="Resource exists")               # 409 Conflict
endpoint.unprocessable_entity(message="Validation failed") # 422 Unprocessable Entity

# Flexible custom response
endpoint.response(
    content={"custom": "data"},
    status_code=202,
    headers={"X-Custom": "value"}
)

# Generic error with custom status code
endpoint.error(
    message="Custom error",
    status_code=418,  # I'm a teapot
    details={"reason": "custom"}
)
```

### @endpoint Decorator for Regular Functions
The `@endpoint` decorator exposes regular functions as API endpoints:

```python path=null start=null
from jvspatial.api import endpoint
from fastapi import HTTPException
from typing import Dict, Any, List

# Simple function endpoint
@endpoint("/api/users/count", methods=["GET"])
async def get_user_count() -> Dict[str, int]:
    """Get total count of users in the system."""
    users = await User.all()
    return {"total_users": len(users)}

# Function endpoint with path parameters
@endpoint("/api/cities/{state}", methods=["GET"])
async def get_cities_by_state(state: str) -> Dict[str, Any]:
    """Get all cities in a specific state."""
    cities = await City.find({"context.state": state})

    if not cities:
        raise HTTPException(
            status_code=404,
            detail=f"No cities found in state: {state}"
        )

    return {
        "state": state,
        "cities": [
            {
                "name": city.name,
                "population": city.population
            } for city in cities
        ],
        "total_count": len(cities)
    }

# Function endpoint with request body
@endpoint("/api/cities/search", methods=["POST"])
async def search_cities(search_request: Dict[str, Any]) -> Dict[str, Any]:
    """Search cities based on criteria."""
    # Extract search parameters
    name_pattern = search_request.get("name_pattern")
    min_population = search_request.get("min_population", 0)
    state = search_request.get("state")

    # Build MongoDB-style query
    query = {}

    if name_pattern:
        query["context.name"] = {"$regex": name_pattern, "$options": "i"}

    if min_population > 0:
        query["context.population"] = {"$gte": min_population}

    if state:
        query["context.state"] = state

    # Execute search
    cities = await City.find(query)

    return {
        "search_criteria": search_request,
        "results": [
            {
                "id": city.id,
                "name": city.name,
                "population": city.population,
                "state": city.state
            } for city in cities
        ],
        "total_results": len(cities)
    }

# Function endpoint with pagination integration
@endpoint("/api/users/paginated", methods=["GET"])
async def get_users_paginated(
    page: int = 1,
    page_size: int = 20,
    department: Optional[str] = None,
    active_only: bool = True
) -> Dict[str, Any]:
    """Get paginated list of users with filtering."""
    from jvspatial.core.pager import ObjectPager

    # Build filters
    filters = {}
    if department:
        filters["context.department"] = department
    if active_only:
        filters["context.active"] = True

    # Create pager
    pager = ObjectPager(
        User,
        page_size=page_size,
        filters=filters,
        order_by="name",
        order_direction="asc"
    )

    # Get page data
    users = await pager.get_page(page)
    pagination_info = pager.to_dict()

    return {
        "users": [
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "department": user.department,
                "active": user.active
            } for user in users
        ],
        "pagination": pagination_info
    }
```

### Server Method Registration

You can also register endpoints directly on server instances:

```python path=null start=null
# Using server instance decorators
@server.walker("/process-data", methods=["POST"])
class DataProcessor(Walker):
    """Process data using server instance registration."""

    data_type: str = EndpointField(
        description="Type of data to process",
        examples=["user", "city", "connection"]
    )

    batch_size: int = EndpointField(
        default=10,
        description="Batch size for processing",
        ge=1,
        le=1000
    )

    @on_visit("Node")
    async def process_any_node(self, here: Node):
        """Process any type of node.

        Args:
            here: The visited Node
        """
        if "processed_nodes" not in self.response:
            self.response["processed_nodes"] = []

        self.response["processed_nodes"].append({
            "id": here.id,
            "type": here.__class__.__name__,
            "processed_at": datetime.now().isoformat()
        })

@server.route("/health-detailed", methods=["GET"])
async def detailed_health_check() -> Dict[str, Any]:
    """Detailed health check endpoint."""
    try:
        # Test database connectivity
        users_count = await User.count()
        cities_count = await City.count()

        return {
            "status": "healthy",
            "database": "connected",
            "statistics": {
                "total_users": users_count,
                "total_cities": cities_count
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Health check failed: {str(e)}"
        )
```

### EndpointField Configuration Options

The `EndpointField` provides extensive configuration for API parameters:

```python path=null start=null
from jvspatial.api.endpoint.router import EndpointField
from typing import List, Optional

@walker_endpoint("/api/advanced-example", methods=["POST"])
class AdvancedEndpointExample(Walker):
    """Demonstrate all EndpointField configuration options."""

    # Basic field with validation
    username: str = EndpointField(
        description="User identifier",
        examples=["john_doe", "jane_smith"],
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_]+$"  # Alphanumeric with underscores
    )

    # Numeric field with constraints
    user_score: float = EndpointField(
        description="User score rating",
        examples=[85.5, 92.0, 78.3],
        ge=0.0,    # Greater than or equal to 0
        le=100.0   # Less than or equal to 100
    )

    # Field with custom endpoint name
    internal_id: str = EndpointField(
        endpoint_name="user_id",  # Will appear as 'user_id' in API
        description="Internal user identifier"
    )

    # Optional field made required for endpoint
    optional_field: Optional[str] = EndpointField(
        default=None,
        endpoint_required=True,  # Required in API despite being Optional in Walker
        description="Field that's optional in Walker but required in API"
    )

    # Required field made optional for endpoint
    required_field: str = EndpointField(
        endpoint_required=False,  # Optional in API despite being required in Walker
        description="Field that's required in Walker but optional in API"
    )

    # Grouped fields for organized API schema
    config_timeout: int = EndpointField(
        default=30,
        description="Timeout in seconds",
        endpoint_group="configuration",
        ge=1,
        le=300
    )

    config_retries: int = EndpointField(
        default=3,
        description="Number of retries",
        endpoint_group="configuration",
        ge=0,
        le=10
    )

    # Hidden field (not shown in API docs)
    debug_mode: bool = EndpointField(
        default=False,
        endpoint_hidden=True,  # Hidden from OpenAPI documentation
        description="Debug mode flag"
    )

    # Deprecated field
    legacy_option: Optional[str] = EndpointField(
        default=None,
        endpoint_deprecated=True,  # Marked as deprecated in API docs
        description="Legacy option - use new_option instead"
    )

    # Field with additional constraints
    email_domain: str = EndpointField(
        description="Allowed email domain",
        endpoint_constraints={
            "format": "hostname",  # Additional OpenAPI constraint
            "example": "company.com"
        }
    )

    # List field with validation
    tags: List[str] = EndpointField(
        default_factory=list,
        description="User tags",
        examples=[["admin", "power-user"], ["guest"]]
    )

    @on_visit("User")
    async def process_with_config(self, here: User):
        """Process user with advanced configuration.

        Args:
            here: The visited User node
        """
        self.response["processed_user"] = {
            "username": self.username,
            "score": self.user_score,
            "config": {
                "timeout": self.config_timeout,
                "retries": self.config_retries
            },
            "tags": self.tags,
            "debug_enabled": self.debug_mode
        }
```

### Running the Server

```python path=null start=null
# Development server
if __name__ == "__main__":
    server.run(
        host="0.0.0.0",
        port=8000,
        reload=True  # Auto-reload for development
    )

# Production server with custom configuration
async def run_production_server():
    """Run server asynchronously for production deployment."""
    await server.run_async(
        host="0.0.0.0",
        port=8080
    )

# Custom startup and shutdown hooks
@server.on_startup
async def startup_tasks():
    """Tasks to run on server startup."""
    print("🚀 Server starting up...")
    # Initialize data, warm up caches, etc.

@server.on_shutdown
async def shutdown_tasks():
    """Tasks to run on server shutdown."""
    print("🛑 Server shutting down...")
    # Cleanup resources, save state, etc.

# Access the underlying FastAPI app if needed
fastapi_app = server.get_app()

# Custom middleware
@server.middleware("http")
async def log_requests(request, call_next):
    """Log all API requests."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    print(f"{request.method} {request.url} - {response.status_code} ({process_time:.2f}s)")
    return response
```

### API Usage Examples

Once your server is running, endpoints are automatically available:

```bash
# Walker endpoint - POST request with parameters
curl -X POST "http://localhost:8000/api/users/process" \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "John Doe",
    "department": "engineering",
    "include_inactive": false,
    "max_connections": 5,
    "start_node": "n:Root:root"
  }'

# Function endpoint - GET request
curl "http://localhost:8000/api/users/count"

# Function endpoint with path parameters
curl "http://localhost:8000/api/cities/CA"

# Function endpoint with query parameters
curl "http://localhost:8000/api/users/paginated?page=1&page_size=10&department=engineering"

# API documentation is automatically available
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

### Best Practices

**✅ Recommended Patterns:**

```python path=null start=null
# Good: Use descriptive endpoint paths
@walker_endpoint("/api/users/analyze-connections", methods=["POST"])
class AnalyzeUserConnections(Walker):
    pass

# Good: Provide comprehensive field documentation
field_name: str = EndpointField(
    description="Clear description of what this field does",
    examples=["example1", "example2"],
    min_length=1,
    max_length=100
)

# Good: Use appropriate HTTP methods
@endpoint("/api/users", methods=["GET"])     # Retrieve data
@endpoint("/api/users", methods=["POST"])    # Create data
@walker_endpoint("/api/process", methods=["POST"])  # Process/execute

# Good: Group related fields
config_field: str = EndpointField(
    endpoint_group="configuration",
    description="Configuration parameter"
)

# Good: Handle errors appropriately in functions
@endpoint("/api/data")
async def get_data():
    try:
        data = await fetch_data()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**❌ Avoided Patterns:**

```python path=null start=null
# Bad: Vague endpoint paths
@walker_endpoint("/process")  # Too generic
@walker_endpoint("/api/thing")  # Unclear purpose

# Bad: Missing field documentation
field_name: str = EndpointField()  # No description or examples

# Bad: Exposing internal fields
internal_state: str = EndpointField()  # Should use exclude_endpoint=True

# Bad: Not handling errors in function endpoints
@endpoint("/api/data")
async def get_data():
    data = await risky_operation()  # No error handling
    return data  # Could fail with 500 error

# Bad: Using wrong HTTP methods
@endpoint("/api/users/delete", methods=["GET"])  # Should be DELETE
@walker_endpoint("/api/data/get", methods=["POST"])  # Should be GET for retrieval
```

---

## 🏗️ Library Architecture Concepts

**jvspatial** is an asynchronous, object-spatial Python library designed for building robust persistence and business logic application layers. Inspired by Jaseci's object-spatial paradigm and leveraging Python's async capabilities, jvspatial empowers developers to model complex relationships, traverse object graphs, and implement agent-based architectures that scale with modern cloud-native concurrency requirements. Key capabilities:

- Typed node/edge modeling via Pydantic
- Precise control over graph traversal
- Multi-backend persistence (JSON, MongoDB, etc.)
- Integrated REST API endpoints
- Async/await architecture

### Core Entities

1. **Object** - Base class for all entities with unified query interface
2. **Node** - Extends Object, represents graph nodes with spatial/contextual data
3. **Edge** - Represents relationships between nodes
4. **Walker** - Implements graph traversal and pathfinding algorithms
5. **GraphContext** - Low-level database interface (use sparingly)

Once a graph is established (nodes and edges are connected in a meaningful way), a walker may be spawned on the root node or anywhere on the graph. The visit method enacts the walker's traversal using a starting point or a list of nodes on the walker's visit queue.

As the walker traverses, it may conditionally trigger methods depending on its position on the graph. This is accomplished by the @on_visit annotation. Similarly, as the walker traverses over nodes and edges, these entities may conditionally trigger their methods based on the walker's visitation; also accomplished through the @on_visit annotation.

### Walker Traversal Pattern

The **recommended approach** for walker traversal is to use the `nodes()` method to get connected nodes for continued traversal.

#### Naming Convention for @on_visit Methods

**IMPORTANT**: When writing `@on_visit` decorated methods, use the following naming convention:

- **`here`**: Parameter name for the visited node/edge (the current location)
- **`visitor`**: Parameter name for the visiting walker (when accessing walker from node context)

```python path=null start=null
# ✅ RECOMMENDED: Use 'here' for the visited node
@on_visit("User")
async def process_user(self, here: Node):
    """Process user node - 'here' represents the current User being visited.

    Args:
        here: The visited User node
    """
    print(f"Currently visiting user: {here.name}")
    connected_users = await here.nodes(node=['User'])
    await self.visit(connected_users)

# ✅ RECOMMENDED: Use 'visitor' when walker is passed to node methods
def node_method_example(self, visitor: Walker):
    """Node method that receives the visiting walker.

    Args:
        visitor: The walker currently visiting this node
    """
    print(f"Being visited by walker: {visitor.__class__.__name__}")

# ❌ AVOID: Generic parameter names
@on_visit("User")
async def process_user(self, node: Node):  # Less clear
    pass

@on_visit("User")
async def process_user(self, n: Node):     # Too abbreviated
    pass
```

**Why this convention?**
- **`here`** clearly indicates the current location in graph traversal
- **`visitor`** clearly indicates the active walker performing the traversal
- Consistent with spatial/navigational metaphors used throughout jvspatial
- Makes code more readable and self-documenting
- Aligns with the library's entity-centric philosophy

```python
from jvspatial.core import Walker, Node
from jvspatial.decorators import on_visit, on_exit

class DataCollector(Walker):
    def __init__(self):
        super().__init__()
        self.collected_data = []
        self.processed_count = 0

    @on_visit("User")
    async def collect_user_data(self, here: Node):
        """Called when walker visits a User node.

        Args:
            here: The visited User node
        """
        self.collected_data.append(here.name)

        # RECOMMENDED: Use nodes() method to get connected nodes
        # Default direction="out" follows outgoing edges (forward traversal)
        next_nodes = await here.nodes()
        await self.visit(next_nodes)

        # Example with semantic filtering - filter connected Users by department
        engineering_users = await here.nodes(
            node=['User'],  # Only User nodes
            department="engineering",  # Simple kwargs filtering
            active=True  # Multiple simple filters
        )
        await self.visit(engineering_users)

    @on_visit("City")
    async def process_city(self, here: Node):
        """Process city nodes with filtering and control flow.

        Args:
            here: The visited City node
        """
        self.processed_count += 1

        # Skip processing for certain conditions
        if here.population < 10000:
            print(f"Skipping small city: {here.name}")
            self.skip()  # Skip to next node in queue
            return  # This line won't be reached

        # Disengage if we've processed enough
        if self.processed_count >= 10:
            print("Processed enough cities, disengaging...")
            await self.disengage()  # Permanently halt and remove from graph
            return

        # Continue with normal processing
        large_cities = await here.nodes(
            node=[{'City': {"context.population": {"$gte": 500_000}}}],
            direction="out"  # Explicit direction for clarity
        )
        await self.visit(large_cities)

        # Example: Mixed filtering approach - dict filters + kwargs
        nearby_cities = await here.nodes(
            node=[{'City': {"context.region": here.region}}],  # Complex filter
            state="NY",  # Simple kwargs filter
            active=True  # Additional simple filter
        )
        await self.visit(nearby_cities)

    @on_exit
    async def cleanup_and_report(self):
        """Called when walker completes or disengages."""
        print(f"Walker finished! Collected {len(self.collected_data)} items")
        print(f"Processed {self.processed_count} cities")
        # Perform cleanup, save results, send notifications, etc.
```

### Walker Control Flow Methods

#### `skip()` - Skip Current Node Processing
The `skip()` method allows you to immediately halt processing of the current node and proceed to the next node in the queue, similar to `continue` in a loop:

```python
class ConditionalWalker(Walker):
    @on_visit("Product")
    async def process_product(self, here: Node):
        """Process product nodes with conditional skipping.

        Args:
            here: The visited Product node
        """
        # Skip discontinued products
        if here.status == "discontinued":
            self.skip()  # Jump to next node in queue
            # Code below won't execute

        # Skip products outside price range
        if not (10 <= here.price <= 1000):
            print(f"Skipping {here.name} - price out of range")
            self.skip()

        # Normal processing for valid products
        print(f"Processing product: {here.name}")
        connected_products = await here.nodes(node=['Product'])
        await self.visit(connected_products)
```

#### `disengage()` - Permanently Halt and Remove Walker from Graph
The `disengage()` method permanently halts the walker and removes it from the graph. Once disengaged, the walker **cannot be resumed** and is considered finished:

```python
class CompletionWalker(Walker):
    def __init__(self):
        super().__init__()
        self.processed_count = 0
        self.max_items = 100
        self.critical_error = False

    @on_visit("Document")
    async def process_document(self, here: Node):
        """Process document nodes with completion tracking.

        Args:
            here: The visited Document node
        """
        try:
            # Process document
            await self.process_item(here)
            self.processed_count += 1

            # Disengage when reaching target or on critical error
            if self.processed_count >= self.max_items:
                print(f"Target reached: {self.processed_count} items processed")
                await self.disengage()  # Permanently finish
                return

            if self.critical_error:
                print("Critical error encountered, disengaging walker")
                await self.disengage()  # Permanently halt due to error
                return

            # Continue to next documents
            next_docs = await here.nodes(node=['Document'])
            await self.visit(next_docs)

        except CriticalError as e:
            print(f"Critical error: {e}")
            self.critical_error = True
            await self.disengage()  # Permanently halt on critical error

    @on_exit
    async def final_cleanup(self):
        """Called when walker disengages - perform final cleanup."""
        print(f"Walker disengaged. Final count: {self.processed_count}")
        # Perform final cleanup, save state, notify completion
        await self.save_final_results()

    async def process_item(self, node):
        """Process individual item."""
        # Simulate processing that might fail
        if node.status == "corrupted":
            raise CriticalError("Corrupted data detected")
        await asyncio.sleep(0.01)

    async def save_final_results(self):
        """Save final processing results."""
        print("💾 Saving final results...")

# Usage - disengage() creates permanent termination
walker = CompletionWalker()
root = await Root.get()

# Start and run to completion (or error)
walker = await walker.spawn(root)
print(f"Walker finished. Status: {'disengaged' if walker.paused else 'completed'}")

# NOTE: Once disengaged, walker cannot be resumed
# walker.resume() would not work - walker is permanently finished

# For pausable/resumable patterns, use different approaches:
# - Save walker state and create new walker instances
# - Use external queue/state management
# - Implement custom pause/resume logic in @on_visit methods
```

#### `pause()` and `resume()` - Temporary Walker Suspension
Walkers can be paused during traversal and resumed later, preserving their queue and state. Unlike `disengage()`, paused walkers can be resumed:

```python
class BatchProcessor(Walker):
    def __init__(self):
        super().__init__()
        self.processed_count = 0
        self.batch_size = 50
        self.total_batches = 0

    @on_visit("Document")
    async def process_document(self, here: Node):
        """Process document nodes with batch pausing.

        Args:
            here: The visited Document node
        """
        # Process document
        await self.heavy_processing(here)
        self.processed_count += 1

        # Pause after processing a batch
        if self.processed_count % self.batch_size == 0:
            self.total_batches += 1
            print(f"Batch {self.total_batches} complete ({self.processed_count} items)")
            print("Pausing for rate limiting...")

            # Clean pause using pause() method
            self.pause(f"Batch {self.total_batches} processing pause")

        # Continue to next documents
        next_docs = await here.nodes(node=['Document'], status="active")
        await self.visit(next_docs)

    async def heavy_processing(self, node):
        """Simulate expensive processing."""
        await asyncio.sleep(0.1)  # Simulate API calls, file I/O, etc.

    @on_exit
    async def report_completion(self):
        """Called when walker completes or is paused."""
        if self.paused:
            print(f"Walker paused after processing {self.processed_count} items")
        else:
            print(f"Walker completed! Total processed: {self.processed_count}")

# Usage - pause and resume cycle
walker = BatchProcessor()
root = await Root.get()

# Start processing - will pause after first batch
walker = await walker.spawn(root)
print(f"Walker state: {'paused' if walker.paused else 'completed'}")
print(f"Queue remaining: {len(walker.queue)} items")

# Simulate processing delay (rate limiting, API cooldown, etc.)
print("\n⏳ Waiting for rate limit cooldown...")
await asyncio.sleep(2.0)

# Resume processing - will continue from where it left off
print("\n▶️  Resuming processing...")
walker = await walker.resume()
print(f"Walker state after resume: {'paused' if walker.paused else 'completed'}")

# Can resume multiple times if walker gets paused again
while walker.paused and walker.queue:
    print(f"\n🔄 Walker paused again, {len(walker.queue)} items remaining")
    await asyncio.sleep(1.0)  # Brief pause
    walker = await walker.resume()

print("\n✅ All processing complete!")
```

#### Advanced Pause/Resume Patterns

```python
class SmartProcessor(Walker):
    def __init__(self):
        super().__init__()
        self.api_calls = 0
        self.max_api_calls = 100
        self.error_count = 0
        self.max_errors = 5

    @on_visit("DataNode")
    async def process_data(self, here: Node):
        """Process data nodes with smart rate limiting.

        Args:
            here: The visited DataNode
        """
        try:
            # Check rate limits
            if self.api_calls >= self.max_api_calls:
                print(f"Rate limit reached ({self.api_calls} calls), pausing...")
                self.api_calls = 0  # Reset counter
                self.pause("Rate limit reached")

            # Check error threshold
            if self.error_count >= self.max_errors:
                print(f"Too many errors ({self.error_count}), pausing for investigation")
                self.pause(f"Error threshold reached: {self.error_count} errors")

            # Process node
            result = await self.call_external_api(here)
            self.api_calls += 1

            # Continue traversal based on result
            if result.should_continue:
                related_nodes = await here.nodes(
                    node=['DataNode'],
                    status="pending",
                    priority={"$gte": result.priority_threshold}
                )
                await self.visit(related_nodes)

        except ApiError as e:
            self.error_count += 1
            print(f"API error #{self.error_count}: {e}")
            # Continue processing - don't pause on single errors

        except CriticalError as e:
            print(f"Critical error: {e}")
            self.pause(f"Critical error: {e}")

    async def call_external_api(self, node):
        """Simulate external API call that might fail."""
        await asyncio.sleep(0.05)  # Simulate API latency
        # Simulate occasional failures
        if random.random() < 0.1:  # 10% failure rate
            raise ApiError("Temporary API failure")
        return APIResult(should_continue=True, priority_threshold=5)

    def pause_for_maintenance(self):
        """Manually pause walker for maintenance."""
        print("🔧 Pausing for scheduled maintenance...")
        self.paused = True

    @on_exit
    async def maintenance_check(self):
        """Check if maintenance is needed when paused."""
        if self.paused:
            print("Walker paused - performing maintenance checks...")
            # Reset error counters, clear caches, etc.
            self.error_count = 0
            print("Maintenance complete - ready to resume")

# Usage with external control
walker = SmartProcessor()
root = await Root.get()

# Start processing
print("🚀 Starting smart processing...")
walker = await walker.spawn(root)

# External monitoring and control
while walker.paused and walker.queue:
    print(f"⏸️  Walker paused - {len(walker.queue)} items remaining")

    # Simulate external decision making
    if should_resume_processing():  # Your logic here
        print("🔄 Conditions met, resuming...")
        walker = await walker.resume()
    else:
        print("⏳ Waiting for conditions to improve...")
        await asyncio.sleep(5.0)

# Helper classes for example
class ApiError(Exception): pass
class CriticalError(Exception): pass
class APIResult:
    def __init__(self, should_continue, priority_threshold):
        self.should_continue = should_continue
        self.priority_threshold = priority_threshold

def should_resume_processing():
    """External logic to determine if processing should resume."""
    return True  # Simplified for example
```

#### `@on_exit` - Cleanup and Finalization
The `@on_exit` decorator marks methods to execute when the walker completes traversal or disengages:

```python
class AnalyticsWalker(Walker):
    def __init__(self):
        super().__init__()
        self.start_time = time.time()
        self.nodes_visited = 0
        self.errors_encountered = 0

    @on_visit("User")
    async def analyze_user(self, here: Node):
        """Analyze user behavior and traverse to related users.

        Args:
            here: The visited User node
        """
        try:
            self.nodes_visited += 1
            # Perform analysis
            await self.analyze_user_behavior(here)

            # Continue traversal
            related_users = await here.nodes(node=['User'])
            await self.visit(related_users)
        except Exception as e:
            self.errors_encountered += 1
            print(f"Error processing user {here.id}: {e}")

    @on_exit
    async def generate_report(self):
        """Generate analytics report when traversal completes."""
        duration = time.time() - self.start_time
        print("\n📊 Analytics Report")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Nodes visited: {self.nodes_visited}")
        print(f"Errors: {self.errors_encountered}")
        print(f"Success rate: {(1 - self.errors_encountered/max(self.nodes_visited, 1))*100:.1f}%")

    @on_exit
    def save_results(self):
        """Save results to database (sync version)."""
        # Save analytics data
        print("💾 Saving results to database...")

    @on_exit
    async def send_notifications(self):
        """Send completion notifications (async version)."""
        # Send email/slack notifications
        print("📧 Sending completion notifications...")

    async def analyze_user_behavior(self, user):
        """Simulate user behavior analysis."""
        await asyncio.sleep(0.01)  # Simulate work
```

### Walker Trail Tracking

Walkers include built-in **trail tracking** capabilities to monitor and record the complete path taken during graph traversal. This is invaluable for debugging, analytics, audit trails, and optimizing traversal strategies.

#### Basic Trail Tracking

```python path=null start=null
from jvspatial.core import Walker, on_visit

class TrailTrackingWalker(Walker):
    def __init__(self):
        super().__init__()
        # Enable trail tracking with memory management
        self.trail_enabled = True
        self.max_trail_length = 100  # Keep last 100 steps (0 = unlimited)

    @on_visit('User')
    async def process_user_with_trail(self, here: Node):
        """Process user nodes while tracking the traversal trail.

        Args:
            here: The visited User node
        """
        print(f"Processing user: {here.name}")

        # Access current trail information
        current_trail = self.get_trail()  # List of node IDs
        trail_length = self.get_trail_length()  # Current trail size
        recent_steps = self.get_recent_trail(count=3)  # Last 3 steps

        print(f"Trail length: {trail_length}, Recent: {recent_steps}")

        # Avoid revisiting recently visited nodes
        if here.id in recent_steps[:-1]:  # Exclude current node
            print(f"Recently visited {here.name}, skipping deeper traversal")
            self.skip()

        # Continue normal traversal
        colleagues = await here.nodes(
            node=['User'],
            department=here.department,
            active=True
        )
        await self.visit(colleagues)

    @on_exit
    async def generate_trail_report(self):
        """Generate comprehensive trail analysis report."""
        # Get trail with actual node objects (database lookups)
        trail_nodes = await self.get_trail_nodes()

        # Get complete path with connecting edges
        trail_path = await self.get_trail_path()

        # Generate detailed report
        self.response['trail_report'] = {
            'summary': {
                'total_steps': self.get_trail_length(),
                'unique_nodes': len(set(self.get_trail())),
                'efficiency_ratio': len(set(self.get_trail())) / max(self.get_trail_length(), 1)
            },
            'visited_nodes': [
                {'step': i+1, 'node_type': node.__class__.__name__, 'node_name': getattr(node, 'name', node.id)}
                for i, node in enumerate(trail_nodes)
            ],
            'path_analysis': [
                {
                    'step': i+1,
                    'node': node.name if hasattr(node, 'name') else node.id,
                    'via_edge': edge.edge_type if edge else 'start'
                }
                for i, (node, edge) in enumerate(trail_path)
            ]
        }

        print(f"\n📊 Trail Report Generated:")
        print(f"  - Total steps: {self.response['trail_report']['summary']['total_steps']}")
        print(f"  - Unique nodes: {self.response['trail_report']['summary']['unique_nodes']}")
        print(f"  - Path efficiency: {self.response['trail_report']['summary']['efficiency_ratio']:.2%}")

# Usage example
walker = TrailTrackingWalker()
root = await Root.get()
await walker.spawn(root)

# Access trail data
final_trail = walker.get_trail()
print(f"Final trail: {final_trail}")
print(f"Trail report: {walker.response.get('trail_report')}")
```

#### Advanced Trail Use Cases

```python path=null start=null
class AdvancedTrailWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.max_trail_length = 0  # Unlimited for comprehensive analysis
        self.visited_nodes = set()  # For cycle detection
        self.performance_metrics = []

    @on_visit('Document')
    async def process_with_cycle_detection(self, here: Node):
        """Process documents with cycle detection using trail data.

        Args:
            here: The visited Document node
        """
        import time
        start_time = time.time()

        # Cycle detection using trail
        if here.id in self.visited_nodes:
            trail = self.get_trail()
            first_visit_index = trail.index(here.id)
            cycle_length = len(trail) - first_visit_index - 1

            print(f"🔄 Cycle detected at {here.id}! Length: {cycle_length} steps")

            self.response.setdefault('cycles_detected', []).append({
                'node_id': here.id,
                'cycle_length': cycle_length,
                'first_visit_step': first_visit_index + 1,
                'detection_step': len(trail)
            })

            # Stop to avoid infinite loop
            await self.disengage()
            return

        self.visited_nodes.add(here.id)

        # Process document
        await self.analyze_document(here)

        # Record performance metrics
        processing_time = time.time() - start_time
        self.performance_metrics.append({
            'node_id': here.id,
            'processing_time': processing_time,
            'step_number': self.get_trail_length(),
            'metadata': self.get_trail_metadata()  # Get current step metadata
        })

        # Continue traversal with trail-aware filtering
        related_docs = await here.nodes(
            node=['Document'],
            status='active'
        )

        # Filter out recently visited to avoid cycles
        recent_trail = self.get_recent_trail(count=10)
        unvisited_docs = [doc for doc in related_docs if doc.id not in recent_trail]

        if unvisited_docs:
            await self.visit(unvisited_docs)
        else:
            print("All related documents recently visited, exploring alternatives")

    @on_visit('User')
    async def audit_user_access(self, here: Node):
        """Create audit trail for user access.

        Args:
            here: The visited User node
        """
        # Get current trail metadata (automatically includes timestamp, node_type, queue_length)
        metadata = self.get_trail_metadata()

        audit_entry = {
            'timestamp': metadata.get('timestamp'),
            'action': 'USER_ACCESS',
            'user_id': here.id,
            'user_name': getattr(here, 'name', 'Unknown'),
            'trail_step': self.get_trail_length(),
            'access_context': {
                'queue_size': metadata.get('queue_length'),
                'node_type': metadata.get('node_type'),
                'previous_steps': self.get_recent_trail(count=3)[:-1]  # Exclude current
            }
        }

        self.response.setdefault('audit_log', []).append(audit_entry)
        print(f"📝 Audit: Accessed user {here.id} at step {audit_entry['trail_step']}")

    @on_exit
    async def comprehensive_analysis(self):
        """Generate comprehensive trail and performance analysis."""
        trail_path = await self.get_trail_path()

        # Performance analysis
        avg_processing_time = sum(m['processing_time'] for m in self.performance_metrics) / len(self.performance_metrics) if self.performance_metrics else 0

        # Path efficiency analysis
        total_steps = self.get_trail_length()
        unique_nodes = len(set(self.get_trail()))

        self.response['comprehensive_analysis'] = {
            'trail_summary': {
                'total_steps': total_steps,
                'unique_nodes_visited': unique_nodes,
                'path_efficiency': unique_nodes / total_steps if total_steps > 0 else 0,
                'cycles_detected': len(self.response.get('cycles_detected', [])),
                'trail_enabled': self.trail_enabled,
                'trail_limit': self.max_trail_length
            },
            'performance_metrics': {
                'avg_processing_time': avg_processing_time,
                'total_processing_time': sum(m['processing_time'] for m in self.performance_metrics),
                'slowest_step': max(self.performance_metrics, key=lambda x: x['processing_time']) if self.performance_metrics else None
            },
            'audit_summary': {
                'total_audit_entries': len(self.response.get('audit_log', [])),
                'user_accesses': len([e for e in self.response.get('audit_log', []) if e['action'] == 'USER_ACCESS'])
            }
        }

        print("\n📈 Comprehensive Analysis Complete:")
        print(f"  - Path efficiency: {self.response['comprehensive_analysis']['trail_summary']['path_efficiency']:.2%}")
        print(f"  - Average processing time: {avg_processing_time:.3f}s")
        print(f"  - Cycles detected: {len(self.response.get('cycles_detected', []))}")

    async def analyze_document(self, doc):
        """Simulate document analysis."""
        import asyncio
        await asyncio.sleep(0.02)  # Simulate processing time

# Usage with trail management
walker = AdvancedTrailWalker()

# Enable debug mode for detailed trail information
walker.debug_mode = True

# Spawn and run analysis
root = await Root.get()
await walker.spawn(root)

# Access comprehensive results
analysis = walker.response.get('comprehensive_analysis', {})
cycles = walker.response.get('cycles_detected', [])
audit_log = walker.response.get('audit_log', [])

print(f"Analysis complete. Efficiency: {analysis.get('trail_summary', {}).get('path_efficiency', 0):.2%}")
print(f"Cycles detected: {len(cycles)}, Audit entries: {len(audit_log)}")
```

#### Trail API Quick Reference

**Configuration (Read/Write):**
- `self.trail_enabled = True` - Enable trail tracking
- `self.max_trail_length = N` - Limit trail to N steps (0 = unlimited)

**Trail Data (Read-Only Properties):**
- `self.trail` - List of visited node IDs (returns copy)
- `self.trail_edges` - Edge IDs between nodes (returns copy)
- `self.trail_metadata` - Metadata per step (returns deep copy)

**Trail Access Methods (O(1) operations):**
- `self.get_trail()` - Get list of visited node IDs
- `self.get_trail_length()` - Get current trail length
- `self.get_recent_trail(count=N)` - Get last N trail steps
- `self.clear_trail()` - Clear entire trail (only way to modify trail)

**Advanced Access (Database operations):**
- `await self.get_trail_nodes()` - Get actual Node objects from trail
- `await self.get_trail_path()` - Get trail with connecting edges
- `self.get_trail_metadata(step=-1)` - Get metadata for specific step

**Use Cases:**
- **Debugging**: Track walker path for troubleshooting
- **Cycle Detection**: Avoid infinite loops in graph traversal
- **Performance Analysis**: Measure processing time per step
- **Audit Trails**: Comprehensive access logging for compliance
- **Path Optimization**: Analyze and improve traversal efficiency

### Walker Queue Manipulation Methods

Walkers maintain an internal queue (deque) of nodes to visit during traversal. Advanced queue manipulation provides fine-grained control over traversal order, priority handling, and dynamic path planning. These methods allow you to programmatically manage the walker's traversal queue:

#### Core Queue Methods

```python path=null start=null
from jvspatial.core import Walker, Node
from jvspatial.decorators import on_visit
from typing import List, Optional

class QueueMasterWalker(Walker):
    def __init__(self):
        super().__init__()
        self.priority_nodes = []
        self.deferred_nodes = []
        self.processed_count = 0

    @on_visit("TaskNode")
    async def process_task(self, here: Node):
        """Demonstrate queue manipulation methods.

        Args:
            here: The visited TaskNode
        """

        # 1. INSPECT QUEUE STATE
        current_queue = self.get_queue()  # Get queue as list
        print(f"Current queue size: {len(current_queue)}")
        print(f"Queue contents: {[n.name for n in current_queue]}")

        # Check if specific node is queued
        if current_queue:
            next_node = current_queue[0]  # Peek at next node
            print(f"Next node to process: {next_node.name}")

        # 2. ADD NODES TO QUEUE
        # Find high-priority nodes to add immediately
        urgent_tasks = await here.nodes(
            node=['TaskNode'],
            priority={"$gte": 9},
            status="pending"
        )

        # Add to front of queue (high priority)
        if urgent_tasks:
            added = self.prepend(urgent_tasks)  # Add to front
            print(f"Added {len(added)} urgent tasks to front of queue")

        # Find normal tasks to add to end
        normal_tasks = await here.nodes(
            node=['TaskNode'],
            priority={"$lt": 9, "$gte": 5},
            status="pending"
        )

        # Add to end of queue (normal priority)
        if normal_tasks:
            added = self.append(normal_tasks)  # Add to end
            print(f"Added {len(added)} normal tasks to end of queue")

        # Alternative: Use visit() method (equivalent to append)
        additional_tasks = await here.nodes(node=['TaskNode'], status="new")
        if additional_tasks:
            self.visit(additional_tasks)  # Same as append()

        # Add nodes right after current processing
        immediate_tasks = await here.nodes(
            node=['TaskNode'],
            priority=10,  # Highest priority
            status="urgent"
        )
        if immediate_tasks:
            added = self.add_next(immediate_tasks)  # Add next in queue
            print(f"Added {len(added)} tasks to process immediately next")

        # 3. CONDITIONAL QUEUE MANIPULATION
        # Check if we have too many items in queue
        if len(self.get_queue()) > 100:
            print("Queue overflow detected, deferring low-priority items")

            # Get current queue and filter it
            current_queue = self.get_queue()
            low_priority = []
            high_priority = []

            for item in current_queue:
                if hasattr(item, 'priority') and item.priority < 5:
                    low_priority.append(item)
                else:
                    high_priority.append(item)

            # Clear queue and rebuild with high priority items only
            self.clear_queue()
            if high_priority:
                self.append(high_priority)

            # Store deferred items for later
            self.deferred_nodes.extend(low_priority)
            print(f"Deferred {len(low_priority)} low-priority items")

        # 4. TARGETED QUEUE MANIPULATION
        # Remove specific completed nodes from queue
        completed_nodes = await here.nodes(
            node=['TaskNode'],
            status="completed"
        )

        for completed in completed_nodes:
            if self.is_queued(completed):
                removed = self.dequeue(completed)
                print(f"Removed {len(removed)} completed tasks from queue")

        # 5. PRECISE QUEUE INSERTION
        # Find a specific node in queue to insert after
        checkpoint_tasks = await here.nodes(
            node=['TaskNode'],
            task_type="checkpoint"
        )

        followup_tasks = await here.nodes(
            node=['TaskNode'],
            depends_on=here.id
        )

        for checkpoint in checkpoint_tasks:
            if self.is_queued(checkpoint) and followup_tasks:
                try:
                    # Insert followup tasks right after checkpoint
                    inserted = self.insert_after(checkpoint, followup_tasks)
                    print(f"Inserted {len(inserted)} followup tasks after checkpoint")
                except ValueError as e:
                    print(f"Could not insert after checkpoint: {e}")

        self.processed_count += 1

    @on_visit("CompletionNode")
    async def handle_completion(self, here: Node):
        """Handle task completion and queue cleanup.

        Args:
            here: The visited CompletionNode
        """

        # Add back any deferred nodes if queue is manageable
        current_queue_size = len(self.get_queue())
        if current_queue_size < 20 and self.deferred_nodes:
            reactivated = self.deferred_nodes[:10]  # Add up to 10 back
            self.deferred_nodes = self.deferred_nodes[10:]  # Remove from deferred

            self.append(reactivated)
            print(f"Reactivated {len(reactivated)} deferred nodes")

        # Insert critical tasks right at the beginning
        critical_tasks = await here.nodes(
            node=['TaskNode'],
            priority=10,
            status="critical"
        )

        if critical_tasks:
            # Find first non-critical task and insert before it
            queue = self.get_queue()
            for i, queued_node in enumerate(queue):
                if hasattr(queued_node, 'priority') and queued_node.priority < 10:
                    try:
                        inserted = self.insert_before(queued_node, critical_tasks)
                        print(f"Inserted {len(inserted)} critical tasks before normal task")
                        break
                    except ValueError:
                        # If insertion fails, just prepend
                        self.prepend(critical_tasks)
                        break

    @on_exit
    async def final_report(self):
        """Report final queue statistics."""
        final_queue = self.get_queue()
        print(f"\n📊 Queue Processing Complete")
        print(f"Total processed: {self.processed_count}")
        print(f"Remaining in queue: {len(final_queue)}")
        print(f"Deferred nodes: {len(self.deferred_nodes)}")

        if final_queue:
            print("Remaining nodes:")
            for node in final_queue[:5]:  # Show first 5
                print(f"  - {node.name}")
            if len(final_queue) > 5:
                print(f"  ... and {len(final_queue) - 5} more")
```

#### Queue Method Reference

Based on the actual Walker implementation in jvspatial:

**Basic Queue Operations:**
- `self.visit(nodes)` - Add nodes to end of queue (equivalent to append)
- `self.append(nodes)` - Add nodes to end of queue
- `self.prepend(nodes)` - Add nodes to front of queue
- `self.add_next(nodes)` - Add nodes next in queue after current item
- `self.get_queue()` - Return entire queue as a list
- `self.clear_queue()` - Clear all nodes from queue
- `self.is_queued(node)` - Check if specific node is in queue

**Advanced Queue Operations:**
- `self.dequeue(nodes)` - Remove specific nodes from queue
- `self.insert_after(target_node, nodes)` - Insert nodes after target node
- `self.insert_before(target_node, nodes)` - Insert nodes before target node

#### Priority-Based Queue Management

```python path=null start=null
class PriorityQueueWalker(Walker):
    def __init__(self):
        super().__init__()
        self.priority_buckets = {
            'urgent': [],      # Priority 9-10
            'high': [],        # Priority 7-8
            'normal': [],      # Priority 4-6
            'low': []          # Priority 1-3
        }

    @on_visit("WorkItem")
    async def process_work_item(self, here: Node):
        """Process work items with priority-based queuing.

        Args:
            here: The visited WorkItem node
        """

        # Get connected work items
        connected_items = await here.nodes(
            node=['WorkItem'],
            status="pending"
        )

        if connected_items:
            # Sort into priority buckets
            self._sort_into_priority_buckets(connected_items)

            # Process highest priority items first
            self._add_by_priority_order()

    def _sort_into_priority_buckets(self, nodes: List[Node]):
        """Sort nodes into priority-based buckets."""
        for node in nodes:
            priority = getattr(node, 'priority', 5)

            if priority >= 9:
                self.priority_buckets['urgent'].append(node)
            elif priority >= 7:
                self.priority_buckets['high'].append(node)
            elif priority >= 4:
                self.priority_buckets['normal'].append(node)
            else:
                self.priority_buckets['low'].append(node)

        print(f"Sorted into buckets: "
              f"urgent={len(self.priority_buckets['urgent'])}, "
              f"high={len(self.priority_buckets['high'])}, "
              f"normal={len(self.priority_buckets['normal'])}, "
              f"low={len(self.priority_buckets['low'])}")

    def _add_by_priority_order(self):
        """Add nodes to walker queue in priority order."""
        # Process urgent items first (add to front)
        if self.priority_buckets['urgent']:
            self.prepend(self.priority_buckets['urgent'])
            self.priority_buckets['urgent'].clear()

        # Add high priority items to front (after urgent)
        if self.priority_buckets['high']:
            # Insert at beginning but after urgent items
            current_queue = self.get_queue()
            if current_queue:
                # Find first non-urgent item and insert before it
                high_items = self.priority_buckets['high']
                self.priority_buckets['high'].clear()

                try:
                    # Try to find insertion point
                    first_non_urgent = None
                    for node in current_queue:
                        if hasattr(node, 'priority') and node.priority < 9:
                            first_non_urgent = node
                            break

                    if first_non_urgent:
                        self.insert_before(first_non_urgent, high_items)
                    else:
                        self.append(high_items)  # All items are urgent

                except ValueError:
                    # Fallback to prepend if insertion fails
                    self.prepend(high_items)
            else:
                self.prepend(self.priority_buckets['high'])
                self.priority_buckets['high'].clear()

        # Add normal priority items to end
        if self.priority_buckets['normal']:
            self.append(self.priority_buckets['normal'])
            self.priority_buckets['normal'].clear()

        # Only add low priority if queue is small
        current_queue_size = len(self.get_queue())
        if current_queue_size < 50 and self.priority_buckets['low']:
            low_items = self.priority_buckets['low'][:10]  # Limit low priority
            self.priority_buckets['low'] = self.priority_buckets['low'][10:]
            self.append(low_items)
```

#### Dynamic Queue Filtering and Manipulation

```python path=null start=null
class AdaptiveQueueWalker(Walker):
    def __init__(self):
        super().__init__()
        self.queue_stats = {
            'added': 0,
            'removed': 0,
            'filtered': 0,
            'reordered': 0
        }

    @on_visit("FilterNode")
    async def adaptive_filtering(self, here: Node):
        """Demonstrate dynamic queue filtering and manipulation.

        Args:
            here: The visited FilterNode
        """

        # Add new nodes based on current context
        candidates = await here.nodes(
            node=['ProcessNode'],
            active=True
        )

        if candidates:
            # Filter candidates before adding to queue
            filtered_candidates = self._filter_candidates(candidates)

            if filtered_candidates:
                # Smart queue insertion based on current load
                current_queue_size = len(self.get_queue())

                if current_queue_size < 20:
                    # Low load: add all to end
                    self.append(filtered_candidates)
                    self.queue_stats['added'] += len(filtered_candidates)
                else:
                    # High load: add only high-priority to front
                    high_priority = [
                        c for c in filtered_candidates
                        if getattr(c, 'priority', 0) >= 8
                    ]
                    if high_priority:
                        self.prepend(high_priority)
                        self.queue_stats['added'] += len(high_priority)

        # Periodic queue maintenance
        if hasattr(here, 'name') and here.name.endswith('_maintenance'):
            self._perform_queue_maintenance()

    def _filter_candidates(self, candidates: List[Node]) -> List[Node]:
        """Filter candidates based on various criteria."""
        filtered = []
        current_queue = self.get_queue()

        for candidate in candidates:
            # Check if already in queue (avoid duplicates)
            if self.is_queued(candidate):
                continue

            # Check resource constraints (mock implementation)
            if hasattr(candidate, 'resource_requirement'):
                if candidate.resource_requirement > self._get_available_resources():
                    continue

            # Check dependencies (mock implementation)
            if hasattr(candidate, 'dependencies'):
                if not self._dependencies_met(candidate.dependencies):
                    continue

            filtered.append(candidate)

        self.queue_stats['filtered'] += len(candidates) - len(filtered)
        return filtered

    def _perform_queue_maintenance(self):
        """Perform queue cleanup and optimization."""
        current_queue = self.get_queue()
        if not current_queue:
            return

        print("🔧 Performing queue maintenance...")

        # 1. Remove stale items (mock - would check expiration)
        non_stale = []
        removed_stale = 0

        for item in current_queue:
            if hasattr(item, 'expires_at'):
                # Mock expiration check
                if not getattr(item, 'is_expired', False):
                    non_stale.append(item)
                else:
                    removed_stale += 1
            else:
                non_stale.append(item)

        # 2. Deduplicate items by ID
        seen_ids = set()
        deduplicated = []
        removed_duplicates = 0

        for item in non_stale:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                deduplicated.append(item)
            else:
                removed_duplicates += 1

        # 3. Reorder by priority
        optimized = sorted(
            deduplicated,
            key=lambda x: getattr(x, 'priority', 0),
            reverse=True
        )

        # 4. Rebuild queue with optimized order
        self.clear_queue()
        if optimized:
            self.append(optimized)

        self.queue_stats['removed'] += removed_stale + removed_duplicates
        self.queue_stats['reordered'] += 1

        print(f"Maintenance complete: removed {removed_stale} stale, "
              f"{removed_duplicates} duplicates, optimized {len(optimized)} items")

    def _get_available_resources(self) -> int:
        """Mock implementation - get available system resources."""
        return 100

    def _dependencies_met(self, dependencies: List[str]) -> bool:
        """Mock implementation - check if dependencies are satisfied."""
        return True

    @on_exit
    async def report_queue_stats(self):
        """Report queue manipulation statistics."""
        print("\n📈 Queue Statistics:")
        for stat, value in self.queue_stats.items():
            print(f"  {stat.capitalize()}: {value}")
```

#### Best Practices for Queue Manipulation

**✅ Recommended Patterns:**

```python path=null start=null
# Good: Check queue state before manipulation
current_queue = self.get_queue()
if current_queue:
    next_item = current_queue[0]  # Look at next item
    # Make decisions based on next item

# Good: Use appropriate method for insertion priority
if item.priority >= 8:
    self.prepend([item])          # High priority to front
else:
    self.append([item])           # Normal priority to end

# Good: Check if node is queued before operations
if self.is_queued(completed_node):
    self.dequeue(completed_node)

# Good: Batch queue operations for efficiency
new_items = await node.nodes(filters)
if new_items:
    self.append(new_items)  # Add all at once

# Good: Safe queue iteration and modification
current_queue = self.get_queue()  # Get snapshot
filtered_items = [n for n in current_queue if meets_criteria(n)]
self.clear_queue()
if filtered_items:
    self.append(filtered_items)

# Good: Precise insertion with error handling
try:
    self.insert_after(target_node, new_nodes)
except ValueError:
    # Target not found, use alternative
    self.prepend(new_nodes)
```

**❌ Avoided Patterns:**

```python path=null start=null
# Bad: Modifying queue during iteration
for item in self.get_queue():  # Don't iterate over changing queue
    if condition:
        self.dequeue(item)  # Modifying during iteration

# Bad: Not handling insertion errors
self.insert_after(target_node, nodes)  # Could raise ValueError

# Bad: Inefficient repeated operations
for item in items:
    self.append([item])  # Many small operations
# Better: self.append(items)  # Single batch operation

# Bad: Not checking queue state
first_item = self.get_queue()[0]  # Could cause IndexError if empty

# Bad: Assuming nodes are still queued
self.dequeue(node)  # Node might not be in queue
# Better: if self.is_queued(node): self.dequeue(node)
```

**Key Points:**
- Use `await node.nodes()` to get connected nodes for traversal (NOT `get_edges()`)
- Default `direction="out"` follows outgoing edges (recommended for forward traversal)
- Use `direction="in"` for reverse traversal along incoming edges
- Use `direction="both"` for bidirectional traversal
- **Semantic Filtering Approaches:**
  - **Simple filtering**: Use kwargs for connected node properties: `state="NY"`
  - **Complex node filtering**: `node=[{'City': {"context.population": {"$gte": 500000}}}]`
  - **Complex edge filtering**: `edge=[{'Highway': {"context.condition": {"$ne": "poor"}}}]`
  - **Mixed approaches**: Combine dict filters with kwargs for maximum flexibility
- **Database-Level Optimization**: All filtering happens at database level for performance
- **MongoDB-Style Operators**: `$gte`, `$lt`, `$ne`, `$in`, `$nin`, `$regex`, etc.
- **Walker Control Flow:**
  - **`skip()`**: Skip current node processing, continue to next (like `continue` in loops)
  - **`pause()`/`resume()`**: Temporarily pause walker (use `self.pause()`), can be resumed later
  - **`disengage()`**: Permanently halt walker and remove from graph (cannot be resumed)
  - **`@on_exit`**: Methods called when walker completes, pauses, or disengages (cleanup)
- The `nodes()` method returns a list that can be directly passed to `walker.visit()`

### Inheritance Hierarchy

```
Object (base class with unified query interface)
├── Node (spatial graph nodes)
├── Edge (relationships)
└── Custom entities (inherit from Node/Object)
```

### Database Backends

- **JSONDatabase** - File-based storage for development/testing
- **MongoDatabase** - MongoDB backend for production
- **Custom databases** - Implement DatabaseInterface

## 📚 Documentation Maintenance

### README Updates

When adding new features:

1. **Review existing README.md**
2. **Update feature list** if adding major functionality
3. **Update installation/setup** if dependencies change
4. **Update usage examples** to reflect new capabilities
5. **Maintain consistency** with existing documentation style

### Documentation Directory

Always review and update `docs/` directory:

```
docs/
├── api/           # API reference documentation
├── guides/        # User guides and tutorials
├── architecture/  # System design documents
└── examples/      # Code examples and tutorials
```

**Update procedure:**
1. Check if new feature requires new documentation files
2. Update existing API documentation for modified classes/methods
3. Add user guides for complex features
4. Update architecture docs if design patterns change

## 💡 Examples Maintenance

### Example Directory Structure

```
examples/
├── basic/                          # Simple usage examples
├── advanced/                      # Complex scenarios
├── modern_query_interface.py      # Comprehensive entity-centric CRUD operations
├── semantic_filtering.py          # Advanced semantic filtering with Node.nodes()
└── migration/                     # Migration guides (if needed)
```

### Example Update Procedure

1. **Review existing examples** for relevance to new features
2. **Update outdated examples** to use modern entity-centric syntax
3. **Create new examples** for significant new features
4. **Ensure examples are runnable** and well-documented
5. **Remove or archive obsolete examples**
6. **Update key reference examples:**
   - `modern_query_interface.py` - Showcase latest entity-centric patterns
   - `semantic_filtering.py` - Demonstrate advanced Node.nodes() filtering
   - Basic examples - Keep simple, focused, and beginner-friendly
   - Advanced examples - Show complex real-world scenarios

### Example Code Standards

Examples should:
- Use entity-centric syntax exclusively
- Include comprehensive comments
- Demonstrate best practices
- Be self-contained and runnable
- Show error handling patterns

## 🧪 Testing Requirements

### Test Organization

```
tests/
├── api/           # FastAPI endpoint tests
├── core/          # Core entity and logic tests
├── db/            # Database backend tests
└── integration/   # End-to-end integration tests
```

### Testing Procedure for New Features

1. **Unit Tests** - Test individual methods and classes
2. **Integration Tests** - Test feature interaction with database
3. **API Tests** - Test HTTP endpoints if applicable
4. **Performance Tests** - For database-heavy features

### Test Code Standards

```python
import pytest
from typing import List
from jvspatial.core import Node, Walker, Edge
from jvspatial.decorators import on_visit
from jvspatial.exceptions import NodeNotFoundError, ValidationError

class TestUser(Node):
    name: str = ""
    email: str = ""
    department: str = ""
    age: int = 0
    active: bool = True
    skills: List[str] = []

class TestDepartment(Node):
    name: str = ""
    location: str = ""
    budget: int = 0

class TestWalker(Walker):
    def __init__(self):
        super().__init__()
        self.visited_users = []

    @on_visit("TestUser")
    async def visit_user(self, node: TestUser):
        self.visited_users.append(node.name)
        # Test semantic filtering in walker
        connected_users = await node.nodes(
            node=['TestUser'],
            department=node.department,
            active=True
        )
        await self.visit(connected_users)

# Entity Creation Tests
@pytest.mark.asyncio
async def test_user_creation():
    """Test entity-centric user creation with full data."""
    user = await TestUser.create(
        name="Alice Johnson",
        email="alice@company.com",
        department="engineering",
        age=30,
        skills=["python", "javascript"]
    )
    assert user.name == "Alice Johnson"
    assert user.email == "alice@company.com"
    assert user.department == "engineering"
    assert user.id is not None
    assert "python" in user.skills

# MongoDB-Style Query Tests
@pytest.mark.asyncio
async def test_mongodb_queries():
    """Test comprehensive MongoDB-style queries."""
    # Setup test data
    await TestUser.create(name="Bob Smith", email="bob@test.com", age=25, department="engineering")
    await TestUser.create(name="Carol Davis", email="carol@test.com", age=35, department="marketing")
    await TestUser.create(name="David Brown", email="david@test.com", age=45, department="engineering")

    # Test regex queries
    b_users = await TestUser.find({"context.name": {"$regex": "^B", "$options": "i"}})
    assert len(b_users) >= 1
    assert any(u.name.startswith("B") for u in b_users)

    # Test comparison operators
    senior_users = await TestUser.find({"context.age": {"$gte": 35}})
    assert all(u.age >= 35 for u in senior_users)

    # Test logical operators
    senior_engineers = await TestUser.find({
        "$and": [
            {"context.department": "engineering"},
            {"context.age": {"$gte": 30}}
        ]
    })
    assert all(u.department == "engineering" and u.age >= 30 for u in senior_engineers)

    # Test array operations
    tech_users = await TestUser.find({"context.skills": {"$in": ["python", "javascript"]}})
    assert all(any(skill in u.skills for skill in ["python", "javascript"]) for u in tech_users)

# Semantic Filtering Tests
@pytest.mark.asyncio
async def test_semantic_filtering():
    """Test Node.nodes() semantic filtering capabilities."""
    # Create test nodes and edges
    dept = await TestDepartment.create(name="Engineering", location="SF")
    user1 = await TestUser.create(name="Alice", department="engineering", active=True)
    user2 = await TestUser.create(name="Bob", department="engineering", active=False)
    user3 = await TestUser.create(name="Carol", department="marketing", active=True)

    # Create connections
    await Edge.create(source=dept, target=user1, edge_type="employs")
    await Edge.create(source=dept, target=user2, edge_type="employs")
    await Edge.create(source=user1, target=user3, edge_type="collaborates")

    # Test simple filtering
    active_employees = await dept.nodes(
        node=['TestUser'],
        active=True
    )
    assert len(active_employees) == 1
    assert active_employees[0].name == "Alice"

    # Test complex filtering
    engineering_employees = await dept.nodes(
        node=[{'TestUser': {"context.department": "engineering"}}],
        active=True
    )
    assert all(u.department == "engineering" and u.active for u in engineering_employees)

    # Test mixed filtering
    collaborators = await user1.nodes(
        node=[{'TestUser': {"context.active": True}}],
        department="marketing"
    )
    assert len(collaborators) >= 1

# Walker Tests
@pytest.mark.asyncio
async def test_walker_traversal():
    """Test walker with semantic filtering."""
    # Setup graph
    root = await TestUser.create(name="Root", department="engineering")
    user1 = await TestUser.create(name="User1", department="engineering", active=True)
    user2 = await TestUser.create(name="User2", department="marketing", active=True)

    await Edge.create(source=root, target=user1, edge_type="manages")
    await Edge.create(source=root, target=user2, edge_type="manages")
    await Edge.create(source=user1, target=user2, edge_type="collaborates")

    # Test walker
    walker = TestWalker()
    await walker.spawn(root)

    # Verify walker visited users
    assert "Root" in walker.visited_users
    assert len(walker.visited_users) >= 1

# Error Handling Tests
@pytest.mark.asyncio
async def test_error_handling():
    """Test proper error handling patterns."""
    # Test NodeNotFoundError
    with pytest.raises(NodeNotFoundError):
        await TestUser.get("nonexistent-id")

    # Test safe retrieval
    user = await TestUser.find_one({"context.email": "nonexistent@test.com"})
    assert user is None

    # Test validation errors (if validation is implemented)
    with pytest.raises((ValidationError, ValueError)):
        await TestUser.create(name="", email="invalid-email")

# Performance Tests
@pytest.mark.asyncio
async def test_bulk_operations():
    """Test bulk operations performance."""
    # Create multiple users
    users_data = [
        {"name": f"User{i}", "email": f"user{i}@test.com", "department": "engineering"}
        for i in range(10)
    ]

    # Bulk create
    users = []
    for user_data in users_data:
        user = await TestUser.create(**user_data)
        users.append(user)

    assert len(users) == 10

    # Bulk query
    engineering_users = await TestUser.find({"context.department": "engineering"})
    assert len(engineering_users) >= 10

    # Bulk update
    for user in users[:5]:
        user.active = False
        await user.save()

    # Verify updates
    inactive_users = await TestUser.find({"context.active": False})
    assert len(inactive_users) >= 5

# Integration Tests
@pytest.mark.asyncio
async def test_full_workflow():
    """Test complete entity lifecycle with relationships."""
    # Create department
    dept = await TestDepartment.create(name="Product", location="NYC", budget=1000000)

    # Create users
    manager = await TestUser.create(
        name="Jane Manager",
        email="jane@company.com",
        department="product",
        age=40
    )

    employee = await TestUser.create(
        name="John Employee",
        email="john@company.com",
        department="product",
        age=28
    )

    # Create relationships
    await Edge.create(source=dept, target=manager, edge_type="employs")
    await Edge.create(source=dept, target=employee, edge_type="employs")
    await Edge.create(source=manager, target=employee, edge_type="manages")

    # Test traversal
    department_employees = await dept.nodes(node=['TestUser'])
    assert len(department_employees) == 2

    managed_employees = await manager.nodes(
        node=['TestUser'],
        direction="out",
        edge=['manages']
    )
    assert len(managed_employees) == 1
    assert managed_employees[0].name == "John Employee"

    # Test complex query
    young_employees = await dept.nodes(
        node=[{'TestUser': {"context.age": {"$lt": 30}}}]
    )
    assert len(young_employees) == 1
    assert young_employees[0].age < 30

    # Cleanup
    await manager.delete()
    await employee.delete()
    await dept.delete()

    # Verify deletion
    deleted_manager = await TestUser.find_one({"context.email": "jane@company.com"})
    assert deleted_manager is None
```

## 🗑️ Cleanup and Maintenance

### Deprecation Procedure

When evolving the library:

1. **Identify obsolete code** - Old patterns, unused utilities
2. **Mark as deprecated** - Add deprecation warnings before removal
3. **Update documentation** - Remove references to deprecated features
4. **Update examples** - Remove or update examples using deprecated code
5. **Clean removal** - Remove deprecated code after grace period

### File Cleanup Checklist

- [ ] Remove unused import statements
- [ ] Delete empty or obsolete modules
- [ ] Archive outdated examples to `examples/archive/`
- [ ] Update `__all__` exports in `__init__.py` files
- [ ] Remove commented-out code blocks
- [ ] Clean up temporary test files

### Migration Strategy

When making breaking changes:

1. **Create migration guide** in `docs/migration/`
2. **Provide before/after examples**
3. **Update all existing examples** to new patterns
4. **Add runtime warnings** for deprecated usage
5. **Version appropriately** using semantic versioning

## 🚀 Development Workflow

### Pre-commit Checklist

- [ ] Code passes `black --check .`
- [ ] Code passes `flake8 .`
- [ ] Code passes `mypy .`
- [ ] All tests pass: `pytest`
- [ ] Examples are updated and runnable
- [ ] Documentation reflects changes
- [ ] Deprecated code is cleaned up

### Code Review Focus Areas

1. **Entity-centric patterns** - Ensure new code uses preferred syntax
2. **Query interface consistency** - MongoDB-style queries throughout
3. **Type safety** - Proper annotations and mypy compliance
4. **Test coverage** - Adequate testing for new features
5. **Documentation completeness** - Examples and guides updated

## 📋 Quick Reference

### Preferred Patterns

```python path=null start=null
# ✅ Entity creation
user = await User.create(name="Alice", email="alice@company.com", department="engineering")

# ✅ Entity queries with MongoDB-style operators
users = await User.find({"context.active": True})
user = await User.find_one({"context.email": email})
senior_engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.age": {"$gte": 35}}
    ]
})
tech_users = await User.find({"context.skills": {"$in": ["python", "javascript"]}})

# ✅ Counting and aggregation
count = await User.count({"context.department": "engineering"})
departments = await User.distinct("department")

# ✅ Entity updates
user.name = "Alice Johnson"
user.active = True
await user.save()

# ✅ Bulk updates
users = await User.find({"context.department": "old_dept"})
for user in users:
    user.department = "new_dept"
    await user.save()

# ✅ Entity deletion
await user.delete()

# ✅ Walker traversal with semantic filtering
@on_visit("User")
async def process_user(self, here: Node):
    """Process user nodes with semantic filtering.

    Args:
        here: The visited User node
    """
    # Use nodes() method with semantic filtering
    connected_users = await here.nodes(
        node=['User'],           # Type filtering
        department="engineering", # Simple kwargs
        active=True             # Multiple simple filters
    )
    await self.visit(connected_users)

    # Complex filtering with MongoDB operators
    senior_connections = await here.nodes(
        node=[{'User': {"context.age": {"$gte": 35}}}],
        direction="out"
    )
    await self.visit(senior_connections)

# ✅ Walker control flow
class MyWalker(Walker):
    @on_visit("Document")
    async def process_document(self, here: Node):
        """Process document nodes with control flow.

        Args:
            here: The visited Document node
        """
        if here.status == "archived":
            self.skip()  # Skip to next node

        if self.processed_count >= 100:
            await self.disengage()  # Permanently halt

        # Normal processing
        next_docs = await here.nodes(node=['Document'], active=True)
        await self.visit(next_docs)

    @on_exit
    async def cleanup(self):
        print(f"Processed {self.processed_count} documents")

# ✅ Error handling
try:
    user = await User.get(user_id)
except NodeNotFoundError:
    logger.warning(f"User {user_id} not found")
    return None
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    raise
```

### Avoided Patterns

```python path=null start=null
# ❌ Direct database access (discouraged)
db = get_database()
await db.create("node", data)
await db.find("node", {"name": "User"})

# ❌ GraphContext methods (discouraged)
ctx = GraphContext(db)
await ctx.create_node(data)
await ctx.get_edges(node_id)

# ❌ Non-standard query formats
await User.find({"age": 25})  # Missing context. prefix
await User.find({"name": "Alice"})  # Should be context.name

# ❌ Old traversal patterns (deprecated)
walker.get_edges(node)  # Use node.nodes() instead
walker.traverse_edges()  # Use semantic filtering

# ❌ Synchronous operations
user = User.create_sync(**data)  # Use async await User.create()
users = User.find_sync(query)   # Use async await User.find()

# ❌ Manual edge management in walkers (show proper naming even in bad examples)
@on_visit("User")
async def visit_user(self, here: Node):
    """DEPRECATED: Manual edge management (avoid this pattern).

    Args:
        here: The visited User node
    """
    # Avoid manual edge retrieval
    edges = await here.get_edges()  # Deprecated
    for edge in edges:
        target = await edge.get_target()
        await self.visit([target])

    # Instead, use semantic filtering
    connected = await here.nodes()  # Preferred
    await self.visit(connected)

# ❌ Missing error handling
user = await User.get(user_id)  # Should handle NodeNotFoundError
user.field = value
await user.save()  # Should handle ValidationError

# ❌ Inefficient queries
# Don't fetch all then filter in Python
all_users = await User.find({})
engineers = [u for u in all_users if u.department == "engineering"]

# Instead, filter at database level
engineers = await User.find({"context.department": "engineering"})

# ❌ Blocking operations in async context
@on_visit("DataNode")
async def process_node(self, here: Node):
    """BAD EXAMPLE: Blocking operations in async context.

    Args:
        here: The visited DataNode
    """
    # Avoid blocking operations
    time.sleep(1.0)  # Blocks event loop

    # Use async alternatives
    await asyncio.sleep(1.0)  # Non-blocking
```

---

## 🎯 Key Naming Conventions

**CRITICAL**: When writing `@on_visit` methods, always use these parameter names:

- **`here`** - The visited node/edge (current location in traversal)
- **`visitor`** - The walker performing the traversal (when passed to node methods)

```python path=null start=null
# ✅ CORRECT naming convention
@on_visit("User")
async def process_user(self, here: Node):
    """Args: here = visited User node"""
    connected = await here.nodes()
    await self.visit(connected)

# ❌ AVOID generic names
@on_visit("User")
async def process_user(self, node: Node):  # Less clear
    pass
```

---

**Remember**: This library prioritizes **clean, maintainable code** with **consistent patterns** across all database backends. Always favor the entity-centric approach, MongoDB-style queries, and the **`here`/`visitor`** naming convention for the best developer experience.
