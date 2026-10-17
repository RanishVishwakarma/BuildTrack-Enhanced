"""Phase 1 security tests (spec v2.0 §24 and PHASE1_SECURITY_AUDIT.md).

Runs every request through the real authentication and authorization code
against an in-memory MongoDB (mongomock-motor); the shared database is never
touched.
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.permissions import ROLE_PERMISSIONS, effective_permissions
from app.core.roles import CANONICAL_ROLES, normalize_role
from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app

API = "/api/v1"
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)

IDS = {name: ObjectId() for name in (
    "admin", "pm_a", "pm_b", "engineer_a", "worker", "contractor_a", "client_a", "client_b",
    "vendor_1", "vendor_2", "suspended", "no_role",
    "project_a", "project_b", "worker_rec", "other_worker_rec", "po_1", "po_2", "invoice_1", "milestone_a",
)}
VENDOR_1, VENDOR_2 = "vendor-rec-1", "vendor-rec-2"


def user(key, role, email, **extra):
    return {"_id": IDS[key], "email": email, "full_name": key, "role": role, "status": "active",
            "password_hash": hash_password("Secret#123"), "created_at": NOW, "updated_at": NOW, **extra}


async def seed(db):
    await db.users.insert_many([
        user("admin", "admin", "admin@buildtrack-tests.io"),
        user("pm_a", "projectmanager", "pma@buildtrack-tests.io"),
        user("pm_b", "projectmanager", "pmb@buildtrack-tests.io"),
        user("engineer_a", "siteengineer", "eng@buildtrack-tests.io"),
        user("worker", "worker", "worker@buildtrack-tests.io"),
        user("contractor_a", "contractor", "con@buildtrack-tests.io"),
        user("client_a", "client", "clienta@buildtrack-tests.io"),
        user("client_b", "client", "clientb@buildtrack-tests.io"),
        user("vendor_1", "vendor", "v1@buildtrack-tests.io", vendor_id=VENDOR_1),
        user("vendor_2", "vendor", "v2@buildtrack-tests.io", vendor_id=VENDOR_2),
        user("suspended", "projectmanager", "susp@buildtrack-tests.io", status="suspended"),
        user("no_role", "string", "norole@buildtrack-tests.io"),
    ])
    await db.projects.insert_many([
        {"_id": IDS["project_a"], "name": "Project A", "client_email": "clienta@buildtrack-tests.io", "status": "active", "budget": 1000},
        {"_id": IDS["project_b"], "name": "Project B", "client_email": "clientb@buildtrack-tests.io", "status": "active", "budget": 9000},
    ])
    await db.user_project_access.insert_many([
        {"user_id": str(IDS["pm_a"]), "project_id": str(IDS["project_a"]), "active": True},
        {"user_id": str(IDS["pm_b"]), "project_id": str(IDS["project_b"]), "active": True},
        {"user_id": str(IDS["engineer_a"]), "project_id": str(IDS["project_a"]), "active": True},
        {"user_id": str(IDS["contractor_a"]), "project_id": str(IDS["project_a"]), "active": True},
    ])
    await db.workers.insert_many([
        {"_id": IDS["worker_rec"], "email": "worker@buildtrack-tests.io", "name": "Worker", "hourly_rate": 300, "salary_amount": 50000, "project_id": str(IDS["project_a"])},
        {"_id": IDS["other_worker_rec"], "email": "other@buildtrack-tests.io", "name": "Other", "hourly_rate": 450, "salary_amount": 70000},
    ])
    await db.payroll.insert_one({"worker_id": str(IDS["other_worker_rec"]), "amount": 70000})
    await db.purchase_orders.insert_many([
        {"_id": IDS["po_1"], "po_number": "PO-1", "vendor_id": VENDOR_1, "status": "sent"},
        {"_id": IDS["po_2"], "po_number": "PO-2", "vendor_id": VENDOR_2, "status": "sent"},
    ])
    await db.invoices.insert_one({"_id": IDS["invoice_1"], "invoice_number": "INV-1", "vendor_id": VENDOR_1, "amount": 100, "gst": 18})
    await db.project_milestones.insert_one({"_id": IDS["milestone_a"], "title": "Slab", "project_id": str(IDS["project_a"])})


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["rbac_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    client = TestClient(app)
    import anyio

    anyio.run(seed, db)
    yield client, db
    app.dependency_overrides.clear()


def auth(key):
    return {"Authorization": f"Bearer {create_access_token(str(IDS[key]))}"}


def run(coro_fn, *args):
    import anyio

    return anyio.run(coro_fn, *args)


# ---------------------------------------------------------------- roles ----

def test_exactly_seven_canonical_roles_with_permissions():
    assert set(CANONICAL_ROLES) == {"admin", "projectmanager", "siteengineer", "worker", "vendor", "client", "contractor"}
    assert set(ROLE_PERMISSIONS) == set(CANONICAL_ROLES)


@pytest.mark.parametrize("stored, expected", [
    ("Administrator", "admin"), ("Project Manager", "projectmanager"), ("manager", "projectmanager"),
    ("engineer", "siteengineer"), ("Client", "client"), ("string", None), ("finance", None), ("store_manager", None),
])
def test_legacy_roles_normalize_or_deny(stored, expected):
    assert normalize_role(stored) == expected


def test_unknown_role_has_no_permissions():
    assert effective_permissions({"role": "string"}) == set()


def test_per_user_grant_and_revoke():
    perms = effective_permissions({"role": "siteengineer", "permissions": ["procurement.payment.record", "not.a.permission"], "revoked_permissions": ["tasks.update.assigned"]})
    assert "procurement.payment.record" in perms
    assert "not.a.permission" not in perms
    assert "tasks.update.assigned" not in perms


# ------------------------------------------------------- spec §24 tests ----

def test_01_worker_denied_company_financials(env):
    client, _ = env
    for path in ("/workforce/payroll", "/procurement/payments", "/procurement/invoices", "/reports/dashboard/metrics"):
        assert client.get(API + path, headers=auth("worker")).status_code == 403, path


def test_02_project_manager_denied_unassigned_project(env):
    client, _ = env
    assert client.get(f"{API}/projects/{IDS['project_b']}", headers=auth("pm_a")).status_code == 404
    names = [p["name"] for p in client.get(f"{API}/projects", headers=auth("pm_a")).json()]
    assert names == ["Project A"]


def test_03_client_denied_other_clients_project_and_reports(env):
    client, _ = env
    assert client.get(f"{API}/projects/{IDS['project_b']}", headers=auth("client_a")).status_code == 404
    assert client.get(f"{API}/reports/project/{IDS['project_b']}", headers=auth("client_a")).status_code == 404
    names = [p["name"] for p in client.get(f"{API}/projects", headers=auth("client_a")).json()]
    assert names == ["Project A"]


def test_04_vendor_denied_other_vendors_purchase_order(env):
    client, _ = env
    assert client.get(f"{API}/procurement/purchase-orders/{IDS['po_2']}/pdf", headers=auth("vendor_1")).status_code == 403
    assert client.get(f"{API}/procurement/purchase-orders/{IDS['po_1']}/pdf", headers=auth("vendor_1")).status_code != 403
    assert client.get(f"{API}/procurement/invoices", headers=auth("vendor_1")).status_code == 403


def test_05_contractor_denied_unrelated_project(env):
    client, _ = env
    assert client.get(f"{API}/projects/{IDS['project_b']}", headers=auth("contractor_a")).status_code == 404
    assert client.get(f"{API}/projects/{IDS['project_a']}", headers=auth("contractor_a")).status_code == 200


def test_06_changing_project_id_does_not_grant_access(env):
    client, _ = env
    # Create a milestone on someone else's project.
    response = client.post(f"{API}/frontend-data/milestones", json={"project_id": str(IDS["project_b"]), "title": "x"}, headers=auth("pm_a"))
    assert response.status_code == 404
    # Move an own milestone into someone else's project.
    response = client.put(f"{API}/frontend-data/milestones/{IDS['milestone_a']}", json={"project_id": str(IDS["project_b"])}, headers=auth("pm_a"))
    assert response.status_code == 404
    # Another PM cannot even read it.
    response = client.put(f"{API}/frontend-data/milestones/{IDS['milestone_a']}", json={"title": "y"}, headers=auth("pm_b"))
    assert response.status_code == 404


def test_10_unauthorized_inventory_adjustment_denied(env):
    client, _ = env
    for key in ("worker", "client_a", "vendor_1", "contractor_a"):
        response = client.post(f"{API}/frontend-data/inventory", json={"material": "Cement", "quantity": 5}, headers=auth(key))
        assert response.status_code == 403, key


def test_15_revoked_project_access_applies_immediately(env):
    client, db = env
    assert client.get(f"{API}/projects/{IDS['project_a']}", headers=auth("pm_a")).status_code == 200

    async def revoke(db):
        await db.user_project_access.update_one({"user_id": str(IDS["pm_a"])}, {"$set": {"active": False}})

    run(revoke, db)
    assert client.get(f"{API}/projects/{IDS['project_a']}", headers=auth("pm_a")).status_code == 404


def test_16_role_change_removes_old_permissions(env):
    client, db = env
    headers = auth("pm_a")  # token issued before the change
    assert client.post(f"{API}/frontend-data/projects", json={"name": "New"}, headers=headers).status_code == 200

    async def demote(db):
        await db.users.update_one({"_id": IDS["pm_a"]}, {"$set": {"role": "worker"}})

    run(demote, db)
    assert client.post(f"{API}/frontend-data/projects", json={"name": "New 2"}, headers=headers).status_code == 403


# ------------------------------------------------ audit-finding tests ----

def test_suspended_account_token_rejected(env):
    client, _ = env
    assert client.get(f"{API}/auth/me", headers=auth("suspended")).status_code == 401


def test_account_without_valid_role_rejected(env):
    client, _ = env
    assert client.get(f"{API}/auth/me", headers=auth("no_role")).status_code == 403


def test_public_signup_cannot_choose_admin(env):
    client, _ = env
    response = client.post(f"{API}/auth/register", json={"email": "new@buildtrack-tests.io", "password": "Secret#123", "role": "Administrator", "name": "N"})
    assert response.status_code == 403


def test_public_signup_stores_canonical_role(env):
    client, db = env
    response = client.post(f"{API}/auth/register", json={"email": "pm2@buildtrack-tests.io", "password": "Secret#123", "role": "Project Manager", "name": "N"})
    assert response.status_code == 200

    async def stored(db):
        return (await db.users.find_one({"email": "pm2@buildtrack-tests.io"}))["role"]

    assert run(stored, db) == "projectmanager"


def test_social_login_disabled(env):
    client, _ = env
    response = client.post(f"{API}/auth/social-login", json={"provider": "google", "email": "admin@buildtrack-tests.io", "full_name": "x"})
    assert response.status_code == 501
    assert "access_token" not in response.text


def test_password_hash_never_returned(env):
    client, _ = env
    body = client.get(f"{API}/auth/me", headers=auth("admin")).json()
    assert "password_hash" not in body
    assert body["role"] == "admin" and "users.roles.assign" in body["permissions"]
    users = client.get(f"{API}/auth/users", headers=auth("admin")).json()
    assert users and all("password_hash" not in u for u in users)


def test_password_reset_does_not_return_token(env):
    client, _ = env
    response = client.post(f"{API}/auth/password-reset/request", json={"email": "admin@buildtrack-tests.io"})
    assert response.status_code == 200
    assert response.json().get("reset_token") is None


def test_login_does_not_reveal_suspension_without_password(env):
    client, _ = env
    response = client.post(f"{API}/auth/login", json={"email": "susp@buildtrack-tests.io", "password": "wrong"})
    assert response.status_code == 401


def test_public_payment_confirmation_disabled(env):
    client, db = env
    response = client.post(f"{API}/procurement/pay-scan/{IDS['invoice_1']}/confirm")
    assert response.status_code == 403

    async def payments(db):
        return await db.payments.count_documents({})

    assert run(payments, db) == 0


def test_quick_pay_requires_payment_permission(env):
    client, _ = env
    for key in ("vendor_1", "worker", "pm_a"):
        assert client.post(f"{API}/procurement/invoices/{IDS['invoice_1']}/quick-pay", headers=auth(key)).status_code == 403, key


def test_wages_hidden_without_sensitive_permission(env):
    client, _ = env
    rows = client.get(f"{API}/workforce/workers", headers=auth("engineer_a")).json()
    assert rows and all(row.get("hourly_rate") is None and row.get("salary_amount") is None for row in rows)
    rows = client.get(f"{API}/workforce/workers", headers=auth("pm_a")).json()
    assert any(row.get("hourly_rate") for row in rows)


def test_worker_reads_only_own_records(env):
    client, _ = env
    assert client.get(f"{API}/workforce/workers", headers=auth("worker")).status_code == 403
    assert client.get(f"{API}/workforce/payroll", params={"worker_id": str(IDS["other_worker_rec"])}, headers=auth("worker")).status_code == 403
    assert client.get(f"{API}/workforce/payroll", params={"worker_id": str(IDS["worker_rec"])}, headers=auth("worker")).status_code == 200


def test_role_change_is_audited_and_self_change_blocked(env):
    client, db = env
    response = client.put(f"{API}/auth/users/{IDS['pm_b']}", json={"role": "Site Engineer"}, headers=auth("admin"))
    assert response.status_code == 200 and response.json()["role"] == "siteengineer"
    response = client.put(f"{API}/auth/users/{IDS['admin']}", json={"role": "worker"}, headers=auth("admin"))
    assert response.status_code == 400
    response = client.put(f"{API}/auth/users/{IDS['pm_a']}", json={"role": "admin"}, headers=auth("pm_a"))
    assert response.status_code == 403

    async def audit(db):
        return await db.audit_logs.find_one({"event_type": "user.role.changed"})

    record = run(audit, db)
    assert record and record["details"] == {"from": "projectmanager", "to": "siteengineer"}


def test_site_engineer_denied_invoices_and_payments(env):
    client, _ = env
    for path in ("/procurement/payments", "/procurement/invoices", "/procurement/export/payments"):
        assert client.get(API + path, headers=auth("engineer_a")).status_code == 403, path
    assert client.get(f"{API}/procurement/purchase-orders", headers=auth("engineer_a")).status_code == 200
