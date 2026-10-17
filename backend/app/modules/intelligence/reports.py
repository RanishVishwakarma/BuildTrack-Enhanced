"""Operational report generator.

Reports are assembled from authorized records only. Each report states its
period, scope, data freshness, the records it drew on and its limitations.
An optional AI narrative is stored separately and labelled as AI-written; the
figures always come from here.
"""

from datetime import timedelta

from app.modules.intelligence import budget, data, materials, risk
from app.modules.intelligence.common import is_done, iso, norm_text, parse_dt, utcnow
from app.modules.intelligence.data import AccessDenied, Scope

REPORT_TYPES = {
    "daily_site": ("Daily site report", ("tasks.read.assigned",), True, 1),
    "weekly_project": ("Weekly project report", ("tasks.read.assigned",), True, 7),
    "inventory": ("Inventory report", ("inventory.read.assigned",), False, 30),
    "procurement": ("Procurement report", ("procurement.read.assigned",), False, 30),
    "deadlines": ("Upcoming deadline report", ("tasks.read.assigned",), False, 14),
    "overdue_tasks": ("Overdue task report", ("tasks.read.assigned",), False, 0),
    "safety_actions": ("Safety action report", ("safety_reports.read.assigned",), False, 30),
    "budget_variance": ("Budget variance report", ("budget.forecast.read",), False, 0),
    "management_summary": ("Management summary", ("risks.read.assigned",), False, 7),
}


def _metric(label, value, note=None):
    return {"label": label, "value": value, **({"note": note} if note else {})}


async def _latest(db, collection: str):
    row = await db[collection].find({}, {"updated_at": 1, "created_at": 1}).sort("updated_at", -1).limit(1).to_list(1)
    return iso(row[0].get("updated_at") or row[0].get("created_at")) if row else None


def _in_period(value, start, end) -> bool:
    when = parse_dt(value)
    return bool(when and start <= when <= end)


async def generate_report(db, scope: Scope, report_type: str, project_id: str | None = None, days: int | None = None) -> dict:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unknown report type '{report_type}'")
    title, needs, needs_project, default_days = REPORT_TYPES[report_type]
    scope.require("reports.generate")
    scope.require(*needs)
    project = None
    if project_id:
        project = next((p for p in scope.projects if str(p["_id"]) == str(project_id)), None)
        if project is None:
            raise AccessDenied("That project does not exist or you are not assigned to it.")
    elif needs_project:
        raise ValueError("This report needs a project.")

    now = utcnow()
    period_days = days if days is not None else default_days
    start = now - timedelta(days=period_days) if period_days else now
    sections: list[dict] = []
    freshness: dict = {}
    limitations: list[str] = []
    builder = BUILDERS[report_type]
    await builder(db, scope, project, start, now, sections, freshness, limitations)
    for source in list(freshness):
        if freshness[source] is None:
            freshness[source] = await _latest(db, source)
    return {
        "type": report_type,
        "title": title + (f": {project.get('name')}" if project else ""),
        "project": {"id": str(project["_id"]), "name": project.get("name")} if project else None,
        "scope": project.get("name") if project else ("all projects" if scope.project_ids is None else f"{len(scope.projects)} assigned project(s)"),
        "period": {"start": iso(start), "end": iso(now), "days": period_days},
        "generated_at": iso(now),
        "data_freshness": {k: v for k, v in freshness.items()},
        "sections": sections,
        "limitations": limitations,
    }


