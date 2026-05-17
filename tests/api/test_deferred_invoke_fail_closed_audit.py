"""Deferred-invoke fail-closed when secret unset (audit §4.16 / SPEC §15.2)."""

import os
from unittest.mock import MagicMock, patch

from jvspatial.api.deferred_invoke_route import _deferred_invoke_secret_ok


def _fake_request(headers: dict) -> MagicMock:
    req = MagicMock()
    req.headers.get = lambda k, default=None: headers.get(k, default)
    req.headers.__getitem__ = lambda _self, k: headers[k]
    return req


def test_no_secret_set_denies_access():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JVSPATIAL_DEFERRED_INVOKE_SECRET", None)
        req = _fake_request({})
        assert _deferred_invoke_secret_ok(req) is False


def test_matching_header_allows():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "shh"},  # pragma: allowlist secret
        clear=False,
    ):
        req = _fake_request({"X-JVSPATIAL-Deferred-Authorize": "shh"})
        assert _deferred_invoke_secret_ok(req) is True


def test_matching_bearer_allows():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "shh"},  # pragma: allowlist secret
        clear=False,
    ):
        req = _fake_request({"Authorization": "Bearer shh"})
        assert _deferred_invoke_secret_ok(req) is True


def test_mismatched_secret_denies():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "shh"},  # pragma: allowlist secret
        clear=False,
    ):
        req = _fake_request({"X-JVSPATIAL-Deferred-Authorize": "wrong"})
        assert _deferred_invoke_secret_ok(req) is False
