"""Contracts for the optional commercial and financial module."""

import uuid
from datetime import date, datetime, time
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

CommercialStatus = Literal["active", "waiting", "paused"]
ValueSource = Literal["customer", "group", "place", "tenant", "unset"]


class CommercialOverrideUpdate(BaseModel):
    commercial_status: CommercialStatus | None = None
    hourly_rate_cents: int | None = Field(default=None, ge=0, le=100_000_000)


class EffectiveCommercialValues(BaseModel):
    commercial_status: CommercialStatus | None
    hourly_rate_cents: int | None
    effective_commercial_status: CommercialStatus
    commercial_status_source: ValueSource
    effective_hourly_rate_cents: int | None
    hourly_rate_source: ValueSource


class CustomerFinancialDetail(EffectiveCommercialValues):
    contact_id: uuid.UUID
    contact_name: str


class GroupParticipantFinancialDetail(CustomerFinancialDetail):
    pass


class GroupFinancialDetail(EffectiveCommercialValues):
    group_id: uuid.UUID
    label: str | None
    participant_count: int
    participants: list[GroupParticipantFinancialDetail]


class GlobalRateInput(BaseModel):
    participant_count: int = Field(ge=1, le=4)
    hourly_rate_cents: int | None = Field(default=None, ge=0, le=100_000_000)


class FinancialSettingsUpdate(BaseModel):
    default_commercial_status: CommercialStatus | None = None
    rates: list[GlobalRateInput] | None = None

    @field_validator("default_commercial_status")
    @classmethod
    def validate_default_status(
        cls,
        status: CommercialStatus | None,
    ) -> CommercialStatus:
        if status is None:
            raise ValueError("Default commercial status cannot be null")
        return status

    @field_validator("rates")
    @classmethod
    def validate_unique_participant_counts(
        cls,
        rates: list[GlobalRateInput] | None,
    ) -> list[GlobalRateInput] | None:
        if rates is None:
            return None
        counts = [rate.participant_count for rate in rates]
        if len(counts) != len(set(counts)):
            raise ValueError("Participant counts must not contain duplicates")
        return rates


class GlobalRateDetail(BaseModel):
    participant_count: int
    hourly_rate_cents: int | None


class FinancialSettingsDetail(BaseModel):
    default_commercial_status: CommercialStatus
    currency: str
    rates: list[GlobalRateDetail]


class PrimeTimeWindowInput(BaseModel):
    days_of_week: list[int]
    start_time: time
    end_time: time

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, days: list[int]) -> list[int]:
        if not days:
            raise ValueError("Select at least one weekday")
        if any(day < 0 or day > 6 for day in days):
            raise ValueError("Weekdays must be between zero and six")
        if len(days) != len(set(days)):
            raise ValueError("Weekdays must not contain duplicates")
        return sorted(days)

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("Prime-time ranges must end after they start")
        return self


class PrimeTimeWindowDetail(PrimeTimeWindowInput):
    id: uuid.UUID | None
    is_default: bool = False


class PrimeTimeWindowsReplace(BaseModel):
    windows: list[PrimeTimeWindowInput]


class PlaceRateInput(BaseModel):
    time_category: Literal["regular", "prime"]
    participant_count: int = Field(ge=1, le=4)
    hourly_rate_cents: int | None = Field(default=None, ge=0, le=100_000_000)


class PlaceRatesReplace(BaseModel):
    rates: list[PlaceRateInput]

    @field_validator("rates")
    @classmethod
    def validate_unique_rules(cls, rates: list[PlaceRateInput]) -> list[PlaceRateInput]:
        rules = [(rate.time_category, rate.participant_count) for rate in rates]
        if len(rules) != len(set(rules)):
            raise ValueError("Place rate rules must not contain duplicates")
        return rates


class PlaceRateDetail(PlaceRateInput):
    effective_hourly_rate_cents: int | None
    source: Literal["place", "tenant", "unset"]


class PlaceRateMatrixDetail(BaseModel):
    place_id: uuid.UUID
    place_name: str
    rates: list[PlaceRateDetail]


class FinancialConfigurationDetail(BaseModel):
    prime_time_windows: list[PrimeTimeWindowDetail]
    places: list[PlaceRateMatrixDetail]


class PricingQuoteInput(BaseModel):
    place_id: uuid.UUID
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    participant_count: int = Field(ge=1, le=4)

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("Pricing quotes must end after they start")
        return self


