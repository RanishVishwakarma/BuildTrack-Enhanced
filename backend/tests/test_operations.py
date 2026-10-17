"""Phases 3, 6, 7, 8 and access management (spec §24 items 11-14, 17, 18)."""

import base64
import hashlib
import hmac
import io
from datetime import datetime, timedelta, timezone

import anyio
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from PIL import Image

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app
from app.modules.intelligence import common
from app.modules.monitoring import engine

API = "/api/v1"
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
IDS = {k: ObjectId() for k in ("admin", "admin2", "pm", "pm_other", "engineer", "worker", "project", "other_project", "item", "task", "worker_rec")}


def user(key, role, email, **extra):
    return {"_id": IDS[key], "email": email, "full_name": key, "role": role, "status": "active", "password_hash": hash_password("x"), **extra}


async def seed(db):
    await db.users.insert_many([
        user("admin", "admin", "admin@ops-tests.io"), user("admin2", "admin", "admin2@ops-tests.io"),
        user("pm", "projectmanager", "pm@ops-tests.io"), user("pm_other", "projectmanager", "pm2@ops-tests.io"),
        user("engineer", "siteengineer", "eng@ops-tests.io"),
        user("worker", "worker", "worker@ops-tests.io", phone="+919800000001", voice_consent=True),
    ])
    pid = str(IDS["project"])
    await db.projects.insert_many([{"_id": IDS["project"], "name": "Skyline", "status": "active"}, {"_id": IDS["other_project"], "name": "Other", "status": "active"}])
    await db.user_project_access.insert_many([
        {"user_id": str(IDS["pm"]), "project_id": pid, "active": True},
        {"user_id": str(IDS["engineer"]), "project_id": pid, "active": True},
        {"user_id": str(IDS["worker"]), "project_id": pid, "active": True},
        {"user_id": str(IDS["pm_other"]), "project_id": str(IDS["other_project"]), "active": True},
    ])
    await db.workers.insert_one({"_id": IDS["worker_rec"], "email": "worker@ops-tests.io", "name": "Worker"})
    await db.tasks.insert_one({"_id": IDS["task"], "project_id": pid, "title": "Shuttering", "status": "pending", "due_date": NOW - timedelta(days=3), "assigned_worker_id": str(IDS["worker_rec"])})
    await db.inventory.insert_one({"_id": IDS["item"], "material": "Cement", "unit": "bags", "stock_quantity": 50})
    await db.material_requests.insert_one({"request_id": "MR-00001", "project_id": pid, "project": "Skyline", "material_name": "Cement", "unit": "bags",
                                           "quantity": 200, "status": "approved", "required_date": NOW + timedelta(days=4), "created_at": NOW - timedelta(days=1)})


