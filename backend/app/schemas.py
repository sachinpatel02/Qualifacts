from datetime import datetime

from sqlmodel import Field, SQLModel

from .models import AppointmentStatus


class AppointmentCreate(SQLModel):
    """Fields required to submit a new pending appointment request."""

    patient_name: str = Field(min_length=1, max_length=120, description="Patient's display name.")
    patient_email: str = Field(min_length=3, max_length=255, description="Email used for appointment notifications.")
    provider_id: int = Field(default=1, description="Provider receiving the request.")
    appointment_type: str = Field(min_length=1, max_length=120, description="Requested type of visit.")
    reason: str = Field(min_length=1, max_length=2000, description="Reason for the visit.")
    scheduled_start: datetime = Field(description="Preferred start time in IST (Asia/Kolkata).")
    duration_minutes: int = Field(default=60, gt=0, le=480, description="Requested duration in minutes.")


class AppointmentAction(SQLModel):
    """Version token required for a concurrency-safe appointment mutation."""

    version: int = Field(gt=0, description="Version last read by the caller.")


class RescheduleRequest(AppointmentAction):
    """New time for a provider reschedule operation."""

    scheduled_start: datetime = Field(description="New start time in IST (Asia/Kolkata).")
    duration_minutes: int = Field(default=60, gt=0, le=480, description="New duration in minutes.")


class AppointmentRead(SQLModel):
    """Appointment returned by the API, including its concurrency version."""

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
    """Immutable audit event describing an appointment change."""

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
