"""Conversation input schema for the extraction pipeline.

Represents the normalized conversation window passed to the LLM.
Matches the format in brief Section 12.3.
"""

from datetime import datetime

from pydantic import BaseModel


class ProfessionalContext(BaseModel):
    """Professional (instructor) defaults."""

    timezone: str = "America/Sao_Paulo"
    default_duration_minutes: int = 60
    service: str = "tennis_lesson"


class ContactContext(BaseModel):
    """Customer/contact info."""

    display_name: str


class UpcomingAppointment(BaseModel):
    """An existing appointment for context (e.g. for rescheduling)."""

    id: str
    start_at: datetime
    end_at: datetime
    service: str | None = None


class Message(BaseModel):
    """A single normalized message in the conversation."""

    id: str
    direction: str  # "inbound" | "outbound"
    sent_at: datetime
    text: str


class ConversationWindow(BaseModel):
    """The full input passed to the extraction LLM.

    This is the normalized conversation context described in brief Section 12.3.
    """

    professional: ProfessionalContext
    contact: ContactContext
    current_time: datetime
    upcoming_appointments: list[UpcomingAppointment] = []
    messages: list[Message]
