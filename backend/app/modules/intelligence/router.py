"""Risk, material, impact, budget and report endpoints (Phases 4 and 5)."""

import json
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.audit import record_audit
from app.core.config import settings
from app.core.permissions import ensure_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.ai import llm
from app.modules.intelligence import budget, impact, materials, reports, risk
from app.modules.intelligence.common import clean, utcnow
from app.modules.intelligence.data import AccessDenied, build_scope

router = APIRouter()

CLIENT_REPORT_TYPES = {"daily_site", "weekly_project"}
CLIENT_SAFE_SECTIONS = {"Progress", "Completed in period", "Milestones"}


def _denied(error: Exception):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))


# ------------------------------------------------------------------- risks

@router.get("/risks")
async def list_risks(project_id: Optional[str] = None, include_cleared: bool = False, current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    try:
        return clean(await risk.stored_assessments(db, scope, project_id, include_cleared))
    except AccessDenied as error:
        _denied(error)


@router.post("/risks/run")
async def run_risks(project_id: Optional[str] = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    try:
        return clean(await risk.run_risk_assessment(db, scope, project_id, persist=True))
    except AccessDenied as error:
        _denied(error)


class RiskReview(BaseModel):
    review_status: Literal["open", "acknowledged", "resolved", "dismissed"]
    note: Optional[str] = Field(default=None, max_length=1000)


@router.patch("/risks/{risk_id}")
async def review_risk(risk_id: str, body: RiskReview, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "risks.review")
    scope = await build_scope(db, current_user)
    record = await db.risk_assessments.find_one({"_id": ObjectId(risk_id)}) if ObjectId.is_valid(risk_id) else None
    if not record or not scope.includes_project(record.get("project_id")):
        raise HTTPException(status_code=404, detail="Risk assessment not found")
    if body.review_status == "dismissed" and not body.note:
        raise HTTPException(status_code=422, detail="Give a reason when dismissing a risk")
    entry = {"status": body.review_status, "note": body.note, "by": str(current_user["_id"]), "at": utcnow()}
    await db.risk_assessments.update_one({"_id": record["_id"]}, {"$set": {"review_status": body.review_status}, "$push": {"review_history": entry}})
    await record_audit(db, "risk.reviewed", actor=current_user, resource_type="risk_assessment", resource_id=risk_id, project_id=record.get("project_id"), details={"to": body.review_status})
    return clean(await db.risk_assessments.find_one({"_id": record["_id"]}))


# --------------------------------------------------------------- materials

@router.get("/materials/forecast")
async def forecast(project_id: Optional[str] = None, horizon_days: int = Query(30, ge=1, le=180), current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    try:
        return clean(await materials.material_forecast(db, scope, project_id, horizon_days))
    except AccessDenied as error:
        _denied(error)


class ReservationCreate(BaseModel):
    item_id: str
    project_id: str
    quantity: float = Field(..., gt=0)
    unit: Optional[str] = None
    needed_by: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=500)


@router.post("/materials/reservations")
async def create_reservation(body: ReservationCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    """Reserve stock for a project. A reservation only earmarks stock; it never
    changes quantities, which still move through inventory transactions."""
    ensure_permission(current_user, "inventory.adjust.assigned")
    scope = await build_scope(db, current_user)
    if not scope.includes_project(body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    item = await db.inventory.find_one({"_id": ObjectId(body.item_id)}) if ObjectId.is_valid(body.item_id) else None
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    if body.unit and item.get("unit") and materials.norm_unit(body.unit) != materials.norm_unit(item.get("unit")):
        raise HTTPException(status_code=422, detail=f"Unit must match the item's unit ({item.get('unit')})")
    doc = {**body.model_dump(), "unit": item.get("unit"), "status": "active", "created_by": str(current_user["_id"]), "created_at": utcnow()}
    result = await db.inventory_reservations.insert_one(doc)
    await record_audit(db, "inventory.reserved", actor=current_user, resource_type="inventory_item", resource_id=body.item_id, project_id=body.project_id, details={"quantity": body.quantity, "reason": body.reason})
    return clean({**doc, "_id": result.inserted_id})


@router.post("/materials/reservations/{reservation_id}/release")
async def release_reservation(reservation_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "inventory.adjust.assigned")
    scope = await build_scope(db, current_user)
    record = await db.inventory_reservations.find_one({"_id": ObjectId(reservation_id)}) if ObjectId.is_valid(reservation_id) else None
    if not record or not scope.includes_project(record.get("project_id")):
        raise HTTPException(status_code=404, detail="Reservation not found")
    await db.inventory_reservations.update_one({"_id": record["_id"]}, {"$set": {"status": "released", "released_by": str(current_user["_id"]), "released_at": utcnow()}})
    await record_audit(db, "inventory.reservation_released", actor=current_user, resource_type="inventory_reservation", resource_id=reservation_id, project_id=record.get("project_id"))
    return {"message": "Reservation released"}


# ------------------------------------------------------------------ impact

class ImpactRequest(BaseModel):
    kind: Literal["purchase_order", "task"]
    record_id: str
    delay_days: int = Field(..., ge=1, le=365)


@router.post("/impact")
async def delay_impact(body: ImpactRequest, current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    try:
        return clean(await impact.analyze_impact(db, scope, kind=body.kind, record_id=body.record_id, delay_days=body.delay_days))
    except AccessDenied as error:
        _denied(error)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


# ------------------------------------------------------------------ budget

@router.get("/budget")
async def budget_view(project_id: Optional[str] = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    try:
        return clean(await budget.budget_overview(db, scope, project_id))
    except AccessDenied as error:
        _denied(error)


# ----------------------------------------------------------------- reports

@router.get("/reports/types")
async def report_types(current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    if not scope.can("reports.generate"):
        return []
    return [{"type": key, "title": title, "needs_project": needs_project, "default_days": days}
            for key, (title, needs, needs_project, days) in reports.REPORT_TYPES.items() if scope.can(*needs)]


class ReportRequest(BaseModel):
    report_type: str
    project_id: Optional[str] = None
    days: Optional[int] = Field(default=None, ge=0, le=366)
    ai_summary: bool = False


async def _ai_summary(report: dict, role: str) -> dict:
    response = await llm.create_message(
        system=("You write short narrative summaries of construction operations reports for a " + role + ". "
                "Use only facts and figures present in the report JSON. Do not add numbers, causes or predictions that are not in it. "
                "Mention the stated limitations if they matter. 120-220 words, plain text, no headings."),
        messages=[{"role": "user", "content": [{"type": "text", "text": json.dumps(report, default=str)}]}],
        max_tokens=2000,
        effort="low",
    )
    return {"text": llm.response_text(response), "model": settings.ai_model, "generated_at": utcnow().isoformat(),
            "label": "AI-written summary of the figures above. Check against the report before relying on it."}


@router.post("/reports")
async def create_report(body: ReportRequest, current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    try:
        report = await reports.generate_report(db, scope, body.report_type, body.project_id, body.days)
    except AccessDenied as error:
        _denied(error)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    summary, summary_error = None, None
    if body.ai_summary:
        ensure_permission(current_user, "ai.report.generate")
        try:
            summary = await _ai_summary(report, str(current_user.get("role")))
            await db.ai_usage.insert_one({"user_id": str(current_user["_id"]), "at": utcnow(), "kind": "report_summary", "model": settings.ai_model})
        except (llm.AINotConfigured, llm.AIUnavailable) as error:
            summary_error = str(error)
    doc = {"owner_id": str(current_user["_id"]), "type": body.report_type, "project_id": body.project_id, "report": report,
           "ai_summary": summary, "client_visible": False, "created_at": utcnow()}
    result = await db.generated_reports.insert_one(doc)
    await record_audit(db, "report.generated", actor=current_user, resource_type="generated_report", resource_id=str(result.inserted_id), project_id=body.project_id, details={"type": body.report_type})
    return clean({**doc, "_id": result.inserted_id, "ai_summary_error": summary_error})


def _client_view(doc: dict) -> dict:
    report = dict(doc["report"])
    report["sections"] = [s for s in report["sections"] if s["title"] in CLIENT_SAFE_SECTIONS]
    report["limitations"] = [l for l in report["limitations"] if "progress" in l.lower()]
    report.pop("data_freshness", None)
    return {**doc, "report": report, "ai_summary": None}


async def _visible_report(db, scope, report_id: str) -> dict:
    doc = await db.generated_reports.find_one({"_id": ObjectId(report_id)}) if ObjectId.is_valid(report_id) else None
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")
    user_id = str(scope.user["_id"])
    if doc["owner_id"] == user_id:
        return doc
    in_scope = doc.get("project_id") is None and scope.project_ids is None or (doc.get("project_id") and scope.includes_project(doc["project_id"]))
    if scope.user.get("role") == "client":
        if doc.get("client_visible") and in_scope and scope.can("reports.read.assigned"):
            return _client_view(doc)
        raise HTTPException(status_code=404, detail="Report not found")
    if in_scope and scope.can("reports.generate") and scope.can(*reports.REPORT_TYPES[doc["type"]][1]):
        return doc
    raise HTTPException(status_code=404, detail="Report not found")


@router.get("/reports")
async def list_reports(current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    ensure_permission(current_user, "reports.read.assigned", "reports.generate")
    docs = await db.generated_reports.find({}, {"report.sections": 0}).sort("created_at", -1).to_list(500)
    visible = []
    for doc in docs:
        try:
            visible.append(await _visible_report(db, scope, str(doc["_id"])))
        except HTTPException:
            continue
    return clean([{"_id": d["_id"], "type": d["type"], "title": d["report"]["title"], "project_id": d.get("project_id"), "client_visible": d.get("client_visible"),
                   "created_at": d["created_at"], "owner_id": d["owner_id"] if current_user.get("role") != "client" else None} for d in visible[:100]])


@router.get("/reports/{report_id}")
async def get_report(report_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    scope = await build_scope(db, current_user)
    return clean(await _visible_report(db, scope, report_id))


@router.post("/reports/{report_id}/publish")
async def publish_report(report_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "reports.publish")
    scope = await build_scope(db, current_user)
    doc = await _visible_report(db, scope, report_id)
    if doc["type"] not in CLIENT_REPORT_TYPES or not doc.get("project_id"):
        raise HTTPException(status_code=422, detail="Only daily site and weekly project reports for a single project can be shared with clients")
    await db.generated_reports.update_one({"_id": doc["_id"]}, {"$set": {"client_visible": True, "published_by": str(current_user["_id"]), "published_at": utcnow()}})
    await record_audit(db, "report.published", actor=current_user, resource_type="generated_report", resource_id=report_id, project_id=doc.get("project_id"))
    return {"message": "Report shared with the project's client"}


@router.get("/reports/{report_id}/export")
async def export_report(report_id: str, format: Literal["csv", "json"] = "csv", current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "reports.export.assigned")
    scope = await build_scope(db, current_user)
    doc = await _visible_report(db, scope, report_id)
    await record_audit(db, "report.exported", actor=current_user, resource_type="generated_report", resource_id=report_id, project_id=doc.get("project_id"), details={"format": format})
    name = f"{doc['type']}-{doc['created_at'].strftime('%Y%m%d')}"
    if format == "json":
        return Response(json.dumps(clean(doc["report"]), indent=2), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    return Response(reports.report_to_csv(clean(doc["report"])), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
