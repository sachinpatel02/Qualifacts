from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, SQLModel, select

from .database import SessionLocal, engine, get_db
from .models import Appointment, AppointmentHistory, AppointmentStatus
from .schemas import (
    AppointmentAction,
    AppointmentCreate,
    AppointmentRead,
    HistoryRead,
    RescheduleRequest,
)
from .services import (
    AppointmentError,
    cancel_appointment,
    confirm_appointment,
    create_appointment,
    process_notification_outbox,
    reschedule_appointment,
)
from .timezone import now_ist


def seed_data() -> None:
    """Create the demo appointments and their initial history on an empty database."""
    with SessionLocal() as session:
        if session.scalar(select(Appointment.id).limit(1)):
            return
        from datetime import datetime, timedelta

        now = now_ist().replace(minute=0, second=0, microsecond=0)
        seed_appointments = [
            Appointment(
                patient_name="Jordan Lee",
                patient_email="jordan@example.com",
                provider_id=1,
                appointment_type="Therapy follow-up",
                reason="Discuss progress since the last visit",
                scheduled_start=now + timedelta(days=1, hours=2),
                scheduled_end=now + timedelta(days=1, hours=3),
                status="confirmed",
            ),
            Appointment(
                patient_name="Jordan Lee",
                patient_email="jordan@example.com",
                provider_id=1,
                appointment_type="Medication review",
                reason="Review current medication plan",
                scheduled_start=now + timedelta(days=4, hours=1),
                scheduled_end=now + timedelta(days=4, hours=2),
                status="pending",
            ),
            Appointment(
                patient_name="Sam Rivera",
                patient_email="sam@example.com",
                provider_id=1,
                appointment_type="Initial consultation",
                reason="First appointment",
                scheduled_start=now + timedelta(days=7),
                scheduled_end=now + timedelta(days=7, hours=1),
                status="pending",
            ),
        ]
        session.add_all(seed_appointments)
        session.flush()
        for appointment in seed_appointments:
            session.add(
                AppointmentHistory(
                    appointment_id=appointment.id,
                    action="seeded",
                    new_status=AppointmentStatus(appointment.status).value,
                    new_start=appointment.scheduled_start,
                    performed_by_role="system",
                    performed_by_id="seed",
                )
            )
        session.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables and seed demo data before serving requests."""
    SQLModel.metadata.create_all(bind=engine)
    seed_data()
    yield


app = FastAPI(
    title="Patient Portal API",
    description=(
        "Appointment management API for the Harbor Health patient portal. "
        "Appointment timestamps use IST (Asia/Kolkata). Mutations require "
        "the version returned by a read to prevent stale updates."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "system", "description": "Service health and runtime information."},
        {
            "name": "appointments",
            "description": "Create, read, and manage appointments.",
        },
        {
            "name": "history",
            "description": "Inspect immutable appointment audit events.",
        },
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run(action):
    """Translate a domain service error into FastAPI's HTTP error response."""
    try:
        return action()
    except AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get(
    "/api/health",
    tags=["system"],
    summary="Check API health",
    response_description="API availability status.",
)
def health():
    """Return a lightweight liveness response for local and deployment checks."""
    return {"status": "ok"}


@app.get(
    "/api/appointments",
    response_model=list[AppointmentRead],
    tags=["appointments"],
    summary="List appointments",
    description="List appointments for a patient or provider. Omitting filters returns all appointments.",
)
def list_appointments(
    provider_id: int | None = Query(
        default=None, description="Return appointments assigned to this provider."
    ),
    patient_email: str | None = Query(
        default=None, description="Return appointments for this patient email."
    ),
    session: Session = Depends(get_db),
):
    """Return appointments ordered by their IST start time."""
    query = select(Appointment).order_by(Appointment.scheduled_start)
    if provider_id is not None:
        query = query.where(Appointment.provider_id == provider_id)
    if patient_email is not None:
        query = query.where(Appointment.patient_email == patient_email)
    return session.scalars(query).all()


@app.post(
    "/api/appointments",
    response_model=AppointmentRead,
    status_code=201,
    tags=["appointments"],
    summary="Request an appointment",
    description="Create a new pending appointment request.",
)
def request_appointment(payload: AppointmentCreate, session: Session = Depends(get_db)):
    """Create and return a patient's pending appointment request."""
    return create_appointment(session, payload)


@app.post(
    "/api/appointments/{appointment_id}/confirm",
    response_model=AppointmentRead,
    tags=["appointments"],
    summary="Confirm an appointment",
    description="Confirm a pending appointment when the provider has no overlapping confirmed visit.",
    responses={
        409: {"description": "Stale version, invalid status, or provider overlap."}
    },
)
def confirm(
    appointment_id: int,
    payload: AppointmentAction,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    """Confirm an appointment and queue its patient notification."""
    appointment = _run(
        lambda: confirm_appointment(
            session, appointment_id, payload.version, "provider-1"
        )
    )
    background_tasks.add_task(_process_notifications)
    return appointment


@app.post(
    "/api/appointments/{appointment_id}/reschedule",
    response_model=AppointmentRead,
    tags=["appointments"],
    summary="Reschedule an appointment",
    description="Move an appointment to a new IST time; moving a pending request confirms it immediately.",
    responses={
        409: {
            "description": "Stale version, cancelled appointment, or provider overlap."
        }
    },
)
def reschedule(
    appointment_id: int,
    payload: RescheduleRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    """Reschedule an appointment and queue its patient notification."""
    appointment = _run(
        lambda: reschedule_appointment(session, appointment_id, payload, "provider-1")
    )
    background_tasks.add_task(_process_notifications)
    return appointment


@app.post(
    "/api/appointments/{appointment_id}/cancel",
    response_model=AppointmentRead,
    tags=["appointments"],
    summary="Cancel an appointment",
    description="Cancel a confirmed appointment using its latest version token.",
    responses={409: {"description": "Stale version or appointment is not confirmed."}},
)
def cancel(
    appointment_id: int,
    payload: AppointmentAction,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    """Cancel an appointment and queue its patient notification."""
    appointment = _run(
        lambda: cancel_appointment(session, appointment_id, payload.version, "patient")
    )
    background_tasks.add_task(_process_notifications)
    return appointment


@app.get(
    "/api/appointments/{appointment_id}/history",
    response_model=list[HistoryRead],
    tags=["history"],
    summary="Get appointment history",
    description="Return append-only audit events ordered from oldest to newest.",
)
def appointment_history(appointment_id: int, session: Session = Depends(get_db)):
    """Return the audit trail for one appointment."""
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return session.scalars(
        select(AppointmentHistory)
        .where(AppointmentHistory.appointment_id == appointment_id)
        .order_by(AppointmentHistory.created_at)
    ).all()


def _process_notifications() -> None:
    """Process queued notification stubs in a separate database session."""
    with SessionLocal() as session:
        process_notification_outbox(session)
