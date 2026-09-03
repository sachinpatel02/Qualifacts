from datetime import datetime

from sqlmodel import Field, SQLModel

from .models import AppointmentStatus


class AppointmentCreate(SQLModel):
    patient_name: str = Field(min_length=1, max_length=120)
    patient_email: str = Field(min_length=3, max_length=255)
    provider_id: int = 1
    appointment_type: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)
    scheduled_start: datetime
    duration_minutes: int = Field(default=60, gt=0, le=480)


class AppointmentAction(SQLModel):
    version: int = Field(gt=0)


class RescheduleRequest(AppointmentAction):
    scheduled_start: datetime
    duration_minutes: int = Field(default=60, gt=0, le=480)


class AppointmentRead(SQLModel):
    id: int
    patient_name: str
    patient_email: str
    provider_id: int
    appointment_type: str
    reason: str
    scheduled_start: datetime
    scheduled_end: datetime
    status: AppointmentStatus
    version: int
    created_at: datetime
    updated_at: datetime


class HistoryRead(SQLModel):
    id: int
    appointment_id: int
    action: str
    previous_status: str | None
    new_status: str | None
    previous_start: datetime | None
    new_start: datetime | None
    performed_by_role: str
    performed_by_id: str
    created_at: datetime
