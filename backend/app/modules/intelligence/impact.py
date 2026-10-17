"""Change-impact analysis: "what happens if X is delayed by N days?"

Calculated impacts follow recorded links only:
  * a purchase order -> the material requests it fulfils (required_date)
  * a material       -> tasks whose `required_materials` name it
  * a task           -> tasks that list it in `depends_on` (finish-to-start)

Possible impacts (not calculated) are milestones due after an impacted task's
new finish; tasks and milestones are not linked in the data, so these are
listed as needing review. Nothing is rescheduled.
"""

from datetime import timedelta

from bson import ObjectId

from app.modules.intelligence.common import is_done, iso, norm_text, parse_dt
from app.modules.intelligence.data import AccessDenied, Scope, project_milestones

ASSUMPTIONS = [
    "Dependencies are finish-to-start; a task starts when its last predecessor finishes.",
    "Task durations are unchanged (due date minus start date, or zero when no start date is recorded).",
    "Slack is the gap between a predecessor's new finish and the dependent task's recorded start.",
]


def _oid(value):
    return ObjectId(value) if ObjectId.is_valid(str(value)) else None


async def _propagate(tasks_by_id: dict, start_ids: list[tuple[str, int]], reason: str) -> list[dict]:
    """Push delays through depends_on links. Returns impacted tasks."""
    dependents: dict[str, list[str]] = {}
    for tid, task in tasks_by_id.items():
        for pred in task.get("depends_on") or []:
            dependents.setdefault(str(pred), []).append(tid)
    impacted: dict[str, dict] = {}
    queue = list(start_ids)
    while queue:
        tid, delay = queue.pop(0)
        if delay <= 0 or tid not in tasks_by_id:
            continue
        task = tasks_by_id[tid]
        if is_done(task.get("status")):
            continue
        if tid in impacted and impacted[tid]["delay_days"] >= delay:
            continue
        due = parse_dt(task.get("due_date"))
        impacted[tid] = {
            "task_id": tid, "title": task.get("title"), "delay_days": delay,
            "original_due_date": iso(due), "new_due_date": iso(due + timedelta(days=delay)) if due else None,
            "cause": reason if tid in dict(start_ids) else "depends on a delayed task",
        }
        new_finish = due + timedelta(days=delay) if due else None
        for child_id in dependents.get(tid, []):
            child = tasks_by_id[child_id]
            child_start = parse_dt(child.get("start_date")) or parse_dt(child.get("due_date"))
            if new_finish and child_start:
                push = (new_finish - child_start).days
            else:
                push = delay
            if push > 0:
                queue.append((child_id, push))
    return sorted(impacted.values(), key=lambda row: -row["delay_days"])


