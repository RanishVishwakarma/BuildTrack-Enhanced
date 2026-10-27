"""Project-level access control.

A permission such as `projects.read.assigned` says what a user may do; this
module decides *which* projects. Sources, in order:

1. `projects.read.all` permission: every project (returns None = unrestricted).
2. `user_project_access` records: {user_id, project_id, active} - the explicit
   assignment created by an admin/PM or seeded by the role migration.
3. Client link: an explicit `user_project_access` grant, made when a manager
   saves the project with the client's email (or in Settings -> Access).
   A matching email alone grants nothing, so signing up with a client's
   address does not open their projects.
4. Worker link: the `workers` record saved on the user as `worker_id` (set
   when a manager creates or links the login, never inferred from email),
   allocated to the project via `workforce_allocations` or `workers.project_id`.

Anything not matched is denied. Lookups 404 rather than 403 so record ids
cannot be probed for existence.
"""


from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.core.permissions import has_permission


def _user_id(user: dict) -> str:
    return str(user.get("_id"))


async def accessible_project_ids(db, user: dict) -> set[str] | None:
    """Ids of projects the user may read, or None when unrestricted."""
    if has_permission(user, "projects.read.all"):
        return None
    if not has_permission(user, "projects.read.assigned"):
        return set()

    ids: set[str] = set()
    async for row in db.user_project_access.find({"user_id": _user_id(user), "active": {"$ne": False}}, {"project_id": 1}):
        ids.add(str(row["project_id"]))

    worker = await _linked_worker(db, user, {"_id": 1, "project_id": 1})
    if worker:
        if worker.get("project_id"):
            ids.add(str(worker["project_id"]))
        async for allocation in db.workforce_allocations.find(
            {"worker_id": str(worker["_id"]), "status": {"$nin": ["ended", "cancelled", "inactive"]}},
            {"project_id": 1},
        ):
            if allocation.get("project_id"):
                ids.add(str(allocation["project_id"]))
    return ids


async def _linked_worker(db, user: dict, projection: dict | None = None) -> dict | None:
    worker_id = str(user.get("worker_id") or "")
    try:
        return await db.workers.find_one({"_id": ObjectId(worker_id)}, projection) if worker_id else None
    except (InvalidId, TypeError):
        return None


async def own_worker_ids(db, user: dict) -> set[str]:
    """The `workers` record a manager linked to this login (user.worker_id)."""
    worker = await _linked_worker(db, user, {"_id": 1})
    return {str(worker["_id"])} if worker else set()


INACTIVE_ALLOCATION = ["ended", "cancelled", "inactive", "ENDED", "CANCELLED", "INACTIVE"]


async def visible_worker_ids(db, current_user) -> set[str] | None:
    """Workers this user may see: None (all) with organisation-wide project
    access; otherwise workers on their projects (record or active allocation),
    unassigned new hires, and their own worker record."""
    projects = await accessible_project_ids(db, current_user)
    if projects is None:
        return None
    every, assigned, mine = set(), set(), set()
    async for worker in db.workers.find({}, {"project_id": 1}):
        wid, pid = str(worker["_id"]), str(worker.get("project_id") or "")
        every.add(wid)
        if pid:
            assigned.add(wid)
            if pid in projects:
                mine.add(wid)
    async for allocation in db.workforce_allocations.find({"status": {"$nin": INACTIVE_ALLOCATION}}, {"worker_id": 1, "project_id": 1}):
        wid = str(allocation.get("worker_id") or "")
        assigned.add(wid)
        if str(allocation.get("project_id") or "") in projects:
            mine.add(wid)
    return mine | (every - assigned) | await own_worker_ids(db, current_user)


async def ensure_worker_visible(db, current_user, worker_id) -> None:
    """404 (not 403) for another project's worker, so ids cannot be probed."""
    visible = await visible_worker_ids(db, current_user)
    if visible is not None and str(worker_id or "") not in visible:
        raise HTTPException(status_code=404, detail="Worker not found")


def project_scope_query(project_ids: set[str] | None, field: str = "_id") -> dict:
    """MongoDB filter limiting `field` to the accessible projects ({} = all)."""
    if project_ids is None:
        return {}
    values: list = []
    for pid in project_ids:
        values.append(pid)
        if field == "_id":
            try:
                values.append(ObjectId(pid))
            except (InvalidId, TypeError):
                pass
    return {field: {"$in": values}}


async def can_access_project(db, user: dict, project_id) -> bool:
    if project_id is None or project_id == "":
        return False
    ids = await accessible_project_ids(db, user)
    return ids is None or str(project_id) in ids


async def ensure_project_access(db, user: dict, project_id) -> None:
    """Raise 404 unless the user may access the project."""
    if not await can_access_project(db, user, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


async def grant_project_access(db, *, user_id: str, project_id: str, granted_by: dict | None, reason: str) -> None:
    """Idempotently assign a user to a project."""
    from datetime import datetime, timezone

    await db.user_project_access.update_one(
        {"user_id": str(user_id), "project_id": str(project_id)},
        {
            "$set": {"active": True, "updated_at": datetime.now(timezone.utc)},
            "$setOnInsert": {
                "granted_by": str(granted_by["_id"]) if granted_by else None,
                "reason": reason,
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )
