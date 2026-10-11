"""Rich capture contracts, independently checked against authorized facts."""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

from jvspatial import (
    GraphContext,
    ProjectionContextConfig,
    ProjectionEvidence,
    ProjectionField,
    ProjectionRelation,
    ProjectionRequest,
    ProjectionScope,
    ProjectionSemantics,
)
from jvspatial.db.jsondb import JsonDB

FIELDS = (
    "name",
    "state",
    "due",
    "source",
    "observed",
    "revision",
    "verified",
    "confidence",
    "risk.level",
    "zero",
    "false",
    "empty",
    "missing",
    "schema",
)
EDGE_FIELDS = ("role", "schema", "revision")


def config(**changes):
    values = dict(
        profile_id="operational",
        revision="1",
        node_fields={
            "Record": (
                ProjectionField(path="name"),
                ProjectionField(
                    path="state",
                    description="Recorded state",
                    evidence=ProjectionEvidence(
                        source_path="source",
                        observed_at_path="observed",
                        verification_path="verified",
                        revision_path="revision",
                        confidence_path="confidence",
                    ),
                ),
                *(
                    ProjectionField(path=path)
                    for path in FIELDS
                    if path not in ("name", "state")
                ),
            )
        },
        edge_fields={
            "Relation": tuple(ProjectionField(path=path) for path in EDGE_FIELDS)
        },
    )
    values.update(changes)
    return ProjectionContextConfig(**values)


def semantics(*extra):
    return ProjectionSemantics(
        edge_types={"Relation": "Recorded association."},
        relation_rules=(
            ProjectionRelation(
                id="requires-v1",
                edge_type="Relation",
                description="Source requires target",
                direction="requires",
                inverse="required by",
                edge_filter={
                    "context.role": "requires",
                    "context.schema": "workflow-v1",
                },
            ),
            ProjectionRelation(
                id="mitigates-v1",
                edge_type="Relation",
                description="Target records a mitigation",
                direction="has mitigation",
                edge_filter={
                    "context.role": "mitigates",
                    "context.schema": "workflow-v1",
                },
            ),
            *extra,
        ),
    )


