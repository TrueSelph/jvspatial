"""AWS Lambda Serverless Deployment Example - Global Server Pattern

This example demonstrates how to deploy a jvspatial FastAPI server to AWS Lambda
when the server is instantiated within the library or a separate module, not in
the main handler file.

Usage:
    1. Install dependencies:
       pip install mangum>=0.17.0
       # Or install optional dependencies:
       pip install jvspatial[serverless]

    2. For AWS Lambda deployment:
       - Package this file and dependencies
       - Set handler to: lambda_example_global.handler
       - Deploy to AWS Lambda with API Gateway trigger

Key Features:
- Server instantiated in library/separate module
- Handler exposed using global server context
- Works with AWS Lambda and API Gateway
- Supports all jvspatial features (walkers, endpoints, etc.)
"""

import asyncio
from typing import Any, Dict

from jvspatial.api import endpoint, get_current_server
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
# SERVER SETUP (in library or separate module)
# =============================================================================

# In a real scenario, the server might be created in:
# - A separate module (e.g., app_config.py)
# - A library initialization function
# - A factory function
# - Or imported from another package

# For this example, we'll simulate this by creating the server in a function
# that would typically be in a separate module:


def _initialize_app_server():
    """Initialize the server (typically in a separate module or library).

    This function simulates server initialization that happens in the library
    or a separate configuration module, not in the main handler file.
    """
    # Create LambdaServer instance
    # This would typically be in app_config.py or similar
    server = LambdaServer(
        title="Lambda API Example (Global Server)",
        description="jvspatial API deployed on AWS Lambda with global server pattern",
        version="1.0.0",
        serverless_lifespan="auto",
        # Database configuration (DynamoDB is default)
        dynamodb_table_name="jvspatial_lambda_global",
        dynamodb_region="us-east-1",
        docs_url="/docs",
        auth_enabled=False,
    )

    # Server is now available globally via get_current_server()
    return server


# Initialize the server (this would be called during module import or app startup)
_initialize_app_server()


# =============================================================================
# ENDPOINTS
# =============================================================================


@endpoint("/health", methods=["GET"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for Lambda."""
    return {
        "status": "healthy",
        "service": "lambda-api-global",
        "environment": "serverless",
        "pattern": "global-server",
    }


@endpoint("/products", methods=["GET"])
async def list_products() -> Dict[str, Any]:
    """List all products."""
    products = await ProductNode.find()
    return {
        "products": await asyncio.gather(*[product.export() for product in products]),
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
#
# Since the server is instantiated in the library/separate module, we get it
# via get_current_server() and then use server.get_lambda_handler() to get the handler.

# Get the current server instance (created in _initialize_app_server or library)
server = get_current_server()

if server is None:
    raise RuntimeError(
        "No server instance found. Ensure the server is initialized before "
        "getting the Lambda handler."
    )

# Type check: ensure server is a LambdaServer instance
if not isinstance(server, LambdaServer):
    raise RuntimeError(
        "Server instance is not a LambdaServer. "
        "Lambda handler is only available for LambdaServer instances."
    )

# Get handler and assign to module-level variable (required for Lambda deployment)
# Lambda will call this handler (e.g., "lambda_example_global.handler")
handler = server.get_lambda_handler()


# =============================================================================
# LOCAL TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("AWS Lambda Serverless Deployment Example - Global Server Pattern")
    print("=" * 80)
    print()
    print("This example demonstrates serverless deployment when the server")
    print("is instantiated in a library or separate module.")
    print()
    print("For AWS Lambda deployment:")
    print("  1. Package this file and dependencies")
    print("  2. Set Lambda handler to: lambda_example_global.handler")
    print("  3. Configure API Gateway trigger")
    print("  4. The server is accessed via get_current_server()")
    print("  5. The handler is obtained using server.get_lambda_handler()")
    print()
    print("Note: LambdaServer does not support run() - Lambda handles execution.")
    print("      For local testing, use Server class instead.")
    print()
    print("=" * 80)
