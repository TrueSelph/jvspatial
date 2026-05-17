"""Request-parameter detection with ``from __future__ import annotations``.

Upstream report: ``wrap_function_with_params`` relied on raw
``param.annotation`` values. With PEP 563 (or quoted forward refs)
the annotation is a *string* like ``"Request"`` — never matches
``FastAPIRequest`` / ``StarletteRequest`` and never matches the
``__name__`` / ``__module__`` heuristic. Result: the wrapper failed
to detect the caller's Request parameter and corrupted the route
signature.

``ParameterModelFactory._create_function_model`` already calls
``typing.get_type_hints(func)``; this fix mirrors that resolution in
``_find_request_parameter`` so both paths agree.
"""

from __future__ import annotations

import inspect

from fastapi import Request

from jvspatial.api.decorators.function_wrappers import _find_request_parameter


def _handler_with_pep563(request: Request, x: int) -> dict:
    """Function whose annotations are strings under PEP 563."""
    return {"x": x}


def _handler_no_request(x: int, y: int) -> dict:
    return {"x": x, "y": y}


def test_request_detected_under_pep563_when_func_passed():
    sig = inspect.signature(_handler_with_pep563)
    # Raw annotation IS a string under ``from __future__ import annotations``.
    assert isinstance(sig.parameters["request"].annotation, str)

    # ``_find_request_parameter`` resolves type hints when ``func`` is supplied.
    has_request, name = _find_request_parameter(sig, _handler_with_pep563)
    assert has_request is True
    assert name == "request"


def test_no_request_param_returns_false():
    sig = inspect.signature(_handler_no_request)
    has_request, name = _find_request_parameter(sig, _handler_no_request)
    assert has_request is False
    assert name is None


def test_back_compat_without_func_argument():
    """Calling without ``func`` still works (legacy signature)."""
    sig = inspect.signature(_handler_no_request)
    has_request, _ = _find_request_parameter(sig)
    # No request param: still False either way.
    assert has_request is False
