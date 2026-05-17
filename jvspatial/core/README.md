# jvspatial/core

Entity hierarchy, graph context, traversal primitives, and decorators.

> **Read first**: [SPEC §1-7](../../SPEC.md), [docs/md/entity-reference.md](../../docs/md/entity-reference.md)

---

## Purpose

`core/` defines the graph data model. Everything jvspatial persists is one of the entity types here: `Object`, `Node`, `Edge`, `Walker`, or `Root`. Traversal is performed by walkers; database I/O is brokered through `GraphContext`.

## Layout

```
core/
├── entities/          # Object, Node, Edge, Walker, Root + walker_components
├── annotations/       # @attribute system + index helpers
├── decorators/        # @on_visit, @on_exit
├── mixins/            # DeferredSaveMixin and globals
├── walker_components/ # Trail, protection, queue, event system (under entities/)
├── context.py         # GraphContext + scoping helpers
├── events.py          # Global event bus + @on_emit
├── graph.py           # DOT / Mermaid export
├── graph_expansion.py # BFS / subgraph utilities
├── pager.py           # ObjectPager
└── utils.py           # generate_id, find_subclass_by_name, datetime helpers
```

## Public API (from `jvspatial.core`)

| Name | What it does |
|---|---|
| `Object`, `Node`, `Edge`, `Walker`, `Root` | Entity classes (SPEC §2) |
| `NodeQuery` | Typed node-query helper |
| `GraphContext` | Database + cache + monitor binding (SPEC §7) |
| `get_default_context` / `set_default_context` / `scoped_default_context` | Context lifecycle |
| `graph_context` / `async_graph_context` | Sync / async context managers |
| `@on_visit`, `@on_exit`, `@on_emit` | Hook decorators |
| `DeferredSaveMixin`, `deferred_saves_globally_allowed`, `flush_deferred_entities` | Save-batching opt-in |
| `ObjectPager`, `paginate_objects`, `paginate_by_field` | Pagination |
| `generate_id`, `find_subclass_by_name`, `serialize_datetime` | Utilities |
| `export_graph`, `generate_graph_dot`, `generate_graph_mermaid`, `expand_node`, `subgraph_bfs` | Visualization / expansion |

## Invariants

- **`__entity_name__` is per-subclass.** Resolution: `cls.__dict__.get("__entity_name__") or cls.__name__`. Not inherited. (`entities/object.py:35-44`)
- **`id` is protected.** Set in `__init__`, cannot be reassigned. (`entities/object.py:46-48`)
- **Walker protection is on by default.** `max_steps=10000`, `max_visits_per_node=100`, `max_execution_time=300s`, `max_queue_size=1000`. Disabling globally is forbidden. (`entities/walker.py:106-115`)
- **Subclass lookup honors entity-name override and caches positive hits only.** Negative caching would break later imports. (`utils.py:58-89`)
- **Root is a singleton with fixed ID `n.Root.root`.** Created under async lock. (`entities/root.py`)
- **MRO matters for mixins.** `DeferredSaveMixin` must precede the base class. (`mixins/`)

## Modification patterns

- Adding a new entity field: declare with `@attribute(...)`. Top-level persisted fields are added via `_get_top_level_fields()`. Update tests under `tests/core/`.
- Adding a new walker hook: decorate with `@on_visit(NodeType | "string_name")`. Hooks are registered at `__init_subclass__` time.
- Adding a new graph utility: prefer `core/graph.py` (export) or `core/graph_expansion.py` (traversal). Both have sibling tests.

## Related docs

- [docs/md/entity-reference.md](../../docs/md/entity-reference.md)
- [docs/md/graph-traversal.md](../../docs/md/graph-traversal.md)
- [docs/md/graph-context.md](../../docs/md/graph-context.md)
- [docs/md/walker-trail-tracking.md](../../docs/md/walker-trail-tracking.md)
- [docs/md/infinite-walk-protection.md](../../docs/md/infinite-walk-protection.md)
- [docs/md/attribute-annotations.md](../../docs/md/attribute-annotations.md)

## Stability

All names listed in "Public API" are part of `jvspatial.__all__` and follow the stable-tier contract (see [docs/md/stability.md](../../docs/md/stability.md)). The contents of `walker_components/`, `mixins/_internal/`, and any underscore-prefixed module are internal — do not import directly.
