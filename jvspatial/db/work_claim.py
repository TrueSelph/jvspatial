"""DB-agnostic work-claim helpers for durable background processing.

Uses ``Database.find_one_and_update``, ``Database.find_one_and_delete``, and
``delete``. All built-in adapters provide these; atomicity is strongest on
MongoDB (native operations). JSON, SQLite, and DynamoDB use the default
read-modify-write / find-then-delete paths (best-effort under concurrency).

Env:
    ``JVSPATIAL_WORK_CLAIM_STALE_SECONDS`` (default TTL 600 seconds).
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Dict, Optional, Tuple

from jvspatial.env import env

logger = logging.getLogger(__name__)

_CLAIM_FIELD = "_jv_claim"
_CLAIM_UNTIL_FIELD = "_jv_claim_until"


def _stale_seconds() -> float:
    return (
        env("JVSPATIAL_WORK_CLAIM_STALE_SECONDS", default=600.0, parse=float) or 600.0
    )


async def claim_record(
    db: Any,
    collection: str,
    record_id: str,
    *,
    stale_seconds: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Atomically lease a document so only one worker processes it.

    Sets ``_jv_claim`` to a unique token and ``_jv_claim_until`` to
    ``now + stale_seconds``. A document is claimable when unclaimed or its
    lease has expired.

    Returns:
        ``(document_without_claim_fields, token)`` on success, or
        ``(None, None)`` when the record does not exist or is already claimed.
    """
    now = time.time()
    stale = stale_seconds if stale_seconds is not None else _stale_seconds()
    token = secrets.token_hex(16)
    query: Dict[str, Any] = {
        "_id": record_id,
        "$or": [
            {_CLAIM_FIELD: {"$exists": False}},
            {_CLAIM_UNTIL_FIELD: {"$lt": now}},
        ],
    }
    update = {"$set": {_CLAIM_FIELD: token, _CLAIM_UNTIL_FIELD: now + stale}}
    try:
        doc = await db.find_one_and_update(collection, query, update)
    except Exception as exc:
        logger.error("Failed to claim %s/%s: %s", collection, record_id, exc)
        return None, None
    if not doc:
        return None, None
    stripped = {k: v for k, v in doc.items() if not k.startswith("_jv_")}
    return stripped, token


async def release_claim(
    db: Any,
    collection: str,
    record_id: str,
    token: str,
) -> None:
    """Release a lease without deleting the underlying document."""
    try:
        await db.find_one_and_update(
            collection,
            {"_id": record_id, _CLAIM_FIELD: token},
            {"$unset": {_CLAIM_FIELD: "", _CLAIM_UNTIL_FIELD: ""}},
        )
    except Exception as exc:
        logger.warning("Failed to release claim %s/%s: %s", collection, record_id, exc)


async def delete_claimed_record(
    db: Any,
    collection: str,
    record_id: str,
    token: str,
) -> bool:
    """Delete a previously claimed record (only if the token still matches)."""
    try:
        deleted = await db.find_one_and_delete(
            collection,
            {"_id": record_id, _CLAIM_FIELD: token},
        )
        return deleted is not None
    except Exception as exc:
        logger.error("Failed to delete claimed %s/%s: %s", collection, record_id, exc)
        return False
