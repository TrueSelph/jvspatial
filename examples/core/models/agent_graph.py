"""Agent Graph Example

Demonstrates building a hierarchical agent system using jvspatial conventions.
Shows entity-centric CRUD operations, MongoDB-style queries, proper walker patterns,
and API endpoint integration following jvspatial best practices.

This example builds an agent system: Root -> App -> Agents -> MyAgent -> Actions
Follows jvspatial conventions for:
- Entity-centric syntax (Agent.create(), Agent.find(), etc.)
- MongoDB-style query interface with dot notation
- Proper @on_visit parameter naming ('here' for visited node)
- Type annotations and error handling
- API endpoint patterns with EndpointField
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from jvspatial.api import Server, create_server, endpoint
from jvspatial.api.decorators import EndpointField
from jvspatial.core import Node, Root, Walker, on_exit, on_visit

# Configure environment for example
os.environ.setdefault("JVSPATIAL_DB_TYPE", "json")
os.environ.setdefault("JVSPATIAL_JSONDB_PATH", "./jvdb/agent_graph")


# ============== NODE DEFINITIONS ==============


class App(Node):
    """Application node representing the main app."""

    name: str = ""
    version: str = "1.0.0"
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: Optional[datetime] = None


class Agents(Node):
    """Container node representing a collection of agents."""

    name: str = "AgentCollection"
    total_agents: int = 0
    active_agents: int = 0


class MyAgent(Node):
    """Individual agent node with spatial properties and capabilities."""

    name: str = ""
    published: bool = True
    latitude: float = 0.0
    longitude: float = 0.0
    capabilities: List[str] = Field(default_factory=list)
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: Optional[datetime] = None


class Actions(Node):
    """Container node representing a collection of actions."""

    name: str = "ActionsCollection"
    total_actions: int = 0
    enabled_actions: int = 0


class Action(Node):
    """Base action node with execution capabilities."""

    name: str = ""
    enabled: bool = True
    action_type: str = "generic"
    description: str = ""
    execution_count: int = 0
    last_executed: Optional[datetime] = None


class FirstAction(Action):
    """First type of action with specific capabilities."""

    action_type: str = "first"
    priority: int = 1


class SecondAction(Action):
    """Second type of action with different capabilities."""

    action_type: str = "second"
    priority: int = 2


class ThirdAction(Action):
    """Third type of action with unique properties."""

    action_type: str = "third"
    priority: int = 3


# ============== API ENDPOINTS ==============

# Initialize API server
server = Server(
    title="Agent Graph API",
    description="Hierarchical agent system with spatial capabilities",
    version="1.0.0",
)


@endpoint("/api/agents/interact", methods=["POST"])
class InteractWalker(Walker):
    """Walker to interact with the agent hierarchy and demonstrate traversal patterns."""

    target_agent_name: str = EndpointField(
        default="",
        description="Name of specific agent to target (optional)",
        examples=["ProductionAgent", "TestAgent"],
    )

    include_inactive: bool = EndpointField(
        default=False, description="Whether to include inactive agents in processing"
    )

    max_actions: int = EndpointField(
        default=3,
        description="Maximum number of actions to process per agent",
        ge=1,
        le=10,
    )

    timeout_seconds: int = EndpointField(
        default=30,
        description="Maximum execution time in seconds",
        ge=1,
        le=60,
    )

    @on_visit(Root)
    async def visit_root(self, here: Root):
        """Start traversal from root node.

        Args:
            here: The visited Root node
        """
        print("🚀 Starting agent hierarchy traversal from Root")

        # RECOMMENDED: Use entity-centric find with MongoDB-style queries
        app_nodes = await App.find({"context.status": "active"})

        if not app_nodes:
            print("📦 No active App nodes found, creating new App")
            app = await App.create(name="AgentSystem", version="1.0.0", status="active")
            await here.connect(app)
            await self.visit([app])
        else:
            print(f"✅ Found {len(app_nodes)} active App nodes")
            await self.visit(app_nodes)

    @on_visit(App)
    async def visit_app(self, here: App):
        """Process app node and find agent collections.

        Args:
            here: The visited App node
        """
        print(f"📱 Processing App: {here.name} (v{here.version})")

        # Update app status
        here.last_active = datetime.now()
        await here.save()

        # RECOMMENDED: Use nodes() method for graph traversal
        agents_nodes = await here.nodes(node=["Agents"])

        if not agents_nodes:
            print("👥 Creating new Agents collection")
            agents = await Agents.create(name="MainAgentCollection")
            await here.connect(agents)
            await self.visit([agents])
        else:
            print(f"✅ Found {len(agents_nodes)} Agents collections")
            await self.visit(agents_nodes)

    @on_visit(Agents)
    async def visit_agents(self, here: Agents):
        """Process agents collection and find individual agents.

        Args:
            here: The visited Agents node
        """
        print(f"👥 Processing Agents collection: {here.name}")

        # Build query filters based on walker parameters
        query_filters: Dict[str, Any] = {"context.published": True}
        if not self.include_inactive:
            query_filters["context.status"] = "active"

        # Add specific agent name filter if provided
        if self.target_agent_name:
            query_filters["context.name"] = self.target_agent_name

        # RECOMMENDED: Use MongoDB-style queries with entity-centric syntax
        my_agents = await MyAgent.find(query_filters)

        if not my_agents:
            if self.target_agent_name:
                print(f"🤖 Creating targeted agent: {self.target_agent_name}")
                agent = await MyAgent.create(
                    name=self.target_agent_name,
                    latitude=40.7128,  # NYC coordinates
                    longitude=-74.0060,
                    capabilities=["data_processing", "api_integration"],
                    status="active",
                )
            else:
                print("🤖 Creating default agent")
                agent = await MyAgent.create(
                    name="DefaultAgent",
                    latitude=37.7749,  # SF coordinates
                    longitude=-122.4194,
                    capabilities=["general_purpose"],
                    status="active",
                )

            await here.connect(agent)
            my_agents = [agent]

        # Update collection statistics
        here.total_agents = len(my_agents)
        here.active_agents = len([a for a in my_agents if a.status == "active"])
        await here.save()

        print(f"✅ Found {len(my_agents)} matching agents")
        await self.visit(my_agents)

    @on_visit(MyAgent)
    async def visit_agent(self, here: MyAgent):
        """Process individual agent and find its actions.

        Args:
            here: The visited MyAgent node
        """
        print(
            f"🤖 Processing Agent: {here.name} at ({here.latitude}, {here.longitude})"
        )

        # Update agent activity
        here.last_active = datetime.now()
        await here.save()

        # Find or create actions collection for this agent
        actions_nodes = await here.nodes(node=["Actions"])

        if not actions_nodes:
            print(f"⚡ Creating Actions collection for {here.name}")
            actions = await Actions.create(name=f"{here.name}_Actions")
            await here.connect(actions)
            await self.visit([actions])
        else:
            print(f"✅ Found {len(actions_nodes)} Actions collections")
            await self.visit(actions_nodes)

    @on_visit(Actions)
    async def visit_actions(self, here: Actions):
        """Process actions collection and find individual actions.

        Args:
            here: The visited Actions node
        """
        print(f"⚡ Processing Actions collection: {here.name}")

        # RECOMMENDED: Use MongoDB-style queries with multiple node types
        action_nodes = await Action.find(
            {
                "$and": [
                    {"context.enabled": True},
                    {
                        "$or": [
                            {"name": "FirstAction"},
                            {"name": "SecondAction"},
                            {"name": "ThirdAction"},
                        ]
                    },
                ]
            }
        )

        if not action_nodes:
            print("⚡ Creating action nodes")
            # Create different action types
            actions_to_create = [
                (FirstAction, "ProcessData", "Processes incoming data streams"),
                (SecondAction, "ValidateResults", "Validates processing results"),
                (ThirdAction, "SendNotifications", "Sends completion notifications"),
            ]

            created_actions = []
            for action_class, action_name, description in actions_to_create:
                action = await action_class.create(
                    name=action_name, description=description, enabled=True
                )
                await here.connect(action)
                created_actions.append(action)

            action_nodes = created_actions

        # Update collection statistics
        here.total_actions = len(action_nodes)
        here.enabled_actions = len([a for a in action_nodes if a.enabled])
        await here.save()

        # Apply max_actions limit
        limited_actions = action_nodes[: self.max_actions]
        print(f"✅ Processing {len(limited_actions)} of {len(action_nodes)} actions")

        await self.visit(limited_actions)

    @on_visit(Action)
    async def visit_action(self, here: Action):
        """Process base action nodes.

        Args:
            here: The visited Action node
        """
        print(f"⚡ Processing Action: {here.name} (type: {here.action_type})")

        # Update execution statistics
        here.execution_count += 1
        here.last_executed = datetime.now()
        await here.save()

        # Report action execution
        await self.report(
            {
                "action_executed": {
                    "name": here.name,
                    "type": here.action_type,
                    "execution_count": here.execution_count,
                    "priority": getattr(here, "priority", 0),
                }
            }
        )

    @on_visit(FirstAction)
    async def visit_first_action(self, here: FirstAction):
        """Process first action type with specific logic.

        Args:
            here: The visited FirstAction node
        """
        print(f"🥇 Executing FirstAction: {here.name} (Priority: {here.priority})")
        # Simulate specific processing for first action type
        await asyncio.sleep(0.01)

    @on_visit(SecondAction)
    async def visit_second_action(self, here: SecondAction):
        """Process second action type with specific logic.

        Args:
            here: The visited SecondAction node
        """
        print(f"🥈 Executing SecondAction: {here.name} (Priority: {here.priority})")
        # Simulate specific processing for second action type
        await asyncio.sleep(0.01)

    @on_visit(ThirdAction)
    async def visit_third_action(self, here: ThirdAction):
        """Process third action type with specific logic.

        Args:
            here: The visited ThirdAction node
        """
        print(f"🥉 Executing ThirdAction: {here.name} (Priority: {here.priority})")
        # Simulate specific processing for third action type
        await asyncio.sleep(0.01)

    @on_exit
    async def finalize_interaction(self):
        """Complete the interaction and provide summary.

        Called when walker completes traversal.
        """
        report = await self.get_report()
        executed_count = len(
            [r for r in report if isinstance(r, dict) and "action_executed" in r]
        )
        print(f"\n✅ Agent interaction completed!")
        print(f"📊 Summary: Executed {executed_count} actions")

        await self.report(
            {
                "interaction_summary": {
                    "status": "completed",
                    "message": f"Successfully processed agent hierarchy with {executed_count} actions",
                    "timestamp": datetime.now().isoformat(),
                }
            }
        )


# ============== UTILITY ENDPOINTS ==============


@endpoint("/api/agents/stats", methods=["GET"])
async def get_agent_statistics() -> Dict[str, Any]:
    """Get comprehensive statistics about the agent system.

    Returns:
        Dictionary containing agent system statistics
    """
    try:
        # RECOMMENDED: Use entity-centric count operations
        total_apps = len(await App.find({"context.status": "active"}))
        total_agents = len(await MyAgent.find({}))
        active_agents = len(await MyAgent.find({"context.status": "active"}))
        published_agents = len(await MyAgent.find({"context.published": True}))
        total_actions = len(await Action.find({}))
        enabled_actions = len(await Action.find({"context.enabled": True}))

        # Get action type breakdown
        first_actions = len(await FirstAction.find({}))
        second_actions = len(await SecondAction.find({}))
        third_actions = len(await ThirdAction.find({}))

        return {
            "system_stats": {
                "active_apps": total_apps,
                "total_agents": total_agents,
                "active_agents": active_agents,
                "published_agents": published_agents,
                "total_actions": total_actions,
                "enabled_actions": enabled_actions,
            },
            "action_breakdown": {
                "first_actions": first_actions,
                "second_actions": second_actions,
                "third_actions": third_actions,
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "error": f"Failed to get statistics: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


@endpoint("/api/agents/search", methods=["POST"])
async def search_agents(search_criteria: Dict[str, Any]) -> Dict[str, Any]:
    """Search agents using MongoDB-style queries.

    Args:
        search_criteria: Dictionary containing search parameters

    Returns:
        Dictionary containing search results
    """
    try:
        # Extract search parameters
        location_filter = search_criteria.get("location")
        status_filter = search_criteria.get("status", "active")
        published_only = search_criteria.get("published_only", True)
        capabilities_filter = search_criteria.get("capabilities", [])

        # Build MongoDB-style query
        query = {}

        if status_filter:
            query["context.status"] = status_filter

        if published_only:
            query["context.published"] = True

        if capabilities_filter:
            # RECOMMENDED: Use MongoDB array operators
            query["context.capabilities"] = {"$in": capabilities_filter}

        if location_filter:
            lat_range = location_filter.get("latitude_range")
            lng_range = location_filter.get("longitude_range")

            if lat_range:
                query["context.latitude"] = {
                    "$gte": lat_range.get("min", -90),
                    "$lte": lat_range.get("max", 90),
                }
            if lng_range:
                query["context.longitude"] = {
                    "$gte": lng_range.get("min", -180),
                    "$lte": lng_range.get("max", 180),
                }

        # RECOMMENDED: Execute query using entity-centric method
        matching_agents = await MyAgent.find(query)

        return {
            "search_criteria": search_criteria,
            "query_used": query,
            "results": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "status": agent.status,
                    "location": {
                        "latitude": agent.latitude,
                        "longitude": agent.longitude,
                    },
                    "capabilities": agent.capabilities,
                    "last_active": (
                        agent.last_active.isoformat() if agent.last_active else None
                    ),
                }
                for agent in matching_agents
            ],
            "total_results": len(matching_agents),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "error": f"Search failed: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


# ============== DEMONSTRATION FUNCTIONS ==============


async def create_sample_agent_hierarchy():
    """Create sample agent hierarchy using entity-centric CRUD operations."""
    print("\n🏗️ Creating sample agent hierarchy using entity-centric methods")

    try:
        # RECOMMENDED: Use entity-centric create operations
        root = await Root.get()

        # Create app
        app = await App.create(
            name="SampleAgentSystem", version="1.0.0", status="active"
        )
        await root.connect(app)
        print(f"✅ Created App: {app.name}")

        # Create agents collection
        agents_collection = await Agents.create(name="ProductionAgents")
        await app.connect(agents_collection)
        print(f"✅ Created Agents collection: {agents_collection.name}")

        # Create sample agents with different locations and capabilities
        # Reduced sample data size to minimize processing time
        agent_configs = [
            {
                "name": "DataProcessor",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "capabilities": ["data_processing"],
            },
            {
                "name": "APIGateway",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "capabilities": ["api_management"],
            },
        ]

        for config in agent_configs:
            agent = await MyAgent.create(**config)
            await agents_collection.connect(agent)

            # Create actions for each agent
            actions_collection = await Actions.create(name=f"{config['name']}_Actions")
            await agent.connect(actions_collection)

            # Reduced action set to minimize processing time
            action_configs = [
                (FirstAction, f"{config['name']}_Process", "Primary processing action"),
                (SecondAction, f"{config['name']}_Validate", "Validation action"),
            ]

            for action_class, action_name, description in action_configs:
                action = await action_class.create(
                    name=action_name, description=description
                )
                await actions_collection.connect(action)

            print(f"✅ Created agent: {config['name']} with 3 actions")

        print(f"🎉 Sample hierarchy created with {len(agent_configs)} agents")
        return app

    except Exception as e:
        print(f"❌ Error creating sample hierarchy: {e}")
        return None


async def demonstrate_entity_queries():
    """Demonstrate MongoDB-style queries using entity-centric methods."""
    print("\n🔍 Demonstrating entity-centric queries with MongoDB-style syntax")

    try:
        # RECOMMENDED: Complex queries using MongoDB operators

        # Find active, published agents
        active_agents = await MyAgent.find(
            {"$and": [{"context.status": "active"}, {"context.published": True}]}
        )
        print(f"✅ Found {len(active_agents)} active, published agents")

        # Find agents with specific capabilities
        processing_agents = await MyAgent.find(
            {"context.capabilities": {"$in": ["data_processing", "analytics"]}}
        )
        print(f"✅ Found {len(processing_agents)} agents with processing capabilities")

        # Find agents in specific geographic regions (West Coast)
        west_coast_agents = await MyAgent.find(
            {
                "$and": [
                    {"context.latitude": {"$gte": 32.0, "$lte": 42.0}},
                    {"context.longitude": {"$gte": -125.0, "$lte": -117.0}},
                ]
            }
        )
        print(f"✅ Found {len(west_coast_agents)} agents on the West Coast")

        # Find recently active agents
        recent_threshold = datetime.now()
        recently_active = await MyAgent.find({"context.last_active": {"$exists": True}})
        print(f"✅ Found {len(recently_active)} agents with activity records")

        # Count different action types
        action_counts = {}
        for action_class in [FirstAction, SecondAction, ThirdAction]:
            count = len(await action_class.find({"context.enabled": True}))
            action_counts[action_class.__name__] = count

        print("✅ Action type counts:", action_counts)

    except Exception as e:
        print(f"❌ Error in query demonstration: {e}")


async def main():
    """Main demonstration function."""
    print("🚀 Agent Graph Example - Entity-Centric CRUD with jvspatial")
    print("Demonstrates proper jvspatial conventions and patterns")

    # Create sample data
    await create_sample_agent_hierarchy()

    # Demonstrate query patterns
    await demonstrate_entity_queries()

    # Run the interaction walker
    print("\n🚶 Running InteractWalker to traverse agent hierarchy")
    root = await Root.get()
    walker = InteractWalker(
        target_agent_name="DataProcessor",
        include_inactive=False,
        max_actions=2,
        timeout_seconds=30,
    )

    await walker.spawn(root)
    report = await walker.get_report()
    print(f"Walker report items: {len(report)}")

    # Display summary from report
    for item in report:
        if isinstance(item, dict) and "interaction_summary" in item:
            print(f"Interaction summary: {item['interaction_summary']}")

    print("\n✅ Example completed successfully!")
    print("Key takeaways:")
    print("  - Used entity-centric CRUD (Agent.create(), Agent.find(), etc.)")
    print("  - Applied MongoDB-style queries with operators ($and, $or, $in, etc.)")
    print("  - Followed proper @on_visit naming convention ('here' parameter)")
    print("  - Implemented type annotations and error handling")
    print("  - Created API endpoints with EndpointField configuration")


if __name__ == "__main__":
    asyncio.run(main())
