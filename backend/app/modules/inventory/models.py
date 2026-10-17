from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# -----------------------------
# Inventory Item Models
# -----------------------------

class InventoryItemBase(BaseModel):
    material_name: str
    quantity: float = 0.0
    unit: str = Field(default="Nos", description="kg, meter, piece, etc.")
    unit_cost: float = 0.0
    supplier_id: Optional[str] = None
    location: Optional[str] = None
    status: str = Field(
        default="in_stock",
        description="in_stock, low_stock, out_of_stock"
    )
    reorder_level: int = 10


class InventoryItemCreate(InventoryItemBase):
    pass


class InventoryItemUpdate(BaseModel):
    material_name: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    supplier_id: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    reorder_level: Optional[int] = None


class InventoryItem(InventoryItemBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# -----------------------------
# Inventory Transaction Models
# -----------------------------

class InventoryTransactionCreate(BaseModel):
    transaction_type: str = Field(
        ...,
        description="in, out, adjustment"
    )
    quantity: int
    reason: Optional[str] = None
    created_by: str


class InventoryTransaction(BaseModel):
    id: str = Field(alias="_id")
    item_id: str
    transaction_type: str
    quantity: int
    reason: Optional[str] = None
    created_by: str
    created_at: datetime

    class Config:
        populate_by_name = True