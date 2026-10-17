from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default="User", alias="name")
    role: str = Field(
        ...,
        description="admin, manager, engineer, store_manager, finance, contractor, worker, client, vendor"
    )
    status: str = Field(
        default="active",
        description="active, inactive, suspended, pending"
    )
    avatar_url: Optional[str] = Field(default=None, alias="avatarUrl")
    vendor_id: Optional[str] = Field(
        default=None,
        description="Linked Vendor record ID for vendor users"
    )

    class Config:
        populate_by_name = True
        extra = "allow"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    vendor_id: Optional[str] = None


class User(UserBase):
    id: str = Field(alias="_id")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True