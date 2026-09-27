"""Regression checks for the combined security and gap review."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request, Response

from jvspatial.api.auth.config import AuthConfig
from jvspatial.api.auth.models import (
    UserCreate,
    UserCreateAdmin,
    UserLogin,
    UserRolesUpdate,
)
from jvspatial.api.auth.service import AuthenticationService
from jvspatial.api.components.app_builder import AppBuilder
from jvspatial.api.components.auth_middleware import AuthenticationMiddleware
from jvspatial.api.config import ServerConfig
from jvspatial.api.integrations.storage.service import FileStorageService
from jvspatial.api.integrations.webhooks.middleware import WebhookMiddleware
from jvspatial.api.integrations.webhooks.utils import (
    WebhookConfig,
    generate_hmac_signature,
)
from jvspatial.api.server_configurator import ServerConfigurator
from jvspatial.core.context import GraphContext, scoped_default_context
from jvspatial.core.entities import Node
from jvspatial.core.entities.node_query import NodeQuery
from jvspatial.core.entities.root import Root
from jvspatial.core.mixins.deferred_save import DeferredSaveMixin
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB
from jvspatial.exceptions import DatabaseError
from jvspatial.storage.exceptions import PathTraversalError
from jvspatial.storage.interfaces.local import LocalFileInterface
from jvspatial.utils.decorators import retry


def _auth(tmp_path):
    return AuthenticationService(
        GraphContext(database=JsonDB(str(tmp_path / "auth"))),
        jwt_secret="combined-security-review-test-secret-12345",
    )


@pytest.mark.asyncio
async def test_user_lookup_error_cannot_authenticate_jwt(tmp_path):
    service = _auth(tmp_path)
    token, _ = service._generate_jwt_token(
        "o.User.fake", "u@example.com", roles=["admin"]
    )
    service._is_token_blacklisted_by_jti = AsyncMock(return_value=False)
    service._get_user_by_id = AsyncMock(side_effect=DatabaseError("unavailable"))
    assert await service.validate_token(token) is None


@pytest.mark.asyncio
async def test_demoted_user_loses_jwt_role(tmp_path):
    service = _auth(tmp_path)
    user = await service.create_user_with_roles(
        UserCreateAdmin(
            email="admin@example.com", password="long-password-123", roles=["admin"]
        )
    )
    token, _ = service._generate_jwt_token(user.id, user.email, roles=["admin"])
    assert "admin" in (await service.validate_token(token)).roles
    await service.update_user_roles(user.id, UserRolesUpdate(roles=["user"]))
    # Revocation may reject the old token outright; either outcome is safe.
    result = await service.validate_token(token)
    assert result is None or "admin" not in result.roles


@pytest.mark.asyncio
async def test_concurrent_public_registration_never_grants_admin(tmp_path):
    service = _auth(tmp_path)
    users = await asyncio.gather(
        service.register_user(
            UserCreate(email="first@example.com", password="long-password-123")
        ),
        service.register_user(
            UserCreate(email="second@example.com", password="long-password-123")
        ),
    )
    assert all(user.roles == ["user"] for user in users)


@pytest.mark.asyncio
async def test_admin_bootstrap_aborts_on_unreadable_user(tmp_path):
    service = _auth(tmp_path)
    service._find_user_by_email = AsyncMock(return_value=None)
    service._user_count = AsyncMock(return_value=1)
    service.context.database.find = AsyncMock(return_value=[{"id": "unreadable"}])
    service.context._deserialize_entity = AsyncMock(side_effect=RuntimeError("bad row"))
    with pytest.raises(RuntimeError, match="bad row"):
        await service.bootstrap_admin("admin@example.com", "long-password-123")


@pytest.mark.asyncio
async def test_logout_deactivates_bound_refresh_token(tmp_path):
    service = _auth(tmp_path)
    await service.register_user(
        UserCreate(email="logout@example.com", password="long-password-123")
    )
    tokens = await service.login_user(
        UserLogin(email="logout@example.com", password="long-password-123")
    )
    assert tokens.refresh_token
    assert await service.validate_token(tokens.access_token)
    assert await service.logout_user(tokens.access_token)
    assert await service.validate_token(tokens.access_token) is None
    with pytest.raises(ValueError, match="Invalid or expired refresh token"):
        await service.refresh_access_token(tokens.refresh_token)


def test_jsondb_rejects_escaping_paths_before_creating_files(tmp_path):
    db = JsonDB(str(tmp_path / "db"))
    with pytest.raises(ValueError):
        db._get_record_path("../outside", "id")
    with pytest.raises(ValueError):
        db._get_record_path("node", "../outside")
    assert not (tmp_path / "outside.json").exists()


@pytest.mark.asyncio
async def test_edge_delete_failure_preserves_node(tmp_path, monkeypatch):
    database = JsonDB(str(tmp_path / "graph"))
    context = GraphContext(database=database)
    parent, child = Node(), Node()
    parent._graph_context = context
    child._graph_context = context
    await context.save(parent)
    await context.save(child)
    with scoped_default_context(context):
        await parent.connect(child)

    original_delete = database.delete

    async def fail_edge_delete(collection, record_id):
        if collection == "edge":
            raise RuntimeError("edge write failed")
        return await original_delete(collection, record_id)

    monkeypatch.setattr(database, "delete", fail_edge_delete)
    with scoped_default_context(context):
        with pytest.raises(RuntimeError, match="edge write failed"):
            await child.delete(cascade=False)
    assert await database.get("node", child.id) is not None


@pytest.mark.asyncio
async def test_cascade_discovery_failure_preserves_parent(tmp_path, monkeypatch):
    database = JsonDB(str(tmp_path / "graph"))
    context = GraphContext(database=database)
    parent, child = Node(), Node()
    parent._graph_context = context
    child._graph_context = context
    await context.save(parent)
    await context.save(child)
    with scoped_default_context(context):
        await parent.connect(child)

    async def fail_edge_lookup(self, graph_context):
        raise RuntimeError("edge lookup failed")

    monkeypatch.setattr(Node, "_incident_edges", fail_edge_lookup)
    with scoped_default_context(context):
        with pytest.raises(RuntimeError, match="edge lookup failed"):
            await parent.delete()
    assert await database.get("node", parent.id) is not None


@pytest.mark.asyncio
async def test_node_query_uses_entity_name_override():
    class NamedNode(Node):
        __entity_name__ = "PublicName"

    source = Node()
    named = NamedNode()
    query = NodeQuery([named], source=source)
    assert await query.filter(node="PublicName") == [named]
    assert await query.filter(node=NamedNode) == [named]


@pytest.mark.asyncio
async def test_atomic_increment_rejects_missing_and_protected_fields(tmp_path):
    context = GraphContext(database=JsonDB(str(tmp_path / "increment")))
    node = Node()
    node._graph_context = context
    await context.save(node)
    assert await context.atomic_increment(node.id, "missing") is False
    with pytest.raises(ValueError, match="protected"):
        await context.atomic_increment(node.id, "id")


def test_undeclared_private_attribute_is_rejected():
    node = Node()
    with pytest.raises(AttributeError):
        node._unexpected = "hidden"


def test_declared_private_method_can_be_replaced_on_an_instance():
    class PluginNode(Node):
        async def _load_token(self):
            return "real"

    node = PluginNode()
    replacement = AsyncMock(return_value="test")
    node._load_token = replacement
    assert node._load_token is replacement
    with pytest.raises(AttributeError):
        node._unknown_helper = replacement


def test_auth_rate_limit_bypass_is_explicit_and_defaults_on():
    config = ServerConfig()
    config.auth.enabled = True
    registry = SimpleNamespace(_function_registry={}, _walker_registry={})
    server = SimpleNamespace(config=config, _endpoint_registry=registry)
    configurator = ServerConfigurator(server)

    assert config.rate_limit.auth_entrypoint_rate_limit_enabled is True
    assert "/api/auth/reset-password" in configurator._build_rate_limit_config()

    config.rate_limit.auth_entrypoint_rate_limit_enabled = False
    assert "/api/auth/reset-password" not in configurator._build_rate_limit_config()


@pytest.mark.asyncio
async def test_version_id_cannot_escape_storage_root(tmp_path):
    storage = LocalFileInterface(root_dir=str(tmp_path / "files"))
    with pytest.raises(PathTraversalError):
        await storage.create_version("safe.txt", b"data", version="../../outside")
    with pytest.raises(PathTraversalError):
        await storage.get_version("safe.txt", "../../outside")
    assert not (tmp_path / "outside.bin").exists()


@pytest.mark.asyncio
async def test_signed_get_webhook_rejects_missing_signature():
    middleware = WebhookMiddleware(
        FastAPI(), config=WebhookConfig(https_required=False), server=None
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/webhook/check",
            "raw_path": b"/webhook/check",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
    )
    with pytest.raises(HTTPException) as exc:
        await middleware._process_webhook_request(
            request,
            {
                "signature_required": True,
                "hmac_secret": "signed-get-test-secret",
                "https_required": False,
            },
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_signed_get_webhook_binds_query_string():
    secret = "signed-get-test-secret"
    signature = generate_hmac_signature(b"event=approved", secret)
    middleware = WebhookMiddleware(
        FastAPI(), config=WebhookConfig(https_required=False), server=None
    )
    config = {
        "signature_required": True,
        "hmac_secret": secret,
        "https_required": False,
    }
    signed = _request("/webhook/check", headers=[(b"x-signature", signature.encode())])
    signed.scope["query_string"] = b"event=approved"
    await middleware._process_webhook_request(signed, config)
    assert signed.state.hmac_verified is True

    tampered = _request(
        "/webhook/check", headers=[(b"x-signature", signature.encode())]
    )
    tampered.scope["query_string"] = b"event=denied"
    with pytest.raises(HTTPException) as exc:
        await middleware._process_webhook_request(tampered, config)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_proxy_creation_awaits_manager_and_uses_code():
    interface = SimpleNamespace(
        file_exists=AsyncMock(return_value=True), base_url="https://files.example"
    )
    manager = SimpleNamespace(
        create_proxy=AsyncMock(return_value=SimpleNamespace(code="abc123"))
    )
    service = FileStorageService(interface, proxy_manager=manager)
    result = await service.handle_create_proxy("safe.txt")
    manager.create_proxy.assert_awaited_once()
    assert result["code"] == "abc123"
    assert result["proxy_url"].endswith("/abc123")


def _request(path: str, *, headers=()):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": list(headers),
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.asyncio
async def test_endpoint_config_lookup_error_denies_request():
    middleware = AuthenticationMiddleware(
        FastAPI(), AuthConfig(auth_enabled=True, test_mode=True), SimpleNamespace()
    )
    request = _request("/api/private")
    request.state.user = SimpleNamespace(id="user", roles=["user"], permissions=[])
    middleware.path_matcher.is_exempt = lambda _: False
    middleware._auth_resolver.endpoint_requires_auth = lambda _: True
    middleware._auth_resolver.endpoint_has_fastapi_auth = lambda _: False
    middleware._auth_resolver.get_endpoint_config = lambda _: 1 / 0
    middleware._normalize_user = AsyncMock(return_value=request.state.user)
    response = await middleware.dispatch(request, AsyncMock())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unconfigured_route_requires_login_but_no_unlisted_role():
    middleware = AuthenticationMiddleware(
        FastAPI(), AuthConfig(auth_enabled=True, test_mode=True), SimpleNamespace()
    )
    middleware.path_matcher.is_exempt = lambda _: False
    middleware._auth_resolver.endpoint_requires_auth = lambda _: True
    middleware._auth_resolver.endpoint_has_fastapi_auth = lambda _: False
    middleware._auth_resolver.get_endpoint_config = lambda _: None
    middleware._normalize_user = AsyncMock(side_effect=lambda user: user)
    next_handler = AsyncMock(return_value=Response(status_code=200))

    request = _request("/api/mcp")
    request.state.user = SimpleNamespace(id="user", roles=["user"], permissions=[])
    response = await middleware.dispatch(request, next_handler)
    assert response.status_code == 200

    admin_request = _request("/api/graph")
    admin_request.state.user = request.state.user
    response = await middleware.dispatch(admin_request, next_handler)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_key_scope_uses_path_boundary():
    key = SimpleNamespace(
        id="key",
        user_id="user",
        allowed_ips=[],
        allowed_endpoints=["/api/files"],
        permissions=[],
        rate_limit_override=None,
    )
    key_service = SimpleNamespace(
        validate_key=AsyncMock(return_value=key), update_key_usage=AsyncMock()
    )
    middleware = AuthenticationMiddleware(
        FastAPI(),
        AuthConfig(auth_enabled=True),
        SimpleNamespace(_api_key_service=key_service),
    )
    header = [(b"x-api-key", b"secret-for-test")]
    assert (
        await middleware._authenticate_api_key(
            _request("/api/files-admin", headers=header)
        )
        is None
    )
    assert await middleware._authenticate_api_key(
        _request("/api/files", headers=header)
    )


@pytest.mark.asyncio
async def test_async_retry_awaits_and_retries():
    calls = []

    @retry(max_attempts=3, delay=0)
    async def sometimes_fails():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("retry")
        return "ok"

    assert await sometimes_fails() == "ok"
    assert len(calls) == 3


def test_root_lock_is_scoped_to_event_loop():
    first = asyncio.run(_get_root_lock())
    second = asyncio.run(_get_root_lock())
    assert first is not second


async def _get_root_lock():
    return Root._loop_lock()


def test_wrong_deferred_save_mro_raises_at_class_creation():
    with pytest.raises(TypeError, match="must precede"):

        class Bad(Node, DeferredSaveMixin):
            pass


@pytest.mark.asyncio
async def test_sqlite_index_rejects_unsafe_field(tmp_path):
    db = SQLiteDB(str(tmp_path / "index.db"))
    with pytest.raises(ValueError, match="Unsafe index"):
        await db.create_index("node", "context.name'escape")
    await db.close()


def test_production_docs_are_unpublished_by_default(monkeypatch):
    monkeypatch.setenv("JVSPATIAL_ENVIRONMENT", "production")
    monkeypatch.delenv("JVSPATIAL_DOCS_DISABLED", raising=False)
    app = AppBuilder(ServerConfig()).create_app()
    assert app.docs_url is None
    assert app.openapi_url is None
