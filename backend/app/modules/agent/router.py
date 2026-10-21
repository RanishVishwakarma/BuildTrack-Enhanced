"""Agent mode API (prefix /ai/agent).

POST /chat streams newline-delimited JSON: one {"type": "step"} event per
agent action as it happens, then {"type": "final"} (or {"type": "error"}).
Runs only on the local Ollama model; it never calls Claude.
"""

import asyncio
import json
import logging
from typing import Optional

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.audit import record_audit
from app.core.config import settings
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.agent import graph
from app.modules.agent.agents import SPECIALISTS, available_specialists, available_tools
from app.modules.agent.knowledge import KnowledgeStore
from app.modules.agent.llm import AgentModelUnavailable, OllamaAgentLLM, model_name
from app.modules.ai.assistant import check_rate_limit
from app.modules.intelligence.common import clean, utcnow
from app.modules.intelligence.data import build_scope

logger = logging.getLogger(__name__)
router = APIRouter()

_store: KnowledgeStore | None = None
_llm = None


def get_store() -> KnowledgeStore:
    global _store
    if _store is None:
        _store = KnowledgeStore()
    return _store


def get_llm():
    return _llm or OllamaAgentLLM()


def set_test_overrides(store=None, llm=None) -> None:
    """Tests install an in-memory store and a scripted model."""
    global _store, _llm
    _store, _llm = store, llm


async def model_status() -> dict:
    if _llm is not None:
        return {"reachable": True, "model_available": True}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            tags = (await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")).json()
    except Exception:
        return {"reachable": False, "model_available": False}
    names = {m.get("name") for m in tags.get("models", [])}
    model = model_name()
    return {"reachable": True, "model_available": model in names or f"{model}:latest" in names}


@router.get("/status")
async def agent_status(current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "ai.agent.use")
    scope = await build_scope(db, current_user)
    store = await asyncio.to_thread(get_store)
    return {
        "model": getattr(_llm, "name", None) or model_name(),
        **(await model_status()),
        **store.stats(),
        "embed_model": settings.agent_embed_model,
        "can_index": has_permission(current_user, "reports.generate"),
        "specialists": [
            {"name": name, "label": SPECIALISTS[name].label, "tools": available_tools(SPECIALISTS[name], scope)}
            for name in available_specialists(scope)
        ],
        "graph": graph.mermaid(),
    }


@router.post("/index")
async def index_records(current_user=Depends(get_current_user), db=Depends(get_database)):
    """Rebuild the search index from site records."""
    ensure_permission(current_user, "ai.agent.use")
    ensure_permission(current_user, "reports.generate")
    store = await asyncio.to_thread(get_store)
    counts = await store.index_records(db)
    await record_audit(db, "ai.agent.indexed", actor=current_user, resource_type="agent_index", details=counts)
    return {"indexed": counts, **store.stats()}


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


@router.post("/chat")
async def agent_chat(body: AgentChatRequest, current_user=Depends(get_current_user), db=Depends(get_database)):
    # Agent mode is role-based: ai.agent.use (admin, project manager and site
    # engineer by default; grant or revoke per user in Settings -> Access).
    ensure_permission(current_user, "ai.agent.use")
    await check_rate_limit(db, current_user)
    model = await model_status()
    if not model["reachable"]:
        raise HTTPException(status_code=503, detail="Agent mode needs Ollama running on this computer. Start Ollama and try again.")
    if not model["model_available"]:
        raise HTTPException(status_code=503, detail=f'The model "{model_name()}" is not downloaded. Run: ollama pull {model_name()}')

    scope = await build_scope(db, current_user)
    if not available_specialists(scope):
        raise HTTPException(status_code=403, detail="Your role has no data the agents can work with.")
    user_id = str(current_user["_id"])
    conversation_id = body.conversation_id if body.conversation_id and ObjectId.is_valid(body.conversation_id) else str(ObjectId())
    earlier = await db.ai_agent_runs.find({"user_id": user_id, "conversation_id": conversation_id}).sort("created_at", -1).to_list(3)
    history = [turn for run in reversed(earlier) for turn in ({"role": "user", "text": run["question"]}, {"role": "assistant", "text": run.get("answer") or ""})]
    run_id = str(ObjectId())
    await db.ai_usage.insert_one({"user_id": user_id, "at": utcnow(), "kind": "agent", "model": model_name()})

    async def events():
        store = await asyncio.to_thread(get_store)
        if store.stats()["chunks"] == 0:
            yield json.dumps({"type": "step", "step": {"type": "index", "label": "Building the search index for the first time"}}) + "\n"
            await store.index_records(db)
        final = None
        try:
            async for event in graph.run(body.message.strip(), db=db, scope=scope, llm=get_llm(), store=store, run_id=run_id, history=history):
                if event["type"] == "final":
                    final = event
                yield json.dumps(clean(event), default=str) + "\n"
        except AgentModelUnavailable as error:
            yield json.dumps({"type": "error", "message": str(error)}) + "\n"
            return
        except Exception:  # never leave the stream hanging
            logger.exception("Agent run failed")
            yield json.dumps({"type": "error", "message": "The agent run failed. Try again or ask a narrower question."}) + "\n"
            return
        await db.ai_agent_runs.insert_one({
            "_id": ObjectId(run_id), "user_id": user_id, "conversation_id": conversation_id, "question": body.message.strip(),
            "answer": final["answer"], "verified": final["verified"], "route": final["route"], "tools": final["tools"],
            "steps": final["steps"], "model": model_name(), "created_at": utcnow(),
        })
        await record_audit(db, "ai.agent.run", actor=current_user, resource_type="agent_run", resource_id=run_id,
                           details={"route": final["route"], "tools": [t["tool"] for t in final["tools"]], "verified": final["verified"]})
        yield json.dumps({"type": "saved", "conversation_id": conversation_id, "run_id": run_id}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
