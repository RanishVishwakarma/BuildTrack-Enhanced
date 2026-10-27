"""Hierarchy: admin manages project managers; a project manager manages the
site team on their projects; a site engineer manages workers on their
projects (attendance, shifts, tasks) but never pay or logins."""

import importlib.util
from pathlib import Path

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app

API = "/api/v1"
U = {k: ObjectId() for k in ("admin", "pm", "pm2", "se", "worker_user")}

spec = importlib.util.spec_from_file_location("seed_demo", Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_demo)


@pytest.fixture(scope="module")
def env():
    db = AsyncMongoMockClient()["hierarchy_test"]
    facts = {}

    async def setup():
        roles = {"admin": "admin", "pm": "project_manager", "pm2": "project_manager", "se": "site_engineer", "worker_user": "worker"}
        await db.users.insert_many([{"_id": U[k], "email": f"{k}@example.com", "full_name": k, "role": r, "status": "active",
                                     "password_hash": hash_password("x")} for k, r in roles.items()])
        await seed_demo.seed(db)
        tower = await db.projects.find_one({"name": {"$regex": "Tower B"}})
        plaza = await db.projects.find_one({"name": "Metro Commercial Plaza"})
        # PM and site engineer work on Tower B only; pm2 manages Plaza.
        await db.user_project_access.delete_many({"user_id": {"$in": [str(U["pm"]), str(U["se"]), str(U["pm2"])]}})
        for user, project in (("pm", tower), ("se", tower), ("pm2", plaza)):
            await db.user_project_access.insert_one({"user_id": str(U[user]), "project_id": str(project["_id"]), "active": True})
        facts["tower"], facts["plaza"] = str(tower["_id"]), str(plaza["_id"])
        facts["tower_worker"] = str((await db.workers.find_one({"project_id": facts["tower"]}))["_id"])
        facts["plaza_worker"] = str((await db.workers.find_one({"project_id": facts["plaza"]}))["_id"])
        facts["tower_shift"] = str((await db.shifts.find_one({"project_id": facts["tower"]}))["_id"])

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(setup)
    with TestClient(app) as client:
        yield client, facts
    app.dependency_overrides.clear()


def call(client, method, path, who, **kwargs):
    return client.request(method, API + path, headers={"Authorization": f"Bearer {create_access_token(str(U[who]))}"}, **kwargs)


def test_site_engineer_runs_their_crew(env):
    client, f = env
    mark = {"worker_id": f["tower_worker"], "date": "2026-10-23", "status": "present"}
    assert call(client, "POST", "/workforce/attendance", "se", json=mark).status_code == 200
    shift = {"worker_id": f["tower_worker"], "shift_id": f["tower_shift"], "date": "2026-10-24T00:00:00", "status": "ACTIVE"}
    assert call(client, "POST", "/workforce/shift-assignments", "se", json=shift).status_code == 200
    task = {"title": "Clean the slab deck", "project_id": f["tower"], "assigned_worker_id": f["tower_worker"]}
    assert call(client, "POST", "/tasks/", "se", json=task).status_code == 200


def test_site_engineer_cannot_reach_other_projects_workers(env):
    client, f = env
    assert call(client, "POST", "/workforce/attendance", "se", json={"worker_id": f["plaza_worker"], "date": "2026-10-23", "status": "absent"}).status_code == 404
    task = {"title": "Not mine", "project_id": f["tower"], "assigned_worker_id": f["plaza_worker"]}
    assert call(client, "POST", "/tasks/", "se", json=task).status_code == 404


def test_site_engineer_never_handles_pay_or_logins(env):
    client, f = env
    pay = {"worker_id": f["tower_worker"], "pay_period_start": "2026-10-01T00:00:00", "pay_period_end": "2026-10-15T00:00:00", "basic_amount": 9000}
    assert call(client, "POST", "/workforce/payroll", "se", json=pay).status_code == 403
    assert call(client, "GET", "/workforce/payroll", "se").status_code == 403
    assert call(client, "POST", f"/workforce/workers/{f['tower_worker']}/login", "se", json={"password": "long-enough-1"}).status_code == 403
    worker = call(client, "GET", f"/workforce/workers/{f['tower_worker']}", "se").json()
    assert worker["hourly_rate"] is None and worker["salary_amount"] is None  # wages hidden


def test_project_manager_assigns_only_the_team_below_them(env):
    client, f = env
    path = f"/access/projects/{f['tower']}/members"
    assert call(client, "POST", path, "pm", json={"user_id": str(U["worker_user"])}).status_code == 200
    for above in ("pm2", "admin"):
        response = call(client, "POST", path, "pm", json={"user_id": str(U[above])})
        assert response.status_code == 403 and "administrator" in response.json()["detail"]
    # A project manager cannot remove another manager either; an admin can do both.
    assert call(client, "POST", path, "admin", json={"user_id": str(U["pm2"])}).status_code == 200
    assert call(client, "DELETE", f"{path}/{U['pm2']}", "pm").status_code == 403
    assert call(client, "DELETE", f"{path}/{U['pm2']}", "admin").status_code == 200
    # Site engineers do not manage project membership at all.
    assert call(client, "POST", path, "se", json={"user_id": str(U["worker_user"])}).status_code == 403
