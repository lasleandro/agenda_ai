"""
API response schemas for the Phase 4 web calendar.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AppointmentSummary(BaseModel):
    """Lightweight appointment for the calendar list view."""

    id: uuid.UUID
    contact_name: str
    contact_id: uuid.UUID
    service: str
    start_at: datetime
    end_at: datetime
    status: str  # tentative | confirmed | cancelled | completed
    source: str

    model_config = {"from_attributes": True}


class AppointmentDetail(BaseModel):
    """Full appointment detail with related context."""

    id: uuid.UUID
    professional_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    service: str
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
    source: str
    recurrence_rule: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CalendarResponse(BaseModel):
    """Response for GET /api/calendar."""

    appointments: list[AppointmentSummary]
