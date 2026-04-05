"""Optional FastAPI mount for embedded graph UI (static files under jvspatial)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server


def _embedded_graph_index() -> Optional[Path]:
    p = (
        Path(__file__).resolve().parents[2]
        / "jvspatial"
        / "static"
        / "admin_graph"
        / "index.html"
    )
    if p.is_file():
        return p
    return None


@pytest.mark.skipif(
    _embedded_graph_index() is None,
    reason="Graph UI not embedded (cd jvgraph-ui && npm run embed)",
)
def test_admin_graph_ui_served_when_embedded() -> None:
    test_id = __name__.replace(".", "_")
    server = Server(
        title="Admin graph mount test",
        db_type="json",
        db_path=f"./.test_dbs/test_admin_graph_ui_{test_id}",
        graph_endpoint_enabled=True,
    )
    client = TestClient(server.get_app())
    r = client.get("/admin/graph/")
    assert r.status_code == 200
    assert b"jvspatial admin graph" in r.content or b"root" in r.content.lower()

    root = client.get("/").json()
    assert root.get("admin_graph_ui") == "/admin/graph/"
