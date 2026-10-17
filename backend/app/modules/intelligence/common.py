"""Small helpers shared by the intelligence services."""

from datetime import date, datetime, timezone
from typing import Any

from bson import ObjectId

# Statuses that mean "work on this is finished" across the modules' vocabularies.
DONE_STATUSES = {"completed", "complete", "done", "closed", "cancelled", "canceled"}


def utcnow() -> datetime:
    """Current UTC time. Tests monkeypatch this to freeze the clock."""
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> datetime | None:
    """Parse the mix of datetimes and ISO strings stored across collections."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        for candidate in (text, text.split("T")[0], text.split(" ")[0]):
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def is_done(status: Any) -> bool:
    return norm_text(status) in DONE_STATUSES


def iso(value: Any) -> str | None:
    parsed = parse_dt(value)
    return parsed.isoformat() if parsed else None


def clean(value: Any) -> Any:
    """Make Mongo documents JSON-safe (ObjectId -> str, datetime -> ISO)."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    return value


def ref(kind: str, record: dict, label: str | None = None) -> dict:
    """A source reference the UI can show next to a finding."""
    return {"type": kind, "id": str(record.get("_id")), "label": label or record.get("name") or record.get("title") or str(record.get("_id"))}
