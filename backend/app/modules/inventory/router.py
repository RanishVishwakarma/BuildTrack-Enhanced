from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime

from app.core.access import ensure_project_access, own_worker_ids
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.inventory.db import (
    create_inventory_item,
    delete_inventory_item,
    get_inventory_item,
    get_low_stock_items,
    get_item_transactions,
    list_inventory,
    record_transaction,
    update_inventory_item,
)
from app.modules.inventory.models import (
    InventoryItem,
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryTransaction,
    InventoryTransactionCreate,
)

router = APIRouter()


def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB ObjectId to string and normalize across inventory/procurement schemas."""
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    
    mat_name = (
        doc.get("material_name")
        or doc.get("material")
        or doc.get("itemName")
        or doc.get("materialName")
        or "Unnamed Material"
    )
    doc["material_name"] = str(mat_name).strip()
    
    qty = (
        doc.get("stock_quantity")
        if doc.get("stock_quantity") is not None
        else (doc.get("quantity") if doc.get("quantity") is not None else (doc.get("stock") or 0))
    )
    doc["quantity"] = float(qty)
    doc.setdefault("unit", doc.get("unit") or "Nos")
    doc.setdefault("unit_cost", float(doc.get("unit_cost") or doc.get("unitCost") or doc.get("unitPrice") or 0.0))
    doc.setdefault("supplier_id", doc.get("supplier") or doc.get("supplierId") or doc.get("vendor_id"))
    doc.setdefault("location", doc.get("location") or "Main Warehouse")
    
    reorder = float(doc.get("reorder_level") or doc.get("reorderLevel") or 10)
    doc["reorder_level"] = int(reorder)
    
    if doc["quantity"] <= 0:
        doc["status"] = "out_of_stock"
    elif doc["quantity"] <= reorder:
        doc["status"] = "low_stock"
    else:
        doc["status"] = "in_stock"
        
    doc.setdefault("created_at", doc.get("created_at") or datetime.utcnow())
    doc.setdefault("updated_at", doc.get("updated_at") or datetime.utcnow())
    return doc


# -----------------------------
# Inventory Item Endpoints
# -----------------------------

@router.post("", response_model=InventoryItem)
@router.post("/", response_model=InventoryItem)
async def create_item_endpoint(
    item: InventoryItemCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "inventory.adjust.assigned")

    result = await create_inventory_item(db, item.model_dump())
    return InventoryItem(**serialize_doc(result))


@router.get("", response_model=list[InventoryItem])
@router.get("/", response_model=list[InventoryItem])
async def list_inventory_endpoint(
    skip: int = 0,
    limit: int = 500,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "inventory.read.assigned")
    raw_items = await list_inventory(db, 0, 10000)
    # Merge items with the same normalized material name
    merged: dict[str, dict] = {}
    for it in raw_items:
        norm = serialize_doc(it)
        key = norm["material_name"].lower()
        if key not in merged or str(norm.get("updated_at", "")) > str(merged[key].get("updated_at", "")):
            merged[key] = norm

    all_items = list(merged.values())
    return [InventoryItem(**i) for i in all_items[skip:skip + limit]]


# IMPORTANT: keep this BEFORE /{item_id}
@router.get("/low-stock", response_model=list[InventoryItem])
async def get_low_stock_endpoint(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "inventory.read.assigned")
    items = await get_low_stock_items(db)
    return [InventoryItem(**serialize_doc(i)) for i in items]


@router.get("/{item_id}", response_model=InventoryItem)
async def get_item_endpoint(
    item_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "inventory.read.assigned")
    item = await get_inventory_item(db, item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    return InventoryItem(**serialize_doc(item))


@router.put("/{item_id}", response_model=InventoryItem)
async def update_item_endpoint(
    item_id: str,
    update: InventoryItemUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "inventory.adjust.assigned")

    item = await get_inventory_item(db, item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    result = await update_inventory_item(
        db,
        item_id,
        update.model_dump(exclude_unset=True),
    )

    return InventoryItem(**serialize_doc(result))


@router.delete("/{item_id}")
async def delete_item_endpoint(
    item_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "records.delete")

    deleted = await delete_inventory_item(db, item_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    return {"message": "Inventory item deleted successfully"}


# -----------------------------
# Inventory Transaction Endpoints
# -----------------------------

@router.post("/{item_id}/transactions", response_model=InventoryTransaction)
async def record_transaction_endpoint(
    item_id: str,
    transaction: InventoryTransactionCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "inventory.adjust.assigned")

    item = await get_inventory_item(db, item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    transaction_data = transaction.model_dump()
    transaction_data["item_id"] = item_id

    result = await record_transaction(db, transaction_data)

    return InventoryTransaction(**serialize_doc(result))


@router.get("/{item_id}/transactions", response_model=list[InventoryTransaction])
async def get_item_transactions_endpoint(
    item_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "inventory.read.assigned")
    transactions = await get_item_transactions(db, item_id)

    return [
        InventoryTransaction(**serialize_doc(t))
        for t in transactions
    ]
