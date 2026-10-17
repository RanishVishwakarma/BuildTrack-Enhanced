"""Project-level access control.

A permission such as `projects.read.assigned` says what a user may do; this
module decides *which* projects. Sources, in order:

1. `projects.read.all` permission: every project (returns None = unrestricted).
2. `user_project_access` records: {user_id, project_id, active} - the explicit
   assignment created by an admin/PM or seeded by the role migration.
3. Client link: the project's client email fields equal the user's email
   (the rule the projects router already applied to clients).
4. Worker link: the `workers` record saved on the user as `worker_id` (set
   when a manager creates or links the login, never inferred from email),
   allocated to the project via `workforce_allocations` or `workers.project_id`.

Anything not matched is denied. Lookups 404 rather than 403 so record ids
cannot be probed for existence.
"""

import re

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.core.permissions import has_permission

CLIENT_EMAIL_FIELDS = ("client_email", "clientEmail", "client")


def _user_id(user: dict) -> str:
    return str(user.get("_id"))


def _email_regex(email: str) -> dict:
    return {"$regex": f"^{re.escape(email)}$", "$options": "i"}


async def accessible_project_ids(db, user: dict) -> set[str] | None:
    """Ids of projects the user may read, or None when unrestricted."""
    if has_permission(user, "projects.read.all"):
        return None
    if not has_permission(user, "projects.read.assigned"):
        return set()

    ids: set[str] = set()
    async for row in db.user_project_access.find({"user_id": _user_id(user), "active": {"$ne": False}}, {"project_id": 1}):
        ids.add(str(row["project_id"]))

    email = str(user.get("email") or "").strip()
    if email:
        if user.get("role") == "client":
            query = {"$or": [{field: _email_regex(email)} for field in CLIENT_EMAIL_FIELDS]}
            async for project in db.projects.find(query, {"_id": 1}):
                ids.add(str(project["_id"]))

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
