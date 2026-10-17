from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase


# ==========================
# Create Purchase Order
# ==========================

async def create_purchase_order(
    db: AsyncIOMotorDatabase,
    purchase_order_data: dict,
):
    purchase_order_data["createdAt"] = datetime.utcnow()

    result = await db.purchase_orders.insert_one(
        purchase_order_data
    )

    return await db.purchase_orders.find_one(
        {"_id": result.inserted_id}
    )


# ==========================
# Get Purchase Order
# ==========================

async def get_purchase_order(
    db: AsyncIOMotorDatabase,
    purchase_order_id: str,
):
    try:
        oid = ObjectId(purchase_order_id)
    except InvalidId:
        return None

    return await db.purchase_orders.find_one(
        {"_id": oid}
    )


# ==========================
# Update Purchase Order
# ==========================

async def update_purchase_order(
    db: AsyncIOMotorDatabase,
    purchase_order_id: str,
    update_data: dict,
):
    try:
        oid = ObjectId(purchase_order_id)
    except InvalidId:
        return None

    await db.purchase_orders.update_one(
        {"_id": oid},
        {"$set": update_data},
    )

    return await db.purchase_orders.find_one(
        {"_id": oid}
    )


# ==========================
# Delete Purchase Order
# ==========================

async def delete_purchase_order(
    db: AsyncIOMotorDatabase,
    purchase_order_id: str,
):
    try:
        oid = ObjectId(purchase_order_id)
    except InvalidId:
        return False

    result = await db.purchase_orders.delete_one(
        {"_id": oid}
    )

    return result.deleted_count > 0


# ==========================
# List Purchase Orders
# ==========================

async def list_purchase_orders(
    db: AsyncIOMotorDatabase,
    skip: int = 0,
    limit: int = 10,
):
    return await (
        db.purchase_orders.find()
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )


# ==========================
# Purchase Orders by Project
# ==========================

async def get_purchase_orders_by_project(
    db: AsyncIOMotorDatabase,
    project_id: str,
):
    return await db.purchase_orders.find(
        {"projectId": project_id}
    ).to_list(None)


# ==========================
# Purchase Orders by Vendor
# ==========================

async def get_purchase_orders_by_vendor(
    db: AsyncIOMotorDatabase,
    vendor_id: str,
):
    return await db.purchase_orders.find(
        {"vendorId": vendor_id}
    ).to_list(None)


# ==========================
# Purchase Orders by Status
# ==========================

async def get_purchase_orders_by_status(
    db: AsyncIOMotorDatabase,
    status: str,
):
    return await db.purchase_orders.find(
        {"status": status}
    ).to_list(None)