"""Free, offline "quick answers" for the Site Assistant (no AI model).

A question is matched to one or more topics by keywords; each topic reads
data through the same authorized services the AI tools use (so permissions and
project scoping are identical) and is written up by fixed templates. Every
number in an answer comes straight from the records. The same `gather` step
also feeds the local-model mode (app.modules.ai.local), which only rephrases.
"""

import re
from dataclasses import dataclass, field

from app.core.audit import record_audit
from app.modules.ai.tools import _collect_sources
from app.modules.intelligence import budget, data, impact, materials, risk
from app.modules.intelligence.common import clean, norm_text, parse_dt
from app.modules.intelligence.data import AccessDenied, Scope


def _date(value) -> str:
    parsed = parse_dt(value)
    return parsed.strftime("%d %b %Y") if parsed else "no date"


def _num(value) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.2f}".rstrip("0").rstrip(".")


@dataclass
class Topic:
    key: str
    label: str
    pattern: str
    permissions: tuple[str, ...]


TOPICS = [
    Topic("impact", "Analysing delay impact", r"\b(delay(ed)?|late|slip)\b.*\b\d+\s*days?\b|\bwhat (happens|if)\b", ("tasks.read.assigned", "procurement.read.assigned")),
    Topic("budget", "Checking budgets", r"\b(budget|cost|spend|spent|invoice|payment|over ?budget|money|expense)", ("budget.forecast.read",)),
    Topic("risks", "Assessing project risks", r"\b(risk|risky|danger|threat|at risk)", ("risks.read.assigned",)),
    Topic("materials", "Forecasting materials", r"\b(short|shortage|run(ning)? out|stock|material|inventory|cement|steel|sand|brick|rebar|aggregate)", ("inventory.read.assigned",)),
    Topic("procurement", "Checking procurement", r"\b(deliver|delivery|deliveries|purchase order|\bpo\b|po-|vendor|supplier|order|approval|procure)", ("procurement.read.assigned",)),
    Topic("my_tasks", "Checking assigned tasks", r"\b(my tasks?|assigned to me|my work|what should i (do|work)|my jobs?)\b", ("tasks.read.own", "tasks.read.assigned")),
    Topic("overdue", "Checking overdue work", r"\b(overdue|late|behind|missed|delayed)\b", ("tasks.read.own", "tasks.read.assigned", "projects.read.assigned", "projects.read.all")),
    Topic("deadlines", "Checking deadlines", r"\b(deadline|due|upcoming|this week|next week|milestone|schedule|coming up)", ("tasks.read.own", "tasks.read.assigned", "projects.read.assigned", "projects.read.all")),
    Topic("progress", "Checking project progress", r"\b(progress|status|how is|how's|percent|complete|completion|on track)", ("projects.read.assigned", "projects.read.all")),
    Topic("attention", "Checking what needs attention", r"\b(attention|today|summary|summari[sz]e|overview|update|happening|priorit|focus|issues?|problems?)\b", ()),
]
HELP_PATTERN = r"^\s*(help|hi|hello|hey|what can you do|what do you do)\b"


@dataclass
class Gathered:
    topics: list[str] = field(default_factory=list)
    sections: list[tuple[str, list[str]]] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


def match_topics(question: str) -> list[Topic]:
    text = question.lower()
    matched = [t for t in TOPICS if re.search(t.pattern, text)]
    keys = {t.key for t in matched}
    if "overdue" in keys and "deadlines" in keys:
        matched = [t for t in matched if t.key != "deadlines"]
    return matched[:3]


def _projects_named(scope: Scope, question: str) -> list[dict]:
    text = norm_text(question)
    return [p for p in scope.projects if p.get("name") and norm_text(p["name"]) in text]


