"""
Unit tests for decorator functions (@on_visit, @on_exit) and spatial utility functions.
"""

import inspect
import math

import pytest

from jvspatial.core.entities import (
    Edge,
    Node,
    Walker,
    _register_hook,
    find_subclass_by_name,
    on_exit,
    on_visit,
)
from jvspatial.spatial import calculate_distance


class TestNode(Node):
    """Test node for decorator testing"""

    name: str = "TestNode"


class TestWalker(Walker):
    """Test walker for decorator testing"""

    name: str = "TestWalker"


class TestEdge(Edge):
    """Test edge for decorator testing"""

    name: str = "TestEdge"


class TestOnVisitDecorator:
    """Test @on_visit decorator functionality"""

    def test_on_visit_with_node_type(self):
        """Test @on_visit decorator with specific node type"""

        @on_visit(TestNode)
        def visit_test_node(walker, here):
            pass

        # Check that decorator sets proper attributes
        assert hasattr(visit_test_node, "_on_visit_target")
        assert visit_test_node._on_visit_target == TestNode
        assert hasattr(visit_test_node, "__visit_target__")
        assert visit_test_node.__visit_target__ == TestNode

    def test_on_visit_without_target(self):
        """Test @on_visit decorator without specific target"""

        @on_visit()
        def visit_any(walker, here):
            pass

        # Should work without target type
        assert hasattr(visit_any, "_on_visit_target")
        assert visit_any._on_visit_target is None

    def test_on_visit_as_function_decorator(self):
        """Test @on_visit used as function decorator directly"""

        @on_visit
        def visit_func(walker, here):
            pass

        # Should work when used directly on function
        assert hasattr(visit_func, "_on_visit_target")
        assert visit_func._on_visit_target is None

    def test_on_visit_preserves_function_attributes(self):
        """Test that @on_visit preserves original function attributes"""

        def original_func(walker, here):
            """Original docstring"""
            return "test_value"

        decorated = on_visit(TestNode)(original_func)

        # Check function name and docstring preserved
        assert decorated.__name__ == original_func.__name__
        assert decorated.__doc__ == original_func.__doc__

        # Check annotations preserved
        if hasattr(original_func, "__annotations__"):
            assert decorated.__annotations__ == original_func.__annotations__

    def test_on_visit_async_function(self):
        """Test @on_visit with async functions"""

        @on_visit(TestNode)
        async def async_visit(walker, here):
            return "async_result"

        # Should preserve async nature
        assert inspect.iscoroutinefunction(async_visit)
        assert hasattr(async_visit, "_on_visit_target")
        assert async_visit._on_visit_target == TestNode

    def test_on_visit_sync_function(self):
        """Test @on_visit with sync functions"""

        @on_visit(TestNode)
        def sync_visit(walker, here):
            return "sync_result"

        # Should preserve sync nature
        assert not inspect.iscoroutinefunction(sync_visit)
        assert hasattr(sync_visit, "_on_visit_target")
        assert sync_visit._on_visit_target == TestNode

    def test_on_visit_invalid_target_type(self):
        """Test @on_visit with invalid target type"""
        with pytest.raises(ValueError):

            @on_visit("invalid_type")
            def visit_invalid(walker, here):
                pass

    def test_on_visit_with_edge_type(self):
        """Test @on_visit with edge type"""

        @on_visit(TestEdge)
        def visit_edge(walker, here):
            pass

        assert visit_edge._on_visit_target == TestEdge

    def test_on_visit_with_walker_type(self):
        """Test @on_visit with walker type"""

        @on_visit(TestWalker)
        def visit_walker(node, visitor):
            pass

        assert visit_walker._on_visit_target == TestWalker


class TestOnExitDecorator:
    """Test @on_exit decorator functionality"""

    def test_on_exit_basic(self):
        """Test basic @on_exit decorator"""

        @on_exit
        def exit_handler():
            pass

        # Check that decorator sets proper attributes
        assert hasattr(exit_handler, "_on_exit")
        assert exit_handler._on_exit == True

    def test_on_exit_async_function(self):
        """Test @on_exit with async function"""

        @on_exit
        async def async_exit():
            return "async_exit"

        # Should preserve async nature and set exit flag
        assert inspect.iscoroutinefunction(async_exit)
        assert hasattr(async_exit, "_on_exit")
        assert async_exit._on_exit == True

    def test_on_exit_sync_function(self):
        """Test @on_exit with sync function"""

        @on_exit
        def sync_exit():
            return "sync_exit"

        # Should preserve sync nature and set exit flag
        assert not inspect.iscoroutinefunction(sync_exit)
        assert hasattr(sync_exit, "_on_exit")
        assert sync_exit._on_exit == True

    def test_on_exit_preserves_function_attributes(self):
        """Test that @on_exit preserves original function attributes"""

        def original_exit():
            """Exit docstring"""
            return "exit_value"

        decorated = on_exit(original_exit)

        # Check function attributes preserved
        assert decorated.__name__ == original_exit.__name__
        assert decorated.__doc__ == original_exit.__doc__


