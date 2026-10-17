"""Rule-based project risk assessment.

Each rule inspects authorized records and, when it fires, produces an
assessment with the factors and source records behind it. Levels come from
explicit thresholds below; no probabilities are produced. Assessments are
stored in `risk_assessments` keyed by (project, rule) so re-running updates
them, and a rule that stops firing marks its assessment "cleared".
"""

from datetime import timedelta

from bson import ObjectId

from app.modules.intelligence.common import is_done, iso, norm_text, parse_dt, utcnow
from app.modules.intelligence.data import Scope, procurement_status, project_milestones, project_progress
from app.modules.intelligence.materials import material_forecast

LEVELS = ["low", "medium", "high", "critical"]

RULES = {
    "overdue_milestones": ("schedule", "Review the late milestones with the site team and agree recovery dates."),
    "overdue_tasks": ("schedule", "Reassign or re-plan overdue tasks and confirm new due dates with their owners."),
    "progress_variance": ("schedule", "Compare actual against planned progress and agree a recovery plan."),
    "blocked_dependencies": ("dependencies", "Unblock the predecessor tasks or re-sequence the dependent work."),
    "material_shortage": ("materials", "Raise or expedite material requests, or arrange an approved transfer."),
    "delayed_procurement": ("procurement", "Contact the vendor for a confirmed delivery date and update the order."),
    "stale_orders": ("procurement", "Ask the vendor for a status update on the orders listed."),
    "deadline_pressure": ("deadline", "Review remaining scope against the end date and escalate if it cannot be met."),
    "no_workforce": ("workforce", "Allocate crew to the project or confirm it is paused."),
    "equipment_unavailable": ("equipment", "Arrange repair or a replacement for the listed equipment."),
}


def _level(value: float, thresholds: list[tuple[float, str]]) -> str:
    for limit, level in thresholds:
        if value >= limit:
            return level
    return "low"


def _finding(rule: str, level: str, factors: list[str], sources: list[dict]) -> dict:
    category, action = RULES[rule]
    return {"rule": rule, "category": category, "level": level, "factors": factors, "sources": sources, "recommended_action": action}