async def analyze_impact(db, scope: Scope, *, kind: str, record_id: str, delay_days: int) -> dict:
    """kind: "purchase_order" or "task"."""
    if delay_days <= 0 or delay_days > 365:
        raise ValueError("delay_days must be between 1 and 365")
    calculated: list[dict] = []
    gaps: list[str] = []

    if kind == "purchase_order":
        scope.require("procurement.read.assigned")
        order = await db.purchase_orders.find_one({"_id": _oid(record_id)}) if _oid(record_id) else None
        if not order or not scope.includes_project(order.get("project_id"), order.get("project")):
            raise AccessDenied("That purchase order does not exist or is outside your projects.")
        project = next((p for p in scope.projects if str(p["_id"]) == str(order.get("project_id")) or norm_text(p.get("name")) == norm_text(order.get("project"))), None)
        expected = parse_dt(order.get("expected_delivery_date"))
        new_arrival = expected + timedelta(days=delay_days) if expected else None
        subject = {"type": "purchase_order", "id": str(order["_id"]), "label": order.get("po_number"), "material": order.get("materials"),
                   "expected_delivery_date": iso(expected), "new_expected_delivery_date": iso(new_arrival)}
        if not expected:
            gaps.append("The order has no expected delivery date, so date impacts cannot be calculated.")
        requests = await db.material_requests.find({"$or": [{"purchase_order_id": str(order["_id"])}, {"po_number": order.get("po_number")}]}).to_list(100)
        for request in requests:
            needed = parse_dt(request.get("required_date"))
            if new_arrival and needed and new_arrival > needed:
                calculated.append({"type": "material_request", "id": str(request["_id"]), "label": request.get("request_id"),
                                   "effect": f"Required by {iso(needed)[:10]}; new arrival {iso(new_arrival)[:10]} is {(new_arrival - needed).days} day(s) late"})
        start_ids: list[tuple[str, int]] = []
        tasks_by_id = {}
        if project is not None and scope.can("tasks.read.assigned"):
            tasks = await db.tasks.find({"project_id": str(project["_id"])}).to_list(5000)
            tasks_by_id = {str(t["_id"]): t for t in tasks}
            material = norm_text(order.get("materials"))
            for task in tasks:
                needs = {norm_text(m) for m in task.get("required_materials") or []}
                start = parse_dt(task.get("start_date"))
                if material and material in needs and new_arrival and start and new_arrival > start and not is_done(task.get("status")):
                    start_ids.append((str(task["_id"]), (new_arrival - start).days))
            if not any(task.get("required_materials") for task in tasks):
                gaps.append("No task records which materials it needs (required_materials), so task impacts from this order cannot be traced.")
        elif project is None:
            gaps.append("The order is not linked to a project id, so tasks cannot be traced.")
        impacted_tasks = await _propagate(tasks_by_id, start_ids, f"waits for {order.get('materials')}")
    elif kind == "task":
        task = await db.tasks.find_one({"_id": _oid(record_id)}) if _oid(record_id) else None
        if not task or not scope.can("tasks.read.assigned") or not scope.includes_project(task.get("project_id")):
            raise AccessDenied("That task does not exist or is outside your projects.")
        project = next((p for p in scope.projects if str(p["_id"]) == str(task.get("project_id"))), None)
        tasks = await db.tasks.find({"project_id": str(task.get("project_id"))}).to_list(5000)
        tasks_by_id = {str(t["_id"]): t for t in tasks}
        due = parse_dt(task.get("due_date"))
        subject = {"type": "task", "id": str(task["_id"]), "label": task.get("title"), "due_date": iso(due), "new_due_date": iso(due + timedelta(days=delay_days)) if due else None}
        impacted_tasks = await _propagate(tasks_by_id, [(str(task["_id"]), delay_days)], "the delay being analysed")
        if not any(t.get("depends_on") for t in tasks):
            gaps.append("No task in this project records dependencies (depends_on), so only the task itself is affected.")
    else:
        raise ValueError("kind must be 'purchase_order' or 'task'")

    possible = []
    if project is not None and impacted_tasks:
        latest = max((parse_dt(t["new_due_date"]) for t in impacted_tasks if t["new_due_date"]), default=None)
        for milestone in await project_milestones(db, project):
            due = parse_dt(milestone["due_date"])
            if latest and due and due < latest and not is_done(milestone["status"]):
                possible.append({"type": "milestone", "id": milestone["id"], "label": milestone["title"],
                                 "effect": f"Due {iso(due)[:10]}, before impacted work now ends {iso(latest)[:10]}. Tasks are not linked to milestones, so confirm whether it depends on this work."})
        end = parse_dt(project.get("end_date") or project.get("endDate"))
        if latest and end and latest > end:
            calculated.append({"type": "project", "id": str(project["_id"]), "label": project.get("name"),
                               "effect": f"Impacted work now ends {iso(latest)[:10]}, after the project end date {iso(end)[:10]}"})

    return {
        "subject": subject,
        "delay_days": delay_days,
        "calculated_impacts": calculated + [{"type": "task", "id": t["task_id"], "label": t["title"], "effect": f"Pushed {t['delay_days']} day(s) ({t['cause']}); due {(t['original_due_date'] or 'unset')[:10]} -> {(t['new_due_date'] or 'unset')[:10]}"} for t in impacted_tasks],
        "possible_impacts": possible,
        "assumptions": ASSUMPTIONS,
        "data_gaps": gaps,
        "note": "Analysis only. No schedule, order or task was changed.",
    }
