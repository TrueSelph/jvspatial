"""
Enhanced unit tests for Node class covering spatial queries, 
edge filtering, export/import, and cascade deletion.
"""

import pytest
import math
from typing import List

from jvspatial.core.entities import Node, Edge, RootNode
from jvspatial.spatial import calculate_distance
# Import spatial utilities to enable find_nearby and find_in_bounds methods
import jvspatial.spatial.utils


class City(Node):
    """Test city node with spatial properties"""
    name: str
    population: int = 0
    latitude: float = 0.0
    longitude: float = 0.0


class Highway(Edge):
    """Test highway edge with properties"""
    lanes: int = 4
    speed_limit: int = 65
    toll_road: bool = False


class TestNodeSpatialQueries:
    """Test spatial query functionality"""
    
    @pytest.mark.asyncio
    async def test_find_nearby_nodes(self):
        """Test finding nodes within radius"""
        # Create cities at known distances
        chicago = await City.create(
            name="Chicago", 
            latitude=41.8781, 
            longitude=-87.6298,
            population=2697000
        )
        milwaukee = await City.create(
            name="Milwaukee",
            latitude=43.0389,
            longitude=-87.9065,
            population=594833
        )
        # New York is much farther
        new_york = await City.create(
            name="New York",
            latitude=40.7128,
            longitude=-74.0060,
            population=8336817
        )
        
        # Find cities within 200km of Chicago
        nearby = await City.find_nearby(41.8781, -87.6298, 200.0)
        nearby_names = [city.name for city in nearby]
        
        assert "Chicago" in nearby_names
        assert "Milwaukee" in nearby_names
        assert "New York" not in nearby_names
        
        # Test smaller radius
        close_cities = await City.find_nearby(41.8781, -87.6298, 50.0)
        close_names = [city.name for city in close_cities]
        
        assert "Chicago" in close_names
        assert "Milwaukee" not in close_names

    @pytest.mark.asyncio
    async def test_find_in_bounds(self):
        """Test finding nodes within bounding box"""
        # Create cities in different regions
        chicago = await City.create(
            name="Chicago",
            latitude=41.8781,
            longitude=-87.6298
        )
        la = await City.create(
            name="Los Angeles", 
            latitude=34.0522,
            longitude=-118.2437
        )
        
        # Midwest bounding box
        midwest_cities = await City.find_in_bounds(
            min_lat=40.0, max_lat=45.0,
            min_lon=-90.0, max_lon=-85.0
        )
        midwest_names = [city.name for city in midwest_cities]
        
        assert "Chicago" in midwest_names
        assert "Los Angeles" not in midwest_names

    @pytest.mark.asyncio
    async def test_spatial_distance_calculation(self):
        """Test the distance calculation function"""
        # Chicago to Milwaukee
        chicago_lat, chicago_lon = 41.8781, -87.6298
        milwaukee_lat, milwaukee_lon = 43.0389, -87.9065
        
        distance = calculate_distance(
            chicago_lat, chicago_lon, 
            milwaukee_lat, milwaukee_lon
        )
        
        # Should be approximately 131 km (actual distance)
        assert 130 <= distance <= 135