class PricingQuoteSegment(BaseModel):
    start_time: time
    end_time: time
    duration_minutes: int
    time_category: Literal["regular", "prime"]
    hourly_rate_cents: int | None
    source: Literal["place", "tenant", "unset"]
    segment_total_cents: int | None


class PricingQuoteDetail(BaseModel):
    participant_count: int
    segments: list[PricingQuoteSegment]
    total_cents: int | None


class FinancialAnalyticsAssumptions(BaseModel):
    period_start: date
    period_end: date
    timezone: str
    revenue_basis: str
    capacity_basis: str
    excluded_constraints: list[str]


class FinancialMetricBreakdown(BaseModel):
    key: str
    label: str
    available_minutes: int
    booked_minutes: int
    unused_minutes: int
    occupancy_pct: float
    projected_revenue_cents: int


class FinancialTimeSeriesPoint(BaseModel):
    date: date
    available_minutes: int
    booked_minutes: int
    projected_revenue_cents: int


class ParticipantMixItem(BaseModel):
    participant_count: int = Field(ge=1, le=4)
    percentage: float = Field(ge=0, le=100)


class CapacityPresetDetail(BaseModel):
    key: Literal["all_individual", "observed_demand", "full_groups"]
    label: str
    participant_mix: list[ParticipantMixItem]
    occupancy_pct: float
    participant_hours: float
    projected_revenue_cents: int


class FinancialDashboardDetail(BaseModel):
    assumptions: FinancialAnalyticsAssumptions
    available_minutes: int
    booked_minutes: int
    unused_minutes: int
    occupancy_pct: float
    participant_hours: float
    projected_revenue_cents: int
    unpriced_booking_count: int
    observed_participant_mix: list[ParticipantMixItem]
    time_series: list[FinancialTimeSeriesPoint]
    by_place: list[FinancialMetricBreakdown]
    by_part_of_day: list[FinancialMetricBreakdown]
    by_weekday: list[FinancialMetricBreakdown]
    by_time_category: list[FinancialMetricBreakdown]
    capacity_presets: list[CapacityPresetDetail]


class ScenarioRateOverride(BaseModel):
    time_category: Literal["regular", "prime"]
    participant_count: int = Field(ge=1, le=4)
    hourly_rate_cents: int = Field(ge=0, le=100_000_000)


