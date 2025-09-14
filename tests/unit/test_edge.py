"""
Comprehensive unit tests for Edge class covering edge directions, 
properties, custom types, and legacy format handling.
"""

import pytest
from typing import Optional

from jvspatial.core.entities import Node, Edge, find_subclass_by_name


class TestNode(Node):
    """Test node for edge testing"""
    name: str = "TestNode"


class Highway(Edge):
    """Test highway edge with properties"""
    lanes: int = 4
    speed_limit: int = 65
    toll_road: bool = False
    distance_km: float = 0.0


class Railroad(Edge):
    """Test railroad edge"""
    electrified: bool = False
    gauge: str = "standard"  # standard, narrow, broad


class TestEdgeCreation:
    """Test edge creation with different parameters"""
    
    @pytest.mark.asyncio
    async def test_basic_edge_creation(self):
        """Test basic edge creation between nodes"""
        node_a = await TestNode.create(name="NodeA")
        node_b = await TestNode.create(name="NodeB")
        
        edge = Edge(left=node_a, right=node_b, direction="out")
        await edge.save()
        
        assert edge.source == node_a.id
        assert edge.target == node_b.id
        assert edge.direction == "out"
        assert edge.id.startswith("e:Edge:")

    @pytest.mark.asyncio
    async def test_edge_with_explicit_ids(self):
        """Test edge creation with explicit source/target IDs"""
        node_a = await TestNode.create(name="NodeA")
        node_b = await TestNode.create(name="NodeB")
        
        edge = Edge(source=node_a.id, target=node_b.id, direction="in")
        await edge.save()
        
        assert edge.source == node_a.id
        assert edge.target == node_b.id
        assert edge.direction == "in"

    @pytest.mark.asyncio
    async def test_custom_edge_creation(self):
        """Test creating custom edge types with properties"""
        node_a = await TestNode.create(name="CityA")
        node_b = await TestNode.create(name="CityB")
        
        highway = Highway(
            left=node_a, 
            right=node_b,
            direction="both",
            lanes=6,
            speed_limit=70,
            toll_road=True,
            distance_km=125.5
        )
        await highway.save()
        
        assert isinstance(highway, Highway)
        assert highway.lanes == 6
        assert highway.speed_limit == 70
        assert highway.toll_road == True
        assert highway.distance_km == 125.5
        assert highway.direction == "both"

    @pytest.mark.asyncio
    async def test_edge_id_generation(self):
        """Test automatic ID generation for edges"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        # Without explicit ID
        edge1 = Edge(left=node_a, right=node_b)
        assert edge1.id.startswith("e:Edge:")
        
        # Custom edge type
        highway = Highway(left=node_a, right=node_b)
        assert highway.id.startswith("e:Highway:")
        
        # With explicit ID
        custom_id = "e:Edge:custom123"
        edge2 = Edge(left=node_a, right=node_b, id=custom_id)
        assert edge2.id == custom_id


class TestEdgeDirections:
    """Test different edge directions and their behavior"""
    
    @pytest.mark.asyncio
    async def test_outbound_direction(self):
        """Test outbound edge direction"""
        node_a = await TestNode.create(name="Start")
        node_b = await TestNode.create(name="End")
        
        edge = Edge(left=node_a, right=node_b, direction="out")
        
        assert edge.source == node_a.id
        assert edge.target == node_b.id
        assert edge.direction == "out"

    @pytest.mark.asyncio
    async def test_inbound_direction(self):
        """Test inbound edge direction"""
        node_a = await TestNode.create(name="Start")
        node_b = await TestNode.create(name="End")
        
        edge = Edge(left=node_a, right=node_b, direction="in")
        
        # Inbound means the direction is reversed
        assert edge.source == node_b.id
        assert edge.target == node_a.id
        assert edge.direction == "in"

    @pytest.mark.asyncio
    async def test_bidirectional_direction(self):
        """Test bidirectional edge direction"""
        node_a = await TestNode.create(name="NodeA")
        node_b = await TestNode.create(name="NodeB")
        
        edge = Edge(left=node_a, right=node_b, direction="both")
        
        assert edge.source == node_a.id
        assert edge.target == node_b.id
        assert edge.direction == "both"

    @pytest.mark.asyncio
    async def test_default_direction(self):
        """Test default edge direction"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        # Default should be "both" (from class definition)
        edge = Edge(left=node_a, right=node_b)
        assert edge.direction == "both"


