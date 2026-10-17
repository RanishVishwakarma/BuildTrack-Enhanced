"""Recommendations and the approval workflow (spec §19).

    detect -> collect evidence -> calculate -> recommend -> check permissions
           -> approve (a person) -> execute (allow-listed, idempotent) -> verify -> audit

Only the action types in EXECUTORS can be executed, and each needs the same
permission a person would need to do it by hand. Anything else (purchase-order
approval, payments, budget or schedule changes) is a "manual" recommendation:
approving it records the decision; a person still does the work in the normal
screens. Executing an approved recommendation never skips that module's own
workflow, e.g. a material request it raises still awaits procurement approval.
"""

from datetime import timedelta

from bson import ObjectId

from app.core.audit import record_audit
from app.core.permissions import has_permission
from app.modules.intelligence import materials
from app.modules.intelligence.common import norm_text, parse_dt, utcnow
from app.modules.notifications.db import create_notification


class WorkflowError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


async def _exec_material_request(db, user, rec, params) -> dict:
    existing = await db.material_requests.find_one({"source_recommendation_id": str(rec["_id"])})
    if existing:
        return {"material_request_id": str(existing["_id"]), "request_id": existing.get("request_id"), "reused": True}
    project = await db.projects.find_one({"_id": ObjectId(params["project_id"])}) if ObjectId.is_valid(str(params.get("project_id"))) else None
    if not project:
        raise WorkflowError(422, "The recommendation's project no longer exists")
    from app.modules.procurement.db import next_code

    now = utcnow()
    doc = {
        "request_id": await next_code(db, "material_requests", "MR"), "project": project.get("name"), "project_id": str(project["_id"]),
        "material_name": params["material_name"], "material_id": params.get("material_id"), "unit": params.get("unit"),
        "quantity": float(params["quantity"]), "required_date": parse_dt(params.get("required_date")) or now + timedelta(days=7),
        "priority": params.get("priority", "high"), "remarks": f"Raised from approved recommendation: {rec['title']}",
        "status": "pending", "requested_by": str(user["_id"]), "source_recommendation_id": str(rec["_id"]), "created_at": now, "updated_at": now,
    }
    result = await db.material_requests.insert_one(doc)
    return {"material_request_id": str(result.inserted_id), "request_id": doc["request_id"], "status": "pending approval"}


async def _exec_reserve(db, user, rec, params) -> dict:
    existing = await db.inventory_reservations.find_one({"source_recommendation_id": str(rec["_id"])})
    if existing:
        return {"reservation_id": str(existing["_id"]), "reused": True}
    item = await db.inventory.find_one({"_id": ObjectId(params["item_id"])}) if ObjectId.is_valid(str(params.get("item_id"))) else None
    if not item:
        raise WorkflowError(422, "The inventory item no longer exists")
    result = await db.inventory_reservations.insert_one({"item_id": params["item_id"], "project_id": params["project_id"], "quantity": float(params["quantity"]),
                                                         "unit": item.get("unit"), "status": "active", "reason": rec["title"], "created_by": str(user["_id"]),
                                                         "source_recommendation_id": str(rec["_id"]), "created_at": utcnow()})
    return {"reservation_id": str(result.inserted_id)}


async def _exec_notify(db, user, rec, params) -> dict:
    existing = await db.notifications.find_one({"source_recommendation_id": str(rec["_id"])})
    if existing:
        return {"notification_id": str(existing["_id"]), "reused": True}
    note = await create_notification(db, {"user_id": params["user_id"], "title": rec["title"], "message": params["message"][:1000], "type": "info",
                                          "category": "recommendation", "entity_type": "recommendation", "entity_id": str(rec["_id"]),
                                          "source_recommendation_id": str(rec["_id"])})
    return {"notification_id": str(note["_id"])}


EXECUTORS = {
    "create_material_request": ("procurement.request.create", _exec_material_request),
    "reserve_stock": ("inventory.adjust.assigned", _exec_reserve),
    "notify_user": ("notifications.send.assigned", _exec_notify),
}


