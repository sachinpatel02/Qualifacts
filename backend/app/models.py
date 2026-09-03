import enum
from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel

from .timezone import now_ist


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"

    id: int | None = Field(default=None, primary_key=True)
    patient_name: str = Field(max_length=120)
    patient_email: str = Field(max_length=255)
    provider_id: int = Field(index=True)
    appointment_type: str = Field(max_length=120)
    reason: str
    scheduled_start: datetime
    scheduled_end: datetime
    status: AppointmentStatus = Field(default=AppointmentStatus.PENDING, index=True)
    version: int = Field(default=1)
    created_at: datetime = Field(default_factory=now_ist)
    updated_at: datetime = Field(
        default_factory=now_ist,
        sa_column_kwargs={"onupdate": now_ist},
    )

    history: list["AppointmentHistory"] = Relationship(
        back_populates="appointment",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class AppointmentHistory(SQLModel, table=True):
    __tablename__ = "appointment_history"

    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointments.id", index=True)
    action: str = Field(max_length=40)
    previous_status: str | None = Field(default=None, max_length=20)
    new_status: str | None = Field(default=None, max_length=20)
    previous_start: datetime | None = None
    new_start: datetime | None = None
    performed_by_role: str = Field(max_length=30)
    performed_by_id: str = Field(max_length=120)
    created_at: datetime = Field(default_factory=now_ist)

    appointment: Appointment = Relationship(back_populates="history")


class NotificationOutbox(SQLModel, table=True):
    __tablename__ = "notification_outbox"

    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointments.id", index=True)
    recipient: str = Field(max_length=255)
    notification_type: str = Field(max_length=40)
    message: str
    status: str = Field(default="pending", max_length=20)
    created_at: datetime = Field(default_factory=now_ist)
    processed_at: datetime | None = None
    error: str | None = None
