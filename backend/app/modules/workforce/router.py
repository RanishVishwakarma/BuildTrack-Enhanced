import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.access import ensure_project_access, own_worker_ids
from app.core.permissions import ensure_permission, has_permission
from app.core.audit import record_audit
from app.core.security import get_current_user, hash_password
from app.modules.auth.db import create_user as create_auth_user, get_user_by_email
from app.modules.auth.models import UserCreate
from app.db.mongodb import get_database

from app.modules.workforce.db import (
    # Workers
    create_worker,
    get_worker,
    update_worker,
    delete_worker,
    list_workers,
    get_workers_by_project,
    get_workers_by_skill,
    get_workers_by_category,
    get_available_workers,

    # Allocation
    create_workforce_allocation,
    get_workforce_allocation,
    update_workforce_allocation,
    delete_workforce_allocation,
    get_project_workforce,
    get_worker_allocations,

    # Attendance
    record_attendance,
    get_attendance,
    update_attendance,
    delete_attendance,
    list_attendance,
    get_worker_attendance,
    get_project_attendance,
    get_low_attendance_workers,
    get_workers_attendance_stats,

    # Shifts
    create_shift,
    get_shift,
    list_shifts,
    update_shift,
    delete_shift,
    assign_worker_shift,
    get_worker_shifts,
    get_project_shift_assignments,
    delete_shift_assignment,

    # Payroll
    create_payroll,
    get_payroll,
    list_payroll,
    update_payroll,
    delete_payroll,

    # Dashboard
    get_workforce_summary,
)

from app.modules.workforce.models import (
    Worker,
    WorkerCreate,
    WorkerLoginCreate,
    WorkerLoginLink,
    WorkerPasswordReset,
    WorkerUpdate,

    WorkforceAllocation,
    WorkforceAllocationCreate,
    WorkforceAllocationUpdate,

    Attendance,
    AttendanceCreate,
    AttendanceUpdate,

    Shift,
    ShiftCreate,
    ShiftUpdate,

    ShiftAssignment,
    ShiftAssignmentCreate,

    Payroll,
    PayrollCreate,
    PayrollUpdate,
)

from app.modules.notifications.db import create_notification


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter()


# ============================================================
# Helpers
# ============================================================

def is_manager_or_admin(current_user) -> bool:
    return has_permission(current_user, "workforce.manage")


def is_admin(current_user) -> bool:
    return has_permission(current_user, "records.delete")


PAY_FIELDS = ("hourly_rate", "salary_amount", "salary_type", "salary")


def redact_pay(doc: dict, current_user) -> dict:
    """Hide wage fields from users without workforce.read.sensitive."""
    if has_permission(current_user, "workforce.read.sensitive"):
        return doc
    return {**doc, **{field: None for field in PAY_FIELDS if field in doc}}


async def guard_crew_read(db, current_user, project_id=None) -> None:
    ensure_permission(current_user, "workforce.read.assigned")
    if project_id:
        await ensure_project_access(db, current_user, project_id)


