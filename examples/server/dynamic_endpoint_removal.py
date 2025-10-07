"""
Example demonstrating dynamic endpoint removal with a running FastAPI server.
This example shows how to:
1. Start a server with multiple endpoints
2. Dynamically remove endpoints while server is running
3. Verify that endpoints are properly removed and FastAPI app is rebuilt
"""

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager

import uvicorn

from jvspatial.api.server import Server, endpoint, walker_endpoint
from jvspatial.core.entities import Node, Walker, on_visit

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create server with endpoints
server = Server(
    title="Dynamic Endpoint Removal Demo",
    description="Demonstrates runtime endpoint removal",
    debug=True,
    port=8002,
)


# Walker endpoints to test removal
@server.walker("/api/user-walker")
class UserWalker(Walker):
    username: str = "test_user"

    @on_visit(Node)
    async def process_user(self, here):
        return self.endpoint.success(
            data={"result": f"Processing user: {self.username}"},
            message="User processed successfully",
        )


@server.walker("/api/admin-walker")
class AdminWalker(Walker):
    admin_action: str = "check_status"

    @on_visit(Node)
    async def process_admin(self, here):
        return self.endpoint.success(
            data={"admin_result": f"Admin action: {self.admin_action}"},
            message="Admin action completed",
        )


# Function endpoints to test removal
@server.route("/api/info")
def get_info():
    """Get server information."""
    return {"message": "Server info endpoint", "active": True}


@server.route("/api/status")
def get_status():
    """Get server status."""
    return {"status": "running", "endpoints": "active"}


@endpoint("/api/debug")
def debug_endpoint():
    """Debug endpoint using package-style registration."""
    return {"debug": "This is a debug endpoint", "timestamp": time.time()}


async def demonstrate_endpoint_removal():
    """Demonstrate endpoint removal with a running server."""

    # Wait a moment for server to start
    await asyncio.sleep(2)

    logger.info("🎯 Starting dynamic endpoint removal demonstration...")

    # Show initial endpoints
    logger.info("📋 Initial endpoints:")
    walker_endpoints = server.list_walker_endpoints()
    function_endpoints = server.list_function_endpoints()
    logger.info(f"  Walkers: {list(walker_endpoints.keys())}")
    logger.info(f"  Functions: {list(function_endpoints.keys())}")

    # Wait and then start removing endpoints
    await asyncio.sleep(3)
    logger.info("⏰ Starting endpoint removal in 3 seconds...")

    # Remove a walker endpoint
    await asyncio.sleep(3)
    logger.info("🗑️  Removing UserWalker...")
    success = server.unregister_walker_class(UserWalker)
    logger.info(f"   UserWalker removal: {'✅ Success' if success else '❌ Failed'}")

    # Remove a function endpoint by reference
    await asyncio.sleep(2)
    logger.info("🗑️  Removing get_info function...")
    success = server.unregister_endpoint(get_info)
    logger.info(f"   get_info removal: {'✅ Success' if success else '❌ Failed'}")

    # Remove a function endpoint by path
    await asyncio.sleep(2)
    logger.info("🗑️  Removing /api/debug endpoint...")
    success = server.unregister_endpoint("/api/debug")
    logger.info(f"   /api/debug removal: {'✅ Success' if success else '❌ Failed'}")

    # Show remaining endpoints
    await asyncio.sleep(1)
    logger.info("📋 Remaining endpoints:")
    walker_endpoints = server.list_walker_endpoints()
    function_endpoints = server.list_function_endpoints()
    logger.info(f"  Walkers: {list(walker_endpoints.keys())}")
    logger.info(f"  Functions: {list(function_endpoints.keys())}")

    # Remove all endpoints from a path
    await asyncio.sleep(2)
    logger.info("🗑️  Removing all endpoints from /api/admin-walker...")
    removed_count = server.unregister_endpoint_by_path("/api/admin-walker")
    logger.info(f"   Removed {removed_count} endpoints")

    # Final state
    await asyncio.sleep(1)
    logger.info("📋 Final endpoints:")
    all_endpoints = server.list_all_endpoints()
    logger.info(f"  Walkers: {list(all_endpoints['walkers'].keys())}")
    logger.info(f"  Functions: {list(all_endpoints['functions'].keys())}")

    logger.info("✅ Dynamic endpoint removal demonstration complete!")


# Custom startup to demonstrate the removal
@server.on_startup
async def setup_demonstration():
    """Set up the demonstration."""
    logger.info("🚀 Server started! Setting up endpoint removal demonstration...")

    # Schedule the demonstration to run in the background
    asyncio.create_task(demonstrate_endpoint_removal())


def main():
    """Run the demonstration server."""
    print("🌟 Dynamic Endpoint Removal Demonstration")
    print("📖 This example shows how endpoints can be removed from a running server")
    print("🔗 Server will start at http://localhost:8002")
    print("📚 API docs: http://localhost:8002/docs")
    print()
    print("🎬 Watch the logs to see endpoints being removed dynamically!")
    print("⏹️  Press Ctrl+C to stop the server")
    print()

    # Add an endpoint to stop the server programmatically
    @server.route("/api/shutdown", methods=["POST"])
    def shutdown_server():
        """Shutdown the server."""
        logger.info("🛑 Shutdown requested...")

        # Schedule shutdown after responding
        def delayed_shutdown():
            time.sleep(1)
            import os

            os._exit(0)

        threading.Thread(target=delayed_shutdown, daemon=True).start()
        return {"message": "Server shutting down..."}

    try:
        server.run(host="0.0.0.0", port=8002, reload=False)
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")


if __name__ == "__main__":
    main()
