"""Project assignments, per-user permission grants and the audit log viewer."""

from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.access import ensure_project_access, grant_project_access
from app.core.audit import record_audit
from app.core.permissions import EXPLICIT_ONLY, PERMISSIONS, ROLE_PERMISSIONS, effective_permissions, ensure_permission
from app.core.roles import normalize_role, role_label
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.intelligence.common import clean, utcnow

router = APIRouter()


async def _user(db, user_id: str) -> dict:
    user = await db.users.find_one({"_id": ObjectId(user_id)}) if ObjectId.is_valid(user_id) else None
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/permissions")
async def registry(current_user=Depends(get_current_user)):
    ensure_permission(current_user, "users.roles.assign")
    return {
        "permissions": [{"id": key, "description": text, "explicit_only": key in EXPLICIT_ONLY} for key, text in PERMISSIONS.items()],
        "role_defaults": {role_label(role): sorted(perms) for role, perms in ROLE_PERMISSIONS.items()},
    }


@router.get("/users/{user_id}/permissions")
async def user_permissions(user_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "users.roles.assign")
    user = await _user(db, user_id)
    role = normalize_role(user.get("role"))
    return {"user_id": user_id, "role": role, "role_defaults": sorted(ROLE_PERMISSIONS.get(role, set())),
            "granted": sorted(user.get("permissions") or []), "revoked": sorted(user.get("revoked_permissions") or []),
            "effective": sorted(effective_permissions(user))}


class PermissionChange(BaseModel):
    granted: list[str] = Field(default_factory=list)
    revoked: list[str] = Field(default_factory=list)


@router.put("/users/{user_id}/permissions")
async def set_user_permissions(user_id: str, body: PermissionChange, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "users.roles.assign")
    if user_id == str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="You cannot change your own permissions")
    unknown = sorted(set(body.granted + body.revoked) - set(PERMISSIONS))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown permissions: {', '.join(unknown)}")
    if set(body.granted) & EXPLICIT_ONLY and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator can grant identity-reveal permission")
    user = await _user(db, user_id)
    before = {"granted": sorted(user.get("permissions") or []), "revoked": sorted(user.get("revoked_permissions") or [])}
    after = {"granted": sorted(set(body.granted)), "revoked": sorted(set(body.revoked))}
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"permissions": after["granted"], "revoked_permissions": after["revoked"], "updated_at": utcnow()}})
    await record_audit(db, "user.permissions.changed", actor=current_user, resource_type="user", resource_id=user_id, details={"before": before, "after": after})
    return await user_permissions(user_id, current_user, db)


@router.get("/projects/{project_id}/members")
async def members(project_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "projects.access.manage")
    await ensure_project_access(db, current_user, project_id)
    rows = await db.user_project_access.find({"project_id": project_id, "active": {"$ne": False}}).to_list(500)
    ids = [ObjectId(r["user_id"]) for r in rows if ObjectId.is_valid(r["user_id"])]
    users = {str(u["_id"]): u for u in await db.users.find({"_id": {"$in": ids}}, {"full_name": 1, "name": 1, "email": 1, "role": 1}).to_list(500)}
    return [{"user_id": r["user_id"], "name": (users.get(r["user_id"]) or {}).get("full_name") or (users.get(r["user_id"]) or {}).get("name"),
             "email": (users.get(r["user_id"]) or {}).get("email"), "role": normalize_role((users.get(r["user_id"]) or {}).get("role")),
             "reason": r.get("reason")} for r in rows]


class Member(BaseModel):
    user_id: str


@router.post("/projects/{project_id}/members")
async def add_member(project_id: str, body: Member, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "projects.access.manage")
    await ensure_project_access(db, current_user, project_id)
    user = await _user(db, body.user_id)
    if normalize_role(user.get("role")) == "vendor":
        raise HTTPException(status_code=422, detail="Vendors see purchase orders through their vendor record, not project membership")
    await grant_project_access(db, user_id=body.user_id, project_id=project_id, granted_by=current_user, reason="assigned")
    await record_audit(db, "project.member.added", actor=current_user, resource_type="user", resource_id=body.user_id, project_id=project_id)
    return {"message": "User assigned to project"}


@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_member(project_id: str, user_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "projects.access.manage")
    await ensure_project_access(db, current_user, project_id)
    if user_id == str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Ask an administrator to remove you from a project")
    result = await db.user_project_access.update_one({"user_id": user_id, "project_id": project_id}, {"$set": {"active": False, "updated_at": utcnow()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Membership not found")
    await record_audit(db, "project.member.removed", actor=current_user, resource_type="user", resource_id=user_id, project_id=project_id)
    return {"message": "User removed from project"}


@router.get("/audit-logs")
async def audit_logs(event_type: Optional[str] = None, actor_id: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                     current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "audit_logs.read")
    query: dict = {}
    if event_type:
        query["event_type"] = event_type
    if actor_id:
        query["actor_id"] = actor_id
    return clean(await db.audit_logs.find(query).sort("timestamp", -1).to_list(limit))
