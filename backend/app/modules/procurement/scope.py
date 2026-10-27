"""Project scoping for procurement.

A user without organisation-wide project access (projects.read.all) sees
only procurement on the projects they are assigned to:

* material requests and purchase orders of those projects (by project_id,
  or by project name on older records saved without an id);
* deliveries, invoices and payments of those purchase orders;
* vendors used on those projects, plus vendors no project has used yet, so
  a new supplier can still be chosen.

Lists pass `scope_filter` to their query. Single records are checked by
`enforce_record_scope`, a router dependency that reads ids from the URL
(`{po_id}`, `{invoice_id}`, ...), so every view, edit, PDF and action on a
record of another project answers 404. Vendor-portal routes keep their own
vendor_id checks and are not affected.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.core.access import accessible_project_ids
from app.core.security import get_current_user
from app.db.mongodb import get_database

SCOPED = {"material_requests", "purchase_orders", "deliveries", "invoices", "payments", "vendors"}
PATH_COLLECTIONS = {"request_id": "material_requests", "po_id": "purchase_orders", "delivery_id": "deliveries",
                    "invoice_id": "invoices", "payment_id": "payments", "vendor_id": "vendors"}


async def _project_match(db, project_ids: set[str]) -> dict:
    names = [p["name"] async for p in db.projects.find({"_id": {"$in": [ObjectId(i) for i in project_ids if ObjectId.is_valid(i)]}}, {"name": 1}) if p.get("name")]
    return {"$or": [{"project_id": {"$in": sorted(project_ids)}},
                    {"project_id": {"$in": [None, ""]}, "project": {"$in": names}}]}


async def scope_filter(db, user: dict, collection: str) -> dict | None:
    """Mongo filter limiting `collection` to the user's projects; None = all."""
    if collection not in SCOPED:
        return None
    project_ids = await accessible_project_ids(db, user)
    if project_ids is None:
        return None
    match = await _project_match(db, project_ids)
    if collection in {"material_requests", "purchase_orders"}:
        return match
    po_ids = [str(po["_id"]) async for po in db.purchase_orders.find(match, {"_id": 1})]
    if collection in {"deliveries", "invoices", "payments"}:
        return {"purchase_order_id": {"$in": po_ids}}
    # vendors: used on my projects, or not used by any project yet
    mine, used = set(), set()
    for coll in ("purchase_orders", "material_requests"):
        async for doc in db[coll].find({}, {"vendor_id": 1, "assigned_vendor_id": 1, "project_id": 1, "project": 1}):
            ids = {str(doc.get(k)) for k in ("vendor_id", "assigned_vendor_id") if doc.get(k)}
            used |= ids
    for coll in ("purchase_orders", "material_requests"):
        async for doc in db[coll].find(match, {"vendor_id": 1, "assigned_vendor_id": 1}):
            mine |= {str(doc.get(k)) for k in ("vendor_id", "assigned_vendor_id") if doc.get(k)}
    every = {str(v["_id"]) async for v in db.vendors.find({}, {"_id": 1})}
    visible = mine | (every - used)
    return {"_id": {"$in": [ObjectId(v) for v in visible if ObjectId.is_valid(v)]}}


def merge(filters: dict | None, scope: dict | None) -> dict | None:
    if not scope:
        return filters or None
    if not filters:
        return scope
    return {"$and": [filters, scope]}


async def ensure_in_scope(db, user: dict, collection: str, record_id: str) -> None:
    scope = await scope_filter(db, user, collection)
    if scope is None:
        return
    try:
        oid = ObjectId(record_id)
    except (InvalidId, TypeError):
        return  # the endpoint reports the bad id itself
    if await db[collection].count_documents({"_id": oid}) and not await db[collection].count_documents({"$and": [{"_id": oid}, scope]}):
        raise HTTPException(status_code=404, detail="Not found")


async def enforce_record_scope(request: Request, db=Depends(get_database)) -> None:
    """Router dependency: a record id in the URL must be on the user's projects."""
    keys = [key for key in request.path_params if key in PATH_COLLECTIONS]
    path = getattr(request.scope.get("route"), "path", request.url.path)
    if not keys or "/vendor/" in path:
        return
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return  # routes without login (QR image) keep their own rules
    user = await get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=header[7:].strip()), db)
    if str(user.get("role") or "").lower() == "vendor":
        return  # vendor access is checked by vendor_id in the endpoints
    for key in keys:
        await ensure_in_scope(db, user, PATH_COLLECTIONS[key], request.path_params[key])
