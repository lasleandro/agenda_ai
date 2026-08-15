"""Scheduling extraction schemas — brief Section 13.

These Pydantic models define the strict structured output the LLM must return.
Instructor (or pydantic-ai) enforces this schema at the API boundary.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Ambiguity(BaseModel):
    """An unresolved ambiguity the LLM detected in the conversation."""

    field: Literal[
        "date",
        "time",
        "duration",
        "customer",
        "service",
        "appointment_reference",
        "confirmation_status",
    ]
    description: str


SchedulingOperation = Literal[
    "create",
    "reschedule",
    "cancel",
    "recurrence",
    "waitlist_request",
    "none",
]

ConfirmationStatus = Literal[
    "instructor_confirmed",
    "customer_confirmed",
    "mutually_confirmed",
    "unclear",
    "not_confirmed",
]


class SchedulingEvent(BaseModel):
    """The structured extraction result for a conversation window.

    operation: the scheduling operation detected (or "none" if no event).
    confirmation_status: who, if anyone, clearly confirmed the operation.
    customer_name: the student/customer name, if identifiable.
    start_at: proposed start datetime (ISO 8601), null if ambiguous. For
        operation="waitlist_request", this is the *desired* start time the
        customer asked for (if any was mentioned), not a booking.
    end_at: proposed end datetime, null if not determinable. Same caveat
        for operation="waitlist_request" as start_at.
    duration_minutes: lesson duration, null if not mentioned.
    service: the service type (e.g. "tennis_lesson"), null if not mentioned.
    existing_appointment_id: reference to an existing appointment for rescheduling/cancellation.
    recurrence_rule: iCal RRULE if recurrence detected, null otherwise.
    confidence: model's self-reported confidence [0.0, 1.0].
    evidence_message_ids: message IDs from the input that support this extraction.
    ambiguities: list of unresolved ambiguities.
    explanation: human-readable explanation of the extraction (in pt-BR).
    """

    operation: SchedulingOperation
    confirmation_status: ConfirmationStatus = "not_confirmed"

    customer_name: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    duration_minutes: int | None = None
    service: str | None = None

    existing_appointment_id: str | None = None
    recurrence_rule: str | None = None

    confidence: float = Field(ge=0.0, le=1.0)
    evidence_message_ids: list[str] = []
    ambiguities: list[Ambiguity] = []
    explanation: str


class SchedulingExtraction(BaseModel):
    """Structured extraction containing every scheduling event in a window."""

    events: list[SchedulingEvent] = Field(min_length=1)
