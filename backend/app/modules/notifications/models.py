from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationBase(BaseModel):
    user_id: Optional[str] = Field(None, description="Target user ID")
    receiver_id: Optional[str] = Field(None, description="Alias for target user ID")
    title: str
    message: str
    type: str = Field("info", description="info, warning, alert, success")
    category: str = Field(
        "system",
        description="project_update, task_assignment, procurement_alert, attendance_alert, deadline, system",
    )
    entity_type: Optional[str] = Field(None, description="project, task, procurement, attendance, system")
    entity_id: Optional[str] = None
    related_entity_type: Optional[str] = Field(None, description="Legacy alias for entity_type")
    related_entity_id: Optional[str] = Field(None, description="Legacy alias for entity_id")


class NotificationCreate(NotificationBase):
    pass


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None


class Notification(NotificationBase):
    id: str = Field(default="", alias="_id")
    user_id: Optional[str] = None
    is_read: bool = Field(default=False)
    created_at: datetime
    updated_at: Optional[datetime] = None
    read_at: Optional[datetime] = None

    model_config = {
        "populate_by_name": True,
    }


