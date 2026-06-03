"""Starlette bindings for Authlib's framework-agnostic request objects.

We subclass ``OAuth2Request`` and override ``args`` (query params) and ``form``
(body params) to return plain dicts — the version-portable binding that avoids
the deprecated ``OAuth2Request(body=...)`` / ``request.data`` paths (Authlib
1.6+). ``build_oauth2_request`` constructs one from a Starlette ``Request`` in
the async handler before handing off to the (threaded) sync Authlib call.
"""

from __future__ import annotations

from typing import Dict

from authlib.oauth2.rfc6749 import OAuth2Request


class StarletteOAuth2Request(OAuth2Request):
    """``OAuth2Request`` backed by pre-extracted Starlette query/form dicts."""

    def __init__(
        self,
        method: str,
        uri: str,
        query: Dict[str, str],
        form: Dict[str, str],
        headers: Dict[str, str],
    ) -> None:
        """Initialise with pre-extracted query and form dicts."""
        super().__init__(method, uri, headers=headers)
        self._query = dict(query or {})
        self._form = dict(form or {})

    @property
    def args(self) -> Dict[str, str]:
        """Return query-string parameters as a plain dict."""
        return self._query

    @property
    def form(self) -> Dict[str, str]:
        """Return form-body parameters as a plain dict."""
        return self._form


async def build_oauth2_request(request) -> StarletteOAuth2Request:
    """Build a ``StarletteOAuth2Request`` from a Starlette ``Request`` (async)."""
    form: Dict[str, str] = {}
    if request.method in ("POST", "PUT", "PATCH"):
        raw = await request.form()
        form = dict(raw.items())
    return StarletteOAuth2Request(
        method=request.method,
        uri=str(request.url),
        query=dict(request.query_params),
        form=form,
        headers=dict(request.headers),
    )
