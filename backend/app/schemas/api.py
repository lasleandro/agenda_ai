"""
API response schemas for the Phase 4 web calendar.
"""

import uuid
from datetime import date, datetime, time
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.instructor_events import InstructorEventDetail


class AppointmentCreate(BaseModel):
    """Dashboard request for a confirmed appointment."""

    contact_id: uuid.UUID
    place_id: uuid.UUID | None = None
    service: str = Field(min_length=1, max_length=100)
    start_at: datetime
    end_at: datetime
    is_recurring: bool = False
    class_type: Literal["individual", "group"] = "individual"
    max_participants: int | None = Field(default=None, ge=1, le=4)
    contact_ids: list[uuid.UUID] = Field(default_factory=list)
    billing_type: str = Field(default="billable", pattern=r"^(billable|courtesy)$")

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
        participant_ids = self.contact_ids or [self.contact_id]
        if len(participant_ids) > 4:
            raise ValueError("A group can have at most four contacts")
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("Appointment contacts must be unique")
        if self.contact_id not in participant_ids:
            raise ValueError("The primary contact must be a participant")
        if self.class_type == "individual" and len(participant_ids) != 1:
            raise ValueError("An individual class must have one contact")
        if self.class_type == "individual" and self.max_participants not in (None, 1):
            raise ValueError("An individual class has capacity for one contact")
        if self.max_participants is not None and len(participant_ids) > self.max_participants:
            raise ValueError("Appointment contacts exceed the configured capacity")
        return self


class AppointmentFormatUpdate(BaseModel):
    """Explicitly update a persisted appointment's format and capacity."""

    class_type: Literal["individual", "group"]
    max_participants: int = Field(ge=1, le=4)

    @model_validator(mode="after")
    def validate_format_capacity(self) -> Self:
        if self.class_type == "individual" and self.max_participants != 1:
            raise ValueError("An individual class has capacity for one contact")
        return self


class OccurrenceClassFormatUpdate(AppointmentFormatUpdate):
    """Format/capacity for one dated occurrence only."""


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
    max_participants: int = 1
    billing_type: str | None = None
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
    max_participants: int = 1
    billing_type: str | None = None
    participants: list[AppointmentParticipantSummary] = []
    occurrence_date: date | None = None
    is_exception: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecurringClassOccurrenceSummary(BaseModel):
    """A dated projection of a recurring class, including its dated guests."""

    recurring_slot_id: uuid.UUID
    occurrence_date: date
    start_at: datetime
    end_at: datetime
    label: str
    place_id: uuid.UUID | None
    place_name: str | None
    class_type: str
    max_participants: int
    participants: list[AppointmentParticipantSummary] = []
    is_exception: bool = False


class OccurrenceClassFormatDetail(BaseModel):
    source_type: str
    source_id: uuid.UUID
    occurrence_date: date
    class_type: str
    max_participants: int
    participant_count: int
    available_seats: int


class CalendarResponse(BaseModel):
    """Response for GET /api/calendar."""

    appointments: list[AppointmentSummary]
    recurring_classes: list[RecurringClassOccurrenceSummary] = []
    events: list[InstructorEventDetail] = []


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
    operation: str | None
    confirmation_status: str | None
    existing_appointment_id: uuid.UUID | None
    resulting_appointment_id: uuid.UUID | None
    operator_action_candidate_id: uuid.UUID | None
    suggested_place_id: uuid.UUID | None
    resolved_place_id: uuid.UUID | None = None
    matching_place_ids: list[uuid.UUID] = []
    place_stay_id: uuid.UUID | None = None
    place_resolution: str | None = None
    place_source: str | None = None
    place_is_exception: bool = False
    contact_id: uuid.UUID | None
    contact_name: str | None
    proposed_start_at: datetime | None
    proposed_end_at: datetime | None
    service: str | None
    confidence: float | None
    status: str
    escalation_status: str | None = None
    escalation_delivery_status: str | None = None
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


class TenantScheduledTaskSummary(BaseModel):
    """Safe daily-agenda status shown inside a platform-admin tenant tile."""

    configured: bool
    enabled: bool
    local_time: time | None
    consent_confirmed: bool
    readiness_issues: list[str]
    next_run_at: datetime | None
    latest_run_status: str | None
    latest_run_at: datetime | None


class TenantSummary(BaseModel):
    """One tile in the platform-admin tenant grid (multi-tenancy roadmap Phase D)."""

    id: uuid.UUID
    name: str
    status: str
    assistant_phone: str | None
    agent_binding_confirmed_at: datetime | None = None
    contact_count: int
    appointment_count: int
    commercial_financials_enabled: bool
    assistant_temperature: float
    assistant_memory_window_messages: int
    status_changed_at: datetime | None = None
    status_reason: str | None = None
    scheduled_task: TenantScheduledTaskSummary

    model_config = {"from_attributes": True}


