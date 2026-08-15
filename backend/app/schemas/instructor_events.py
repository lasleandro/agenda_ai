"""API schemas for instructor events (instructor events roadmap v0.1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class InstructorEventCreate(BaseModel):
    event_type: str
    start_at: datetime
    end_at: datetime
    place_id: uuid.UUID | None = None
    title: str | None = None
    income_cents: int | None = None
    note: str | None = None


class InstructorEventDetail(BaseModel):
    id: uuid.UUID
    event_type: str
    title: str | None
    place_id: uuid.UUID | None
    place_name: str | None
    start_at: datetime
    end_at: datetime
    income_cents: int | None
    note: str | None
    status: str
    created_at: datetime


class InstructorEventListResponse(BaseModel):
    events: list[InstructorEventDetail]
