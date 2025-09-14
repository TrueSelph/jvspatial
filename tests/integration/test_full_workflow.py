"""
Integration tests for complete jvspatial workflows.
Tests end-to-end functionality including persistence, traversal, and API integration.
"""

import asyncio
import os
import shutil
import tempfile
from typing import List

import pytest

# Import spatial utilities to enable find_nearby and find_in_bounds methods
import jvspatial.spatial.utils
from jvspatial.api.api import GraphAPI
from jvspatial.core.entities import Edge, Node, RootNode, Walker, on_exit, on_visit
from jvspatial.db.factory import get_database
from jvspatial.db.jsondb import JsonDB


# Test Node Types
class City(Node):
    """City node with spatial properties"""

    name: str
    population: int = 0
    latitude: float = 0.0
    longitude: float = 0.0

    def __init__(self, **kwargs):
        if kwargs.get("name", "").strip() == "":
            raise ValueError("City name cannot be empty")
        super().__init__(**kwargs)


class Agent(Node):
    """Agent node with status and location"""

    name: str
    status: str = "active"
    latitude: float = 0.0
    longitude: float = 0.0
    skills: List[str] = []


class Mission(Node):
    """Mission node"""

    title: str
    description: str = ""
    priority: str = "medium"
    status: str = "planned"


# Test Edge Types
class Highway(Edge):
    """Highway connection between cities"""

    lanes: int = 4
    speed_limit: int = 65
    distance_km: float = 0.0


class Assignment(Edge):
    """Assignment edge between agent and mission"""

    assigned_at: str = ""
    role: str = "operator"


