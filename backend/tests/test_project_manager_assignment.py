"""Admins assign projects to project managers; the assigned manager (and only
they) gets access, and a manager cannot hand a project to another manager."""

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app

API = "/api/v1"
U = {k: ObjectId() for k in ("admin", "pm", "pm2")}


async def seed(db):
    await db.users.insert_many([
        {"_id": U["admin"], "email": "admin@example.org", "full_name": "Admin", "role": "admin", "status": "active", "password_hash": hash_password("x")},
        {"_id": U["pm"], "email": "priya@example.org", "full_name": "Priya PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")},
        {"_id": U["pm2"], "email": "rahul@example.org", "full_name": "Rahul PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")},
    ])


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["pm_assign_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def call(client, method, path, who, **kwargs):
    return client.request(method, API + path, headers={"Authorization": f"Bearer {create_access_token(str(U[who]))}"}, **kwargs)


def names(client, who):
    return sorted(p["name"] for p in call(client, "GET", "/projects", who).json())


def new_project(client, who, name, manager=None):
    body = {"name": name, "start_date": "2026-11-01T00:00:00", **({"project_manager_id": manager} if manager else {})}
    return call(client, "POST", "/projects", who, json=body)


def test_admin_assigns_and_reassigns_a_project(client):
    created = new_project(client, "admin", "Tower C", str(U["pm"])).json()
    assert created["project_manager_id"] == str(U["pm"]) and created["project_manager_name"] == "Priya PM"
    assert names(client, "pm") == ["Tower C"] and names(client, "pm2") == []

    moved = call(client, "PUT", f"/projects/{created['_id']}", "admin", json={"project_manager_id": str(U["pm2"])}).json()
    assert moved["project_manager_name"] == "Rahul PM"
    assert names(client, "pm") == [] and names(client, "pm2") == ["Tower C"]


def test_unassigned_project_is_seen_by_no_manager(client):
    new_project(client, "admin", "Hospital Annex")
    assert names(client, "pm") == [] and names(client, "pm2") == [] and names(client, "admin") == ["Hospital Annex"]


def test_manager_manages_own_project_and_cannot_hand_it_over(client):
    mine = new_project(client, "pm", "Villa 7").json()
    assert mine["project_manager_id"] == str(U["pm"]) and names(client, "pm2") == []
    refused = call(client, "PUT", f"/projects/{mine['_id']}", "pm", json={"project_manager_id": str(U["pm2"])})
    assert refused.status_code == 403 and "administrator" in refused.json()["detail"]
    assert new_project(client, "pm", "Villa 8", str(U["pm2"])).status_code == 403
    assert names(client, "pm") == ["Villa 7"]  # the refused create left nothing behind


def test_managers_list_offers_a_manager_only_themselves(client):
    assert [m["email"] for m in call(client, "GET", "/auth/managers", "pm").json()] == ["priya@example.org"]
    assert len(call(client, "GET", "/auth/managers", "admin").json()) == 2


def test_older_projects_with_a_manager_name_still_resolve(client):
    created = new_project(client, "admin", "Old style", "Rahul PM").json()  # display name, as older records stored
    assert created["project_manager_id"] == str(U["pm2"]) and names(client, "pm2") == ["Old style"]