async def _daily_or_weekly(db, scope, project, start, end, sections, freshness, limitations):
    pid = str(project["_id"])
    progress = await data.project_progress(db, scope, pid)
    tasks = await db.tasks.find({"project_id": pid}).to_list(5000)
    completed = [t for t in tasks if is_done(t.get("status")) and _in_period(t.get("updated_at"), start, end)]
    overdue = [t for t in tasks if parse_dt(t.get("due_date")) and parse_dt(t.get("due_date")) < end and not is_done(t.get("status"))]
    blocked = [t for t in tasks if norm_text(t.get("status")) == "blocked"]
    sections.append({"title": "Progress", "kind": "metrics", "items": [
        _metric("Measured progress", f"{progress['actual_progress_percent']}%" if progress["actual_progress_percent"] is not None else "No data", progress["actual_basis"]),
        _metric("Planned progress", f"{progress['planned_progress_percent']}%" if progress["planned_progress_percent"] is not None else "No data", progress["planned_basis"]),
        _metric("Tasks completed in period", len(completed)),
        _metric("Overdue tasks", len(overdue)),
        _metric("Blocked tasks", len(blocked)),
    ]})
    if completed:
        sections.append({"title": "Completed in period", "kind": "list", "items": [t.get("title") for t in completed[:30]]})
    if overdue or blocked:
        sections.append({"title": "Needs attention", "kind": "table", "columns": ["Task", "Status", "Due"],
                         "rows": [[t.get("title"), t.get("status"), (iso(t.get("due_date")) or "")[:10]] for t in (overdue + blocked)[:30]]})
    milestones = progress["milestones"]
    if milestones:
        sections.append({"title": "Milestones", "kind": "table", "columns": ["Milestone", "Status", "Due"],
                         "rows": [[m["title"], m["status"], (m["due_date"] or "")[:10]] for m in milestones]})
    if scope.can("procurement.read.assigned"):
        deliveries = await db.deliveries.find({}).to_list(20000)
        orders = {str(o["_id"]): o for o in await db.purchase_orders.find({}).to_list(20000)}
        mine = [d for d in deliveries if (o := orders.get(str(d.get("purchase_order_id")))) and (str(o.get("project_id") or "") == pid or norm_text(o.get("project")) == norm_text(project.get("name"))) and _in_period(d.get("delivery_date") or d.get("updated_at"), start, end)]
        sections.append({"title": "Deliveries in period", "kind": "table", "columns": ["PO", "Material", "Quantity", "Status"],
                         "rows": [[d.get("po_number"), d.get("material"), d.get("quantity_received"), d.get("status")] for d in mine[:30]] or [["None recorded", "", "", ""]]})
        freshness["deliveries"] = None
    if scope.can("workforce.read.assigned"):
        attendance = await db.attendance.find({"project_id": pid}).to_list(20000)
        in_period = [a for a in attendance if _in_period(a.get("date") or a.get("created_at"), start, end)]
        present = sum(1 for a in in_period if norm_text(a.get("status")) in {"present", "late", "half day", "half_day"})
        sections.append({"title": "Attendance", "kind": "metrics", "items": [_metric("Attendance records", len(in_period)), _metric("Present / late / half day", present)]})
        freshness["attendance"] = None
    safety = await db.safety_reports.find({"project_id": pid}).to_list(5000) if scope.can("safety_reports.read.assigned") else []
    if scope.can("safety_reports.read.assigned"):
        new = [s for s in safety if _in_period(s.get("created_at"), start, end)]
        sections.append({"title": "Safety", "kind": "metrics", "items": [_metric("Safety reports in period", len(new)), _metric("Open safety reports", sum(1 for s in safety if s.get("status") not in {"closed", "resolved"}))]})
    if scope.can("evidence.read.assigned"):
        evidence = await db.progress_evidence.count_documents({"project_id": pid, "created_at": {"$gte": start}})
        sections.append({"title": "Progress evidence", "kind": "metrics", "items": [_metric("Photos/evidence uploaded in period", evidence)]})
    freshness["tasks"] = None
    limitations.append("Measured progress uses milestones (or tasks when there are none); the stored project 'progress' field is not used.")


async def _inventory(db, scope, project, start, end, sections, freshness, limitations):
    forecast = await materials.material_forecast(db, scope, str(project["_id"]) if project else None)
    sections.append({"title": "Stock position", "kind": "table", "columns": ["Material", "Unit", "Physical", "Reserved", "Available", "Incoming (confirmed)", "Required", "Shortfall"],
                     "rows": [[r["material"], r["unit"], r["physical_stock"], r["reserved"], r["available"], r["incoming_confirmed"], r["required_approved"], r["projected_shortfall"]] for r in forecast["items"][:200]]})
    if forecast["shortages"]:
        sections.append({"title": "Projected shortages", "kind": "list", "items": [f"{r['material']}: {r['projected_shortfall']:g} {r['unit'] or ''} ({r['shortfall_formula']})" for r in forecast["shortages"]]})
    anomalies = [(r["material"], a) for r in forecast["items"] for a in r["wastage_anomalies"]]
    if anomalies:
        sections.append({"title": "Wastage and unusual issues", "kind": "list", "items": [f"{m}: {a['quantity']:g} on {(a['date'] or '')[:10]} ({'; '.join(a['flags'])})" for m, a in anomalies]})
    freshness["inventory"] = None
    limitations.extend(forecast["limitations"])


