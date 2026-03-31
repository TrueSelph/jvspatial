"""Server startup vs strict JVSPATIAL_* env and merge precedence."""

import pytest

from jvspatial.api.server import Server
from jvspatial.env_adapter import JvspatialConfigEnvError


def test_server_rejects_unknown_jvspatial_env_key(monkeypatch, tmp_path):
    monkeypatch.setenv("JVSPATIAL_NOT_A_REAL_KEY", "1")
    db = tmp_path / "jvdb"
    db.mkdir()
    with pytest.raises(JvspatialConfigEnvError, match="Unknown environment variable"):
        Server(title="t", db_type="json", db_path=str(db))


def test_server_constructor_overrides_env_port(monkeypatch, tmp_path):
    monkeypatch.setenv("JVSPATIAL_PORT", "9999")
    db = tmp_path / "jvdb"
    db.mkdir()
    server = Server(title="t", port=8080, db_type="json", db_path=str(db))
    assert server.config.port == 8080


def test_server_env_overrides_default_when_no_kwarg(monkeypatch, tmp_path):
    monkeypatch.setenv("JVSPATIAL_PORT", "7777")
    db = tmp_path / "jvdb"
    db.mkdir()
    server = Server(title="t", db_type="json", db_path=str(db))
    assert server.config.port == 7777


def test_server_graph_endpoint_enabled_from_allowlisted_env(monkeypatch, tmp_path):
    monkeypatch.setenv("JVSPATIAL_GRAPH_ENDPOINT_ENABLED", "true")
    db = tmp_path / "jvdb"
    db.mkdir()
    server = Server(title="t", db_type="json", db_path=str(db))
    assert server.config.graph_endpoint_enabled is True
