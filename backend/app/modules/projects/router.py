from bson import ObjectId
import re
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime

from app.core.access import accessible_project_ids, ensure_project_access, grant_project_access, project_scope_query
from app.core.audit import record_audit
from app.core.permissions import ensure_permission, has_permission
from app.core.roles import normalize_role
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.notifications.db import create_notification
from app.modules.projects.db import (
    add_milestone,
    create_project,
    delete_project,
    get_project,
    get_projects_by_manager,
    list_projects,
    update_project,
)
from app.modules.projects.models import (
    MilestoneBase,
    Project,
    ProjectCreate,
    ProjectUpdate,
)

CLIENT_ACCESS_REASON = "project client"


MANAGER_ACCESS_REASON = "project manager"


async def resolve_manager(db, value) -> dict | None:
    """The project-manager account named by `value`: an account id, or (older
    records) the manager's display name or email."""
    value = str(value or "").strip()
    if not value or value == "unassigned":
        return None
    user = await db.users.find_one({"_id": ObjectId(value)}) if ObjectId.is_valid(value) else None
    if user is None:
        exact = {"$regex": f"^{re.escape(value)}$", "$options": "i"}
        user = await db.users.find_one({"$or": [{"full_name": exact}, {"name": exact}, {"email": exact}]})
    return user if user and normalize_role(user.get("role")) == "projectmanager" else None


async def assign_manager(db, actor: dict, project_id: str, value, previous=None) -> str:
    """Hierarchy: an admin assigns projects to project managers; a project
    manager can only manage a project themselves. The assigned manager gets
    access to the project, and a replaced manager loses that access.
    Returns the value to store (the account id, or "unassigned")."""
    manager = await resolve_manager(db, value)
    if value not in (None, "", "unassigned") and manager is None:
        raise HTTPException(status_code=422, detail="Choose a project manager account")
    is_admin = normalize_role(actor.get("role")) == "admin"
    if manager and not is_admin and str(manager["_id"]) != str(actor["_id"]):
        raise HTTPException(status_code=403, detail="Only an administrator can assign a project to another project manager")
    old = await resolve_manager(db, previous)
    if old and (not manager or old["_id"] != manager["_id"]):
        if not is_admin and str(old["_id"]) != str(actor["_id"]):
            raise HTTPException(status_code=403, detail="Only an administrator can change another manager's project")
        await db.user_project_access.update_many(
            {"user_id": str(old["_id"]), "project_id": str(project_id), "reason": MANAGER_ACCESS_REASON},
            {"$set": {"active": False, "updated_at": datetime.utcnow()}},
        )
    if manager:
        await grant_project_access(db, user_id=str(manager["_id"]), project_id=str(project_id), granted_by=actor, reason=MANAGER_ACCESS_REASON)
        return str(manager["_id"])
    return "unassigned"


async def with_manager_names(db, projects: list[dict]) -> list[dict]:
    ids = {str(p.get("project_manager_id")) for p in projects if ObjectId.is_valid(str(p.get("project_manager_id") or ""))}
    names = {str(u["_id"]): u.get("full_name") or u.get("name") or u.get("email")
             async for u in db.users.find({"_id": {"$in": [ObjectId(i) for i in ids]}}, {"full_name": 1, "name": 1, "email": 1})}
    out = []
    for project in projects:
        project = serialize_project(project)
        value = str(project.get("project_manager_id") or "")
        project["project_manager_name"] = names.get(value) or (None if ObjectId.is_valid(value) or value == "unassigned" else value or None)
        out.append(project)
    return out


async def grant_client_access(db, client_user: dict | None, project_id: str, granted_by: dict) -> None:
    """A manager naming a client on a project gives that client account access.
    Only accounts with the client role qualify; access is never inferred from
    an email match at read time."""
    if client_user and str(client_user.get("role") or "").lower() == "client" and client_user.get("_id"):
        await grant_project_access(db, user_id=str(client_user["_id"]), project_id=project_id, granted_by=granted_by, reason=CLIENT_ACCESS_REASON)


router = APIRouter()


