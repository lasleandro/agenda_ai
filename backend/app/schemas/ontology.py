"""
API schemas for the customer ontology roadmap: Places, RecurringSlots, and
enriched Contacts. Kept separate from schemas/api.py (calendar/conversation
schemas) so each ontology area can evolve independently.
"""

import uuid
from datetime import date, datetime, time
from typing import Literal, Self

from pydantic import BaseModel, field_validator, model_validator

GroupLevel = Literal["beginner", "intermediate", "advanced"]
SlotKind = Literal["availability", "class"]


# ---------------------------------------------------------------------------
# Place ("Local")
# ---------------------------------------------------------------------------

class PlaceCreate(BaseModel):
    name: str
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class PlaceUpdate(BaseModel):
    name: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class PlaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    address_line: str | None
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None

    model_config = {"from_attributes": True}


class PlaceDetail(PlaceSummary):
    postal_code: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime


class PlaceListResponse(BaseModel):
    places: list[PlaceSummary]


# ---------------------------------------------------------------------------
# RecurringSlot ("Horário Fixo")
# ---------------------------------------------------------------------------

class RecurringSlotCreate(BaseModel):
    place_id: uuid.UUID
    day_of_week: int  # 0=Monday .. 6=Sunday
    start_time: time
    end_time: time
    label: str | None = None
    group_name: str | None = None
    class_type: str = "individual"  # "individual" | "group"
    slot_kind: SlotKind = "availability"
    level: GroupLevel | None = None
    max_participants: int = 1
    recurrence_type: str = "weekly"
    scheduled_date: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "RecurringSlotCreate":
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class RecurringSlotBulkCreate(BaseModel):
    place_id: uuid.UUID
    days_of_week: list[int]
    start_time: time
    end_time: time
    label: str | None = None
    group_name: str | None = None
    class_type: str = "individual"
    slot_kind: SlotKind = "availability"
    level: GroupLevel | None = None
    max_participants: int = 1
    valid_from: date | None = None
    valid_until: date | None = None

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, days: list[int]) -> list[int]:
        if not days:
            raise ValueError("Select at least one day of the week")
        if any(day < 0 or day > 6 for day in days):
            raise ValueError("Days of week must be between 0 and 6")
        if len(days) != len(set(days)):
            raise ValueError("Days of week must not contain duplicates")
        return sorted(days)

    @model_validator(mode="after")
    def validate_time_range(self) -> "RecurringSlotBulkCreate":
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class RecurringSlotUpdate(BaseModel):
    place_id: uuid.UUID | None = None
    day_of_week: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    label: str | None = None
    group_name: str | None = None
    class_type: str | None = None
    slot_kind: SlotKind | None = None
    level: GroupLevel | None = None
    max_participants: int | None = None
    recurrence_type: str | None = None
    scheduled_date: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    status: str | None = None


class RecurringSlotDetail(BaseModel):
    id: uuid.UUID
    place_id: uuid.UUID
    place_name: str
    day_of_week: int
    start_time: time
    end_time: time
    label: str | None
    group_name: str | None
    class_type: str
    slot_kind: str
    level: str | None
    max_participants: int
    recurrence_type: str
    scheduled_date: date | None
    valid_from: date | None
    valid_until: date | None
    status: str
    participant_count: int


class RecurringSlotListResponse(BaseModel):
    slots: list[RecurringSlotDetail]


class RecurringSlotParticipantCreate(BaseModel):
    contact_id: uuid.UUID


class RecurringSlotParticipantDetail(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str


class RecurringGroupDetail(RecurringSlotDetail):
    participants: list[RecurringSlotParticipantDetail]


class RecurringGroupCreate(BaseModel):
    place_id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time
    label: str | None = None
    group_name: str | None = None
    level: GroupLevel
    max_participants: int
    contact_ids: list[uuid.UUID]
    recurrence_type: str = "weekly"
    scheduled_date: date | None = None
    valid_from: date | None = None
    valid_until: date | None = None

    @field_validator("day_of_week")
    @classmethod
    def validate_day_of_week(cls, day: int) -> int:
        if day < 0 or day > 6:
            raise ValueError("Day of week must be between 0 and 6")
        return day

    @field_validator("max_participants")
    @classmethod
    def validate_max_participants(cls, capacity: int) -> int:
        if capacity < 2 or capacity > 4:
            raise ValueError("Group capacity must be between 2 and 4")
        return capacity

    @field_validator("contact_ids")
    @classmethod
    def validate_contact_ids(cls, contact_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(contact_ids) < 1:
            raise ValueError("Select at least one contact")
        if len(contact_ids) > 4:
            raise ValueError("A group can have at most four contacts")
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("Contacts must not contain duplicates")
        return contact_ids

    @field_validator("recurrence_type")
    @classmethod
    def validate_recurrence_type(cls, recurrence_type: str) -> str:
        if recurrence_type not in {"weekly", "once"}:
            raise ValueError("Recurrence type must be weekly or once")
        return recurrence_type

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        if self.recurrence_type == "once" and self.scheduled_date is None:
            raise ValueError("A scheduled date is required for a sporadic group")
        if self.scheduled_date is not None and self.day_of_week != self.scheduled_date.weekday():
            raise ValueError("Day of week must match the scheduled date")
        return self


# ---------------------------------------------------------------------------
# Contact ("Clientes")
# ---------------------------------------------------------------------------

class ContactUpdate(BaseModel):
    display_name: str | None = None
    level: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    home_place_id: uuid.UUID | None = None


class ContactSummary(BaseModel):
    id: uuid.UUID
    display_name: str
    phone: str | None
    level: str | None
    home_place_id: uuid.UUID | None
    home_place_name: str | None
    makeup_credits_available: int = 0


class CourtesyAppointmentSummary(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    place_name: str | None
    service: str
    status: str


class ContactDetail(ContactSummary):
    address_line: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    latitude: float | None
    longitude: float | None
    makeup_credits_available: int = 0
    created_at: datetime
    fixed_slots: list[RecurringSlotDetail] = []
    courtesy_appointments: list[CourtesyAppointmentSummary] = []


class ContactListResponse(BaseModel):
    contacts: list[ContactSummary]


class WaitlistEntryCreate(BaseModel):
    contact_id: uuid.UUID
    place_id: uuid.UUID | None = None
    desired_date: date
    desired_start_time: time
    desired_end_time: time
    class_type: str | None = None  # "individual" | "group", None if either works
    duration_minutes: int | None = None  # defaults to (end - start) if omitted
    note: str | None = None


class WaitlistEntryDetail(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    place_id: uuid.UUID | None
    place_name: str | None
    desired_date: date
    desired_start_time: time
    desired_end_time: time
    class_type: str | None
    duration_minutes: int
    status: str
    note: str | None
    created_at: datetime


class WaitlistEntryListResponse(BaseModel):
    entries: list[WaitlistEntryDetail]
