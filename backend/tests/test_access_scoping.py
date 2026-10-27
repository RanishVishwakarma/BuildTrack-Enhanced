"""Clients get projects only by explicit grant; managers see only the
workers on their own projects (plus unassigned new hires)."""

from datetime import datetime

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app

API = "/api/v1"
IDS = {k: ObjectId() for k in ("admin", "pm", "client", "squatter", "mine", "theirs", "w_mine", "w_theirs", "w_new", "pay_theirs", "att_theirs")}
DAY = datetime(2026, 10, 20)


async def seed(db):
    def user(key, role, email):
        return {"_id": IDS[key], "email": email, "full_name": key, "role": role, "status": "active", "password_hash": hash_password("x")}

    await db.users.insert_many([user("admin", "admin", "admin@sc.io"), user("pm", "project_manager", "pm@sc.io"),
                                user("client", "client", "owner@sc.io"),
                                # signed up with the email another client uses on a project
                                user("squatter", "client", "theirs-client@sc.io")])
    await db.projects.insert_many([
        {"_id": IDS["mine"], "name": "Mine", "status": "active", "client_email": "owner@sc.io"},
        {"_id": IDS["theirs"], "name": "Theirs", "status": "active", "client_email": "theirs-client@sc.io"},
    ])
    await db.user_project_access.insert_one({"user_id": str(IDS["pm"]), "project_id": str(IDS["mine"]), "active": True})
    await db.workers.insert_many([
        {"_id": IDS["w_mine"], "first_name": "On", "last_name": "Mine", "email": "a@sc.io", "project_id": str(IDS["mine"]), "status": "assigned",
         "created_at": DAY, "updated_at": DAY},
        {"_id": IDS["w_theirs"], "first_name": "On", "last_name": "Theirs", "email": "b@sc.io", "project_id": str(IDS["theirs"]), "status": "assigned",
         "hourly_rate": 300, "created_at": DAY, "updated_at": DAY},
        {"_id": IDS["w_new"], "first_name": "New", "last_name": "Hire", "email": "c@sc.io", "status": "available", "created_at": DAY, "updated_at": DAY},
    ])
    await db.attendance.insert_one({"_id": IDS["att_theirs"], "worker_id": str(IDS["w_theirs"]), "project_id": str(IDS["theirs"]), "date": DAY,
                                    "status": "present", "created_at": DAY, "updated_at": DAY})
    await db.payroll.insert_one({"_id": IDS["pay_theirs"], "worker_id": str(IDS["w_theirs"]), "amount": 9000,
                                 "pay_period_start": DAY, "pay_period_end": DAY, "created_at": DAY, "updated_at": DAY})


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["scoping_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def auth(key):
    return {"Authorization": f"Bearer {create_access_token(str(IDS[key]))}"}


def project_names(client, who):
    data = client.get(f"{API}/projects", headers=auth(who)).json()
    rows = data if isinstance(data, list) else data.get("items", [])
    return sorted(p["name"] for p in rows)


# ------------------------------------------------------------ clients
def test_matching_email_alone_opens_no_project(env):
    client, _ = env
    assert project_names(client, "squatter") == []
    assert client.get(f"{API}/projects/{IDS['theirs']}", headers=auth("squatter")).status_code == 404


def test_naming_a_client_on_a_project_grants_and_moves_access(env):
    client, _ = env
    assert project_names(client, "client") == []  # email match no longer counts
    assert client.put(f"{API}/projects/{IDS['mine']}", json={"client_email": "owner@sc.io"}, headers=auth("pm")).status_code == 200
    assert project_names(client, "client") == ["Mine"]
    # The manager hands the project to another client: the first one loses it.
    assert client.put(f"{API}/projects/{IDS['mine']}", json={"client_email": "theirs-client@sc.io"}, headers=auth("pm")).status_code == 200
    assert project_names(client, "client") == [] and project_names(client, "squatter") == ["Mine"]


# ------------------------------------------------------------ workers
def worker_names(client, who, path="/workforce/workers"):
    return sorted(f"{w['first_name']} {w['last_name']}" for w in client.get(API + path, headers=auth(who)).json())


def test_manager_lists_only_own_project_workers_and_new_hires(env):
    client, _ = env
    assert worker_names(client, "pm") == ["New Hire", "On Mine"]
    assert worker_names(client, "pm", "/workforce/workers/available") == ["New Hire"]
    assert worker_names(client, "admin") == ["New Hire", "On Mine", "On Theirs"]


def test_another_projects_worker_is_hidden_everywhere(env):
    client, _ = env
    other = str(IDS["w_theirs"])
    for path in (f"/workforce/workers/{other}", f"/workforce/attendance/worker/{other}", f"/workforce/allocations/worker/{other}",
                 f"/workforce/shift-assignments/worker/{other}", f"/workforce/payroll/{IDS['pay_theirs']}"):
        assert client.get(API + path, headers=auth("pm")).status_code == 404, path
    assert client.get(f"{API}/workforce/payroll", params={"worker_id": other}, headers=auth("pm")).status_code == 404
    assert client.get(f"{API}/workforce/attendance", headers=auth("pm")).json() == []
    assert client.get(f"{API}/workforce/payroll", headers=auth("pm")).json() == []


def test_manager_cannot_act_on_another_projects_worker(env):
    client, _ = env
    other = str(IDS["w_theirs"])
    assert client.post(f"{API}/workforce/attendance", json={"worker_id": other, "date": "2026-10-21", "status": "absent"}, headers=auth("pm")).status_code == 404
    assert client.put(f"{API}/workforce/attendance/{IDS['att_theirs']}", json={"status": "absent"}, headers=auth("pm")).status_code == 404
    assert client.put(f"{API}/workforce/workers/{other}", json={"hourly_rate": 1}, headers=auth("pm")).status_code == 404
    # Own project's worker still works.
    assert client.post(f"{API}/workforce/attendance", json={"worker_id": str(IDS["w_mine"]), "date": "2026-10-21", "status": "present"},
                       headers=auth("pm")).status_code == 200
