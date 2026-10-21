"""Self-registered staff accounts wait for approval; managers only manage
logins for workers on their own projects."""

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app

API = "/api/v1"
IDS = {k: ObjectId() for k in ("admin", "pm", "mine", "theirs", "on_mine", "on_theirs", "unassigned")}


async def seed(db):
    await db.users.insert_many([
        {"_id": IDS["admin"], "email": "admin@su-tests.io", "full_name": "Admin", "role": "admin", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["pm"], "email": "pm@su-tests.io", "full_name": "PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")},
    ])
    await db.projects.insert_many([{"_id": IDS["mine"], "name": "Mine", "status": "active"}, {"_id": IDS["theirs"], "name": "Theirs", "status": "active"}])
    await db.user_project_access.insert_one({"user_id": str(IDS["pm"]), "project_id": str(IDS["mine"]), "active": True})
    await db.workers.insert_many([
        {"_id": IDS["on_mine"], "first_name": "A", "last_name": "Mine", "email": "a@su-tests.io", "project_id": str(IDS["mine"]), "status": "assigned"},
        {"_id": IDS["on_theirs"], "first_name": "B", "last_name": "Theirs", "email": "b@su-tests.io", "project_id": str(IDS["theirs"]), "status": "assigned"},
        {"_id": IDS["unassigned"], "first_name": "C", "last_name": "New", "email": "c@su-tests.io", "status": "available"},
    ])


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["signup_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def auth(who):
    return {"Authorization": f"Bearer {create_access_token(str(IDS[who]))}"}


def register(client, email, role):
    return client.post(f"{API}/auth/register", json={"full_name": "New Person", "email": email, "password": "long-enough-1", "role": role})


def login(client, email):
    return client.post(f"{API}/auth/login", json={"email": email, "password": "long-enough-1"})


@pytest.mark.parametrize("role", ["project_manager", "site_engineer", "contractor"])
def test_staff_signup_waits_for_admin_approval(client, role):
    created = register(client, f"{role}@su-tests.io", role).json()
    assert created["pending_approval"] is True and created["user"]["status"] == "pending"
    refused = login(client, f"{role}@su-tests.io")
    assert refused.status_code == 403 and "waiting for an administrator" in refused.json()["detail"]

    assert client.post(f"{API}/auth/users/{created['user']['_id']}/status", params={"status_value": "active"}, headers=auth("admin")).status_code == 200
    assert login(client, f"{role}@su-tests.io").status_code == 200


@pytest.mark.parametrize("role", ["worker", "client"])
def test_worker_and_client_signup_stay_active(client, role):
    created = register(client, f"{role}@su-tests.io", role).json()
    assert created["pending_approval"] is False and login(client, f"{role}@su-tests.io").status_code == 200


def test_manager_cannot_take_over_another_projects_workers(client):
    url = f"{API}/workforce/workers/{{}}/login"
    body = {"password": "worker-pass-1"}
    assert client.post(url.format(IDS["on_theirs"]), json=body, headers=auth("pm")).status_code == 404
    assert client.post(url.format(IDS["on_theirs"]) + "/link", json={"email": "pm@su-tests.io"}, headers=auth("pm")).status_code == 404
    assert client.post(url.format(IDS["on_mine"]), json=body, headers=auth("pm")).status_code == 201
    assert client.post(url.format(IDS["unassigned"]), json=body, headers=auth("pm")).status_code == 201  # new hire, no project yet
    # An admin sees every project.
    assert client.post(url.format(IDS["on_theirs"]), json=body, headers=auth("admin")).status_code == 201
    assert client.put(url.format(IDS["on_theirs"]) + "/password", json=body, headers=auth("pm")).status_code == 404
    assert client.delete(url.format(IDS["on_theirs"]), headers=auth("pm")).status_code == 404
