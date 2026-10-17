"""Optional automated voice calls for unacknowledged critical alerts (Phase 8).

Off unless VOICE_CALLS_ENABLED=true and every TWILIO_* setting and
PUBLIC_BASE_URL are configured. Safeguards:
  * the recipient must hold voice_calls.receive, have given consent and a phone number;
  * calls are only placed inside VOICE_CALL_HOURS (VOICE_CALL_TIMEZONE);
  * one call record per alert, at most VOICE_MAX_ATTEMPTS attempts;
  * a queued call is cancelled when its alert is acknowledged or resolved;
  * after the last failed attempt a person is notified to follow up;
  * provider webhooks must carry a valid Twilio signature;
  * a keypress only acknowledges the alert. It never edits tasks, stock or orders.
Calls are not a substitute for emergency services.
"""

import base64
import hashlib
import hmac
import logging
from datetime import datetime, time, timedelta
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import httpx
from bson import ObjectId

from app.core.audit import record_audit
from app.core.config import settings
from app.core.permissions import effective_permissions
from app.modules.intelligence.common import utcnow
from app.modules.notifications.db import create_notification

logger = logging.getLogger(__name__)
RETRY_MINUTES = 15
RETENTION_DAYS = 90


def voice_enabled() -> bool:
    return bool(settings.voice_calls_enabled and settings.twilio_account_sid and settings.twilio_auth_token
                and settings.twilio_from_number and settings.public_base_url)


def within_call_hours(moment: datetime | None = None) -> bool:
    moment = moment or utcnow()
    try:
        start_text, end_text = settings.voice_call_hours.split("-")
        start, end = time.fromisoformat(start_text.strip()), time.fromisoformat(end_text.strip())
        local = moment.astimezone(ZoneInfo(settings.voice_call_timezone)).time()
    except Exception:
        logger.error("Invalid VOICE_CALL_HOURS or VOICE_CALL_TIMEZONE; no calls will be placed")
        return False
    return start <= local <= end


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    return ("*" * max(0, len(digits) - 4)) + digits[-4:]


async def queue_call_for_alert(db, alert: dict, requested_by: dict | None = None) -> dict:
    """Queue (or explain why not) a call about an alert. Idempotent per alert."""
    alert_id = str(alert["_id"])
    existing = await db.voice_calls.find_one({"alert_id": alert_id})
    if existing:
        return existing
    user = await db.users.find_one({"_id": ObjectId(alert["user_id"])}) if ObjectId.is_valid(str(alert.get("user_id"))) else None
    reason = None
    if not voice_enabled():
        reason = "voice calls are not configured"
    elif not user or str(user.get("status", "active")).lower() != "active":
        reason = "recipient account is not active"
    elif "voice_calls.receive" not in effective_permissions(user):
        reason = "recipient's role does not receive automated calls"
    elif not user.get("voice_consent"):
        reason = "recipient has not consented to automated calls"
    elif not user.get("phone"):
        reason = "recipient has no phone number"
    now = utcnow()
    record = {
        "alert_id": alert_id, "user_id": alert["user_id"], "project_id": alert.get("project_id"),
        "message": f"{alert['title']}. {alert['message']}"[:400],
        "status": "skipped" if reason else "queued", "reason": reason, "attempts": 0, "next_attempt_at": now,
        "created_at": now, "retention_until": now + timedelta(days=RETENTION_DAYS),
        "requested_by": str(requested_by["_id"]) if requested_by else "escalation",
    }
    try:
        result = await db.voice_calls.insert_one(record)
    except Exception:  # unique index on alert_id: another run queued it first
        return await db.voice_calls.find_one({"alert_id": alert_id})
    record["_id"] = result.inserted_id
    return record


def twiml_for(call: dict) -> str:
    base = settings.public_base_url.rstrip("/")
    action = f"{base}{settings.api_v1_prefix}/voice/webhooks/gather?call_id={call['_id']}"
    text = escape(call["message"])
    return (
        "<Response>"
        f'<Gather numDigits="1" timeout="8" method="POST" action="{escape(action)}">'
        "<Say>Hello. This is an automated assistant calling from BuildTrack.</Say>"
        f"<Say>{text}</Say>"
        "<Say>Press 1 to acknowledge. Press 2 to ask your manager to call you back.</Say>"
        "</Gather>"
        "<Say>No response was received. The alert remains open in BuildTrack. Goodbye.</Say>"
        "</Response>"
    )


async def _place_call(call: dict, phone: str) -> str:
    """Start a call with Twilio. Returns the provider call SID."""
    base = settings.public_base_url.rstrip("/")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Calls.json"
    data = {
        "To": phone,
        "From": settings.twilio_from_number,
        "Twiml": twiml_for(call),
        "StatusCallback": f"{base}{settings.api_v1_prefix}/voice/webhooks/status?call_id={call['_id']}",
        "StatusCallbackEvent": "completed",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, data=data, auth=(settings.twilio_account_sid, settings.twilio_auth_token))
    response.raise_for_status()
    return response.json()["sid"]


