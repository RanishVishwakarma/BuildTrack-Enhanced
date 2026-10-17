"""GST on purchase orders: rate slabs, calculation and CGST/SGST vs IGST."""

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
from app.modules.procurement.gst import GSTError, price_order, state_code

API = "/api/v1"
COMPANY = "27AAACB1234C1Z5"   # Maharashtra
SAME_STATE = "27AAFCV9876K1Z2"
OTHER_STATE = "29AAFCV9876K1Z2"  # Karnataka
NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def test_state_code_needs_a_valid_gstin():
    assert state_code(COMPANY) == "27"
    assert state_code("27abc") is None and state_code(None) is None


def test_same_state_splits_cgst_and_sgst(monkeypatch):
    monkeypatch.setattr(settings, "company_gstin", COMPANY)
    price = price_order(100, 380, gst_rate=18, vendor_gstin=SAME_STATE)
    assert price == {"subtotal": 38000.0, "gst_rate": 18.0, "gst": 6840.0, "cgst": 3420.0, "sgst": 3420.0, "igst": 0.0,
                     "supply_type": "intra_state", "total_cost": 44840.0}


def test_other_state_is_igst(monkeypatch):
    monkeypatch.setattr(settings, "company_gstin", COMPANY)
    price = price_order(3, 333.33, gst_rate=28, vendor_gstin=OTHER_STATE)
    assert price["igst"] == price["gst"] == 280.0 and price["cgst"] == 0.0 and price["supply_type"] == "inter_state"


def test_split_undetermined_without_both_gstins(monkeypatch):
    monkeypatch.setattr(settings, "company_gstin", None)
    price = price_order(10, 100, gst_rate=5, vendor_gstin=SAME_STATE)
    assert price["gst"] == 50.0 and price["supply_type"] == "undetermined" and price["cgst"] is None


def test_odd_paise_split_still_adds_up(monkeypatch):
    monkeypatch.setattr(settings, "company_gstin", COMPANY)
    price = price_order(1, 10.01, gst_rate=5, vendor_gstin=SAME_STATE)  # GST 0.50 -> 0.25 + 0.25
    assert round(price["cgst"] + price["sgst"], 2) == price["gst"]


def test_rejects_rates_outside_the_slabs():
    with pytest.raises(GSTError):
        price_order(1, 100, gst_rate=7)


def test_legacy_amount_without_rate_is_kept():
    price = price_order(10, 100, gst_amount=123.45)
    assert price["gst"] == 123.45 and price["supply_type"] == "manual" and price["total_cost"] == 1123.45


# ------------------------------------------------------------------ API

IDS = {k: ObjectId() for k in ("pm", "vendor", "request", "item")}


async def seed(db):
    await db.users.insert_one({"_id": IDS["pm"], "email": "pm@gst-tests.io", "full_name": "PM", "role": "admin", "status": "active", "password_hash": hash_password("x")})
    await db.vendors.insert_one({"_id": IDS["vendor"], "vendor_name": "Shree Cement Traders", "status": "active", "gst_number": OTHER_STATE})
    await db.material_requests.insert_one({"_id": IDS["request"], "request_id": "MR-00001", "project": "Tower A", "material_name": "Cement",
                                           "quantity": 100, "status": "vendor_accepted", "vendor_id": str(IDS["vendor"]), "required_date": NOW})


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "company_gstin", COMPANY)
    db = AsyncMongoMockClient()["gst_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    yield TestClient(app), db
    app.dependency_overrides.clear()


def auth():
    return {"Authorization": f"Bearer {create_access_token(str(IDS['pm']))}"}


def po_payload(**extra):
    return {"request_id": str(IDS["request"]), "vendor_id": str(IDS["vendor"]), "project": "Tower A", "materials": "Cement",
            "quantity": 100, "unit_price": 380, "expected_delivery_date": NOW.isoformat(), **extra}


def test_purchase_order_calculates_gst_and_igst(env):
    client, _ = env
    po = client.post(f"{API}/procurement/purchase-orders", json=po_payload(gst_rate=18, gst=1), headers=auth()).json()
    assert (po["subtotal"], po["gst"], po["igst"], po["total_cost"], po["supply_type"]) == (38000, 6840, 6840, 44840, "inter_state")


def test_invalid_rate_is_refused(env):
    client, _ = env
    response = client.post(f"{API}/procurement/purchase-orders", json=po_payload(gst_rate=10), headers=auth())
    assert response.status_code == 400 and "GST rate must be one of" in response.json()["detail"]


def test_editing_reprices_including_gst(env):
    client, _ = env
    po = client.post(f"{API}/procurement/purchase-orders", json=po_payload(gst_rate=18), headers=auth()).json()
    updated = client.put(f"{API}/procurement/purchase-orders/{po['_id']}", json={"quantity": 50}, headers=auth()).json()
    assert (updated["subtotal"], updated["gst"], updated["total_cost"]) == (19000, 3420, 22420)
    assert client.put(f"{API}/procurement/purchase-orders/{po['_id']}", json={"gst_rate": 15}, headers=auth()).status_code == 422


def test_gst_config_and_inventory_default_rate(env):
    client, _ = env
    config = client.get(f"{API}/procurement/gst-config", headers=auth()).json()
    assert config == {"slabs": [0, 5, 12, 18, 28], "company_state_code": "27", "company_gstin_configured": True}
    ok = client.post(f"{API}/inventory/", json={"material_name": "Cement", "gst_rate": 28, "hsn_code": "2523"}, headers=auth())
    assert ok.status_code in (200, 201) and ok.json()["gst_rate"] == 28
    bad = client.post(f"{API}/inventory/", json={"material_name": "Sand", "gst_rate": 9}, headers=auth())
    assert bad.status_code == 422