class TestRegisterHook:
    """Test _register_hook function"""

    def test_register_walker_hook_for_node(self):
        """Test registering walker hook for node target"""

        def visit_node(walker, here):
            pass

        # Set target manually
        visit_node.__visit_target__ = TestNode
        visit_node._context_var = None  # Pre-existing attribute

        # Register hook
        registered = _register_hook(TestWalker, visit_node)

        # Should set context variable
        assert hasattr(registered, "_context_var")
        assert registered._context_var == "here"

    def test_register_node_hook_for_walker(self):
        """Test registering node hook for walker target"""

        def handle_walker(node, visitor):
            pass

        # Set target manually
        handle_walker.__visit_target__ = TestWalker
        handle_walker._context_var = None  # Pre-existing attribute

        # Register hook
        registered = _register_hook(TestNode, handle_walker)

        # Should set context variable
        assert hasattr(registered, "_context_var")
        assert registered._context_var == "visitor"

    def test_register_hook_invalid_walker_target(self):
        """Test registering walker hook with invalid target"""

        def invalid_hook(walker, here):
            pass

        # Set invalid target
        invalid_hook.__visit_target__ = str  # Invalid type

        # Should raise TypeError
        with pytest.raises(TypeError):
            _register_hook(TestWalker, invalid_hook)

    def test_register_hook_invalid_node_target(self):
        """Test registering node hook with invalid target"""

        def invalid_hook(node, visitor):
            pass

        # Set invalid target
        invalid_hook.__visit_target__ = str  # Invalid type

        # Should raise TypeError
        with pytest.raises(TypeError):
            _register_hook(TestNode, invalid_hook)

    def test_register_hook_none_target(self):
        """Test registering hook with None target"""

        def generic_hook(obj, context):
            pass

        # Set None target
        generic_hook.__visit_target__ = None

        # Add context var for testing
        generic_hook._context_var = None

        # Should work for walker
        walker_hook = _register_hook(TestWalker, generic_hook)
        assert walker_hook._context_var == "here"

        # Reset for node test
        generic_hook._context_var = None

        # Should work for node
        node_hook = _register_hook(TestNode, generic_hook)
        assert node_hook._context_var == "visitor"


class TestSpatialFunctions:
    """Test spatial calculation functions"""

    def test_calculate_distance_same_point(self):
        """Test distance calculation for same point"""
        lat, lon = 40.7128, -74.0060  # New York
        distance = calculate_distance(lat, lon, lat, lon)

        assert distance == 0.0

    def test_calculate_distance_known_cities(self):
        """Test distance calculation between known cities"""
        # New York to Los Angeles
        ny_lat, ny_lon = 40.7128, -74.0060
        la_lat, la_lon = 34.0522, -118.2437

        distance = calculate_distance(ny_lat, ny_lon, la_lat, la_lon)

        # Should be approximately 3944 km
        assert 3900 <= distance <= 4000

    def test_calculate_distance_chicago_milwaukee(self):
        """Test distance between Chicago and Milwaukee"""
        chicago_lat, chicago_lon = 41.8781, -87.6298
        milwaukee_lat, milwaukee_lon = 43.0389, -87.9065

        distance = calculate_distance(
            chicago_lat, chicago_lon, milwaukee_lat, milwaukee_lon
        )

        # Should be approximately 131 km (actual distance)
        assert 130 <= distance <= 135

    def test_calculate_distance_equator_points(self):
        """Test distance calculation along equator"""
        # Two points on equator, 1 degree apart
        lat1, lon1 = 0.0, 0.0
        lat2, lon2 = 0.0, 1.0

        distance = calculate_distance(lat1, lon1, lat2, lon2)

        # 1 degree longitude at equator ≈ 111.32 km
        assert 110 <= distance <= 112

    def test_calculate_distance_poles(self):
        """Test distance between poles"""
        north_pole_lat, north_pole_lon = 90.0, 0.0
        south_pole_lat, south_pole_lon = -90.0, 0.0

        distance = calculate_distance(
            north_pole_lat, north_pole_lon, south_pole_lat, south_pole_lon
        )

        # Should be approximately half Earth's circumference (≈ 20,015 km)
        assert 19500 <= distance <= 20500

    def test_calculate_distance_negative_coordinates(self):
        """Test distance calculation with negative coordinates"""
        # Sydney, Australia
        sydney_lat, sydney_lon = -33.8688, 151.2093
        # London, UK
        london_lat, london_lon = 51.5074, -0.1278

        distance = calculate_distance(sydney_lat, sydney_lon, london_lat, london_lon)

        # Should be approximately 17,000 km
        assert 16500 <= distance <= 17500

    def test_calculate_distance_edge_cases(self):
        """Test distance calculation edge cases"""
        # Test with extreme latitude values
        extreme_lat1, extreme_lon1 = 89.9, 0.0
        extreme_lat2, extreme_lon2 = -89.9, 180.0

        distance = calculate_distance(
            extreme_lat1, extreme_lon1, extreme_lat2, extreme_lon2
        )

        # Should be a valid distance (close to pole-to-pole)
        assert 19000 <= distance <= 21000

    def test_haversine_formula_accuracy(self):
        """Test accuracy of Haversine formula implementation"""
        # Test case where we know the exact distance
        # Two points 1 degree apart on same latitude
        lat = 45.0  # 45 degrees north
        lon1, lon2 = 0.0, 1.0

        distance = calculate_distance(lat, lon1, lat, lon2)

        # At 45°N, 1° longitude ≈ 78.71 km
        expected = 111.32 * math.cos(math.radians(45))  # Approximate formula

        # Should be within 1% of expected
        assert abs(distance - expected) / expected < 0.01


