from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MilestoneBase(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: datetime
    status: str = Field(default="pending", description="pending, in_progress, completed")


class Milestone(MilestoneBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = "Commercial"
    client: Optional[str] = None
    client_email: Optional[str] = None
    project_manager_id: Optional[str] = "unassigned"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = 0.0
    progress: Optional[float] = 0.0
    status: str = Field(default="planning", description="planning, active, on_hold, completed")
    location: Optional[str] = None

    class Config:
        populate_by_name = True
        extra = "allow"


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    client: Optional[str] = None
    client_email: Optional[str] = None
    project_manager_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[float] = None
    progress: Optional[float] = None
    status: Optional[str] = None
    location: Optional[str] = None

    class Config:
        populate_by_name = True
        extra = "allow"


class Project(ProjectBase):
    id: str = Field(alias="_id")
    milestones: list = Field(default=[])
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
