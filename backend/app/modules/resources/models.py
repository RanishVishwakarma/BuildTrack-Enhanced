from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ResourceBase(BaseModel):
    resource_name: str
    resource_type: str = Field(default="equipment", description="equipment, tool, vehicle, material, etc.")
    description: Optional[str] = None
    quantity: float = 1.0
    unit: Optional[str] = "Nos"
    acquisition_cost: float = 0.0
    acquisition_date: Optional[datetime] = None
    status: str = Field(default="available", description="available, in_use, maintenance, retired")
    assigned_to: Optional[str] = None
    assigned_project: Optional[str] = None
    maintenance_schedule: Optional[str] = None


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(BaseModel):
    resource_name: Optional[str] = None
    resource_type: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_project: Optional[str] = None


class Resource(ResourceBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class MaintenanceLogCreate(BaseModel):
    maintenance_date: datetime
    maintenance_type: str = Field(..., description="routine, repair, inspection")
    description: str
    cost: float = 0.0
    performed_by: str


class MaintenanceLog(MaintenanceLogCreate):
    resource_id: str
    id: str = Field(alias="_id")
    created_at: datetime

    class Config:
        populate_by_name = True