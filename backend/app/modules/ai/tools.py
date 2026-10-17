"""Read-only tools the AI Site Assistant may call.

Each tool wraps an authorized service in app.modules.intelligence and declares
the permission(s) it needs. A user is only offered tools they hold, and every
call is checked again at execution time, so a model that names a tool it was
not offered (or prompt-injected text asking for one) is still refused. Tools
never write, run code or query the database directly.
"""

import json
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.core.audit import record_audit
from app.modules.intelligence import budget, data, impact, materials, risk
from app.modules.intelligence.common import clean
from app.modules.intelligence.data import AccessDenied, Scope

MAX_RESULT_CHARS = 24000


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict
    permissions: tuple[str, ...]
    handler: Callable[..., Awaitable[dict]]
    label: str

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.properties),
                "additionalProperties": False,
            },
        }


NULLABLE_PROJECT = {"type": ["string", "null"], "description": "Project id from get_authorized_projects, or null for all of the user's projects."}


async def _projects(db, scope: Scope) -> dict:
    return {"projects": await data.authorized_projects(db, scope)}


async def _progress(db, scope: Scope, project_id: str) -> dict:
    return await data.project_progress(db, scope, project_id)


async def _assigned_tasks(db, scope: Scope) -> dict:
    rows = await data.scoped_tasks(db, scope)
    if scope.worker_ids:
        # A user with a worker record: only work assigned to them or their trade.
        rows = [t for t in rows if str(t.get("assigned_worker_id") or "") in scope.worker_ids or t.get("assigned_category") in scope.worker_categories]
    return {"tasks": [data.task_row(scope, t) for t in rows if not data.is_done(t.get("status"))]}


async def _project_tasks(db, scope: Scope, project_id: str | None, status: str | None) -> dict:
    rows = [data.task_row(scope, t) for t in await data.scoped_tasks(db, scope, project_id)]
    if status:
        rows = [r for r in rows if data.norm_text(r["status"]) == data.norm_text(status)]
    return {"tasks": rows}


async def _deadlines(db, scope: Scope, days: int, project_id: str | None) -> dict:
    return await data.upcoming_deadlines(db, scope, days, project_id)


async def _inventory(db, scope: Scope) -> dict:
    return {"items": await data.inventory_items(db, scope)}


async def _procurement(db, scope: Scope, project_id: str | None) -> dict:
    return await data.procurement_status(db, scope, project_id)


async def _forecast(db, scope: Scope, project_id: str | None, horizon_days: int) -> dict:
    return await materials.material_forecast(db, scope, project_id, horizon_days)


async def _risks(db, scope: Scope, project_id: str | None) -> dict:
    return await risk.run_risk_assessment(db, scope, project_id, persist=False)


async def _impact(db, scope: Scope, kind: str, record_id: str, delay_days: int) -> dict:
    return await impact.analyze_impact(db, scope, kind=kind, record_id=record_id, delay_days=delay_days)


async def _budget(db, scope: Scope, project_id: str | None) -> dict:
    return await budget.budget_overview(db, scope, project_id)


async def _propose(db, scope: Scope, project_id: str, title: str, rationale: str, instruction: str, priority: str) -> dict:
    """The only write the assistant can make: a *proposal* that a person must
    approve in the Action Center. It cannot execute anything."""
    from app.modules.actions.service import propose

    if not scope.includes_project(project_id):
        raise AccessDenied("That project does not exist or you are not assigned to it.")
    rec = await propose(db, title=title[:200], rationale=rationale[:2000], project_id=project_id, priority=priority,
                        action={"type": "manual", "params": {"instruction": instruction[:2000]}},
                        created_by=str(scope.user["_id"]), source="assistant")
    await record_audit(db, "recommendation.proposed", actor=scope.user, resource_type="recommendation", resource_id=str(rec["_id"]), project_id=project_id, details={"via": "assistant"})
    return {"recommendation_id": str(rec["_id"]), "status": "proposed", "note": "Saved to the Action Center for approval by another authorized person. Nothing has been executed."}


async def _report(db, scope: Scope, report_type: str, project_id: str | None) -> dict:
    from app.modules.intelligence import reports

    return await reports.generate_report(db, scope, report_type, project_id)


