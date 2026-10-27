"""A project manager linked to one project sees only that project's data.

Uses the demo dataset (scripts/seed_demo.py) in memory: Tower B, Metro
Commercial Plaza and City Hospital Annex, with the PM linked to Tower B only.
"""

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
ADMIN, PM = ObjectId(), ObjectId()

spec = importlib.util.spec_from_file_location("seed_demo", Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_demo)


@pytest.fixture(scope="module")
def env():
    db = AsyncMongoMockClient()["isolation_test"]
    facts = {}

    async def setup():
        await db.users.insert_many([
            {"_id": ADMIN, "email": "admin@example.com", "full_name": "Admin", "role": "admin", "status": "active", "password_hash": hash_password("x")},
            {"_id": PM, "email": "pm@example.com", "full_name": "PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")},
        ])
        await seed_demo.seed(db)
        tower = await db.projects.find_one({"name": {"$regex": "Tower B"}})
        plaza = await db.projects.find_one({"name": "Metro Commercial Plaza"})
        await db.user_project_access.delete_many({"user_id": str(PM), "project_id": {"$ne": str(tower["_id"])}})
        facts["plaza_po"] = await db.purchase_orders.find_one({"project_id": str(plaza["_id"])})
        facts["plaza_invoice"] = await db.invoices.find_one({"purchase_order_id": str(facts["plaza_po"]["_id"])})
        facts["plaza_delivery"] = await db.deliveries.find_one({"purchase_order_id": str(facts["plaza_po"]["_id"])})
        facts["steel"] = await db.vendors.find_one({"vendor_name": "Bharat Steel Distributors"})  # used only by Plaza
        facts["tower_po"] = await db.purchase_orders.find_one({"project_id": str(tower["_id"])})
        facts["plaza_worker"] = await db.workers.find_one({"project_id": str(plaza["_id"])})

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(setup)
    with TestClient(app) as client:
        yield client, facts
    app.dependency_overrides.clear()


def get(client, path, who=PM, **params):
    return client.get(API + path, params=params, headers={"Authorization": f"Bearer {create_access_token(str(who))}"})


def items(response):
    data = response.json()
    return data["items"] if isinstance(data, dict) and "items" in data else data


@pytest.mark.parametrize("path", ["/procurement/material-requests", "/procurement/purchase-orders", "/procurement/deliveries",
                                  "/procurement/invoices", "/procurement/payments"])
def test_procurement_lists_hold_only_the_managers_project(env, path):
    client, facts = env
    rows = items(get(client, path))
    text = str(rows)
    assert "Metro Commercial Plaza" not in text and str(facts["plaza_po"]["_id"]) not in text
    assert len(items(get(client, path, ADMIN))) > len(rows)


def test_vendor_directory_hides_other_projects_suppliers(env):
    client, facts = env
    names = {v["vendor_name"] for v in items(get(client, "/procurement/vendors"))}
    assert "Bharat Steel Distributors" not in names and "Shree Cement Traders" in names
    assert "Bharat Steel Distributors" in {v["vendor_name"] for v in items(get(client, "/procurement/vendors", ADMIN))}


def test_other_projects_records_answer_404(env):
    client, facts = env
    for path in (f"/procurement/purchase-orders/{facts['plaza_po']['_id']}", f"/procurement/purchase-orders/{facts['plaza_po']['_id']}/pdf",
                 f"/procurement/invoices/{facts['plaza_invoice']['_id']}/match", f"/procurement/invoices/{facts['plaza_invoice']['_id']}/status",
                 f"/procurement/vendors/{facts['steel']['_id']}", f"/workforce/workers/{facts['plaza_worker']['_id']}"):
        assert get(client, path).status_code == 404, path
    assert get(client, f"/procurement/purchase-orders/{facts['tower_po']['_id']}").status_code == 200
    assert get(client, f"/procurement/purchase-orders/{facts['plaza_po']['_id']}", ADMIN).status_code == 200


def test_dashboards_count_only_visible_records(env):
    client, _ = env
    pm, admin = get(client, "/procurement/dashboard").json(), get(client, "/procurement/dashboard", ADMIN).json()
    assert pm["active_purchase_orders"] < admin["active_purchase_orders"]
    pm_w, admin_w = get(client, "/workforce/dashboard/summary").json(), get(client, "/workforce/dashboard/summary", ADMIN).json()
    assert pm_w["total_workers"] == 5 and admin_w["total_workers"] == 10


def test_older_apis_are_scoped_too(env):
    client, facts = env
    workers = get(client, "/frontend-data/workers").json()
    assert workers and all(w.get("project_id") != facts["plaza_worker"]["project_id"] for w in workers)
    assert {r["worker_id"] for r in get(client, "/frontend-data/attendance").json()} <= {w["_id"] for w in workers}
    names = {r["project_name"] for r in get(client, "/reports/project").json()}
    assert names == {"Green Valley Residency - Tower B"}