async def _give_up(db, call: dict, why: str) -> None:
    await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"status": "failed", "reason": why, "finished_at": utcnow()}})
    alert = await db.alerts.find_one({"_id": ObjectId(call["alert_id"])}) if ObjectId.is_valid(call["alert_id"]) else None
    from app.modules.monitoring.engine import admins, project_managers

    people = await project_managers(db, call.get("project_id")) or await admins(db)
    for user_id in people:
        await create_notification(db, {"user_id": user_id, "title": "Automated call failed - follow up in person",
                                       "message": f"Could not reach the person responsible ({why}). {alert['title'] if alert else ''}",
                                       "type": "error", "category": "escalation", "entity_type": "alert", "entity_id": call["alert_id"]})


async def dispatch_due_calls(db) -> int:
    """Place queued calls that are due. Called by the scheduler."""
    if not voice_enabled():
        return 0
    now = utcnow()
    await db.voice_calls.delete_many({"retention_until": {"$lte": now}})
    if not within_call_hours(now):
        return 0
    placed = 0
    for call in await db.voice_calls.find({"status": "queued", "next_attempt_at": {"$lte": now}}).to_list(50):
        claimed = await db.voice_calls.update_one({"_id": call["_id"], "status": "queued"}, {"$set": {"status": "dialing"}, "$inc": {"attempts": 1}})
        if claimed.modified_count != 1:
            continue
        alert = await db.alerts.find_one({"_id": ObjectId(call["alert_id"])}) if ObjectId.is_valid(call["alert_id"]) else None
        if not alert or alert.get("status") != "open" or alert.get("acknowledged_at"):
            await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"status": "cancelled", "reason": "alert no longer open"}})
            continue
        user = await db.users.find_one({"_id": ObjectId(call["user_id"])})
        if not user or not user.get("voice_consent") or not user.get("phone"):
            await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"status": "cancelled", "reason": "consent or phone withdrawn"}})
            continue
        try:
            sid = await _place_call(call, user["phone"])
            await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"status": "initiated", "provider_sid": sid, "initiated_at": utcnow()}})
            placed += 1
        except Exception as error:
            logger.warning("Voice call %s failed: %s", call["_id"], error)
            if call.get("attempts", 0) + 1 >= settings.voice_max_attempts:
                await _give_up(db, call, "provider error")
            else:
                await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"status": "queued", "next_attempt_at": utcnow() + timedelta(minutes=RETRY_MINUTES), "last_error": "provider error"}})
    return placed


def valid_twilio_signature(url: str, params: dict, signature: str | None) -> bool:
    """Twilio request validation: base64(HMAC-SHA1(token, url + sorted params))."""
    if not signature or not settings.twilio_auth_token:
        return False
    payload = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(settings.twilio_auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


async def handle_gather(db, call_id: str, digits: str) -> str:
    call = await db.voice_calls.find_one({"_id": ObjectId(call_id)}) if ObjectId.is_valid(call_id) else None
    if not call:
        return "<Response><Say>Sorry, this call could not be matched.</Say></Response>"
    now = utcnow()
    if digits == "1":
        await db.alerts.update_one({"_id": ObjectId(call["alert_id"]), "acknowledged_at": None}, {"$set": {"acknowledged_at": now, "acknowledged_via": "voice"}})
        await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"outcome": "acknowledged", "outcome_at": now}})
        await record_audit(db, "voice_call.acknowledged", actor={"_id": call["user_id"], "role": None}, resource_type="alert", resource_id=call["alert_id"], project_id=call.get("project_id"))
        return "<Response><Say>Thank you. The alert is marked as acknowledged. Please update the record in BuildTrack.</Say></Response>"
    if digits == "2":
        from app.modules.monitoring.engine import admins, project_managers

        await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"outcome": "callback_requested", "outcome_at": now}})
        for user_id in await project_managers(db, call.get("project_id")) or await admins(db):
            await create_notification(db, {"user_id": user_id, "title": "Call-back requested", "message": f"The person called about '{call['message'][:120]}' asked for a call back.",
                                           "type": "warning", "category": "escalation", "entity_type": "alert", "entity_id": call["alert_id"]})
        return "<Response><Say>Thank you. Your manager has been asked to call you back.</Say></Response>"
    return "<Response><Say>No valid option was chosen. The alert remains open. Goodbye.</Say></Response>"


async def handle_status(db, call_id: str, call_status: str) -> None:
    call = await db.voice_calls.find_one({"_id": ObjectId(call_id)}) if ObjectId.is_valid(call_id) else None
    if not call:
        return
    status = (call_status or "").lower()
    if status == "completed":
        await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"status": "completed", "finished_at": utcnow()}})
    elif status in {"busy", "no-answer", "failed", "canceled"}:
        if call.get("attempts", 0) >= settings.voice_max_attempts:
            await _give_up(db, call, status)
        else:
            await db.voice_calls.update_one({"_id": call["_id"]}, {"$set": {"status": "queued", "next_attempt_at": utcnow() + timedelta(minutes=RETRY_MINUTES), "last_error": status}})
