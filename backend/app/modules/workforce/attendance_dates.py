"""Attendance is kept per calendar day on site.

`date` is stored as midnight of the site's calendar day with no time zone
(e.g. 2026-10-18T00:00:00), so it reads back as the same day everywhere.
Check-in and check-out are real instants, stored in UTC and returned with
their zone so the browser shows local times.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def site_zone() -> ZoneInfo:
    return ZoneInfo(settings.app_timezone)


def work_day(value: datetime | None) -> datetime | None:
    """Calendar day (naive midnight) for an attendance date.

    A date-only value is already a day. A value with a zone is an instant
    and is converted to the site zone first. A naive value with a time
    (records saved before this rule) was stored as UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
            return value
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(site_zone())
    return datetime(local.year, local.month, local.day)


def as_utc(value):
    """Mark a stored (naive UTC) instant as UTC for the API response."""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def hours_between(check_in: datetime | None, check_out: datetime | None) -> float | None:
    if not check_in or not check_out:
        return None
    seconds = (as_utc(check_out) - as_utc(check_in)).total_seconds()
    return round(seconds / 3600, 2) if seconds > 0 else None