class TestEdgeProperties:
    """Test edge properties and validation"""
    
    @pytest.mark.asyncio
    async def test_highway_properties(self):
        """Test highway-specific properties"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        highway = Highway(
            left=node_a,
            right=node_b,
            lanes=8,
            speed_limit=80,
            toll_road=False,
            distance_km=250.7
        )
        
        assert highway.lanes == 8
        assert highway.speed_limit == 80
        assert highway.toll_road == False
        assert highway.distance_km == 250.7

    @pytest.mark.asyncio
    async def test_railroad_properties(self):
        """Test railroad-specific properties"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        railroad = Railroad(
            left=node_a,
            right=node_b,
            electrified=True,
            gauge="broad"
        )
        
        assert railroad.electrified == True
        assert railroad.gauge == "broad"

    @pytest.mark.asyncio
    async def test_edge_property_defaults(self):
        """Test default values for edge properties"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        highway = Highway(left=node_a, right=node_b)
        
        # Test defaults
        assert highway.lanes == 4
        assert highway.speed_limit == 65
        assert highway.toll_road == False
        assert highway.distance_km == 0.0


class TestEdgePersistence:
    """Test edge export, save, and retrieval"""
    
    @pytest.mark.asyncio
    async def test_edge_export(self):
        """Test edge export functionality"""
        node_a = await TestNode.create(name="Start")
        node_b = await TestNode.create(name="End")
        
        highway = Highway(
            left=node_a,
            right=node_b,
            direction="out",
            lanes=6,
            speed_limit=70,
            toll_road=True
        )
        
        exported = highway.export()
        
        assert exported["id"] == highway.id
        assert exported["name"] == "Highway"
        assert exported["source"] == node_a.id
        assert exported["target"] == node_b.id
        assert exported["direction"] == "out"
        assert exported["bidirectional"] == False  # Legacy compatibility
        
        # Check context contains custom properties
        context = exported["context"]
        assert context["lanes"] == 6
        assert context["speed_limit"] == 70
        assert context["toll_road"] == True

    @pytest.mark.asyncio
    async def test_edge_save_and_retrieve(self):
        """Test saving and retrieving edges"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        original = Highway(
            left=node_a,
            right=node_b,
            lanes=4,
            speed_limit=65,
            distance_km=100.0
        )
        await original.save()
        
        # Retrieve the edge
        retrieved = await Highway.get(original.id)
        
        assert retrieved is not None
        assert retrieved.id == original.id
        assert isinstance(retrieved, Highway)
        assert retrieved.source == original.source
        assert retrieved.target == original.target
        assert retrieved.lanes == original.lanes
        assert retrieved.speed_limit == original.speed_limit
        assert retrieved.distance_km == original.distance_km

    @pytest.mark.asyncio
    async def test_edge_subclass_instantiation(self):
        """Test that retrieved edges maintain their subclass type"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        highway = Highway(left=node_a, right=node_b, lanes=6)
        await highway.save()
        highway_id = highway.id
        
        # Retrieve as base Edge class
        retrieved_as_edge = await Edge.get(highway_id)
        assert isinstance(retrieved_as_edge, Highway)
        assert retrieved_as_edge.lanes == 6
        
        # Retrieve as specific Highway class
        retrieved_as_highway = await Highway.get(highway_id)
        assert isinstance(retrieved_as_highway, Highway)
        assert retrieved_as_highway.lanes == 6


class TestEdgeLegacyFormat:
    """Test handling of legacy data formats"""
    
    @pytest.mark.asyncio
    async def test_legacy_data_format_retrieval(self):
        """Test retrieving edges stored in legacy format"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        # Simulate legacy data format (source/target in context)
        legacy_data = {
            "id": "e:Edge:legacy123",
            "name": "Edge",
            "context": {
                "source": node_a.id,
                "target": node_b.id,
                "direction": "out"
            }
        }
        
        # Save legacy format to database
        db = Edge.get_db()
        await db.save("edge", legacy_data)
        
        # Retrieve should work correctly
        retrieved = await Edge.get("e:Edge:legacy123")
        
        assert retrieved is not None
        assert retrieved.source == node_a.id
        assert retrieved.target == node_b.id
        assert retrieved.direction == "out"

    @pytest.mark.asyncio
    async def test_new_format_with_top_level_fields(self):
        """Test new format with source/target at top level"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        # Create edge in new format
        edge = Edge(left=node_a, right=node_b, direction="both")
        await edge.save()
        
        # Retrieve should work
        retrieved = await Edge.get(edge.id)
        
        assert retrieved is not None
        assert retrieved.source == node_a.id
        assert retrieved.target == node_b.id
        assert retrieved.direction == "both"


class TestEdgeAll:
    """Test Edge.all() functionality"""
    
    @pytest.mark.asyncio
    async def test_retrieve_all_edges(self):
        """Test retrieving all edges"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        node_c = await TestNode.create()
        
        # Create test edges
        edge1 = Edge(left=node_a, right=node_b)
        await edge1.save()
        
        highway = Highway(left=node_b, right=node_c, lanes=6)
        await highway.save()
        
        railroad = Railroad(left=node_a, right=node_c, electrified=True)
        await railroad.save()
        
        # Get all edges
        all_edges = await Edge.all()
        
        # Should have at least our test edges
        assert len(all_edges) >= 3
        
        # Check for specific edge types
        edge_types = [type(edge).__name__ for edge in all_edges]
        assert "Edge" in edge_types
        assert "Highway" in edge_types
        assert "Railroad" in edge_types

    @pytest.mark.asyncio
    async def test_retrieve_specific_edge_type(self):
        """Test retrieving edges of specific types"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        # Create highway
        highway = Highway(left=node_a, right=node_b, lanes=4)
        await highway.save()
        
        # Get all highways
        all_highways = await Highway.all()
        
        # Should have at least our test highway
        highway_ids = [h.id for h in all_highways]
        assert highway.id in highway_ids
        
        # All should be Highway instances
        for h in all_highways:
            assert isinstance(h, Highway)


class TestEdgeValidation:
    """Test edge validation and error handling"""
    
    @pytest.mark.asyncio
    async def test_edge_without_nodes(self):
        """Test creating edge without providing nodes"""
        edge = Edge(source="test_source", target="test_target")
        
        assert edge.source == "test_source"
        assert edge.target == "test_target"
        assert edge.direction == "both"  # default from class definition

    @pytest.mark.asyncio
    async def test_edge_with_mixed_parameters(self):
        """Test edge creation with both nodes and explicit IDs"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        # Explicit source/target should override left/right
        edge = Edge(
            left=node_a,
            right=node_b,
            source="custom_source",
            target="custom_target"
        )
        
        assert edge.source == "custom_source"
        assert edge.target == "custom_target"


