"""HMAC verification regression coverage (audit §4.3 / SPEC §15.2).

``verify_hmac_signature`` previously sliced 7 chars off
``expected_signature`` before comparison, while the incoming signature
had already had its prefix stripped. The mismatched lengths fed into
``hmac.compare_digest`` always returned False — webhook signature auth
rejected every request.
"""

import pytest

from jvspatial.api.integrations.webhooks.utils import (
    generate_hmac_signature,
    verify_hmac_signature,
)


def test_valid_hmac_with_default_prefix_verifies():
    payload = b'{"event":"ping"}'
    secret = "shared-secret"  # pragma: allowlist secret
    signature_with_prefix = generate_hmac_signature(payload, secret)
    assert signature_with_prefix.startswith("sha256=")

    assert verify_hmac_signature(payload, signature_with_prefix, secret) is True


def test_valid_hmac_without_prefix_verifies():
    payload = b'{"event":"ping"}'
    secret = "shared-secret"  # pragma: allowlist secret
    bare = generate_hmac_signature(payload, secret, prefix="")

    assert verify_hmac_signature(payload, bare, secret, prefix="") is True


def test_invalid_hmac_rejects():
    payload = b'{"event":"ping"}'
    secret = "shared-secret"  # pragma: allowlist secret
    # Tampered signature
    bad = "sha256=" + ("0" * 64)
    assert verify_hmac_signature(payload, bad, secret) is False


def test_empty_signature_or_secret_rejects():
    assert (
        verify_hmac_signature(b"x", "", "secret") is False
    )  # pragma: allowlist secret
    assert verify_hmac_signature(b"x", "sha256=abc", "") is False
