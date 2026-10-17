from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase


# =====================================================
# Create Invoice
# =====================================================

async def create_invoice(
    db: AsyncIOMotorDatabase,
    invoice_data: dict,
):
    invoice_data["createdAt"] = datetime.utcnow()

    result = await db.invoice_tracking.insert_one(
        invoice_data
    )

    return await db.invoice_tracking.find_one(
        {"_id": result.inserted_id}
    )


# =====================================================
# Get Invoice
# =====================================================

async def get_invoice(
    db: AsyncIOMotorDatabase,
    invoice_id: str,
):
    try:
        oid = ObjectId(invoice_id)
    except InvalidId:
        return None

    return await db.invoice_tracking.find_one(
        {"_id": oid}
    )


# =====================================================
# Update Invoice
# =====================================================

async def update_invoice(
    db: AsyncIOMotorDatabase,
    invoice_id: str,
    update_data: dict,
):
    try:
        oid = ObjectId(invoice_id)
    except InvalidId:
        return None

    await db.invoice_tracking.update_one(
        {"_id": oid},
        {"$set": update_data},
    )

    return await db.invoice_tracking.find_one(
        {"_id": oid}
    )


# =====================================================
# Delete Invoice
# =====================================================

async def delete_invoice(
    db: AsyncIOMotorDatabase,
    invoice_id: str,
):
    try:
        oid = ObjectId(invoice_id)
    except InvalidId:
        return False

    result = await db.invoice_tracking.delete_one(
        {"_id": oid}
    )

    return result.deleted_count > 0


# =====================================================
# List Invoices
# =====================================================

async def list_invoices(
    db: AsyncIOMotorDatabase,
    skip: int = 0,
    limit: int = 10,
):
    return await (
        db.invoice_tracking.find()
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )


# =====================================================
# Get Invoices by Project
# =====================================================

async def get_invoices_by_project(
    db: AsyncIOMotorDatabase,
    project_id: str,
):
    return await db.invoice_tracking.find(
        {"projectId": project_id}
    ).to_list(None)


# =====================================================
# Get Invoices by Vendor
# =====================================================

async def get_invoices_by_vendor(
    db: AsyncIOMotorDatabase,
    vendor_id: str,
):
    return await db.invoice_tracking.find(
        {"vendorId": vendor_id}
    ).to_list(None)


# =====================================================
# Get Invoices by Status
# =====================================================

async def get_invoices_by_status(
    db: AsyncIOMotorDatabase,
    status: str,
):
    return await db.invoice_tracking.find(
        {"status": status}
    ).to_list(None)