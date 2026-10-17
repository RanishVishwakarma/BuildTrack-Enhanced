from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.access import can_access_project, ensure_project_access, own_worker_ids
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.auth.db import get_user_by_email
from app.modules.notifications.db import create_notification
from app.modules.tasks.db import (
    create_task,
    delete_task,
    get_task,
    list_tasks_for_project,
    list_tasks_for_worker,
    update_task,
)
from app.modules.tasks.models import Task, TaskCreate, TaskUpdate
from app.modules.workforce.db import get_worker

router = APIRouter()


async def can_read_task(db, current_user, task: dict) -> bool:
    """Project members with tasks.read.assigned, or the assigned worker."""
    if has_permission(current_user, "tasks.read.assigned") and await can_access_project(db, current_user, task.get("project_id")):
        return True
    worker_id = str(task.get("assigned_worker_id") or "")
    return bool(worker_id) and worker_id in await own_worker_ids(db, current_user)


def serialize_task(doc: dict) -> dict:
    task = dict(doc)
    task["_id"] = str(task["_id"])
    return task


async def notify_assigned_worker(db, worker_id: str, project_id: str, task_id: str, title: str):
    """
    Best-effort: if the assigned worker has a matching login account
    (by email — same linkage used at login, see auth/router.py),
    send them a task-assignment notification.

    entity_type="task" already routes to /workers in
    topbar.component.ts's onNotificationClick, so no frontend change
    is needed for this to show up correctly.
    """
    worker = await get_worker(db, worker_id)
    if not worker or not worker.get("email"):
        return

    user = await get_user_by_email(db, worker["email"])
    if not user:
        return

    await create_notification(db, {
        "user_id": str(user["_id"]),
        "title": "New Task Assigned",
        "message": f"You've been assigned a new task: '{title}'.",
        "type": "info",
        "category": "task_assignment",
        "entity_type": "task",
        "entity_id": task_id,
    })


@router.post("/", response_model=Task)
async def create_task_endpoint(
    task: TaskCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Create a task on a project, optionally assigned to a worker."""
    ensure_permission(current_user, "tasks.assign")
    await ensure_project_access(db, current_user, task.project_id)

    task_data = task.model_dump()
    result = await create_task(db, task_data)
    task_id = str(result["_id"])

    if result.get("assigned_worker_id"):
        await notify_assigned_worker(
            db,
            result["assigned_worker_id"],
            result["project_id"],
            task_id,
            result.get("title", "Task"),
        )

    return Task(**serialize_task(result))


@router.get("/project/{project_id}", response_model=list[Task])
async def get_project_tasks(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """List all tasks for a project."""
    ensure_permission(current_user, "tasks.read.assigned")
    await ensure_project_access(db, current_user, project_id)
    tasks = await list_tasks_for_project(db, project_id)
    return [Task(**serialize_task(t)) for t in tasks]


@router.get("/worker/{worker_id}", response_model=list[Task])
async def get_worker_tasks(
    worker_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """List all tasks assigned to a specific worker (for a worker's 'My Tasks' view)."""
    if not has_permission(current_user, "tasks.read.assigned") and worker_id not in await own_worker_ids(db, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    tasks = await list_tasks_for_worker(db, worker_id)
    return [Task(**serialize_task(t)) for t in tasks]


@router.get("/{task_id}", response_model=Task)
async def get_task_endpoint(
    task_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    task = await get_task(db, task_id)
    if not task or not await can_read_task(db, current_user, task):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return Task(**serialize_task(task))


@router.put("/{task_id}", response_model=Task)
async def update_task_endpoint(
    task_id: str,
    update: TaskUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Update a task.

    Project members with tasks.update.assigned may edit any field. The
    assigned worker (tasks.update.own) may change only the status.
    """
    existing = await get_task(db, task_id)
    if not existing or not await can_read_task(db, current_user, existing):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    update_data = update.model_dump(exclude_unset=True)
    manages_project = has_permission(current_user, "tasks.update.assigned") and await can_access_project(
        db, current_user, existing.get("project_id")
    )
    if not manages_project:
        own_task = str(existing.get("assigned_worker_id") or "") in await own_worker_ids(db, current_user)
        if not (own_task and has_permission(current_user, "tasks.update.own")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        if set(update_data) - {"status"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update the status of your own task")
    result = await update_task(db, task_id, update_data)

    # Notify only if the assignment actually changed to someone new.
    new_worker_id = result.get("assigned_worker_id")
    if new_worker_id and new_worker_id != existing.get("assigned_worker_id"):
        await notify_assigned_worker(
            db,
            new_worker_id,
            result["project_id"],
            task_id,
            result.get("title", "Task"),
        )

    return Task(**serialize_task(result))


@router.delete("/{task_id}")
async def delete_task_endpoint(
    task_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "records.delete")

    deleted = await delete_task(db, task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return {"message": "Task deleted successfully"}