@pytest.fixture
def env(monkeypatch, tmp_path):
    for target in ("app.modules.intelligence.common.utcnow", "app.modules.intelligence.data.utcnow", "app.modules.intelligence.materials.utcnow",
                   "app.modules.intelligence.risk.utcnow", "app.modules.monitoring.engine.utcnow", "app.modules.actions.service.utcnow",
                   "app.modules.hub.safety.utcnow", "app.modules.hub.suggestions.utcnow", "app.modules.voice.service.utcnow", "app.modules.evidence.router.utcnow"):
        monkeypatch.setattr(target, lambda: NOW)
    monkeypatch.setattr(settings, "private_upload_dir", str(tmp_path))
    db = AsyncMongoMockClient()["ops_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed, db)
    yield TestClient(app), db
    app.dependency_overrides.clear()


def auth(key):
    return {"Authorization": f"Bearer {create_access_token(str(IDS[key]))}"}


def run(fn, *args):
    return anyio.run(fn, *args)


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 120, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------------------------------------------- Phase 3

def test_13_monitoring_retries_do_not_duplicate_alerts_or_notifications(env):
    client, db = env
    first = client.post(f"{API}/monitoring/run", headers=auth("admin")).json()
    assert first["status"] == "success" and first["alerts_created"] > 0

    async def counts(db):
        return await db.alerts.count_documents({}), await db.notifications.count_documents({}), await db.ai_recommendations.count_documents({})

    before = run(counts, db)
    second = client.post(f"{API}/monitoring/run", headers=auth("admin")).json()
    assert second["alerts_created"] == 0 and run(counts, db) == before
    alerts = client.get(f"{API}/monitoring/alerts", headers=auth("worker")).json()
    assert any(a["rule"] == "overdue_task" for a in alerts)


def test_concurrent_run_is_skipped_by_lease(env):
    client, db = env

    async def hold(db):
        await db.job_locks.insert_one({"_id": "monitoring", "owner": "other", "expires_at": NOW + timedelta(minutes=5)})

    run(hold, db)
    assert client.post(f"{API}/monitoring/run", headers=auth("admin")).json()["status"] == "skipped"


def test_alert_resolves_when_condition_clears_and_ack_is_owner_only(env):
    client, db = env
    client.post(f"{API}/monitoring/run", headers=auth("admin"))
    alert = next(a for a in client.get(f"{API}/monitoring/alerts", headers=auth("worker")).json() if a["rule"] == "overdue_task")
    assert client.post(f"{API}/monitoring/alerts/{alert['_id']}/acknowledge", headers=auth("pm_other")).status_code == 404
    assert client.post(f"{API}/monitoring/alerts/{alert['_id']}/acknowledge", headers=auth("worker")).json()["acknowledged_at"]

    async def finish(db):
        await db.tasks.update_one({"_id": IDS["task"]}, {"$set": {"status": "completed"}})

    run(finish, db)
    client.post(f"{API}/monitoring/run", headers=auth("admin"))
    assert all(a["rule"] != "overdue_task" for a in client.get(f"{API}/monitoring/alerts", headers=auth("worker")).json())


def test_escalation_happens_once(env, monkeypatch):
    client, db = env
    client.post(f"{API}/monitoring/run", headers=auth("admin"))

    async def age(db):
        await db.alerts.update_many({}, {"$set": {"created_at": NOW - timedelta(hours=5)}})

    run(age, db)
    assert run(engine.escalate, db) > 0

    async def escalations(db):
        return await db.notifications.count_documents({"category": "escalation"})

    count = run(escalations, db)
    assert run(engine.escalate, db) == 0 and run(escalations, db) == count


def test_monitoring_runs_need_permission(env):
    client, _ = env
    assert client.post(f"{API}/monitoring/run", headers=auth("pm")).status_code == 403
    assert client.get(f"{API}/monitoring/runs", headers=auth("worker")).status_code == 403


# --------------------------------------------------------- Phase 8 actions

def test_11_recommended_order_is_never_created_without_approval(env):
    client, db = env
    assert client.post(f"{API}/recommendations/generate", headers=auth("pm")).json()["created"] == 1
    rec = client.get(f"{API}/recommendations", headers=auth("pm")).json()[0]
    assert rec["status"] == "proposed" and rec["action"]["type"] == "create_material_request" and rec["action"]["params"]["quantity"] == 150

    async def counts(db):
        return await db.purchase_orders.count_documents({}), await db.material_requests.count_documents({})

    assert run(counts, db) == (0, 1)
    executed = client.post(f"{API}/recommendations/{rec['_id']}/decision", json={"decision": "approve"}, headers=auth("pm")).json()
    assert executed["status"] == "executed"
    assert run(counts, db) == (0, 2)  # a pending material request, never a purchase order

    async def raised(db):
        return await db.material_requests.find_one({"source_recommendation_id": rec["_id"]})

    assert run(raised, db)["status"] == "pending"
    again = client.post(f"{API}/recommendations/{rec['_id']}/decision", json={"decision": "approve"}, headers=auth("admin"))
    assert again.status_code == 409 and run(counts, db) == (0, 2)


def test_18_proposer_cannot_approve_own_recommendation(env):
    client, _ = env
    rec = client.post(f"{API}/recommendations", json={"title": "Add night shift", "rationale": "Two milestones are late.", "project_id": str(IDS["project"]),
                                                      "instruction": "Plan a night shift"}, headers=auth("pm")).json()
    assert client.post(f"{API}/recommendations/{rec['_id']}/decision", json={"decision": "approve"}, headers=auth("pm")).status_code == 403
    assert client.post(f"{API}/recommendations/{rec['_id']}/decision", json={"decision": "reject"}, headers=auth("admin")).status_code == 422
    approved = client.post(f"{API}/recommendations/{rec['_id']}/decision", json={"decision": "approve"}, headers=auth("admin")).json()
    assert approved["status"] == "approved"  # manual: recorded, not executed
    verified = client.post(f"{API}/recommendations/{rec['_id']}/verify", json={"effective": True, "note": "Shift running"}, headers=auth("pm")).json()
    assert verified["status"] == "verified"


# ----------------------------------------------------------- Phase 6

def test_14_unsupported_or_spoofed_upload_rejected(env):
    client, _ = env
    data = {"project_id": str(IDS["project"]), "description": "Slab photo"}
    response = client.post(f"{API}/evidence", data=data, files={"file": ("photo.png", b"MZ\x90\x00 not an image", "image/png")}, headers=auth("engineer"))
    assert response.status_code == 422
    response = client.post(f"{API}/evidence", data=data, files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "image/png")}, headers=auth("engineer"))
    assert response.status_code == 422
    other = client.post(f"{API}/evidence", data={**data, "project_id": str(IDS["other_project"])}, files={"file": ("p.png", png_bytes(), "image/png")}, headers=auth("engineer"))
    assert other.status_code == 404


