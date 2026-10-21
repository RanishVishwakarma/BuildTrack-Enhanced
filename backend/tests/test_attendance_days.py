"""Attendance is one record per worker per site calendar day."""

from datetime import datetime, timezone

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app
from app.modules.workforce.attendance_dates import hours_between, work_day

API = "/api/v1/workforce/attendance"
IDS = {k: ObjectId() for k in ("pm", "worker")}


def test_work_day_rules(monkeypatch):
    monkeypatch.setattr(settings, "app_timezone", "Asia/Kolkata")
    assert work_day(datetime(2026, 10, 18)) == datetime(2026, 10, 18)  # already a day
    assert work_day(datetime(2026, 10, 17, 18, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 18)  # IST midnight
    assert work_day(datetime(2026, 10, 17, 18, 30)) == datetime(2026, 10, 18)  # legacy naive UTC
    assert work_day(datetime(2026, 10, 18, 10, 0)) == datetime(2026, 10, 18)
    assert hours_between(datetime(2026, 10, 18, 3, 30), datetime(2026, 10, 18, 12, 0)) == 8.5


async def seed(db):
    await db.users.insert_one({"_id": IDS["pm"], "email": "pm@att-tests.io", "full_name": "PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")})
    await db.workers.insert_one({"_id": IDS["worker"], "first_name": "Ravi", "last_name": "K", "email": "ravi@att-tests.io", "status": "available"})


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "app_timezone", "Asia/Kolkata")
    db = AsyncMongoMockClient()["attendance_days_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def auth():
    return {"Authorization": f"Bearer {create_access_token(str(IDS['pm']))}"}


def mark(client, date, status):
    return client.post(API, json={"worker_id": str(IDS["worker"]), "date": date, "status": status}, headers=auth())


def test_marking_twice_updates_the_same_day(env):
    client, db = env
    first = mark(client, "2026-10-18", "present").json()
    # An older client sending IST midnight as a UTC instant lands on the same day.
    second = mark(client, "2026-10-17T18:30:00.000Z", "absent").json()
    assert first["_id"] == second["_id"] and second["status"] == "absent"
    assert anyio.run(db.attendance.count_documents, {}) == 1
    assert second["date"].startswith("2026-10-18T00:00:00")


def test_day_listing_and_times_carry_a_zone(env):
    client, _ = env
    created = mark(client, "2026-10-18", "present").json()
    mark(client, "2026-10-17", "leave")
    client.put(f"{API}/{created['_id']}", json={"check_in_time": "2026-10-18T03:30:00Z", "check_out_time": "2026-10-18T12:00:00Z"}, headers=auth())

    day = client.get(API, params={"date": "2026-10-18"}, headers=auth()).json()
    assert len(day) == 1 and day[0]["status"] == "present"
    assert day[0]["check_in_time"].endswith("Z") or day[0]["check_in_time"].endswith("+00:00")
    assert day[0]["hours_worked"] == 8.5