TOOLS: list[Tool] = [
    Tool("get_authorized_projects", "List the projects this user may see, with status and dates (and budget when permitted).", {}, ("projects.read.all", "projects.read.assigned"), _projects, "Checking your projects"),
    Tool("get_project_progress", "Planned vs actual progress for one project, with milestones and task counts. States how each number was calculated.",
         {"project_id": {"type": "string", "description": "Project id."}}, ("projects.read.all", "projects.read.assigned"), _progress, "Checking project progress"),
    Tool("get_assigned_tasks", "Open tasks assigned to this user (or, for managers without a worker record, open tasks on their projects).", {}, ("tasks.read.own", "tasks.read.assigned"), _assigned_tasks, "Checking assigned tasks"),
    Tool("get_project_tasks", "Tasks on the user's projects, optionally filtered by status.",
         {"project_id": NULLABLE_PROJECT, "status": {"type": ["string", "null"], "description": "pending, in_progress, blocked, completed, or null for all."}},
         ("tasks.read.assigned",), _project_tasks, "Checking project tasks"),
    Tool("get_upcoming_deadlines", "Overdue and upcoming tasks, milestones and expected deliveries.",
         {"days": {"type": "integer", "description": "Look-ahead window in days (1-90)."}, "project_id": NULLABLE_PROJECT},
         ("tasks.read.own", "tasks.read.assigned", "projects.read.assigned", "projects.read.all"), _deadlines, "Checking deadlines"),
    Tool("get_authorized_inventory", "Current stock levels and items at or below their reorder level.", {}, ("inventory.read.assigned",), _inventory, "Checking inventory"),
    Tool("get_material_forecast", "Physical, reserved, available and incoming stock against approved requirements, with projected shortfalls, consumption and wastage anomalies.",
         {"project_id": NULLABLE_PROJECT, "horizon_days": {"type": "integer", "description": "Requirement window in days (1-180)."}},
         ("inventory.read.assigned",), _forecast, "Forecasting materials"),
    Tool("get_authorized_procurement_status", "Pending approvals, open material requests and purchase orders, overdue deliveries and orders without recent updates.",
         {"project_id": NULLABLE_PROJECT}, ("procurement.read.assigned",), _procurement, "Checking procurement"),
    Tool("get_project_risks", "Rule-based risk assessment per project with contributing factors and source records. No probabilities.",
         {"project_id": NULLABLE_PROJECT}, ("risks.read.assigned",), _risks, "Assessing project risks"),
    Tool("analyze_delay_impact", "What happens if a purchase order or task is delayed: calculated impacts, possible impacts, assumptions and data gaps. Changes nothing.",
         {"kind": {"type": "string", "enum": ["purchase_order", "task"]}, "record_id": {"type": "string", "description": "Id of the purchase order or task."},
          "delay_days": {"type": "integer", "description": "Delay in days (1-365)."}},
         ("tasks.read.assigned", "procurement.read.assigned"), _impact, "Analysing delay impact"),
    Tool("get_budget_summary", "Approved budget, paid, invoiced-unpaid and committed costs, variance, duplicate-invoice, price-change and quantity flags.",
         {"project_id": NULLABLE_PROJECT}, ("budget.forecast.read",), _budget, "Checking budgets"),
    Tool("generate_authorized_report", "Build an operational report from records (not saved).",
         {"report_type": {"type": "string", "enum": ["daily_site", "weekly_project", "inventory", "procurement", "deadlines", "overdue_tasks", "safety_actions", "budget_variance", "management_summary"]},
          "project_id": NULLABLE_PROJECT}, ("reports.generate",), _report, "Building a report"),
    Tool("propose_recommendation", "Save a recommended action to the Action Center for a person to approve. Use only when the user asks you to record a recommendation. It executes nothing.",
         {"project_id": {"type": "string"}, "title": {"type": "string"}, "rationale": {"type": "string", "description": "Facts from tool results that support it."},
          "instruction": {"type": "string", "description": "What the responsible person should do."}, "priority": {"type": "string", "enum": ["low", "medium", "high"]}},
         ("ai.recommendation.review",), _propose, "Saving a recommendation for approval"),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def tools_for(scope: Scope) -> list[Tool]:
    return [tool for tool in TOOLS if scope.can(*tool.permissions)]


def _collect_sources(value, found: list) -> None:
    if isinstance(value, dict):
        if {"type", "id", "label"} <= set(value) and isinstance(value.get("type"), str):
            found.append({"type": value["type"], "id": str(value["id"]), "label": str(value["label"])})
        for item in value.values():
            _collect_sources(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_sources(item, found)


async def execute_tool(db, scope: Scope, name: str, tool_input: dict) -> tuple[str, bool, list[dict]]:
    """Run one tool call. Returns (result_text, is_error, sources)."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return f"Unknown tool '{name}'.", True, []
    if not scope.can(*tool.permissions):
        await record_audit(db, "ai.tool.denied", actor=scope.user, resource_type="ai_tool", resource_id=name, outcome="denied")
        return "This tool is not permitted for the current user. Explain that this information is outside their access.", True, []
    if not isinstance(tool_input, dict) or set(tool_input) - set(tool.properties):
        return "Invalid tool input.", True, []
    args = {key: tool_input.get(key) for key in tool.properties}
    try:
        result = clean(await tool.handler(db, scope, **args))
    except AccessDenied as error:
        return str(error), True, []
    except ValueError as error:
        return f"Invalid input: {error}", True, []
    sources: list[dict] = []
    _collect_sources(result, sources)
    text = json.dumps(result, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + '... [truncated: ask about a single project for full detail]'
    return text, False, sources
