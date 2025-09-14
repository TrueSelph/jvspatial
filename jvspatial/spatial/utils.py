"""Spatial utility functions for coordinate calculations and queries."""

import math
from typing import List, Type

from ..core.entities import Node


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers using Haversine formula."""
    earth_radius = 6371  # Earth's radius in kilometers
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius * c


async def find_nearby_nodes(
    node_class: Type[Node], latitude: float, longitude: float, radius_km: float = 10.0
) -> List[Node]:
    """Find nodes within a specified radius of coordinates.

    Args:
        node_class: The Node class to search within
        latitude: Center latitude
        longitude: Center longitude
        radius_km: Search radius in kilometers

    Returns:
        List of nodes within the radius
    """
    from ..core.entities import find_subclass_by_name

    # Get all nodes from the database
    collection = node_class.get_collection_name_for_class()
    nodes_data = await node_class.get_db().find(collection, {})
    nearby = []

    for data in nodes_data:
        # Only process nodes that match the calling class or have the right stored name
        stored_name = data.get("name", node_class.__name__)
        if stored_name == node_class.__name__ or node_class.__name__ == "Node":
            try:
                # Check if this node has spatial data
                context = data.get("context", {})
                if "latitude" in context and "longitude" in context:
                    distance = calculate_distance(
                        latitude,
                        longitude,
                        float(context["latitude"]),
                        float(context["longitude"]),
                    )
                    if distance <= radius_km:
                        # Create the node with proper subclass
                        target_class = (
                            find_subclass_by_name(node_class, stored_name) or node_class
                        )
                        node = target_class(id=data["id"], **context)
                        if "edges" in data:
                            node.edge_ids = data["edges"]
                        nearby.append(node)
            except (ValueError, TypeError, KeyError):
                # Skip nodes that can't be processed
                continue
    return nearby


async def find_nodes_in_bounds(
    node_class: Type[Node],
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> List[Node]:
    """Find nodes within a bounding box.

    Args:
        node_class: The Node class to search within
        min_lat: Minimum latitude
        max_lat: Maximum latitude
        min_lon: Minimum longitude
        max_lon: Maximum longitude

    Returns:
        List of nodes within the bounding box
    """
    from ..core.entities import find_subclass_by_name

    # Get all nodes from the database
    collection = node_class.get_collection_name_for_class()
    nodes_data = await node_class.get_db().find(collection, {})
    bounded = []

    for data in nodes_data:
        # Only process nodes that match the calling class or have the right stored name
        stored_name = data.get("name", node_class.__name__)
        if stored_name == node_class.__name__ or node_class.__name__ == "Node":
            try:
                # Check if this node has spatial data
                context = data.get("context", {})
                if "latitude" in context and "longitude" in context:
                    lat, lon = float(context["latitude"]), float(context["longitude"])
                    if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                        # Create the node with proper subclass
                        target_class = (
                            find_subclass_by_name(node_class, stored_name) or node_class
                        )
                        node = target_class(id=data["id"], **context)
                        if "edges" in data:
                            node.edge_ids = data["edges"]
                        bounded.append(node)
            except (ValueError, TypeError, KeyError):
                # Skip nodes that can't be processed
                continue
    return bounded


# Add convenience methods to Node classes via monkey patching
def _add_spatial_methods_to_node() -> None:
    """Add spatial methods as class methods to Node classes."""
    try:
        # Import here to avoid circular imports
        from ..core.entities import Node

        async def find_nearby(
            cls: Type[Node], latitude: float, longitude: float, radius_km: float = 10.0
        ) -> List[Node]:
            return await find_nearby_nodes(cls, latitude, longitude, radius_km)

        async def find_in_bounds(
            cls: Type[Node],
            min_lat: float,
            max_lat: float,
            min_lon: float,
            max_lon: float,
        ) -> List[Node]:
            return await find_nodes_in_bounds(cls, min_lat, max_lat, min_lon, max_lon)

        # Only add if not already present
        if not hasattr(Node, "find_nearby"):
            Node.find_nearby = classmethod(find_nearby)
        if not hasattr(Node, "find_in_bounds"):
            Node.find_in_bounds = classmethod(find_in_bounds)

    except ImportError:
        # Ignore import errors during module initialization
        pass


# Automatically add spatial methods when module is imported
_add_spatial_methods_to_node()