class TestFullWorkflowScenarios:
    """Test complete end-to-end scenarios"""

    def setup_method(self):
        """Set up isolated test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_env = os.environ.get("JVSPATIAL_JSONDB_PATH")

        # Configure test database
        os.environ["JVSPATIAL_DB_TYPE"] = "json"
        os.environ["JVSPATIAL_JSONDB_PATH"] = self.temp_dir

        # Reset database instances
        from jvspatial.core.entities import Object

        Object.set_db(None)

        # Clear any existing database instance
        try:
            import shutil

            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            os.makedirs(self.temp_dir, exist_ok=True)
        except Exception:
            pass

    def teardown_method(self):
        """Clean up test environment"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        # Restore original environment
        if self.original_env:
            os.environ["JVSPATIAL_JSONDB_PATH"] = self.original_env
        elif "JVSPATIAL_JSONDB_PATH" in os.environ:
            del os.environ["JVSPATIAL_JSONDB_PATH"]

    @pytest.mark.asyncio
    async def test_city_network_creation_and_traversal(self):
        """Test creating a network of cities and traversing them"""

        # Create cities with real coordinates
        chicago = await City.create(
            name="Chicago", population=2697000, latitude=41.8781, longitude=-87.6298
        )

        milwaukee = await City.create(
            name="Milwaukee", population=594833, latitude=43.0389, longitude=-87.9065
        )

        detroit = await City.create(
            name="Detroit", population=670031, latitude=42.3314, longitude=-83.0458
        )

        # Connect cities with highways
        highway1 = await chicago.connect(
            milwaukee, Highway, lanes=6, speed_limit=70, distance_km=118.0
        )

        highway2 = await chicago.connect(
            detroit, Highway, lanes=4, speed_limit=65, distance_km=382.0
        )

        # Verify persistence
        root = await RootNode.get()
        await root.connect(chicago)
        await root.connect(milwaukee)
        await root.connect(detroit)

        # Test spatial queries
        nearby_cities = await City.find_nearby(41.8781, -87.6298, 200.0)
        nearby_names = [city.name for city in nearby_cities]

        assert "Chicago" in nearby_names
        assert "Milwaukee" in nearby_names
        assert "Detroit" not in nearby_names  # Too far

        # Create a tourist walker to traverse the network
        class Tourist(Walker):
            visited_cities: List[str] = []
            total_distance: float = 0.0

            @on_visit(City)
            async def visit_city(self, here):
                self.visited_cities.append(here.name)
                print(f"Tourist visiting {here.name} (pop: {here.population})")

                # Travel via highways to connected cities
                all_edges = await here.edges()
                highways = [e for e in all_edges if isinstance(e, Highway)]
                for highway in highways:
                    if highway.source == here.id:
                        target_city = await City.get(highway.target)
                    else:
                        target_city = await City.get(highway.source)

                    if target_city and target_city.name not in self.visited_cities:
                        self.total_distance += highway.distance_km
                        await self.visit(target_city)

            @on_exit
            async def trip_summary(self):
                self.response["cities_visited"] = self.visited_cities
                self.response["total_distance"] = self.total_distance
                self.response["trip_completed"] = True

        # Run the tourist walker
        tourist = Tourist()
        result = await tourist.spawn(start=chicago)

        assert "Chicago" in tourist.visited_cities
        assert "Milwaukee" in tourist.visited_cities
        assert len(tourist.visited_cities) >= 2
        assert tourist.total_distance > 0
        assert result.response["trip_completed"] == True

    @pytest.mark.asyncio
    async def test_agent_mission_assignment_workflow(self):
        """Test agent and mission management workflow"""

        # Create agents with different skills
        field_agent = await Agent.create(
            name="Agent Smith",
            status="active",
            latitude=40.7128,
            longitude=-74.0060,
            skills=["surveillance", "combat"],
        )

        tech_agent = await Agent.create(
            name="Agent Jones",
            status="active",
            latitude=40.7580,
            longitude=-73.9855,
            skills=["hacking", "electronics"],
        )

        analyst = await Agent.create(
            name="Agent Brown",
            status="active",
            latitude=40.6892,
            longitude=-74.0445,
            skills=["analysis", "linguistics"],
        )

        # Create missions
        surveillance_mission = await Mission.create(
            title="Urban Surveillance",
            description="Monitor target location",
            priority="high",
            status="planned",
        )

        cyber_mission = await Mission.create(
            title="Network Infiltration",
            description="Gain access to secure network",
            priority="critical",
            status="planned",
        )

        # Create assignment workflow walker
        class MissionAssignment(Walker):
            assignments_made: int = 0

            @on_visit(RootNode)
            async def start_assignment(self, here):
                # Find all missions and agents
                missions = await Mission.all()
                agents = await Agent.all()

                self.response["total_missions"] = len(missions)
                self.response["total_agents"] = len(agents)

                # Visit each mission for assignment
                await self.visit(missions)

            @on_visit(Mission)
            async def assign_mission(self, here):
                # Find suitable agents based on mission requirements
                all_agents = await Agent.all()
                suitable_agents = []

                if "surveillance" in here.title.lower():
                    suitable_agents = [
                        a for a in all_agents if "surveillance" in a.skills
                    ]
                elif "network" in here.title.lower():
                    suitable_agents = [a for a in all_agents if "hacking" in a.skills]

                # Assign best agent
                if suitable_agents:
                    agent = suitable_agents[0]
                    assignment = await here.connect(
                        agent,
                        Assignment,
                        assigned_at="2024-01-01T00:00:00Z",
                        role="primary",
                    )

                    # Update mission and agent status
                    here.status = "assigned"
                    await here.save()

                    agent.status = "mission"
                    await agent.save()

                    self.assignments_made += 1

            @on_exit
            async def assignment_summary(self):
                self.response["assignments_made"] = self.assignments_made
                self.response["status"] = "completed"

        # Run assignment workflow
        assignment_walker = MissionAssignment()
        result = await assignment_walker.spawn()

        assert result.response["assignments_made"] >= 2
        assert result.response["total_missions"] >= 2
        assert result.response["total_agents"] >= 3

        # Verify assignments were persisted
        updated_surveillance = await Mission.get(surveillance_mission.id)
        updated_cyber = await Mission.get(cyber_mission.id)

        assert updated_surveillance.status == "assigned"
        assert updated_cyber.status == "assigned"

    @pytest.mark.asyncio
    async def test_concurrent_walker_execution(self):
        """Test multiple walkers running concurrently"""

        # Create test data
        cities = []
        for i in range(5):
            city = await City.create(
                name=f"City_{i}",
                population=100000 + (i * 50000),
                latitude=40.0 + (i * 0.5),
                longitude=-74.0 + (i * 0.5),
            )
            cities.append(city)

        # Connect cities in a chain
        for i in range(len(cities) - 1):
            await cities[i].connect(cities[i + 1], Highway, distance_km=100.0)

        # Define different walker types
        class PopulationCounter(Walker):
            @on_visit(City)
            async def count_population(self, here):
                if "total_population" not in self.response:
                    self.response["total_population"] = 0
                self.response["total_population"] += here.population

            @on_exit
            async def finalize_count(self):
                self.response["walker_type"] = "population_counter"

        class CityLister(Walker):
            @on_visit(City)
            async def list_city(self, here):
                if "cities" not in self.response:
                    self.response["cities"] = []
                self.response["cities"].append(here.name)

            @on_exit
            async def finalize_list(self):
                self.response["walker_type"] = "city_lister"

        class DistanceCalculator(Walker):
            last_city: City = None

            @on_visit(City)
            async def calculate_distance(self, here):
                if "total_distance" not in self.response:
                    self.response["total_distance"] = 0.0
                    self.response["visited_cities"] = []

                # Prevent infinite loops
                if here.name in self.response["visited_cities"]:
                    return

                self.response["visited_cities"].append(here.name)

                if self.last_city:
                    # Find highway between cities
                    edges = await here.edges()
                    for edge in edges:
                        if isinstance(edge, Highway):
                            if (
                                edge.source == self.last_city.id
                                and edge.target == here.id
                            ) or (
                                edge.target == self.last_city.id
                                and edge.source == here.id
                            ):
                                self.response["total_distance"] += edge.distance_km
                                break

                self.last_city = here

                # Visit connected cities (limit to prevent infinite loops)
                if len(self.response["visited_cities"]) < 5:  # Max 5 cities
                    connected = await (await here.nodes()).filter(node="City")
                    unvisited = [
                        c
                        for c in connected
                        if c.name not in self.response["visited_cities"]
                    ]
                    if unvisited:
                        await self.visit(
                            [unvisited[0]]
                        )  # Visit only one to prevent explosion

            @on_exit
            async def finalize_distance(self):
                self.response["walker_type"] = "distance_calculator"

        # Run walkers concurrently
        async def run_walker(walker_class, start_city):
            walker = walker_class()
            return await walker.spawn(start=start_city)

        # Execute multiple walkers concurrently
        tasks = [
            run_walker(PopulationCounter, cities[0]),
            run_walker(CityLister, cities[0]),
            run_walker(DistanceCalculator, cities[0]),
        ]

        results = await asyncio.gather(*tasks)

        # Verify all walkers completed successfully
        assert len(results) == 3

        # Check population counter
        pop_result = next(
            r for r in results if r.response.get("walker_type") == "population_counter"
        )
        assert pop_result.response["total_population"] > 0

        # Check city lister
        list_result = next(
            r for r in results if r.response.get("walker_type") == "city_lister"
        )
        assert len(list_result.response["cities"]) >= 1

        # Check distance calculator
        dist_result = next(
            r for r in results if r.response.get("walker_type") == "distance_calculator"
        )
        assert "total_distance" in dist_result.response

    @pytest.mark.asyncio
    async def test_persistence_across_sessions(self):
        """Test that data persists across different sessions"""

        # Session 1: Create initial data
        session1_city = await City.create(
            name="Persistent City", population=500000, latitude=45.0, longitude=-75.0
        )

        session1_agent = await Agent.create(
            name="Persistent Agent", status="active", skills=["persistence", "testing"]
        )

        # Connect them
        await session1_city.connect(session1_agent)

        # Store IDs for later retrieval
        city_id = session1_city.id
        agent_id = session1_agent.id

        # Simulate session end by clearing database connection
        from jvspatial.core.entities import Object

        Object.set_db(None)

        # Session 2: Retrieve and verify data
        retrieved_city = await City.get(city_id)
        retrieved_agent = await Agent.get(agent_id)

        assert retrieved_city is not None
        assert retrieved_city.name == "Persistent City"
        assert retrieved_city.population == 500000

        assert retrieved_agent is not None
        assert retrieved_agent.name == "Persistent Agent"
        assert "persistence" in retrieved_agent.skills

        # Test connection persistence
        connected_agents = await (await retrieved_city.nodes()).filter(node="Agent")
        assert len(connected_agents) == 1
        assert connected_agents[0].name == "Persistent Agent"

        # Session 3: Modify data and verify changes persist
        retrieved_city.population = 600000
        await retrieved_city.save()

        retrieved_agent.status = "modified"
        await retrieved_agent.save()

        # Clear and retrieve again
        Object.set_db(None)

        final_city = await City.get(city_id)
        final_agent = await Agent.get(agent_id)

        assert final_city.population == 600000
        assert final_agent.status == "modified"