class TestFindSubclassByName:
    """Test find_subclass_by_name utility function"""

    def test_find_exact_class(self):
        """Test finding exact class match"""
        result = find_subclass_by_name(Node, "Node")
        assert result == Node

    def test_find_nonexistent_class(self):
        """Test finding non-existent class"""
        result = find_subclass_by_name(Node, "NonExistentNode")
        assert result is None

    def test_find_with_multiple_inheritance(self):
        """Test finding class with multiple inheritance paths"""

        class Mixin:
            pass

        class ComplexNode(Node, Mixin):
            pass

        result = find_subclass_by_name(Node, "ComplexNode")
        assert result == ComplexNode

    def test_find_in_different_base_classes(self):
        """Test finding subclasses in different base classes"""
        # Test with Edge base class
        result = find_subclass_by_name(Edge, "TestEdge")
        assert result == TestEdge

        # Test with Walker base class
        result = find_subclass_by_name(Walker, "TestWalker")
        assert result == TestWalker

    def test_find_partial_name_match(self):
        """Test that partial name matches don't work"""
        result = find_subclass_by_name(Node, "Test")  # partial match
        assert result is None

        result = find_subclass_by_name(Node, "Node")  # exact match
        assert result == Node


class TestMathUtilities:
    """Test mathematical utilities used in spatial functions"""

    def test_radians_conversion(self):
        """Test radian conversion used in distance calculations"""
        # Test conversion of common angles
        assert math.radians(0) == 0
        assert abs(math.radians(90) - math.pi / 2) < 1e-10
        assert abs(math.radians(180) - math.pi) < 1e-10
        assert abs(math.radians(360) - 2 * math.pi) < 1e-10

    def test_trigonometric_functions(self):
        """Test trigonometric functions used in distance calculation"""
        # Test sin function
        assert abs(math.sin(0) - 0) < 1e-10
        assert abs(math.sin(math.pi / 2) - 1) < 1e-10

        # Test cos function
        assert abs(math.cos(0) - 1) < 1e-10
        assert abs(math.cos(math.pi / 2) - 0) < 1e-10

        # Test atan2 function
        assert abs(math.atan2(0, 1) - 0) < 1e-10
        assert abs(math.atan2(1, 0) - math.pi / 2) < 1e-10

    def test_sqrt_function(self):
        """Test sqrt function used in distance calculation"""
        assert math.sqrt(0) == 0
        assert math.sqrt(1) == 1
        assert math.sqrt(4) == 2
        assert abs(math.sqrt(2) - 1.4142135623730951) < 1e-10


class TestCoordinateValidation:
    """Test coordinate validation and edge cases"""

    def test_valid_latitude_range(self):
        """Test valid latitude coordinates"""
        # Valid latitudes: -90 to +90
        valid_lats = [-90, -45, 0, 45, 90]

        for lat in valid_lats:
            # Should not raise errors
            distance = calculate_distance(lat, 0, lat, 0)
            assert distance == 0

    def test_valid_longitude_range(self):
        """Test valid longitude coordinates"""
        # Valid longitudes: -180 to +180
        valid_lons = [-180, -90, 0, 90, 180]

        for lon in valid_lons:
            # Should not raise errors
            distance = calculate_distance(0, lon, 0, lon)
            assert distance == 0

    def test_extreme_coordinate_values(self):
        """Test extreme but valid coordinate values"""
        # Test extreme latitudes
        distance1 = calculate_distance(90, 0, -90, 0)  # Pole to pole
        assert distance1 > 0

        # Test extreme longitudes
        distance2 = calculate_distance(0, -180, 0, 180)  # Should be 0 (same meridian)
        assert (
            abs(distance2) < 1e-10
        )  # -180 and 180 are the same meridian (allow for floating point precision)

    def test_coordinate_precision(self):
        """Test high precision coordinates"""
        # Test with high precision decimal coordinates
        lat1, lon1 = 40.748817, -73.985428  # Empire State Building
        lat2, lon2 = 40.689247, -74.044502  # Statue of Liberty

        distance = calculate_distance(lat1, lon1, lat2, lon2)

        # Should be approximately 8.8 km
        assert 8 <= distance <= 10
