"""Reload-safety utilities for jvspatial apps running under uvicorn --reload.

When uvicorn spawns a reload worker it loads the application module twice:
first as ``__mp_main__``, then as the real module path.  The second load
gets cached submodules from the first run, so ``@endpoint`` decorators
never re-execute and the new server instance receives zero endpoints.

``evict_package`` solves this by removing a package and all of its
submodules from ``sys.modules`` so the next ``import`` triggers a fresh
load and re-registers every decorator with the current server.
"""

import sys
from typing import List


def evict_package(package: str) -> bool:
    """Remove a package and all submodules from ``sys.modules`` if cached.

    Safe to call unconditionally -- if nothing is cached the function is a
    no-op and returns ``False``.

    Args:
        package: Dotted module name to evict (e.g. ``"app.api"``).

    Returns:
        ``True`` when at least one entry was removed, ``False`` otherwise.
    """
    if package not in sys.modules:
        return False
    evicted: List[str] = [
        key
        for key in list(sys.modules.keys())
        if key == package or key.startswith(package + ".")
    ]
    for key in evicted:
        del sys.modules[key]
    return bool(evicted)


__all__ = ["evict_package"]