def test_17_copied_link_stops_working_when_access_is_revoked(env):
    client, db = env
    evidence = client.post(f"{API}/evidence", data={"project_id": str(IDS["project"]), "description": "Slab photo"},
                           files={"file": ("p.png", png_bytes(), "image/png")}, headers=auth("engineer")).json()
    assert "storage_key" not in evidence
    link = client.post(f"{API}/evidence/{evidence['_id']}/link", headers=auth("pm")).json()["url"]
    assert client.get(link.replace(settings.api_v1_prefix, API, 1)).status_code == 200
    assert client.get(link.replace(settings.api_v1_prefix, API, 1).replace("signature=", "signature=x")).status_code == 403
    assert client.post(f"{API}/evidence/{evidence['_id']}/link", headers=auth("pm_other")).status_code == 404

    async def revoke(db):
        await db.user_project_access.update_one({"user_id": str(IDS["pm"])}, {"$set": {"active": False}})

    run(revoke, db)
    assert client.get(link.replace(settings.api_v1_prefix, API, 1)).status_code == 404
    duplicate = client.post(f"{API}/evidence", data={"project_id": str(IDS["project"]), "description": "Same photo"},
                            files={"file": ("p.png", png_bytes(), "image/png")}, headers=auth("engineer")).json()
    assert duplicate["flags"][0]["code"] == "duplicate_image"
    assert client.patch(f"{API}/evidence/{evidence['_id']}/review", json={"review_status": "accepted", "note": "ok fine"}, headers=auth("engineer")).status_code == 403


# ----------------------------------------------------------- Phase 7

def test_urgent_safety_report_escalates_immediately_and_protects_identity(env):
    client, db = env
    report = client.post(f"{API}/hub/safety/reports", json={"report_type": "hazard", "severity": "urgent", "title": "Open shaft", "description": "Lift shaft on level 3 has no barrier.",
                                                           "project_id": str(IDS["project"]), "anonymous": True}, headers=auth("worker")).json()
    assert report["escalated_to_count"] == 1 and report["is_mine"]

    async def escalation(db):
        return await db.notifications.find_one({"user_id": str(IDS["pm"]), "category": "safety"}), await db.alerts.find_one({"rule": "urgent_safety_report"})

    note, alert = run(escalation, db)
    assert note and alert["severity"] == "critical"
    seen = client.get(f"{API}/hub/safety/reports/{report['_id']}", headers=auth("pm")).json()
    assert seen["reporter"] == "Anonymous" and "reporter_id" not in seen
    assert client.post(f"{API}/hub/safety/reports/{report['_id']}/reveal-reporter", json={"reason": "Need witness statement"}, headers=auth("admin")).status_code == 403

    async def grant(db):
        await db.users.update_one({"_id": IDS["admin"]}, {"$set": {"permissions": ["safety_reports.identity.reveal"]}})

    run(grant, db)
    revealed = client.post(f"{API}/hub/safety/reports/{report['_id']}/reveal-reporter", json={"reason": "Need witness statement"}, headers=auth("admin")).json()
    assert revealed["email"] == "worker@ops-tests.io"
    assert client.get(f"{API}/hub/safety/reports/{report['_id']}", headers=auth("pm_other")).status_code == 404


def test_corrective_action_closed_by_someone_else(env):
    client, _ = env
    report = client.post(f"{API}/hub/safety/reports", json={"report_type": "near_miss", "severity": "medium", "title": "Loose plank", "description": "Scaffold plank moved when stepped on.",
                                                           "project_id": str(IDS["project"])}, headers=auth("worker")).json()
    action = client.post(f"{API}/hub/safety/reports/{report['_id']}/actions", json={"title": "Fix plank", "description": "Secure all planks", "assignee_id": str(IDS["engineer"]),
                                                                                  "due_date": (NOW + timedelta(days=1)).isoformat()}, headers=auth("pm")).json()
    # Not the assignee and no assign rights: the action is invisible (404), not just forbidden.
    assert client.post(f"{API}/hub/safety/actions/{action['_id']}/update", json={"status": "done_pending_verification", "note": "Fixed"}, headers=auth("worker")).status_code == 404
    assert client.post(f"{API}/hub/safety/actions/{action['_id']}/update", json={"status": "done_pending_verification", "note": "Fixed"}, headers=auth("engineer")).status_code == 200
    closed = client.post(f"{API}/hub/safety/actions/{action['_id']}/close", json={"decision": "verified_closed", "verification_note": "Checked on site"}, headers=auth("pm")).json()
    assert closed["status"] == "verified_closed"


