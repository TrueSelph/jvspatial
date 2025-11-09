"""Manager classes for file storage operations.

This package provides high-level managers for various storage operations,
including URL proxy management, file management, and metadata handling.
"""

from .proxy import URLProxyManager, get_proxy_manager

__all__ = [
    "URLProxyManager",
    "get_proxy_manager",
]