async def _topic(db, scope: Scope, topic: str, question: str, out: Gathered) -> None:
    named = _projects_named(scope, question)
    pid = str(named[0]["_id"]) if len(named) == 1 else None

    if topic in {"deadlines", "overdue", "attention"}:
        info = await data.upcoming_deadlines(db, scope, 14 if topic == "deadlines" else 7, pid)
        out.data.setdefault("deadlines", info)
        lines = [f"{i['title']} ({i['project']}) is {i['overdue_days']} day(s) overdue." for i in info["overdue"][:8]]
        if topic != "overdue":
            lines += [f"{i['title']} ({i['project']}) is due {_date(i['due_date'])}." for i in info["upcoming"][:8]]
        title = "Overdue work" if topic == "overdue" else "Deadlines"
        out.sections.append((title, lines or ["Nothing overdue or due soon in your projects."]))

    if topic in {"materials", "attention"} and scope.can("inventory.read.assigned"):
        info = await materials.material_forecast(db, scope, pid, 30)
        out.data.setdefault("materials", {"shortages": info["shortages"], "low_stock": info["low_stock"]})
        lines = [f"{r['material']}: short by {_num(r['projected_shortfall'])} {r['unit'] or ''} ({r['shortfall_formula']}), needed {_date(r['next_required_date'])}." for r in info["shortages"][:8]]
        if topic == "materials":
            lines += [f"{r['material']} is at or below its reorder level ({_num(r['available'])} available)." for r in info["low_stock"] if r["projected_shortfall"] <= 0][:6]
        out.sections.append(("Materials", lines or ["No projected shortages in the next 30 days."]))

    if topic in {"procurement", "attention"} and scope.can("procurement.read.assigned"):
        info = await data.procurement_status(db, scope, pid)
        out.data.setdefault("procurement", {k: info[k] for k in ("pending_approvals", "overdue_deliveries", "orders_without_recent_update")})
        lines = [f"{o['po_number']} ({o['materials']}) delivery is {o['days_late']} day(s) late." for o in info["overdue_deliveries"][:8]]
        lines += [f"Request {r['request_id']} for {_num(r['quantity'])} {r['unit'] or ''} {r['material']} is awaiting approval." for r in info["pending_approvals"][:6]]
        if topic == "procurement":
            lines += [f"{o['po_number']} has had no update for {o['days_since_update']} day(s)." for o in info["orders_without_recent_update"][:5]]
            lines.append(f"Open purchase orders: {len(info['open_purchase_orders'])}.")
        out.sections.append(("Procurement", lines or ["No late deliveries or pending approvals."]))

    if topic in {"risks", "attention"} and scope.can("risks.read.assigned"):
        info = await risk.run_risk_assessment(db, scope, pid, persist=False)
        out.data.setdefault("risks", info["projects"])
        lines = []
        for project in info["projects"]:
            for finding in project["findings"]:
                if topic == "risks" or finding["level"] in {"high", "critical"}:
                    lines.append(f"{project['project']}: {finding['level']} {finding['category']} risk. {finding['factors'][0]}")
        out.sections.append(("Risks", lines[:10] or ["No rule-based risks are currently triggered."]))

    if topic == "my_tasks":
        rows = await data.scoped_tasks(db, scope, pid)
        if scope.worker_ids:
            rows = [t for t in rows if str(t.get("assigned_worker_id") or "") in scope.worker_ids or t.get("assigned_category") in scope.worker_categories]
        rows = [data.task_row(scope, t) for t in rows if not data.is_done(t.get("status"))]
        out.data["my_tasks"] = rows
        out.sections.append(("Your open tasks", [f"{r['title']} ({r['project']}): {r['status']}, due {_date(r['due_date'])}." for r in rows[:12]] or ["You have no open tasks."]))

    if topic == "progress":
        projects = named or scope.projects[:5]
        lines, rows = [], []
        for project in projects:
            info = await data.project_progress(db, scope, str(project["_id"]))
            rows.append(info)
            actual = f"{info['actual_progress_percent']}% done ({info['actual_basis']})" if info["actual_progress_percent"] is not None else "no measured progress yet (no milestones or tasks)"
            planned = f", planned {info['planned_progress_percent']}% by now" if info["planned_progress_percent"] is not None else ""
            lines.append(f"{project.get('name')}: {actual}{planned}.")
        out.data["progress"] = rows
        out.sections.append(("Progress", lines or ["No projects in your scope."]))

    if topic == "budget":
        info = await budget.budget_overview(db, scope, pid)
        out.data["budget"] = info["projects"]
        lines = [f"{p['project']}: known cost Rs {_num(p['known_cost'])} of Rs {_num(p['approved_budget'])} budget ({p['known_cost_percent_of_budget']}%)." if p["approved_budget"] else f"{p['project']}: known cost Rs {_num(p['known_cost'])} (no budget recorded)." for p in info["projects"]]
        lines += [f"Check: {f['reason']}" for f in info["duplicate_invoice_flags"][:3]]
        lines += [f"Check: {f['po_number']} price {f['change_percent']}% vs other orders." for f in info["price_change_flags"][:3]]
        out.sections.append(("Budget", lines or ["No budget data."]))

    if topic == "impact":
        days = re.search(r"(\d+)\s*days?", question)
        po = re.search(r"\bpo-?\s*(\d+)\b", question.lower())
        record = None
        if po and scope.can("procurement.read.assigned"):
            number = po.group(1)
            for order in await db.purchase_orders.find({"po_number": {"$regex": f"{number}$", "$options": "i"}}).to_list(5):
                if scope.includes_project(order.get("project_id"), order.get("project")):
                    record = ("purchase_order", order)
                    break
        if record is None and scope.can("procurement.read.assigned"):
            text = norm_text(question)
            for order in await db.purchase_orders.find({"status": {"$in": ["created", "sent", "accepted", "processing", "shipped"]}}).to_list(500):
                if order.get("materials") and norm_text(order["materials"]) in text and scope.includes_project(order.get("project_id"), order.get("project")):
                    record = ("purchase_order", order)
                    break
        if record is None or not days:
            out.sections.append(("Delay impact", ["Name the purchase order (e.g. PO-00012) or its material, and the number of days, e.g. \"What if the steel delivery is 3 days late?\". You can also use Insights > Delay impact."]))
        else:
            kind, doc = record
            info = await impact.analyze_impact(db, scope, kind=kind, record_id=str(doc["_id"]), delay_days=int(days.group(1)))
            out.data["impact"] = info
            lines = [f"{c['label']}: {c['effect']}" for c in info["calculated_impacts"][:8]] or ["No calculated impacts from the recorded links."]
            lines += [f"Possibly affected: {c['label']}. {c['effect']}" for c in info["possible_impacts"][:4]]
            lines += [f"Data gap: {g}" for g in info["data_gaps"]]
            out.sections.append((f"If {doc.get('po_number')} is {days.group(1)} day(s) late", lines))