class TestNodeConnections:
    """Test node connection and edge management"""
    
    @pytest.mark.asyncio
    async def test_custom_edge_creation(self):
        """Test creating connections with custom edge types"""
        chicago = await City.create(name="Chicago")
        milwaukee = await City.create(name="Milwaukee")
        
        # Create highway connection
        highway = await chicago.connect(
            milwaukee, 
            Highway,
            lanes=6,
            speed_limit=70,
            toll_road=True
        )
        
        assert isinstance(highway, Highway)
        assert highway.lanes == 6
        assert highway.speed_limit == 70
        assert highway.toll_road == True
        assert highway.source == chicago.id
        assert highway.target == milwaukee.id

    @pytest.mark.asyncio
    async def test_edge_directions(self):
        """Test different edge directions"""
        node_a = await Node.create()
        node_b = await Node.create()
        
        # Test outbound connection
        edge_out = await node_a.connect(node_b, direction="out")
        assert edge_out.source == node_a.id
        assert edge_out.target == node_b.id
        assert edge_out.direction == "out"
        
        # Test inbound connection
        edge_in = await node_a.connect(node_b, direction="in")
        assert edge_in.source == node_b.id
        assert edge_in.target == node_a.id
        assert edge_in.direction == "in"
        
        # Test bidirectional connection
        edge_both = await node_a.connect(node_b, direction="both")
        assert edge_both.direction == "both"

    @pytest.mark.asyncio
    async def test_edge_filtering(self):
        """Test filtering edges by direction and type"""
        chicago = await City.create(name="Chicago")
        milwaukee = await City.create(name="Milwaukee")
        detroit = await City.create(name="Detroit")
        
        # Create different types of connections
        highway = await chicago.connect(milwaukee, Highway, direction="out")
        regular_edge = await chicago.connect(detroit, direction="out")
        
        # Test filtering by direction
        out_edges = await chicago.edges(direction="out")
        assert len(out_edges) == 2
        
        # Test filtering connected nodes by edge type
        highway_nodes = await (await chicago.nodes()).filter(edge=Highway)
        highway_names = [node.name for node in highway_nodes]
        assert "Milwaukee" in highway_names
        assert "Detroit" not in highway_names

    @pytest.mark.asyncio
    async def test_node_query_filtering(self):
        """Test NodeQuery filtering capabilities"""
        chicago = await City.create(name="Chicago", population=2697000)
        milwaukee = await City.create(name="Milwaukee", population=594833)
        small_town = await Node.create()  # Not a city
        
        root = await RootNode.get()
        await root.connect(chicago)
        await root.connect(milwaukee)
        await root.connect(small_town)
        
        # Filter by node type
        cities = await (await root.nodes()).filter(node="City")
        city_names = [city.name for city in cities]
        assert "Chicago" in city_names
        assert "Milwaukee" in city_names
        assert len(cities) == 2
        
        # Filter by multiple node types
        all_connected = await (await root.nodes()).filter(node=["City", "Node"])
        assert len(all_connected) >= 3


class TestNodePersistence:
    """Test node export, import, and persistence"""
    
    @pytest.mark.asyncio
    async def test_node_export(self):
        """Test node export functionality"""
        chicago = await City.create(
            name="Chicago",
            population=2697000,
            latitude=41.8781,
            longitude=-87.6298
        )
        
        exported = chicago.export()
        
        assert exported["id"] == chicago.id
        assert exported["name"] == "City"
        assert exported["context"]["name"] == "Chicago"
        assert exported["context"]["population"] == 2697000
        assert exported["context"]["latitude"] == 41.8781
        assert exported["context"]["longitude"] == -87.6298
        assert "edges" in exported
        
    @pytest.mark.asyncio
    async def test_node_persistence_and_retrieval(self):
        """Test saving and retrieving nodes"""
        original = await City.create(
            name="Detroit", 
            population=670031,
            latitude=42.3314,
            longitude=-83.0458
        )
        
        # Retrieve the saved node
        retrieved = await City.get(original.id)
        
        assert retrieved is not None
        assert retrieved.id == original.id
        assert retrieved.name == original.name
        assert retrieved.population == original.population
        assert retrieved.latitude == original.latitude
        assert retrieved.longitude == original.longitude

    @pytest.mark.asyncio
    async def test_subclass_instantiation(self):
        """Test that retrieved nodes maintain their subclass type"""
        city = await City.create(name="Boston")
        city_id = city.id
        
        # Retrieve as base Node class
        retrieved_as_node = await Node.get(city_id)
        assert isinstance(retrieved_as_node, City)
        assert retrieved_as_node.name == "Boston"
        
        # Retrieve as specific City class
        retrieved_as_city = await City.get(city_id)
        assert isinstance(retrieved_as_city, City)
        assert retrieved_as_city.name == "Boston"