class TestAPIIntegrationWorkflows:
    """Test API integration with full workflows"""

    def setup_method(self):
        """Set up API test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_env = os.environ.get("JVSPATIAL_JSONDB_PATH")

        os.environ["JVSPATIAL_DB_TYPE"] = "json"
        os.environ["JVSPATIAL_JSONDB_PATH"] = self.temp_dir

        from jvspatial.core.entities import Object

        Object.set_db(None)

        # Clear any existing database instance
        try:
            import shutil

            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            os.makedirs(self.temp_dir, exist_ok=True)
        except Exception:
            pass

    def teardown_method(self):
        """Clean up API test environment"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        if self.original_env:
            os.environ["JVSPATIAL_JSONDB_PATH"] = self.original_env
        elif "JVSPATIAL_JSONDB_PATH" in os.environ:
            del os.environ["JVSPATIAL_JSONDB_PATH"]

    @pytest.mark.asyncio
    async def test_api_endpoint_workflow(self):
        """Test complete API endpoint workflow"""

        # Create API with endpoints
        api = GraphAPI()

        @api.endpoint("/create-city", methods=["POST"])
        class CreateCity(Walker):
            name: str
            population: int = 0
            latitude: float = 0.0
            longitude: float = 0.0

            @on_visit(RootNode)
            async def create_city(self, here):
                city = await City.create(
                    name=self.name,
                    population=self.population,
                    latitude=self.latitude,
                    longitude=self.longitude,
                )

                await here.connect(city)

                self.response["city_id"] = city.id
                self.response["city_name"] = city.name
                self.response["status"] = "created"

        @api.endpoint("/find-nearby-cities", methods=["POST"])
        class FindNearbyCities(Walker):
            latitude: float
            longitude: float
            radius_km: float = 10.0

            @on_visit(RootNode)
            async def find_cities(self, here):
                nearby = await City.find_nearby(
                    self.latitude, self.longitude, self.radius_km
                )

                self.response["cities"] = [
                    {"name": city.name, "population": city.population}
                    for city in nearby
                ]
                self.response["count"] = len(nearby)
                self.response["search_center"] = [self.latitude, self.longitude]

        # Test city creation endpoint
        create_handler = None
        find_handler = None

        for route in api.router.routes:
            if hasattr(route, "path"):
                if route.path == "/create-city":
                    create_handler = route.endpoint
                elif route.path == "/find-nearby-cities":
                    find_handler = route.endpoint

        assert create_handler is not None
        assert find_handler is not None

        # Create multiple cities via API
        city_data = [
            {
                "name": "API City 1",
                "population": 100000,
                "latitude": 40.0,
                "longitude": -74.0,
            },
            {
                "name": "API City 2",
                "population": 200000,
                "latitude": 40.1,
                "longitude": -74.1,
            },
            {
                "name": "API City 3",
                "population": 300000,
                "latitude": 45.0,
                "longitude": -75.0,
            },  # Far away
        ]

        created_cities = []
        for data in city_data:
            result = await create_handler(data)
            assert result["status"] == "created"
            assert result["city_name"] == data["name"]
            created_cities.append(result)

        # Test nearby search via API
        search_result = await find_handler(
            {"latitude": 40.05, "longitude": -74.05, "radius_km": 20.0}
        )

        assert search_result["count"] >= 2  # Should find at least 2 nearby cities
        assert search_result["search_center"] == [40.05, -74.05]

        # Verify the correct cities were found
        found_names = [city["name"] for city in search_result["cities"]]
        assert "API City 1" in found_names
        assert "API City 2" in found_names
        assert "API City 3" not in found_names  # Too far away

    @pytest.mark.asyncio
    async def test_complex_api_workflow_with_traversal(self):
        """Test complex API workflow with graph traversal"""

        api = GraphAPI()

        @api.endpoint("/deploy-agents", methods=["POST"])
        class DeployAgents(Walker):
            mission_area_lat: float
            mission_area_lon: float
            mission_radius: float = 5.0
            agent_count: int = 3

            @on_visit(RootNode)
            async def deploy_mission(self, here):
                # Create mission area
                mission = await Mission.create(
                    title="Area Deployment",
                    description=f"Deploy {self.agent_count} agents",
                    priority="high",
                )

                # Create and position agents around mission area
                deployed_agents = []
                for i in range(self.agent_count):
                    # Position agents in circle around mission area
                    import math

                    angle = (2 * math.pi * i) / self.agent_count
                    agent_lat = self.mission_area_lat + (0.01 * math.cos(angle))
                    agent_lon = self.mission_area_lon + (0.01 * math.sin(angle))

                    agent = await Agent.create(
                        name=f"Deployed Agent {i+1}",
                        latitude=agent_lat,
                        longitude=agent_lon,
                        status="deployed",
                    )

                    # Assign agent to mission
                    await mission.connect(agent, Assignment, role="field_operative")
                    deployed_agents.append(agent)

                # Connect mission to root for discoverability
                await here.connect(mission)

                self.response["mission_id"] = mission.id
                self.response["deployed_agents"] = [
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "position": [agent.latitude, agent.longitude],
                    }
                    for agent in deployed_agents
                ]
                self.response["deployment_status"] = "completed"

        # Get handler and execute deployment
        deploy_handler = None
        for route in api.router.routes:
            if hasattr(route, "path") and route.path == "/deploy-agents":
                deploy_handler = route.endpoint
                break

        assert deploy_handler is not None

        # Execute deployment
        deployment_result = await deploy_handler(
            {
                "mission_area_lat": 40.7128,
                "mission_area_lon": -74.0060,
                "mission_radius": 2.0,
                "agent_count": 4,
            }
        )

        assert deployment_result["deployment_status"] == "completed"
        assert len(deployment_result["deployed_agents"]) == 4
        assert "mission_id" in deployment_result

        # Verify deployment was persisted
        mission_id = deployment_result["mission_id"]
        retrieved_mission = await Mission.get(mission_id)

        assert retrieved_mission is not None
        assert retrieved_mission.title == "Area Deployment"

        # Verify agents were assigned
        assigned_agents = await (await retrieved_mission.nodes()).filter(node="Agent")
        assert len(assigned_agents) == 4

        for agent in assigned_agents:
            assert agent.status == "deployed"
            assert "Deployed Agent" in agent.name


