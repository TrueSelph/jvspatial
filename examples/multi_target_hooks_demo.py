#!/usr/bin/env python3
"""
Enhanced @on_visit Decorator Demo

This example demonstrates the new multi-target @on_visit decorator features:
- Multi-target hooks: @on_visit(TypeA, TypeB)
- Catch-all hooks: @on_visit()
- Edge traversal and hooks
- Node and Edge responding to Walker visits
"""

import asyncio
from typing import List

from jvspatial.core.entities import Edge, Node, Walker, on_exit, on_visit

# =============================================================================
# NODE TYPES
# =============================================================================


class City(Node):
    """City node representing urban centers"""

    name: str
    population: int = 0
    tourism_score: int = 5


class Warehouse(Node):
    """Warehouse node for logistics"""

    name: str
    capacity: int = 1000
    current_stock: int = 0


class Port(Node):
    """Port node for maritime logistics"""

    name: str
    cargo_capacity: int = 10000
    has_customs: bool = True


# =============================================================================
# EDGE TYPES
# =============================================================================


class Highway(Edge):
    """Highway connecting cities"""

    name: str
    lanes: int = 4
    speed_limit: int = 65
    toll_cost: float = 0.0


class ShippingRoute(Edge):
    """Maritime shipping route"""

    name: str
    distance_km: float = 0.0
    max_cargo_weight: float = 50000.0


class Railroad(Edge):
    """Railroad connection"""

    name: str
    tracks: int = 2
    electrified: bool = False


# =============================================================================
# WALKER TYPES
# =============================================================================


class TouristWalker(Walker):
    """Tourist exploring cities and attractions"""

    budget: float = 1000.0
    cities_visited: int = 0

    @on_visit(City)  # Single target - only cities
    async def visit_city(self, here):
        self.cities_visited += 1
        self.budget -= 50.0  # Spending money in the city
        self.report(
            {
                "city_visited": {
                    "name": here.name,
                    "population": here.population,
                    "tourism_score": here.tourism_score,
                    "money_spent": 50.0,
                }
            }
        )

        # Note: Edge traversal is now automatic when moving between connected nodes
        # No need to manually handle edge traversal

    @on_visit(Highway)  # Tourist using highway transportation
    async def travel_highway(self, here):
        travel_cost = (
            here.toll_cost
            + (here.distance_km if hasattr(here, "distance_km") else 0) * 0.1
        )
        self.budget -= travel_cost
        self.report(
            {
                "transportation_used": {
                    "type": "Highway",
                    "name": here.name,
                    "cost": travel_cost,
                    "lanes": here.lanes,
                }
            }
        )


class LogisticsWalker(Walker):
    """Logistics walker managing cargo and supply chains"""

    cargo_capacity: float = 25000.0
    current_cargo: float = 0.0

    @on_visit(Warehouse, Port)  # Multi-target - both warehouses and ports
    async def handle_logistics_facility(self, here):
        facility_type = here.__class__.__name__

        if facility_type == "Warehouse":
            # Load/unload at warehouse
            available_space = here.capacity - here.current_stock
            load_amount = min(available_space, self.cargo_capacity - self.current_cargo)
            self.current_cargo += load_amount
            here.current_stock += load_amount

        elif facility_type == "Port":
            # International shipping operations
            if here.has_customs:
                self.report({"customs_clearance": here.name})

        self.report(
            {
                "facility_visited": {
                    "name": here.name,
                    "type": facility_type,
                    "capacity": getattr(
                        here, "capacity", getattr(here, "cargo_capacity", 0)
                    ),
                    "cargo_loaded": getattr(self, "current_cargo", 0),
                }
            }
        )

        # Note: Transportation edges are traversed automatically when moving between facilities
        # Edge hooks will be triggered transparently during traversal

    @on_visit(ShippingRoute, Railroad, Highway)  # Multi-target transportation
    async def use_transportation(self, here):
        transport_type = here.__class__.__name__
        cost = 0.0

        if transport_type == "ShippingRoute":
            cost = here.distance_km * 2.0  # $2 per km for shipping
        elif transport_type == "Railroad":
            cost = (
                500.0 if here.electrified else 300.0
            )  # Fixed cost based on electrification
        elif transport_type == "Highway":
            cost = here.toll_cost + 100.0  # Toll plus fuel

        self.report(
            {
                "transportation_used": {
                    "type": transport_type,
                    "name": here.name,
                    "cost": cost,
                    "cargo_weight": self.current_cargo,
                }
            }
        )


