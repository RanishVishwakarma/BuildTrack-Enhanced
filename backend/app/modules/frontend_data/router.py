from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.access import accessible_project_ids, ensure_project_access, grant_project_access, visible_worker_ids
from app.core.audit import record_audit
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database

router = APIRouter()

# Fields only users with `workforce.read.sensitive` may see on worker records.
SENSITIVE_WORKER_FIELDS = ("salary", "salary_amount", "salary_type", "hourly_rate")
PROJECT_FIELDS = ("project_id", "projectId")


@dataclass(frozen=True)
class Resource:
    """How one /frontend-data collection is authorized.

    scope: "project" - the record is a project; "project_field" - the record
    carries project_id/projectId; "worker" - a worker record and "worker_field"
    - a record carrying worker_id (both limited to the workers the user may
    see); None - not project-specific (company-wide).
    """

    collection: str
    read: str
    create: str
    update: str | None
    scope: str | None = None
    delete: bool = True


RESOURCES: dict[str, Resource] = {
    "projects": Resource("projects", "projects.read.assigned", "projects.create", "projects.update.assigned", scope="project"),
    "milestones": Resource("project_milestones", "projects.read.assigned", "projects.update.assigned", "projects.update.assigned", scope="project_field"),
    "tasks": Resource("project_tasks", "tasks.read.assigned", "tasks.assign", "tasks.assign", scope="project_field"),
    "documents": Resource("project_documents", "documents.read.assigned", "documents.manage", None, scope="project_field"),
    "inventory": Resource("inventory", "inventory.read.assigned", "inventory.adjust.assigned", "inventory.adjust.assigned"),
    "workers": Resource("workers", "workforce.read.assigned", "workforce.manage", "workforce.manage", scope="worker"),
    "resources": Resource("resources", "resources.read.assigned", "resources.manage", "resources.manage"),
    "procurement": Resource("procurements", "procurement.read.assigned", "procurement.request.review", "procurement.request.review"),
    "attendance": Resource("attendance", "workforce.read.assigned", "workforce.manage", "workforce.manage", scope="worker_field"),
    "reports": Resource("reports", "reports.read.assigned", "reports.generate", None, delete=False),
}


class FrontendRecord(BaseModel):
    data: Optional[dict[str, Any]] = None

    class Config:
        extra = "allow"

    def get_data(self) -> dict[str, Any]:
        if self.data is not None and isinstance(self.data, dict):
            return self.data
        d = self.model_dump(exclude={"data"})
        return d or {}


def serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value


def id_filter(record_id: str) -> dict[str, Any]:
    try:
        return {"_id": ObjectId(record_id)}
    except InvalidId:
        return {"id": record_id}


def record_project_id(record: dict | None) -> str | None:
    for field in PROJECT_FIELDS:
        if record and record.get(field):
            return str(record[field])
    return None


def redact(resource: Resource, user: dict, doc: dict) -> dict:
    if resource.collection == "workers" and not has_permission(user, "workforce.read.sensitive"):
        return {key: value for key, value in doc.items() if key not in SENSITIVE_WORKER_FIELDS}
    return doc


async def scope_filter(db, resource: Resource, user: dict) -> dict:
    if resource.scope in {"worker", "worker_field"}:
        visible = await visible_worker_ids(db, user)
        if visible is None:
            return {}
        if resource.scope == "worker":
            return {"_id": {"$in": [ObjectId(w) for w in visible if ObjectId.is_valid(w)]}}
        return {"worker_id": {"$in": sorted(visible)}}
    ids = await accessible_project_ids(db, user)
    if resource.scope is None or ids is None:
        return {}
    values: list[Any] = list(ids)
    if resource.scope == "project":
        values += [ObjectId(pid) for pid in ids if ObjectId.is_valid(pid)]
        return {"_id": {"$in": values}}
    return {"$or": [{field: {"$in": values}} for field in PROJECT_FIELDS]}


async def load_authorized(db, resource: Resource, user: dict, record_id: str) -> dict:
    """Fetch one record the user may access, or 404."""
    query = {"$and": [id_filter(record_id), await scope_filter(db, resource, user)]}
    record = await db[resource.collection].find_one(query)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return record


def clean_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in data.items() if not str(key).startswith("$")}
    payload.pop("_id", None)
    payload.pop("id", None)
    return payload


def register(name: str, resource: Resource) -> None:
    path = f"/{name}"

    async def list_records(current_user=Depends(get_current_user), db=Depends(get_database)):
        ensure_permission(current_user, resource.read)
        docs = await db[resource.collection].find(await scope_filter(db, resource, current_user)).to_list(5000)
        return [serialize(redact(resource, current_user, doc)) for doc in docs]

    async def create_record(record: FrontendRecord, current_user=Depends(get_current_user), db=Depends(get_database)):
        ensure_permission(current_user, resource.create)
        data = clean_payload(record.get_data())
        if resource.scope == "project_field":
            await ensure_project_access(db, current_user, record_project_id(data))
        now = datetime.utcnow()
        doc = {**data, "created_at": data.get("created_at", now), "updated_at": now, "created_by": str(current_user["_id"])}
        result = await db[resource.collection].insert_one(doc)
        if resource.scope == "project":
            # The creator can always see the project they created.
            await grant_project_access(db, user_id=str(current_user["_id"]), project_id=str(result.inserted_id), granted_by=current_user, reason="creator")
        await record_audit(db, f"{resource.collection}.created", actor=current_user, resource_type=resource.collection, resource_id=str(result.inserted_id), project_id=record_project_id(doc) if resource.scope == "project_field" else (str(result.inserted_id) if resource.scope == "project" else None))
        created = await db[resource.collection].find_one({"_id": result.inserted_id})
        return serialize(redact(resource, current_user, created))

    async def update_record(record_id: str, record: FrontendRecord, current_user=Depends(get_current_user), db=Depends(get_database)):
        ensure_permission(current_user, resource.update)
        existing = await load_authorized(db, resource, current_user, record_id)
        data = clean_payload(record.get_data())
        new_project = record_project_id(data)
        if resource.scope == "project_field" and new_project and new_project != record_project_id(existing):
            # Moving a record to another project requires access to that one too.
            await ensure_project_access(db, current_user, new_project)
        data["updated_at"] = datetime.utcnow()
        await db[resource.collection].update_one({"_id": existing["_id"]}, {"$set": data})
        updated = await db[resource.collection].find_one({"_id": existing["_id"]})
        return serialize(redact(resource, current_user, updated))

    async def delete_record(record_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
        ensure_permission(current_user, "records.delete")
        existing = await load_authorized(db, resource, current_user, record_id)
        await db[resource.collection].delete_one({"_id": existing["_id"]})
        await record_audit(db, f"{resource.collection}.deleted", actor=current_user, resource_type=resource.collection, resource_id=record_id)
        return {"message": "Deleted"}

    router.add_api_route(path, list_records, methods=["GET"], name=f"list_{name}")
    router.add_api_route(path, create_record, methods=["POST"], name=f"create_{name}")
    if resource.update:
        router.add_api_route(f"{path}/{{record_id}}", update_record, methods=["PUT"], name=f"update_{name}")
    if resource.delete:
        router.add_api_route(f"{path}/{{record_id}}", delete_record, methods=["DELETE"], name=f"delete_{name}")


for _name, _resource in RESOURCES.items():
    register(_name, _resource)
