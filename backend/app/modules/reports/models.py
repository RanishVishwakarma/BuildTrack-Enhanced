from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReportBase(BaseModel):
    title: str
    description: Optional[str] = None
    report_type: str = Field(..., description="project_summary, financial, resource_utilization, workforce, procurement")
    project_id: Optional[str] = None
    generated_by: str
    filters: Optional[dict] = None


class ReportCreate(ReportBase):
    pass


class Report(ReportBase):
    id: str = Field(alias="_id")
    data: dict = Field(default_factory=dict)
    file_url: Optional[str] = None
    status: str = Field(default="completed", description="pending, in_progress, completed, failed")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class DashboardMetrics(BaseModel):
    total_projects: int = 0
    active_projects: int = 0
    total_resources: int = 0
    available_resources: int = 0
    total_workers: int = 0
    total_inventory_value: float = 0.0
    low_stock_items: int = 0
    pending_procurements: int = 0
    total_expenses: float = 0.0