@pytest_asyncio.fixture(
    loop_scope="function", params=["json", "sqlite", "postgres", "mongodb"]
)
async def graph(tmp_path, request):
    cleanup = None
    if request.param == "json":
        db = JsonDB(str(tmp_path))
    elif request.param == "sqlite":
        from jvspatial.db.sqlite import SQLiteDB

        db = SQLiteDB(str(tmp_path / "rich.db"))
    elif request.param == "postgres":
        dsn = os.getenv("JVSPATIAL_PROJECTION_TEST_DSN")
        if not dsn:
            pytest.skip("disposable PostgreSQL DSN unavailable")
        import asyncpg

        from jvspatial.db.postgres import PostgresDB

        admin = await asyncpg.connect(dsn)
        schema = "rich_" + uuid.uuid4().hex
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        db = PostgresDB(dsn=dsn, schema_name=schema)

        async def cleanup():
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()

    else:
        uri = os.getenv("JVSPATIAL_PROJECTION_MONGO_URI")
        if not uri:
            pytest.skip("disposable MongoDB URI unavailable")
        from jvspatial.db.mongodb import MongoDB

        db = MongoDB(uri=uri, db_name="rich_" + uuid.uuid4().hex)

        async def cleanup():
            await db._client.drop_database(db.db_name)

    context = GraphContext(db)
    nodes = [
        ("n.Root.root", "Root", {}),
        ("n.App.demo", "App", {"workspace": "demo"}),
        (
            "n.Record.project",
            "Record",
            {
                "name": "Harbor",
                "state": "active",
                "due": "2026-12-01",
                "workspace": "demo",
                "risk": {"level": None, "secret": "secret-sibling"},
                "zero": 0,
                "false": False,
                "empty": "",
            },
        ),
        (
            "n.Record.a",
            "Record",
            {
                "name": "Permit",
                "state": "unverified",
                "source": "opaque-source",
                "observed": "2020-01-01",
                "revision": "r1",
                "verified": "unverified",
                "confidence": 0,
                "workspace": "demo",
            },
        ),
        (
            "n.Record.b",
            "Record",
            {"name": "Procurement", "state": "complete", "workspace": "demo"},
        ),
        (
            "n.Record.mitigation",
            "Record",
            {"name": "Recorded mitigation", "state": "proposed", "workspace": "demo"},
        ),
        (
            "n.Record.alternative",
            "Record",
            {"name": "Unverified alternative", "workspace": "demo"},
        ),
        ("n.Record.private", "Record", {"name": "secret-node", "workspace": "demo"}),
        (
            "n.Record.hidden",
            "Record",
            {"name": "secret-intermediate-descendant", "workspace": "demo"},
        ),
        ("n.App.foreign", "App", {"workspace": "foreign"}),
        (
            "n.Record.foreign",
            "Record",
            {"name": "foreign-secret", "workspace": "foreign"},
        ),
    ]
    for nid, entity, attrs in nodes:
        await context.database.save(
            "node", {"id": nid, "entity": entity, "context": attrs}
        )
    links = [
        ("root-app", "n.Root.root", "n.App.demo", "contains"),
        ("root-foreign", "n.Root.root", "n.App.foreign", "contains"),
        ("foreign-record", "n.App.foreign", "n.Record.foreign", "contains"),
        ("app-project", "n.App.demo", "n.Record.project", "contains"),
    ]
    links += [
        (name, "n.Record.project", target, role)
        for name, target, role in [
            ("a", "n.Record.a", "requires"),
            ("b", "n.Record.b", "requires"),
            ("mitigation", "n.Record.mitigation", "mitigates"),
            ("alternative", "n.Record.alternative", "alternative"),
            ("private", "n.Record.private", "requires"),
            ("foreign", "n.Record.foreign", "requires"),
        ]
    ]
    links += [
        ("hidden", "n.Record.private", "n.Record.hidden", "requires"),
        ("cycle", "n.Record.a", "n.Record.project", "requires"),
        ("shared", "n.Record.b", "n.Record.a", "requires"),
    ]
    for name, source, target, role in links:
        await context.database.save(
            "edge",
            {
                "id": "e.Relation." + name,
                "entity": "Relation",
                "source": source,
                "target": target,
                "bidirectional": False,
                "context": {"role": role, "schema": "workflow-v1", "revision": "1"},
            },
        )
    try:
        yield context
    finally:
        if request.param == "mongodb":
            await cleanup()
        if hasattr(db, "close"):
            await db.close()
        if request.param == "postgres":
            await cleanup()


class Policy:
    def __init__(self, denied=(), fields=()):
        self.denied, self.fields = denied, fields

    async def authorize(self, kind, records):
        return {
            r["id"]: tuple(
                f
                for f in (FIELDS if kind == "node" else EDGE_FIELDS)
                if f not in self.fields
            )
            for r in records
            if r["id"] not in ("n.Record.private", *self.denied)
        }


async def capture(graph, **changes):
    return await graph.project_graph(
        changes.pop(
            "request",
            ProjectionRequest(
                root_id="n.Record.project",
                max_depth=3,
                view="ontology",
                max_bytes=65536,
            ),
        ),
        scope=changes.pop(
            "scope",
            ProjectionScope(
                name="demo",
                node_query={"context.workspace": "demo"},
                node_fields=FIELDS,
                edge_fields=EDGE_FIELDS,
            ),
        ),
        access=changes.pop("access", Policy()),
        semantics=changes.pop("semantics", semantics()),
        context_config=changes.pop("context_config", config()),
        **changes,
    )


