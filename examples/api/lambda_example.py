"""AWS Lambda Serverless Deployment Example

This example demonstrates how to deploy a jvspatial FastAPI server to AWS Lambda
using Mangum as the ASGI adapter.

Usage:
    1. Install dependencies:
       pip install mangum>=0.17.0
       # Or install optional dependencies:
       pip install jvspatial[serverless]

    2. For local testing with SAM CLI or similar:
       python lambda_example.py

    3. For AWS Lambda deployment:
       - Package this file and dependencies
       - Set handler to: lambda_example.handler
       - Deploy to AWS Lambda with API Gateway trigger

Key Features:
- Serverless-compatible FastAPI application
- Automatic Mangum integration
- Works with AWS Lambda and API Gateway
- Supports all jvspatial features (walkers, endpoints, etc.)
- Database configuration for Lambda environment
"""

from typing import Any, Dict

from jvspatial.api import Server, create_lambda_handler, endpoint
from jvspatial.core import Node

# =============================================================================
# DATA MODELS
# =============================================================================


class ProductNode(Node):
    """Product node in the graph database."""

    name: str = ""
    description: str = ""
    price: float = 0.0
    category: str = ""
    in_stock: bool = True


# =============================================================================
# SERVER SETUP
# =============================================================================

# Create server instance with serverless mode enabled
# When serverless_mode=True, the Lambda handler is automatically created
# Note: For Lambda, you typically want to configure database to use
# environment variables or Lambda layers for persistence
server = Server(
    title="Lambda API Example",
    description="jvspatial API deployed on AWS Lambda",
    version="1.0.0",
    # Enable serverless mode - handler will be created automatically
    serverless_mode=True,
    # Serverless configuration options
    serverless_lifespan="auto",  # Enable startup/shutdown events
    # serverless_api_gateway_base_path="/prod",  # Uncomment if using API Gateway base path
    # Database configuration - use environment variables in Lambda
    # For Lambda, DynamoDB is recommended for persistent storage
    # Option 1: DynamoDB (recommended for Lambda)
    db_type="dynamodb",
    dynamodb_table_name="jvspatial_lambda",  # Or use environment variable
    dynamodb_region="us-east-1",  # Or use environment variable
    # Option 2: JSON (ephemeral, uses /tmp)
    # db_type="json",
    # db_path="/tmp/jvdb",  # Lambda /tmp directory (ephemeral)
    # Disable docs in production Lambda if desired
    docs_url="/docs",
    auth_enabled=False,
)


# =============================================================================
# ENDPOINTS
# =============================================================================


@endpoint("/health", methods=["GET"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for Lambda."""
    return {
        "status": "healthy",
        "service": "lambda-api",
        "environment": "serverless",
    }


@endpoint("/products", methods=["GET"])
async def list_products() -> Dict[str, Any]:
    """List all products."""
    products = await ProductNode.find()
    return {
        "products": [product.export() for product in products],
        "count": len(products),
    }


@endpoint("/products", methods=["POST"])
async def create_product(
    name: str,
    description: str,
    price: float,
    category: str,
    in_stock: bool = True,
) -> Dict[str, Any]:
    """Create a new product."""
    product = await ProductNode.create(
        name=name,
        description=description,
        price=price,
        category=category,
        in_stock=in_stock,
    )
    return {"product": product.export(), "message": "Product created successfully"}


@endpoint("/products/{product_id}", methods=["GET"])
async def get_product(product_id: str) -> Dict[str, Any]:
    """Get a specific product by ID."""
    product = await ProductNode.get(product_id)
    if not product:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Product not found")

    return {"product": product.export()}


# =============================================================================
# LAMBDA HANDLER
# =============================================================================

# With serverless_mode=True, the handler is automatically:
# 1. Created during server initialization
# 2. Exposed as a module-level 'handler' variable for AWS Lambda
#
# AWS Lambda will call this handler (e.g., "lambda_example.handler").
# No manual assignment needed when serverless_mode=True!

# The handler is automatically available as 'handler' at module level.
# You can also access it via:
# - server.lambda_handler (property)
# - server.get_lambda_handler() (method)

# Note: If you need to override the auto-exposed handler, you can still assign it:
# handler = server.lambda_handler  # or custom handler

# Alternative: Manual handler creation (if serverless_mode=False)
# handler = create_lambda_handler(server)
# handler = server.get_lambda_handler(lifespan="auto")


# =============================================================================
# LOCAL TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("AWS Lambda Serverless Deployment Example")
    print("=" * 80)
    print()
    print("This example demonstrates serverless deployment with jvspatial.")
    print()
    print("For AWS Lambda deployment:")
    print("  1. Package this file and dependencies")
    print("  2. Set Lambda handler to: lambda_example.handler")
    print("  3. Configure API Gateway trigger")
    print("  4. Set environment variables for database configuration")
    print()
    print("For local testing, the server will run normally:")
    print("  - Visit http://localhost:8000/docs for API documentation")
    print("  - Test endpoints at http://localhost:8000/api/...")
    print()
    print("=" * 80)

    # For local development/testing, run the server normally
    server.run(host="127.0.0.1", port=8000)
