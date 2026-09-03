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
    SQLModel.metadata.create_all(bind=engine)
    seed_data()
    yield


app = FastAPI(title="Patient Portal API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run(action):
    try:
        return action()
    except AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/appointments", response_model=list[AppointmentRead])
def list_appointments(
    provider_id: int | None = Query(default=None),
    patient_email: str | None = Query(default=None),
    session: Session = Depends(get_db),
):
    query = select(Appointment).order_by(Appointment.scheduled_start)
    if provider_id is not None:
        query = query.where(Appointment.provider_id == provider_id)
    if patient_email is not None:
        query = query.where(Appointment.patient_email == patient_email)
    return session.scalars(query).all()


@app.post("/api/appointments", response_model=AppointmentRead, status_code=201)
def request_appointment(payload: AppointmentCreate, session: Session = Depends(get_db)):
    return create_appointment(session, payload)


@app.post("/api/appointments/{appointment_id}/confirm", response_model=AppointmentRead)
def confirm(
    appointment_id: int,
    payload: AppointmentAction,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    appointment = _run(
        lambda: confirm_appointment(
            session, appointment_id, payload.version, "provider-1"
        )
    )
    background_tasks.add_task(_process_notifications)
    return appointment


@app.post(
    "/api/appointments/{appointment_id}/reschedule", response_model=AppointmentRead
)
def reschedule(
    appointment_id: int,
    payload: RescheduleRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    appointment = _run(
        lambda: reschedule_appointment(session, appointment_id, payload, "provider-1")
    )
    background_tasks.add_task(_process_notifications)
    return appointment


@app.post("/api/appointments/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel(
    appointment_id: int,
    payload: AppointmentAction,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
):
    appointment = _run(
        lambda: cancel_appointment(session, appointment_id, payload.version, "patient")
    )
    background_tasks.add_task(_process_notifications)
    return appointment


@app.get("/api/appointments/{appointment_id}/history", response_model=list[HistoryRead])
def appointment_history(appointment_id: int, session: Session = Depends(get_db)):
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return session.scalars(
        select(AppointmentHistory)
        .where(AppointmentHistory.appointment_id == appointment_id)
        .order_by(AppointmentHistory.created_at)
    ).all()


def _process_notifications() -> None:
    with SessionLocal() as session:
        process_notification_outbox(session)
