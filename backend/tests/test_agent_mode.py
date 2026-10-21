"""Agent mode: LangGraph supervisor + specialists + RAG + reflection.

No model is called: a scripted stand-in plays Gemma's part, so these tests
are free and deterministic. They check the orchestration, the guard rails
(tool validation, permissions, retrieval filtering) and the verifier.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import anyio
import chromadb
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.security import create_access_token, hash_password
from app.db.mongodb import get_database
from app.main import app
from app.modules.agent import router as agent_router
from app.modules.agent.agents import keyword_route, validate_call
from app.modules.agent.knowledge import HashingEmbeddings, KnowledgeStore
from app.modules.agent.verify import unsupported_numbers
from app.modules.intelligence.data import Scope

API = "/api/v1/ai/agent"
IDS = {k: ObjectId() for k in ("pm", "worker", "engineer", "contractor", "client", "vendor", "pm_revoked", "project", "other_project", "safety_a", "safety_b")}
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def new_store() -> KnowledgeStore:
    return KnowledgeStore(client=chromadb.EphemeralClient(), embeddings=HashingEmbeddings(), name=f"test-{uuid.uuid4().hex[:10]}")


def scope_for(user_id: str, permissions: set[str], project_ids):
    return Scope(user={"_id": user_id, "_permissions": permissions}, project_ids=project_ids)


# ------------------------------------------------------------------ unit
def test_verifier_flags_invented_figures():
    evidence = ['{"po_number": "PO-0007", "quantity": 100, "received": 60, "unit_price": 380.0, "due": "2026-10-18"}']
    assert unsupported_numbers("PO-0007: 60 of 100 bags received at Rs 380, due 18 Oct.", evidence) == []
    assert unsupported_numbers("PO-0007 is 4 days late and costs Rs 45,000.", evidence) == ["4", "45000"]
    assert unsupported_numbers("About 67% done.", ['{"progress": 66.67}']) == []


def test_tool_calls_are_validated_before_running():
    allowed = ["get_upcoming_deadlines", "search_site_records"]
    assert validate_call("delete_project", {}, allowed)[1].startswith("'delete_project' is not one of your tools")
    assert validate_call("get_upcoming_deadlines", {"days": "14", "project_id": None}, allowed) == ({"days": 14, "project_id": None}, None)
    assert "Unknown input" in validate_call("get_upcoming_deadlines", {"days": 7, "sql": "drop"}, allowed)[1]
    assert validate_call("search_site_records", {}, allowed)[1].startswith("search_site_records needs 'query'")


def test_keyword_routing_fallback():
    allowed = ["procurement", "schedule", "safety"]
    assert keyword_route("Is the cement purchase order late?", allowed)[0] == "procurement"
    assert keyword_route("Any fall hazard incidents this week?", allowed)[0] == "safety"


def test_retrieval_is_filtered_by_permission_project_and_owner():
    store = new_store()

    async def seed(db):
        await db.safety_reports.insert_many([
            {"_id": IDS["safety_a"], "title": "Scaffold plank loose", "description": "Loose scaffold plank on level 3 near the lift shaft.",
             "severity": "high", "status": "open", "project_id": str(IDS["project"]), "anonymous": True, "reporter_id": "secret-person"},
            {"_id": IDS["safety_b"], "title": "Scaffold missing toe board", "description": "Scaffold toe board missing at the east block.",
             "severity": "medium", "status": "open", "project_id": str(IDS["other_project"])},
        ])

    db = AsyncMongoMockClient()["agent_rag_test"]
    anyio.run(seed, db)
    anyio.run(store.index_records, db)
    store.remember("u1", "What is open on scaffolds?", "One scaffold issue is open.", "run-1")

    engineer = scope_for("u1", {"safety_reports.read.assigned"}, {str(IDS["project"])})
    hits = store.search(engineer, "scaffold problems", k=5)
    labels = {h.label for h in hits}
    assert "Scaffold plank loose" in labels and "Scaffold missing toe board" not in labels  # other project
    assert all("secret-person" not in h.text for h in hits)  # anonymous reporter never indexed
    assert [h.label for h in store.recall(engineer, "open scaffold issues")] == ["What is open on scaffolds?"]

    stranger = scope_for("u2", {"ai.query"}, {str(IDS["project"])})  # no safety permission, no memory of u1
    assert store.search(stranger, "scaffold problems", k=5) == []


# ------------------------------------------------------------------ graph via the API
class ScriptedGemma:
    """Plays the model: routes, misuses a tool once, then behaves; invents a
    figure in the first draft so the verifier has to send it back."""

    name = "scripted-gemma"

    def __init__(self):
        self.prompts = []

    async def json(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        if "supervisor" in prompt:
            return {"agents": ["procurement", "schedule"], "reason": "Cement order and its effect on the schedule."}
        if "Procurement agent" in prompt:
            if "Results so far" not in prompt:
                return {"thought": "Check open orders.", "action": "get_authorized_procurement_status", "input": {"project_id": None}}
            return {"thought": "Enough.", "action": "finish", "note": "Procurement status checked."}
        if "Schedule agent" in prompt:
            if "Results so far" not in prompt:
                return {"thought": "Try deleting.", "action": "delete_project", "input": {}}
            if "Result of" not in prompt:
                return {"thought": "Check deadlines.", "action": "get_upcoming_deadlines", "input": {"days": "14", "project_id": None}}
            return {"thought": "Enough.", "action": "finish", "note": "Deadlines checked."}
        return {"action": "finish"}

    async def text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "NOT in the evidence" in prompt:
            return "The 40 bag cement order needs follow-up with the vendor. The procurement manager should chase it today."
        return "The 40 bag cement order is 999 days late."


async def seed_api(db):
    await db.users.insert_many([
        {"_id": IDS["pm"], "email": "pm@agent-tests.io", "full_name": "PM", "role": "project_manager", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["worker"], "email": "w@agent-tests.io", "full_name": "W", "role": "worker", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["engineer"], "email": "se@agent-tests.io", "full_name": "SE", "role": "site_engineer", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["contractor"], "email": "c@agent-tests.io", "full_name": "C", "role": "contractor", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["vendor"], "email": "v@agent-tests.io", "full_name": "V", "role": "vendor", "status": "active", "vendor_id": "v1", "password_hash": hash_password("x")},
        {"_id": IDS["client"], "email": "cl@agent-tests.io", "full_name": "CL", "role": "client", "status": "active", "password_hash": hash_password("x")},
        {"_id": IDS["pm_revoked"], "email": "pm2@agent-tests.io", "full_name": "PM2", "role": "project_manager", "status": "active",
         "revoked_permissions": ["ai.agent.use"], "password_hash": hash_password("x")},
    ])
    await db.projects.insert_one({"_id": IDS["project"], "name": "Tower A", "status": "active", "description": "12 floor residential tower",
                                  "start_date": NOW - timedelta(days=60), "end_date": NOW + timedelta(days=120)})
    await db.user_project_access.insert_one({"user_id": str(IDS["pm"]), "project_id": str(IDS["project"]), "active": True})


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["agent_api_test"]

    async def override_db():
        yield db

    app.dependency_overrides[get_database] = override_db
    anyio.run(seed_api, db)
    model = ScriptedGemma()
    agent_router.set_test_overrides(store=new_store(), llm=model)
    with TestClient(app) as client:
        yield client, db, model
    agent_router.set_test_overrides()
    app.dependency_overrides.clear()


def auth(who):
    return {"Authorization": f"Bearer {create_access_token(str(IDS[who]))}"}


def stream(client, who, message):
    response = client.post(f"{API}/chat", json={"message": message}, headers=auth(who))
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_agent_run_routes_uses_tools_and_reflects(env):
    client, db, model = env
    events = stream(client, "pm", "Will the 40 bag cement order delay Tower A?")
    steps = [e["step"] for e in events if e["type"] == "step"]
    final = next(e for e in events if e["type"] == "final")

    route = next(s for s in steps if s["type"] == "route")
    assert route["agents"] == ["Procurement agent", "Schedule agent"] and not route["fallback"]
    tools = {(s["agent"], s["tool"]) for s in steps if s["type"] == "tool"}
    assert ("Procurement agent", "get_authorized_procurement_status") in tools and ("Schedule agent", "get_upcoming_deadlines") in tools
    assert any(s["type"] == "error" and "delete_project" in s["message"] for s in steps)  # rejected, never run
    checks = [s for s in steps if s["type"] == "check"]
    assert checks[0] == {"type": "check", "ok": False, "missing": ["999"], "retry": True} and checks[-1]["ok"] is True

    assert final["verified"] and "999" not in final["answer"] and final["route"] == ["procurement", "schedule"]
    run = anyio.run(db.ai_agent_runs.find_one, {"user_id": str(IDS["pm"])})
    assert run["verified"] and run["model"]
    assert events[-1]["type"] == "saved"
    # The verified answer is now long-term memory for this user.
    assert any("memory" == s["type"] for s in [e["step"] for e in stream(client, "pm", "Will the 40 bag cement order delay Tower A?") if e["type"] == "step"])


@pytest.mark.parametrize("who", ["worker", "contractor", "client", "vendor", "pm_revoked"])
def test_agent_mode_is_limited_to_permitted_roles(env, who):
    client, _, model = env
    assert client.get(f"{API}/status", headers=auth(who)).status_code == 403
    response = client.post(f"{API}/chat", json={"message": "Is the cement late?"}, headers=auth(who))
    assert response.status_code == 403 and model.prompts == []  # refused before the model is called
    assert client.post(f"{API}/index", headers=auth(who)).status_code == 403


def test_permitted_roles_get_only_their_agents(env):
    client, _, _ = env
    pm = client.get(f"{API}/status", headers=auth("pm")).json()
    assert {s["name"] for s in pm["specialists"]} == {"procurement", "schedule", "safety"}
    assert pm["model"] == "scripted-gemma" and pm["embedder"] == "hashing-512" and "supervisor" in pm["graph"]
    engineer = client.get(f"{API}/status", headers=auth("engineer")).json()
    tools = {s["name"]: set(s["tools"]) for s in engineer["specialists"]}
    # A site engineer has no budget or recommendation-approval rights, so those tools are not offered.
    assert "get_budget_summary" not in tools.get("procurement", set())
    assert client.post(f"{API}/index", headers=auth("engineer")).status_code == 403  # rebuilding needs reports.generate


def test_unavailable_model_is_a_clear_503(env, monkeypatch):
    client, _, _ = env

    async def down():
        return {"reachable": False, "model_available": False}

    monkeypatch.setattr(agent_router, "model_status", down)
    response = client.post(f"{API}/chat", json={"message": "hello"}, headers=auth("pm"))
    assert response.status_code == 503 and "Ollama" in response.json()["detail"]