class TestErrorRecoveryWorkflows:
    """Test error recovery and resilience in workflows"""

    def setup_method(self):
        """Set up error recovery test environment"""
        self.temp_dir = tempfile.mkdtemp()
        os.environ["JVSPATIAL_DB_TYPE"] = "json"
        os.environ["JVSPATIAL_JSONDB_PATH"] = self.temp_dir

        from jvspatial.core.entities import Object

        Object.set_db(None)

        # Clear any existing database instance
        try:
            import shutil

            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            os.makedirs(self.temp_dir, exist_ok=True)
        except Exception:
            pass

    def teardown_method(self):
        """Clean up error recovery test environment"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_walker_error_recovery(self):
        """Test walker continues after errors in individual hooks"""

        class FaultyWalker(Walker):
            processed_count: int = 0
            error_count: int = 0

            @on_visit(RootNode)
            async def start_processing(self, here):
                # Create test cities
                cities = []
                for i in range(5):
                    city = await City.create(name=f"City_{i}")
                    await here.connect(city)
                    cities.append(city)

                await self.visit(cities)

            @on_visit(City)
            async def process_city(self, here):
                self.processed_count += 1

                # Simulate error in every other city
                if "2" in here.name or "4" in here.name:
                    self.error_count += 1
                    raise ValueError(f"Simulated error processing {here.name}")

                # Normal processing
                self.response[f"processed_{here.name}"] = True

            @on_exit
            async def summarize_processing(self):
                self.response["total_processed"] = self.processed_count
                self.response["total_errors"] = self.error_count
                self.response["recovery_successful"] = True

        # Run faulty walker
        walker = FaultyWalker()
        result = await walker.spawn()

        # Walker should complete despite errors
        assert result.response["recovery_successful"] == True
        assert result.response["total_processed"] == 5
        assert result.response["total_errors"] == 2

        # Non-error cities should be processed
        assert result.response.get("processed_City_0") == True
        assert result.response.get("processed_City_1") == True
        assert result.response.get("processed_City_3") == True

    @pytest.mark.asyncio
    async def test_data_consistency_after_partial_failures(self):
        """Test data remains consistent after partial operation failures"""

        # Create initial valid data
        city1 = await City.create(name="Valid City 1", population=100000)
        city2 = await City.create(name="Valid City 2", population=200000)

        # Simulate partial failure scenario
        class PartialFailureWalker(Walker):
            @on_visit(RootNode)
            async def partial_operations(self, here):
                try:
                    # This should succeed
                    city3 = await City.create(name="Valid City 3", population=300000)
                    await here.connect(city3)
                    self.response["city3_created"] = True

                    # This will fail due to validation
                    try:
                        invalid_city = City(name="")  # Invalid empty name
                        await invalid_city.save()
                        self.response["invalid_city_created"] = True
                    except Exception as e:
                        self.response["expected_error"] = str(e)

                    # This should also succeed
                    city4 = await City.create(name="Valid City 4", population=400000)
                    await here.connect(city4)
                    self.response["city4_created"] = True

                except Exception as e:
                    self.response["unexpected_error"] = str(e)

            @on_exit
            async def verify_consistency(self):
                # Count valid cities
                all_cities = await City.all()
                valid_cities = [c for c in all_cities if c.name and c.name.strip()]

                self.response["total_valid_cities"] = len(valid_cities)
                self.response["consistency_check"] = "passed"

        # Run partial failure walker
        walker = PartialFailureWalker()
        result = await walker.spawn()

        # Verify expected behavior
        assert result.response["city3_created"] == True
        assert result.response["city4_created"] == True
        assert "expected_error" in result.response
        assert "unexpected_error" not in result.response
        assert result.response["consistency_check"] == "passed"
        assert (
            result.response["total_valid_cities"] >= 4
        )  # At least 2 initial + 2 new valid cities