async def gather(db, scope: Scope, question: str) -> Gathered:
    out = Gathered()
    if re.search(HELP_PATTERN, question.lower()) and len(question) < 40:
        out.topics = ["help"]
        return out
    topics = match_topics(question) or [t for t in TOPICS if t.key == "attention"]
    for topic in topics:
        if topic.permissions and not scope.can(*topic.permissions):
            out.denied.append(topic.label)
            await record_audit(db, "ai.tool.denied", actor=scope.user, resource_type="ai_topic", resource_id=topic.key, outcome="denied")
            continue
        try:
            await _topic(db, scope, topic.key, question, out)
            out.tools.append({"name": topic.key, "label": topic.label, "ok": True})
            out.topics.append(topic.key)
        except AccessDenied:
            out.denied.append(topic.label)
    return out


HELP_TEXT = (
    "I answer from your project records. Try:\n"
    "- What needs attention today?\n- Which tasks are overdue?\n- Are any materials running short?\n"
    "- Which deliveries are late?\n- How is <project name> progressing?\n- What are the project risks?\n"
    "- What if PO-00012 is 3 days late?"
)


def write_answer(gathered: Gathered) -> str:
    if gathered.topics == ["help"]:
        return HELP_TEXT
    parts = []
    for title, lines in gathered.sections:
        parts.append(f"{title}:\n" + "\n".join(f"- {line}" for line in lines))
    if gathered.denied:
        parts.append("Outside your access: " + ", ".join(gathered.denied).lower() + ".")
    if not parts:
        parts.append("I could not find anything for that. " + HELP_TEXT)
    return "\n\n".join(parts)


async def answer(db, scope: Scope, question: str) -> dict:
    gathered = await gather(db, scope, question)
    sources: list[dict] = []
    _collect_sources(clean(gathered.data), sources)
    tools = gathered.tools + [{"name": label, "label": label, "ok": False} for label in gathered.denied]
    return {"answer": write_answer(gathered), "tools": tools, "sources": sources, "gathered": gathered}
