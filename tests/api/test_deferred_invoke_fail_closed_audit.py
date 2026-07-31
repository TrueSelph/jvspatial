"""Deferred-invoke auth: fail-closed for public peers; loopback for LWA."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

from jvspatial.api.deferred_invoke_route import (
    _deferred_invoke_secret_ok,
    _is_loopback_client,
)


def _fake_request(headers: dict, host: Optional[str] = "testclient") -> MagicMock:
    req = MagicMock()
    req.headers.get = lambda k, default=None: headers.get(k, default)
    req.headers.__getitem__ = lambda _self, k: headers[k]
    if host is None:
        req.client = None
    else:
        req.client = SimpleNamespace(host=host, port=50000)
    return req


def test_no_secret_set_denies_non_loopback():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JVSPATIAL_DEFERRED_INVOKE_SECRET", None)
        req = _fake_request({}, host="3.16.58.158")
        assert _deferred_invoke_secret_ok(req) is False


def test_no_secret_set_allows_loopback():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JVSPATIAL_DEFERRED_INVOKE_SECRET", None)
        for host in ("127.0.0.1", "::1", "localhost", "LOCALHOST"):
            req = _fake_request({}, host=host)
            assert _deferred_invoke_secret_ok(req) is True, host


def test_no_client_denies_when_secret_unset():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JVSPATIAL_DEFERRED_INVOKE_SECRET", None)
        req = _fake_request({}, host=None)
        assert _deferred_invoke_secret_ok(req) is False


def test_loopback_allows_even_when_secret_set_without_header():
    """LWA self-invoke cannot attach custom headers; loopback must still work."""
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "shh"},  # pragma: allowlist secret
        clear=False,
    ):
        req = _fake_request({}, host="127.0.0.1")
        assert _deferred_invoke_secret_ok(req) is True


def test_matching_header_allows_non_loopback():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "shh"},  # pragma: allowlist secret
        clear=False,
    ):
        req = _fake_request(
            {"X-JVSPATIAL-Deferred-Authorize": "shh"},
            host="3.16.58.158",
        )
        assert _deferred_invoke_secret_ok(req) is True


def test_matching_bearer_allows_non_loopback():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "shh"},  # pragma: allowlist secret
        clear=False,
    ):
        req = _fake_request(
            {"Authorization": "Bearer shh"},
            host="3.16.58.158",
        )
        assert _deferred_invoke_secret_ok(req) is True


def test_mismatched_secret_denies_non_loopback():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "shh"},  # pragma: allowlist secret
        clear=False,
    ):
        req = _fake_request(
            {"X-JVSPATIAL-Deferred-Authorize": "wrong"},
            host="3.16.58.158",
        )
        assert _deferred_invoke_secret_ok(req) is False


def test_is_loopback_client_helpers():
    assert _is_loopback_client(_fake_request({}, host="127.0.0.1")) is True
    assert _is_loopback_client(_fake_request({}, host="testclient")) is False
    assert _is_loopback_client(_fake_request({}, host=None)) is False
