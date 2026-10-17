"""Three-way match of purchase order, accepted deliveries and invoices."""

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

API = "/api/v1/procurement"
NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
IDS = {k: ObjectId() for k in ("admin", "vendor_user", "vendor", "po")}


async def seed(db):
    await db.users.insert_many([
        {"_id": IDS["admin"], "email": "admin@im-tests.io", "full_name": "Admin", "role": "admin", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["vendor_user"], "email": "v@im-tests.io", "full_name": "Ravi", "role": "vendor", "status": "active",
         "vendor_id": str(IDS["vendor"]), "password_hash": hash_password("x")},
    ])
    await db.vendors.insert_one({"_id": IDS["vendor"], "vendor_name": "Shree Cement", "status": "active", "gst_number": "27AAFCV9876K1Z2"})
    # 100 bags at Rs 380 + 18% GST, same state as the company -> CGST + SGST.
    await db.purchase_orders.insert_one({"_id": IDS["po"], "po_number": "PO-0001", "vendor_id": str(IDS["vendor"]), "materials": "Cement",
                                         "quantity": 100, "unit_price": 380, "subtotal": 38000, "gst_rate": 18, "gst": 6840,
                                         "total_cost": 44840, "status": "accepted"})


async def deliver(db, quantity, status="accepted", quality="passed"):
    await db.deliveries.insert_one({"purchase_order_id": str(IDS["po"]), "material": "Cement", "quantity_received": quantity,
                                    "status": status, "quality_status": quality, "delivery_date": NOW})


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "company_gstin", "27AAACB1234C1Z5")
    db = AsyncMongoMockClient()["invoice_match_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def auth(who="admin"):
    return {"Authorization": f"Bearer {create_access_token(str(IDS[who]))}"}


def invoice(number, amount, gst):
    return {"invoice_number": number, "purchase_order_id": str(IDS["po"]), "amount": amount, "gst": gst, "invoice_date": NOW.isoformat()}


def test_preview_bills_only_accepted_deliveries(env):
    client, db = env
    anyio.run(deliver, db, 80)
    anyio.run(deliver, db, 20, "delivered", "pending")  # arrived, not inspected yet
    preview = client.get(f"{API}/purchase-orders/{IDS['po']}/invoice-preview", headers=auth()).json()
    assert (preview["received_quantity"], preview["billable_amount"], preview["expected_gst"]) == (80, 30400, 5472)
    assert (preview["cgst"], preview["sgst"], preview["supply_type"]) == (2736, 2736, "intra_state")
    assert any("not yet inspected" in flag for flag in preview["flags"])


def test_partial_invoices_and_po_cap(env):
    client, db = env
    anyio.run(deliver, db, 100)
    first = client.post(f"{API}/invoices", json=invoice("SC/101", 30400, 5472), headers=auth())
    assert first.status_code == 200 and first.json()["cgst"] == 2736 and first.json()["vendor_id"] == str(IDS["vendor"])

    preview = client.get(f"{API}/purchase-orders/{IDS['po']}/invoice-preview", headers=auth()).json()
    assert (preview["previously_invoiced"], preview["billable_amount"]) == (30400, 7600)

    over = client.post(f"{API}/invoices", json=invoice("SC/102", 9000, 1620), headers=auth())
    assert over.status_code == 400 and "exceeds what is left" in over.json()["detail"]
    assert client.post(f"{API}/invoices", json=invoice("SC/101", 100, 18), headers=auth()).status_code == 400  # duplicate number


def test_vendor_portal_invoice_is_capped_too(env):
    client, db = env
    anyio.run(deliver, db, 100)
    response = client.post(f"{API}/vendor/invoices", json=invoice("SC/201", 40000, 7200), headers=auth("vendor_user"))
    assert response.status_code == 400
    ok = client.post(f"{API}/vendor/invoices", json=invoice("SC/202", 38000, 6840), headers=auth("vendor_user"))
    assert ok.status_code == 200 and ok.json()["supply_type"] == "intra_state"
    preview = client.get(f"{API}/vendor/purchase-orders/{IDS['po']}/invoice-preview", headers=auth("vendor_user")).json()
    assert preview["billable_amount"] == 0


def test_mismatch_needs_a_reason_to_verify(env):
    client, db = env
    anyio.run(deliver, db, 50)
    created = client.post(f"{API}/invoices", json=invoice("SC/301", 38000, 5000), headers=auth()).json()
    match = client.get(f"{API}/invoices/{created['_id']}/match", headers=auth()).json()
    assert match["billable_amount"] == 19000 and len(match["flags"]) == 2  # over delivered, wrong GST

    refused = client.patch(f"{API}/invoices/{created['_id']}/verify", json={}, headers=auth())
    assert refused.status_code == 409 and "Add a comment" in refused.json()["detail"]
    allowed = client.patch(f"{API}/invoices/{created['_id']}/verify", json={"comments": "Balance delivered today, GRN pending"}, headers=auth())
    assert allowed.status_code == 200 and allowed.json()["status"] == "verified"


def test_clean_invoice_verifies_without_comment(env):
    client, db = env
    anyio.run(deliver, db, 100)
    created = client.post(f"{API}/invoices", json=invoice("SC/401", 38000, 6840), headers=auth()).json()
    assert client.get(f"{API}/invoices/{created['_id']}/match", headers=auth()).json()["flags"] == []
    assert client.patch(f"{API}/invoices/{created['_id']}/verify", json={}, headers=auth()).status_code == 200
