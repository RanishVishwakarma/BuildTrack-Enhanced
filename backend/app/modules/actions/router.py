"""Action Center endpoints: recommendations, approvals, execution, verification."""

from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.audit import record_audit
from app.core.permissions import ensure_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.actions import service
from app.modules.intelligence.common import clean
from app.modules.intelligence.data import build_scope

router = APIRouter()


async def _scoped_query(db, user) -> dict:
    scope = await build_scope(db, user)
    if scope.project_ids is None:
        return {}
    return {"$or": [{"project_id": {"$in": list(scope.project_ids)}}, {"owner_id": str(user["_id"])}, {"created_by": str(user["_id"])}]}


async def _load(db, user, rec_id: str) -> dict:
    if not ObjectId.is_valid(rec_id):
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec = await db.ai_recommendations.find_one({"$and": [{"_id": ObjectId(rec_id)}, await _scoped_query(db, user)]})
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


@router.get("")
async def list_recommendations(status: Optional[str] = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.recommendation.review")
    query = await _scoped_query(db, current_user)
    if status:
        query = {"$and": [query, {"status": status}]}
    return clean(await db.ai_recommendations.find(query).sort([("status", 1), ("created_at", -1)]).to_list(500))


@router.post("/generate")
async def generate(current_user=Depends(get_current_user), db=Depends(get_database)):
    """Create recommendations from the material and procurement engines for
    the user's projects. Duplicates of open recommendations are skipped."""
    ensure_permission(current_user, "ai.recommendation.review")
    scope = await build_scope(db, current_user)
    from app.modules.monitoring.engine import project_managers

    async def owner(pid):
        managers = await project_managers(db, pid)
        return managers[0] if managers else None

    created = await service.generate_from_engines(db, scope, owner)
    return {"created": created}


class ManualProposal(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    rationale: str = Field(..., min_length=10, max_length=2000)
    project_id: str
    priority: Literal["low", "medium", "high"] = "medium"
    instruction: str = Field(..., min_length=5, max_length=2000)


@router.post("")
async def propose_manual(body: ManualProposal, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.recommendation.review")
    scope = await build_scope(db, current_user)
    if not scope.includes_project(body.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    rec = await service.propose(db, title=body.title, rationale=body.rationale, project_id=body.project_id, priority=body.priority,
                                action={"type": "manual", "params": {"instruction": body.instruction}}, created_by=str(current_user["_id"]), source="user")
    await record_audit(db, "recommendation.proposed", actor=current_user, resource_type="recommendation", resource_id=str(rec["_id"]), project_id=body.project_id)
    return clean(rec)


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/{rec_id}/decision")
async def decide(rec_id: str, body: Decision, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.recommendation.approve")
    rec = await _load(db, current_user, rec_id)
    try:
        return clean(await service.decide(db, current_user, rec, body.decision, body.note))
    except service.WorkflowError as error:
        raise HTTPException(status_code=error.status, detail=str(error))


@router.post("/{rec_id}/execute")
async def retry_execution(rec_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    """Re-run a failed execution. Safe to repeat: executors reuse what an
    earlier attempt created."""
    ensure_permission(current_user, "ai.recommendation.approve")
    rec = await _load(db, current_user, rec_id)
    if rec["status"] != "execution_failed":
        raise HTTPException(status_code=409, detail="Only failed executions can be retried")
    await db.ai_recommendations.update_one({"_id": rec["_id"], "status": "execution_failed"}, {"$set": {"status": "approved"}})
    return clean(await service.execute(db, current_user, rec["_id"]))


class Verification(BaseModel):
    effective: bool
    note: str = Field(..., min_length=5, max_length=2000)


@router.post("/{rec_id}/verify")
async def verify(rec_id: str, body: Verification, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.recommendation.review")
    rec = await _load(db, current_user, rec_id)
    try:
        return clean(await service.verify(db, current_user, rec, body.effective, body.note))
    except service.WorkflowError as error:
        raise HTTPException(status_code=error.status, detail=str(error))


@router.get("/activity")
async def activity(current_user=Depends(get_current_user), db=Depends(get_database)):
    """Recent recommendation, alert and AI events visible to this user."""
    ensure_permission(current_user, "ai.query")
    events = await db.audit_logs.find({"actor_id": str(current_user["_id"]), "event_type": {"$regex": "^(ai\\.|recommendation\\.|alert\\.|report\\.|risk\\.|evidence\\.|voice)"}}).sort("timestamp", -1).to_list(100)
    return clean(events)