class FinancialScenarioInput(BaseModel):
    name: str = Field(default="Cenário sem nome", min_length=1, max_length=120)
    date_from: date
    date_to: date
    place_ids: list[uuid.UUID] | None = None
    mode: Literal[
        "all_individual",
        "observed_demand",
        "full_groups",
        "custom",
    ] = "observed_demand"
    occupancy_pct: float = Field(default=100, ge=0, le=100)
    participant_mix: list[ParticipantMixItem] | None = None
    rate_overrides: list[ScenarioRateOverride] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise ValueError("Scenario name cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_scenario(self) -> Self:
        if self.date_to < self.date_from:
            raise ValueError("Scenario end date must be on or after start date")
        if (self.date_to - self.date_from).days > 365:
            raise ValueError("Scenario period cannot exceed 366 days")
        if self.place_ids is not None and len(self.place_ids) != len(
            set(self.place_ids)
        ):
            raise ValueError("Scenario places must not contain duplicates")
        rules = [
            (rate.time_category, rate.participant_count)
            for rate in self.rate_overrides
        ]
        if len(rules) != len(set(rules)):
            raise ValueError("Scenario rate overrides must not contain duplicates")
        if self.participant_mix:
            counts = [item.participant_count for item in self.participant_mix]
            if len(counts) != len(set(counts)):
                raise ValueError("Participant mix must not contain duplicates")
            if abs(sum(item.percentage for item in self.participant_mix) - 100) > 0.01:
                raise ValueError("Participant mix percentages must total 100")
        if self.mode == "custom" and not self.participant_mix:
            raise ValueError("Custom scenarios require a participant mix")
        return self


class FinancialScenarioMetric(BaseModel):
    available_minutes: int
    utilized_minutes: int
    occupancy_pct: float
    participant_hours: float
    projected_revenue_cents: int


class FinancialTradeoffDetail(BaseModel):
    participant_count: int
    average_hourly_rate_cents: int | None
    full_class_revenue_cents: int | None
    revenue_vs_individual_pct: float | None
    break_even_occupancy_pct: float | None


class FinancialScenarioResult(BaseModel):
    assumptions: FinancialAnalyticsAssumptions
    mode: str
    participant_mix: list[ParticipantMixItem]
    baseline: FinancialScenarioMetric
    scenario: FinancialScenarioMetric
    incremental_revenue_cents: int
    incremental_participant_hours: float
    tradeoffs: list[FinancialTradeoffDetail]


class FinancialScenarioDetail(BaseModel):
    id: uuid.UUID
    name: str
    input_snapshot: FinancialScenarioInput
    result_snapshot: FinancialScenarioResult
    created_at: datetime


class FinancialScenarioList(BaseModel):
    scenarios: list[FinancialScenarioDetail]


AttendanceStatus = Literal["attended", "no_show", "cancelled"]
RevenueSourceType = Literal["appointment", "recurring_slot"]
RevenueRateSource = Literal["customer", "group", "place", "tenant", "unset"]


class RevenueCandidateParticipant(BaseModel):
    contact_id: uuid.UUID
    contact_name: str


class RevenueCandidateDetail(BaseModel):
    source_type: RevenueSourceType
    source_id: uuid.UUID
    occurrence_date: date
    starts_at: datetime
    ends_at: datetime
    source_label: str
    place_id: uuid.UUID | None
    place_name: str | None
    participants: list[RevenueCandidateParticipant]
    recognized_occurrence_id: uuid.UUID | None
    can_confirm: bool
    billing_type: str | None = None


class RevenueCandidateList(BaseModel):
    total: int
    limit: int
    offset: int
    candidates: list[RevenueCandidateDetail]


class RevenueParticipantOutcomeInput(BaseModel):
    contact_id: uuid.UUID
    attendance_status: AttendanceStatus
    billable: bool
    non_billable_reason: str | None = None


class RevenueOccurrenceCreate(BaseModel):
    source_type: RevenueSourceType
    source_id: uuid.UUID
    occurrence_date: date
    participant_outcomes: list[RevenueParticipantOutcomeInput]
    adjustment_cents: int = Field(default=0, ge=-100_000_000, le=100_000_000)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("participant_outcomes")
    @classmethod
    def validate_unique_participants(
        cls,
        outcomes: list[RevenueParticipantOutcomeInput],
    ) -> list[RevenueParticipantOutcomeInput]:
        contact_ids = [outcome.contact_id for outcome in outcomes]
        if not outcomes:
            raise ValueError("At least one participant outcome is required")
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("Participant outcomes must not contain duplicates")
        return outcomes

    @field_validator("note")
    @classmethod
    def normalize_note(cls, note: str | None) -> str | None:
        if note is None:
            return None
        return note.strip() or None


class RevenuePricingLineDetail(BaseModel):
    id: uuid.UUID
    start_time: time
    end_time: time
    duration_minutes: int
    time_category: Literal["regular", "prime"]
    hourly_rate_cents: int | None
    rate_source: RevenueRateSource
    billable: bool
    quoted_amount_cents: int
    billed_amount_cents: int
    pricing_context: dict


class RevenueOccurrenceParticipantDetail(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    attendance_status: AttendanceStatus
    billable: bool
    non_billable_reason: str | None = None
    quoted_amount_cents: int
    billed_amount_cents: int
    pricing_lines: list[RevenuePricingLineDetail]


class RevenueOccurrenceDetail(BaseModel):
    id: uuid.UUID
    source_type: RevenueSourceType
    source_id: uuid.UUID
    occurrence_date: date
    starts_at: datetime
    ends_at: datetime
    timezone: str
    source_label: str
    place_id: uuid.UUID | None
    place_name: str | None
    outcome_status: Literal["attended", "no_show", "cancelled", "mixed"]
    participant_count: int
    billable_participant_count: int
    currency: str
    quoted_total_cents: int
    subtotal_cents: int
    adjustment_cents: int
    total_cents: int
    note: str | None
    confirmed_at: datetime
    participants: list[RevenueOccurrenceParticipantDetail]


class RevenueSummaryBreakdown(BaseModel):
    key: str
    label: str
    occurrence_count: int
    total_cents: int


class RevenueSummaryTimePoint(BaseModel):
    date: date
    occurrence_count: int
    total_cents: int


class RevenueSummaryDetail(BaseModel):
    period_start: date
    period_end: date
    currency: str
    revenue_basis: str
    occurrence_count: int
    participant_count: int
    billable_participant_count: int
    quoted_total_cents: int
    subtotal_cents: int
    adjustment_cents: int
    total_cents: int
    by_place: list[RevenueSummaryBreakdown]
    by_customer: list[RevenueSummaryBreakdown]
    by_group: list[RevenueSummaryBreakdown]
    time_series: list[RevenueSummaryTimePoint]
    occurrences: list[RevenueOccurrenceDetail]
