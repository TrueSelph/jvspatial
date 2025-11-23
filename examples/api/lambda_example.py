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
- Automatic Mangum integration with transparent handler exposure
- Works with AWS Lambda and API Gateway
- Supports all jvspatial features (walkers, endpoints, etc.)
- Automatic Lambda temp directory detection and configuration
"""

import asyncio
from typing import Any, Dict

from jvspatial.api import endpoint
from jvspatial.api.lambda_server import LambdaServer
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

# Create LambdaServer instance
# LambdaServer automatically:
# - Sets DynamoDB as default database (can be overridden)
# - Creates and exposes Lambda handler as 'handler'
# - Detects and uses Lambda temp directory (/tmp) for file-based databases
# - Configures Mangum for AWS Lambda compatibility
server = LambdaServer(
    title="Lambda API Example",
    description="jvspatial API deployed on AWS Lambda",
    version="1.0.0",
    # Serverless configuration options (optional)
    serverless_lifespan="auto",  # Enable startup/shutdown events
    # serverless_api_gateway_base_path="/prod",  # Uncomment if using API Gateway base path
    # Database configuration (DynamoDB is default)
    dynamodb_table_name="jvspatial_lambda",  # Or use environment variable
    dynamodb_region="us-east-1",  # Or use environment variable
    # Alternative: Use file-based databases with Lambda temp directory
    # db_type="json",  # Will use /tmp/jvdb (ephemeral)
    # db_type="sqlite",  # Will use /tmp/jvdb/sqlite/jvspatial.db (ephemeral)
    # Note: File-based databases use ephemeral /tmp storage in Lambda.
    # Data will be lost between invocations. Use DynamoDB for persistence.
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
    import asyncio

    products_list = await asyncio.gather(*[product.export() for product in products])
    return {
        "products": products_list,
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
    return {
        "product": await product.export(),
        "message": "Product created successfully",
    }


@endpoint("/products/{product_id}", methods=["GET"])
async def get_product(product_id: str) -> Dict[str, Any]:
    """Get a specific product by ID."""
    product = await ProductNode.get(product_id)
    if not product:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Product not found")

    return {"product": await product.export()}


# =============================================================================
# LAMBDA HANDLER
# =============================================================================

# LambdaServer automatically creates the handler during initialization.
# AWS Lambda requires the handler to be available at module level.
# Simply call get_lambda_handler() and assign it to a module-level variable.

# Get handler and assign to module-level variable (required for Lambda deployment)
# Lambda will call this handler (e.g., "lambda_example.handler")
handler = server.get_lambda_handler()

# The handler is now available as 'handler' at module level.
# You can also access it via:
# - server.lambda_handler (property)


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
    print("  4. That's it! No additional configuration needed.")
    print("     - Handler is available via server.get_lambda_handler()")
    print("     - Lambda temp directory (/tmp) is automatically used")
    print("     - DynamoDB is the default database (persistent)")
    print()
    print("Note: LambdaServer does not support run() - Lambda handles execution.")
    print("      For local testing, use Server class instead.")
    print()
    print("=" * 80)
