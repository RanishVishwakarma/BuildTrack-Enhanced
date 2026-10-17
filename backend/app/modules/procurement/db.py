from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase


def oid(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except InvalidId:
        return None


def now() -> datetime:
    return datetime.utcnow()


async def next_code(db: AsyncIOMotorDatabase, name: str, prefix: str) -> str:
    counter = await db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return f"{prefix}-{counter['seq']:05d}"


async def log_activity(db: AsyncIOMotorDatabase, action: str, entity: str, entity_id: str, user: dict | None = None, meta: dict | None = None):
    await db.procurement_activity.insert_one(
        {
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "user_id": str(user.get("_id", "")) if user else None,
            "user_name": user.get("full_name") if user else None,
            "meta": meta or {},
            "created_at": now(),
        }
    )


async def create_doc(db: AsyncIOMotorDatabase, collection: str, data: dict, user: dict | None = None):
    data["created_at"] = now()
    data["updated_at"] = now()
    result = await db[collection].insert_one(data)
    doc = await db[collection].find_one({"_id": result.inserted_id})
    await log_activity(db, "created", collection, str(result.inserted_id), user)
    return doc


async def get_doc(db: AsyncIOMotorDatabase, collection: str, doc_id: str):
    object_id = oid(doc_id)
    query = {"_id": object_id} if object_id else {"$or": [{"_id": doc_id}, {"id": doc_id}, {"po_number": doc_id}]}
    return await db[collection].find_one(query)


async def update_doc(db: AsyncIOMotorDatabase, collection: str, doc_id: str, data: dict, user: dict | None = None):
    object_id = oid(doc_id)
    query = {"_id": object_id} if object_id else {"$or": [{"_id": doc_id}, {"id": doc_id}, {"po_number": doc_id}]}
    data["updated_at"] = now()
    await db[collection].update_one(query, {"$set": data})
    await log_activity(db, "updated", collection, doc_id, user, data)
    return await db[collection].find_one(query)


async def delete_doc(db: AsyncIOMotorDatabase, collection: str, doc_id: str, user: dict | None = None) -> bool:
    object_id = oid(doc_id)
    query = {"_id": object_id} if object_id else {"$or": [{"_id": doc_id}, {"id": doc_id}, {"po_number": doc_id}]}
    result = await db[collection].delete_one(query)
    if result.deleted_count:
        await log_activity(db, "deleted", collection, doc_id, user)
    return result.deleted_count > 0


async def list_docs(
    db: AsyncIOMotorDatabase,
    collection: str,
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    fields: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    sort_by: str = "created_at",
    sort_dir: int = -1,
):
    query_parts: list[dict[str, Any]] = []
    if filters:
        query_parts.append(filters)
    if search and fields:
        query_parts.append({"$or": [{field: {"$regex": search, "$options": "i"}} for field in fields]})

    if len(query_parts) == 0:
        query = {}
    elif len(query_parts) == 1:
        query = query_parts[0]
    else:
        query = {"$and": query_parts}

    cursor = db[collection].find(query).sort(sort_by, sort_dir).skip(skip).limit(limit)
    total = await db[collection].count_documents(query)
    return {"items": await cursor.to_list(limit), "total": total}


async def create_material_request(db: AsyncIOMotorDatabase, data: dict, user: dict):
    # Validate project reference (save its actual database ID, not just the name).
    project_id = data.get("project_id")
    if project_id:
        project = await db.projects.find_one({"_id": oid(project_id)}) if oid(project_id) else None
        if not project:
            return None, "Invalid project selected"
        data["project"] = project.get("name") or data.get("project", "Project")
        data["project_id"] = str(project["_id"])

    # Validate material reference against the inventory/material master collection.
    material_id = data.get("material_id")
    material = None
    if material_id:
        material = await db.inventory.find_one({"_id": oid(material_id)}) if oid(material_id) else None
        if not material:
            return None, "Invalid material selected"
        data["material_name"] = material.get("material_name") or material.get("material") or data.get("material_name", "Material")
        data["material_id"] = str(material["_id"])
        data.setdefault("unit", material.get("unit"))

    data["request_id"] = await next_code(db, "material_requests", "MR")
    data["status"] = "pending"
    data["requested_by"] = user.get("full_name") or str(user.get("_id", ""))
    return await create_doc(db, "material_requests", data, user), None


async def approve_material_request(db: AsyncIOMotorDatabase, request_id: str, status: str, comments: str | None, user: dict):
    object_id = oid(request_id)
    if not object_id:
        return None
    data = {
        "status": status,
        "approval_comments": comments,
        "approved_by": user.get("full_name") or str(user.get("_id", "")),
        "approved_at": now(),
        "updated_at": now(),
    }
    await db.material_requests.update_one({"_id": object_id}, {"$set": data})
    await log_activity(db, status, "material_requests", request_id, user, {"comments": comments})
    return await db.material_requests.find_one({"_id": object_id})


async def assign_vendor_to_material_request(db: AsyncIOMotorDatabase, request_id: str, vendor_id: str, user: dict):
    request = await get_doc(db, "material_requests", request_id)
    if not request:
        return None, "Material request not found"
    if request.get("status") == "rejected":
        return None, "Cannot assign vendor to a rejected request"
    if request.get("status") not in {"approved", "vendor_assigned", "sent_to_vendor"}:
        return None, "Vendor can be assigned only after request approval"

    vendor = await get_doc(db, "vendors", vendor_id)
    if not vendor:
        return None, "Vendor not found"
    if vendor.get("status") != "active":
        return None, "Only active vendors can be assigned"

    data = {
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("vendor_name"),
        "vendor_assigned_by": user.get("full_name") or str(user.get("_id", "")),
        "vendor_assigned_at": now(),
        "assigned_vendor_id": vendor_id,
        "vendor_response": None,
        "vendor_response_date": None,
        "vendor_comment": None,
        "status": "sent_to_vendor",
        "updated_at": now(),
    }
    await db.material_requests.update_one({"_id": request["_id"]}, {"$set": data})
    await log_activity(db, "vendor_assigned", "material_requests", request_id, user, {"vendor_id": vendor_id})
    return await db.material_requests.find_one({"_id": request["_id"]}), None


async def vendor_respond_to_request(db: AsyncIOMotorDatabase, request_id: str, action: str, comment: str | None, user: dict):
    """Vendor accepts/rejects a procurement request assigned to their vendor record."""
    request = await get_doc(db, "material_requests", request_id)
    if not request:
        return None, "Material request not found"

    # 1. Only a vendor user may respond.
    if user.get("role") != "vendor":
        return None, "Only a vendor user can respond to procurement requests"

    # 2. The vendor must be linked to a vendor record.
    vendor_id = user.get("vendor_id")
    if not vendor_id:
        return None, "Your account is not linked to a vendor record"

    # 3. This vendor must be the one assigned to this request.
    if str(request.get("vendor_id") or request.get("assigned_vendor_id") or "") != str(vendor_id):
        return None, "You are not the assigned vendor for this request"

    # 4. Request must be in a valid state for acceptance/rejection.
    if request.get("status") not in {"sent_to_vendor", "vendor_assigned", "vendor_accepted", "vendor_rejected"}:
        return None, "This request is not available for vendor response"

    # 5. Request cannot be responded to twice.
    if request.get("vendor_response") is not None:
        return None, "You have already responded to this request"

    # 6. Rejection requires a reason/comment.
    if action == "reject" and not (comment and comment.strip()):
        return None, "A rejection reason or comment is required"

    new_status = "vendor_accepted" if action == "accept" else "vendor_rejected"
    data = {
        "status": new_status,
        "vendor_response": action,
        "vendor_response_date": now(),
        "vendor_comment": comment,
        "updated_at": now(),
    }
    await db.material_requests.update_one({"_id": request["_id"]}, {"$set": data})
    await log_activity(db, f"vendor_{action}", "material_requests", request_id, user, {"comment": comment})
    return await db.material_requests.find_one({"_id": request["_id"]}), None

async def create_purchase_order_from_request(db: AsyncIOMotorDatabase, data: dict, user: dict):
    request = await get_doc(db, "material_requests", data["request_id"])
    if not request:
        return None, "Material request not found"
    if request.get("purchase_order_id"):
        return None, "Purchase order already exists for this material request"

    assigned_vendor_id = request.get("vendor_id") or data.get("vendor_id")
    if not assigned_vendor_id:
        return None, "Assign a vendor before generating a purchase order"

    if request.get("status") != "vendor_accepted":
        return None, "Purchase order can be generated only after the vendor accepts the procurement request"

    vendor = await get_doc(db, "vendors", assigned_vendor_id)
    if not vendor:
        return None, "Assigned vendor not found"
    if vendor.get("status") != "active":
        return None, "Assigned vendor is not active"

    if request.get("vendor_id") and data.get("vendor_id") and data["vendor_id"] != request["vendor_id"]:
        return None, "Purchase order vendor must match the assigned request vendor"

    data["vendor_id"] = assigned_vendor_id
    data["project"] = request["project"]
    data["project_id"] = request.get("project_id")
    data["materials"] = request["material_name"]
    data["material_id"] = request.get("material_id")
    data["quantity"] = request["quantity"]
    data["po_number"] = await next_code(db, "purchase_orders", "PO")
    subtotal = float(data["quantity"]) * float(data.get("unit_price") or 0)
    gst = float(data.get("gst") or 0)
    data["subtotal"] = subtotal
    data["gst"] = gst
    data["total_cost"] = subtotal + gst
    doc = await create_doc(db, "purchase_orders", data, user)
    await db.material_requests.update_one(
        {"_id": request["_id"]},
        {
            "$set": {
                "status": "po_generated",
                "vendor_id": assigned_vendor_id,
                "vendor_name": vendor.get("vendor_name"),
                "vendor_assigned_by": request.get("vendor_assigned_by") or user.get("full_name") or str(user.get("_id", "")),
                "vendor_assigned_at": request.get("vendor_assigned_at") or now(),
                "purchase_order_id": str(doc["_id"]),
                "po_number": doc["po_number"],
                "updated_at": now(),
            }
        },
    )
    await log_activity(db, "po_generated", "material_requests", data["request_id"], user, {"purchase_order_id": str(doc["_id"])})
    return doc, None


async def update_purchase_order(db: AsyncIOMotorDatabase, po_id: str, data: dict, user: dict):
    if "quantity" in data or "unit_price" in data:
        current = await get_doc(db, "purchase_orders", po_id)
        if not current:
            return None
        quantity = float(data.get("quantity", current.get("quantity", 0)))
        unit_price = float(data.get("unit_price", current.get("unit_price", 0)))
        data["total_cost"] = quantity * unit_price
    return await update_doc(db, "purchase_orders", po_id, data, user)


async def sync_delivery_inventory(db: AsyncIOMotorDatabase, delivery_doc: dict, user: dict | None = None):
    """Accurately reconcile inventory stock based on the delivery's verified status and quantity.
    Prevents double-counting by tracking exact credited stock per delivery."""
    if not delivery_doc:
        return

    delivery_id = str(delivery_doc["_id"])
    material = delivery_doc.get("material")
    if not material:
        return

    is_accepted = delivery_doc.get("status") in {"accepted", "partial"} and delivery_doc.get("quality_status") == "passed"
    target_credited = float(delivery_doc.get("quantity_received") or delivery_doc.get("quantity") or 0) if is_accepted else 0.0
    current_credited = float(delivery_doc.get("stock_credited_quantity") or 0.0)

    delta = target_credited - current_credited
    if delta == 0:
        return

    # Update delivery's credited tracker
    await db.deliveries.update_one({"_id": delivery_doc["_id"]}, {"$set": {"stock_credited_quantity": target_credited}})

    # Find or create inventory item
    existing = await db.inventory.find_one({"$or": [{"material": material}, {"material_name": material}]})
    
    actor_name = (user.get("full_name") or user.get("name") or str(user.get("_id", "System"))) if user else "System"
    transaction = {
        "transaction_type": "PURCHASE_RECEIPT" if delta > 0 else "INVENTORY_ADJUSTMENT",
        "delivery_id": delivery_id,
        "material": material,
        "quantity": abs(delta),
        "delta": delta,
        "unit": delivery_doc.get("unit") or "Nos",
        "created_by": actor_name,
        "created_at": now(),
        "remarks": f"Delivery QA update (delta: {delta:+.2f} units)",
    }

    if existing:
        await db.inventory.update_one(
            {"_id": existing["_id"]},
            {
                "$inc": {"stock_quantity": delta, "quantity": delta},
                "$push": {"transactions": transaction},
                "$set": {"material": material, "material_name": material, "updated_at": now()},
            }
        )
    else:
        if delta > 0:
            await db.inventory.insert_one({
                "material": material,
                "material_name": material,
                "stock_quantity": delta,
                "quantity": delta,
                "unit": delivery_doc.get("unit") or "Nos",
                "status": "in_stock",
                "reorder_level": 10,
                "transactions": [transaction],
                "created_at": now(),
                "updated_at": now(),
            })

    if delta > 0:
        await log_activity(db, "inventory_increased", "inventory", material, user, transaction)
    elif delta < 0:
        await log_activity(db, "inventory_adjusted", "inventory", material, user, transaction)

    # If delivery is accepted with quality passed, transition the linked purchase order to 'delivered'
    if is_accepted and delivery_doc.get("purchase_order_id"):
        po_id_raw = str(delivery_doc["purchase_order_id"])
        po_query = {"$or": [{"_id": po_id_raw}]}
        if oid(po_id_raw):
            po_query["$or"].append({"_id": oid(po_id_raw)})
        
        await db.purchase_orders.update_one(
            po_query,
            {"$set": {"status": "delivered", "updated_at": now()}}
        )

        req_query = {"$or": [{"purchase_order_id": po_id_raw}]}
        if oid(po_id_raw):
            req_query["$or"].append({"purchase_order_id": oid(po_id_raw)})
        await db.material_requests.update_one(
            req_query,
            {"$set": {"status": "delivered", "updated_at": now()}}
        )


async def create_delivery_and_inventory(db: AsyncIOMotorDatabase, data: dict, user: dict):
    # Resolve material name/id from the linked purchase order when available.
    po = await get_doc(db, "purchase_orders", data.get("purchase_order_id", "")) if data.get("purchase_order_id") else None
    if po:
        data.setdefault("material", po.get("materials") or data.get("material", ""))
        data.setdefault("material_id", po.get("material_id"))
        data.setdefault("vendor_id", po.get("vendor_id"))

    # Partial delivery: if received < ordered quantity mark as partial.
    ordered_qty = float(po.get("quantity") or 0) if po else float(data.get("quantity_ordered") or 0)
    received = float(data.get("quantity_received", 0))
    partial = po is not None and ordered_qty > received
    if partial:
        data["status"] = "partial"
    elif data.get("status") not in {"accepted", "rejected"}:
        data["status"] = "accepted" if data.get("quality_status") == "passed" else "rejected"

    doc = await create_doc(db, "deliveries", data, user)
    await sync_delivery_inventory(db, doc, user)

    # Sync downstream PO / request statuses based on this delivery.
    delivery_status = data.get("status")
    if po:
        po_updates = {"updated_at": now()}
        if delivery_status == "accepted":
            po_updates["status"] = "delivered"
        elif delivery_status == "partial":
            po_updates["status"] = "accepted"
        elif delivery_status == "rejected":
            po_updates["status"] = "sent"
        await db.purchase_orders.update_one({"_id": po["_id"]}, {"$set": po_updates})

        req = await db.material_requests.find_one({"purchase_order_id": str(po["_id"])})
        if req:
            req_status = (
                "partially_delivered" if delivery_status == "partial"
                else "delivered" if delivery_status == "accepted"
                else req.get("status")
            )
            if req_status != req.get("status"):
                await db.material_requests.update_one(
                    {"_id": req["_id"]}, {"$set": {"status": req_status, "updated_at": now()}}
                )

    return doc


async def update_invoice_status(db: AsyncIOMotorDatabase, invoice_id: str, status: str, user: dict, comments: str | None = None):
    data = {"status": status, "verification_comments": comments}
    if status == "approved":
        data["payment_status"] = "approved"
    if status == "rejected":
        data["payment_status"] = "pending"
    return await update_doc(db, "invoices", invoice_id, data, user)


async def create_payment_for_invoice(db: AsyncIOMotorDatabase, data: dict, user: dict):
    invoice = await get_doc(db, "invoices", data["invoice_id"])
    if not invoice:
        return None, "Invoice not found"
    
    if data.get("status") == "paid" or not data.get("status"):
        data["status"] = "paid"
        if not data.get("paid_at"):
            data["paid_at"] = now()

    # Pre-fill vendor_id and purchase_order_id if not explicitly provided
    if not data.get("vendor_id"):
        data["vendor_id"] = invoice.get("vendor_id", "")
    if not data.get("purchase_order_id"):
        data["purchase_order_id"] = invoice.get("purchase_order_id", "")

    # Keep readable references on the payment so its history still shows names
    # if the invoice, purchase order or vendor is deleted later.
    data["invoice_number"] = invoice.get("invoice_number")
    if data.get("purchase_order_id"):
        po = await get_doc(db, "purchase_orders", str(data["purchase_order_id"]))
        data["po_number"] = (po or {}).get("po_number") or invoice.get("po_number")
    if data.get("vendor_id"):
        vendor = await get_doc(db, "vendors", str(data["vendor_id"]))
        data["vendor_name"] = (vendor or {}).get("vendor_name") or invoice.get("vendor_name")

    payment_doc = await create_doc(db, "payments", data, user)

    if data.get("status") == "paid":
        await db.invoices.update_one(
            {"_id": invoice["_id"]},
            {"$set": {"payment_status": "paid", "status": "approved", "updated_at": now()}}
        )

        # Notify the vendor user that payment was recorded
        vendor_id = invoice.get("vendor_id")
        if vendor_id:
            vendor_users = await db.users.find({
                "$or": [{"vendor_id": str(vendor_id)}, {"_id": oid(vendor_id)}]
            }).to_list(10)
            for vu in vendor_users:
                await create_notification(db, {
                    "user_id": str(vu["_id"]),
                    "title": "Payment Received",
                    "message": f"Payment of ₹{data.get('amount', invoice.get('amount', 0)):,.2f} for Invoice '{invoice.get('invoice_number')}' has been processed and paid.",
                    "type": "success",
                    "category": "payment",
                    "entity_type": "payment",
                    "entity_id": str(payment_doc["_id"]),
                })

    return payment_doc, None


async def dashboard_stats(db: AsyncIOMotorDatabase):
    raw_activity = await db.procurement_activity.find().sort("created_at", -1).limit(4).to_list(4)
    formatted_activity = []
    for a in raw_activity:
        action = a.get("action", "")
        entity = a.get("entity", "")
        entity_id = str(a.get("entity_id", ""))
        user_name = a.get("user_name") or "System Admin"
        meta = a.get("meta") or {}
        created_at = a.get("created_at")

        # Human-friendly Title and Description
        if action == "inventory_increased":
            title = "Inventory Stock Increased"
            qty = meta.get("quantity", "")
            unit = meta.get("unit") or "units"
            desc = f"Received {qty} {unit} of {entity_id} into warehouse inventory."
            icon = "fa-boxes-stacked"
            color = "green"
        elif entity == "payments":
            title = "Payment Processed"
            remarks = meta.get("remarks") or ""
            desc = f"Payment status set to {meta.get('status', 'paid')}. {remarks}".strip()
            icon = "fa-receipt"
            color = "emerald"
        elif entity == "invoices":
            title = f"Invoice {action.capitalize()}"
            status_text = meta.get("status") or action
            comm = f" - Notes: {meta.get('verification_comments')}" if meta.get('verification_comments') else ""
            desc = f"Invoice status updated to {status_text}{comm}."
            icon = "fa-file-invoice-dollar"
            color = "purple"
        elif entity == "deliveries":
            title = f"Delivery {action.capitalize()}"
            desc = f"Material delivery recorded. Status: {meta.get('status', 'received')}."
            icon = "fa-truck-ramp-box"
            color = "blue"
        elif entity == "purchase_orders":
            title = f"Purchase Order {action.capitalize()}"
            desc = f"Purchase order updated. Status: {meta.get('status', action)}."
            icon = "fa-file-contract"
            color = "indigo"
        elif entity == "material_requests":
            title = f"Material Request {action.capitalize()}"
            desc = f"Material request updated. Status: {meta.get('status', action)}."
            icon = "fa-clipboard-list"
            color = "amber"
        else:
            title = f"{entity.replace('_', ' ').title()} {action.capitalize()}"
            desc = f"Action '{action}' performed on {entity} by {user_name}."
            icon = "fa-bell"
            color = "blue"

        formatted_activity.append({
            "_id": str(a.get("_id")),
            "title": title,
            "description": desc,
            "timestamp": created_at,
            "created_at": created_at,
            "user_name": user_name,
            "action": action,
            "entity": entity,
            "icon": icon,
            "color": color,
        })

    return {
        "pending_requests": await db.material_requests.count_documents({"status": "pending"}),
        "active_purchase_orders": await db.purchase_orders.count_documents({"status": {"$in": ["created", "sent", "accepted"]}}),
        "pending_deliveries": await db.deliveries.count_documents({"status": {"$in": ["pending", "partial"]}}),
        "pending_payments": await db.payments.count_documents({"status": {"$in": ["pending", "approved"]}}),
        "recent_activity": formatted_activity,
    }


async def create_vendor(db: AsyncIOMotorDatabase, data: dict):
    return await create_doc(db, "vendors", data)


async def get_vendor(db: AsyncIOMotorDatabase, vendor_id: str):
    return await get_doc(db, "vendors", vendor_id)


async def list_vendors(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 10):
    res = await list_docs(db, "vendors", skip=skip, limit=limit)
    return res["items"]


async def create_procurement(db: AsyncIOMotorDatabase, data: dict):
    return await create_doc(db, "procurements", data)


async def get_procurement(db: AsyncIOMotorDatabase, procurement_id: str):
    return await get_doc(db, "procurements", procurement_id)


async def list_procurements(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 10):
    res = await list_docs(db, "procurements", skip=skip, limit=limit)
    return res["items"]


async def update_procurement(db: AsyncIOMotorDatabase, procurement_id: str, data: dict):
    return await update_doc(db, "procurements", procurement_id, data)


async def delete_procurement(db: AsyncIOMotorDatabase, procurement_id: str):
    return await delete_doc(db, "procurements", procurement_id)


async def list_purchase_orders(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 10):
    res = await list_docs(db, "purchase_orders", skip=skip, limit=limit)
    return res["items"]


async def list_invoices(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 10):
    res = await list_docs(db, "invoices", skip=skip, limit=limit)
    return res["items"]

async def list_materials_from_inventory(db: AsyncIOMotorDatabase, active_only: bool = True):
    """Material master list sourced from the `inventory` collection."""
    query = {}
    if active_only:
        query["$or"] = [
            {"status": {"$nin": ["inactive", "deleted"]}},
            {"status": {"$exists": False}},
        ]
    docs = await db.inventory.find(query).sort("material_name", 1).to_list(200)
    return docs


async def get_inventory_history(db: AsyncIOMotorDatabase, material_id: str | None = None, limit: int = 100):
    """Inventory transaction history (opening stock + entries)."""
    query = {}
    if material_id:
        query["material_id"] = material_id
    txn_cursor = db.inventory_transactions.find(query).sort("created_at", -1).limit(limit)
    transactions = await txn_cursor.to_list(limit)

    # Crawl back through receipts to compute opening stock for a material.
    opening = {}
    material_names = {}
    inventory_items = await db.inventory.find().to_list(200)
    for item in inventory_items:
        mid = str(item.get("_id"))
        material_names[mid] = item.get("material_name") or item.get("material") or item.get("material", "")
        stock = float(item.get("stock_quantity") or item.get("quantity") or 0)
        opening[mid] = stock - sum(
            float(t.get("quantity") or 0)
            for t in await db.inventory_transactions.find({"material_id": mid}).to_list(1000)
        )
    return {"materials": material_names, "opening_stock": opening, "transactions": transactions}


async def vendor_dashboard_stats(db: AsyncIOMotorDatabase, vendor_id: str, user_id: str | None = None):
    """Summary + records for the logged-in vendor's portal."""
    vendor = await get_doc(db, "vendors", vendor_id)

    # Build comprehensive vendor identifier variants
    v_ids: list[Any] = [str(vendor_id)]
    if oid(vendor_id):
        v_ids.append(oid(vendor_id))
    if user_id:
        v_ids.append(str(user_id))
        if oid(user_id):
            v_ids.append(oid(user_id))
    if vendor:
        v_ids.append(str(vendor["_id"]))
        v_ids.append(vendor["_id"])

    # 1. Purchase Orders & Deliveries
    po_conditions: list[dict[str, Any]] = [{"vendor_id": {"$in": v_ids}}]
    if vendor and vendor.get("vendor_name"):
        po_conditions.append({"vendor": vendor["vendor_name"]})
        po_conditions.append({"supplier": vendor["vendor_name"]})
    pos = await db.purchase_orders.find({"$or": po_conditions}).sort("created_at", -1).to_list(200)
    po_ids_str = [str(p["_id"]) for p in pos]

    # Deliveries for this vendor / POs
    deliveries = await db.deliveries.find(
        {"$or": [{"vendor_id": {"$in": v_ids}}, {"purchase_order_id": {"$in": po_ids_str}}]}
    ).sort("created_at", -1).to_list(200)

    delivered_po_ids = {
        str(d.get("purchase_order_id"))
        for d in deliveries
        if (d.get("status") in {"accepted", "delivered"} or d.get("quality_status") == "passed") and d.get("purchase_order_id")
    }

    total_pos = len(pos)
    pending_orders = sum(1 for p in pos if p.get("status") in {"created", "sent", "pending"})
    delivered_orders = sum(
        1 for p in pos
        if p.get("status") in {"delivered", "received", "completed"} or str(p["_id"]) in delivered_po_ids
    )
    accepted_orders = sum(
        1 for p in pos
        if (p.get("status") in {"accepted", "processing", "shipped"}) and (str(p["_id"]) not in delivered_po_ids)
    )

    # 2. Material Requests
    req_conditions: list[dict[str, Any]] = [
        {"vendor_id": {"$in": v_ids}},
        {"assigned_vendor_id": {"$in": v_ids}},
    ]
    if vendor and vendor.get("vendor_name"):
        req_conditions.append({"vendor_name": vendor["vendor_name"]})

    requests = await db.material_requests.find({"$or": req_conditions}).sort("created_at", -1).to_list(200)
    pending_responses = sum(1 for r in requests if r.get("status") in {"vendor_assigned", "sent_to_vendor", "pending"} and not r.get("vendor_response"))
    accepted_reqs = sum(1 for r in requests if r.get("status") in {"vendor_accepted", "po_generated", "po_sent"} or r.get("vendor_response") == "accept")
    rejected_reqs = sum(1 for r in requests if r.get("status") == "vendor_rejected" or r.get("vendor_response") == "reject")

    # 3. Deliveries Pending
    pending_deliveries = sum(1 for d in deliveries if d.get("status") in {"pending", "partial", "processing", "shipped", "in_transit", "dispatched"})

    # 4. Invoices
    invoices = await db.invoices.find(
        {"$or": [{"vendor_id": {"$in": v_ids}}, {"purchase_order_id": {"$in": po_ids_str}}]}
    ).sort("created_at", -1).to_list(200)
    pending_invoices = sum(1 for inv in invoices if inv.get("status") == "pending")
    pending_payments = sum(1 for inv in invoices if inv.get("payment_status") in {"pending", "approved"})

    # 5. Recent Notifications
    notifications = []
    if user_id:
        notif_ids: list[Any] = [str(user_id)]
        if oid(user_id):
            notif_ids.append(oid(user_id))
        notif_ids.extend(v_ids)
        notifications = await db.notifications.find(
            {"$or": [{"user_id": {"$in": notif_ids}}, {"receiver_id": {"$in": notif_ids}}]}
        ).sort("created_at", -1).limit(10).to_list(10)

    return {
        "vendor": vendor,
        "total_assigned": len(requests),
        "pending_responses": pending_responses,
        "accepted_requests": accepted_reqs,
        "rejected_requests": rejected_reqs,
        "total_purchase_orders": total_pos,
        "pending_orders": pending_orders,
        "accepted_orders": accepted_orders,
        "delivered_orders": delivered_orders,
        "pending_deliveries": pending_deliveries,
        "pending_invoices": pending_invoices,
        "pending_payments": pending_payments,
        "requests": requests,
        "purchase_orders": pos,
        "deliveries": deliveries,
        "invoices": invoices,
        "recent_notifications": notifications,
    }