def test_suggestion_lifecycle_rules(env):
    client, _ = env
    sid = client.post(f"{API}/hub/suggestions", json={"title": "Reuse formwork", "problem": "Plywood formwork is thrown away after two uses.",
                                                      "proposed_solution": "Switch to aluminium formwork for typical floors.", "category": "material_wastage",
                                                      "project_id": str(IDS["project"]), "expected_benefit": "Less plywood waste"}, headers=auth("worker")).json()["_id"]
    t = lambda status, key, note=None: client.post(f"{API}/hub/suggestions/{sid}/transition", json={"to_status": status, "note": note}, headers=auth(key))
    assert t("under_review", "worker").status_code == 403
    assert t("under_review", "pm").status_code == 200
    assert t("rejected", "pm").status_code == 422
    assert t("approved_for_trial", "pm").status_code == 200
    assert t("in_implementation", "engineer").status_code == 200
    assert t("impact_verification", "engineer").status_code == 200
    assert t("implemented", "pm").status_code == 422  # no measured outcome yet
    client.post(f"{API}/hub/suggestions/{sid}/outcomes", json={"metric": "material_wastage_reduced", "value": 30, "unit": "sheets/month", "measured_on": "2026-10-14",
                                                              "method": "Store issue records, before vs after"}, headers=auth("engineer"))
    done = t("implemented", "pm").json()
    assert done["status"] == "implemented" and done["expected_benefit"] == "Less plywood waste" and done["measured_outcomes"][0]["kind"] == "measured"
    assert client.get(f"{API}/hub/suggestions/{sid}", headers=auth("pm_other")).status_code == 404


# ----------------------------------------------------------- Phase 8 voice

def _sign(url, params, token):
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def test_12_voice_webhook_requires_valid_signature(env, monkeypatch):
    client, db = env
    for key, value in {"voice_calls_enabled": True, "twilio_account_sid": "AC1", "twilio_auth_token": "secret", "twilio_from_number": "+15550001111", "public_base_url": "https://bt.example.org"}.items():
        monkeypatch.setattr(settings, key, value)
    client.post(f"{API}/monitoring/run", headers=auth("admin"))

    async def queue(db):
        from app.modules.voice.service import queue_call_for_alert

        alert = await db.alerts.find_one({"rule": "overdue_task", "user_id": str(IDS["worker"])})
        return await queue_call_for_alert(db, alert), alert

    call, alert = run(queue, db)
    assert call["status"] == "queued"
    path = f"{API}/voice/webhooks/gather?call_id={call['_id']}"
    assert client.post(path, data={"Digits": "1"}, headers={"X-Twilio-Signature": "forged"}).status_code == 403
    signature = _sign(f"https://bt.example.org{path}", {"Digits": "1"}, "secret")
    assert client.post(path, data={"Digits": "1"}, headers={"X-Twilio-Signature": signature}).status_code == 200

    async def acked(db):
        return await db.alerts.find_one({"_id": alert["_id"]})

    assert run(acked, db)["acknowledged_via"] == "voice"


def test_voice_call_needs_configuration_and_consent(env):
    client, db = env
    client.post(f"{API}/monitoring/run", headers=auth("admin"))

    async def queue(db):
        from app.modules.voice.service import queue_call_for_alert

        alert = await db.alerts.find_one({"user_id": str(IDS["pm"])})
        return await queue_call_for_alert(db, alert)

    call = run(queue, db)
    assert call["status"] == "skipped" and call["reason"] == "voice calls are not configured"


# ----------------------------------------------------------- access admin

def test_permission_grants_and_project_membership(env):
    client, _ = env
    assert client.put(f"{API}/access/users/{IDS['admin']}/permissions", json={"granted": ["audit_logs.read"]}, headers=auth("admin")).status_code == 403
    assert client.put(f"{API}/access/users/{IDS['engineer']}/permissions", json={"granted": ["made.up"]}, headers=auth("admin")).status_code == 422
    body = client.put(f"{API}/access/users/{IDS['engineer']}/permissions", json={"granted": ["procurement.payment.record"]}, headers=auth("admin")).json()
    assert "procurement.payment.record" in body["effective"]
    assert client.put(f"{API}/access/users/{IDS['engineer']}/permissions", json={"granted": []}, headers=auth("pm")).status_code == 403
    assert client.post(f"{API}/access/projects/{IDS['project']}/members", json={"user_id": str(IDS["pm_other"])}, headers=auth("pm")).status_code == 200
    assert client.post(f"{API}/access/projects/{IDS['other_project']}/members", json={"user_id": str(IDS["engineer"])}, headers=auth("pm")).status_code == 404
    logs = client.get(f"{API}/access/audit-logs", headers=auth("admin")).json()
    assert any(l["event_type"] == "user.permissions.changed" for l in logs)
    assert client.get(f"{API}/access/audit-logs", headers=auth("pm")).status_code == 403