def serialize_project(doc: dict) -> dict:
    """Normalize legacy frontend-data project documents to the module schema."""
    project = dict(doc)
    project["_id"] = str(project["_id"])
    project.setdefault("description", project.get("category", ""))
    project.setdefault("project_manager_id", project.get("managerId") or project.get("manager") or "unassigned")
    project.setdefault("start_date", project.get("startDate") or datetime.utcnow())
    project.setdefault("end_date", project.get("endDate") or project.get("start_date") or datetime.utcnow())
    project.setdefault("budget", project.get("budget", 0))
    project.setdefault("status", project.get("status", "planning"))
    project.setdefault("location", "")
    project.setdefault("client", project.get("client") or "")
    project.setdefault("client_email", project.get("client_email") or project.get("clientEmail") or "")
    project.setdefault("milestones", [])
    project.setdefault("created_at", datetime.utcnow())
    project.setdefault("updated_at", datetime.utcnow())

    # Compute progress accurately across milestones and active project timelines
    milestones = project.get("milestones") or []
    if milestones and len(milestones) > 0:
        completed = sum(1 for m in milestones if str(m.get("status", "")).lower() == "completed")
        in_prog = sum(1 for m in milestones if str(m.get("status", "")).lower() in ["in_progress", "in progress", "active"])
        project["progress"] = round(((completed * 100.0) + (in_prog * 50.0)) / len(milestones), 1)
    elif "progress" in project and project["progress"] is not None and float(project["progress"] or 0) > 0:
        project["progress"] = round(float(project["progress"]), 1)
    else:
        st = str(project.get("status", "")).lower()
        if st in ["completed"]:
            project["progress"] = 100.0
        elif st in ["active", "in_progress", "in progress"]:
            # Real timeline progression based on start_date and end_date
            try:
                s_date = project.get("startDate") or project.get("start_date")
                e_date = project.get("endDate") or project.get("end_date")
                s_dt = datetime.fromisoformat(str(s_date).replace("Z", "+00:00").split()[0]) if isinstance(s_date, str) else s_date
                e_dt = datetime.fromisoformat(str(e_date).replace("Z", "+00:00").split()[0]) if isinstance(e_date, str) else e_date

                now = datetime.utcnow()
                if hasattr(s_dt, "tzinfo") and s_dt.tzinfo:
                    s_dt = s_dt.replace(tzinfo=None)
                if hasattr(e_dt, "tzinfo") and e_dt.tzinfo:
                    e_dt = e_dt.replace(tzinfo=None)

                if s_dt and e_dt and e_dt > s_dt:
                    total_days = max(1, (e_dt - s_dt).days)
                    elapsed_days = max(1, (now - s_dt).days)
                    pct = min(95.0, max(15.0, round((elapsed_days / total_days) * 100.0, 1)))
                    project["progress"] = pct
                else:
                    project["progress"] = 45.0
            except Exception:
                project["progress"] = 45.0
        else:
            project["progress"] = 0.0

    return project


