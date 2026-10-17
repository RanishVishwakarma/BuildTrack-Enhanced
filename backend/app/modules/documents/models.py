from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Document(BaseModel):
    id: str = Field(alias="_id")
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    uploaded_by: str
    category: Optional[str] = None
    created_at: datetime

    class Config:
        populate_by_name = True