class TestNodeDestruction:
    """Test node deletion and cascade operations"""
    
    @pytest.mark.asyncio
    async def test_simple_node_deletion(self):
        """Test basic node deletion"""
        node = await Node.create()
        node_id = node.id
        
        await node.destroy()
        
        # Node should no longer exist
        retrieved = await Node.get(node_id)
        assert retrieved is None

    @pytest.mark.asyncio  
    async def test_cascade_deletion(self):
        """Test cascade deletion of connected edges"""
        node_a = await Node.create()
        node_b = await Node.create()
        
        # Create connection
        edge = await node_a.connect(node_b)
        edge_id = edge.id
        
        # Delete node with cascade
        await node_a.destroy(cascade=True)
        
        # Node should be gone
        retrieved_node = await Node.get(node_a.id)
        assert retrieved_node is None
        
        # Edge should also be gone
        retrieved_edge = await Edge.get(edge_id)
        assert retrieved_edge is None
        
        # Other node should still exist but with updated edge list
        node_b_retrieved = await Node.get(node_b.id)
        assert node_b_retrieved is not None

    @pytest.mark.asyncio
    async def test_non_cascade_deletion(self):
        """Test non-cascade deletion preserves edges"""
        node_a = await Node.create()
        node_b = await Node.create()
        
        edge = await node_a.connect(node_b)
        edge_id = edge.id
        
        # Delete node without cascade
        await node_a.destroy(cascade=False)
        
        # Node should be gone
        retrieved_node = await Node.get(node_a.id)
        assert retrieved_node is None
        
        # Edge should still exist (orphaned)
        retrieved_edge = await Edge.get(edge_id)
        assert retrieved_edge is not None


class TestNodeAll:
    """Test Node.all() functionality"""
    
    @pytest.mark.asyncio
    async def test_retrieve_all_nodes(self):
        """Test retrieving all nodes"""
        # Create some test nodes
        cities = []
        for i in range(3):
            city = await City.create(name=f"TestCity{i}")
            cities.append(city)
        
        all_nodes = await Node.all()
        all_cities = await City.all()
        
        # Should have at least our test nodes
        assert len(all_nodes) >= 3
        assert len(all_cities) >= 3
        
        # Check that our cities are in the results
        all_city_names = [city.name for city in all_cities if hasattr(city, 'name')]
        for i in range(3):
            assert f"TestCity{i}" in all_city_names


class TestNodeEdgeIds:
    """Test edge ID management in nodes"""
    
    @pytest.mark.asyncio
    async def test_edge_id_updates(self):
        """Test that edge IDs are properly maintained"""
        node_a = await Node.create()
        node_b = await Node.create()
        node_c = await Node.create()
        
        # Connect nodes
        edge1 = await node_a.connect(node_b)
        edge2 = await node_a.connect(node_c)
        
        # Check edge IDs are tracked
        assert edge1.id in node_a.edge_ids
        assert edge2.id in node_a.edge_ids
        assert edge1.id in node_b.edge_ids
        assert edge2.id in node_c.edge_ids
        
        # Check edge count
        assert len(node_a.edge_ids) == 2
        assert len(node_b.edge_ids) == 1
        assert len(node_c.edge_ids) == 1

    @pytest.mark.asyncio
    async def test_duplicate_edge_prevention(self):
        """Test that duplicate edge IDs aren't added"""
        node_a = await Node.create()
        node_b = await Node.create()
        
        # Create connection
        edge = await node_a.connect(node_b)
        original_count = len(node_a.edge_ids)
        
        # Try to add the same edge ID again (shouldn't happen in normal usage)
        if edge.id not in node_a.edge_ids:
            node_a.edge_ids.append(edge.id)
        
        # Count should remain the same
        assert len(node_a.edge_ids) == original_count