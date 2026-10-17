"""Authorized, deterministic reads used by the AI assistant, monitoring,
risk engine and reports.

Every function takes a `Scope` built from the authenticated user. Permission
checks and project filters are applied inside the database queries here, so
callers (including the LLM tool layer) cannot widen what a user may see.
Figures are calculated in Python; nothing here estimates or invents values.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from bson import ObjectId

from app.core.access import accessible_project_ids, own_worker_ids, project_scope_query
from app.core.permissions import has_permission
from app.modules.intelligence.common import clean, is_done, iso, norm_text, parse_dt, ref, to_float, utcnow

OPEN_PO_STATUSES = {"created", "sent", "accepted", "processing", "shipped"}
CLOSED_DELIVERY_STATUSES = {"delivered", "received", "accepted", "cancelled", "rejected"}
OPEN_REQUEST_STATUSES = {
    "pending", "approved", "vendor_assigned", "sent_to_vendor", "vendor_accepted", "po_generated",
    "po_sent", "po_accepted", "partially_delivered",
}


class AccessDenied(Exception):
    """The user lacks the permission or project access for this data."""


@dataclass
class Scope:
    user: dict
    project_ids: set[str] | None  # None = every project
    projects: list[dict] = field(default_factory=list)
    worker_ids: set[str] = field(default_factory=set)
    worker_categories: set[str] = field(default_factory=set)

    @property
    def project_names(self) -> set[str]:
        return {norm_text(p.get("name")) for p in self.projects if p.get("name")}

    def can(self, *permissions: str) -> bool:
        return has_permission(self.user, *permissions)

    def require(self, *permissions: str) -> None:
        if not self.can(*permissions):
            raise AccessDenied(f"Your role does not include access to this ({' or '.join(permissions)}).")

    def includes_project(self, project_id=None, project_name=None) -> bool:
        if self.project_ids is None:
            return True
        if project_id and str(project_id) in self.project_ids:
            return True
        return bool(project_name) and norm_text(project_name) in self.project_names

    def project_label(self, project_id=None, project_name=None) -> str:
        for project in self.projects:
            if project_id and str(project["_id"]) == str(project_id):
                return project.get("name") or str(project_id)
        return project_name or (str(project_id) if project_id else "Unassigned")


async def build_scope(db, user: dict) -> Scope:
    ids = await accessible_project_ids(db, user)
    query = project_scope_query(ids) if ids is not None else {}
    projects = await db.projects.find(query).to_list(1000) if has_permission(user, "projects.read.all", "projects.read.assigned") else []
    worker_ids = await own_worker_ids(db, user)
    categories: set[str] = set()
    if worker_ids:
        async for worker in db.workers.find({"_id": {"$in": [ObjectId(i) for i in worker_ids if ObjectId.is_valid(i)]}}, {"category": 1}):
            if worker.get("category"):
                categories.add(str(worker["category"]))
    return Scope(user=user, project_ids=ids, projects=projects, worker_ids=worker_ids, worker_categories=categories)


def _project_or_denied(scope: Scope, project_id: str) -> dict:
    for project in scope.projects:
        if str(project["_id"]) == str(project_id):
            return project
    raise AccessDenied("That project does not exist or you are not assigned to it.")


# ------------------------------------------------------------------ projects

async def project_milestones(db, project: dict) -> list[dict]:
    """Milestones from both stores: project_milestones records and the
    project's embedded `milestones` array."""
    pid = str(project["_id"])
    rows = await db.project_milestones.find({"$or": [{"project_id": pid}, {"projectId": pid}]}).to_list(500)
    milestones = [
        {"id": str(row["_id"]), "title": row.get("title") or row.get("name") or "Milestone", "due_date": iso(row.get("due_date") or row.get("dueDate")), "status": row.get("status") or "pending", "source": "project_milestones"}
        for row in rows
    ]
    for index, item in enumerate(project.get("milestones") or []):
        if isinstance(item, dict):
            milestones.append({"id": f"{pid}:embedded:{index}", "title": item.get("title") or item.get("name") or "Milestone", "due_date": iso(item.get("due_date") or item.get("dueDate")), "status": item.get("status") or "pending", "source": "project.milestones"})
    return milestones


