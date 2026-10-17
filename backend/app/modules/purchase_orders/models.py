from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PurchaseOrderBase(BaseModel):
    purchaseOrderId: str
    projectId: str
    procurementId: str
    vendorId: str
    orderNumber: str
    orderDate: datetime
    totalAmount: float
    status: str = Field(
        default="Pending",
        description="Pending, Approved, Ordered, Delivered, Cancelled",
    )
    expectedDelivery: Optional[datetime] = None


class PurchaseOrderCreate(PurchaseOrderBase):
    pass


class PurchaseOrderUpdate(BaseModel):
    orderNumber: Optional[str] = None
    totalAmount: Optional[float] = None
    status: Optional[str] = None
    expectedDelivery: Optional[datetime] = None


class PurchaseOrder(PurchaseOrderBase):
    id: str = Field(alias="_id")
    createdAt: datetime

    class Config:
        populate_by_name = True