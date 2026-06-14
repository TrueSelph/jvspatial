"""Flatten FastAPI/Starlette route trees.

Starlette >= 0.52 changed ``app.include_router(...)``: instead of expanding the
included ``APIRoute`` objects directly into ``app.routes``, it inserts a single
``_IncludedRouter`` wrapper whose real routes live on ``.original_router.routes``.
Older Starlette flattened them inline.

jvspatial introspects the route table in several places (auth resolution,
OpenAPI security wiring, duplicate-route detection). Those call sites must
recurse through included routers and mounts to find the actual endpoints, or
included routes (e.g. the file-storage endpoints) become invisible — which makes
the auth resolver deny-by-default and return 401 for routes that should be
public. ``iter_api_routes`` yields every ``APIRoute`` regardless of Starlette
version.
"""

from typing import Iterable, Iterator

from fastapi.routing import APIRoute

__all__ = ["iter_api_routes"]


def iter_api_routes(routes: Iterable) -> Iterator[APIRoute]:
    """Yield every ``APIRoute`` in ``routes``, recursing into nested routers/mounts.

    Handles three shapes:
    - a plain ``APIRoute`` (yielded directly);
    - a Starlette >= 0.52 ``_IncludedRouter`` wrapper (recurse via
      ``original_router.routes``);
    - a ``Mount`` / sub-application (recurse via ``routes``).
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        # Starlette >= 0.52 include_router() wrapper.
        original = getattr(route, "original_router", None)
        if original is not None and hasattr(original, "routes"):
            yield from iter_api_routes(original.routes)
            continue
        # Mounts / sub-apps expose nested routes via ``.routes``.
        sub = getattr(route, "routes", None)
        if sub:
            yield from iter_api_routes(sub)
