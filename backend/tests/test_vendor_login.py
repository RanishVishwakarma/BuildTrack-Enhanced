"""Vendor portal logins created by admins and project managers."""

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.security import create_access_token, hash_password, verify_password
from app.db.mongodb import get_database
from app.main import app

API = "/api/v1/procurement"
IDS = {k: ObjectId() for k in ("pm", "engineer", "vendor", "other")}


async def seed(db):
    await db.users.insert_many([
        {"_id": IDS["pm"], "email": "pm@vl-tests.io", "full_name": "PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["engineer"], "email": "se@vl-tests.io", "full_name": "SE", "role": "site_engineer", "status": "active", "password_hash": hash_password("x")},
    ])
    await db.vendors.insert_many([
        {"_id": IDS["vendor"], "vendor_name": "Shree Cement Traders", "contact_person": "Ravi", "email": "sales@shree.io", "status": "active"},
        {"_id": IDS["other"], "vendor_name": "Steel Co", "contact_person": "Anil", "email": "pm@vl-tests.io", "status": "active"},
    ])


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["vendor_login_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def auth(who):
    return {"Authorization": f"Bearer {create_access_token(str(IDS[who]))}"}


def test_pm_creates_login_for_existing_vendor(env):
    client, db = env
    response = client.post(f"{API}/vendors/{IDS['vendor']}/login", json={"password": "cement-2026"}, headers=auth("pm"))
    assert response.status_code == 201 and response.json()["login_email"] == "sales@shree.io"

    user = anyio.run(db.users.find_one, {"email": "sales@shree.io"})
    assert user["role"] == "vendor" and user["vendor_id"] == str(IDS["vendor"])
    assert verify_password("cement-2026", user["password_hash"]) and "password" not in user

    listed = client.get(f"{API}/vendors", headers=auth("pm")).json()["items"]
    assert {v["vendor_name"]: v["login_email"] for v in listed} == {"Shree Cement Traders": "sales@shree.io", "Steel Co": None}

    again = client.post(f"{API}/vendors/{IDS['vendor']}/login", json={"password": "cement-2026"}, headers=auth("pm"))
    assert again.status_code == 409


def test_refuses_an_email_that_already_has_an_account(env):
    client, _ = env
    response = client.post(f"{API}/vendors/{IDS['other']}/login", json={"password": "steel-2026x"}, headers=auth("pm"))
    assert response.status_code == 409


def test_short_password_and_other_roles_refused(env):
    client, _ = env
    assert client.post(f"{API}/vendors/{IDS['vendor']}/login", json={"password": "short"}, headers=auth("pm")).status_code == 422
    assert client.post(f"{API}/vendors/{IDS['vendor']}/login", json={"password": "long-enough"}, headers=auth("engineer")).status_code == 403
    assert "login_email" not in client.get(f"{API}/vendors", headers=auth("engineer")).json()["items"][0]


def test_reset_password_only_touches_the_vendor_login(env):
    client, db = env
    assert client.put(f"{API}/vendors/{IDS['vendor']}/login/password", json={"password": "new-pass-1"}, headers=auth("pm")).status_code == 404
    client.post(f"{API}/vendors/{IDS['vendor']}/login", json={"password": "cement-2026"}, headers=auth("pm"))
    assert client.put(f"{API}/vendors/{IDS['vendor']}/login/password", json={"password": "new-pass-1"}, headers=auth("engineer")).status_code == 403
    assert client.put(f"{API}/vendors/{IDS['vendor']}/login/password", json={"password": "new-pass-1"}, headers=auth("pm")).status_code == 200
    user = anyio.run(db.users.find_one, {"email": "sales@shree.io"})
    assert verify_password("new-pass-1", user["password_hash"])
