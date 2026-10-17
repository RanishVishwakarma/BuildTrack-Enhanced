from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


Priority = Literal["low", "medium", "high"]
RequestStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "vendor_assigned",
    "sent_to_vendor",
    "vendor_accepted",
    "vendor_rejected",
    "po_generated",
    "po_sent",
    "po_accepted",
    "partially_delivered",
    "delivered",
    "invoice_pending",
    "invoice_verified",
    "payment_pending",
    "paid",
    "completed",
]
VendorStatus = Literal["active", "inactive"]
POStatus = Literal[
    "created",
    "sent",
    "accepted",
    "rejected",
    "processing",
    "shipped",
    "delivered",
    "received",
    "cancelled",
]
QualityStatus = Literal["pending", "passed", "failed"]
DeliveryStatus = Literal[
    "pending",
    "accepted",
    "processing",
    "shipped",
    "delivered",
    "received",
    "cancelled",
    "rejected",
    "partial",
]
InvoiceStatus = Literal["pending", "verified", "approved", "rejected"]
PaymentStatus = Literal["pending", "approved", "paid"]


class MongoModel(BaseModel):
    id: str = Field(alias="_id")

    class Config:
        populate_by_name = True


class VendorBase(BaseModel):
    vendor_name: str = Field(..., min_length=2, max_length=120)
    contact_person: str = Field(..., min_length=2, max_length=120)
    phone: str = Field(..., min_length=7, max_length=20)
    email: EmailStr
    address: str = Field(..., min_length=2, max_length=300)
    gst_number: Optional[str] = Field(default=None, max_length=50)
    pan_number: Optional[str] = Field(default=None, max_length=50)
    materials_supplied: list[str] = Field(default_factory=list)
    rating: float = Field(default=0, ge=0, le=5)
    status: VendorStatus = "active"


class VendorCreate(VendorBase):
    pass


class VendorCreateWithAccount(VendorBase):
    """Vendor creation with optional login account.

    When ``create_login_account`` is True the endpoint also creates a
    User document with role ``vendor`` and links it via ``vendor_id``.
    """

    create_login_account: bool = False
    password: Optional[str] = Field(
        default=None,
        min_length=6,
        description="Login password — required when create_login_account is True",
    )


class VendorUpdate(BaseModel):
    vendor_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    contact_person: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, min_length=7, max_length=20)
    email: Optional[EmailStr] = None
    address: Optional[str] = Field(default=None, min_length=2, max_length=300)
    gst_number: Optional[str] = Field(default=None, max_length=50)
    pan_number: Optional[str] = Field(default=None, max_length=50)
    materials_supplied: Optional[list[str]] = None
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    status: Optional[VendorStatus] = None


class Vendor(VendorBase, MongoModel):
    created_at: datetime
    updated_at: datetime


class MaterialRequestBase(BaseModel):
    project: str = Field(..., min_length=2, max_length=160)
    project_id: Optional[str] = None
    material_name: str = Field(..., min_length=2, max_length=160)
    material_id: Optional[str] = None
    unit: Optional[str] = None
    quantity: float = Field(..., gt=0)
    required_date: datetime
    priority: Priority = "medium"
    remarks: Optional[str] = None


class MaterialRequestCreate(MaterialRequestBase):
    pass


class MaterialRequestUpdate(BaseModel):
    project: Optional[str] = Field(default=None, min_length=2, max_length=160)
    project_id: Optional[str] = None
    material_name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    material_id: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    required_date: Optional[datetime] = None
    priority: Optional[Priority] = None
    remarks: Optional[str] = None


class ApprovalAction(BaseModel):
    status: Literal["approved", "rejected"]
    comments: Optional[str] = None


class VendorAssignment(BaseModel):
    vendor_id: str = Field(..., min_length=1)


class VendorResponseAction(BaseModel):
    """Vendor accept/reject payload. Rejection requires a comment/reason."""

    action: Literal["accept", "reject"]
    comment: Optional[str] = Field(default=None, max_length=1000)



class MaterialRequest(MaterialRequestBase, MongoModel):
    request_id: str
    status: RequestStatus = "pending"
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_assigned_by: Optional[str] = None
    vendor_assigned_at: Optional[datetime] = None
    assigned_vendor_id: Optional[str] = None
    vendor_response: Optional[str] = None
    vendor_response_date: Optional[datetime] = None
    vendor_comment: Optional[str] = None
    purchase_order_id: Optional[str] = None
    po_number: Optional[str] = None
    requested_by: Optional[str] = None
    approval_comments: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderBase(BaseModel):
    request_id: str = Field(..., min_length=1)
    vendor_id: str = Field(..., min_length=1)
    project: str = Field(..., min_length=2, max_length=160)
    project_id: Optional[str] = None
    materials: str = Field(..., min_length=2, max_length=200)
    material_id: Optional[str] = None
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    gst: float = Field(default=0, ge=0)
    subtotal: float = Field(default=0, ge=0)
    expected_delivery_date: datetime
    status: POStatus = "created"


class PurchaseOrderCreate(PurchaseOrderBase):
    pass


class PORejectPayload(BaseModel):
    reason: str = Field(..., min_length=2, max_length=1000)


class PurchaseOrderUpdate(BaseModel):
    vendor_id: Optional[str] = None
    project: Optional[str] = Field(default=None, min_length=2, max_length=160)
    project_id: Optional[str] = None
    materials: Optional[str] = Field(default=None, min_length=2, max_length=200)
    material_id: Optional[str] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)
    gst: Optional[float] = Field(default=None, ge=0)
    subtotal: Optional[float] = Field(default=None, ge=0)
    expected_delivery_date: Optional[datetime] = None
    status: Optional[POStatus] = None
    rejection_reason: Optional[str] = None