class InspectionWalker(Walker):
    """Safety inspector checking all types of facilities and routes"""

    inspection_count: int = 0
    violations_found: int = 0

    @on_visit()  # Catch-all - inspects ANY node type
    async def inspect_facility(self, here):
        self.inspection_count += 1
        facility_type = here.__class__.__name__

        # Simulate inspection with different violation rates by type
        violation_rates = {"City": 0.1, "Warehouse": 0.15, "Port": 0.2}
        import random

        has_violation = random.random() < violation_rates.get(facility_type, 0.05)

        if has_violation:
            self.violations_found += 1

        self.report(
            {
                "facility_inspection": {
                    "facility": here.name,
                    "type": facility_type,
                    "violation": has_violation,
                    "inspection_id": f"INS-{self.inspection_count:04d}",
                }
            }
        )

        # Note: Connected routes are inspected automatically during traversal
        # Edge inspection hooks will be triggered transparently

    @on_visit()  # Catch-all - inspects ANY edge type
    async def inspect_route(self, here):
        if isinstance(here, Edge):  # Only process actual edges
            route_type = here.__class__.__name__

            # Different safety standards for different route types
            safety_scores = {"Highway": 85, "Railroad": 92, "ShippingRoute": 78}
            safety_score = safety_scores.get(route_type, 70)

            self.report(
                {
                    "route_inspection": {
                        "route": here.name,
                        "type": route_type,
                        "safety_score": safety_score,
                        "status": "PASS" if safety_score >= 80 else "NEEDS_IMPROVEMENT",
                    }
                }
            )


# =============================================================================
# SMART FACILITIES (Nodes with Walker-specific responses)
# =============================================================================


class SmartCity(City):
    """Smart city that responds differently to different walker types"""

    @on_visit(TouristWalker)
    async def welcome_tourist(self, visitor):
        # Offer tourist discounts and recommendations
        visitor.report(
            {
                "special_offer": {
                    "city": self.name,
                    "offer": "20% discount at local attractions",
                    "bonus_points": self.tourism_score * 10,
                }
            }
        )

        # Smart city provides optimal route recommendations
        if hasattr(visitor, "budget") and visitor.budget < 200:
            visitor.report(
                f"Low budget warning in {self.name} - consider budget accommodations"
            )

    @on_visit(InspectionWalker)
    async def prepare_for_inspection(self, visitor):
        # Smart city auto-reports compliance metrics
        visitor.report(
            {
                "auto_report": {
                    "city": self.name,
                    "compliance_score": 95,
                    "last_inspection": "2024-01-15",
                    "status": "EXCELLENT",
                }
            }
        )


class SmartWarehouse(Warehouse):
    """Smart warehouse with automated systems"""

    @on_visit(LogisticsWalker, InspectionWalker)  # Multi-target response
    async def handle_authorized_visitor(self, visitor):
        visitor_type = visitor.__class__.__name__

        if visitor_type == "LogisticsWalker":
            # Provide real-time inventory data
            visitor.report(
                {
                    "inventory_data": {
                        "warehouse": self.name,
                        "current_stock": self.current_stock,
                        "available_capacity": self.capacity - self.current_stock,
                        "optimal_load": min(
                            visitor.cargo_capacity, self.capacity - self.current_stock
                        ),
                    }
                }
            )

        elif visitor_type == "InspectionWalker":
            # Provide automated compliance reports
            visitor.report(
                {
                    "automated_compliance": {
                        "warehouse": self.name,
                        "safety_systems": "ACTIVE",
                        "temperature_controlled": True,
                        "last_maintenance": "2024-02-01",
                    }
                }
            )


# =============================================================================
# SMART TRANSPORTATION (Edges with Walker-specific responses)
# =============================================================================


class SmartHighway(Highway):
    """Smart highway with dynamic tolling and traffic management"""

    @on_visit(LogisticsWalker)
    async def handle_commercial_traffic(self, visitor):
        # Commercial vehicles get different rates and priority lanes
        visitor.report(
            {
                "highway_service": {
                    "highway": self.name,
                    "commercial_rate": self.toll_cost
                    * 0.8,  # 20% discount for logistics
                    "priority_lane_access": True,
                    "estimated_time": (
                        f"{self.distance_km / (self.speed_limit * 0.9):.1f} hours"
                        if hasattr(self, "distance_km")
                        else "N/A"
                    ),
                }
            }
        )

    @on_visit(TouristWalker)
    async def handle_tourist_traffic(self, visitor):
        # Tourists get scenic route information
        visitor.report(
            {
                "scenic_info": {
                    "highway": self.name,
                    "scenic_rating": 8,
                    "rest_stops": 3,
                    "tourist_rate": self.toll_cost
                    * 1.1,  # Small premium for scenic routes
                }
            }
        )


