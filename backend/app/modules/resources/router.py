from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime

from app.core.access import ensure_project_access, own_worker_ids
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.resources.db import (
    assign_resource,
    create_resource,
    delete_resource,
    get_available_resources,
    get_maintenance_history,
    get_resource,
    get_resources_by_project,
    list_resources,
    record_maintenance,
    unassign_resource,
    update_resource,
)
from app.modules.resources.models import (
    MaintenanceLog,
    MaintenanceLogCreate,
    Resource,
    ResourceCreate,
    ResourceUpdate,
)

router = APIRouter()


def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB's ObjectId _id field to a string so Pydantic models validate correctly."""
    doc = dict(doc)  # avoid mutating the original dict
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    doc.setdefault("resource_name", doc.get("name") or "Unnamed Resource")
    doc.setdefault("resource_type", doc.get("type") or "equipment")
    doc.setdefault("description", doc.get("unit") or doc.get("location") or "")
    try:
        doc["quantity"] = float(doc.get("quantity") if doc.get("quantity") is not None else 1.0)
    except (TypeError, ValueError):
        doc["quantity"] = 1.0
    doc.setdefault("unit", doc.get("unit") or "Nos")
    doc.setdefault("acquisition_cost", doc.get("cost") or 0)
    doc.setdefault("acquisition_date", doc.get("created_at") or datetime.utcnow())
    doc.setdefault("status", doc.get("status") or "available")
    doc.setdefault("assigned_to", doc.get("assignedTo"))
    doc.setdefault("assigned_project", doc.get("allocatedProjectId") or doc.get("projectId") or doc.get("assigned_project"))
    doc.setdefault("maintenance_schedule", doc.get("maintenanceSchedule"))
    doc.setdefault("created_at", datetime.utcnow())
    doc.setdefault("updated_at", datetime.utcnow())
    return doc


@router.post("", response_model=Resource)
@router.post("/", response_model=Resource)
async def create_resource_endpoint(
    resource: ResourceCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Create new resource"""
    ensure_permission(current_user, "resources.manage")

    resource_data = resource.model_dump()
    result = await create_resource(db, resource_data)
    return Resource(**serialize_doc(result))


@router.get("", response_model=list[Resource])
@router.get("/", response_model=list[Resource])
async def list_resources_endpoint(
    skip: int = 0,
    limit: int = 500,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """List all resources"""
    ensure_permission(current_user, "resources.read.assigned")
    resources = await list_resources(db, skip, limit)
    return [Resource(**serialize_doc(r)) for r in resources]


@router.get("/available", response_model=list[Resource])
async def get_available_resources_endpoint(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get all available resources"""
    ensure_permission(current_user, "resources.read.assigned")
    resources = await get_available_resources(db)
    return [Resource(**serialize_doc(r)) for r in resources]


@router.get("/project/{project_id}", response_model=list[Resource])
async def get_project_resources(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get all resources in a project"""
    ensure_permission(current_user, "resources.read.assigned")
    await ensure_project_access(db, current_user, project_id)
    resources = await get_resources_by_project(db, project_id)
    return [Resource(**serialize_doc(r)) for r in resources]


@router.get("/{resource_id}", response_model=Resource)
async def get_resource_endpoint(
    resource_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get resource by ID"""
    ensure_permission(current_user, "resources.read.assigned")
    resource = await get_resource(db, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )
    return Resource(**serialize_doc(resource))



@router.put("/{resource_id}", response_model=Resource)
async def update_resource_endpoint(
    resource_id: str,
    update: ResourceUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Update resource"""
    ensure_permission(current_user, "resources.manage")

    resource = await get_resource(db, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    update_data = update.model_dump(exclude_unset=True)
    result = await update_resource(db, resource_id, update_data)
    return Resource(**serialize_doc(result))


@router.post("/{resource_id}/assign/{worker_id}/{project_id}", response_model=Resource)
async def assign_resource_endpoint(
    resource_id: str,
    worker_id: str,
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Assign resource to worker and project"""
    ensure_permission(current_user, "resources.manage")

    resource = await get_resource(db, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    result = await assign_resource(db, resource_id, worker_id, project_id)
    return Resource(**serialize_doc(result))


@router.post("/{resource_id}/unassign", response_model=Resource)
async def unassign_resource_endpoint(
    resource_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Return resource to available"""
    ensure_permission(current_user, "resources.manage")

    resource = await get_resource(db, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    result = await unassign_resource(db, resource_id)
    return Resource(**serialize_doc(result))


@router.delete("/{resource_id}")
async def delete_resource_endpoint(
    resource_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Delete resource"""
    ensure_permission(current_user, "records.delete")

    deleted = await delete_resource(db, resource_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )
    return {"message": "Resource deleted successfully"}


@router.post("/{resource_id}/maintenance", response_model=MaintenanceLog)
async def record_maintenance_endpoint(
    resource_id: str,
    maintenance: MaintenanceLogCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Record maintenance for resource"""
    ensure_permission(current_user, "resources.manage")

    resource = await get_resource(db, resource_id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    maintenance_data = maintenance.model_dump()
    maintenance_data["resource_id"] = resource_id
    result = await record_maintenance(db, maintenance_data)
    return MaintenanceLog(**serialize_doc(result))


@router.get("/{resource_id}/maintenance", response_model=list[MaintenanceLog])
async def get_maintenance_history_endpoint(
    resource_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get maintenance history for resource"""
    ensure_permission(current_user, "resources.read.assigned")
    maintenance_logs = await get_maintenance_history(db, resource_id)
    return [MaintenanceLog(**serialize_doc(log)) for log in maintenance_logs]
