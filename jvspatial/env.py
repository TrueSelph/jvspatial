"""Live environment helpers for jvspatial."""

from __future__ import annotations

import os
from typing import Any, Callable, List, Literal, Optional

from jvspatial.runtime.serverless import is_serverless_mode


def env(
    name: str,
    default: Any = None,
    *,
    strip: bool = True,
    parse: Optional[Callable[[str], Any]] = None,
) -> Any:
    """Read live env var and optionally parse it.

    Returns ``default`` when value is unset/blank or parsing fails.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip() if strip else raw
    if not value:
        return default
    if parse is None:
        return value
    try:
        return parse(value)
    except (TypeError, ValueError):
        return default


def parse_bool(value: str) -> bool:
    """Parse true/false, 1/0, yes/no, on/off."""
    lowered = str(value).strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"Invalid boolean: {value}")


def parse_bool_basic(value: str) -> bool:
    """Parse true/false, 1/0, yes/no (without on/off)."""
    lowered = str(value).strip().lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    raise ValueError(f"Invalid boolean: {value}")


def parse_csv(value: str) -> List[str]:
    """Parse comma-delimited string into non-empty trimmed items."""
    return [part.strip() for part in str(value).split(",") if part.strip()]


def normalize_optional_secret_string(value: Optional[str]) -> Optional[str]:
    """Treat unset, blank, and common null placeholders as no secret."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lower() in ("null", "none", "undefined", "(null)", "nil"):
        return None
    return s


def parse_optional_nonnegative_int(value: Optional[str]) -> Optional[int]:
    """Parse env-like string to int; None if unset/invalid/negative."""
    if value is None or not str(value).strip():
        return None
    try:
        n = int(value)
        return n if n >= 0 else None
    except ValueError:
        return None


def resolve_file_storage_root(
    merged_root: Optional[str] = None,
    *,
    serverless: Optional[bool] = None,
) -> str:
    """Resolve local filesystem root for stored files."""
    if serverless is None:
        serverless = is_serverless_mode()

    files = env("JVSPATIAL_FILES_ROOT_PATH")
    merged = merged_root.strip() if isinstance(merged_root, str) else merged_root
    default = "/tmp/.files" if serverless else "./.files"
    if files:
        return files
    if merged:
        return merged
    return default


def resolve_db_paths(*, serverless: Optional[bool] = None) -> tuple[str, str]:
    """Resolve JSON and SQLite DB paths from env/defaults."""
    if serverless is None:
        serverless = is_serverless_mode()
    generic = env("JVSPATIAL_DB_PATH")
    default_json = "/tmp/jvdb" if serverless else "jvdb"
    default_sqlite = (
        "/tmp/jvdb/sqlite/jvspatial.db" if serverless else "jvdb/sqlite/jvspatial.db"
    )
    resolved = generic or default_sqlite
    return (generic or default_json, resolved)


def resolve_api_prefix() -> str:
    """Return API prefix, defaulting to ``/api``."""
    return env("JVSPATIAL_API_PREFIX", default="/api")


def resolve_files_route_base() -> str:
    """Return normalized base route for file-serving endpoints."""
    prefix = resolve_api_prefix().strip().rstrip("/")
    return f"{prefix}/files" if prefix else "/files"


def resolve_aws_region() -> str:
    """Return AWS region from env vars, falling back to ``us-east-1``."""
    return (
        os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
    ).strip() or "us-east-1"


EnvironmentMode = Literal["development", "production"]


def get_environment_mode(
    config_fallback: Optional[Callable[[], Optional[str]]] = None,
) -> EnvironmentMode:
    """Get current environment mode."""
    raw = os.getenv("JVSPATIAL_ENVIRONMENT")
    if raw is not None and str(raw).strip():
        mode = str(raw).strip().lower()
        return "production" if mode == "production" else "development"
    if config_fallback is not None:
        val = config_fallback()
        if val is not None:
            return "production" if val.lower() == "production" else "development"
    return "development"


def is_development_mode(
    config_fallback: Optional[Callable[[], Optional[str]]] = None,
) -> bool:
    """Return True when current environment mode is development."""
    return get_environment_mode(config_fallback) == "development"


def is_production_mode(
    config_fallback: Optional[Callable[[], Optional[str]]] = None,
) -> bool:
    """Return True when current environment mode is production."""
    return get_environment_mode(config_fallback) == "production"


_DEFAULT_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


def resolve_cors_origins() -> List[str]:
    """Return configured CORS origins or development defaults."""
    return env(
        "JVSPATIAL_CORS_ORIGINS",
        default=list(_DEFAULT_DEV_CORS_ORIGINS),
        parse=parse_csv,
    )