@pytest.mark.parametrize("view", ["relationships", "hierarchy", "ontology"])
async def test_rich_facts_meanings_and_closed_graph(graph, view):
    result = await capture(
        graph,
        request=ProjectionRequest(
            root_id="n.Record.project", view=view, max_depth=3, max_bytes=65536
        ),
    )
    data = result.to_dict()
    assert data["format_version"] == 2
    nodes = {n["id"]: n for n in data["nodes"]}
    assert set(nodes) == {
        "n.Record.project",
        "n.Record.a",
        "n.Record.b",
        "n.Record.mitigation",
        "n.Record.alternative",
    }
    project = nodes["n.Record.project"]
    assert project["fields"]["risk.level"]["state"] == "null"
    assert project["fields"]["missing"]["state"] == "missing"
    assert (
        project["context"]["zero"] == 0
        and project["context"]["false"] is False
        and project["context"]["empty"] == ""
    )
    evidence = nodes["n.Record.a"]["fields"]["state"]["evidence"]
    assert (
        evidence["source"] == "opaque-source"
        and evidence["observed_at"] == "2020-01-01"
    )
    assert evidence["confidence"] == 0 and evidence["value_class"] == "recorded"
    assert data["coverage"]["decision_sufficiency"] == "not_assessed"
    for edge in data["edges"]:
        assert edge["source"] in nodes and edge["target"] in nodes
    assert set(data["relation_definitions"]) == {"requires-v1", "mitigates-v1"}
    assert "application_declared" in result.render_text()
    assert all(
        secret not in result.render_text()
        for secret in (
            "secret-sibling",
            "secret-node",
            "foreign-secret",
            "secret-intermediate-descendant",
        )
    )


@pytest.mark.parametrize("field", ["role", "schema", "source", "observed", "state"])
async def test_denied_or_omitted_inputs_are_not_evidence(graph, field):
    result = await capture(graph, access=Policy(fields=(field,)))
    text = result.render_text()
    if field in EDGE_FIELDS:
        assert result.to_dict()["relation_definitions"] == {}
        assert "requires-v1" not in text
    else:
        for node in result.to_dict()["nodes"]:
            assert field not in node["fields"]
        assert "opaque-source" not in text if field == "source" else True


async def test_explicit_empty_fields_and_ambiguous_rules(graph):
    result = await capture(
        graph,
        request=ProjectionRequest(
            root_id="n.Record.project", node_fields=(), edge_fields=(), max_bytes=65536
        ),
    )
    assert all(
        n["context"] == {} and n["fields"] == {} for n in result.to_dict()["nodes"]
    )
    assert result.to_dict()["relation_definitions"] == {}
    extra = ProjectionRelation(
        id="conflict",
        edge_type="Relation",
        description="Conflicting declaration",
        direction="may require",
        edge_filter={"context.role": "requires", "context.schema": "workflow-v1"},
    )
    result = await capture(graph, semantics=semantics(extra))
    assert any(
        e["relation"]["status"] == "ambiguous" for e in result.to_dict()["edges"]
    )


