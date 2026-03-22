"""Smoke tests: HTTP GET serves bytes from the configured local file_storage root."""

import shutil
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.constants import APIRoutes
from jvspatial.api.context import set_current_server
from jvspatial.api.server import Server


@pytest.mark.asyncio
async def test_get_storage_files_serves_from_configured_root():
    tid = uuid.uuid4().hex[:8]
    base = Path(tempfile.mkdtemp(prefix=f"jvsp_storage_{tid}_"))
    root = base / "vault"
    db_path = base / f"db_{tid}"
    try:
        server = Server(
            title="storage-serve-test",
            db_type="json",
            db_path=str(db_path),
            auth=dict(auth_enabled=False),
            webhook=dict(webhook_https_required=False),
            file_storage=dict(
                file_storage_enabled=True,
                file_storage_provider="local",
                file_storage_root=str(root),
            ),
        )
        set_current_server(server)
        assert server._file_interface is not None
        await server._file_interface.save_file("smoke/hello.txt", b"hello-bytes")

        app = server.get_app()
        # Routes use ``APIRoutes.STORAGE_FILES`` (default ``/storage/files``, see load_env)
        url = f"{APIRoutes.STORAGE_FILES}/smoke/hello.txt"
        with TestClient(app) as client:
            r = client.get(url)
        assert r.status_code == 200
        assert r.content == b"hello-bytes"
    finally:
        shutil.rmtree(base, ignore_errors=True)
