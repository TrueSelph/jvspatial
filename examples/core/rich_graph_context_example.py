"""Rooted operational facts with declared meanings and recorded evidence.

Run ``python -m examples.core.rich_graph_context_example``. All data is synthetic;
capturing and rendering do not call a model or certify operational readiness.
"""

import asyncio
import tempfile
from typing import ClassVar

from jvspatial import (
    Edge,
    GraphContext,
    Node,
    ProjectionContextConfig,
    ProjectionEvidence,
    ProjectionField,
    ProjectionRelation,
    ProjectionRequest,
    ProjectionScope,
    ProjectionSemantics,
    Root,
)
from jvspatial.core.context import scoped_default_context_async
from jvspatial.db.jsondb import JsonDB


class RichDemoApp(Node):
    workspace: str = "demo"


class ForeignDemoApp(Node):
    workspace: str = "foreign"


class OperationalRecord(Node):
    __entity_name__: ClassVar[str] = "RichDemoRecord"
    workspace: str = "demo"
    name: str = ""
    state: str = "unverified"
    due: str = "2026-12-01"
    source: str = ""
    observed: str = ""
    verified: str = "unverified"
    amount: int = 0
    visibility: str = "public"


class RecordedRelation(Edge):
    __entity_name__: ClassVar[str] = "RichDemoRelation"
    role: str = "contains"
    schema_revision: str = "operations-v1"


NODE_FIELDS = ("name", "state", "due", "source", "observed", "verified", "amount")
EDGE_FIELDS = ("role", "schema_revision")
PROFILE = ProjectionContextConfig(
    profile_id="recorded-operations",
    revision="1",
    node_fields={
        "RichDemoRecord": tuple(
            ProjectionField(
                path=path,
                unit="items" if path == "amount" else None,
                evidence=(
                    ProjectionEvidence(
                        source_path="source",
                        observed_at_path="observed",
                        verification_path="verified",
                    )
                    if path == "state"
                    else None
                ),
            )
            for path in NODE_FIELDS
        )
    },
    edge_fields={
        "RichDemoRelation": tuple(ProjectionField(path=path) for path in EDGE_FIELDS)
    },
)
SEMANTICS = ProjectionSemantics(
    label_fields={"RichDemoRecord": "name"},
    relation_rules=tuple(
        ProjectionRelation(
            id=f"operations-v1/{role}",
            edge_type="RichDemoRelation",
            description=description,
            direction=direction,
            inverse=inverse,
            edge_filter={
                "context.role": role,
                "context.schema_revision": "operations-v1",
            },
        )
        for role, description, direction, inverse in (
            (
                "requires",
                "Source requires the recorded target; readiness is not inferred.",
                "requires",
                "required by",
            ),
            (
                "mitigated_by",
                "Target is a proposed mitigation for this source only.",
                "has proposed mitigation",
                "proposed mitigation for",
            ),
            (
                "alternative",
                "Target is an unverified alternative, not an equivalent replacement.",
                "has candidate alternative",
                "candidate alternative to",
            ),
        )
    ),
)


class DemoAccess:
    async def authorize(self, kind, records):
        return {
            row["id"]: NODE_FIELDS if kind == "node" else EDGE_FIELDS
            for row in records
            if row.get("context", {}).get("visibility") != "private"
        }


async def seed_demo(context):
    """Seed two prerequisites, a mitigation, conflicting observations and denials."""
    async with scoped_default_context_async(context):
        root = await Root.get()
        app = await RichDemoApp.create()
        foreign_app = await ForeignDemoApp.create()
        await root.connect(app, edge=RecordedRelation, direction="out")
        await root.connect(foreign_app, edge=RecordedRelation, direction="out")
        records = {}
        for key, attrs in (
            ("project", {"name": "Harbor launch", "state": "active"}),
            (
                "supply",
                {
                    "name": "Recorded supply commitment",
                    "state": "confirmed",
                    "source": "synthetic/current-report",
                    "observed": "2026-10-11",
                    "verified": "recorded-confirmation",
                    "amount": 40,
                },
            ),
            ("test", {"name": "Validation prerequisite", "state": "pending"}),
            ("mitigation", {"name": "Supply backup proposal", "state": "proposed"}),
            ("alternative", {"name": "Unverified alternative"}),
            (
                "stale",
                {
                    "name": "Conflicting older supply observation",
                    "state": "unavailable",
                    "source": "synthetic/older-report",
                    "observed": "2020-01-01",
                    "amount": 0,
                },
            ),
            ("private", {"name": "Denied record", "visibility": "private"}),
            ("hidden", {"name": "Denied intermediary descendant"}),
            ("foreign", {"name": "Other partition record", "workspace": "foreign"}),
        ):
            records[key] = await OperationalRecord.create(**attrs)
            parent = (
                foreign_app
                if key == "foreign"
                else records["private"] if key == "hidden" else app
            )
            await parent.connect(records[key], edge=RecordedRelation, direction="out")
        for source, target, role in (
            ("project", "supply", "requires"),
            ("project", "test", "requires"),
            ("supply", "mitigation", "mitigated_by"),
            ("supply", "alternative", "alternative"),
            ("supply", "stale", "alternative"),
            ("test", "supply", "requires"),
            ("supply", "test", "requires"),
            ("project", "private", "requires"),
            ("project", "foreign", "requires"),
        ):
            await records[source].connect(
                records[target], edge=RecordedRelation, direction="out", role=role
            )
        return records


def demo_scope():
    return ProjectionScope(
        name="recorded operations",
        node_query={"context.workspace": "demo"},
        node_fields=NODE_FIELDS,
        edge_fields=EDGE_FIELDS,
    )


async def capture_demo(
    context, records, *, view="ontology", execution_mode="compatibility"
):
    return await context.project_graph(
        ProjectionRequest(
            root_id=records["project"].id,
            view=view,
            max_depth=3,
            max_bytes=65536,
            execution_mode=execution_mode,
        ),
        scope=demo_scope(),
        access=DemoAccess(),
        semantics=SEMANTICS,
        context_config=PROFILE,
    )


async def main():
    with tempfile.TemporaryDirectory() as directory:
        context = GraphContext(JsonDB(directory))
        records = await seed_demo(context)
        result = await capture_demo(context, records)
        print(result.render_text())
        print("Host diagnostics:", result.statistics)


if __name__ == "__main__":
    asyncio.run(main())