async def guard_worker_read(db, current_user, worker_id=None, project_id=None) -> None:
    if has_permission(current_user, "workforce.read.assigned"):
        if project_id:
            await ensure_project_access(db, current_user, project_id)
        return
    if worker_id and str(worker_id) in await own_worker_ids(db, current_user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


async def guard_pay_read(db, current_user, worker_id=None, project_id=None) -> None:
    if has_permission(current_user, "workforce.read.sensitive"):
        if project_id:
            await ensure_project_access(db, current_user, project_id)
        return
    if worker_id and str(worker_id) in await own_worker_ids(db, current_user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def serialize_doc(doc: dict) -> dict:
    """
    Convert MongoDB ObjectId to string.
    Also ensures timestamps exist.
    """
    if not doc:
        return doc

    doc = dict(doc)

    if "_id" in doc:
        doc["_id"] = str(doc["_id"])

    doc.setdefault("created_at", datetime.utcnow())
    doc.setdefault("updated_at", datetime.utcnow())

    return doc


def serialize_worker_doc(doc: dict, attendance_stats: dict = None) -> dict:
    """
    Convert old/legacy worker documents into the current Worker model.
    """
    doc = serialize_doc(doc)

    doc.setdefault(
        "worker_code",
        doc.get("worker_code") or f"WRK-{str(doc.get('_id', ''))[-4:].upper()}",
    )

    # Legacy name support
    name_parts = str(
        doc.get("name") or "Worker"
    ).split()

    doc.setdefault(
        "first_name",
        name_parts[0] if name_parts else "Worker",
    )

    doc.setdefault(
        "last_name",
        " ".join(name_parts[1:])
        if len(name_parts) > 1
        else "-",
    )

    doc.setdefault(
        "email",
        doc.get("email")
        or f"{doc['_id']}@buildtrack.local",
    )

    doc.setdefault(
        "phone",
        doc.get("phone") or doc.get("contact"),
    )

    doc.setdefault(
        "category",
        doc.get("category") or "SKILLED_WORKER",
    )

    doc.setdefault(
        "skill_type",
        doc.get("skillType")
        or doc.get("role")
        or "General",
    )

    doc.setdefault(
        "designation",
        doc.get("designation")
        or doc.get("role"),
    )

    doc.setdefault(
        "experience_years",
        doc.get("experience_years")
        or doc.get("experience")
        or 0,
    )

    doc.setdefault(
        "employment_type",
        doc.get("employment_type")
        or "FULL_TIME",
    )

    doc.setdefault(
        "salary_type",
        doc.get("salary_type")
        or "HOURLY",
    )

    doc.setdefault(
        "hourly_rate",
        doc.get("hourly_rate")
        or doc.get("hourlyRate")
        or doc.get("salary")
        or 0,
    )

    doc.setdefault(
        "salary_amount",
        doc.get("salary_amount")
        or doc.get("salary"),
    )

    doc.setdefault(
        "project_id",
        doc.get("project_id")
        or doc.get("assignedProjectId")
        or doc.get("projectId"),
    )

    doc.setdefault(
        "status",
        doc.get("status") or "available",
    )

    if attendance_stats is not None:
        wid = str(doc.get("_id", ""))
        stat = attendance_stats.get(wid)
        if stat:
            doc["attendance_pct"] = float(stat.get("percentage", 0.0))
            if stat.get("is_inactive"):
                doc["status"] = "inactive"
        else:
            doc.setdefault("attendance_pct", 0.0)
    else:
        doc.setdefault("attendance_pct", float(doc.get("attendance_pct") or 0.0))

    return doc


def serialize_attendance_doc(doc: dict) -> dict:
    """
    Convert old/legacy attendance documents into current schema.
    """
    doc = serialize_doc(doc)

    doc.setdefault(
        "worker_id",
        doc.get("workerId")
        or doc.get("worker_id")
        or "",
    )

    doc.setdefault(
        "project_id",
        doc.get("projectId")
        or doc.get("project_id"),
    )

    date_value = doc.get("date") or datetime.utcnow()

    doc.setdefault(
        "date",
        date_value,
    )

    doc.setdefault(
        "check_in_time",
        normalize_attendance_time(
            doc.get("checkIn")
            or doc.get("check_in_time"),
            date_value,
        ),
    )

    doc.setdefault(
        "check_out_time",
        normalize_attendance_time(
            doc.get("checkOut")
            or doc.get("check_out_time"),
            date_value,
        ),
    )

    doc.setdefault(
        "status",
        doc.get("status") or "absent",
    )

    doc.setdefault(
        "hours_worked",
        doc.get("hoursWorked")
        or doc.get("hours_worked"),
    )

    doc.setdefault(
        "overtime_hours",
        doc.get("overtime_hours")
        or doc.get("overtimeHours")
        or 0,
    )

    doc.setdefault(
        "remarks",
        doc.get("remarks"),
    )

    return doc


def normalize_attendance_time(
    value,
    date_value,
):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value)

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    date_text = (
        str(date_value)
        .split("T")[0]
        .split(" ")[0]
    )

    try:
        return datetime.fromisoformat(
            f"{date_text}T{text}"
        )
    except ValueError:
        return None


def serialize_allocation_doc(doc: dict) -> dict:
    return serialize_doc(doc)


def serialize_shift_doc(doc: dict) -> dict:
    return serialize_doc(doc)


def serialize_shift_assignment_doc(doc: dict) -> dict:
    return serialize_doc(doc)


def serialize_payroll_doc(doc: dict) -> dict:
    return serialize_doc(doc)


# ============================================================
# WORKER REGISTRATION
# ============================================================

@router.post(
    "/workers",
    response_model=Worker,
)
async def create_worker_endpoint(
    worker: WorkerCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Register a new workforce member.
    """
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or manager can create workers",
        )

    worker_data = worker.model_dump()

    result = await create_worker(
        db,
        worker_data,
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to create worker",
        )

    await create_notification(
        db,
        {
            "user_id": str(current_user["_id"]),
            "title": "New Worker Registered",
            "message": (
                f"Worker "
                f"'{result.get('first_name', 'Worker')} "
                f"{result.get('last_name', '')}' "
                f"has been registered."
            ),
            "type": "info",
            "category": "workforce",
            "entity_type": "worker",
            "entity_id": str(result["_id"]),
        },
    )

    return Worker(
        **redact_pay(serialize_worker_doc(result), current_user)
    )


@router.get(
    "/workers",
    response_model=list[Worker],
)
async def list_workers_endpoint(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    skill_type: Optional[str] = None,
    project_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    List workers with optional filters.
    """
    await guard_crew_read(db, current_user, project_id)
    if category:
        workers = await get_workers_by_category(
            db,
            category,
        )
    elif skill_type:
        workers = await get_workers_by_skill(
            db,
            skill_type,
        )
    elif project_id:
        workers = await get_workers_by_project(
            db,
            project_id,
        )
    else:
        workers = await list_workers(
            db,
            skip,
            limit,
        )

    if status_filter:
        workers = [
            worker
            for worker in workers
            if worker.get("status") == status_filter
        ]

    stats = await get_workers_attendance_stats(db, days=30)
    logins = await worker_logins(db, [worker["_id"] for worker in workers]) if has_permission(current_user, "workforce.login.manage") else {}

    return [
        Worker(**redact_pay(serialize_worker_doc(worker, stats), current_user), login_email=(logins.get(str(worker["_id"])) or {}).get("email"))
        for worker in workers
    ]


# Worker logins. The link is the user's `worker_id`, set only here; access
# to a worker's tasks, attendance and pay follows it (app/core/access.py).
LINKABLE_ROLES = {"worker", "contractor"}


async def worker_logins(db, worker_ids: list) -> dict:
    ids = [str(worker_id) for worker_id in worker_ids]
    users = await db.users.find({"worker_id": {"$in": ids}}, {"email": 1, "worker_id": 1, "role": 1}).to_list(len(ids) * 2 + 1)
    return {str(user["worker_id"]): user for user in users}


async def worker_for_login(db, worker_id: str) -> dict:
    worker = await get_worker(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    if (await worker_logins(db, [worker_id])).get(str(worker_id)):
        raise HTTPException(status_code=409, detail="This worker already has a login")
    return worker


@router.post("/workers/{worker_id}/login", status_code=status.HTTP_201_CREATED)
async def create_worker_login(worker_id: str, payload: WorkerLoginCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    """Create a worker-role login for this worker record."""
    ensure_permission(current_user, "workforce.login.manage")
    worker = await worker_for_login(db, worker_id)
    email = (payload.email or worker.get("email") or "").strip()
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email for the login")
    if await get_user_by_email(db, email):
        raise HTTPException(status_code=409, detail="This email already has an account. Use Link existing account instead.")
    user = await create_auth_user(db, UserCreate(
        email=email,
        full_name=f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip() or "Worker",
        role="worker",
        status="active",
        worker_id=str(worker["_id"]),
        password=payload.password,
    ))
    await record_audit(db, "worker.login.created", actor=current_user, resource_type="worker", resource_id=worker_id, details={"email": email})
    return {"message": f"Login created. Login email: {email}", "login_email": email, "user_id": str(user["_id"])}


@router.post("/workers/{worker_id}/login/link")
async def link_worker_login(worker_id: str, payload: WorkerLoginLink, current_user=Depends(get_current_user), db=Depends(get_database)):
    """Attach an account the worker registered themselves."""
    ensure_permission(current_user, "workforce.login.manage")
    await worker_for_login(db, worker_id)
    user = await get_user_by_email(db, payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="No account with this email")
    if str(user.get("role") or "").lower() not in LINKABLE_ROLES:
        raise HTTPException(status_code=400, detail="Only worker or contractor accounts can be linked to a worker")
    if user.get("worker_id") and str(user["worker_id"]) != str(worker_id):
        raise HTTPException(status_code=409, detail="This account is already linked to another worker")
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"worker_id": str(worker_id), "updated_at": datetime.utcnow()}})
    await record_audit(db, "worker.login.linked", actor=current_user, resource_type="worker", resource_id=worker_id, details={"email": user["email"]})
    return {"message": f"Linked {user['email']} to this worker.", "login_email": user["email"]}


@router.delete("/workers/{worker_id}/login")
async def unlink_worker_login(worker_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    """Detach the login from this worker. The account itself is kept."""
    ensure_permission(current_user, "workforce.login.manage")
    login = (await worker_logins(db, [worker_id])).get(str(worker_id))
    if not login:
        raise HTTPException(status_code=404, detail="This worker has no login")
    await db.users.update_one({"_id": login["_id"]}, {"$unset": {"worker_id": ""}, "$set": {"updated_at": datetime.utcnow()}})
    await record_audit(db, "worker.login.unlinked", actor=current_user, resource_type="worker", resource_id=worker_id, details={"email": login["email"]})
    return {"message": f"{login['email']} is no longer linked to this worker."}


@router.put("/workers/{worker_id}/login/password")
async def reset_worker_password(worker_id: str, payload: WorkerPasswordReset, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "workforce.login.manage")
    login = (await worker_logins(db, [worker_id])).get(str(worker_id))
    if not login:
        raise HTTPException(status_code=404, detail="This worker has no login")
    if str(login.get("role") or "").lower() not in LINKABLE_ROLES:
        raise HTTPException(status_code=400, detail="Only worker or contractor passwords can be reset here")
    await db.users.update_one({"_id": login["_id"]}, {"$set": {"password_hash": hash_password(payload.password), "updated_at": datetime.utcnow()}})
    await record_audit(db, "worker.login.password_reset", actor=current_user, resource_type="worker", resource_id=worker_id, details={"email": login["email"]})
    return {"message": f"Password updated for {login['email']}."}


@router.get(
    "/workers/available",
    response_model=list[Worker],
)
async def get_available_workers_endpoint(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Get all currently available workers.
    """
    await guard_crew_read(db, current_user)
    workers = await get_available_workers(db)
    stats = await get_workers_attendance_stats(db, days=30)

    return [
        Worker(**redact_pay(serialize_worker_doc(worker, stats), current_user))
        for worker in workers
    ]


@router.get(
    "/workers/project/{project_id}",
    response_model=list[Worker],
)
async def get_project_workers(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Get all workers associated with a project.
    """
    await guard_crew_read(db, current_user, project_id)
    workers = await get_workers_by_project(
        db,
        project_id,
    )
    stats = await get_workers_attendance_stats(db, days=30)

    return [
        Worker(**redact_pay(serialize_worker_doc(worker, stats), current_user))
        for worker in workers
    ]


@router.get(
    "/workers/category/{category}",
    response_model=list[Worker],
)
async def get_workers_by_category_endpoint(
    category: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Get workers by workforce category.
    """
    await guard_crew_read(db, current_user)
    workers = await get_workers_by_category(
        db,
        category,
    )
    stats = await get_workers_attendance_stats(db, days=30)

    return [
        Worker(**redact_pay(serialize_worker_doc(worker, stats), current_user))
        for worker in workers
    ]


@router.get(
    "/workers/skill/{skill_type}",
    response_model=list[Worker],
)
async def get_workers_by_skill_type(
    skill_type: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Get workers with a specific skill.
    """
    await guard_crew_read(db, current_user)
    workers = await get_workers_by_skill(
        db,
        skill_type,
    )
    stats = await get_workers_attendance_stats(db, days=30)

    return [
        Worker(**redact_pay(serialize_worker_doc(worker, stats), current_user))
        for worker in workers
    ]


@router.get(
    "/workers/{worker_id}",
    response_model=Worker,
)
async def get_worker_endpoint(
    worker_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_worker_read(db, current_user, worker_id)
    worker = await get_worker(
        db,
        worker_id,
    )

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    stats = await get_workers_attendance_stats(db, days=30)

    return Worker(
        **redact_pay(serialize_worker_doc(worker, stats), current_user)
    )


@router.put(
    "/workers/{worker_id}",
    response_model=Worker,
)
async def update_worker_endpoint(
    worker_id: str,
    update: WorkerUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can update workers",
        )

    existing = await get_worker(
        db,
        worker_id,
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    update_data = update.model_dump(
        exclude_unset=True,
        exclude_none=True
    )
    if "assigned_project_id" in update_data:
        update_data["project_id"] = update_data.pop(
            "assigned_project_id"
        )

    updated = await update_worker(
        db,
        worker_id,
        update_data
    )

    return Worker(
        **redact_pay(serialize_worker_doc(updated), current_user)
    )


@router.delete(
    "/workers/{worker_id}"
)
async def delete_worker_endpoint(
    worker_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin can delete workers",
        )

    deleted = await delete_worker(
        db,
        worker_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    return {
        "message": "Worker deleted successfully"
    }


# ============================================================
# WORKFORCE ALLOCATION
# ============================================================

@router.post(
    "/allocations",
    response_model=WorkforceAllocation,
)
async def create_allocation_endpoint(
    allocation: WorkforceAllocationCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Assign a worker to a project.
    """
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can allocate workers",
        )

    worker = await get_worker(
        db,
        allocation.worker_id,
    )

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    allocation_data = allocation.model_dump()

    result = await create_workforce_allocation(
        db,
        allocation_data,
    )

    await create_notification(
        db,
        {
            "user_id": str(current_user["_id"]),
            "title": "Workforce Allocation",
            "message": (
                f"Worker '{allocation.worker_id}' "
                f"was assigned to project "
                f"'{allocation.project_id}'."
            ),
            "type": "info",
            "category": "workforce",
            "entity_type": "workforce_allocation",
            "entity_id": str(result["_id"]),
        },
    )

    return WorkforceAllocation(
        **serialize_allocation_doc(result)
    )


@router.get(
    "/allocations/{allocation_id}",
    response_model=WorkforceAllocation,
)
async def get_allocation_endpoint(
    allocation_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_crew_read(db, current_user)
    allocation = await get_workforce_allocation(
        db,
        allocation_id,
    )

    if not allocation:
        raise HTTPException(
            status_code=404,
            detail="Workforce allocation not found",
        )

    return WorkforceAllocation(
        **serialize_allocation_doc(allocation)
    )


@router.put(
    "/allocations/{allocation_id}",
    response_model=WorkforceAllocation,
)
async def update_allocation_endpoint(
    allocation_id: str,
    update: WorkforceAllocationUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can update allocations",
        )

    existing = await get_workforce_allocation(
        db,
        allocation_id,
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Workforce allocation not found",
        )

    result = await update_workforce_allocation(
        db,
        allocation_id,
        update.model_dump(
            exclude_unset=True
        ),
    )

    return WorkforceAllocation(
        **serialize_allocation_doc(result)
    )


@router.delete(
    "/allocations/{allocation_id}"
)
async def delete_allocation_endpoint(
    allocation_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can remove allocations",
        )

    deleted = await delete_workforce_allocation(
        db,
        allocation_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Workforce allocation not found",
        )

    return {
        "message": "Workforce allocation removed successfully"
    }


@router.get(
    "/allocations/project/{project_id}",
    response_model=list[WorkforceAllocation],
)
async def get_project_workforce_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_crew_read(db, current_user, project_id)
    allocations = await get_project_workforce(
        db,
        project_id,
    )

    return [
        WorkforceAllocation(
            **serialize_allocation_doc(item)
        )
        for item in allocations
    ]


@router.get(
    "/allocations/worker/{worker_id}",
    response_model=list[WorkforceAllocation],
)
async def get_worker_allocations_endpoint(
    worker_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_worker_read(db, current_user, worker_id)
    allocations = await get_worker_allocations(
        db,
        worker_id,
    )

    return [
        WorkforceAllocation(
            **serialize_allocation_doc(item)
        )
        for item in allocations
    ]


# ============================================================
# ATTENDANCE
# ============================================================

@router.post(
    "/attendance",
    response_model=Attendance,
)
async def record_attendance_endpoint(
    attendance: AttendanceCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can record attendance",
        )

    worker = await get_worker(
        db,
        attendance.worker_id,
    )

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    result = await record_attendance(
        db,
        attendance.model_dump(),
    )

    worker_name = f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip() or worker.get("name") or "Worker"
    status_label = "Present" if str(result.get("status") or "").lower() == "present" else "Absent"
    is_present = status_label == "Present"

    await create_notification(
        db,
        {
            "user_id": str(current_user["_id"]),
            "title": f"Attendance Marked: {worker_name}",
            "message": f"Worker {worker_name} has been marked {status_label}.",
            "type": "success" if is_present else "warning",
            "category": "attendance_alert",
            "entity_type": "attendance",
            "entity_id": str(result["_id"]),
        },
    )

    return Attendance(
        **serialize_attendance_doc(result)
    )


@router.get(
    "/attendance",
    response_model=list[Attendance],
)
async def list_attendance_endpoint(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_crew_read(db, current_user)
    records = await list_attendance(
        db,
        skip,
        limit,
    )

    return [
        Attendance(
            **serialize_attendance_doc(record)
        )
        for record in records
    ]


@router.get(
    "/attendance/project/{project_id}",
    response_model=list[Attendance],
)
async def get_project_attendance_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_crew_read(db, current_user, project_id)
    records = await get_project_attendance(
        db,
        project_id,
    )

    return [
        Attendance(
            **serialize_attendance_doc(record)
        )
        for record in records
    ]


@router.get(
    "/attendance/worker/{worker_id}",
    response_model=list[Attendance],
)
async def get_worker_attendance_endpoint(
    worker_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_worker_read(db, current_user, worker_id)
    records = await get_worker_attendance(
        db,
        worker_id,
        start_date,
        end_date,
    )

    return [
        Attendance(
            **serialize_attendance_doc(record)
        )
        for record in records
    ]


@router.get(
    "/attendance/low-attendance"
)
async def get_low_attendance_workers_endpoint(
    project_id: Optional[str] = None,
    days: int = 30,
    threshold: float = 75.0,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Flags workers whose attendance percentage over the last `days`
    days is below `threshold`. Manager/admin only.
    """
    await guard_crew_read(db, current_user, project_id)
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can view low-attendance workers",
        )

    return await get_low_attendance_workers(
        db,
        project_id,
        days,
        threshold,
    )


@router.post(
    "/attendance/notify-low-attendance/{worker_id}"
)
async def notify_low_attendance_endpoint(
    worker_id: str,
    days: int = 30,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Manually sends a low-attendance warning notification to the
    worker's linked user account (found via User.worker_id).
    """
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can send attendance notifications",
        )

    worker = await get_worker(
        db,
        worker_id,
    )

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    linked_user = await db.users.find_one(
        {"worker_id": worker_id}
    )

    if not linked_user:
        raise HTTPException(
            status_code=404,
            detail=(
                "No linked user account for this worker — "
                "they haven't logged in yet, so they can't "
                "receive an in-app notification"
            ),
        )

    worker_name = f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip()

    notif = await create_notification(
        db,
        {
            "user_id": str(linked_user["_id"]),
            "title": "Low Attendance Warning",
            "message": (
                f"Your attendance over the last {days} days is "
                f"below the required threshold. Please speak "
                f"with your project manager."
            ),
            "type": "warning",
            "category": "attendance_alert",
            "entity_type": "worker",
            "entity_id": worker_id,
        },
    )

    return {
        "message": f"Notification sent to {worker_name}",
        "notification_id": str(notif["_id"]),
    }


@router.put(
    "/attendance/{attendance_id}",
    response_model=Attendance,
)
async def update_attendance_endpoint(
    attendance_id: str,
    attendance: AttendanceUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can update attendance",
        )

    existing = await get_attendance(
        db,
        attendance_id,
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found",
        )

    result = await update_attendance(
        db,
        attendance_id,
        attendance.model_dump(
            exclude_unset=True
        ),
    )

    worker = await get_worker(db, str(existing.get("worker_id", "")))
    worker_name = (
        f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip()
        if worker else "Worker"
    ) or "Worker"
    status_label = "Present" if str(result.get("status") or "").lower() == "present" else "Absent"
    is_present = status_label == "Present"

    await create_notification(
        db,
        {
            "user_id": str(current_user["_id"]),
            "title": f"Attendance Update: {worker_name}",
            "message": f"Worker {worker_name} has been marked {status_label}.",
            "type": "success" if is_present else "warning",
            "category": "attendance_alert",
            "entity_type": "attendance",
            "entity_id": str(result["_id"]),
        },
    )

    return Attendance(
        **serialize_attendance_doc(result)
    )


@router.delete(
    "/attendance/{attendance_id}"
)
async def delete_attendance_endpoint(
    attendance_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin can delete attendance records",
        )

    deleted = await delete_attendance(
        db,
        attendance_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found",
        )

    return {
        "message": "Attendance record deleted successfully"
    }


# ============================================================
# SHIFT SCHEDULING
# ============================================================

@router.post(
    "/shifts",
    response_model=Shift,
)
async def create_shift_endpoint(
    shift: ShiftCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can create shifts",
        )

    result = await create_shift(
        db,
        shift.model_dump(),
    )

    return Shift(
        **serialize_shift_doc(result)
    )


@router.get(
    "/shifts",
    response_model=list[Shift],
)
async def list_shifts_endpoint(
    project_id: Optional[str] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_crew_read(db, current_user, project_id)
    shifts = await list_shifts(
        db,
        project_id,
    )

    return [
        Shift(
            **serialize_shift_doc(shift)
        )
        for shift in shifts
    ]


@router.get(
    "/shifts/{shift_id}",
    response_model=Shift,
)
async def get_shift_endpoint(
    shift_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_crew_read(db, current_user)
    shift = await get_shift(
        db,
        shift_id,
    )

    if not shift:
        raise HTTPException(
            status_code=404,
            detail="Shift not found",
        )

    return Shift(
        **serialize_shift_doc(shift)
    )


@router.put(
    "/shifts/{shift_id}",
    response_model=Shift,
)
async def update_shift_endpoint(
    shift_id: str,
    update: ShiftUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can update shifts",
        )

    existing = await get_shift(
        db,
        shift_id,
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Shift not found",
        )

    result = await update_shift(
        db,
        shift_id,
        update.model_dump(
            exclude_unset=True
        ),
    )

    return Shift(
        **serialize_shift_doc(result)
    )


@router.delete(
    "/shifts/{shift_id}"
)
async def delete_shift_endpoint(
    shift_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin can delete shifts",
        )

    deleted = await delete_shift(
        db,
        shift_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Shift not found",
        )

    return {
        "message": "Shift deleted successfully"
    }


# ============================================================
# SHIFT ASSIGNMENT
# ============================================================

@router.post(
    "/shift-assignments",
    response_model=ShiftAssignment,
)
async def assign_worker_shift_endpoint(
    assignment: ShiftAssignmentCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can assign shifts",
        )

    worker = await get_worker(
        db,
        assignment.worker_id,
    )

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    shift = await get_shift(
        db,
        assignment.shift_id,
    )

    if not shift:
        raise HTTPException(
            status_code=404,
            detail="Shift not found",
        )

    data = assignment.model_dump()

    result = await assign_worker_shift(
        db,
        data,
    )

    return ShiftAssignment(
        **serialize_shift_assignment_doc(result)
    )


@router.get(
    "/shift-assignments",
    response_model=list[ShiftAssignment],
)
async def list_shift_assignments_endpoint(
    worker_id: Optional[str] = None,
    project_id: Optional[str] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Get shift assignments.

    Optional filters:
    - worker_id
    - project_id
    """
    await guard_worker_read(db, current_user, worker_id, project_id=project_id)

    if worker_id:
        assignments = await get_worker_shifts(
            db,
            worker_id,
        )

    elif project_id:
        assignments = await get_project_shift_assignments(
            db,
            project_id,
        )

    else:
        assignments = await db.shift_assignments.find(
            {}
        ).sort(
            "created_at",
            -1,
        ).to_list(
            length=None,
        )

    return [
        ShiftAssignment(
            **serialize_shift_assignment_doc(item)
        )
        for item in assignments
    ]


@router.get(
    "/shift-assignments/worker/{worker_id}",
    response_model=list[ShiftAssignment],
)
async def get_worker_shifts_endpoint(
    worker_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_worker_read(db, current_user, worker_id)
    assignments = await get_worker_shifts(
        db,
        worker_id,
    )

    return [
        ShiftAssignment(
            **serialize_shift_assignment_doc(item)
        )
        for item in assignments
    ]


@router.get(
    "/shift-assignments/project/{project_id}",
    response_model=list[ShiftAssignment],
)
async def get_project_shift_assignments_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_crew_read(db, current_user, project_id)
    assignments = await get_project_shift_assignments(
        db,
        project_id,
    )

    return [
        ShiftAssignment(
            **serialize_shift_assignment_doc(item)
        )
        for item in assignments
    ]


@router.delete(
    "/shift-assignments/{assignment_id}"
)
async def delete_shift_assignment_endpoint(
    assignment_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can remove shift assignments",
        )

    deleted = await delete_shift_assignment(
        db,
        assignment_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Shift assignment not found",
        )

    return {
        "message": "Shift assignment removed successfully"
    }


# ============================================================
# PAYROLL MONITORING
# ============================================================

@router.post(
    "/payroll",
    response_model=Payroll,
)
async def create_payroll_endpoint(
    payroll: PayrollCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can create payroll",
        )

    worker = await get_worker(
        db,
        payroll.worker_id,
    )

    if not worker:
        raise HTTPException(
            status_code=404,
            detail="Worker not found",
        )

    payroll_data = payroll.model_dump()

    # Automatically calculate net amount
    basic = float(
        payroll_data.get("basic_amount") or 0
    )

    overtime_amount = float(
        payroll_data.get("overtime_amount") or 0
    )

    deductions = float(
        payroll_data.get("deductions") or 0
    )

    bonus = float(
        payroll_data.get("bonus") or 0
    )

    payroll_data["net_amount"] = (
        basic
        + overtime_amount
        + bonus
        - deductions
    )

    result = await create_payroll(
        db,
        payroll_data,
    )

    return Payroll(
        **serialize_payroll_doc(result)
    )


@router.get(
    "/payroll",
    response_model=list[Payroll],
)
async def list_payroll_endpoint(
    project_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    await guard_pay_read(db, current_user, worker_id, project_id=project_id)
    payroll_records = await list_payroll(
        db,
        project_id,
        worker_id,
    )

    return [
        Payroll(
            **serialize_payroll_doc(record)
        )
        for record in payroll_records
    ]


@router.get(
    "/payroll/{payroll_id}",
    response_model=Payroll,
)
async def get_payroll_endpoint(
    payroll_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    payroll = await get_payroll(
        db,
        payroll_id,
    )

    if not payroll:
        raise HTTPException(
            status_code=404,
            detail="Payroll record not found",
        )
    await guard_pay_read(db, current_user, payroll.get("worker_id"))

    return Payroll(
        **serialize_payroll_doc(payroll)
    )


@router.put(
    "/payroll/{payroll_id}",
    response_model=Payroll,
)
async def update_payroll_endpoint(
    payroll_id: str,
    update: PayrollUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_manager_or_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin or manager can update payroll",
        )

    existing = await get_payroll(
        db,
        payroll_id,
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Payroll record not found",
        )

    update_data = update.model_dump(
        exclude_unset=True
    )

    # Recalculate net amount when financial values change.
    basic = float(
        update_data.get(
            "basic_amount",
            existing.get("basic_amount", 0),
        )
        or 0
    )

    overtime_amount = float(
        update_data.get(
            "overtime_amount",
            existing.get("overtime_amount", 0),
        )
        or 0
    )

    deductions = float(
        update_data.get(
            "deductions",
            existing.get("deductions", 0),
        )
        or 0
    )

    bonus = float(
        update_data.get(
            "bonus",
            existing.get("bonus", 0),
        )
        or 0
    )

    update_data["net_amount"] = (
        basic
        + overtime_amount
        + bonus
        - deductions
    )

    result = await update_payroll(
        db,
        payroll_id,
        update_data,
    )

    return Payroll(
        **serialize_payroll_doc(result)
    )


@router.delete(
    "/payroll/{payroll_id}"
)
async def delete_payroll_endpoint(
    payroll_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    if not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only admin can delete payroll records",
        )

    deleted = await delete_payroll(
        db,
        payroll_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Payroll record not found",
        )

    return {
        "message": "Payroll record deleted successfully"
    }


# ============================================================
# WORKFORCE DASHBOARD
# ============================================================

@router.get(
    "/dashboard/summary"
)
async def workforce_dashboard_summary(
    project_id: Optional[str] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Workforce overview for dashboard.
    """
    await guard_crew_read(db, current_user, project_id)
    return await get_workforce_summary(
        db,
        project_id,
    )