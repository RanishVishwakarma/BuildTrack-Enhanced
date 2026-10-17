import csv
import io
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.core.config import BASE_DIR
from app.core.audit import record_audit
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.auth.db import create_user as create_auth_user, get_user_by_email
from app.modules.auth.models import UserCreate
from app.modules.notifications.db import create_notification
from app.modules.procurement.db import (
    assign_vendor_to_material_request,
    approve_material_request,
    create_delivery_and_inventory,
    create_doc,
    create_material_request,
    create_payment_for_invoice,
    create_purchase_order_from_request,
    dashboard_stats,
    delete_doc,
    get_doc,
    get_inventory_history,
    list_docs,
    list_materials_from_inventory,
    oid,
    sync_delivery_inventory,
    update_doc,
    update_invoice_status,
    update_purchase_order,
    vendor_dashboard_stats,
    vendor_respond_to_request,
)
from app.modules.procurement.models import (
    ApprovalAction,
    DashboardStats,
    Delivery,
    DeliveryCreate,
    DeliveryUpdate,
    InventoryItem,
    Invoice,
    InvoiceAction,
    InvoiceCreate,
    InvoiceUpdate,
    MaterialItem,
    MaterialRequest,
    MaterialRequestCreate,
    MaterialRequestUpdate,
    Payment,
    PaymentCreate,
    PaymentUpdate,
    PORejectPayload,
    PurchaseOrder,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    Vendor,
    VendorAssignment,
    VendorCreate,
    VendorCreateWithAccount,
    VendorDashboardStats,
    VendorDeliveryCreate,
    VendorDeliveryUpdate,
    VendorInvoiceCreate,
    VendorResponseAction,
    VendorUpdate,
)

router = APIRouter()
UPLOAD_DIR = BASE_DIR / "uploads" / "invoices"


# Stored role values (canonical and legacy) for admins and project managers.
MANAGER_ROLE_VALUES = ["admin", "Admin", "Administrator", "projectmanager", "manager", "Project Manager", "project_manager"]


def require_vendor(user: dict) -> str:
    """Ensure the logged-in user is a vendor and return vendor_id."""
    if str(user.get("role") or "").lower() != "vendor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vendor access required")
    vendor_id = user.get("vendor_id")
    if vendor_id:
        return str(vendor_id)
    # If not explicitly set, fall back to user _id as vendor identifier
    return str(user.get("_id", ""))


async def resolve_vendor_id(db, user: dict) -> str:
    """Ensure the logged-in user is a vendor linked to a vendor record and return resolved vendor_id."""
    if str(user.get("role") or "").lower() != "vendor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Vendor access required")
    vendor_id = user.get("vendor_id")
    if vendor_id:
        return str(vendor_id)

    # Auto-resolve vendor by email or name if vendor_id wasn't populated
    user_email = user.get("email")
    user_id_str = str(user.get("_id", ""))
    vendor = await db.vendors.find_one({
        "$or": [
            {"email": user_email},
            {"contact_person": user.get("full_name") or user.get("name")},
            {"vendor_name": user.get("full_name") or user.get("name")},
        ]
    })
    if vendor:
        resolved_id = str(vendor["_id"])
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"vendor_id": resolved_id}})
        return resolved_id

    return user_id_str


async def notify_vendor_user(db, vendor_id: str, notification_data: dict):
    """Notify all user accounts linked to the given vendor record."""
    v_ids = [str(vendor_id)]
    if oid(vendor_id):
        v_ids.append(oid(vendor_id))

    users = await db.users.find({
        "role": {"$regex": "^vendor$", "$options": "i"},
        "$or": [
            {"vendor_id": {"$in": v_ids}},
            {"_id": {"$in": v_ids}},
        ],
    }).to_list(50)

    if not users:
        # Check by vendor doc email
        vendor = await db.vendors.find_one({"_id": oid(vendor_id)}) if oid(vendor_id) else None
        if vendor and vendor.get("email"):
            users = await db.users.find({"email": vendor["email"]}).to_list(10)

    for vendor_user in users:
        data = dict(notification_data)
        data["user_id"] = str(vendor_user["_id"])
        await create_notification(db, data)


def serialize(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value


def serialize_doc(doc: dict) -> dict:
    return serialize(dict(doc))


def page(items: dict) -> dict:
    return {"items": [serialize_doc(item) for item in items["items"]], "total": items["total"]}


def normalize_inventory(doc: dict) -> dict:
    """Bring any `inventory` document (regardless of which schema created it) into
    the unified shape the procurement UI expects: material + stock_quantity."""
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    d["material"] = d.get("material") or d.get("material_name") or "Unnamed Item"
    try:
        d["stock_quantity"] = float(d.get("stock_quantity") or d.get("quantity") or 0)
    except (TypeError, ValueError):
        d["stock_quantity"] = 0
    d["transactions"] = serialize(d.get("transactions") or [])
    return serialize_doc(d)


# Procurement duty groups expressed as permissions (app.core.permissions).
GROUP_PERMISSIONS = {
    "project_manager": "procurement.request.review",
    "site_engineer": "procurement.request.create",
    "store_manager": "procurement.delivery.receive",
}


def require_role(user: dict, group: str):
    permission = GROUP_PERMISSIONS.get(group)
    if permission is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient procurement permissions")
    ensure_permission(user, permission)



FINANCE_READ_PERMISSIONS = ("budget.read.assigned", "procurement.invoice.manage", "procurement.payment.record")
FINANCIAL_COLLECTIONS = {"invoices", "payments"}


async def guard_procurement_read(db, user: dict, collection: str | None = None, record_id: str | None = None, allow_vendor_list: bool = False, financial: bool = False) -> None:
    """Internal readers need procurement.read.assigned, plus a finance or budget
    permission for invoices and payments. Vendors may only read records
    carrying their own vendor_id (or lists that filter by it)."""
    if user.get("role") == "vendor":
        vendor_id = str(user.get("vendor_id") or "")
        if allow_vendor_list and vendor_id:
            return
        if vendor_id and collection and record_id:
            record = await get_doc(db, collection, record_id)
            if record and vendor_id in {str(record.get("vendor_id") or ""), str(record.get("assigned_vendor_id") or "")}:
                return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    ensure_permission(user, "procurement.read.assigned")
    if financial or collection in FINANCIAL_COLLECTIONS:
        ensure_permission(user, *FINANCE_READ_PERMISSIONS)


def list_params(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    search: str | None = None,
    sort_by: str = "created_at",
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
):
    return skip, limit, search, sort_by, -1 if sort_dir == "desc" else 1


def money(value) -> str:
    try:
        return f"Rs {float(value):,.2f}"
    except (TypeError, ValueError):
        return "Rs 0.00"


def short_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d %b, %Y")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d %b, %Y")
        except ValueError:
            return value
    return "-"


def draw_document_template(pdf: canvas.Canvas, *, title: str, number: str, accent: colors.Color):
    width, height = letter
    dark = colors.HexColor("#1f2933")
    light = colors.HexColor("#eef2f7")

    pdf.setFillColor(dark)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, height - 66, "BUILD")
    pdf.setFillColor(accent)
    pdf.drawString(56, height - 79, "TRACK")

    pdf.setFillColor(dark)
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(width - 56, height - 66, f"NO. {number}")

    pdf.setFont("Helvetica-Bold", 48)
    pdf.drawString(56, height - 140, title)

    pdf.setFillColor(light)
    pdf.rect(56, 390, width - 112, 26, fill=1, stroke=0)
    pdf.setFillColor(dark)

    pdf.setFillColor(colors.HexColor("#d7dde5"))
    pdf.roundRect(-30, -90, 360, 150, 28, fill=1, stroke=0)
    pdf.setFillColor(accent)
    pdf.roundRect(185, -100, 520, 170, 36, fill=1, stroke=0)
    pdf.setFillColor(dark)


