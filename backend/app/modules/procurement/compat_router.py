from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.access import ensure_project_access, own_worker_ids
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.procurement.db import (
    create_procurement,
    create_vendor,
    delete_procurement,
    get_procurement,
    get_vendor,
    list_procurements,
    list_vendors,
    update_procurement,
)
from app.modules.procurement.models import (
    Procurement,
    ProcurementCreate,
    ProcurementUpdate,
    Vendor,
    VendorCreate,
)

router = APIRouter()


def serialize_doc(doc: dict) -> dict:
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])

    doc.setdefault("contact_person", "Contact Person")
    doc.setdefault("phone", "0000000000")
    doc.setdefault("address", "N/A")
    doc.setdefault("vendor_name", "Supplier")
    doc.setdefault("email", "vendor@example.com")
    doc.setdefault("status", "active")

    doc.setdefault("vendor_id", doc.get("vendorId") or doc.get("supplierName") or doc.get("supplier") or "supplier")
    doc.setdefault("project_id", doc.get("projectId"))
    if "items" not in doc:
        quantity = doc.get("quantity") or 1
        unit_price = doc.get("unitPrice") or doc.get("amount") or 0
        doc["items"] = [
            {
                "item_name": doc.get("materialName") or doc.get("itemsSummary") or "Procurement item",
                "quantity": quantity,
                "unit_price": unit_price,
                "total_cost": doc.get("totalAmount") or doc.get("amount") or quantity * unit_price,
            }
        ]
    doc.setdefault("requested_by", doc.get("requestedBy") or "frontend")
    doc.setdefault("request_date", doc.get("requestDate") or doc.get("purchaseDate") or datetime.utcnow())
    doc.setdefault("expected_delivery", doc.get("expectedDelivery") or doc.get("deliveryDate"))
    doc.setdefault("status", doc.get("status") or "pending")
    doc.setdefault("total_amount", doc.get("totalAmount") or doc.get("amount") or 0)
    doc.setdefault("notes", doc.get("remarks") or doc.get("poNo"))
    doc.setdefault("created_at", doc.get("createdAt") or datetime.utcnow())
    doc.setdefault("updated_at", doc.get("updatedAt") or datetime.utcnow())
    return doc


@router.post("/vendors", response_model=Vendor)
async def create_vendor_compat_endpoint(
    vendor: VendorCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "procurement.vendor.manage")

    result = await create_vendor(db, vendor.model_dump())
    return Vendor(**serialize_doc(result))


@router.get("/vendors", response_model=list[Vendor])
async def list_vendors_compat_endpoint(
    skip: int = 0,
    limit: int = 10,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "procurement.read.assigned")
    vendors = await list_vendors(db, skip, limit)
    return [Vendor(**serialize_doc(vendor)) for vendor in vendors]


@router.get("/vendors/{vendor_id}", response_model=Vendor)
async def get_vendor_compat_endpoint(
    vendor_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "procurement.read.assigned")
    vendor = await get_vendor(db, vendor_id)
    if not vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return Vendor(**serialize_doc(vendor))


@router.post("/procurements", response_model=Procurement)
async def create_procurement_compat_endpoint(
    procurement: ProcurementCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "procurement.request.review")

    result = await create_procurement(db, procurement.model_dump())
    return Procurement(**serialize_doc(result))


@router.get("/procurements", response_model=list[Procurement])
async def list_procurements_compat_endpoint(
    skip: int = 0,
    limit: int = 10,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "procurement.read.assigned")
    procurements = await list_procurements(db, skip, limit)
    return [Procurement(**serialize_doc(item)) for item in procurements]


@router.get("/procurements/{procurement_id}", response_model=Procurement)
async def get_procurement_compat_endpoint(
    procurement_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "procurement.read.assigned")
    procurement = await get_procurement(db, procurement_id)
    if not procurement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procurement order not found")
    return Procurement(**serialize_doc(procurement))


@router.put("/procurements/{procurement_id}", response_model=Procurement)
async def update_procurement_compat_endpoint(
    procurement_id: str,
    update: ProcurementUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "procurement.request.review")

    procurement = await get_procurement(db, procurement_id)
    if not procurement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procurement order not found")

    result = await update_procurement(db, procurement_id, update.model_dump(exclude_unset=True))
    return Procurement(**serialize_doc(result))


@router.delete("/procurements/{procurement_id}")
async def delete_procurement_compat_endpoint(
    procurement_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "records.delete")

    deleted = await delete_procurement(db, procurement_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procurement order not found")
    return {"message": "Procurement order deleted successfully"}
