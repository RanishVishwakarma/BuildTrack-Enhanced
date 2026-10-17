from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# =====================================================
# Invoice Tracking Models
# =====================================================

class InvoiceBase(BaseModel):
    invoiceId: str
    purchaseOrderId: str
    vendorId: str
    projectId: str

    invoiceNumber: str
    invoiceDate: datetime

    amount: float

    status: str = Field(
        default="Pending",
        description="Pending, Approved, Paid, Rejected",
    )

    approvedBy: Optional[str] = ""

    paymentMethod: Optional[str] = ""

    paymentDate: Optional[datetime] = None

    paymentRemarks: Optional[str] = ""

    dueDate: datetime

    remarks: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    invoiceNumber: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    approvedBy: Optional[str] = None
    paymentMethod: Optional[str] = None
    paymentDate: Optional[datetime] = None
    paymentRemarks: Optional[str] = None
    dueDate: Optional[datetime] = None
    remarks: Optional[str] = None


class Invoice(InvoiceBase):
    id: str = Field(alias="_id")
    createdAt: datetime

    class Config:
        populate_by_name = True