"""Serverless behavior tests for webhook middleware."""

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.context import set_current_server
from jvspatial.api.server import Server


def test_async_webhook_executes_inline_in_serverless_mode():
    """Serverless mode must not return queued async response."""
    test_id = uuid.uuid4().hex[:8]
    server = Server(
        title="Test API",
        db_type="json",
        db_path=f"./.test_dbs/test_db_webhook_serverless_{test_id}",
        auth=dict(auth_enabled=False),
        webhook=dict(webhook_https_required=False),
    )
    set_current_server(server)

    @endpoint("/webhook/serverless-inline", methods=["POST"], webhook=True)
    async def webhook_handler():
        return {"status": "processed-inline"}

    webhook_handler._jvspatial_endpoint_config["async_processing"] = True  # type: ignore[attr-defined]

    server.app = None
    client = TestClient(server.get_app())
    with patch.dict("os.environ", {"SERVERLESS_MODE": "true"}):
        response = client.post("/api/webhook/serverless-inline", json={"event": "x"})

    assert response.status_code == 200
    assert response.json()["status"] == "processed-inline"