async def propose(db, *, title: str, rationale: str, project_id: str | None, action: dict, priority: str, created_by: str,
                  sources: list | None = None, dedup_key: str | None = None, owner_id: str | None = None, deadline=None, source: str = "system") -> dict | None:
    """Create a recommendation unless an open one with the same key exists."""
    if action.get("type") not in EXECUTORS and action.get("type") != "manual":
        raise WorkflowError(422, "Unsupported action type")
    if dedup_key and await db.ai_recommendations.find_one({"dedup_key": dedup_key, "status": {"$in": ["proposed", "approved", "executing"]}}):
        return None
    now = utcnow()
    doc = {"title": title, "rationale": rationale, "project_id": project_id, "action": action, "priority": priority, "owner_id": owner_id,
           "deadline": deadline, "sources": sources or [], "status": "proposed", "created_by": created_by, "source": source,
           "dedup_key": dedup_key, "created_at": now, "updated_at": now, "history": [{"status": "proposed", "by": created_by, "at": now}]}
    result = await db.ai_recommendations.insert_one(doc)
    return {**doc, "_id": result.inserted_id}


async def generate_from_engines(db, scope, owner_lookup) -> int:
    """Turn calculated shortages and late deliveries into recommendations."""
    created = 0
    forecast = await materials.material_forecast(db, scope, horizon_days=21)
    by_name = {norm_text(p.get("name")): p for p in scope.projects}
    for row in forecast["shortages"]:
        demand = sorted(row["demand"], key=lambda d: d["required_date"] or "9999")
        project = by_name.get(norm_text(demand[0]["project"])) if demand else None
        if not project:
            continue
        pid = str(project["_id"])
        rec = await propose(
            db, title=f"Raise a material request for {row['projected_shortfall']:g} {row['unit'] or ''} {row['material']}".replace("  ", " "),
            rationale=f"Projected shortfall: {row['shortfall_formula']} = {row['projected_shortfall']:g}. Needed by {(row['next_required_date'] or 'unspecified')[:10]}.",
            project_id=pid, priority="high",
            action={"type": "create_material_request", "params": {"project_id": pid, "material_name": row["material"], "material_id": row["item_id"],
                                                                   "unit": row["unit"], "quantity": row["projected_shortfall"], "required_date": row["next_required_date"], "priority": "high"}},
            created_by="system", sources=[{"type": "inventory_item", "id": row["item_id"], "label": row["material"]}],
            dedup_key=f"shortage:{row['item_id']}:{pid}", owner_id=await owner_lookup(pid), deadline=parse_dt(row["next_required_date"]), source="materials_engine")
        created += rec is not None
    from app.modules.intelligence.data import procurement_status

    status = await procurement_status(db, scope)
    for order in status["overdue_deliveries"]:
        project = by_name.get(norm_text(order["project"]))
        pid = str(project["_id"]) if project else None
        rec = await propose(
            db, title=f"Get a confirmed delivery date for {order['po_number']}",
            rationale=f"{order['materials']} was expected {(order['expected_delivery_date'] or '')[:10]} and is {order['days_late']} day(s) late.",
            project_id=pid, priority="high" if order["days_late"] >= 7 else "medium",
            action={"type": "manual", "params": {"instruction": "Contact the vendor, record the confirmed date on the purchase order, and assess the delay impact."}},
            created_by="system", sources=[{"type": "purchase_order", "id": order["id"], "label": order["po_number"]}],
            dedup_key=f"late_po:{order['id']}", owner_id=await owner_lookup(pid), source="procurement_monitor")
        created += rec is not None
    return created