class TenantWhatsappNumberUpdate(BaseModel):
    """Platform-admin edit of a tenant's WhatsApp number."""

    whatsapp: str


class TenantListResponse(BaseModel):
    """Paginated response for GET /api/admin/tenants."""

    tenants: list[TenantSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class TenantCreateRequest(BaseModel):
    """Platform-admin request to create a tenant and its initial owner."""

    name: str = Field(min_length=2, max_length=255)
    owner_email: str = Field(min_length=3, max_length=255)
    whatsapp: str = Field(min_length=3, max_length=30)
    timezone: str = Field(default="America/Sao_Paulo", min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_tenant_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Tenant name must contain at least two characters")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def validate_timezone_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Timezone is required")
        return cleaned


class TenantCreateResponse(BaseModel):
    """Created tenant and the address that will receive activation."""

    tenant: TenantSummary
    owner_email: str


class TenantStatusChangeRequest(BaseModel):
    """Admin request body for suspend / archive (reason is optional)."""

    reason: str | None = Field(default=None, max_length=500)


class TenantStatusState(BaseModel):
    """Current tenant lifecycle state returned after a transition."""

    status: str
    status_changed_at: datetime | None
    status_reason: str | None


class TenantFeatureUpdate(BaseModel):
    """Admin request to enable or disable one supported tenant feature."""

    enabled: bool


class TenantFeatureState(BaseModel):
    """Current state returned after an admin feature mutation."""

    feature_key: str
    enabled: bool


class WhatsappConnectionRequestState(BaseModel):
    """Whether the tenant has already asked the admin to connect WhatsApp."""

    requested: bool


class AgentBindingState(BaseModel):
    """Whether the tenant's number is bound to the shared agent channel."""

    bound: bool
    confirmed_at: datetime | None
    platform_number: str | None


class AgentBindingChallengeResponse(BaseModel):
    """A freshly issued binding code for the instructor to send by WhatsApp."""

    code: str
    platform_number: str
    expires_at: datetime


class AssistantSettingsUpdate(BaseModel):
    """Admin request to tune the instructor agent's sampling/memory knobs."""

    temperature: float
    memory_window_messages: int


class AssistantSettingsState(BaseModel):
    """Current instructor-agent settings for one tenant."""

    temperature: float
    memory_window_messages: int


class ScheduledTaskUpdate(BaseModel):
    """Platform-admin configuration for one tenant's daily agenda task."""

    enabled: bool
    local_time: time
    consent_confirmed: bool = False


class ScheduledTaskRunState(BaseModel):
    """Sanitized scheduled-task delivery history row."""

    id: uuid.UUID
    target_local_date: date
    scheduled_for_at: datetime
    status: str
    attempt_count: int
    agenda_item_count: int | None
    class_count: int | None
    event_count: int | None
    last_error_code: str | None
    last_error_detail: str | None
    accepted_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduledTaskHistoryResponse(BaseModel):
    """Paginated run history for one tenant's daily agenda task."""

    runs: list[ScheduledTaskRunState]


class ScheduledTaskAdminSummary(BaseModel):
    """One tenant row in the platform-admin scheduled-task panel."""

    professional_id: uuid.UUID
    professional_name: str
    tenant_status: str
    task_id: uuid.UUID | None
    enabled: bool
    local_time: time
    timezone: str
    consent_confirmed: bool
    sender_phone_masked: str | None
    recipient_phone_masked: str | None
    readiness_issues: list[str]
    next_run_at: datetime | None
    latest_run: ScheduledTaskRunState | None


class ScheduledTaskAdminListResponse(BaseModel):
    """One paginated page of tenant daily-agenda configurations."""

    tasks: list[ScheduledTaskAdminSummary]
    total: int
    page: int
    page_size: int


class ScheduledTaskTenantSuggestion(BaseModel):
    """Minimal tenant result for the scheduled-task creation combobox."""

    id: uuid.UUID
    name: str
    status: str
    timezone: str
    task_configured: bool
    readiness_issues: list[str]


class ScheduledTaskTenantSuggestionResponse(BaseModel):
    """Bounded async tenant-search result set."""

    tenants: list[ScheduledTaskTenantSuggestion]


class ScheduledTaskRunLogEntry(BaseModel):
    """One safe, platform-admin execution-log row."""

    id: uuid.UUID
    professional_id: uuid.UUID
    professional_name: str
    task_type: str
    target_local_date: date
    scheduled_for_at: datetime
    scheduled_local_time: str
    status: str
    attempt_count: int
    agenda_item_count: int | None
    provider_key: str | None
    accepted_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    finished_at: datetime | None
    last_error_code: str | None
    last_error_detail: str | None
    created_at: datetime


class ScheduledTaskRunLogResponse(BaseModel):
    """One paginated page of global scheduled-task execution logs."""

    runs: list[ScheduledTaskRunLogEntry]
    total: int
    page: int
    page_size: int
