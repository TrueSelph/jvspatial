"""Agent Graph Example

Demonstrates building a hierarchical graph structure with agents and actions.
Shows both the original API and new GraphContext patterns for database management.

This example builds a graph: Root -> App -> Agents -> MyAgent -> Actions -> Action types
"""

import asyncio
import tempfile

from jvspatial.api.endpoint_router import EndpointRouter
from jvspatial.core.context import GraphContext, get_default_context
from jvspatial.core.entities import Edge, Node, Root, Walker, on_exit, on_visit
from jvspatial.db.factory import get_database


class App(Node):
    """Application node representing the main app"""


class CustomEdge(Edge):
    """Custom edge type for connecting nodes"""

    pass


class Agents(Node):
    """Agents node representing a collection of agents"""


class MyAgent(Node):
    """Individual agent node with spatial properties"""

    published: bool = True
    latitude: float = 0.0
    longitude: float = 0.0


class Actions(Node):
    """Actions node representing a collection of actions"""


class Action(Node):
    """Base action node"""

    enabled: bool = True


class FirstAction(Action):
    pass


class SecondAction(Action):
    pass


class ThirdAction(Action):
    pass


# API Endpoint example
api = EndpointRouter()


@api.endpoint("/interact", methods=["POST"])
class Interact(Walker):
    @on_visit(Root)
    async def on_root(self, here):
        print("on_root called")
        app_nodes = await (await here.nodes()).filter(node="App")
        if not app_nodes:
            print("No App nodes found, creating new App node")
            app_node = App()
            await here.connect(app_node)
            await self.visit(app_node)
        else:
            print(f"Found App nodes: {app_nodes}")
            await self.visit(app_nodes[0])

    @on_visit(App)
    async def on_app(self, here):
        print(f"On app node: {here.id}")
        print("Looking for Agents nodes...")
        agents_nodes = await (await here.nodes()).filter(node="Agents")
        if not agents_nodes:
            print("No Agents nodes found, creating new Agents node")
            agents_node = Agents()
            await here.connect(agents_node)
            await self.visit(agents_node)
        else:
            print(f"Found Agents nodes: {agents_nodes}")
            await self.visit(agents_nodes[0])

    @on_visit(Agents)
    async def on_agents(self, here):
        print(f"On agents node: {here.id}")
        print("Looking for MyAgent nodes...")
        my_agents = await (await here.nodes()).filter(node="MyAgent", published=True)
        if not my_agents:
            print("No MyAgent nodes found, creating new MyAgent node")
            my_agent = MyAgent(latitude=0.0, longitude=0.0)
            await here.connect(my_agent)
            print(f"Created new MyAgent: {my_agent.id}")
            await self.visit(my_agent)
        else:
            print(f"Found MyAgent nodes: {my_agents}")
            await self.visit(my_agents[0])

    @on_visit(MyAgent)
    async def on_agent(self, here):
        print(f"On MyAgent node: {here.id}")
        print("Looking for Actions nodes...")
        actions_nodes = await (await here.nodes()).filter(node="Actions")
        if not actions_nodes:
            print("No Actions nodes found, creating new Actions node")
            actions_node = Actions()
            await here.connect(actions_node)
            print(f"Created new Actions node: {actions_node.id}")
            await self.visit(actions_node)
        else:
            print(f"Found Actions nodes: {actions_nodes}")
            await self.visit(actions_nodes[0])

    @on_visit(Actions)
    async def on_actions(self, here):
        print(f"On Actions node: {here.id}")
        print("Looking for Action nodes...")
        action_nodes = await (await here.nodes()).filter(
            node=["FirstAction", "SecondAction", "ThirdAction"]
        )
        if not action_nodes:
            print("No Action nodes found, creating new Action nodes")
            first_action = FirstAction()
            second_action = SecondAction()
            third_action = ThirdAction()
            await here.connect(first_action)
            await here.connect(second_action)
            await here.connect(third_action)
            action_nodes = [first_action, second_action, third_action]
            print(f"Created new Action nodes: {[node.id for node in action_nodes]}")
        # Visit all action nodes
        print(f"Visiting Action nodes: {[node.id for node in action_nodes if node]}")
        for action_node in action_nodes:
            if action_node:
                await self.visit(action_node)

    @on_visit(Action)
    async def on_action(self, here):
        print(f"On action node: {here.id} (type: {here.__class__.__name__})")

    @on_visit(FirstAction)
    async def on_first_action(self, here):
        print(f"On FirstAction node: {here.id}")

    @on_visit(SecondAction)
    async def on_second_action(self, here):
        print(f"On SecondAction node: {here.id}")

    @on_visit(ThirdAction)
    async def on_third_action(self, here):
        print(f"On ThirdAction node: {here.id}")

    @on_exit
    async def respond(self):
        print("Traversal completed")


async def demonstrate_graphcontext_with_agents():
    """Show how GraphContext works with complex hierarchical structures."""
    print("\n=== GRAPHCONTEXT WITH AGENT HIERARCHIES ===")

    # Create isolated context for agent management
    agent_db = get_database(db_type="json", base_path=tempfile.mkdtemp())
    agent_ctx = GraphContext(database=agent_db)

    print("📊 Created isolated context for agent management")

    # Build agent hierarchy using GraphContext
    app = await agent_ctx.create_node(App)
    agents_collection = await agent_ctx.create_node(Agents)

    # Connect app to agents
    await agent_ctx.create_edge(Edge, left=app, right=agents_collection)

    # Create multiple agents with different properties
    agent1 = await agent_ctx.create_node(
        MyAgent, published=True, latitude=40.7128, longitude=-74.0060
    )  # NYC
    agent2 = await agent_ctx.create_node(
        MyAgent, published=True, latitude=34.0522, longitude=-118.2437
    )  # LA
    agent3 = await agent_ctx.create_node(
        MyAgent, published=False, latitude=41.8781, longitude=-87.6298
    )  # Chicago

    # Connect agents to collection
    for agent in [agent1, agent2, agent3]:
        await agent_ctx.create_edge(Edge, left=agents_collection, right=agent)

    print(f"✅ Created app hierarchy with {len([agent1, agent2, agent3])} agents")
    print(f"✅ Agents in NYC, LA, and Chicago")

    # Show that we can still use original API with these entities
    agent1.latitude = 40.7589  # Move to Times Square
    await agent1.save()  # Original API works!

    print("✅ Updated agent location using original API (agent.save())")

    # Query agents using GraphContext
    all_nodes = await agent_ctx.database.find("node", {})
    agent_nodes = [n for n in all_nodes if n.get("name") == "MyAgent"]

    print(f"📍 Found {len(agent_nodes)} agents in isolated database")

    return agent_ctx


async def main():
    print("🚀 Agent Graph Example")
    print("Shows hierarchical graph building with original API + GraphContext")

    print("\n=== ORIGINAL API APPROACH ===")
    # Get root node - original approach
    root = await Root.get()
    print(f"Root node retrieved: {root.id}")

    # Run the Interact walker - original approach
    print("\n=== RUNNING INTERACT WALKER (Original API) ===")
    walker = Interact()
    await walker.spawn(root)

    # Show advanced GraphContext patterns
    agent_ctx = await demonstrate_graphcontext_with_agents()

    print("\n=== COMPARISON ===")
    print("✅ Original API: Simple, works exactly as before")
    print("✅ GraphContext: Advanced control, isolation, testing")
    print("✅ Both approaches work together seamlessly")


if __name__ == "__main__":
    asyncio.run(main())
