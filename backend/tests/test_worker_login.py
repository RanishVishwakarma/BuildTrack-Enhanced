"""Worker logins are linked by a saved worker_id, never by matching email."""

from datetime import datetime

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.security import create_access_token, hash_password, verify_password
from app.db.mongodb import get_database
from app.main import app

API = "/api/v1"
IDS = {k: ObjectId() for k in ("pm", "engineer", "squatter", "ravi", "sunil", "vendor_user")}


async def seed(db):
    await db.users.insert_many([
        {"_id": IDS["pm"], "email": "pm@wl-tests.io", "full_name": "PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["engineer"], "email": "se@wl-tests.io", "full_name": "SE", "role": "site_engineer", "status": "active", "password_hash": hash_password("x")},
        # Registered themselves with Ravi's email before Ravi got a login.
        {"_id": IDS["squatter"], "email": "ravi@wl-tests.io", "full_name": "Not Ravi", "role": "worker", "status": "active", "password_hash": hash_password("x")},
        # A vendor login with no vendor record link.
        {"_id": IDS["vendor_user"], "email": "v@wl-tests.io", "full_name": "Ravi", "role": "vendor", "status": "active", "password_hash": hash_password("x")},
    ])
    await db.workers.insert_many([
        {"_id": IDS["ravi"], "first_name": "Ravi", "last_name": "Kumar", "email": "ravi@wl-tests.io", "hourly_rate": 300, "status": "active"},
        {"_id": IDS["sunil"], "first_name": "Sunil", "last_name": "Rao", "email": "sunil@wl-tests.io", "hourly_rate": 250, "status": "active"},
    ])
    await db.vendors.insert_one({"vendor_name": "Shree Cement", "contact_person": "Ravi", "email": "v@wl-tests.io", "status": "active"})
    await db.payroll.insert_one({"worker_id": str(IDS["ravi"]), "amount": 21000, "pay_period_start": datetime(2026, 9, 1), "pay_period_end": datetime(2026, 9, 30)})


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["worker_login_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def auth(user_id):
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def payroll(client, who, worker="ravi"):
    return client.get(f"{API}/workforce/payroll", params={"worker_id": str(IDS[worker])}, headers=auth(who))


def test_matching_email_alone_grants_nothing(env):
    client, _ = env
    assert payroll(client, IDS["squatter"]).status_code == 403
    login = client.post(f"{API}/auth/login", json={"email": "ravi@wl-tests.io", "password": "x"}).json()
    assert login["worker_id"] is None


def test_pm_creates_login_and_worker_sees_own_records(env):
    client, db = env
    created = client.post(f"{API}/workforce/workers/{IDS['sunil']}/login", json={"password": "sunil-2026"}, headers=auth(IDS["pm"]))
    assert created.status_code == 201 and created.json()["login_email"] == "sunil@wl-tests.io"
    user = anyio.run(db.users.find_one, {"email": "sunil@wl-tests.io"})
    assert user["role"] == "worker" and user["worker_id"] == str(IDS["sunil"])

    login = client.post(f"{API}/auth/login", json={"email": "sunil@wl-tests.io", "password": "sunil-2026"}).json()
    assert login["worker_id"] == str(IDS["sunil"]) and login["user"]["worker_id"] == str(IDS["sunil"])
    assert payroll(client, user["_id"], "sunil").status_code == 200
    assert payroll(client, user["_id"], "ravi").status_code == 403

    rows = client.get(f"{API}/workforce/workers", headers=auth(IDS["pm"])).json()
    assert {r["first_name"]: r["login_email"] for r in rows} == {"Ravi": None, "Sunil": "sunil@wl-tests.io"}
    again = client.post(f"{API}/workforce/workers/{IDS['sunil']}/login", json={"password": "sunil-2026"}, headers=auth(IDS["pm"]))
    assert again.status_code == 409


def test_existing_email_must_be_linked_deliberately(env):
    client, _ = env
    response = client.post(f"{API}/workforce/workers/{IDS['ravi']}/login", json={"password": "ravi-2026x"}, headers=auth(IDS["pm"]))
    assert response.status_code == 409 and "Link existing account" in response.json()["detail"]
    # Linking a manager account to a worker record is refused.
    assert client.post(f"{API}/workforce/workers/{IDS['ravi']}/login/link", json={"email": "se@wl-tests.io"}, headers=auth(IDS["pm"])).status_code == 400

    assert client.post(f"{API}/workforce/workers/{IDS['ravi']}/login/link", json={"email": "ravi@wl-tests.io"}, headers=auth(IDS["pm"])).status_code == 200
    assert payroll(client, IDS["squatter"]).status_code == 200
    # One login per worker, one worker per login.
    assert client.post(f"{API}/workforce/workers/{IDS['sunil']}/login/link", json={"email": "ravi@wl-tests.io"}, headers=auth(IDS["pm"])).status_code == 409

    assert client.delete(f"{API}/workforce/workers/{IDS['ravi']}/login", headers=auth(IDS["pm"])).status_code == 200
    assert payroll(client, IDS["squatter"]).status_code == 403


def test_reset_password_and_permission(env):
    client, db = env
    client.post(f"{API}/workforce/workers/{IDS['sunil']}/login", json={"password": "sunil-2026"}, headers=auth(IDS["pm"]))
    url = f"{API}/workforce/workers/{IDS['sunil']}/login/password"
    assert client.put(url, json={"password": "short"}, headers=auth(IDS["pm"])).status_code == 422
    assert client.put(url, json={"password": "new-pass-1"}, headers=auth(IDS["engineer"])).status_code == 403
    assert client.put(url, json={"password": "new-pass-1"}, headers=auth(IDS["pm"])).status_code == 200
    assert verify_password("new-pass-1", anyio.run(db.users.find_one, {"email": "sunil@wl-tests.io"})["password_hash"])
    assert client.post(f"{API}/workforce/workers/{IDS['ravi']}/login", json={"password": "long-enough"}, headers=auth(IDS["engineer"])).status_code == 403


def test_unlinked_vendor_login_is_not_matched_by_name(env):
    client, db = env
    response = client.get(f"{API}/procurement/vendor/purchase-orders", headers=auth(IDS["vendor_user"]))
    assert response.status_code == 403 and "not linked" in response.json()["detail"]
    assert anyio.run(db.users.find_one, {"_id": IDS["vendor_user"]}).get("vendor_id") is None


def test_worker_schedule_shows_only_own_shifts(env):
    client, db = env
    morning, night = ObjectId(), ObjectId()

    async def shifts():
        now = datetime(2026, 10, 18)
        await db.shifts.insert_many([
            {"_id": morning, "name": "Morning", "start_time": "08:00", "end_time": "16:00", "status": "ACTIVE", "created_at": now, "updated_at": now},
            {"_id": night, "name": "Night", "start_time": "20:00", "end_time": "04:00", "status": "ACTIVE", "created_at": now, "updated_at": now},
        ])
        await db.shift_assignments.insert_one({"worker_id": str(IDS["sunil"]), "shift_id": str(morning), "date": now, "status": "ACTIVE",
                                               "created_at": now, "updated_at": now})

    anyio.run(shifts)
    client.post(f"{API}/workforce/workers/{IDS['sunil']}/login", json={"password": "sunil-2026"}, headers=auth(IDS["pm"]))
    sunil = anyio.run(db.users.find_one, {"email": "sunil@wl-tests.io"})

    listed = client.get(f"{API}/workforce/shifts", headers=auth(sunil["_id"]))
    assert listed.status_code == 200 and [s["name"] for s in listed.json()] == ["Morning"]
    mine = client.get(f"{API}/workforce/shift-assignments", params={"worker_id": str(IDS["sunil"])}, headers=auth(sunil["_id"]))
    assert mine.status_code == 200 and len(mine.json()) == 1
    # Not linked: nothing.
    assert client.get(f"{API}/workforce/shifts", headers=auth(IDS["squatter"])).status_code == 403
    assert len(client.get(f"{API}/workforce/shifts", headers=auth(IDS["pm"])).json()) == 2
