# Examples

The canonical runnable index is [examples/README.md](../../examples/README.md).
Examples are grouped by feature rather than located directly in the repository
root. Each group has setup and usage notes.

| Area | Index |
| --- | --- |
| Entities, graph traversal and visualization | [Core examples](../../examples/core/README.md) |
| Authenticated and public HTTP endpoints | [API examples](../../examples/api/README.md) |
| Backends, queries and database contexts | [Database examples](../../examples/database/README.md) |
| File storage | [Storage examples](../../examples/storage/README.md) |
| Scheduled work | [Scheduler examples](../../examples/scheduler/README.md) |
| Failure handling | [Error-handling examples](../../examples/error_handling/README.md) |
| Logging | [Logging examples](../../examples/logging/README.md) |

Run from the repository root after installing the dependencies documented in
the relevant group's README:

```bash
python examples/database/sqlite_example.py
python examples/storage/file_storage_demo.py
python examples/core/graph_visualization_example.py
```

Server examples start local HTTP services; database and cloud-storage examples
may require a reachable backend or configured credentials. Inspect their setup
before running them against an existing installation. Example completion does
not qualify production authorization, storage durability or deployed topology.

## Related guides

- [Quick Start](quick-start-guide.md)
- [Entity Reference](entity-reference.md)
- [Authentication](authentication.md)
- [Graph Visualization](graph-visualization.md)
- [Graph Context for Inference](graph-projection.md)
- [Transactions](transactions.md)
