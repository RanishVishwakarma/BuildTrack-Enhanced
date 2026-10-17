"""Voice call endpoints: consent, call logs, manual calls and provider webhooks."""

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.audit import record_audit
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.intelligence.common import clean, utcnow
from app.modules.intelligence.data import build_scope
from app.modules.voice import service

router = APIRouter()


class Preferences(BaseModel):
    voice_consent: bool
    phone: Optional[str] = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$", description="E.164 format, e.g. +919876543210")


@router.get("/preferences")
async def get_preferences(current_user=Depends(get_current_user)):
    return {"voice_consent": bool(current_user.get("voice_consent")), "phone": service.mask_phone(current_user.get("phone")),
            "can_receive": has_permission(current_user, "voice_calls.receive"), "calls_enabled": service.voice_enabled()}


@router.put("/preferences")
async def set_preferences(body: Preferences, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "voice_calls.receive")
    if body.voice_consent and not (body.phone or current_user.get("phone")):
        raise HTTPException(status_code=422, detail="A phone number is needed to receive calls")
    update = {"voice_consent": body.voice_consent, "voice_consent_at": utcnow()}
    if body.phone:
        update["phone"] = body.phone
    await db.users.update_one({"_id": current_user["_id"]}, {"$set": update})
    if not body.voice_consent:
        await db.voice_calls.update_many({"user_id": str(current_user["_id"]), "status": "queued"}, {"$set": {"status": "cancelled", "reason": "consent withdrawn"}})
    await record_audit(db, "voice.consent.changed", actor=current_user, resource_type="user", resource_id=str(current_user["_id"]), details={"consent": body.voice_consent})
    return {"voice_consent": body.voice_consent}


def _public(call: dict) -> dict:
    call = clean(call)
    call.pop("phone", None)
    return call


@router.get("/calls")
async def call_logs(current_user=Depends(get_current_user), db=Depends(get_database)):
    if has_permission(current_user, "voice_calls.logs.read.assigned"):
        scope = await build_scope(db, current_user)
        query = {} if scope.project_ids is None else {"$or": [{"project_id": {"$in": list(scope.project_ids)}}, {"user_id": str(current_user["_id"])}]}
    else:
        query = {"user_id": str(current_user["_id"])}
    rows = await db.voice_calls.find(query).sort("created_at", -1).to_list(200)
    return [_public(r) for r in rows]


@router.post("/alerts/{alert_id}/call")
async def call_about_alert(alert_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "voice_calls.initiate.assigned")
    alert = await db.alerts.find_one({"_id": ObjectId(alert_id)}) if ObjectId.is_valid(alert_id) else None
    scope = await build_scope(db, current_user)
    if not alert or not scope.includes_project(alert.get("project_id")):
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.get("status") != "open" or alert.get("acknowledged_at"):
        raise HTTPException(status_code=409, detail="The alert is already acknowledged or resolved")
    call = await service.queue_call_for_alert(db, alert, requested_by=current_user)
    await record_audit(db, "voice_call.requested", actor=current_user, resource_type="alert", resource_id=alert_id, project_id=alert.get("project_id"), details={"status": call.get("status")})
    return _public(call)


async def _verified_form(request: Request) -> dict:
    if not service.voice_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    form = dict((await request.form()).items())
    # Twilio signs the public URL it called, including the query string.
    url = service.settings.public_base_url.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    if not service.valid_twilio_signature(url, form, request.headers.get("X-Twilio-Signature")):
        raise HTTPException(status_code=403, detail="Invalid signature")
    return form


@router.post("/webhooks/gather")
async def gather_webhook(request: Request, call_id: str, db=Depends(get_database)):
    form = await _verified_form(request)
    return Response(await service.handle_gather(db, call_id, str(form.get("Digits", ""))), media_type="application/xml")


@router.post("/webhooks/status")
async def status_webhook(request: Request, call_id: str, db=Depends(get_database)):
    form = await _verified_form(request)
    await service.handle_status(db, call_id, str(form.get("CallStatus", "")))
    return Response("<Response/>", media_type="application/xml")