class PurchaseOrder(PurchaseOrderBase, MongoModel):
    po_number: str
    subtotal: float
    gst: float
    total_cost: float
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DeliveryBase(BaseModel):
    purchase_order_id: str = Field(..., min_length=1)
    po_number: Optional[str] = None
    vendor_id: Optional[str] = None
    material: str = Field(..., min_length=2, max_length=200)
    quantity_received: float = Field(..., gt=0)
    quality_status: QualityStatus = "pending"
    delivery_date: datetime
    dispatch_date: Optional[datetime] = None
    vehicle_number: Optional[str] = Field(default=None, max_length=60)
    tracking_number: Optional[str] = Field(default=None, max_length=100)
    remarks: Optional[str] = None
    status: DeliveryStatus = "pending"


class DeliveryCreate(DeliveryBase):
    pass


class DeliveryUpdate(BaseModel):
    quantity_received: Optional[float] = Field(default=None, gt=0)
    quality_status: Optional[QualityStatus] = None
    delivery_date: Optional[datetime] = None
    dispatch_date: Optional[datetime] = None
    vehicle_number: Optional[str] = None
    tracking_number: Optional[str] = None
    remarks: Optional[str] = None
    status: Optional[DeliveryStatus] = None


class VendorDeliveryCreate(BaseModel):
    purchase_order_id: str = Field(..., min_length=1)
    quantity: float = Field(..., gt=0)
    dispatch_date: Optional[datetime] = None
    vehicle_number: Optional[str] = Field(default=None, max_length=60)
    tracking_number: Optional[str] = Field(default=None, max_length=100)
    remarks: Optional[str] = None
    status: DeliveryStatus = "shipped"


class VendorDeliveryUpdate(BaseModel):
    status: DeliveryStatus
    vehicle_number: Optional[str] = None
    tracking_number: Optional[str] = None
    remarks: Optional[str] = None


class Delivery(DeliveryBase, MongoModel):
    created_at: datetime
    updated_at: datetime


class InventoryItem(MongoModel):
    material: str
    stock_quantity: float
    transactions: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class InvoiceBase(BaseModel):
    invoice_number: str = Field(..., min_length=2, max_length=80)
    vendor_id: Optional[str] = Field(default="", max_length=120)
    purchase_order_id: str = Field(..., min_length=1)
    amount: float = Field(..., ge=0)
    gst: float = Field(default=0, ge=0)
    invoice_date: datetime
    payment_status: PaymentStatus = "pending"
    attachment_url: Optional[str] = None
    status: InvoiceStatus = "pending"


class InvoiceCreate(InvoiceBase):
    pass


class VendorInvoiceCreate(BaseModel):
    purchase_order_id: str = Field(..., min_length=1)
    invoice_number: str = Field(..., min_length=2, max_length=80)
    invoice_date: datetime
    amount: float = Field(..., ge=0)
    gst: float = Field(default=0, ge=0)
    attachment_url: Optional[str] = None


class InvoiceUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, ge=0)
    gst: Optional[float] = Field(default=None, ge=0)
    invoice_date: Optional[datetime] = None
    payment_status: Optional[PaymentStatus] = None
    attachment_url: Optional[str] = None
    status: Optional[InvoiceStatus] = None


class InvoiceAction(BaseModel):
    comments: Optional[str] = None


class Invoice(InvoiceBase, MongoModel):
    verification_comments: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaymentBase(BaseModel):
    invoice_id: str = Field(..., min_length=1)
    vendor_id: str = Field(..., min_length=1)
    purchase_order_id: str = Field(..., min_length=1)
    amount: float = Field(..., ge=0)
    status: PaymentStatus = "pending"
    paid_at: Optional[datetime] = None
    remarks: Optional[str] = None


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    paid_at: Optional[datetime] = None
    remarks: Optional[str] = None


class Payment(PaymentBase, MongoModel):
    created_at: datetime
    updated_at: datetime


class DashboardStats(BaseModel):
    pending_requests: int
    active_purchase_orders: int
    pending_deliveries: int
    pending_payments: int
    recent_activity: list[dict]


class MaterialItem(BaseModel):
    """Material master record sourced from the `inventory` collection."""

    id: str = Field(alias="_id")
    material: str
    material_name: Optional[str] = None
    available_stock: float = 0
    unit: Optional[str] = None
    status: Optional[str] = None

    class Config:
        populate_by_name = True


class VendorDashboardStats(BaseModel):
    vendor: Vendor | None = None
    total_assigned: int = 0
    pending_responses: int = 0
    accepted_requests: int = 0
    rejected_requests: int = 0
    total_purchase_orders: int = 0
    pending_orders: int = 0
    accepted_orders: int = 0
    delivered_orders: int = 0
    pending_deliveries: int = 0
    pending_invoices: int = 0
    pending_payments: int = 0
    requests: list[MaterialRequest] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrder] = Field(default_factory=list)
    deliveries: list[Delivery] = Field(default_factory=list)
    invoices: list[Invoice] = Field(default_factory=list)
    recent_notifications: list[dict] = Field(default_factory=list)


class ProcurementItem(BaseModel):
    item_name: str
    quantity: float
    unit_price: float
    total_cost: float


class ProcurementBase(BaseModel):
    vendor_id: str
    project_id: Optional[str] = None
    items: list[ProcurementItem]
    requested_by: str
    request_date: datetime
    expected_delivery: Optional[datetime] = None
    status: str = "pending"
    total_amount: float
    notes: Optional[str] = None


class ProcurementCreate(ProcurementBase):
    pass


class ProcurementUpdate(BaseModel):
    status: Optional[str] = None
    expected_delivery: Optional[datetime] = None
    notes: Optional[str] = None


class Procurement(ProcurementBase, MongoModel):
    created_at: datetime
    updated_at: datetime