@router.post("", response_model=Project)
@router.post("/", response_model=Project)
async def create_project_endpoint(
    project: ProjectCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Create a new project and auto-provision client user if email specified"""
    ensure_permission(current_user, "projects.create")

    project_data = project.model_dump()
    c_email = str(project_data.get("client_email") or project_data.get("clientEmail") or "").strip().lower()
    client_account = None
    if c_email:
        project_data["client_email"] = c_email
        project_data["clientEmail"] = c_email

        # Auto-provision Client login if it doesn't exist yet
        client_user = await db.users.find_one({"email": {"$regex": f"^{re.escape(c_email)}$", "$options": "i"}})
        if not client_user:
            client_name = project_data.get("client") or c_email.split("@")[0].capitalize()
            new_client = {
                "email": c_email,
                "name": client_name,
                # No password: the client sets one through password reset.
                # (Previously every auto-created client got "Client@123".)
                "role": "client",
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            inserted = await db.users.insert_one(new_client)
            new_client["_id"] = inserted.inserted_id
            
            # Notify admins of new client registration
            from app.modules.auth.router import notify_admin_of_new_user
            await notify_admin_of_new_user(db, new_client, "Client")
            client_user = new_client
        client_account = client_user

    # A project manager who creates a project manages it unless an admin picks someone.
    wanted = project_data.get("project_manager_id")
    if wanted in (None, "", "unassigned") and normalize_role(current_user.get("role")) == "projectmanager":
        wanted = str(current_user["_id"])
    project_data["project_manager_id"] = "unassigned"
    result = await create_project(db, project_data)
    p_id = str(result["_id"])
    await grant_project_access(db, user_id=str(current_user["_id"]), project_id=p_id, granted_by=current_user, reason="creator")
    try:
        manager_value = await assign_manager(db, current_user, p_id, wanted)
    except HTTPException:
        await db.projects.delete_one({"_id": result["_id"]})
        await db.user_project_access.delete_many({"project_id": p_id})
        raise
    await db.projects.update_one({"_id": result["_id"]}, {"$set": {"project_manager_id": manager_value}})
    result["project_manager_id"] = manager_value
    await grant_client_access(db, client_account, p_id, current_user)
    await record_audit(db, "project.created", actor=current_user, resource_type="project", resource_id=p_id, project_id=p_id)

    # Trigger project update notification
    target_user = result.get("project_manager_id") or str(current_user["_id"])
    await create_notification(db, {
        "user_id": target_user,
        "title": "Project Created",
        "message": f"Project '{result.get('name', 'New Project')}' has been successfully created.",
        "type": "success",
        "category": "project_update",
        "entity_type": "project",
        "entity_id": p_id,
    })

    return Project(**(await with_manager_names(db, [result]))[0])


@router.get("/manager/{manager_id}", response_model=list[Project])
async def get_manager_projects(
    manager_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get all projects by manager"""

    if manager_id != str(current_user["_id"]) and not has_permission(current_user, "projects.read.all"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    ids = await accessible_project_ids(db, current_user)
    projects = [
        project for project in await get_projects_by_manager(db, manager_id)
        if ids is None or str(project["_id"]) in ids
    ]

    return [Project(**p) for p in await with_manager_names(db, projects)]


@router.get("", response_model=list[Project])
@router.get("/", response_model=list[Project])
async def list_projects_endpoint(
    skip: int = 0,
    limit: int = 500,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """List the projects the current user may access."""
    ensure_permission(current_user, "projects.read.all", "projects.read.assigned")
    ids = await accessible_project_ids(db, current_user)
    if ids is None:
        projects = await list_projects(db, skip, limit)
    else:
        limit = max(1, min(limit, 500))
        projects = await db.projects.find(project_scope_query(ids)).skip(skip).limit(limit).to_list(limit)

    return [Project(**p) for p in await with_manager_names(db, projects)]


@router.get("/{project_id}", response_model=Project)
async def get_project_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get project by ID"""
    await ensure_project_access(db, current_user, project_id)
    project = await get_project(db, project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return Project(**(await with_manager_names(db, [project]))[0])


@router.put("/{project_id}", response_model=Project)
async def update_project_endpoint(
    project_id: str,
    update: ProjectUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Update project"""

    ensure_permission(current_user, "projects.update.assigned")
    await ensure_project_access(db, current_user, project_id)

    project = await get_project(db, project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    update_data = update.model_dump(exclude_unset=True)
    if "project_manager_id" in update_data and update_data["project_manager_id"] != project.get("project_manager_id"):
        update_data["project_manager_id"] = await assign_manager(db, current_user, project_id, update_data["project_manager_id"], project.get("project_manager_id"))
    c_email = str(update_data.get("client_email") or update_data.get("clientEmail") or "").strip().lower()
    client_account = None
    if c_email:
        update_data["client_email"] = c_email
        update_data["clientEmail"] = c_email

        # Auto-provision Client login if it doesn't exist yet
        client_user = await db.users.find_one({"email": {"$regex": f"^{re.escape(c_email)}$", "$options": "i"}})
        if not client_user:
            client_name = update_data.get("client") or project.get("client") or c_email.split("@")[0].capitalize()
            new_client = {
                "email": c_email,
                "name": client_name,
                # No password: the client sets one through password reset.
                # (Previously every auto-created client got "Client@123".)
                "role": "client",
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            inserted = await db.users.insert_one(new_client)
            new_client["_id"] = inserted.inserted_id

            from app.modules.auth.router import notify_admin_of_new_user
            await notify_admin_of_new_user(db, new_client, "Client")
            client_user = new_client
        client_account = client_user

    result = await update_project(db, project_id, update_data)
    if c_email:
        old_email = str(project.get("client_email") or project.get("clientEmail") or "").strip().lower()
        if old_email and old_email != c_email:
            # The previous client loses the access this project's email gave them.
            previous = await db.users.find_one({"email": {"$regex": f"^{re.escape(old_email)}$", "$options": "i"}}, {"_id": 1})
            if previous:
                await db.user_project_access.update_many(
                    {"user_id": str(previous["_id"]), "project_id": str(project_id), "reason": CLIENT_ACCESS_REASON},
                    {"$set": {"active": False, "updated_at": datetime.utcnow()}},
                )
        await grant_client_access(db, client_account, str(project_id), current_user)
    p_name = result.get("name") or project.get("name") or "Project"
    target_user = result.get("project_manager_id") or str(current_user["_id"])

    await create_notification(db, {
        "user_id": target_user,
        "title": "Project Updated",
        "message": f"Project '{p_name}' has been updated.",
        "type": "info",
        "category": "project_update",
        "entity_type": "project",
        "entity_id": project_id,
    })

    return Project(**(await with_manager_names(db, [result]))[0])


@router.delete("/{project_id}")
async def delete_project_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Delete project"""

    ensure_permission(current_user, "records.delete")
    await ensure_project_access(db, current_user, project_id)

    deleted = await delete_project(db, project_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    await record_audit(db, "project.deleted", actor=current_user, resource_type="project", resource_id=project_id, project_id=project_id)
    return {"message": "Project deleted successfully"}


@router.post("/{project_id}/milestones")
async def add_milestone_endpoint(
    project_id: str,
    milestone: MilestoneBase,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Add milestone to project"""

    ensure_permission(current_user, "projects.update.assigned")
    await ensure_project_access(db, current_user, project_id)

    project = await get_project(db, project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    milestone_data = milestone.model_dump()

    result = await add_milestone(db, project_id, milestone_data)

    result["_id"] = str(result["_id"])
    target_user = project.get("project_manager_id") or str(current_user["_id"])
    await create_notification(db, {
        "user_id": target_user,
        "title": "New Milestone Added",
        "message": f"Milestone '{milestone_data.get('title', 'Milestone')}' was added to project '{project.get('name', '')}'.",
        "type": "info",
        "category": "project_update",
        "entity_type": "project",
        "entity_id": project_id,
    })

    return result

