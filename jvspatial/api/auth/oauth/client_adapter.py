"""Authlib ``ClientMixin`` adapter over the stored ``OAuthClient`` record."""

from __future__ import annotations

from authlib.oauth2.rfc6749 import ClientMixin

from jvspatial.api.auth.oauth.models import OAuthClient, verify_client_secret


class OAuthClientAdapter(ClientMixin):
    """Wrap an ``OAuthClient`` so Authlib can validate redirect/grant/scope/auth."""

    def __init__(self, client: OAuthClient) -> None:
        self.client = client

    def get_client_id(self) -> str:
        """Return the public client identifier."""
        return self.client.client_id

    def get_default_redirect_uri(self):
        """Return the first registered redirect URI, or None if none registered."""
        uris = self.client.redirect_uris or []
        return uris[0] if uris else None

    def get_allowed_scope(self, scope: str) -> str:
        """Filter *scope* to only the scopes allowed for this client."""
        if not scope:
            return ""
        allowed = set((self.client.scope or "").split())
        return " ".join(s for s in scope.split() if s in allowed)

    def check_redirect_uri(self, redirect_uri: str) -> bool:
        """Return True only when *redirect_uri* is in the registered list."""
        return redirect_uri in (self.client.redirect_uris or [])

    def check_client_secret(self, client_secret: str) -> bool:
        """Constant-time verify *client_secret* against the stored hash."""
        if not self.client.client_secret_hash:
            return False
        return verify_client_secret(client_secret, self.client.client_secret_hash)

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        """Return True when *method* matches the client's registered auth method."""
        return method == (self.client.token_endpoint_auth_method or "none")

    def check_response_type(self, response_type: str) -> bool:
        """Return True when *response_type* is in the client's allowed list."""
        return response_type in (self.client.response_types or [])

    def check_grant_type(self, grant_type: str) -> bool:
        """Return True when *grant_type* is in the client's allowed list."""
        return grant_type in (self.client.grant_types or [])
