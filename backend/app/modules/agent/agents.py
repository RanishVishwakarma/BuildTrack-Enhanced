"""Specialist agents and the tools each may use.

The tools are the Site Assistant's read-only tools (app/modules/ai/tools.py),
which check the user's permissions on every call, plus `search_site_records`
(RAG over the knowledge store). A specialist sees only its own tools, and
only those the user holds. Tool calls the model writes are validated against
the tool's JSON schema before anything runs.
"""

from dataclasses import dataclass, field

from app.modules.ai.tools import TOOLS_BY_NAME
from app.modules.intelligence.data import Scope

SEARCH_TOOL = "search_site_records"
SEARCH_SPEC = {
    "description": "Search safety reports, improvement suggestions, saved reports and project descriptions by meaning. Use for 'what did the report say', incidents, past issues.",
    "properties": {"query": {"type": "string", "description": "What to look for, in plain words."}},
}
SITE_KINDS = ["safety_report", "suggestion", "report", "project"]


@dataclass(frozen=True)
class Specialist:
    name: str
    label: str
    role: str
    tools: tuple[str, ...]
    # Called when the model finishes without using any tool, so every answer
    # is grounded in records rather than the model's guesses.
    default_call: tuple[str, dict]
    keywords: tuple[str, ...] = field(default=())


SPECIALISTS: dict[str, Specialist] = {
    "procurement": Specialist(
        "procurement", "Procurement agent",
        "You handle materials, stock, purchase orders, vendors, deliveries and costs.",
        ("get_authorized_procurement_status", "get_authorized_inventory", "get_material_forecast", "get_budget_summary",
         "analyze_delay_impact", "propose_recommendation", SEARCH_TOOL),
        ("get_authorized_procurement_status", {"project_id": None}),
        ("material", "stock", "cement", "steel", "sand", "order", "po", "purchase", "vendor", "supplier", "deliver",
         "invoice", "budget", "cost", "spend", "inventory", "shortage", "price"),
    ),
    "schedule": Specialist(
        "schedule", "Schedule agent",
        "You handle projects, progress, tasks, milestones, deadlines, delays and their impact.",
        ("get_authorized_projects", "get_project_progress", "get_project_tasks", "get_assigned_tasks", "get_upcoming_deadlines",
         "get_project_risks", "analyze_delay_impact", "propose_recommendation", SEARCH_TOOL),
        ("get_upcoming_deadlines", {"days": 14, "project_id": None}),
        ("delay", "late", "deadline", "due", "schedule", "progress", "task", "milestone", "overdue", "behind", "plan",
         "project", "finish", "complete", "risk", "today", "week"),
    ),
    "safety": Specialist(
        "safety", "Safety agent",
        "You handle site safety: incidents, hazards, safety reports, corrective actions and site risks.",
        ("get_project_risks", "generate_authorized_report", SEARCH_TOOL),
        (SEARCH_TOOL, {"query": "recent safety incidents and hazards"}),
        ("safety", "incident", "accident", "injury", "hazard", "ppe", "helmet", "unsafe", "near miss", "fire", "fall",
         "corrective", "report", "said", "suggestion"),
    ),
}


def tool_spec(name: str) -> dict:
    if name == SEARCH_TOOL:
        return SEARCH_SPEC
    tool = TOOLS_BY_NAME[name]
    return {"description": tool.description, "properties": tool.properties}


def available_tools(specialist: Specialist, scope: Scope) -> list[str]:
    allowed = []
    for name in specialist.tools:
        if name == SEARCH_TOOL:
            allowed.append(name)
        elif scope.can(*TOOLS_BY_NAME[name].permissions):
            allowed.append(name)
    return allowed


def available_specialists(scope: Scope) -> list[str]:
    """Specialists with at least one tool besides search for this user: a
    role without safety, procurement or schedule data never gets that agent."""
    return [s.name for s in SPECIALISTS.values() if [t for t in available_tools(s, scope) if t != SEARCH_TOOL]]


def keyword_route(question: str, allowed: list[str]) -> list[str]:
    """Fallback router when the model's routing reply is unusable."""
    text = question.lower()
    scored = [(sum(word in text for word in SPECIALISTS[n].keywords), n) for n in allowed]
    picked = [n for score, n in sorted(scored, reverse=True) if score > 0][:2]
    return picked or ([n for n in ("schedule", "procurement") if n in allowed][:1] or allowed[:1])


def _check_type(value, spec: dict) -> bool:
    kinds = spec.get("type")
    kinds = kinds if isinstance(kinds, list) else [kinds]
    checks = {"string": lambda v: isinstance(v, str), "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
              "null": lambda v: v is None, "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
    return any(checks.get(kind, lambda v: True)(value) for kind in kinds)


def validate_call(name: str, raw_input, allowed: list[str]) -> tuple[dict | None, str | None]:
    """Clean a model-written tool call. Returns (input, error)."""
    if name not in allowed:
        return None, f"'{name}' is not one of your tools: {', '.join(allowed)}."
    props = tool_spec(name)["properties"]
    raw_input = raw_input if isinstance(raw_input, dict) else {}
    unknown = set(raw_input) - set(props)
    if unknown:
        return None, f"Unknown input field(s) for {name}: {', '.join(sorted(unknown))}."
    clean = {}
    for key, spec in props.items():
        value = raw_input.get(key)
        if value in ("", "null", "None"):
            value = None
        if isinstance(value, str) and "integer" in str(spec.get("type")) and value.strip().isdigit():
            value = int(value)
        if value is None and "null" not in str(spec.get("type")):
            if spec.get("type") == "integer":
                value = 14 if key in {"days", "horizon_days"} else None
            if value is None:
                return None, f"{name} needs '{key}' ({spec.get('description') or spec.get('type')})."
        if not _check_type(value, spec):
            return None, f"'{key}' for {name} must be {spec.get('type')}."
        if "enum" in spec and value not in spec["enum"]:
            return None, f"'{key}' must be one of {spec['enum']}."
        clean[key] = value
    return clean, None
