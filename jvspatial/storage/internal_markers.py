"""Internal storage objects (not user uploads) that must bypass strict MIME allowlists."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def should_skip_mime_allowlist(
    file_path: str, metadata: Optional[Dict[str, Any]]
) -> bool:
    """True for directory/sandbox placeholder objects saved with empty or tiny bodies."""
    meta = metadata or {}
    name = Path(file_path).name
    if name == ".jvdirectory" and meta.get("type") == "directory":
        return True
    if name == ".jvagent_sandbox" and str(meta.get("sandbox") or "") == "1":
        return True
    return False


def trivial_marker_validation(file_path: str, content: bytes) -> Dict[str, Any]:
    """Synthetic validation result for internal markers (no MIME allowlist)."""
    filename = Path(file_path).name
    return {
        "valid": True,
        "mime_type": "text/plain",
        "size_bytes": len(content),
        "extension": Path(filename).suffix.lower(),
        "filename": filename,
    }