def draw_table_header(pdf: canvas.Canvas, y: int, columns: list[tuple[str, int]]):
    pdf.setFont("Helvetica-Bold", 10)
    for label, x in columns:
        pdf.drawString(x, y, label)


def draw_total_row(pdf: canvas.Canvas, y: int, label: str, amount: str):
    pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
    pdf.line(60, y + 18, 552, y + 18)
    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(390, y, label)
    pdf.drawRightString(552, y, amount)


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user)
    return serialize_doc(await dashboard_stats(db))


@router.post("/vendors", response_model=Vendor)
async def create_vendor(vendor: VendorCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "procurement.vendor.manage")
    return Vendor(**serialize_doc(await create_doc(db, "vendors", vendor.model_dump(), current_user)))


@router.post("/vendors/create-account")
async def create_vendor_with_account(
    payload: VendorCreateWithAccount,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Administrator-only endpoint.

    Atomically creates:
      1. A Vendor document (company record).
      2. A User document with role='vendor' linked via vendor_id.

    If ``create_login_account`` is False only the vendor record is created
    (identical to POST /vendors).
    """

    ensure_permission(current_user, "users.create")

    # -- Validate login-account fields when requested --
    if payload.create_login_account:
        if not payload.password or len(payload.password.strip()) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required (min 6 characters) when creating a login account",
            )

        # Check email uniqueness in users collection
        existing_user = await get_user_by_email(db, payload.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is already registered as a user account",
            )

    # -- Step 1: Create Vendor record --
    vendor_data = payload.model_dump(
        exclude={"create_login_account", "password"},
    )
    vendor_doc = await create_doc(db, "vendors", vendor_data, current_user)
    vendor_id = str(vendor_doc["_id"])

    result = {
        "vendor": serialize_doc(vendor_doc),
        "message": "Vendor created successfully",
        "user_created": False,
    }

    # -- Step 2 (optional): Create User login account --
    if payload.create_login_account:
        try:
            user_create = UserCreate(
                email=payload.email,
                full_name=payload.contact_person or payload.vendor_name,
                role="vendor",
                status="active",
                vendor_id=vendor_id,
                password=payload.password,
            )
            user_doc = await create_auth_user(db, user_create)

            # Return safe user info — NEVER the password_hash
            safe_user = {
                "_id": str(user_doc["_id"]),
                "email": user_doc["email"],
                "full_name": user_doc["full_name"],
                "role": user_doc["role"],
                "status": user_doc.get("status", "active"),
                "vendor_id": user_doc.get("vendor_id"),
            }

            result["user"] = safe_user
            result["user_created"] = True
            result["message"] = (
                f"Vendor and login account created successfully. "
                f"Login email: {payload.email}"
            )
        except Exception as exc:
            # Rollback: remove the just-created vendor if user creation fails
            await db.vendors.delete_one({"_id": vendor_doc["_id"]})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Vendor was rolled back — user account creation failed: {exc}",
            )

    return result


@router.get("/vendors")
async def vendors(params=Depends(list_params), status_filter: str | None = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user)
    skip, limit, search, sort_by, sort_dir = params
    filters = {"status": status_filter} if status_filter else None
    return page(await list_docs(db, "vendors", skip, limit, search, ["vendor_name", "contact_person", "email", "phone"], filters, sort_by, sort_dir))


@router.get("/vendors/active")
async def active_vendors(params=Depends(list_params), current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user)
    skip, limit, search, sort_by, sort_dir = params
    return page(await list_docs(db, "vendors", skip, limit, search, ["vendor_name", "contact_person", "email", "phone"], {"status": "active"}, sort_by, sort_dir))


@router.get("/vendors/{vendor_id}", response_model=Vendor)
async def get_vendor(vendor_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user)
    doc = await get_doc(db, "vendors", vendor_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return Vendor(**serialize_doc(doc))


@router.put("/vendors/{vendor_id}", response_model=Vendor)
async def edit_vendor(vendor_id: str, vendor: VendorUpdate, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "procurement.vendor.manage")
    doc = await update_doc(db, "vendors", vendor_id, vendor.model_dump(exclude_unset=True), current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return Vendor(**serialize_doc(doc))


@router.delete("/vendors/{vendor_id}")
async def remove_vendor(vendor_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "records.delete")
    if not await delete_doc(db, "vendors", vendor_id, current_user):
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted successfully"}


@router.post("/material-requests", response_model=MaterialRequest)
async def create_request(request: MaterialRequestCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "site_engineer")
    created, error = await create_material_request(db, request.model_dump(), current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)
    mr_id = str(created["_id"])
    req_no = created.get("request_id", mr_id)

    await create_notification(db, {
        "user_id": str(current_user["_id"]),
        "title": "Material Request Created",
        "message": f"Material request '{req_no}' for '{created.get('material_name', 'Material')}' created.",
        "type": "info",
        "category": "procurement_alert",
        "entity_type": "procurement",
        "entity_id": mr_id,
    })

    return MaterialRequest(**serialize_doc(created))


@router.get("/material-requests")
async def material_requests(params=Depends(list_params), status_filter: str | None = None, priority: str | None = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, allow_vendor_list=True)
    skip, limit, search, sort_by, sort_dir = params
    filters = {}
    # Vendors only see procurement requests assigned to their own vendor record.
    if current_user.get("role") == "vendor":
        vendor_id = current_user.get("vendor_id")
        if not vendor_id:
            raise HTTPException(status_code=403, detail="Account is not linked to a vendor record")
        filters["$or"] = [{"vendor_id": str(vendor_id)}, {"assigned_vendor_id": str(vendor_id)}]
    if status_filter:
        filters["status"] = status_filter
    if priority:
        filters["priority"] = priority
    return page(await list_docs(db, "material_requests", skip, limit, search, ["request_id", "project", "material_name", "status"], filters or None, sort_by, sort_dir))


@router.get("/material-requests/{request_id}", response_model=MaterialRequest)
async def get_request(request_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, "material_requests", request_id)
    doc = await get_doc(db, "material_requests", request_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Material request not found")
    return MaterialRequest(**serialize_doc(doc))


@router.put("/material-requests/{request_id}", response_model=MaterialRequest)
async def edit_request(request_id: str, request: MaterialRequestUpdate, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "site_engineer")
    doc = await update_doc(db, "material_requests", request_id, request.model_dump(exclude_unset=True), current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Material request not found")
    return MaterialRequest(**serialize_doc(doc))


@router.delete("/material-requests/{request_id}")
async def remove_material_request(request_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "site_engineer")
    if not await delete_doc(db, "material_requests", request_id, current_user):
        raise HTTPException(status_code=404, detail="Material request not found")
    return {"message": "Material request deleted successfully"}


@router.patch("/material-requests/{request_id}/approval", response_model=MaterialRequest)
async def approve_request(request_id: str, action: ApprovalAction, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "project_manager")
    doc = await approve_material_request(db, request_id, action.status, action.comments, current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Material request not found")

    target_user = doc.get("requested_by") or str(current_user["_id"])
    req_no = doc.get("request_id", request_id)
    await create_notification(db, {
        "user_id": str(target_user),
        "title": f"Material Request {action.status.capitalize()}",
        "message": f"Material request '{req_no}' has been {action.status}.",
        "type": "success" if action.status == "approved" else "alert",
        "category": "procurement_alert",
        "entity_type": "procurement",
        "entity_id": request_id,
    })

    return MaterialRequest(**serialize_doc(doc))


@router.put("/material-requests/{request_id}/assign-vendor", response_model=MaterialRequest)
async def assign_vendor(request_id: str, assignment: VendorAssignment, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "project_manager")
    doc, error = await assign_vendor_to_material_request(db, request_id, assignment.vendor_id, current_user)
    if error:
        status_code = 404 if error in {"Material request not found", "Vendor not found"} else 400
        raise HTTPException(status_code=status_code, detail=error)

    req_no = doc.get("request_id", request_id)
    await create_notification(db, {
        "user_id": str(current_user["_id"]),
        "title": "Vendor Assigned",
        "message": f"Vendor assigned to material request '{req_no}'.",
        "type": "success",
        "category": "procurement_alert",
        "entity_type": "procurement",
        "entity_id": request_id,
    })
    if doc.get("vendor_id"):
        await notify_vendor_user(db, str(doc["vendor_id"]), {
            "title": "New Procurement Request",
            "message": f"A material request '{req_no}' has been assigned to you. Please review and respond.",
            "type": "info",
            "category": "procurement_alert",
            "entity_type": "procurement",
            "entity_id": request_id,
        })
    return MaterialRequest(**serialize_doc(doc))


@router.get("/materials", response_model=list[MaterialItem])
async def materials(current_user=Depends(get_current_user), db=Depends(get_database)):
    """List available materials from the inventory master (with stock + unit)."""
    ensure_permission(current_user, "procurement.read.assigned", "procurement.request.create")
    docs = await list_materials_from_inventory(db)
    items = []
    for d in docs:
        d = dict(d)
        d["_id"] = str(d["_id"])
        d["material"] = d.get("material") or d.get("material_name") or "Unnamed Item"
        try:
            d["available_stock"] = float(d.get("stock_quantity") or d.get("quantity") or 0)
        except (TypeError, ValueError):
            d["available_stock"] = 0
        d.setdefault("material_name", d["material"])
        d.setdefault("unit", "Nos")
        d.setdefault("status", d.get("status") or "in_stock")
        items.append(MaterialItem(**d))
    return items


@router.post("/material-requests/{request_id}/vendor-accept", response_model=MaterialRequest)
async def vendor_accept(request_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_vendor(current_user)
    doc, error = await vendor_respond_to_request(db, request_id, "accept", None, current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)
    await create_notification(db, {
        "user_id": str(current_user["_id"]),
        "title": "Request Accepted",
        "message": f"Vendor accepted procurement request '{doc.get('request_id', request_id)}'.",
        "type": "success",
        "category": "procurement_alert",
        "entity_type": "procurement",
        "entity_id": request_id,
    })
    return MaterialRequest(**serialize_doc(doc))


@router.post("/material-requests/{request_id}/vendor-reject", response_model=MaterialRequest)
async def vendor_reject(request_id: str, payload: VendorResponseAction, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_vendor(current_user)
    doc, error = await vendor_respond_to_request(db, request_id, "reject", payload.comment, current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)
    await create_notification(db, {
        "user_id": str(current_user["_id"]),
        "title": "Request Rejected",
        "message": f"Vendor rejected procurement request '{doc.get('request_id', request_id)}'. Reason: {payload.comment or 'N/A'}",
        "type": "warning",
        "category": "procurement_alert",
        "entity_type": "procurement",
        "entity_id": request_id,
    })
    return MaterialRequest(**serialize_doc(doc))


@router.get("/vendor/dashboard", response_model=VendorDashboardStats)
async def vendor_dashboard(current_user=Depends(get_current_user), db=Depends(get_database)):
    vendor_id = await resolve_vendor_id(db, current_user)
    user_id = str(current_user.get("_id", ""))
    raw_stats = await vendor_dashboard_stats(db, vendor_id, user_id)
    stats = serialize_doc(raw_stats)

    return VendorDashboardStats(
        vendor=Vendor(**stats["vendor"]) if stats.get("vendor") else None,
        total_assigned=stats["total_assigned"],
        pending_responses=stats["pending_responses"],
        accepted_requests=stats["accepted_requests"],
        rejected_requests=stats["rejected_requests"],
        total_purchase_orders=stats["total_purchase_orders"],
        pending_orders=stats["pending_orders"],
        accepted_orders=stats["accepted_orders"],
        delivered_orders=stats["delivered_orders"],
        pending_deliveries=stats["pending_deliveries"],
        pending_invoices=stats["pending_invoices"],
        pending_payments=stats["pending_payments"],
        requests=[MaterialRequest(**r) for r in stats.get("requests", [])],
        purchase_orders=[PurchaseOrder(**po) for po in stats.get("purchase_orders", [])],
        deliveries=[Delivery(**d) for d in stats.get("deliveries", [])],
        invoices=[Invoice(**inv) for inv in stats.get("invoices", [])],
        recent_notifications=stats.get("recent_notifications", []),
    )


@router.get("/vendor/material-requests")
async def vendor_material_requests(
    params=Depends(list_params),
    status_filter: str | None = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor view of material requests assigned to them."""
    vendor_id = await resolve_vendor_id(db, current_user)
    user_id = str(current_user.get("_id", ""))
    vendor = await get_doc(db, "vendors", vendor_id)

    v_ids = [str(vendor_id)]
    if oid(vendor_id):
        v_ids.append(oid(vendor_id))
    if user_id:
        v_ids.append(str(user_id))
        if oid(user_id):
            v_ids.append(oid(user_id))
    if vendor:
        v_ids.append(str(vendor["_id"]))
        v_ids.append(vendor["_id"])

    req_conditions = [
        {"vendor_id": {"$in": v_ids}},
        {"assigned_vendor_id": {"$in": v_ids}},
    ]
    if vendor and vendor.get("vendor_name"):
        req_conditions.append({"vendor_name": vendor["vendor_name"]})

    filters: dict = {"$or": req_conditions}
    if status_filter and status_filter.lower() != "all":
        s = status_filter.lower()
        if s == "pending":
            status_match = {"$in": ["vendor_assigned", "sent_to_vendor", "pending"]}
        elif s == "accepted":
            status_match = {"$in": ["vendor_accepted", "po_generated", "po_sent"]}
        elif s == "rejected":
            status_match = "vendor_rejected"
        else:
            status_match = status_filter
        filters = {"$and": [{"$or": req_conditions}, {"status": status_match}]}

    skip, limit, search, sort_by, sort_dir = params
    return page(await list_docs(db, "material_requests", skip, limit, search, ["request_id", "project", "material_name", "status", "priority"], filters, sort_by, sort_dir))


@router.post("/vendor/material-requests/{request_id}/accept", response_model=MaterialRequest)
async def vendor_accept_material_request(
    request_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor accepts an assigned material request."""
    vendor_id = require_vendor(current_user)
    doc, error = await vendor_respond_to_request(db, request_id, "accept", None, current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)

    req_no = doc.get("request_id", request_id)
    vendor_name = current_user.get("full_name") or "Vendor"
    # Notify admin & project managers
    managers = await db.users.find({"role": {"$in": MANAGER_ROLE_VALUES}}).to_list(20)
    for u in managers:
        await create_notification(db, {
            "user_id": str(u["_id"]),
            "title": "Material Request Accepted by Vendor",
            "message": f"Vendor '{vendor_name}' accepted material request '{req_no}'. You can now generate a Purchase Order.",
            "type": "success",
            "category": "procurement_alert",
            "entity_type": "procurement",
            "entity_id": request_id,
        })

    return MaterialRequest(**serialize_doc(doc))


@router.post("/vendor/material-requests/{request_id}/reject", response_model=MaterialRequest)
async def vendor_reject_material_request(
    request_id: str,
    payload: PORejectPayload,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor rejects an assigned material request with reason."""
    vendor_id = require_vendor(current_user)
    doc, error = await vendor_respond_to_request(db, request_id, "reject", payload.reason, current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)

    req_no = doc.get("request_id", request_id)
    vendor_name = current_user.get("full_name") or "Vendor"
    managers = await db.users.find({"role": {"$in": MANAGER_ROLE_VALUES}}).to_list(20)
    for u in managers:
        await create_notification(db, {
            "user_id": str(u["_id"]),
            "title": "Material Request Rejected by Vendor",
            "message": f"Vendor '{vendor_name}' rejected material request '{req_no}'. Reason: {payload.reason}",
            "type": "alert",
            "category": "procurement_alert",
            "entity_type": "procurement",
            "entity_id": request_id,
        })

    return MaterialRequest(**serialize_doc(doc))


@router.get("/vendor/purchase-orders")
async def vendor_purchase_orders(
    params=Depends(list_params),
    status_filter: str | None = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor view of their purchase orders ONLY (strictly isolated by JWT vendor_id)."""
    vendor_id = require_vendor(current_user)
    skip, limit, search, sort_by, sort_dir = params
    filters: dict = {"vendor_id": vendor_id}
    if status_filter and status_filter.lower() != "all":
        s = status_filter.lower()
        if s == "pending":
            filters["status"] = {"$in": ["created", "sent"]}
        elif s == "accepted":
            filters["status"] = "accepted"
        elif s in {"completed", "delivered"}:
            filters["status"] = {"$in": ["delivered", "received"]}
        elif s == "rejected":
            filters["status"] = "rejected"
        else:
            filters["status"] = status_filter

    return page(await list_docs(db, "purchase_orders", skip, limit, search, ["po_number", "project", "materials", "status"], filters, sort_by, sort_dir))


@router.post("/vendor/purchase-orders/{po_id}/accept", response_model=PurchaseOrder)
async def vendor_accept_purchase_order(
    po_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor accepts a Purchase Order."""
    vendor_id = require_vendor(current_user)
    existing = await get_doc(db, "purchase_orders", po_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if str(existing.get("vendor_id") or "") != vendor_id:
        raise HTTPException(status_code=403, detail="You are not authorized for this purchase order")
    if existing.get("status") not in {"created", "sent"}:
        raise HTTPException(status_code=400, detail=f"Purchase order cannot be accepted in status '{existing.get('status')}'")

    doc = await update_purchase_order(db, po_id, {"status": "accepted"}, current_user)
    request_id = doc.get("request_id")
    if request_id:
        await update_doc(db, "material_requests", request_id, {"status": "po_accepted"}, current_user)

    po_no = doc.get("po_number", po_id)
    vendor_name = current_user.get("full_name") or "Vendor"
    # Notify admins/managers
    admin_users = await db.users.find({"role": {"$in": MANAGER_ROLE_VALUES}}).to_list(20)
    for u in admin_users:
        await create_notification(db, {
            "user_id": str(u["_id"]),
            "title": "PO Accepted by Vendor",
            "message": f"Vendor '{vendor_name}' accepted Purchase Order '{po_no}'.",
            "type": "success",
            "category": "procurement_alert",
            "entity_type": "purchase_order",
            "entity_id": po_id,
        })

    return PurchaseOrder(**serialize_doc(doc))


@router.post("/vendor/purchase-orders/{po_id}/reject", response_model=PurchaseOrder)
async def vendor_reject_purchase_order(
    po_id: str,
    payload: PORejectPayload,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor rejects a Purchase Order with required reason."""
    vendor_id = require_vendor(current_user)
    existing = await get_doc(db, "purchase_orders", po_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if str(existing.get("vendor_id") or "") != vendor_id:
        raise HTTPException(status_code=403, detail="You are not authorized for this purchase order")
    if existing.get("status") not in {"created", "sent"}:
        raise HTTPException(status_code=400, detail=f"Purchase order cannot be rejected in status '{existing.get('status')}'")

    doc = await update_purchase_order(db, po_id, {"status": "rejected", "rejection_reason": payload.reason}, current_user)
    po_no = doc.get("po_number", po_id)
    vendor_name = current_user.get("full_name") or "Vendor"

    # Notify admins/managers
    admin_users = await db.users.find({"role": {"$in": MANAGER_ROLE_VALUES}}).to_list(20)
    for u in admin_users:
        await create_notification(db, {
            "user_id": str(u["_id"]),
            "title": "PO Rejected by Vendor",
            "message": f"Vendor '{vendor_name}' rejected Purchase Order '{po_no}'. Reason: {payload.reason}",
            "type": "alert",
            "category": "procurement_alert",
            "entity_type": "purchase_order",
            "entity_id": po_id,
        })

    return PurchaseOrder(**serialize_doc(doc))


@router.get("/vendor/deliveries")
async def vendor_deliveries(
    params=Depends(list_params),
    status_filter: str | None = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor view of deliveries for their purchase orders."""
    vendor_id = require_vendor(current_user)
    skip, limit, search, sort_by, sort_dir = params
    filters: dict = {"vendor_id": vendor_id}
    if status_filter and status_filter.lower() != "all":
        filters["status"] = status_filter

    return page(await list_docs(db, "deliveries", skip, limit, search, ["material", "status", "vehicle_number", "tracking_number"], filters, sort_by, sort_dir))


@router.post("/vendor/deliveries", response_model=Delivery)
async def vendor_create_delivery(
    payload: VendorDeliveryCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor logs/dispatches a delivery against their accepted Purchase Order."""
    vendor_id = require_vendor(current_user)
    po = await get_doc(db, "purchase_orders", payload.purchase_order_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if str(po.get("vendor_id") or "") != vendor_id:
        raise HTTPException(status_code=403, detail="You are not the vendor for this purchase order")
    if po.get("status") not in {"accepted", "processing", "shipped"}:
        raise HTTPException(status_code=400, detail="Delivery can only be created for accepted purchase orders")

    delivery_data = {
        "purchase_order_id": payload.purchase_order_id,
        "po_number": po.get("po_number"),
        "vendor_id": vendor_id,
        "material": po.get("materials", "Materials"),
        "quantity_received": payload.quantity,
        "quality_status": "pending",
        "delivery_date": datetime.utcnow(),
        "dispatch_date": payload.dispatch_date or datetime.utcnow(),
        "vehicle_number": payload.vehicle_number,
        "tracking_number": payload.tracking_number,
        "remarks": payload.remarks,
        "status": payload.status or "shipped",
    }
    doc = await create_doc(db, "deliveries", delivery_data, current_user)
    
    # Update PO status to shipped/processing if appropriate
    if payload.status in {"shipped", "delivered"}:
        await update_doc(db, "purchase_orders", payload.purchase_order_id, {"status": payload.status}, current_user)

    # Notify Store Managers & Project Managers
    store_managers = await db.users.find({"$or": [{"role": {"$in": MANAGER_ROLE_VALUES}}, {"permissions": "procurement.delivery.receive"}]}).to_list(20)
    for u in store_managers:
        await create_notification(db, {
            "user_id": str(u["_id"]),
            "title": "Delivery Dispatched by Vendor",
            "message": f"Vendor dispatched delivery for PO '{po.get('po_number')}'. Material: {po.get('materials')}, Qty: {payload.quantity}.",
            "type": "info",
            "category": "procurement_alert",
            "entity_type": "delivery",
            "entity_id": str(doc["_id"]),
        })

    return Delivery(**serialize_doc(doc))


@router.put("/vendor/deliveries/{delivery_id}", response_model=Delivery)
async def vendor_update_delivery(
    delivery_id: str,
    payload: VendorDeliveryUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor updates delivery status (e.g. processing, shipped, delivered)."""
    vendor_id = require_vendor(current_user)
    existing = await get_doc(db, "deliveries", delivery_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if str(existing.get("vendor_id") or "") != vendor_id:
        raise HTTPException(status_code=403, detail="You are not authorized for this delivery")

    update_data = payload.model_dump(exclude_unset=True)
    doc = await update_doc(db, "deliveries", delivery_id, update_data, current_user)
    return Delivery(**serialize_doc(doc))


@router.get("/vendor/invoices")
async def vendor_invoices(
    params=Depends(list_params),
    status_filter: str | None = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor view of invoices submitted by them."""
    vendor_id = require_vendor(current_user)
    skip, limit, search, sort_by, sort_dir = params
    filters: dict = {"vendor_id": vendor_id}
    if status_filter and status_filter.lower() != "all":
        filters["status"] = status_filter

    return page(await list_docs(db, "invoices", skip, limit, search, ["invoice_number", "status", "payment_status"], filters, sort_by, sort_dir))


@router.post("/vendor/invoices", response_model=Invoice)
async def vendor_create_invoice(
    invoice: VendorInvoiceCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor submits an invoice for their purchase order."""
    vendor_id = await resolve_vendor_id(db, current_user)
    po = await get_doc(db, "purchase_orders", invoice.purchase_order_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if str(po.get("vendor_id") or "") != str(vendor_id) and str(po.get("vendor_id") or "") != str(current_user.get("_id")):
        raise HTTPException(status_code=403, detail="You are not the vendor for this purchase order")

    # Check for duplicate invoice number
    existing_inv = await db.invoices.find_one({"invoice_number": invoice.invoice_number})
    if existing_inv:
        raise HTTPException(status_code=400, detail="An invoice with this invoice number already exists")

    inv_data = invoice.model_dump()
    inv_data["vendor_id"] = str(vendor_id)
    inv_data["status"] = "pending"
    inv_data["payment_status"] = "pending"

    doc = await create_doc(db, "invoices", inv_data, current_user)

    # Notify Finance and Admins
    finance_users = await db.users.find({"$or": [{"role": {"$in": MANAGER_ROLE_VALUES}}, {"permissions": "procurement.payment.record"}]}).to_list(20)
    for u in finance_users:
        await create_notification(db, {
            "user_id": str(u["_id"]),
            "title": "New Vendor Invoice Submitted",
            "message": f"Vendor submitted invoice '{invoice.invoice_number}' for PO '{po.get('po_number')}'. Amount: ₹{invoice.amount:,.2f}.",
            "type": "info",
            "category": "procurement_alert",
            "entity_type": "invoice",
            "entity_id": str(doc["_id"]),
        })

    return Invoice(**serialize_doc(doc))


@router.get("/vendor/profile", response_model=Vendor)
async def get_vendor_profile(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get the profile of the currently logged-in vendor."""
    vendor_id = require_vendor(current_user)
    doc = await get_doc(db, "vendors", vendor_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Vendor record not found")
    return Vendor(**serialize_doc(doc))


@router.put("/vendor/profile", response_model=Vendor)
async def update_vendor_profile(
    vendor_update: VendorUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Vendor updates their own company details."""
    vendor_id = require_vendor(current_user)
    allowed_update = vendor_update.model_dump(exclude_unset=True, exclude={"rating", "status"})
    doc = await update_doc(db, "vendors", vendor_id, allowed_update, current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Vendor record not found")
    return Vendor(**serialize_doc(doc))


@router.get("/inventory/history")
async def inventory_history(material_id: str | None = Query(None), current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user)
    history = await get_inventory_history(db, material_id)
    return serialize(history)


@router.delete("/material-requests/{request_id}")
async def remove_request(request_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "records.delete")
    if not await delete_doc(db, "material_requests", request_id, current_user):
        raise HTTPException(status_code=404, detail="Material request not found")
    return {"message": "Material request deleted successfully"}


@router.post("/purchase-orders", response_model=PurchaseOrder)
async def create_po(po: PurchaseOrderCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "project_manager")
    doc, error = await create_purchase_order_from_request(db, po.model_dump(), current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)

    po_id = str(doc["_id"])
    po_no = doc.get("po_number", po_id)
    await create_notification(db, {
        "user_id": str(current_user["_id"]),
        "title": "Purchase Order Created",
        "message": f"Purchase Order '{po_no}' created for project '{doc.get('project', '')}'.",
        "type": "success",
        "category": "procurement_alert",
        "entity_type": "procurement",
        "entity_id": po_id,
    })
    if doc.get("vendor_id"):
        await notify_vendor_user(db, str(doc["vendor_id"]), {
            "title": "Purchase Order Generated",
            "message": f"A purchase order '{po_no}' has been generated for your accepted request.",
            "type": "success",
            "category": "procurement_alert",
            "entity_type": "procurement",
            "entity_id": po_id,
        })

    return PurchaseOrder(**serialize_doc(doc))


async def list_purchase_orders(db, skip: int = 0, limit: int = 10):
    res = await list_docs(db, "purchase_orders", skip, limit)
    return res["items"]


async def list_invoices(db, skip: int = 0, limit: int = 10):
    res = await list_docs(db, "invoices", skip, limit)
    return res["items"]


@router.get("/purchase-orders")
async def purchase_orders(params=Depends(list_params), status_filter: str | None = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, allow_vendor_list=True)
    skip, limit, search, sort_by, sort_dir = params
    filters = {}
    if current_user.get("role") == "vendor":
        vendor_id = current_user.get("vendor_id")
        if not vendor_id:
            raise HTTPException(status_code=403, detail="Account is not linked to a vendor record")
        filters["vendor_id"] = str(vendor_id)
    if status_filter:
        filters["status"] = status_filter
    return page(await list_docs(db, "purchase_orders", skip, limit, search, ["po_number", "project", "materials", "status"], filters or None, sort_by, sort_dir))


@router.get("/invoices")
async def invoices(params=Depends(list_params), status_filter: str | None = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, financial=True)
    skip, limit, search, sort_by, sort_dir = params
    if search or status_filter:
        filters = {"status": status_filter} if status_filter else None
        return page(await list_docs(db, "invoices", skip, limit, search, ["invoice_number", "status", "payment_status"], filters, sort_by, sort_dir))
    res = await list_invoices(db, skip, limit)
    if isinstance(res, list):
        return [serialize_doc(item) for item in res]
    return page(res)


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrder)
async def get_po(po_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, "purchase_orders", po_id)
    doc = await get_doc(db, "purchase_orders", po_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return PurchaseOrder(**serialize_doc(doc))


@router.put("/purchase-orders/{po_id}", response_model=PurchaseOrder)
async def edit_po(po_id: str, po: PurchaseOrderUpdate, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "project_manager")
    doc = await update_purchase_order(db, po_id, po.model_dump(exclude_unset=True), current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return PurchaseOrder(**serialize_doc(doc))


@router.patch("/purchase-orders/{po_id}/status", response_model=PurchaseOrder)
async def change_po_status(po_id: str, po: PurchaseOrderUpdate, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "project_manager")
    if not po.status:
        raise HTTPException(status_code=400, detail="Status is required")
    doc = await update_purchase_order(db, po_id, {"status": po.status}, current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return PurchaseOrder(**serialize_doc(doc))


@router.put("/purchase-orders/{po_id}/send", response_model=PurchaseOrder)
async def send_po(po_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "project_manager")
    existing = await get_doc(db, "purchase_orders", po_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if not existing.get("vendor_id"):
        raise HTTPException(status_code=400, detail="Cannot send purchase order without an assigned vendor")
    doc = await update_purchase_order(db, po_id, {"status": "sent"}, current_user)
    request_id = doc.get("request_id")
    po_no = doc.get("po_number", po_id)
    if request_id:
        await update_doc(db, "material_requests", request_id, {"status": "po_sent"}, current_user)
    if doc.get("vendor_id"):
        await notify_vendor_user(db, str(doc["vendor_id"]), {
            "title": "Purchase Order Sent",
            "message": f"Purchase Order '{po_no}' has been sent to you. Please confirm.",
            "type": "info",
            "category": "procurement_alert",
            "entity_type": "procurement",
            "entity_id": po_id,
        })
    return PurchaseOrder(**serialize_doc(doc))


@router.put("/purchase-orders/{po_id}/accept", response_model=PurchaseOrder)
async def vendor_accept_po(po_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    """Vendor confirms the purchase order."""
    vendor_id = require_vendor(current_user)
    existing = await get_doc(db, "purchase_orders", po_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if str(existing.get("vendor_id") or "") != vendor_id:
        raise HTTPException(status_code=403, detail="You are not the vendor for this purchase order")
    if existing.get("status") not in {"created", "sent"}:
        raise HTTPException(status_code=400, detail="Purchase order is not in a confirmable state")
    doc = await update_purchase_order(db, po_id, {"status": "accepted"}, current_user)
    request_id = doc.get("request_id")
    if request_id:
        await update_doc(db, "material_requests", request_id, {"status": "po_accepted"}, current_user)
    return PurchaseOrder(**serialize_doc(doc))


@router.get("/purchase-orders/{po_id}/pdf")
async def po_pdf(po_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, "purchase_orders", po_id)
    doc = await get_doc(db, "purchase_orders", po_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    vendor = await get_doc(db, "vendors", doc.get("vendor_id", "")) if doc.get("vendor_id") else None

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    draw_document_template(pdf, title="PURCHASE ORDER", number=doc.get("po_number", po_id), accent=colors.HexColor("#2563eb"))

    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, 606, "Date:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(92, 606, short_date(doc.get("created_at")))

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, 560, "Vendor:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(56, 544, vendor.get("vendor_name", "-") if vendor else doc.get("vendor_id", "-"))
    pdf.drawString(56, 530, vendor.get("contact_person", "-") if vendor else "-")
    pdf.drawString(56, 516, vendor.get("email", "-") if vendor else "-")
    pdf.drawString(56, 502, vendor.get("phone", "-") if vendor else "-")

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(320, 560, "Project:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(320, 544, doc.get("project", "-"))
    pdf.drawString(320, 530, f"Request: {doc.get('request_id', '-')}")
    pdf.drawString(320, 516, f"Expected: {short_date(doc.get('expected_delivery_date'))}")
    pdf.drawString(320, 502, f"Status: {doc.get('status', '-')}")

    draw_table_header(pdf, 398, [("Item", 68), ("Quantity", 292), ("Unit Price", 382), ("Amount", 490)])
    quantity = float(doc.get("quantity", 0) or 0)
    unit_price = float(doc.get("unit_price", 0) or 0)
    total = float(doc.get("total_cost", quantity * unit_price) or 0)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(68, 366, doc.get("materials", "-"))
    pdf.drawRightString(330, 366, f"{quantity:g}")
    pdf.drawRightString(432, 366, money(unit_price))
    pdf.drawRightString(552, 366, money(total))
    draw_total_row(pdf, 322, "Total", money(total))

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, 266, "Note:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(92, 266, "Please supply materials as per approved request and expected delivery date.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={doc['po_number']}.pdf"})


@router.delete("/purchase-orders/{po_id}")
async def remove_po(po_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "project_manager")
    if not await delete_doc(db, "purchase_orders", po_id, current_user):
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return {"message": "Purchase order deleted successfully"}


@router.post("/deliveries", response_model=Delivery)
async def create_delivery(delivery: DeliveryCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "store_manager")
    doc = await create_delivery_and_inventory(db, delivery.model_dump(), current_user)
    d_id = str(doc["_id"])

    await create_notification(db, {
        "user_id": str(current_user["_id"]),
        "title": "Delivery Received",
        "message": f"Delivery for '{doc.get('material', 'materials')}' received and inventory updated.",
        "type": "success",
        "category": "procurement_alert",
        "entity_type": "procurement",
        "entity_id": d_id,
    })

    return Delivery(**serialize_doc(doc))



@router.get("/deliveries")
async def deliveries(params=Depends(list_params), status_filter: str | None = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user)
    skip, limit, search, sort_by, sort_dir = params
    filters = {"status": status_filter} if status_filter else None
    result = await list_docs(db, "deliveries", skip, limit, search, ["material", "status", "quality_status"], filters, sort_by, sort_dir)
    
    # Pre-fetch vendors and POs map for instant name resolution
    all_vendors = await db.vendors.find().to_list(200)
    vendor_map = {}
    for v in all_vendors:
        vendor_map[str(v["_id"])] = v.get("vendor_name") or "Vendor Partner"
        if v.get("user_id"):
            vendor_map[str(v["user_id"])] = v.get("vendor_name") or "Vendor Partner"

    all_pos = await db.purchase_orders.find().to_list(500)
    po_map = {str(p["_id"]): p for p in all_pos}

    enhanced_items = []
    for item in result["items"]:
        d = dict(item)
        po_id = str(d.get("purchase_order_id") or "")
        po = po_map.get(po_id)
        if po:
            d.setdefault("po_number", po.get("po_number"))
            d.setdefault("project", po.get("project"))
            if not d.get("vendor_id") and po.get("vendor_id"):
                d["vendor_id"] = str(po.get("vendor_id"))

        v_id = str(d.get("vendor_id") or "")
        if v_id in vendor_map:
            d["vendor_name"] = vendor_map[v_id]
        elif po and (po.get("vendor") or po.get("supplier")):
            d["vendor_name"] = po.get("vendor") or po.get("supplier")
        
        enhanced_items.append(serialize_doc(d))

    return {"items": enhanced_items, "total": result["total"]}


@router.put("/deliveries/{delivery_id}", response_model=Delivery)
async def edit_delivery(delivery_id: str, delivery: DeliveryUpdate, current_user=Depends(get_current_user), db=Depends(get_database)):
    require_role(current_user, "store_manager")
    doc = await update_doc(db, "deliveries", delivery_id, delivery.model_dump(exclude_unset=True), current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    # Reconcile inventory delta accurately without duplicate addition
    await sync_delivery_inventory(db, doc, current_user)
    return Delivery(**serialize_doc(doc))


@router.get("/inventory")
async def inventory(params=Depends(list_params), current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user)
    skip, limit, search, sort_by, sort_dir = params

    # Read the full inventory collection (source of truth used by the inventory
    # page) and normalise every document, regardless of whether it was created by
    # the inventory module (material_name/quantity) or by a procurement delivery
    # (material/stock_quantity). Records for the same material are merged so the
    # screen always reflects the actual, up-to-date stock.
    raw = await db.inventory.find().to_list(100000)
    merged: dict[str, dict] = {}
    for item in raw:
        norm = normalize_inventory(item)
        key = (norm.get("material") or "").strip().lower()
        if not key:
            continue
        existing = merged.get(key)
        if existing is None:
            merged[key] = norm
        else:
            existing_tx = existing.get("transactions") or []
            new_tx = norm.get("transactions") or []
            existing["transactions"] = existing_tx + new_tx
            # Keep the most recently updated stock as the accurate figure.
            norm_updated = norm.get("updated_at")
            exist_updated = existing.get("updated_at")
            if norm_updated and (not exist_updated or str(norm_updated) > str(exist_updated)):
                existing["stock_quantity"] = norm.get("stock_quantity", 0)
                existing["updated_at"] = norm_updated

    items = list(merged.values())
    if search:
        term = search.lower()
        items = [it for it in items if term in (it.get("material") or "").lower()]

    def inv_sort_key(item: dict):
        if sort_by == "material":
            return (item.get("material") or "").lower()
        val = item.get(sort_by)
        return str(val) if val is not None else ""

    items.sort(key=inv_sort_key, reverse=(sort_dir == -1))
    total = len(items)
    paged = [serialize_doc(it) for it in items[skip:skip + limit]]
    return {"items": paged, "total": total}


@router.post("/invoices", response_model=Invoice)
async def create_invoice(invoice: InvoiceCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "procurement.invoice.manage", "procurement.request.review")
    return Invoice(**serialize_doc(await create_doc(db, "invoices", invoice.model_dump(), current_user)))


@router.post("/invoices/upload")
async def upload_invoice_attachment(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    ensure_permission(current_user, "procurement.invoice.manage", "procurement.request.review")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "invoice_attachment").name.replace("\\", "_").replace("/", "_")
    content = await file.read()
    path = UPLOAD_DIR / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
    with path.open("wb") as uploaded:
        uploaded.write(content)
    return {"attachment_url": str(path.relative_to(BASE_DIR)).replace("\\", "/")}


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, "invoices", invoice_id)
    invoice = await get_doc(db, "invoices", invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    vendor = await get_doc(db, "vendors", invoice.get("vendor_id", "")) if invoice.get("vendor_id") else None
    po = await get_doc(db, "purchase_orders", invoice.get("purchase_order_id", "")) if invoice.get("purchase_order_id") else None

    amount = float(invoice.get("amount", 0) or 0)
    gst = float(invoice.get("gst", 0) or 0)
    total = amount + gst

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    accent_violet = colors.HexColor("#7c3aed")
    draw_document_template(pdf, title="INVOICE", number=invoice.get("invoice_number", invoice_id), accent=accent_violet)

    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, 606, "Invoice Date:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(118, 606, short_date(invoice.get("invoice_date")))

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, 560, "Vendor:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(56, 544, vendor.get("vendor_name", "-") if vendor else invoice.get("vendor_id", "-"))
    pdf.drawString(56, 530, vendor.get("contact_person", "-") if vendor else "-")
    pdf.drawString(56, 516, vendor.get("email", "-") if vendor else "-")
    pdf.drawString(56, 502, vendor.get("phone", "-") if vendor else "-")

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(320, 560, "Billed To / Project:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(320, 544, po.get("project", "-") if po else "BuildTrack Project")
    pdf.drawString(320, 530, f"PO Ref: {po.get('po_number', '-') if po else invoice.get('purchase_order_id', '-')}")
    pdf.drawString(320, 516, f"Materials: {po.get('materials', '-') if po else '-'}")
    pdf.drawString(320, 502, f"Payment Status: {str(invoice.get('payment_status', 'pending')).upper()}")

    draw_table_header(pdf, 398, [("Item", 68), ("Quantity", 292), ("Unit Price", 382), ("Amount", 490)])
    quantity = float(po.get("quantity", 1) or 1) if po else 1.0
    unit_price = amount / quantity if quantity > 0 else amount

    pdf.setFont("Helvetica", 10)
    item_title = po.get("materials", "Invoice Item(s)") if po else "Base Invoice Amount"
    pdf.drawString(68, 366, item_title)
    pdf.drawRightString(330, 366, f"{quantity:g}")
    pdf.drawRightString(432, 366, money(unit_price))
    pdf.drawRightString(552, 366, money(amount))

    if gst > 0:
        pdf.drawString(68, 342, "GST / Applicable Tax")
        pdf.drawRightString(330, 342, "1")
        pdf.drawRightString(432, 342, money(gst))
        pdf.drawRightString(552, 342, money(gst))
        draw_total_row(pdf, 304, "Grand Total", money(total))
    else:
        draw_total_row(pdf, 322, "Grand Total", money(total))

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, 266, "Verification:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(132, 266, f"Status: {str(invoice.get('status', 'pending')).upper()}")
    if invoice.get("verification_comments"):
        pdf.setFont("Helvetica", 9)
        pdf.drawString(56, 250, f"Comments: {invoice.get('verification_comments')}")

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(56, 212, "Note:")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(92, 212, "This invoice is subject to BuildTrack procurement approval and verified delivery inspection.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    safe_number = str(invoice.get("invoice_number", "invoice")).replace("/", "_").replace("\\", "_")
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_number}.pdf"'}
    )


@router.put("/invoices/{invoice_id}", response_model=Invoice)
async def edit_invoice(invoice_id: str, invoice: InvoiceUpdate, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "procurement.invoice.manage", "procurement.request.review")
    doc = await update_doc(db, "invoices", invoice_id, invoice.model_dump(exclude_unset=True), current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return Invoice(**serialize_doc(doc))


@router.delete("/invoices/{invoice_id}")
async def remove_invoice(invoice_id: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "records.delete")
    if not await delete_doc(db, "invoices", invoice_id, current_user):
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"message": "Invoice deleted successfully"}


@router.patch("/invoices/{invoice_id}/{action}", response_model=Invoice)
async def invoice_action(invoice_id: str, action: str, payload: InvoiceAction, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "procurement.invoice.manage")
    if action not in {"verify", "approve", "reject"}:
        raise HTTPException(status_code=400, detail="Action must be verify, approve, or reject")
    status_map = {"verify": "verified", "approve": "approved", "reject": "rejected"}
    doc = await update_invoice_status(db, invoice_id, status_map[action], current_user, payload.comments)
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return Invoice(**serialize_doc(doc))


@router.post("/payments", response_model=Payment)
async def create_payment(payment: PaymentCreate, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "procurement.payment.record")
    doc, error = await create_payment_for_invoice(db, payment.model_dump(), current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return Payment(**serialize_doc(doc))


@router.get("/payments")
async def payments(params=Depends(list_params), status_filter: str | None = None, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, financial=True)
    skip, limit, search, sort_by, sort_dir = params
    filters = {"status": status_filter} if status_filter else None
    return page(await list_docs(db, "payments", skip, limit, search, ["status", "remarks"], filters, sort_by, sort_dir))


@router.put("/payments/{payment_id}", response_model=Payment)
async def edit_payment(payment_id: str, payment: PaymentUpdate, current_user=Depends(get_current_user), db=Depends(get_database)):
    ensure_permission(current_user, "procurement.payment.record")
    data = payment.model_dump(exclude_unset=True)
    if data.get("status") == "paid" and not data.get("paid_at"):
        data["paid_at"] = datetime.utcnow()
    doc = await update_doc(db, "payments", payment_id, data, current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Payment not found")
    if data.get("status") == "paid":
        await update_doc(db, "invoices", doc["invoice_id"], {"payment_status": "paid"}, current_user)
    return Payment(**serialize_doc(doc))


@router.get("/export/{collection}")
async def export_collection(collection: str, current_user=Depends(get_current_user), db=Depends(get_database)):
    await guard_procurement_read(db, current_user, financial=collection in FINANCIAL_COLLECTIONS)
    allowed = {"vendors", "material_requests", "purchase_orders", "deliveries", "inventory", "invoices", "payments"}
    if collection not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported export collection")
    records = await db[collection].find().to_list(10000)
    output = io.StringIO()
    fields = sorted({key for record in records for key in record.keys()}) if records else ["message"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow({key: serialize(record.get(key)) for key in fields})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={collection}.csv"})


@router.get("/invoices/{invoice_id}/status")
async def get_invoice_payment_status(invoice_id: str, db=Depends(get_database)):
    """Check live payment status for an invoice."""
    invoice = await get_doc(db, "invoices", invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {
        "invoice_id": str(invoice.get("_id", invoice_id)),
        "invoice_number": invoice.get("invoice_number"),
        "payment_status": invoice.get("payment_status", "pending"),
        "status": invoice.get("status", "pending"),
    }


@router.get("/invoices/{invoice_id}/qr")
async def generate_invoice_payment_qr(invoice_id: str, db=Depends(get_database)):
    """Generate dynamic payment QR code for an invoice."""
    import qrcode
    from fastapi.responses import Response

    invoice = await get_doc(db, "invoices", invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    vendor = await get_doc(db, "vendors", invoice.get("vendor_id", "")) if invoice.get("vendor_id") else None
    vendor_name = vendor.get("vendor_name", "BuildTrack Vendor") if vendor else "BuildTrack Vendor"
    total_amount = float(invoice.get("amount", 0) or 0) + float(invoice.get("gst", 0) or 0)

    # Standard UPI URI format compatible with GPay, PhonePe, Paytm, BHIM
    upi_pa = "buildtrack.finance@okaxis"
    upi_pn = vendor_name.replace(" ", "+")
    upi_uri = f"upi://pay?pa={upi_pa}&pn={upi_pn}&am={total_amount:.2f}&tn=INV-{invoice.get('invoice_number')}&cu=INR"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(upi_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e293b", back_color="#ffffff")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


@router.post("/invoices/{invoice_id}/quick-pay")
async def quick_pay_invoice(
    invoice_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Mark invoice as paid and record payment entry."""
    ensure_permission(current_user, "procurement.payment.record")
    invoice = await get_doc(db, "invoices", invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    total_amount = float(invoice.get("amount", 0) or 0) + float(invoice.get("gst", 0) or 0)
    payment_payload = {
        "invoice_id": str(invoice["_id"]),
        "vendor_id": str(invoice.get("vendor_id", "")),
        "purchase_order_id": str(invoice.get("purchase_order_id", "")),
        "amount": total_amount,
        "status": "paid",
        "paid_at": datetime.utcnow(),
        "remarks": f"QR / Instant Payment for Invoice {invoice.get('invoice_number')}",
    }

    doc, err = await create_payment_for_invoice(db, payment_payload, current_user)
    if err:
        raise HTTPException(status_code=400, detail=err)
    await record_audit(db, "payment.recorded", actor=current_user, resource_type="invoice", resource_id=invoice_id, details={"amount": total_amount, "method": "quick_pay"})

    return {"message": "Payment recorded successfully", "payment": serialize_doc(doc)}


@router.get("/pay-scan/{invoice_id}")
async def mobile_pay_scan_page(invoice_id: str, db=Depends(get_database)):
    """Mobile-responsive checkout screen when scanning QR on phone."""
    from starlette.responses import HTMLResponse

    invoice = await get_doc(db, "invoices", invoice_id)
    if not invoice:
        return HTMLResponse("<h2>Invoice not found</h2>", status_code=404)

    vendor = await get_doc(db, "vendors", invoice.get("vendor_id", "")) if invoice.get("vendor_id") else None
    vendor_name = vendor.get("vendor_name", "BuildTrack Vendor") if vendor else "BuildTrack Vendor"
    total_amount = float(invoice.get("amount", 0) or 0) + float(invoice.get("gst", 0) or 0)
    is_paid = invoice.get("payment_status") == "paid"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>BuildTrack - Pay Invoice {invoice.get('invoice_number')}</title>
      <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        body {{ background: #0f172a; color: #f8fafc; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1.5rem; }}
        .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 16px; width: 100%; max-width: 420px; padding: 2rem; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); text-align: center; }}
        .badge {{ display: inline-block; padding: 0.35rem 0.85rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; margin-bottom: 1.25rem; }}
        .badge.pending {{ background: rgba(234,179,8,0.2); color: #facc15; border: 1px solid #ca8a04; }}
        .badge.paid {{ background: rgba(34,197,94,0.2); color: #4ade80; border: 1px solid #16a34a; }}
        h2 {{ font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem; }}
        .sub {{ color: #94a3b8; font-size: 0.875rem; margin-bottom: 1.5rem; }}
        .amount-box {{ background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; }}
        .amount-label {{ font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
        .amount-val {{ font-size: 2.2rem; font-weight: 800; color: #38bdf8; margin-top: 0.25rem; }}
        .details {{ text-align: left; background: #0f172a; border-radius: 10px; padding: 1rem; font-size: 0.875rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.6rem; }}
        .row {{ display: flex; justify-content: space-between; }}
        .row span:first-child {{ color: #94a3b8; }}
        .row span:last-child {{ font-weight: 600; color: #e2e8f0; }}
        .btn {{ width: 100%; padding: 0.9rem; border-radius: 10px; font-size: 1rem; font-weight: 700; border: none; cursor: pointer; transition: all 0.2s ease; display: flex; align-items: center; justify-content: center; gap: 0.5rem; }}
        .btn-pay {{ background: #2563eb; color: #ffffff; box-shadow: 0 10px 15px -3px rgba(37,99,235,0.4); }}
        .btn-pay:hover {{ background: #1d4ed8; }}
        .success-box {{ display: none; background: rgba(34,197,94,0.15); border: 1px solid #22c55e; border-radius: 12px; padding: 1.5rem; text-align: center; }}
        .success-box.show {{ display: block; }}
        .check-icon {{ width: 56px; height: 56px; background: #22c55e; color: #ffffff; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem; font-size: 1.75rem; font-weight: bold; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div id="payment-view" style="display: {'none' if is_paid else 'block'};">
          <span class="badge pending">Pending Payment</span>
          <h2>BuildTrack Procurement</h2>
          <p class="sub">Instant UPI & Vendor Payment Checkout</p>

          <div class="amount-box">
            <div class="amount-label">Total Amount Payable</div>
            <div class="amount-val">₹{total_amount:,.2f}</div>
          </div>

          <div class="details">
            <div class="row"><span>Invoice No:</span><span>{invoice.get('invoice_number')}</span></div>
            <div class="row"><span>Vendor:</span><span>{vendor_name}</span></div>
            <div class="row"><span>PO Ref:</span><span>{invoice.get('purchase_order_id', '-')}</span></div>
          </div>

          <button id="pay-btn" class="btn btn-pay" onclick="processPayment()">
            ✓ Confirm & Pay Now (₹{total_amount:,.2f})
          </button>
        </div>

        <div id="success-view" class="success-box {'show' if is_paid else ''}">
          <div class="check-icon">✓</div>
          <h3 style="color: #4ade80; font-size: 1.25rem; font-weight: 700; margin-bottom: 0.5rem;">Payment Successful!</h3>
          <p style="color: #cbd5e1; font-size: 0.9rem;">Invoice <strong>{invoice.get('invoice_number')}</strong> has been marked as <strong>PAID</strong> in BuildTrack Procurement.</p>
          <div style="margin-top: 1rem; font-size: 0.8rem; color: #94a3b8;">Amount: ₹{total_amount:,.2f}</div>
        </div>
      </div>

      <script>
        async function processPayment() {{
          const btn = document.getElementById('pay-btn');
          btn.disabled = true;
          btn.innerText = 'Processing Payment...';
          try {{
            const res = await fetch('/api/v1/procurement/pay-scan/{invoice_id}/confirm', {{ method: 'POST' }});
            if (res.ok) {{
              document.getElementById('payment-view').style.display = 'none';
              document.getElementById('success-view').classList.add('show');
            }} else {{
              alert('Failed to process payment.');
              btn.disabled = false;
              btn.innerText = 'Confirm & Pay Now';
            }}
          }} catch (e) {{
            alert('Could not reach BuildTrack. The payment has not been recorded.');
            btn.disabled = false;
            btn.innerText = 'Confirm & Pay Now';
          }}
        }}
      </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.post("/pay-scan/{invoice_id}/confirm")
async def confirm_mobile_scan_payment(invoice_id: str, db=Depends(get_database)):
    """Public confirmation endpoint when payment is confirmed via phone scan.

    SECURITY: disabled. It required no login and recorded a full payment for
    any invoice id, and opening a QR page is not evidence that money moved.
    Payments are recorded by a user holding procurement.payment.record.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Payments must be confirmed by an authorized finance user in BuildTrack.",
    )
    invoice = await get_doc(db, "invoices", invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    total_amount = float(invoice.get("amount", 0) or 0) + float(invoice.get("gst", 0) or 0)
    system_user = {"full_name": "BuildTrack QR System", "_id": "system_qr"}

    payment_payload = {
        "invoice_id": str(invoice["_id"]),
        "vendor_id": str(invoice.get("vendor_id", "")),
        "purchase_order_id": str(invoice.get("purchase_order_id", "")),
        "amount": total_amount,
        "status": "paid",
        "paid_at": datetime.utcnow(),
        "remarks": f"Phone Scan / UPI Payment for Invoice {invoice.get('invoice_number')}",
    }

    doc, err = await create_payment_for_invoice(db, payment_payload, system_user)
    if err:
        raise HTTPException(status_code=400, detail=err)

    return {"message": "Payment successful", "payment": serialize_doc(doc)}