async def project_progress(db, scope: Scope, project_id: str) -> dict:
    """Planned vs actual progress with the basis of each number stated."""
    scope.require("projects.read.all", "projects.read.assigned")
    project = _project_or_denied(scope, project_id)
    now = utcnow()
    start, end = parse_dt(project.get("start_date") or project.get("startDate")), parse_dt(project.get("end_date") or project.get("endDate"))

    planned = None
    planned_basis = "no start/end dates recorded"
    if start and end and end > start:
        planned = round(min(100.0, max(0.0, (now - start) / (end - start) * 100)), 1)
        planned_basis = "share of the scheduled duration elapsed"

    milestones = await project_milestones(db, project)
    tasks = await db.tasks.find({"project_id": str(project["_id"])}).to_list(2000)
    actual, actual_basis = None, "no milestones or tasks recorded"
    if milestones:
        actual = round(sum(1 for m in milestones if is_done(m["status"])) / len(milestones) * 100, 1)
        actual_basis = f"{sum(1 for m in milestones if is_done(m['status']))} of {len(milestones)} milestones completed"
    elif tasks:
        actual = round(sum(1 for t in tasks if is_done(t.get("status"))) / len(tasks) * 100, 1)
        actual_basis = f"{sum(1 for t in tasks if is_done(t.get('status')))} of {len(tasks)} tasks completed"

    result = {
        "project": ref("project", project),
        "status": project.get("status"),
        "start_date": iso(start),
        "end_date": iso(end),
        "planned_progress_percent": planned,
        "planned_basis": planned_basis,
        "actual_progress_percent": actual,
        "actual_basis": actual_basis,
        "variance_points": round(actual - planned, 1) if actual is not None and planned is not None else None,
        "days_remaining": (end - now).days if end else None,
        "milestones": milestones,
        "task_counts": {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if is_done(t.get("status"))),
            "blocked": sum(1 for t in tasks if norm_text(t.get("status")) == "blocked"),
        },
        "note": "The stored 'progress' field is not used: for projects without milestones the API reports an estimated value, not a measurement.",
    }
    if scope.can("budget.read.assigned"):
        result["budget"] = to_float(project.get("budget"))
    return result


async def authorized_projects(db, scope: Scope) -> list[dict]:
    scope.require("projects.read.all", "projects.read.assigned")
    rows = []
    for project in scope.projects:
        row = {
            "id": str(project["_id"]),
            "name": project.get("name"),
            "status": project.get("status"),
            "location": project.get("location"),
            "start_date": iso(project.get("start_date") or project.get("startDate")),
            "end_date": iso(project.get("end_date") or project.get("endDate")),
        }
        if scope.can("budget.read.assigned"):
            row["budget"] = to_float(project.get("budget"))
        rows.append(row)
    return rows


# --------------------------------------------------------------------- tasks

async def scoped_tasks(db, scope: Scope, project_id: str | None = None) -> list[dict]:
    """Tasks the user may read: project tasks, or only their own."""
    if scope.can("tasks.read.assigned"):
        if project_id:
            _project_or_denied(scope, project_id)
            query = {"project_id": str(project_id)}
        elif scope.project_ids is None:
            query = {}
        else:
            query = {"project_id": {"$in": list(scope.project_ids)}}
        return await db.tasks.find(query).to_list(5000)
    if scope.can("tasks.read.own"):
        own = [{"assigned_worker_id": {"$in": list(scope.worker_ids)}}] if scope.worker_ids else []
        if scope.worker_categories and scope.project_ids:
            own.append({"assigned_category": {"$in": list(scope.worker_categories)}, "project_id": {"$in": list(scope.project_ids)}})
        if not own:
            return []
        query = {"$or": own}
        if project_id:
            query = {"$and": [query, {"project_id": str(project_id)}]}
        return await db.tasks.find(query).to_list(2000)
    raise AccessDenied("Your role does not include access to tasks.")


def task_row(scope: Scope, task: dict, now=None) -> dict:
    now = now or utcnow()
    due = parse_dt(task.get("due_date"))
    overdue = bool(due and due < now and not is_done(task.get("status")))
    return {
        "id": str(task["_id"]),
        "title": task.get("title"),
        "project": scope.project_label(task.get("project_id")),
        "project_id": task.get("project_id"),
        "status": task.get("status"),
        "due_date": iso(due),
        "overdue_days": (now - due).days if overdue else 0,
        "assigned_worker_id": task.get("assigned_worker_id"),
        "assigned_category": task.get("assigned_category"),
        "depends_on": task.get("depends_on") or [],
    }


async def upcoming_deadlines(db, scope: Scope, days: int = 14, project_id: str | None = None) -> dict:
    """Overdue and upcoming items: tasks, milestones and (when permitted)
    expected deliveries and required material dates."""
    now = utcnow()
    horizon = now + timedelta(days=max(1, min(days, 90)))
    items = []
    tasks = await scoped_tasks(db, scope, project_id) if scope.can("tasks.read.own", "tasks.read.assigned") else []
    for task in tasks:
        due = parse_dt(task.get("due_date"))
        if due and due <= horizon and not is_done(task.get("status")):
            row = task_row(scope, task, now)
            items.append({"kind": "task", **row})
    if scope.can("projects.read.all", "projects.read.assigned"):
        projects = [_project_or_denied(scope, project_id)] if project_id else scope.projects
        for project in projects:
            for milestone in await project_milestones(db, project):
                due = parse_dt(milestone["due_date"])
                if due and due <= horizon and not is_done(milestone["status"]):
                    items.append({"kind": "milestone", "id": milestone["id"], "title": milestone["title"], "project": project.get("name"), "project_id": str(project["_id"]), "status": milestone["status"], "due_date": iso(due), "overdue_days": max(0, (now - due).days) if due < now else 0})
    if scope.can("procurement.read.assigned"):
        status = await procurement_status(db, scope, project_id)
        for po in status["open_purchase_orders"]:
            due = parse_dt(po["expected_delivery_date"])
            if due and due <= horizon:
                items.append({"kind": "delivery", "id": po["id"], "title": f"Delivery for {po['po_number']} ({po['materials']})", "project": po["project"], "status": po["status"], "due_date": po["expected_delivery_date"], "overdue_days": max(0, (now - due).days) if due < now else 0})
    items.sort(key=lambda item: item["due_date"] or "")
    return {
        "as_of": now.isoformat(),
        "window_days": days,
        "overdue": [item for item in items if item["overdue_days"] > 0],
        "upcoming": [item for item in items if item["overdue_days"] == 0],
    }