# =============================================================================
# DEMO EXECUTION
# =============================================================================


async def create_demo_network():
    """Create a demo transportation network"""
    print("🏗️  Creating demo transportation network...")

    # Create cities (mix of regular and smart cities)
    new_york = await SmartCity.create(
        name="New York", population=8400000, tourism_score=9
    )
    chicago = await City.create(name="Chicago", population=2700000, tourism_score=7)
    los_angeles = await SmartCity.create(
        name="Los Angeles", population=4000000, tourism_score=8
    )

    # Create logistics facilities
    chicago_warehouse = await SmartWarehouse.create(
        name="Chicago Distribution Center", capacity=5000, current_stock=2000
    )
    la_port = await Port.create(
        name="Port of Los Angeles", cargo_capacity=100000, has_customs=True
    )

    # Create transportation network
    ny_chicago_highway = await SmartHighway.create(
        left=new_york,
        right=chicago,
        name="I-80",
        lanes=6,
        speed_limit=75,
        toll_cost=25.0,
    )

    chicago_warehouse_road = await Highway.create(
        left=chicago,
        right=chicago_warehouse,
        name="Industrial Parkway",
        lanes=4,
        speed_limit=45,
        toll_cost=5.0,
    )

    chicago_la_railroad = await Railroad.create(
        left=chicago,
        right=los_angeles,
        name="Southwest Chief",
        tracks=2,
        electrified=False,
    )

    la_port_road = await Highway.create(
        left=los_angeles,
        right=la_port,
        name="Harbor Freeway",
        lanes=8,
        speed_limit=55,
        toll_cost=0.0,
    )

    return {
        "cities": [new_york, chicago, los_angeles],
        "facilities": [chicago_warehouse, la_port],
        "routes": [
            ny_chicago_highway,
            chicago_warehouse_road,
            chicago_la_railroad,
            la_port_road,
        ],
    }


async def run_walker_demo(walker, start_location, walker_name):
    """Run a walker demo and display results"""
    print(f"\n🚶 Running {walker_name} Demo")
    print("=" * 50)

    await walker.spawn(start=start_location)

    print(f"📊 {walker_name} Results:")
    report = walker.get_report()

    # Group report items by type
    report_types = {}
    for item in report:
        if isinstance(item, dict):
            for key in item.keys():
                if key not in report_types:
                    report_types[key] = []
                report_types[key].append(item[key])
        elif isinstance(item, str):
            if "messages" not in report_types:
                report_types["messages"] = []
            report_types["messages"].append(item)

    # Display grouped results
    for key, values in report_types.items():
        print(f"  {key.replace('_', ' ').title()}: {len(values)} items")
        for item in values[:3]:  # Show first 3 items
            if isinstance(item, dict):
                print(f"    • {item}")
            else:
                print(f"    • {item}")
        if len(values) > 3:
            print(f"    ... and {len(values) - 3} more items")

    print(f"  Total Report Items: {len(report)}")
    return walker


async def main():
    """Main demo function"""
    print("🌟 Enhanced @on_visit Decorator Demo")
    print("=====================================")
    print()
    print("This demo showcases:")
    print("• Multi-target hooks: @on_visit(TypeA, TypeB)")
    print("• Catch-all hooks: @on_visit()")
    print("• Edge traversal and processing")
    print("• Nodes/Edges responding to specific Walker types")
    print()

    # Create the demo network
    network = await create_demo_network()

    # Demo 1: Tourist Walker (single target + edge hooks)
    tourist = TouristWalker(budget=1000.0)
    await run_walker_demo(tourist, network["cities"][0], "Tourist Walker")

    # Demo 2: Logistics Walker (multi-target nodes + multi-target edges)
    logistics = LogisticsWalker(cargo_capacity=25000.0)
    await run_walker_demo(logistics, network["facilities"][0], "Logistics Walker")

    # Demo 3: Inspection Walker (catch-all for everything)
    inspector = InspectionWalker()
    await run_walker_demo(inspector, network["cities"][1], "Inspection Walker")

    print("\n✅ Demo completed!")
    print("\nKey Features Demonstrated:")
    print("• Multi-target hooks allow one function to handle multiple types")
    print("• Catch-all hooks with @on_visit() process any node/edge type")
    print("• Edge traversal enables rich transportation modeling")
    print("• Smart facilities respond differently to different walker types")
    print("• Type validation prevents incorrect hook targeting")


if __name__ == "__main__":
    asyncio.run(main())
