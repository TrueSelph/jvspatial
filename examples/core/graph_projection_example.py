"""Dummy supply-chain graph demonstrating evidence for model inference.

Run from an installed checkout with ``python -m examples.core.graph_projection_example``.
All nodes belong to an application root. No model provider or credentials are used.
"""

import asyncio
import tempfile

from jvspatial import (
    Edge,
    GraphContext,
    Node,
    ProjectionRequest,
    ProjectionScope,
    ProjectionSemantics,
    Root,
)
from jvspatial.core.context import scoped_default_context_async
from jvspatial.db.jsondb import JsonDB


class DemoApp(Node):
    name: str = "Supply chain demo"
    workspace: str = "demo"


class Category(Node):
    name: str = ""
    workspace: str = "demo"


class Project(Node):
    name: str = ""
    status: str = "active"
    workspace: str = "demo"


class Component(Node):
    name: str = ""
    status: str = "qualified"
    workspace: str = "demo"


class Supplier(Node):
    name: str = ""
    availability: str = "available"
    visibility: str = "public"
    private_contact: str = "synthetic confidential contact"
    workspace: str = "demo"


class Region(Node):
    name: str = ""
    disruption: str = "none"
    workspace: str = "demo"


class Contains(Edge):
    pass


class DependsOn(Edge):
    criticality: str = "required"


class SuppliedBy(Edge):
    pass


class LocatedIn(Edge):
    pass


class AlternativeTo(Edge):
    qualification: str = "unverified"


async def seed_demo(context):
    """Create shared dependencies, a cycle, an alternative, and a private branch."""
    async with scoped_default_context_async(context):
        root = await Root.get()
        app = await DemoApp.create()
        await root.connect(app, edge=Contains, direction="out")
        categories = {}
        for name in ("projects", "components", "suppliers", "regions"):
            categories[name] = await Category.create(name=name)
            await app.connect(categories[name], edge=Contains, direction="out")
        objects = {}
        for key, cls, branch, attrs in (
            ("harbor", Project, "projects", {"name": "Harbor water system"}),
            ("clinic", Project, "projects", {"name": "Clinic backup system"}),
            ("controller", Component, "components", {"name": "Control board"}),
            ("pump", Component, "components", {"name": "Pump"}),
            ("firmware", Component, "components", {"name": "Firmware"}),
            (
                "alternate",
                Component,
                "components",
                {"name": "Alternative board", "status": "unverified"},
            ),
            (
                "coastal",
                Supplier,
                "suppliers",
                {"name": "Coastal Parts", "availability": "delayed"},
            ),
            ("inland", Supplier, "suppliers", {"name": "Inland Parts"}),
            (
                "confidential",
                Supplier,
                "suppliers",
                {"name": "Private Lab", "visibility": "private"},
            ),
            (
                "floodplain",
                Region,
                "regions",
                {"name": "Floodplain", "disruption": "flood warning"},
            ),
            ("interior", Region, "regions", {"name": "Interior"}),
            (
                "restricted",
                Region,
                "regions",
                {"name": "Restricted region", "disruption": "private disruption"},
            ),
        ):
            objects[key] = await cls.create(**attrs)
            await categories[branch].connect(
                objects[key], edge=Contains, direction="out"
            )
        links = {}
        for key, source, target, edge, direction in (
            ("harbor_controller", "harbor", "controller", DependsOn, "out"),
            ("harbor_pump", "harbor", "pump", DependsOn, "out"),
            ("clinic_controller", "clinic", "controller", DependsOn, "out"),
            ("controller_firmware", "controller", "firmware", DependsOn, "out"),
            ("firmware_controller", "firmware", "controller", DependsOn, "out"),
            ("controller_supplier", "controller", "coastal", SuppliedBy, "out"),
            ("pump_supplier", "pump", "coastal", SuppliedBy, "out"),
            ("coastal_region", "coastal", "floodplain", LocatedIn, "out"),
            ("alternate_supplier", "alternate", "inland", SuppliedBy, "out"),
            ("inland_region", "inland", "interior", LocatedIn, "out"),
            ("alternate", "controller", "alternate", AlternativeTo, "both"),
            ("private_supplier", "controller", "confidential", SuppliedBy, "out"),
            ("private_region", "confidential", "restricted", LocatedIn, "out"),
        ):
            links[key] = await objects[source].connect(
                objects[target], edge=edge, direction=direction
            )
        return {"root": root, "app": app, **categories, **objects}, links


class PublicDemoAccess:
    """Example host policy: deny private suppliers and confidential contact fields."""

    async def authorize(self, kind, records):
        fields = (
            ("name", "status", "availability", "disruption")
            if kind == "node"
            else ("criticality", "qualification")
        )
        return {
            row["id"]: fields
            for row in records
            if row.get("context", {}).get("visibility") != "private"
        }


DEMO_SEMANTICS = ProjectionSemantics(
    node_types={
        "Project": "An active project requiring components.",
        "Component": "A component or firmware used by a project.",
        "Supplier": "A supplier's recorded availability; not a delivery guarantee.",
        "Region": "A geographic region with a recorded disruption indicator.",
    },
    edge_types={
        "DependsOn": "Source requires target; dependency alone does not prove impact.",
        "SuppliedBy": "Source component is supplied by target supplier.",
        "LocatedIn": "Source supplier is located in target region.",
        "AlternativeTo": "An unverified candidate alternative; interchangeability is not established.",
        "Contains": "Application-declared organizational containment.",
    },
    label_fields={
        kind: "name"
        for kind in (
            "Project",
            "Component",
            "Supplier",
            "Region",
            "Category",
            "DemoApp",
        )
    },
)


def demo_scope():
    """Define workspace membership and allowlisted attributes at the host boundary."""
    return ProjectionScope(
        name="public supply-chain demo",
        node_query={"context.workspace": "demo"},
        node_fields=("name", "status", "availability", "disruption"),
        edge_fields=("criticality", "qualification"),
    )


async def main():
    """Print an ontology capture and its host-only work measurements."""
    with tempfile.TemporaryDirectory() as directory:
        context = GraphContext(JsonDB(base_path=directory))
        objects, _ = await seed_demo(context)
        result = await context.project_graph(
            ProjectionRequest(
                root_id=objects["harbor"].id,
                view="ontology",
                max_depth=4,
                edge_types=("DependsOn", "SuppliedBy", "LocatedIn", "AlternativeTo"),
                max_bytes=65536,
            ),
            scope=demo_scope(),
            access=PublicDemoAccess(),
            semantics=DEMO_SEMANTICS,
        )
        print(result.render_text())
        print("Host diagnostics:", result.statistics)


if __name__ == "__main__":
    asyncio.run(main())
