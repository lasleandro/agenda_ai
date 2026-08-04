"""
Calendar API — Phase 4 read endpoints.

GET  /api/calendar          — list appointments for a date range (query params:
                              start_date, end_date).
GET  /api/appointments/{id} — single appointment detail.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_authenticated
from app.database import SessionLocal
from app.models import Appointment, Contact
from app.schemas.api import AppointmentDetail, AppointmentSummary, CalendarResponse

router = APIRouter(prefix="/api", tags=["calendar"])

TZ_SP = timezone(timedelta(hours=-3))  # America/Sao_Paulo


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/calendar", response_model=CalendarResponse)
def list_appointments(
    start_date: date = Query(..., description="Start date (ISO format, e.g. 2026-08-03)"),
    end_date: date = Query(..., description="End date (ISO format, inclusive)"),
    db: Session = Depends(get_db),
    _user: dict = Depends(require_authenticated),
):
    """Return all appointments whose start falls within [start_date, end_date]."""
    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=TZ_SP)
    end_dt = datetime(
        end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=TZ_SP
    )

    rows = (
        db.query(Appointment, Contact.display_name)
        .join(Contact, Appointment.contact_id == Contact.id)
        .filter(Appointment.start_at >= start_dt, Appointment.start_at <= end_dt)
        .order_by(Appointment.start_at)
        .all()
    )

    appointments = [
        AppointmentSummary(
            id=appt.id,
            contact_name=contact_name,
            contact_id=appt.contact_id,
            service=appt.service,
            start_at=appt.start_at,
            end_at=appt.end_at,
            status=appt.status,
            source=appt.source,
        )
        for appt, contact_name in rows
    ]

    return CalendarResponse(appointments=appointments)


@router.get("/appointments/{appointment_id}", response_model=AppointmentDetail)
def get_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_authenticated),
):
    """Return a single appointment with full detail."""
    appt = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id)
        .first()
    )
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    contact = db.query(Contact).filter(Contact.id == appt.contact_id).first()

    return AppointmentDetail(
        id=appt.id,
        professional_id=appt.professional_id,
        contact_id=appt.contact_id,
        contact_name=contact.display_name if contact else "Desconhecido",
        service=appt.service,
        start_at=appt.start_at,
        end_at=appt.end_at,
        timezone=appt.timezone,
        status=appt.status,
        source=appt.source,
        recurrence_rule=appt.recurrence_rule,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
    )