async def assess_project(db, scope: Scope, project: dict, forecast: dict | None = None) -> list[dict]:
    """Run every rule for one project. Returns the rules that fired."""
    now = utcnow()
    pid = str(project["_id"])
    findings = []

    milestones = await project_milestones(db, project)
    late = [(m, (now - parse_dt(m["due_date"])).days) for m in milestones if parse_dt(m["due_date"]) and parse_dt(m["due_date"]) < now and not is_done(m["status"])]
    if late:
        worst = max(days for _, days in late)
        findings.append(_finding("overdue_milestones", _level(worst, [(30, "critical"), (14, "high"), (3, "medium")]),
                                 [f"{m['title']} is {d} day(s) past its due date" for m, d in late[:10]],
                                 [{"type": "milestone", "id": m["id"], "label": m["title"]} for m, _ in late[:10]]))

    tasks = await db.tasks.find({"project_id": pid}).to_list(5000)
    overdue = [(t, (now - parse_dt(t.get("due_date"))).days) for t in tasks if parse_dt(t.get("due_date")) and parse_dt(t.get("due_date")) < now and not is_done(t.get("status"))]
    if overdue:
        worst = max(d for _, d in overdue)
        level = _level(len(overdue) * 2 + worst, [(30, "high"), (8, "medium")])
        findings.append(_finding("overdue_tasks", level,
                                 [f"{len(overdue)} task(s) overdue; the oldest by {worst} day(s)"] + [f"{t.get('title')}: {d} day(s) late" for t, d in overdue[:8]],
                                 [{"type": "task", "id": str(t["_id"]), "label": t.get("title")} for t, _ in overdue[:10]]))

    by_id = {str(t["_id"]): t for t in tasks}
    blocked = []
    for task in tasks:
        if is_done(task.get("status")):
            continue
        open_predecessors = [by_id[d] for d in (task.get("depends_on") or []) if d in by_id and not is_done(by_id[d].get("status"))]
        late_predecessors = [p for p in open_predecessors if parse_dt(p.get("due_date")) and parse_dt(p.get("due_date")) < now]
        if norm_text(task.get("status")) == "blocked" or late_predecessors:
            blocked.append((task, late_predecessors))
    if blocked:
        findings.append(_finding("blocked_dependencies", "high" if len(blocked) >= 3 else "medium",
                                 [f"{t.get('title')} is blocked" + (f" by late task(s): {', '.join(p.get('title') or '?' for p in ps)}" if ps else "") for t, ps in blocked[:8]],
                                 [{"type": "task", "id": str(t["_id"]), "label": t.get("title")} for t, _ in blocked[:10]]))

    progress = await project_progress(db, scope, pid)
    variance = progress["variance_points"]
    if variance is not None and variance <= -10:
        findings.append(_finding("progress_variance", "high" if variance <= -20 else "medium",
                                 [f"Actual progress {progress['actual_progress_percent']}% ({progress['actual_basis']}) vs planned {progress['planned_progress_percent']}% ({progress['planned_basis']})"],
                                 [{"type": "project", "id": pid, "label": project.get("name")}]))
    end = parse_dt(project.get("end_date") or project.get("endDate"))
    actual = progress["actual_progress_percent"]
    if end and now <= end <= now + timedelta(days=14) and actual is not None and actual < 90 and not is_done(project.get("status")):
        findings.append(_finding("deadline_pressure", "high" if (end - now).days <= 7 else "medium",
                                 [f"Project ends {iso(end)[:10]} ({(end - now).days} day(s)) with {actual}% measured progress"],
                                 [{"type": "project", "id": pid, "label": project.get("name")}]))

    if scope.can("inventory.read.assigned"):
        forecast = forecast if forecast is not None else await material_forecast(db, scope, pid, horizon_days=21)
        short = [row for row in forecast["shortages"] if any(norm_text(d.get("project")) == norm_text(project.get("name")) for d in row["demand"])] if forecast.get("project") is None else forecast["shortages"]
        if short:
            soonest = min((parse_dt(r["next_required_date"]) for r in short if r["next_required_date"]), default=None)
            level = "high" if soonest and soonest <= now + timedelta(days=7) else "medium"
            findings.append(_finding("material_shortage", level,
                                     [f"{r['material']}: shortfall {r['projected_shortfall']:g} {r['unit'] or ''} ({r['shortfall_formula']}), needed by {(r['next_required_date'] or 'unspecified')[:10]}" for r in short[:8]],
                                     [{"type": "inventory_item", "id": r["item_id"], "label": r["material"]} for r in short[:10]]))

    if scope.can("procurement.read.assigned"):
        status = await procurement_status(db, scope, pid)
        if status["overdue_deliveries"]:
            worst = max(o["days_late"] for o in status["overdue_deliveries"])
            findings.append(_finding("delayed_procurement", _level(worst, [(14, "critical"), (7, "high"), (1, "medium")]),
                                     [f"{o['po_number']} ({o['materials']}) is {o['days_late']} day(s) past its expected delivery" for o in status["overdue_deliveries"][:8]],
                                     [{"type": "purchase_order", "id": o["id"], "label": o["po_number"]} for o in status["overdue_deliveries"][:10]]))
        stale = [o for o in status["orders_without_recent_update"] if o not in status["overdue_deliveries"]]
        if stale:
            findings.append(_finding("stale_orders", "low",
                                     [f"{o['po_number']}: no update for {o['days_since_update']} day(s)" for o in stale[:8]],
                                     [{"type": "purchase_order", "id": o["id"], "label": o["po_number"]} for o in stale[:10]]))

    if norm_text(project.get("status")) in {"active", "in progress", "in_progress"} and scope.can("workforce.read.assigned"):
        allocated = await db.workforce_allocations.count_documents({"project_id": pid, "status": {"$nin": ["ended", "cancelled", "inactive"]}})
        if allocated == 0:
            findings.append(_finding("no_workforce", "medium", ["Project is active but has no current workforce allocation"], [{"type": "project", "id": pid, "label": project.get("name")}]))

    if scope.can("resources.read.assigned"):
        broken = await db.resources.find({"assigned_project": pid, "status": {"$in": ["maintenance", "under_maintenance", "out_of_service", "broken", "repair"]}}).to_list(100)
        if broken:
            findings.append(_finding("equipment_unavailable", "medium",
                                     [f"{r.get('name') or r.get('resource_name') or 'Equipment'} is {r.get('status')}" for r in broken[:8]],
                                     [{"type": "resource", "id": str(r["_id"]), "label": r.get("name") or "Equipment"} for r in broken[:10]]))
    return findings