@pytest.mark.parametrize("budget", [4096, 8192, 16000])
async def test_metadata_fits_exact_bytes_and_definitions_are_closed(graph, budget):
    result = await capture(
        graph,
        request=ProjectionRequest(
            root_id="n.Record.project", max_depth=3, max_bytes=budget
        ),
    )
    data = result.to_dict()
    assert (
        len(
            json.dumps(
                data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        <= budget
    )
    referenced = {rid for e in data["edges"] for rid in e["relation"]["definition_ids"]}
    assert referenced == set(data["relation_definitions"])
    ids = {n["id"] for n in data["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in data["edges"])
    assert all(set(p["nodes"]).issubset(ids) for p in data["paths"].values())
    assert result.statistics["payload_bytes"] == len(result._payload.encode())
    assert result._payload == json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


async def test_scope_rejects_unapproved_configuration_before_reads(graph):
    graph.database.graph_node_batch = lambda *_: pytest.fail("must reject before reads")
    with pytest.raises(ValueError, match="scope"):
        await capture(
            graph,
            context_config=config(
                node_fields={"Record": (ProjectionField(path="secret"),)}
            ),
        )


@pytest.mark.parametrize(
    "path", ["*", "risk.*", "risk..level", "context.$where", "a.", "a" * 129]
)
def test_invalid_paths_are_rejected(path):
    with pytest.raises(ValueError):
        ProjectionField(path=path)
    with pytest.raises(ValueError):
        ProjectionEvidence(source_path=path)


def test_bounded_declarations_and_unknown_inputs():
    with pytest.raises(ValueError):
        config(
            node_fields={
                "Record": (ProjectionField(path="name"), ProjectionField(path="name"))
            }
        )
    with pytest.raises(ValueError):
        ProjectionField(path="name", surprise=True)
    with pytest.raises(ValueError):
        ProjectionField(path="name", max_string=0)
    with pytest.raises(ValueError):
        ProjectionRelation(
            id="bad",
            edge_type="Relation",
            description="",
            direction="x",
            edge_filter={"context.role": {"$where": "execute"}},
        )
    with pytest.raises(ValueError):
        semantics(semantics().relation_rules[0])


async def test_clipped_selectors_and_evidence_remain_unresolved(graph):
    profile = config(
        edge_fields={
            "Relation": (
                ProjectionField(path="role", max_string=1),
                ProjectionField(path="schema"),
            )
        },
        node_fields={
            "Record": (
                ProjectionField(
                    path="state", evidence=ProjectionEvidence(source_path="source")
                ),
                ProjectionField(path="source", max_string=2),
            )
        },
    )
    result = await capture(graph, context_config=profile)
    assert result.to_dict()["relation_definitions"] == {}
    node = next(n for n in result.to_dict()["nodes"] if n["id"] == "n.Record.a")
    assert node["fields"]["source"]["state"] == "truncated"
    assert node["fields"]["state"]["evidence"] == {
        "status": "unresolved",
        "value_class": "recorded",
    }
    assert not result.to_dict()["meta"]["detail_complete"]


async def test_endpoint_selectors_only_use_authorized_captured_fields(graph):
    rule = ProjectionRelation(
        id="endpoint",
        edge_type="Relation",
        description="Target's recorded condition",
        direction="requires",
        target_filter={"context.state": "unverified"},
    )
    result = await capture(graph, semantics=ProjectionSemantics(relation_rules=(rule,)))
    assert "endpoint" in result.to_dict()["relation_definitions"]
    result = await capture(
        graph,
        access=Policy(fields=("state",)),
        semantics=ProjectionSemantics(relation_rules=(rule,)),
    )
    assert result.to_dict()["relation_definitions"] == {}
    result = await capture(
        graph,
        request=ProjectionRequest(root_id="n.Record.project", node_fields=("name",)),
        semantics=ProjectionSemantics(relation_rules=(rule,)),
    )
    assert result.to_dict()["relation_definitions"] == {}


async def test_revocation_and_input_mutation_do_not_reuse_capture_authority(graph):
    profile = config()
    old = await capture(graph, context_config=profile)
    new = await capture(graph, access=Policy(denied=("n.Record.a",)))
    assert "n.Record.a" not in {n["id"] for n in new.to_dict()["nodes"]}
    assert "n.Record.a" in {n["id"] for n in old.to_dict()["nodes"]}
    original = graph.database.graph_node_batch

    async def mutate(ids):
        profile.node_fields.clear()
        return await original(ids)

    graph.database.graph_node_batch = mutate
    result = await capture(graph, context_config=profile)
    assert result.to_dict()["format_version"] == 2
    assert "state" in result.to_dict()["nodes"][0]["fields"]


async def test_same_record_enrichment_adds_no_database_operations(graph):
    request = ProjectionRequest(
        root_id="n.Record.project", max_depth=3, max_bytes=1000000
    )
    plain = await capture(
        graph, request=request, context_config=None, semantics=ProjectionSemantics()
    )
    rich = await capture(graph, request=request)
    assert (
        rich.statistics["database_operations"]
        == plain.statistics["database_operations"]
    )
    assert rich.statistics["candidate_records"] == plain.statistics["candidate_records"]


async def test_type_profile_empty_defaults_and_request_intersection(graph):
    profile = config(node_fields={"Record": ()})
    result = await capture(graph, context_config=profile)
    assert all(
        n["fields"] == {} and n["context"] == {} for n in result.to_dict()["nodes"]
    )
    result = await capture(
        graph,
        context_config=config(node_fields={"Other": (ProjectionField(path="name"),)}),
        semantics=ProjectionSemantics(),
    )
    assert "state" in result.to_dict()["nodes"][0]["fields"]
    result = await capture(
        graph,
        context_config=config(node_fields={"Record": (ProjectionField(path="name"),)}),
        request=ProjectionRequest(root_id="n.Record.project", node_fields=("state",)),
    )
    assert result.to_dict()["nodes"][0]["fields"] == {}


@pytest.mark.parametrize(
    "change",
    [
        {"max_nodes": 1},
        {"max_edges": 0},
        {"max_candidates": 1},
        {"max_frontier": 1},
        {"max_edges_per_node": 1},
        {"max_depth": 0},
        {"page_size": 1},
    ],
)
async def test_rich_existing_limits_preserve_closure(graph, change):
    result = await capture(
        graph,
        request=ProjectionRequest(
            root_id="n.Record.project", max_bytes=65536, **change
        ),
    )
    data = result.to_dict()
    ids = {n["id"] for n in data["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in data["edges"])
    assert result.statistics["candidate_records"] <= change.get("max_candidates", 1000)


@pytest.mark.parametrize("view", ["relationships", "hierarchy", "ontology"])
async def test_legacy_exact_parity(tmp_path, monkeypatch, view):
    import jvspatial.core.graph_projection as module

    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 11, tzinfo=timezone.utc)

    monkeypatch.setattr(module, "datetime", Clock)
    ctx = GraphContext(JsonDB(str(tmp_path)))
    for nid, entity, attrs in [
        (
            "n.Project.a",
            "Project",
            {"name": "Harbor", "risk": {"level": None}, "count": 0},
        ),
        ("n.Component.b", "Component", {"name": "Pump", "count": False}),
    ]:
        await ctx.database.save("node", {"id": nid, "entity": entity, "context": attrs})
    await ctx.database.save(
        "edge",
        {
            "id": "e.Link.ab",
            "entity": "Link",
            "source": "n.Project.a",
            "target": "n.Component.b",
            "bidirectional": False,
            "context": {"role": "requires"},
        },
    )
    gold = json.loads(
        (
            Path(__file__).parents[1] / "fixtures" / "graph_projection_v1.json"
        ).read_text()
    )[view]
    for context_config in (None, ProjectionContextConfig()):
        result = await ctx.project_graph(
            ProjectionRequest(root_id="n.Project.a", view=view),
            scope=ProjectionScope.all(
                node_fields=("name", "risk.level", "count"), edge_fields=("role",)
            ),
            semantics=ProjectionSemantics(
                edge_types={"Link": "Recorded association."},
                label_fields={"Project": "name"},
            ),
            context_config=context_config,
        )
        assert result.to_dict() == gold["data"]
        assert (
            result.render_text() == gold["text"]
            and result.render_mermaid() == gold["mermaid"]
        )
        assert [r.model_dump(mode="json") for r in result.expansion_requests()] == gold[
            "expansions"
        ]


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        0,
        1.25,
        float("inf"),
        float("nan"),
        "",
        "短" * 300,
        '\\"' * 300,
        [False, 0, None, {"nested": "text"}],
        {"x": [1, 2, 3]},
        object(),
    ],
)
@pytest.mark.parametrize(
    "limits",
    [
        {},
        {"max_string": 16, "max_items": 1, "max_value_depth": 0},
        {"max_bytes": 4096, "max_string": 4096},
    ],
)
def test_rich_clipping_matches_legacy_values(value, limits):
    from jvspatial.core.graph_projection import _Capture, _selected

    request = ProjectionRequest(root_id="n.Record.test", **limits)
    row = {"id": request.root_id, "entity": "Record", "context": {"value": value}}
    capture = _Capture(
        GraphContext(JsonDB("unused")),
        request,
        ProjectionScope.all(node_fields=("value",)),
        None,
        ProjectionSemantics(),
        ProjectionContextConfig(profile_id="parity"),
    )
    values, truncated, _ = capture._detail("node", row, ("value",))
    expected_values, expected_truncated = _selected(row, ("value",), request)
    assert values == expected_values
    assert truncated == expected_truncated


@pytest.mark.parametrize("view", ["relationships", "hierarchy", "ontology"])
async def test_real_entity_example_custom_discriminators_and_conflicts(tmp_path, view):
    from examples.core.rich_graph_context_example import capture_demo, seed_demo

    context = GraphContext(JsonDB(str(tmp_path)))
    records = await seed_demo(context)
    result = await capture_demo(context, records, view=view)
    data = result.to_dict()
    assert {node["id"] for node in data["nodes"]} == {
        records[key].id
        for key in ("project", "supply", "test", "mitigation", "alternative", "stale")
    }
    assert {node["entity"] for node in data["nodes"]} == {"RichDemoRecord"}
    assert set(data["relation_definitions"]) == {
        "operations-v1/requires",
        "operations-v1/mitigated_by",
        "operations-v1/alternative",
    }
    assert data["meta"]["complete"]
    assert data["coverage"]["decision_sufficiency"] == "not_assessed"
    supply = next(node for node in data["nodes"] if node["id"] == records["supply"].id)
    stale = next(node for node in data["nodes"] if node["id"] == records["stale"].id)
    assert (
        supply["context"]["state"] == "confirmed"
        and stale["context"]["state"] == "unavailable"
    )
    assert stale["fields"]["state"]["evidence"]["observed_at"] == "2020-01-01"
    assert all(
        records[key].id not in result.render_text()
        for key in ("private", "hidden", "foreign")
    )


async def test_schema_qualified_logical_and_missing_selectors(graph):
    original = semantics().relation_rules[0]
    rule = original.model_copy(
        update={
            "edge_filter": {
                "$and": [
                    {"context.role": {"$regex": "^requires$"}},
                    {"context.schema": "workflow-v1"},
                ]
            }
        }
    )
    wrong_schema = original.model_copy(
        update={
            "id": "wrong-schema",
            "edge_filter": {
                "context.role": "requires",
                "context.schema": "other-schema",
            },
        }
    )
    missing = original.model_copy(
        update={
            "id": "missing-state",
            "target_filter": {"context.missing": {"$exists": False}},
        }
    )
    result = await capture(
        graph,
        semantics=ProjectionSemantics(relation_rules=(rule, wrong_schema, missing)),
    )
    assert set(result.to_dict()["relation_definitions"]) == {original.id}
    assert all(
        edge["relation"]["status"] != "ambiguous" for edge in result.to_dict()["edges"]
    )


async def test_rich_policy_failure_and_cancellation(graph):
    class FailingPolicy:
        async def authorize(self, kind, records):
            raise RuntimeError("policy failed")

    with pytest.raises(RuntimeError, match="policy failed"):
        await capture(graph, access=FailingPolicy())
    entered = asyncio.Event()

    class SlowPolicy:
        async def authorize(self, kind, records):
            entered.set()
            await asyncio.sleep(10)
            return {}

    task = asyncio.create_task(capture(graph, access=SlowPolicy()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    result = await capture(
        graph,
        access=SlowPolicy(),
        request=ProjectionRequest(root_id="n.Record.project", timeout_seconds=0.01),
    )
    assert result.to_dict()["meta"]["stop_reasons"] == ["timeout"]
    assert result.to_dict()["format_version"] == 2


@pytest.mark.parametrize("observe,cache", [(False, False), (True, False), (True, True)])
async def test_rich_native_wrappers(tmp_path, observe, cache):
    from examples.core.rich_graph_context_example import capture_demo, seed_demo
    from jvspatial import create_database

    db = create_database(
        "sqlite",
        db_path=str(tmp_path / "wrapper.db"),
        observe=observe,
        cache_get_size=10 if cache else 0,
    )
    try:
        context = GraphContext(db)
        records = await seed_demo(context)
        result = await capture_demo(context, records, execution_mode="native")
        assert result.to_dict()["meta"]["execution_mode"] == "native"
        assert len(result.to_dict()["nodes"]) == 6
    finally:
        await db.close()


def test_unsupported_capture_format_fails_renderers():
    from jvspatial import GraphProjection

    result = GraphProjection('{"format_version":3}', "{}", "{}")
    for method in (result.to_dict, result.render_text, result.render_mermaid):
        with pytest.raises(ValueError, match="format version"):
            method()


def test_profile_and_rule_aggregate_limits():
    with pytest.raises(ValueError, match="64 types"):
        ProjectionContextConfig(node_fields={f"Type{i}": () for i in range(65)})
    with pytest.raises(ValueError, match="32 fields"):
        ProjectionContextConfig(
            node_fields={
                "Type": tuple(ProjectionField(path=f"f{i}") for i in range(33))
            }
        )
    with pytest.raises(ValueError, match="65536 bytes"):
        ProjectionContextConfig(
            node_fields={
                f"Type{i}": tuple(
                    ProjectionField(path=f"f{j}", description="x" * 1024)
                    for j in range(32)
                )
                for i in range(3)
            }
        )
    with pytest.raises(ValueError, match="8192 bytes"):
        ProjectionRelation(
            id="oversized",
            edge_type="Relation",
            description="",
            direction="x",
            edge_filter={"context.role": "x" * 8192},
        )
    with pytest.raises(ValueError, match="64 unique IDs"):
        ProjectionSemantics(
            relation_rules=tuple(
                ProjectionRelation(
                    id=f"r{i}", edge_type="Relation", description="", direction="x"
                )
                for i in range(65)
            )
        )
    with pytest.raises(ValueError, match="65536 bytes"):
        ProjectionSemantics(
            relation_rules=tuple(
                ProjectionRelation(
                    id=f"r{i}",
                    edge_type="Relation",
                    description="x" * 1024,
                    conditions="y" * 1024,
                    direction="x",
                )
                for i in range(40)
            )
        )


async def test_deterministic_priority_tighter_caps_and_intrinsic_selector(graph):
    profile = config(
        node_fields={
            "Record": (
                ProjectionField(path="name", priority=2, max_string=3),
                ProjectionField(path="state", priority=1),
            )
        }
    )
    rule = ProjectionRelation(
        id="intrinsic",
        edge_type="Relation",
        description="An explicit permitted identity rule",
        direction="requires",
        source_filter={"id": "n.Record.project", "entity": "Record"},
        target_filter={"id": "n.Record.a"},
    )
    result = await capture(
        graph,
        context_config=profile,
        semantics=ProjectionSemantics(relation_rules=(rule,)),
    )
    project = next(
        row for row in result.to_dict()["nodes"] if row["id"] == "n.Record.project"
    )
    assert project["context"]["name"] == "Har"
    assert project["fields"]["name"]["state"] == "truncated"
    assert set(project["fields"]) == {"name", "state"}
    assert set(result.to_dict()["relation_definitions"]) == {"intrinsic"}
