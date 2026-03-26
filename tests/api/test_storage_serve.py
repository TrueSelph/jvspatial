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
from jvspatial.env import clear_load_env_cache


@pytest.mark.asyncio
async def test_get_files_serves_from_configured_root():
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
        url = f"{APIRoutes.FILES_ROOT}/smoke/hello.txt"
        with TestClient(app) as client:
            r = client.get(url)
        assert r.status_code == 200
        assert r.content == b"hello-bytes"
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.mark.asyncio
async def test_openapi_files_delete_has_security_when_get_is_public(monkeypatch):
    """DELETE must show OpenAPI security (padlock) even when GET shares the same path template."""
    tid = uuid.uuid4().hex[:8]
    base = Path(tempfile.mkdtemp(prefix=f"jvsp_openapi_{tid}_"))
    root = base / "vault"
    db_path = base / f"db_{tid}"
    monkeypatch.delenv("JVSPATIAL_FILES_PUBLIC_READ", raising=False)
    clear_load_env_cache()
    try:
        server = Server(
            title="files-openapi-security",
            db_type="json",
            db_path=str(db_path),
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-openapi-files",
                jwt_algorithm="HS256",
            ),
            webhook=dict(webhook_https_required=False),
            file_storage=dict(
                file_storage_enabled=True,
                file_storage_provider="local",
                file_storage_root=str(root),
            ),
        )
        set_current_server(server)
        app = server.get_app()
        schema = app.openapi()
        path_key = f"{APIRoutes.FILES_ROOT}/{{file_path}}"
        assert "delete" in schema["paths"][path_key]
        assert schema["paths"][path_key]["delete"].get("security")
        assert "get" in schema["paths"][path_key]
        assert not schema["paths"][path_key]["get"].get("security")
    finally:
        shutil.rmtree(base, ignore_errors=True)
        clear_load_env_cache()


@pytest.mark.asyncio
async def test_get_files_open_by_default_when_auth_enabled(monkeypatch):
    """Default JVSPATIAL_FILES_PUBLIC_READ: anonymous GET allowed when auth middleware is on."""
    tid = uuid.uuid4().hex[:8]
    base = Path(tempfile.mkdtemp(prefix=f"jvsp_files_open_{tid}_"))
    root = base / "vault"
    db_path = base / f"db_{tid}"
    monkeypatch.delenv("JVSPATIAL_FILES_PUBLIC_READ", raising=False)
    clear_load_env_cache()
    try:
        server = Server(
            title="files-open-get-test",
            db_type="json",
            db_path=str(db_path),
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-files-open-get",
                jwt_algorithm="HS256",
            ),
            webhook=dict(webhook_https_required=False),
            file_storage=dict(
                file_storage_enabled=True,
                file_storage_provider="local",
                file_storage_root=str(root),
            ),
        )
        set_current_server(server)
        assert server._file_interface is not None
        await server._file_interface.save_file("smoke/hello.txt", b"open-bytes")

        app = server.get_app()
        url = f"{APIRoutes.FILES_ROOT}/smoke/hello.txt"
        with TestClient(app) as client:
            r = client.get(url)
        assert r.status_code == 200
        assert r.content == b"open-bytes"
    finally:
        shutil.rmtree(base, ignore_errors=True)
        clear_load_env_cache()


@pytest.mark.asyncio
async def test_get_files_requires_auth_when_files_public_read_false(monkeypatch):
    tid = uuid.uuid4().hex[:8]
    base = Path(tempfile.mkdtemp(prefix=f"jvsp_files_auth_{tid}_"))
    root = base / "vault"
    db_path = base / f"db_{tid}"
    monkeypatch.setenv("JVSPATIAL_FILES_PUBLIC_READ", "false")
    clear_load_env_cache()
    try:
        server = Server(
            title="files-auth-test",
            db_type="json",
            db_path=str(db_path),
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-files-public-read",
                jwt_algorithm="HS256",
            ),
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
        url = f"{APIRoutes.FILES_ROOT}/smoke/hello.txt"
        with TestClient(app) as client:
            r = client.get(url)
        assert r.status_code == 401
        assert r.json().get("error_code") == "authentication_required"
    finally:
        shutil.rmtree(base, ignore_errors=True)
        monkeypatch.delenv("JVSPATIAL_FILES_PUBLIC_READ", raising=False)
        clear_load_env_cache()


@pytest.mark.asyncio
async def test_post_files_upload_requires_auth_when_get_is_public(monkeypatch):
    """POST upload stays authenticated when GET is public by default."""
    tid = uuid.uuid4().hex[:8]
    base = Path(tempfile.mkdtemp(prefix=f"jvsp_files_post_auth_{tid}_"))
    root = base / "vault"
    db_path = base / f"db_{tid}"
    monkeypatch.delenv("JVSPATIAL_FILES_PUBLIC_READ", raising=False)
    clear_load_env_cache()
    try:
        server = Server(
            title="files-post-auth-test",
            db_type="json",
            db_path=str(db_path),
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-files-post",
                jwt_algorithm="HS256",
            ),
            webhook=dict(webhook_https_required=False),
            file_storage=dict(
                file_storage_enabled=True,
                file_storage_provider="local",
                file_storage_root=str(root),
            ),
        )
        set_current_server(server)
        app = server.get_app()
        upload_url = APIRoutes.FILES_UPLOAD
        with TestClient(app) as client:
            r = client.post(upload_url, files={"file": ("x.txt", b"x", "text/plain")})
        assert r.status_code == 401
        assert r.json().get("error_code") == "authentication_required"
    finally:
        shutil.rmtree(base, ignore_errors=True)
        clear_load_env_cache()


@pytest.mark.asyncio
async def test_delete_files_requires_auth_when_get_is_public(monkeypatch):
    """DELETE stays authenticated when GET is public (path:path route matching)."""
    tid = uuid.uuid4().hex[:8]
    base = Path(tempfile.mkdtemp(prefix=f"jvsp_files_del_auth_{tid}_"))
    root = base / "vault"
    db_path = base / f"db_{tid}"
    monkeypatch.delenv("JVSPATIAL_FILES_PUBLIC_READ", raising=False)
    clear_load_env_cache()
    try:
        server = Server(
            title="files-delete-auth-test",
            db_type="json",
            db_path=str(db_path),
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-files-delete",
                jwt_algorithm="HS256",
            ),
            webhook=dict(webhook_https_required=False),
            file_storage=dict(
                file_storage_enabled=True,
                file_storage_provider="local",
                file_storage_root=str(root),
            ),
        )
        set_current_server(server)
        assert server._file_interface is not None
        await server._file_interface.save_file("smoke/nested/hello.txt", b"keep")

        app = server.get_app()
        url = f"{APIRoutes.FILES_ROOT}/smoke/nested/hello.txt"
        with TestClient(app) as client:
            r_get = client.get(url)
            r_del = client.delete(url)
        assert r_get.status_code == 200
        assert r_get.content == b"keep"
        assert r_del.status_code == 401
        assert r_del.json().get("error_code") == "authentication_required"
    finally:
        shutil.rmtree(base, ignore_errors=True)
        clear_load_env_cache()
