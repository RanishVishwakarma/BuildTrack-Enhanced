from fastapi import APIRouter, Depends, HTTPException, status

from app.core.access import ensure_project_access, own_worker_ids
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.purchase_orders.db import (
    create_purchase_order,
    delete_purchase_order,
    get_purchase_order,
    get_purchase_orders_by_project,
    get_purchase_orders_by_status,
    get_purchase_orders_by_vendor,
    list_purchase_orders,
    update_purchase_order,
)
from app.modules.purchase_orders.models import (
    PurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)

router = APIRouter()


def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB ObjectId to string."""
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# =====================================================
# Create Purchase Order
# =====================================================

@router.post("/", response_model=PurchaseOrder)
async def create_purchase_order_endpoint(
    purchase_order: PurchaseOrderCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Create new purchase order"""

    ensure_permission(current_user, "procurement.request.review")

    purchase_order_data = purchase_order.model_dump()

    result = await create_purchase_order(
        db,
        purchase_order_data,
    )

    return PurchaseOrder(**serialize_doc(result))


# =====================================================
# List Purchase Orders
# =====================================================

@router.get("/", response_model=list[PurchaseOrder])
async def list_purchase_orders_endpoint(
    skip: int = 0,
    limit: int = 10,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """List purchase orders"""
    ensure_permission(current_user, "procurement.read.assigned")

    purchase_orders = await list_purchase_orders(
        db,
        skip,
        limit,
    )

    return [
        PurchaseOrder(**serialize_doc(po))
        for po in purchase_orders
    ]


# =====================================================
# Get Purchase Order
# =====================================================

@router.get("/{purchase_order_id}", response_model=PurchaseOrder)
async def get_purchase_order_endpoint(
    purchase_order_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get purchase order"""
    ensure_permission(current_user, "procurement.read.assigned")

    purchase_order = await get_purchase_order(
        db,
        purchase_order_id,
    )

    if not purchase_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found",
        )

    return PurchaseOrder(**serialize_doc(purchase_order))


# =====================================================
# Update Purchase Order
# =====================================================

@router.put("/{purchase_order_id}", response_model=PurchaseOrder)
async def update_purchase_order_endpoint(
    purchase_order_id: str,
    update: PurchaseOrderUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Update purchase order"""

    ensure_permission(current_user, "procurement.request.review")

    purchase_order = await get_purchase_order(
        db,
        purchase_order_id,
    )

    if not purchase_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found",
        )

    update_data = update.model_dump(exclude_unset=True)

    result = await update_purchase_order(
        db,
        purchase_order_id,
        update_data,
    )

    return PurchaseOrder(**serialize_doc(result))


# =====================================================
# Delete Purchase Order
# =====================================================

@router.delete("/{purchase_order_id}")
async def delete_purchase_order_endpoint(
    purchase_order_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Delete purchase order"""

    ensure_permission(current_user, "records.delete")

    deleted = await delete_purchase_order(
        db,
        purchase_order_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found",
        )

    return {
        "message": "Purchase order deleted successfully"
    }


# =====================================================
# Purchase Orders by Project
# =====================================================

@router.get("/project/{project_id}", response_model=list[PurchaseOrder])
async def get_purchase_orders_by_project_endpoint(
    project_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get purchase orders by project"""
    ensure_permission(current_user, "procurement.read.assigned")

    purchase_orders = await get_purchase_orders_by_project(
        db,
        project_id,
    )

    return [
        PurchaseOrder(**serialize_doc(po))
        for po in purchase_orders
    ]


# =====================================================
# Purchase Orders by Vendor
# =====================================================

@router.get("/vendor/{vendor_id}", response_model=list[PurchaseOrder])
async def get_purchase_orders_by_vendor_endpoint(
    vendor_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get purchase orders by vendor"""
    ensure_permission(current_user, "procurement.read.assigned")

    purchase_orders = await get_purchase_orders_by_vendor(
        db,
        vendor_id,
    )

    return [
        PurchaseOrder(**serialize_doc(po))
        for po in purchase_orders
    ]


# =====================================================
# Purchase Orders by Status
# =====================================================

@router.get("/status/{status}", response_model=list[PurchaseOrder])
async def get_purchase_orders_by_status_endpoint(
    status: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get purchase orders by status"""
    ensure_permission(current_user, "procurement.read.assigned")

    purchase_orders = await get_purchase_orders_by_status(
        db,
        status,
    )

    return [
        PurchaseOrder(**serialize_doc(po))
        for po in purchase_orders
    ]