async def decide(db, user, rec: dict, decision: str, note: str | None) -> dict:
    if rec["status"] != "proposed":
        raise WorkflowError(409, f"This recommendation is already {rec['status']}")
    if rec.get("created_by") == str(user["_id"]):
        raise WorkflowError(403, "A recommendation must be approved by someone other than its proposer")
    if decision == "reject" and not note:
        raise WorkflowError(422, "A reason is required to reject")
    now = utcnow()
    if decision == "reject":
        await db.ai_recommendations.update_one({"_id": rec["_id"], "status": "proposed"}, {"$set": {"status": "rejected", "updated_at": now, "decided_by": str(user["_id"])},
                                                                                         "$push": {"history": {"status": "rejected", "note": note, "by": str(user["_id"]), "at": now}}})
        await record_audit(db, "recommendation.rejected", actor=user, resource_type="recommendation", resource_id=str(rec["_id"]), project_id=rec.get("project_id"))
        return await db.ai_recommendations.find_one({"_id": rec["_id"]})

    action_type = rec["action"]["type"]
    if action_type != "manual":
        permission = EXECUTORS[action_type][0]
        if not has_permission(user, permission):
            raise WorkflowError(403, f"Approving this executes an action that needs '{permission}', which you do not hold")
    claimed = await db.ai_recommendations.update_one({"_id": rec["_id"], "status": "proposed"}, {"$set": {"status": "approved", "decided_by": str(user["_id"]), "approved_at": now, "updated_at": now},
                                                                                              "$push": {"history": {"status": "approved", "note": note, "by": str(user["_id"]), "at": now}}})
    if claimed.modified_count != 1:
        raise WorkflowError(409, "The recommendation changed; reload and try again")
    await record_audit(db, "recommendation.approved", actor=user, resource_type="recommendation", resource_id=str(rec["_id"]), project_id=rec.get("project_id"), correlation_id=str(rec["_id"]))
    if action_type == "manual":
        return await db.ai_recommendations.find_one({"_id": rec["_id"]})
    return await execute(db, user, rec["_id"])


async def execute(db, user, rec_id) -> dict:
    """Run an approved, allow-listed action exactly once."""
    claimed = await db.ai_recommendations.find_one_and_update({"_id": rec_id, "status": "approved"}, {"$set": {"status": "executing", "updated_at": utcnow()}})
    if claimed is None:
        return await db.ai_recommendations.find_one({"_id": rec_id})
    permission, executor = EXECUTORS[claimed["action"]["type"]]
    try:
        if not has_permission(user, permission):
            raise WorkflowError(403, f"Missing permission '{permission}' at execution time")
        result = await executor(db, user, claimed, claimed["action"]["params"])
        status, extra = "executed", {"execution_result": result, "executed_at": utcnow(), "executed_by": str(user["_id"])}
    except WorkflowError as error:
        status, extra = "execution_failed", {"execution_error": str(error)}
    except Exception as error:  # record, do not retry blindly
        status, extra = "execution_failed", {"execution_error": f"{type(error).__name__}"}
    await db.ai_recommendations.update_one({"_id": rec_id}, {"$set": {"status": status, "updated_at": utcnow(), **extra},
                                                            "$push": {"history": {"status": status, "by": str(user["_id"]), "at": utcnow()}}})
    await record_audit(db, f"recommendation.{status}", actor=user, resource_type="recommendation", resource_id=str(rec_id), project_id=claimed.get("project_id"),
                       outcome="success" if status == "executed" else "error", details=extra.get("execution_result") or {"error": extra.get("execution_error")}, correlation_id=str(rec_id))
    return await db.ai_recommendations.find_one({"_id": rec_id})


async def verify(db, user, rec: dict, effective: bool, note: str) -> dict:
    if rec["status"] not in {"executed", "approved"}:
        raise WorkflowError(409, "Only executed (or approved manual) recommendations can be verified")
    if rec["status"] == "approved" and rec["action"]["type"] != "manual":
        raise WorkflowError(409, "This action has not been executed yet")
    now = utcnow()
    await db.ai_recommendations.update_one({"_id": rec["_id"]}, {"$set": {"status": "verified", "verified_effective": effective, "verification_note": note, "verified_by": str(user["_id"]), "verified_at": now, "updated_at": now},
                                                                "$push": {"history": {"status": "verified", "note": note, "by": str(user["_id"]), "at": now}}})
    await record_audit(db, "recommendation.verified", actor=user, resource_type="recommendation", resource_id=str(rec["_id"]), project_id=rec.get("project_id"), details={"effective": effective}, correlation_id=str(rec["_id"]))
    return await db.ai_recommendations.find_one({"_id": rec["_id"]})

