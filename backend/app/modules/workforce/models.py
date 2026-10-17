from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# Worker
# ============================================================

WORKFORCE_CATEGORIES = [
    "ENGINEER",
    "SUPERVISOR",
    "CONTRACTOR",
    "SKILLED_WORKER",
    "UNSKILLED_WORKER",
    "CONSULTANT",
]


class WorkerBase(BaseModel):
    worker_code: Optional[str] = Field(
        default=None,
        description="Unique worker ID/code e.g. WRK-1001",
    )
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None

    # Workforce category
    category: str = Field(
        default="SKILLED_WORKER",
        description=(
            "ENGINEER, SUPERVISOR, CONTRACTOR, "
            "SKILLED_WORKER, UNSKILLED_WORKER, CONSULTANT"
        ),
    )

    # Actual skill
    skill_type: str = Field(
        ...,
        description="electrician, plumber, carpenter, mason, etc.",
    )

    designation: Optional[str] = None
    experience_years: Optional[float] = 0

    employment_type: str = Field(
        default="FULL_TIME",
        description="FULL_TIME, PART_TIME, CONTRACT",
    )

    joining_date: Optional[datetime] = None

    # Salary / wage information
    salary_type: str = Field(
        default="HOURLY",
        description="HOURLY, DAILY, MONTHLY",
    )

    hourly_rate: float = 0
    salary_amount: Optional[float] = None

    # Current project
    project_id: Optional[str] = None

    status: str = Field(
        default="available",
        description="available, assigned, unavailable",
    )

    attendance_pct: Optional[float] = Field(
        default=0,
        description="Attendance percentage in the last 30 days",
    )


class WorkerCreate(WorkerBase):
    pass


class WorkerUpdate(BaseModel):
    worker_code: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    category: Optional[str] = None
    skill_type: Optional[str] = None
    designation: Optional[str] = None
    experience_years: Optional[float] = None

    employment_type: Optional[str] = None
    joining_date: Optional[datetime] = None

    salary_type: Optional[str] = None
    hourly_rate: Optional[float] = None
    salary_amount: Optional[float] = None

    project_id: Optional[str] = None
    status: Optional[str] = None


class WorkerLoginCreate(BaseModel):
    """Login for a worker record. Email defaults to the worker's."""

    email: Optional[str] = None
    password: str = Field(..., min_length=8, max_length=128)


class WorkerLoginLink(BaseModel):
    """Attach an account the worker already registered."""

    email: str


class WorkerPasswordReset(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)


class Worker(WorkerBase):
    id: str = Field(alias="_id")
    # Shown only to users who manage worker logins.
    login_email: Optional[str] = None
    # Wage fields are None when the reader lacks workforce.read.sensitive.
    salary_type: Optional[str] = None
    hourly_rate: Optional[float] = None
    salary_amount: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# ============================================================
# Workforce Allocation
# ============================================================

class WorkforceAllocationBase(BaseModel):
    worker_id: str
    project_id: str

    role: Optional[str] = None

    start_date: datetime
    end_date: Optional[datetime] = None

    status: str = Field(
        default="ACTIVE",
        description="ACTIVE, COMPLETED, CANCELLED",
    )


class WorkforceAllocationCreate(WorkforceAllocationBase):
    pass


class WorkforceAllocationUpdate(BaseModel):
    role: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None


class WorkforceAllocation(WorkforceAllocationBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# ============================================================
# Attendance
# ============================================================

class AttendanceBase(BaseModel):
    worker_id: str
    project_id: Optional[str] = None

    date: datetime

    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None

    status: str = Field(
        default="absent",
        description="present, absent, leave",
    )

    hours_worked: Optional[float] = None
    overtime_hours: Optional[float] = 0

    remarks: Optional[str] = None


class AttendanceCreate(AttendanceBase):
    pass


class AttendanceUpdate(BaseModel):
    project_id: Optional[str] = None

    date: Optional[datetime] = None

    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None

    status: Optional[str] = None

    hours_worked: Optional[float] = None
    overtime_hours: Optional[float] = None

    remarks: Optional[str] = None


class Attendance(AttendanceBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# ============================================================
# Shift Scheduling
# ============================================================

class ShiftBase(BaseModel):
    name: str

    project_id: Optional[str] = None

    start_time: str
    end_time: str

    description: Optional[str] = None

    status: str = Field(
        default="ACTIVE",
        description="ACTIVE, INACTIVE",
    )


class ShiftCreate(ShiftBase):
    pass


class ShiftUpdate(BaseModel):
    name: Optional[str] = None
    project_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class Shift(ShiftBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# ============================================================
# Shift Assignment
# ============================================================

class ShiftAssignmentBase(BaseModel):
    worker_id: str
    shift_id: str
    project_id: Optional[str] = None

    date: datetime

    status: str = Field(
        default="ACTIVE",
        description="ACTIVE, COMPLETED, CANCELLED",
    )


class ShiftAssignmentCreate(ShiftAssignmentBase):
    pass


class ShiftAssignment(ShiftAssignmentBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True


# ============================================================
# Payroll
# ============================================================

class PayrollBase(BaseModel):
    worker_id: str
    project_id: Optional[str] = None

    pay_period_start: datetime
    pay_period_end: datetime

    basic_amount: float = 0
    overtime_hours: float = 0
    overtime_amount: float = 0

    deductions: float = 0
    bonus: float = 0

    net_amount: float = 0

    status: str = Field(
        default="DRAFT",
        description="DRAFT, PENDING, APPROVED, PAID",
    )


class PayrollCreate(PayrollBase):
    pass


class PayrollUpdate(BaseModel):
    basic_amount: Optional[float] = None
    overtime_hours: Optional[float] = None
    overtime_amount: Optional[float] = None
    deductions: Optional[float] = None
    bonus: Optional[float] = None
    net_amount: Optional[float] = None
    status: Optional[str] = None


class Payroll(PayrollBase):
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True