async def _procurement(db, scope, project, start, end, sections, freshness, limitations):
    status = await data.procurement_status(db, scope, str(project["_id"]) if project else None)
    sections.append({"title": "Summary", "kind": "metrics", "items": [
        _metric("Pending approvals", len(status["pending_approvals"])), _metric("Open requests", len(status["open_requests"])),
        _metric("Open purchase orders", len(status["open_purchase_orders"])), _metric("Overdue deliveries", len(status["overdue_deliveries"])),
        _metric("Orders without an update for 7+ days", len(status["orders_without_recent_update"]))]})
    if status["overdue_deliveries"]:
        sections.append({"title": "Overdue deliveries", "kind": "table", "columns": ["PO", "Material", "Expected", "Days late"],
                         "rows": [[o["po_number"], o["materials"], (o["expected_delivery_date"] or "")[:10], o["days_late"]] for o in status["overdue_deliveries"]]})
    if status["pending_approvals"]:
        sections.append({"title": "Awaiting approval", "kind": "table", "columns": ["Request", "Material", "Quantity", "Required by"],
                         "rows": [[r["request_id"], r["material"], r["quantity"], (r["required_date"] or "")[:10]] for r in status["pending_approvals"]]})
    freshness["purchase_orders"] = None
    freshness["material_requests"] = None


async def _deadlines(db, scope, project, start, end, sections, freshness, limitations):
    result = await data.upcoming_deadlines(db, scope, 14, str(project["_id"]) if project else None)
    for key, label in (("overdue", "Overdue"), ("upcoming", "Due in the next 14 days")):
        sections.append({"title": label, "kind": "table", "columns": ["Type", "Item", "Project", "Due", "Days late"],
                         "rows": [[i["kind"], i["title"], i["project"], (i["due_date"] or "")[:10], i["overdue_days"]] for i in result[key]] or [["None", "", "", "", ""]]})
    freshness["tasks"] = None


async def _overdue(db, scope, project, start, end, sections, freshness, limitations):
    rows = [data.task_row(scope, t) for t in await data.scoped_tasks(db, scope, str(project["_id"]) if project else None)]
    overdue = sorted([r for r in rows if r["overdue_days"] > 0], key=lambda r: -r["overdue_days"])
    sections.append({"title": "Overdue tasks", "kind": "table", "columns": ["Task", "Project", "Status", "Due", "Days late"],
                     "rows": [[r["title"], r["project"], r["status"], (r["due_date"] or "")[:10], r["overdue_days"]] for r in overdue] or [["None", "", "", "", ""]]})
    freshness["tasks"] = None


async def _safety(db, scope, project, start, end, sections, freshness, limitations):
    query = {"project_id": str(project["_id"])} if project else ({} if scope.project_ids is None else {"project_id": {"$in": list(scope.project_ids)}})
    reports = await db.safety_reports.find(query).to_list(5000)
    report_ids = [str(r["_id"]) for r in reports]
    actions = await db.corrective_actions.find({"safety_report_id": {"$in": report_ids}}).to_list(10000)
    open_actions = [a for a in actions if a.get("status") not in {"closed", "cancelled"}]
    overdue = [a for a in open_actions if parse_dt(a.get("due_date")) and parse_dt(a.get("due_date")) < end]
    sections.append({"title": "Summary", "kind": "metrics", "items": [
        _metric("Safety reports in period", sum(1 for r in reports if _in_period(r.get("created_at"), start, end))),
        _metric("Urgent reports open", sum(1 for r in reports if r.get("severity") == "urgent" and r.get("status") not in {"closed", "resolved"})),
        _metric("Open corrective actions", len(open_actions)), _metric("Overdue corrective actions", len(overdue))]})
    if open_actions:
        sections.append({"title": "Open corrective actions", "kind": "table", "columns": ["Action", "Status", "Due"],
                         "rows": [[a.get("title"), a.get("status"), (iso(a.get("due_date")) or "")[:10]] for a in open_actions[:50]]})
    freshness["safety_reports"] = None
    limitations.append("Reporter identities are not included in reports.")