class TestFindSubclassByName:
    """Test the find_subclass_by_name utility function"""
    
    def test_find_exact_class(self):
        """Test finding exact class match"""
        result = find_subclass_by_name(Edge, "Edge")
        assert result == Edge

    # def test_find_subclass(self):
    #     """Test finding subclass by name"""
    #     result = find_subclass_by_name(Edge, "Highway")
    #     assert result == Highway
        
    #     result = find_subclass_by_name(Edge, "Railroad")
    #     assert result == Railroad

    def test_find_nonexistent_class(self):
        """Test finding non-existent class"""
        result = find_subclass_by_name(Edge, "NonExistentEdge")
        assert result is None

    def test_find_in_deep_hierarchy(self):
        """Test finding in deeper class hierarchies"""
        class SpecialHighway(Highway):
            pass
        
        result = find_subclass_by_name(Edge, "SpecialHighway")
        assert result == SpecialHighway


class TestEdgeBackwardCompatibility:
    """Test backward compatibility features"""
    
    @pytest.mark.asyncio
    async def test_bidirectional_field(self):
        """Test the bidirectional field for backward compatibility"""
        node_a = await TestNode.create()
        node_b = await TestNode.create()
        
        # Both direction
        edge_both = Edge(left=node_a, right=node_b, direction="both")
        exported_both = edge_both.export()
        assert exported_both["bidirectional"] == True
        
        # Out direction
        edge_out = Edge(left=node_a, right=node_b, direction="out")
        exported_out = edge_out.export()
        assert exported_out["bidirectional"] == False
        
        # In direction
        edge_in = Edge(left=node_a, right=node_b, direction="in")
        exported_in = edge_in.export()
        assert exported_in["bidirectional"] == False