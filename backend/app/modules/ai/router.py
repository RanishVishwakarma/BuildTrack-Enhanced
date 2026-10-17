"""AI Site Assistant endpoints (Phase 2).

The overview is computed deterministically from authorized records and works
without an API key. Only /assistant/chat calls the language model.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.audit import record_audit
from app.core.config import settings
from app.core.permissions import ensure_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.ai import assistant, llm, local
from app.modules.intelligence import data, materials, risk
from app.modules.intelligence.common import clean, norm_text
from app.modules.intelligence.data import AccessDenied, build_scope

router = APIRouter()


@router.get("/status")
async def ai_status(current_user=Depends(get_current_user)):
    provider = assistant.active_provider()
    ollama = await local.ollama_status() if provider == "ollama" else None
    return {
        # Paid Claude features (report summaries, photo analysis, hub AI help).
        "configured": llm.ai_configured(),
        "model": settings.ai_model if llm.ai_configured() else None,
        # Chat works in every mode except "Claude selected but not enabled".
        "chat_available": provider != "unavailable",
        "chat_engine": assistant.ENGINE_LABELS.get(provider),
        "chat_provider": provider,
        "local_model": {"name": settings.ollama_model, **ollama} if ollama else None,
        "can_query": "ai.query" in current_user.get("_permissions", set()),
        "monitoring_enabled": settings.monitoring_enabled,
        "voice_calls_enabled": bool(settings.voice_calls_enabled),
    }


@router.get("/suggested-questions")
async def suggested_questions(current_user=Depends(get_current_user)):
    return assistant.SUGGESTED_QUESTIONS.get(current_user.get("role"), [])


@router.get("/overview")
async def overview(current_user=Depends(get_current_user), db=Depends(get_database)):
    """What needs attention, computed from records the user may see."""
    ensure_permission(current_user, "ai.query")
    scope = await build_scope(db, current_user)
    result: dict = {"sections": []}

    async def section(key, title, fn):
        try:
            items = await fn()
        except AccessDenied:
            return
        result["sections"].append({"key": key, "title": title, "items": items})

    async def alerts():
        rows = await db.alerts.find({"user_id": str(current_user["_id"]), "status": "open"}).sort("severity_rank", -1).to_list(50)
        return [{"title": a.get("title"), "detail": a.get("message"), "severity": a.get("severity"), "id": str(a["_id"]), "type": "alert", "acknowledged": bool(a.get("acknowledged_at"))} for a in rows]

    async def deadlines():
        info = await data.upcoming_deadlines(db, scope, 7)
        return [{"title": i["title"], "detail": f"{i['project']} · {'overdue by ' + str(i['overdue_days']) + ' day(s)' if i['overdue_days'] else 'due ' + (i['due_date'] or '')[:10]}",
                 "severity": "high" if i["overdue_days"] > 3 else ("medium" if i["overdue_days"] else "low"), "type": i["kind"], "id": i["id"]} for i in info["overdue"] + info["upcoming"]][:40]

    async def shortages():
        info = await materials.material_forecast(db, scope, horizon_days=21)
        rows = [{"title": f"{r['material']} short by {r['projected_shortfall']:g} {r['unit'] or ''}".strip(), "detail": r["shortfall_formula"] + (f" · needed {r['next_required_date'][:10]}" if r["next_required_date"] else ""),
                 "severity": "high", "type": "inventory_item", "id": r["item_id"]} for r in info["shortages"]]
        rows += [{"title": f"{r['material']} at or below reorder level", "detail": f"{r['available']:g} available, reorder at {r['reorder_level']:g}", "severity": "medium", "type": "inventory_item", "id": r["item_id"]}
                 for r in info["low_stock"] if r["projected_shortfall"] <= 0]
        return rows[:40]

    async def procurement():
        info = await data.procurement_status(db, scope)
        rows = [{"title": f"{o['po_number']} delivery {o['days_late']} day(s) late", "detail": f"{o['materials']} · {o['project']}", "severity": "high" if o["days_late"] >= 7 else "medium", "type": "purchase_order", "id": o["id"]} for o in info["overdue_deliveries"]]
        rows += [{"title": f"{r['request_id'] or 'Request'} awaiting approval", "detail": f"{r['material']} × {r['quantity']:g} for {r['project']}", "severity": "low", "type": "material_request", "id": r["id"]} for r in info["pending_approvals"]]
        return rows[:40]

    async def blockers():
        rows = await data.scoped_tasks(db, scope)
        return [{"title": t.get("title"), "detail": scope.project_label(t.get("project_id")), "severity": "medium", "type": "task", "id": str(t["_id"])} for t in rows if norm_text(t.get("status")) == "blocked"][:40]

    async def risks():
        rows = await risk.stored_assessments(db, scope)
        return [{"title": f"{r.get('project_name')}: {r.get('category')} risk ({r.get('level')})", "detail": (r.get("factors") or [""])[0], "severity": r.get("level"), "type": "risk_assessment", "id": str(r["_id"])}
                for r in rows if r.get("level") in {"high", "critical"}][:40]

    await section("alerts", "Critical alerts", alerts)
    await section("deadlines", "Deadlines", deadlines)
    await section("shortages", "Material shortages", shortages)
    await section("procurement", "Procurement delays", procurement)
    await section("blockers", "Unresolved blockers", blockers)
    await section("risks", "High risks", risks)
    return clean(result)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None


@router.post("/assistant/chat")
async def chat(body: ChatRequest, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.query")
    scope = await build_scope(db, current_user)
    return clean(await assistant.chat(db, scope, body.message, body.conversation_id))


@router.get("/conversations")
async def conversations(current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.query")
    rows = await db.ai_conversations.find({"user_id": str(current_user["_id"])}, {"title": 1, "updated_at": 1, "created_at": 1}).sort("updated_at", -1).to_list(100)
    return clean([{"id": r["_id"], "title": r.get("title"), "updated_at": r.get("updated_at")} for r in rows])


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.query")
    return clean(assistant.public_conversation(await assistant.load_conversation(db, current_user, conversation_id)))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.query")
    conversation = await assistant.load_conversation(db, current_user, conversation_id)
    await db.ai_conversations.delete_one({"_id": conversation["_id"], "user_id": str(current_user["_id"])})
    await record_audit(db, "ai.conversation.deleted", actor=current_user, resource_type="ai_conversation", resource_id=conversation_id)
    return {"message": "Conversation deleted"}