async def _budget(db, scope, project, start, end, sections, freshness, limitations):
    overview = await budget.budget_overview(db, scope, str(project["_id"]) if project else None)
    sections.append({"title": "Budget position", "kind": "table", "columns": ["Project", "Budget", "Paid", "Invoiced unpaid", "Open commitments", "Known cost", "% of budget"],
                     "rows": [[p["project"], p["approved_budget"], p["paid"], p["invoiced_unpaid"], p["open_commitments"], p["known_cost"], p["known_cost_percent_of_budget"]] for p in overview["projects"]]})
    for key, label in (("duplicate_invoice_flags", "Possible duplicate invoices"), ("price_change_flags", "Unusual price changes"), ("quantity_reconciliation_flags", "Ordered / received / invoiced mismatches")):
        if overview[key]:
            sections.append({"title": label, "kind": "list", "items": [f.get("reason") or (f"{f.get('po_number')}: " + "; ".join(f.get("flags", [])) if f.get("flags") else f"{f.get('po_number')} {f.get('material')}: {f.get('change_percent')}% vs median {f.get('median_of_other_orders')}") for f in overview[key]]})
    freshness["invoices"] = None
    freshness["payments"] = None
    limitations.extend(overview["limitations"])


async def _management(db, scope, project, start, end, sections, freshness, limitations):
    risks = await risk.run_risk_assessment(db, scope, str(project["_id"]) if project else None, persist=False)
    sections.append({"title": "Project risk", "kind": "table", "columns": ["Project", "Overall level", "Top factors"],
                     "rows": [[p["project"], p["overall_level"], "; ".join(f["factors"][0] for f in p["findings"][:3])] for p in risks["projects"]]})
    deadlines = await data.upcoming_deadlines(db, scope, 7, str(project["_id"]) if project else None)
    sections.append({"title": "Next 7 days", "kind": "metrics", "items": [_metric("Overdue items", len(deadlines["overdue"])), _metric("Items due", len(deadlines["upcoming"]))]})
    if scope.can("budget.forecast.read"):
        overview = await budget.budget_overview(db, scope, str(project["_id"]) if project else None)
        over = [p for p in overview["projects"] if p["over_budget"]]
        sections.append({"title": "Budget", "kind": "metrics", "items": [_metric("Projects over budget (known cost)", len(over))]})
    freshness["tasks"] = None
    limitations.append(risks["method"])


BUILDERS = {
    "daily_site": _daily_or_weekly,
    "weekly_project": _daily_or_weekly,
    "inventory": _inventory,
    "procurement": _procurement,
    "deadlines": _deadlines,
    "overdue_tasks": _overdue,
    "safety_actions": _safety,
    "budget_variance": _budget,
    "management_summary": _management,
}


def report_to_csv(report: dict) -> str:
    """Flatten a report into CSV: one block per section."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([report["title"]])
    writer.writerow(["Scope", report["scope"], "Period", report["period"]["start"][:10], report["period"]["end"][:10], "Generated", report["generated_at"]])
    for section in report["sections"]:
        writer.writerow([])
        writer.writerow([section["title"]])
        if section["kind"] == "metrics":
            for item in section["items"]:
                writer.writerow([item["label"], item["value"], item.get("note", "")])
        elif section["kind"] == "table":
            writer.writerow(section["columns"])
            writer.writerows(section["rows"])
        elif section["kind"] == "list":
            for item in section["items"]:
                writer.writerow([item])
    writer.writerow([])
    writer.writerow(["Limitations"])
    for item in report["limitations"]:
        writer.writerow([item])
    return buffer.getvalue()