# ----------------------------------------------------------------- inventory

def stock_quantity(item: dict) -> float:
    for key in ("stock_quantity", "quantity"):
        value = to_float(item.get(key))
        if value is not None:
            return value
    return 0.0


async def inventory_items(db, scope: Scope) -> list[dict]:
    scope.require("inventory.read.assigned")
    rows = []
    for item in await db.inventory.find({}).to_list(5000):
        quantity = stock_quantity(item)
        reorder = to_float(item.get("reorder_level"))
        rows.append({
            "id": str(item["_id"]),
            "material": item.get("material") or item.get("material_name") or item.get("itemName") or "Unnamed item",
            "unit": item.get("unit"),
            "physical_stock": quantity,
            "reorder_level": reorder,
            "below_reorder_level": reorder is not None and quantity <= reorder,
            "location": item.get("location"),
            "updated_at": iso(item.get("updated_at")),
        })
    return rows


# --------------------------------------------------------------- procurement

def _procurement_filter(scope: Scope, record: dict) -> bool:
    if scope.user.get("role") == "vendor":
        vendor_id = str(scope.user.get("vendor_id") or "")
        return bool(vendor_id) and vendor_id in {str(record.get("vendor_id") or ""), str(record.get("assigned_vendor_id") or "")}
    return scope.includes_project(record.get("project_id"), record.get("project"))


async def procurement_status(db, scope: Scope, project_id: str | None = None) -> dict:
    """Open requests, open orders, overdue deliveries and stale orders."""
    if scope.user.get("role") != "vendor":
        scope.require("procurement.read.assigned")
    elif not scope.user.get("vendor_id"):
        raise AccessDenied("This vendor account is not linked to a vendor record.")
    now = utcnow()
    project = _project_or_denied(scope, project_id) if project_id else None

    def wanted(record):
        if not _procurement_filter(scope, record):
            return False
        if project is not None:
            return str(record.get("project_id") or "") == str(project["_id"]) or norm_text(record.get("project")) == norm_text(project.get("name"))
        return True

    requests = [r for r in await db.material_requests.find({}).to_list(5000) if wanted(r)]
    orders = [o for o in await db.purchase_orders.find({}).to_list(5000) if wanted(o)]
    deliveries = await db.deliveries.find({"purchase_order_id": {"$in": [str(o["_id"]) for o in orders]}}).to_list(10000)
    received = {}
    for delivery in deliveries:
        if norm_text(delivery.get("status")) in {"delivered", "received", "accepted"}:
            key = str(delivery.get("purchase_order_id"))
            received[key] = received.get(key, 0.0) + (to_float(delivery.get("quantity_received")) or 0.0)

    open_requests = [
        {"id": str(r["_id"]), "request_id": r.get("request_id"), "material": r.get("material_name"), "quantity": to_float(r.get("quantity")), "unit": r.get("unit"),
         "project": r.get("project"), "status": r.get("status"), "required_date": iso(r.get("required_date")), "priority": r.get("priority"), "remarks": r.get("remarks")}
        for r in requests if norm_text(r.get("status")) in OPEN_REQUEST_STATUSES
    ]
    open_orders, overdue, stale = [], [], []
    for order in orders:
        status = norm_text(order.get("status"))
        if status not in OPEN_PO_STATUSES:
            continue
        expected = parse_dt(order.get("expected_delivery_date"))
        updated = parse_dt(order.get("updated_at")) or parse_dt(order.get("created_at"))
        ordered = to_float(order.get("quantity")) or 0.0
        row = {
            "id": str(order["_id"]), "po_number": order.get("po_number"), "materials": order.get("materials"), "project": order.get("project"),
            "status": order.get("status"), "vendor_id": order.get("vendor_id"), "quantity_ordered": ordered,
            "quantity_received": received.get(str(order["_id"]), 0.0), "expected_delivery_date": iso(expected), "last_update": iso(updated),
        }
        open_orders.append(row)
        if expected and expected < now:
            overdue.append({**row, "days_late": (now - expected).days})
        if updated and (now - updated).days >= 7:
            stale.append({**row, "days_since_update": (now - updated).days})
    return {
        "as_of": now.isoformat(),
        "pending_approvals": [r for r in open_requests if norm_text(r["status"]) == "pending"],
        "open_requests": open_requests,
        "open_purchase_orders": open_orders,
        "overdue_deliveries": overdue,
        "orders_without_recent_update": stale,
    }


def to_json(value):
    return clean(value)
