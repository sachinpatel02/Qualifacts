from datetime import datetime, timedelta

from sqlalchemy import text
from sqlmodel import Session, select

from .models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    NotificationOutbox,
)
from .schemas import AppointmentCreate, RescheduleRequest
from .timezone import as_ist_naive, now_ist


class AppointmentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def _history(
    appointment: Appointment,
    action: str,
    role: str,
    actor: str,
    previous_status: AppointmentStatus | None,
    previous_start: datetime | None,
) -> AppointmentHistory:
    return AppointmentHistory(
        appointment_id=appointment.id,
        action=action,
        previous_status=previous_status.value if previous_status else None,
        new_status=appointment.status.value if appointment.status else None,
        previous_start=previous_start,
        new_start=appointment.scheduled_start,
        performed_by_role=role,
        performed_by_id=actor,
    )


def _begin_write(session: Session) -> None:
    # SQLite serializes writers so the overlap check and update are atomic.
    session.execute(text("BEGIN IMMEDIATE"))


def _get_appointment(session: Session, appointment_id: int) -> Appointment:
    appointment = session.scalar(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    if not appointment:
        raise AppointmentError(404, "Appointment not found")
    return appointment


def _check_version(appointment: Appointment, version: int) -> None:
    if appointment.version != version:
        raise AppointmentError(
            409,
            "Appointment changed since you viewed it; refresh and try again.",
        )


def _check_overlap(
    session: Session,
    appointment: Appointment,
    start: datetime,
    end: datetime,
) -> None:
    overlap = session.scalar(
        select(Appointment).where(
            Appointment.provider_id == appointment.provider_id,
            Appointment.id != appointment.id,
            Appointment.status == AppointmentStatus.CONFIRMED,
            Appointment.scheduled_start < end,
            Appointment.scheduled_end > start,
        )
    )
    if overlap:
        raise AppointmentError(
            409,
            "The provider already has a confirmed appointment during that time.",
        )


def create_appointment(session: Session, payload: AppointmentCreate) -> Appointment:
    scheduled_start = as_ist_naive(payload.scheduled_start)
    end = scheduled_start + timedelta(minutes=payload.duration_minutes)
    appointment = Appointment(
        patient_name=payload.patient_name,
        patient_email=payload.patient_email,
        provider_id=payload.provider_id,
        appointment_type=payload.appointment_type,
        reason=payload.reason,
        scheduled_start=scheduled_start,
        scheduled_end=end,
        status=AppointmentStatus.PENDING,
        version=1,
    )
    session.add(appointment)
    session.flush()
    session.add(
        _history(
            appointment,
            "requested",
            "patient",
            payload.patient_email,
            None,
            None,
        )
    )
    session.commit()
    session.refresh(appointment)
    return appointment


def confirm_appointment(
    session: Session, appointment_id: int, version: int, actor: str
) -> Appointment:
    _begin_write(session)
    appointment = _get_appointment(session, appointment_id)
    _check_version(appointment, version)
    if appointment.status != AppointmentStatus.PENDING:
        raise AppointmentError(409, "Only pending appointments can be confirmed.")
    _check_overlap(
        session, appointment, appointment.scheduled_start, appointment.scheduled_end
    )

    previous_status = appointment.status
    appointment.status = AppointmentStatus.CONFIRMED
    appointment.version += 1
    session.add(
        _history(
            appointment,
            "confirmed",
            "provider",
            actor,
            previous_status,
            appointment.scheduled_start,
        )
    )
    session.add(
        NotificationOutbox(
            appointment_id=appointment.id,
            recipient=appointment.patient_email,
            notification_type="appointment_confirmed",
            message=f"Your appointment on {appointment.scheduled_start.isoformat()} is confirmed.",
        )
    )
    session.commit()
    session.refresh(appointment)
    return appointment


def reschedule_appointment(
    session: Session,
    appointment_id: int,
    payload: RescheduleRequest,
    actor: str,
) -> Appointment:
    _begin_write(session)
    appointment = _get_appointment(session, appointment_id)
    _check_version(appointment, payload.version)
    if appointment.status == AppointmentStatus.CANCELLED:
        raise AppointmentError(409, "Cancelled appointments cannot be rescheduled.")

    scheduled_start = as_ist_naive(payload.scheduled_start)
    new_end = scheduled_start + timedelta(minutes=payload.duration_minutes)
    if appointment.status == AppointmentStatus.CONFIRMED:
        _check_overlap(session, appointment, scheduled_start, new_end)
    previous_status = appointment.status
    previous_start = appointment.scheduled_start
    appointment.scheduled_start = scheduled_start
    appointment.scheduled_end = new_end
    appointment.version += 1
    session.add(
        _history(
            appointment,
            "rescheduled",
            "provider",
            actor,
            previous_status,
            previous_start,
        )
    )
    session.commit()
    session.refresh(appointment)
    return appointment


def cancel_appointment(
    session: Session, appointment_id: int, version: int, actor: str
) -> Appointment:
    _begin_write(session)
    appointment = _get_appointment(session, appointment_id)
    _check_version(appointment, version)
    if appointment.status != AppointmentStatus.CONFIRMED:
        raise AppointmentError(409, "Only confirmed appointments can be cancelled.")

    previous_status = appointment.status
    appointment.status = AppointmentStatus.CANCELLED
    appointment.version += 1
    session.add(
        _history(
            appointment,
            "cancelled",
            "patient",
            actor,
            previous_status,
            appointment.scheduled_start,
        )
    )
    session.commit()
    session.refresh(appointment)
    return appointment


def process_notification_outbox(session: Session) -> None:
    jobs = session.scalars(
        select(NotificationOutbox)
        .where(NotificationOutbox.status == "pending")
        .order_by(NotificationOutbox.created_at)
    ).all()
    for job in jobs:
        try:
            print(f"Would send {job.notification_type} to {job.recipient}")
            job.status = "sent"
            job.processed_at = now_ist()
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            job.status = "failed"
            job.error = str(exc)
    session.commit()
