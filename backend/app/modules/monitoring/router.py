"""Monitoring endpoints: own alerts, acknowledgement, runs (Phase 3)."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.core.audit import record_audit
from app.core.permissions import ensure_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.intelligence.common import clean, utcnow
from app.modules.monitoring.engine import run_monitoring

router = APIRouter()


@router.get("/alerts")
async def my_alerts(status: str = "open", current_user=Depends(get_current_user), db=Depends(get_database)):
    query = {"user_id": str(current_user["_id"])}
    if status != "all":
        query["status"] = status
    rows = await db.alerts.find(query).sort([("severity_rank", -1), ("created_at", -1)]).to_list(200)
    return clean(rows)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge(alert_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    alert = await db.alerts.find_one({"_id": ObjectId(alert_id), "user_id": str(current_user["_id"])}) if ObjectId.is_valid(alert_id) else None
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if not alert.get("acknowledged_at"):
        await db.alerts.update_one({"_id": alert["_id"]}, {"$set": {"acknowledged_at": utcnow(), "acknowledged_via": "app"}})
        # An acknowledged alert no longer needs a call.
        await db.voice_calls.update_many({"alert_id": alert_id, "status": "queued"}, {"$set": {"status": "cancelled", "reason": "acknowledged in app"}})
        await record_audit(db, "alert.acknowledged", actor=current_user, resource_type="alert", resource_id=alert_id, project_id=alert.get("project_id"))
    return clean(await db.alerts.find_one({"_id": alert["_id"]}))


@router.post("/run")
async def run_now(current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "monitoring.run")
    return clean(await run_monitoring(db, trigger="manual", actor=current_user))


@router.get("/runs")
async def runs(current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "monitoring.run")
    return clean(await db.job_runs.find({}).sort("started_at", -1).to_list(50))
