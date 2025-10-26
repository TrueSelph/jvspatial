"""Exception handlers for the jvspatial API.

This module provides FastAPI exception handlers for the standardized
exception hierarchy, ensuring consistent error responses.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from jvspatial.api.exceptions import JVSpatialAPIException

logger = logging.getLogger(__name__)


async def jvspatial_exception_handler(
    request: Request, exc: JVSpatialAPIException
) -> JSONResponse:
    """Handle JVSpatialAPIException instances.

    Args:
        request: The FastAPI request
        exc: The exception instance

    Returns:
        JSON response with error details
    """
    # Log the error
    if exc.status_code >= 500:
        logger.error(
            f"API Error [{exc.error_code}]: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "status_code": exc.status_code,
                "details": exc.details,
                "path": request.url.path,
                "method": request.method,
            },
            exc_info=True,
        )
    else:
        logger.warning(
            f"API Error [{exc.error_code}]: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "status_code": exc.status_code,
                "path": request.url.path,
                "method": request.method,
            },
        )

    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle generic exceptions.

    Args:
        request: The FastAPI request
        exc: The exception instance

    Returns:
        JSON response with generic error
    """
    logger.error(
        f"Unhandled exception: {exc}",
        extra={"path": request.url.path, "method": request.method},
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal_error",
            "message": "An internal error occurred",
        },
    )


def register_exception_handlers(app: FastAPI, debug: bool = False) -> None:
    """Register all exception handlers on the FastAPI app.

    Args:
        app: The FastAPI application instance
        debug: Whether to include exception details in responses
    """
    # Register JVSpatialAPIException handler
    app.add_exception_handler(JVSpatialAPIException, jvspatial_exception_handler)

    # Register generic exception handler (only if not in debug mode)
    if not debug:
        app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Exception handlers registered")


__all__ = [
    "jvspatial_exception_handler",
    "generic_exception_handler",
    "register_exception_handlers",
]
