"""
API response schemas for the Phase 4 web calendar.
"""

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class AppointmentCreate(BaseModel):
    """Dashboard request for a confirmed appointment."""

    contact_id: uuid.UUID
    place_id: uuid.UUID
    service: str = Field(min_length=1, max_length=100)
    start_at: datetime
    end_at: datetime
    is_recurring: bool = False

    @field_validator("service")
    @classmethod
    def validate_service(cls, service: str) -> str:
        cleaned = service.strip()
        if not cleaned:
            raise ValueError("Service is required")
        return cleaned

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("Appointment times must include a timezone")
        if self.end_at <= self.start_at:
            raise ValueError("Appointment end must be after its start")
        return self


class AppointmentParticipantSummary(BaseModel):
    """One participant on an appointment (the primary contact plus any
    added via propose_add_appointment_participant)."""

    contact_id: uuid.UUID
    display_name: str


class AppointmentSummary(BaseModel):
    """Lightweight appointment for the calendar list view."""

    id: uuid.UUID
    contact_name: str
    contact_id: uuid.UUID
    place_id: uuid.UUID | None
    place_name: str | None
    service: str
    start_at: datetime
    end_at: datetime
    status: str  # tentative | confirmed | cancelled | completed
    source: str
    recurrence_rule: str | None = None
    class_type: str = "individual"
    participants: list[AppointmentParticipantSummary] = []
    # The specific dated occurrence this row represents — pass back on
    # GET /api/appointments/{id}?occurrence_date=... so a rescheduled/
    # recurring occurrence resolves to the right override, not the
    # appointment's original (possibly stale) start_at/end_at/place.
    occurrence_date: date

    model_config = {"from_attributes": True}


class AppointmentDetail(BaseModel):
    """Full appointment detail with related context."""

    id: uuid.UUID
    professional_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    place_id: uuid.UUID | None
    place_name: str | None
    service: str
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
    source: str
    recurrence_rule: str | None = None
    class_type: str = "individual"
    participants: list[AppointmentParticipantSummary] = []
    occurrence_date: date | None = None
    is_exception: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CalendarResponse(BaseModel):
    """Response for GET /api/calendar."""

    appointments: list[AppointmentSummary]


class ConversationSummary(BaseModel):
    """Lightweight conversation for the developer conversation-list view (Phase 1)."""

    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    contact_phone: str | None
    last_message_at: datetime | None
    status: str

    model_config = {"from_attributes": True}


class MessageDetail(BaseModel):
    """A single message, for the developer conversation view (Phase 1)."""

    id: uuid.UUID
    direction: str
    message_type: str
    text: str | None
    sent_at: datetime
    received_at: datetime
    processing_status: str

    model_config = {"from_attributes": True}


class CandidateEvidenceItem(BaseModel):
    """A source message backing an appointment candidate (Phase 2)."""

    message_id: uuid.UUID
    sequence: int
    direction: str
    sent_at: datetime
    text: str | None

    model_config = {"from_attributes": True}


class CandidateDetail(BaseModel):
    """An appointment candidate with its supporting evidence (Phase 2)."""

    id: uuid.UUID
    action: str
    proposed_start_at: datetime | None
    proposed_end_at: datetime | None
    service: str | None
    confidence: float | None
    status: str
    ambiguities: list[dict]
    created_at: datetime
    evidence: list[CandidateEvidenceItem]

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    """Response for GET /api/conversations/{id} — conversation with its messages
    and detected appointment candidates, most recent first."""

    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    contact_phone: str | None
    status: str
    messages: list[MessageDetail]
    candidates: list[CandidateDetail] = []


class ConversationListResponse(BaseModel):
    """Response for GET /api/conversations."""

    conversations: list[ConversationSummary]


class TenantSummary(BaseModel):
    """One tile in the platform-admin tenant grid (multi-tenancy roadmap Phase D)."""

    id: uuid.UUID
    name: str
    status: str
    assistant_phone: str | None
    contact_count: int
    appointment_count: int
    commercial_financials_enabled: bool
    assistant_temperature: float
    assistant_memory_window_messages: int

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    """Response for GET /api/admin/tenants."""

    tenants: list[TenantSummary]


class TenantFeatureUpdate(BaseModel):
    """Admin request to enable or disable one supported tenant feature."""

    enabled: bool


class TenantFeatureState(BaseModel):
    """Current state returned after an admin feature mutation."""

    feature_key: str
    enabled: bool


class AssistantSettingsUpdate(BaseModel):
    """Admin request to tune the instructor agent's sampling/memory knobs."""

    temperature: float
    memory_window_messages: int


class AssistantSettingsState(BaseModel):
    """Current instructor-agent settings for one tenant."""

    temperature: float
    memory_window_messages: int