async def _responsible_manager(db, project_id: str) -> str | None:
    rows = await db.user_project_access.find({"project_id": project_id, "active": {"$ne": False}}).to_list(100)
    ids = [ObjectId(r["user_id"]) for r in rows if ObjectId.is_valid(r["user_id"])]
    if not ids:
        return None
    manager = await db.users.find_one({"_id": {"$in": ids}, "role": "projectmanager", "status": {"$regex": "^active$", "$options": "i"}})
    return str(manager["_id"]) if manager else None


async def run_risk_assessment(db, scope: Scope, project_id: str | None = None, persist: bool = True) -> dict:
    """Assess the user's projects (or one). With persist=True, upsert stored
    assessments and clear those whose rule no longer fires."""
    scope.require("risks.read.assigned")
    projects = [p for p in scope.projects if project_id is None or str(p["_id"]) == str(project_id)]
    if project_id and not projects:
        from app.modules.intelligence.data import AccessDenied

        raise AccessDenied("That project does not exist or you are not assigned to it.")
    now = utcnow()
    summary = []
    forecast = await material_forecast(db, scope, horizon_days=21) if scope.can("inventory.read.assigned") else None
    for project in projects:
        if is_done(project.get("status")):
            continue
        pid = str(project["_id"])
        findings = await assess_project(db, scope, project, forecast)
        responsible = await _responsible_manager(db, pid)
        if persist:
            fired = set()
            for finding in findings:
                fired.add(finding["rule"])
                existing = await db.risk_assessments.find_one({"project_id": pid, "rule": finding["rule"]})
                update = {**finding, "project_id": pid, "project_name": project.get("name"), "responsible_user_id": responsible, "last_detected_at": now, "status": "active"}
                if existing is None:
                    await db.risk_assessments.insert_one({**update, "detected_at": now, "review_status": "open"})
                else:
                    reopened = existing.get("status") == "cleared" or LEVELS.index(finding["level"]) > LEVELS.index(existing.get("level", "low"))
                    changes = {**update}
                    if reopened and existing.get("review_status") in {"resolved", "dismissed"}:
                        changes["review_status"] = "open"
                    await db.risk_assessments.update_one({"_id": existing["_id"]}, {"$set": changes})
            await db.risk_assessments.update_many(
                {"project_id": pid, "rule": {"$nin": list(fired)}, "status": "active"},
                {"$set": {"status": "cleared", "cleared_at": now}},
            )
        overall = max((f["level"] for f in findings), key=LEVELS.index, default=None)
        summary.append({"project_id": pid, "project": project.get("name"), "overall_level": overall or "none", "findings": findings, "responsible_user_id": responsible})
    summary.sort(key=lambda s: -(LEVELS.index(s["overall_level"]) if s["overall_level"] in LEVELS else -1))
    return {"as_of": now.isoformat(), "projects": summary, "method": "Rule-based thresholds on authorized records; no probabilities are estimated."}


async def stored_assessments(db, scope: Scope, project_id: str | None = None, include_cleared: bool = False) -> list[dict]:
    scope.require("risks.read.assigned")
    query: dict = {}
    if not include_cleared:
        query["status"] = "active"
    if scope.project_ids is not None:
        query["project_id"] = {"$in": list(scope.project_ids)}
    if project_id:
        if not scope.includes_project(project_id):
            from app.modules.intelligence.data import AccessDenied

            raise AccessDenied("That project does not exist or you are not assigned to it.")
        query["project_id"] = str(project_id)
    rows = await db.risk_assessments.find(query).sort("last_detected_at", -1).to_list(1000)
    return rows

