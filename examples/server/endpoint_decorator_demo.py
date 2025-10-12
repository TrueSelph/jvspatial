"""
Endpoint Decorator Demo

This example demonstrates the new decorator functionality:
1. @walker_endpoint - Register Walker classes to default server
2. @endpoint - Register regular functions to default server
3. Dynamic walker removal capabilities

Features demonstrated:
- @walker_endpoint decorator usage
- @endpoint decorator for simple function routes
- Walker removal and cleanup
- Mixed Walker and function endpoints

Run with: python endpoint_decorator_demo.py
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException

from jvspatial.api import create_server, endpoint
from jvspatial.api.endpoint.decorators import EndpointField
from jvspatial.api.routing.endpoint import EndpointRouter
from jvspatial.core.entities import Node, Root, Walker, on_visit

# ====================== DATA MODEL ======================


class Product(Node):
    """Simple product model."""

    name: str
    price: float
    category: str = "general"
    in_stock: bool = True
    quantity: int = 0


# ====================== SERVER SETUP ======================

server = create_server(
    title="Endpoint Decorator Demo API",
    description="Demonstrating @walker_endpoint and @endpoint decorators",
    version="1.0.0",
    debug=True,
    db_type="json",
    db_path="jvdb/endpoint_demo",
)

print(f"📋 Server created: {server.config.title}")


# ====================== WALKER ENDPOINTS ======================


@endpoint("/products/create")
class CreateProduct(Walker):
    """Create product using server instance decorator."""

    name: str = EndpointField(description="Product name", min_length=1, max_length=100)

    price: float = EndpointField(description="Product price", gt=0.0)

    category: str = EndpointField(default="general", description="Product category")

    quantity: int = EndpointField(default=0, description="Initial stock quantity", ge=0)

    @on_visit(Root)
    async def create_product(self, here):
        try:
            product = await Product.create(
                name=self.name,
                price=self.price,
                category=self.category,
                quantity=self.quantity,
                in_stock=self.quantity > 0,
            )

            await here.connect(product)

            return self.endpoint.success(
                data={
                    "product_id": product.id,
                    "name": product.name,
                    "price": product.price,
                    "category": product.category,
                    "quantity": product.quantity,
                },
                message="Product created successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Failed to create product", details={"error": str(e)}
            )


@endpoint("/products/search", methods=["POST"])
class SearchProducts(Walker):
    """Search products using @walker_endpoint decorator."""

    category: Optional[str] = EndpointField(
        default=None, description="Filter by category"
    )

    min_price: Optional[float] = EndpointField(
        default=None, description="Minimum price filter", ge=0.0
    )

    max_price: Optional[float] = EndpointField(
        default=None, description="Maximum price filter", ge=0.0
    )

    in_stock_only: bool = EndpointField(
        default=True, description="Only show products in stock"
    )

    @on_visit(Root)
    async def search_products(self, here):
        try:
            all_products = await Product.all()
            filtered_products = []

            for product in all_products:
                # Apply filters
                if self.category and product.category != self.category:
                    continue
                if self.min_price is not None and product.price < self.min_price:
                    continue
                if self.max_price is not None and product.price > self.max_price:
                    continue
                if self.in_stock_only and not product.in_stock:
                    continue

                filtered_products.append(
                    {
                        "id": product.id,
                        "name": product.name,
                        "price": product.price,
                        "category": product.category,
                        "in_stock": product.in_stock,
                        "quantity": product.quantity,
                    }
                )

            return self.endpoint.success(
                data={
                    "products": filtered_products,
                    "count": len(filtered_products),
                    "filters": {
                        "category": self.category,
                        "min_price": self.min_price,
                        "max_price": self.max_price,
                        "in_stock_only": self.in_stock_only,
                    },
                },
                message="Search completed successfully",
            )

        except Exception as e:
            return self.endpoint.error(
                message="Search failed", details={"error": str(e)}
            )


@endpoint("/products/bulk-update", methods=["POST"], tags=["bulk"])
class BulkUpdateProducts(Walker):
    """Bulk update products - demonstrates additional parameters."""

    product_ids: List[str] = EndpointField(description="List of product IDs to update")

    price_multiplier: Optional[float] = EndpointField(
        default=None, description="Multiply prices by this factor", gt=0.0
    )

    new_category: Optional[str] = EndpointField(
        default=None, description="Set new category for all products"
    )

    adjust_stock: Optional[int] = EndpointField(
        default=None, description="Adjust stock quantity (can be negative)"
    )

    @on_visit(Root)
    async def bulk_update(self, here):
        try:
            updated_products = []
            failed_products = []

            for product_id in self.product_ids:
                try:
                    product = await Product.get(product_id)
                    if not product:
                        failed_products.append(
                            {"id": product_id, "error": "Product not found"}
                        )
                        continue

                    # Apply updates
                    changes = {}

                    if self.price_multiplier is not None:
                        old_price = product.price
                        product.price = round(old_price * self.price_multiplier, 2)
                        changes["price"] = {"old": old_price, "new": product.price}

                    if self.new_category is not None:
                        old_category = product.category
                        product.category = self.new_category
                        changes["category"] = {
                            "old": old_category,
                            "new": product.category,
                        }

                    if self.adjust_stock is not None:
                        old_quantity = product.quantity
                        product.quantity = max(0, old_quantity + self.adjust_stock)
                        product.in_stock = product.quantity > 0
                        changes["quantity"] = {
                            "old": old_quantity,
                            "new": product.quantity,
                        }
                        changes["in_stock"] = product.in_stock

                    await product.save()

                    updated_products.append(
                        {"id": product.id, "name": product.name, "changes": changes}
                    )

                except Exception as e:
                    failed_products.append({"id": product_id, "error": str(e)})

            if failed_products and not updated_products:
                return self.endpoint.error(
                    message="Bulk update failed",
                    details={
                        "failed_products": failed_products,
                        "summary": {
                            "total": len(self.product_ids),
                            "successful": 0,
                            "failed": len(failed_products),
                        },
                    },
                )
            elif failed_products:
                return self.endpoint.success(
                    data={
                        "updated_products": updated_products,
                        "failed_products": failed_products,
                        "summary": {
                            "total": len(self.product_ids),
                            "successful": len(updated_products),
                            "failed": len(failed_products),
                        },
                    },
                    message="Bulk update partially completed",
                )
            else:
                return self.endpoint.success(
                    data={
                        "updated_products": updated_products,
                        "summary": {
                            "total": len(self.product_ids),
                            "successful": len(updated_products),
                            "failed": 0,
                        },
                    },
                    message="Bulk update completed successfully",
                )

        except Exception as e:
            return self.endpoint.error(
                message="Bulk update failed", details={"error": str(e)}
            )


# ====================== FUNCTION ENDPOINTS ======================


@endpoint("/products", methods=["GET"])
async def list_all_products(limit: int = 100, category: Optional[str] = None):
    """List all products using @endpoint decorator."""
    try:
        products = await Product.all()

        # Apply category filter if specified
        if category:
            products = [p for p in products if p.category == category]

        # Apply limit
        products = products[:limit]

        return {
            "products": [
                {
                    "id": product.id,
                    "name": product.name,
                    "price": product.price,
                    "category": product.category,
                    "in_stock": product.in_stock,
                    "quantity": product.quantity,
                }
                for product in products
            ],
            "count": len(products),
            "filters": {"category": category, "limit": limit},
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@endpoint("/products/categories", methods=["GET"])
async def get_categories():
    """Get all product categories."""
    try:
        products = await Product.all()
        categories = list(set(product.category for product in products))

        # Count products per category
        category_counts = {}
        for product in products:
            category = product.category
            category_counts[category] = category_counts.get(category, 0) + 1

        return {
            "categories": categories,
            "category_counts": category_counts,
            "total_categories": len(categories),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@endpoint("/products/{product_id}", methods=["GET"])
async def get_product_by_id(product_id: str):
    """Get a specific product by ID."""
    try:
        product = await Product.get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        return {
            "product": {
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "category": product.category,
                "in_stock": product.in_stock,
                "quantity": product.quantity,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@endpoint("/products/{product_id}", methods=["DELETE"])
async def delete_product(product_id: str):
    """Delete a product."""
    try:
        product = await Product.get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # In a real implementation, you'd delete the product from the database
        # For this demo, we'll just mark it as out of stock
        product.in_stock = False
        product.quantity = 0
        await product.save()

        return {
            "status": "success",
            "message": f"Product {product.name} marked as deleted",
            "product_id": product_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================== WALKER MANAGEMENT ENDPOINTS ======================


@endpoint("/admin/walkers", methods=["GET"])
async def list_walker_endpoints():
    """List all registered walkers - demonstrates server introspection."""
    try:
        walker_info = server.list_walker_endpoints_safe()

        return {"registered_walkers": walker_info, "count": len(walker_info)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@endpoint("/admin/walkers/{walker_name}/remove", methods=["DELETE"])
async def remove_walker(walker_name: str):
    """Remove a walker by name - demonstrates dynamic removal."""
    try:
        # Get walker info using public API
        walker_info = server.list_walker_endpoints()

        if walker_name not in walker_info:
            raise HTTPException(
                status_code=404, detail=f"Walker {walker_name} not found"
            )

        # Get the path from walker info and remove by path
        walker_path = walker_info[walker_name]["path"]
        removed = server.unregister_endpoint_by_path(walker_path)

        if removed > 0:
            return {
                "status": "success",
                "message": f"Walker {walker_name} removed from registration",
                "note": "Endpoint may still be accessible until server restart due to FastAPI limitations",
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to remove walker")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====================== STARTUP CONFIGURATION ======================


@server.on_startup
async def initialize_products():
    """Create sample products."""
    print("🔄 Initializing sample products...")

    sample_products = [
        await Product.create(
            name="Laptop Pro", price=1299.99, category="electronics", quantity=15
        ),
        await Product.create(
            name="Coffee Mug", price=12.50, category="kitchen", quantity=50
        ),
        await Product.create(
            name="Programming Book", price=39.99, category="books", quantity=25
        ),
        await Product.create(
            name="Desk Chair", price=249.99, category="furniture", quantity=8
        ),
        await Product.create(
            name="Smartphone",
            price=699.99,
            category="electronics",
            quantity=0,  # Out of stock
            in_stock=False,
        ),
    ]

    root = await Root.get()  # type: ignore[call-arg]
    for product in sample_products:
        await root.connect(product)

    print(f"✅ Created {len(sample_products)} sample products")


async def demonstrate_walker_removal():
    """Demonstrate dynamic walker removal after startup."""
    await asyncio.sleep(3)  # Wait for startup to complete

    print("\n🔄 Demonstrating walker removal...")

    # List current walkers
    walker_info = server.list_walker_endpoints()
    print(f"📋 Currently registered walkers: {len(walker_info)}")
    for name, info in walker_info.items():
        print(f"  • {name}: {info['path']} {info['methods']}")

    # Remove the bulk update walker by name
    if "BulkUpdateProducts" in walker_info:
        bulk_walker_path = walker_info["BulkUpdateProducts"]["path"]
        print(f"\n🗑️ Removing walker: BulkUpdateProducts at {bulk_walker_path}")
        removed = server.unregister_endpoint_by_path(bulk_walker_path)
        print(f"Removal {'successful' if removed > 0 else 'failed'}")

        # List walkers again
        walker_info = server.list_walker_endpoints()
        print(f"📋 Walkers after removal: {len(walker_info)}")
        for name in walker_info.keys():
            print(f"  • {name}")


@server.on_startup
async def schedule_walker_removal():
    """Schedule walker removal demonstration."""
    asyncio.create_task(demonstrate_walker_removal())


# ====================== MAIN EXECUTION ======================

if __name__ == "__main__":
    print("🌟 Endpoint Decorator Demo")
    print("=" * 50)
    print("This demo shows the new decorator functionality:")
    print("• @walker_endpoint - Register Walker classes")
    print("• @endpoint - Register regular functions")
    print("• Dynamic walker removal")
    print("• Mixed endpoint types in one API")
    print()

    print("📋 Available endpoints:")
    print("  Walker endpoints:")
    print("    • POST /api/products/create - Create product (server decorator)")
    print("    • POST /api/products/search - Search products (@walker_endpoint)")
    print("    • POST /api/products/bulk-update - Bulk update (@walker_endpoint)")
    print("  Function endpoints:")
    print("    • GET /products - List products (@endpoint)")
    print("    • GET /products/categories - Get categories (@endpoint)")
    print("    • GET /products/{id} - Get product by ID (@endpoint)")
    print("    • DELETE /products/{id} - Delete product (@endpoint)")
    print("  Admin endpoints:")
    print("    • GET /admin/walkers - List registered walkers")
    print("    • DELETE /admin/walkers/{name}/remove - Remove walker")
    print()

    print("🔧 Starting server...")
    print("📖 API docs: http://127.0.0.1:8002/docs")
    print("💡 Watch for walker removal demonstration after startup!")
    print()

    # Run the server
    server.run(
        host="127.0.0.1",
        port=8002,
        reload=False,  # Disable reload to see dynamic operations
    )
