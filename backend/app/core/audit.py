"""Append-only audit log for security-sensitive and operational events.

Records go to the `audit_logs` collection. There is deliberately no update or
delete helper. Never pass passwords, tokens or API keys in `details`.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

_REDACT = ("password", "token", "secret", "api_key", "apikey", "authorization")


def _clean(details: dict | None) -> dict:
    if not details:
        return {}
    return {
        key: ("[redacted]" if any(word in key.lower() for word in _REDACT) else value)
        for key, value in details.items()
    }


async def record_audit(
    db,
    event_type: str,
    *,
    actor: dict | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    project_id: str | None = None,
    outcome: str = "success",
    details: dict | None = None,
    correlation_id: str | None = None,
) -> None:
    """Write one audit event. Failures are logged, never raised to the caller."""
    record = {
        "event_type": event_type,
        "actor_id": str(actor["_id"]) if actor and actor.get("_id") else None,
        "actor_role": actor.get("role") if actor else None,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id is not None else None,
        "project_id": str(project_id) if project_id is not None else None,
        "outcome": outcome,
        "details": _clean(details),
        "correlation_id": correlation_id or uuid4().hex,
        "timestamp": datetime.now(timezone.utc),
    }
    try:
        await db.audit_logs.insert_one(record)
    except Exception:  # an audit failure must not break the request
        logger.exception("Failed to write audit event %s", event_type)
