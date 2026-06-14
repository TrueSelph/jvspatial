"""RS256 signing-key store for the OAuth authorization server.

Generates/persists RSA keypairs as ``OAuthSigningKey`` Objects, exposes the
active signing key, and builds the JWKS (public keys only) the AS publishes.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple, cast

import jwt  # PyJWT
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from jvspatial.api.auth.oauth.models import OAuthSigningKey


def _generate_rsa_pem_pair() -> Tuple[str, str]:
    """Return ``(private_pem, public_pem)`` for a fresh RSA-2048 keypair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


async def generate_signing_key() -> OAuthSigningKey:
    """Create, persist, and return a new active RS256 signing key."""
    private_pem, public_pem = _generate_rsa_pem_pair()
    key = OAuthSigningKey(
        kid=uuid.uuid4().hex,
        public_pem=public_pem,
        private_pem=private_pem,
        algorithm="RS256",
        active=True,
    )
    await key.save()
    return key


async def get_active_signing_key() -> Optional[OAuthSigningKey]:
    """Return the active signing key (newest if several), or ``None``."""
    # Object.find() returns List[Object]; cast to our concrete subtype.
    active = cast(
        List[OAuthSigningKey],
        await OAuthSigningKey.find({"context.active": True}),
    )
    if not active:
        return None
    return sorted(active, key=lambda k: k.created_at, reverse=True)[0]


async def ensure_signing_key() -> OAuthSigningKey:
    """Return the active signing key, generating one if none exists."""
    existing = await get_active_signing_key()
    if existing is not None:
        return existing
    return await generate_signing_key()


async def _jwks_keys() -> List[OAuthSigningKey]:
    """Return all keys whose public half should appear in JWKS (active + recent)."""
    # Object.find() returns List[Object]; cast to our concrete subtype.
    return cast(List[OAuthSigningKey], await OAuthSigningKey.find({}))


async def build_jwks() -> Dict[str, Any]:
    """Build the JWKS document (public keys only) for the AS metadata."""
    keys = await _jwks_keys()
    jwks_keys: List[Dict[str, Any]] = []
    for k in keys:
        # Load the public key object from PEM so to_jwk can accept it.
        # PyJWT 2.x RSAAlgorithm.to_jwk requires a cryptography key object,
        # not a raw PEM string.
        public_key = serialization.load_pem_public_key(k.public_pem.encode("utf-8"))
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
        jwk.update({"kid": k.kid, "use": "sig", "alg": k.algorithm})
        jwk.pop("d", None)
        jwks_keys.append(jwk)
    return {"keys": jwks_keys}
