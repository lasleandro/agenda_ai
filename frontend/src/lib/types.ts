/** Mirror of the FastAPI AppointmentParticipantSummary schema. */
export interface AppointmentParticipantSummary {
  contact_id: string;
  display_name: string;
}

/** Mirror of the FastAPI AppointmentSummary schema. */
export interface AppointmentSummary {
  id: string;
  contact_name: string;
  contact_id: string;
  place_id: string | null;
  place_name: string | null;
  service: string;
  start_at: string; // ISO 8601
  end_at: string; // ISO 8601
  status: "tentative" | "confirmed" | "cancelled" | "completed";
  source: string;
  recurrence_rule: string | null;
  class_type?: "individual" | "group";
  participants?: AppointmentParticipantSummary[];
  billing_type?: "billable" | "courtesy";
  // The specific dated occurrence this row represents — pass back to
  // fetchAppointment so a rescheduled/recurring occurrence resolves to the
  // right override instead of the appointment's original start_at/place.
  occurrence_date: string;
}

/** Mirror of the FastAPI AppointmentDetail schema. */
export interface AppointmentDetail {
  id: string;
  professional_id: string;
  contact_id: string;
  contact_name: string;
  place_id: string | null;
  place_name: string | null;
  service: string;
  start_at: string;
  end_at: string;
  timezone: string;
  status: "tentative" | "confirmed" | "cancelled" | "completed";
  source: string;
  recurrence_rule: string | null;
  class_type?: "individual" | "group";
  participants?: AppointmentParticipantSummary[];
  occurrence_date?: string | null;
  is_exception?: boolean;
  created_at: string;
  updated_at: string;
}

// Instructor Events (instructor events roadmap v0.1) — non-class calendar
// occupants: refereeing a tournament, running a workshop or clinic. No
// client involved, optional flat fee. Named to avoid confusion with
// audit-log "events" elsewhere in the platform.
export const EVENT_TYPES = ["tournament_referee", "workshop", "clinic", "other"] as const;
export type EventType = (typeof EVENT_TYPES)[number];

/** Mirror of the FastAPI InstructorEventDetail schema. */
export interface InstructorEvent {
  id: string;
  event_type: EventType;
  title: string | null;
  place_id: string | null;
  place_name: string | null;
  start_at: string;
  end_at: string;
  income_cents: number | null;
  note: string | null;
  status: "confirmed" | "cancelled";
  created_at: string;
}

export interface InstructorEventListResponse {
  events: InstructorEvent[];
}

/** Mirror of the FastAPI InstructorEventCreate schema. */
export interface InstructorEventInput {
  event_type: EventType;
  start_at: string;
  end_at: string;
  place_id?: string | null;
  title?: string | null;
  income_cents?: number | null;
  note?: string | null;
}

export interface CalendarResponse {
  appointments: AppointmentSummary[];
  events: InstructorEvent[];
}

export interface AppointmentCreateInput {
  contact_id: string;
  contact_ids?: string[];
  place_id: string;
  service: string;
  start_at: string;
  end_at: string;
  is_recurring: boolean;
  class_type?: "individual" | "group";
  billing_type?: "billable" | "courtesy";
}

/** Mirror of the FastAPI MessageDetail schema. */
export interface MessageDetail {
  id: string;
  direction: "inbound" | "outbound";
  message_type: string;
  text: string | null;
  sent_at: string;
  received_at: string;
  processing_status: string;
}

/** Mirror of the FastAPI CandidateEvidenceItem schema. */
export interface CandidateEvidenceItem {
  message_id: string;
  sequence: number;
  direction: "inbound" | "outbound";
  sent_at: string;
  text: string | null;
}

export type CandidateAction =
  | "create"
  | "confirm"
  | "reschedule"
  | "cancel"
  | "recurrence"
  | "waitlist_request"
  | "none";

/** Mirror of the FastAPI CandidateDetail schema. */
export interface CandidateDetail {
  id: string;
  action: CandidateAction;
  operation: CandidateAction | null;
  confirmation_status:
    | "instructor_confirmed"
    | "customer_confirmed"
    | "mutually_confirmed"
    | "unclear"
    | "not_confirmed"
    | null;
  existing_appointment_id: string | null;
  resulting_appointment_id: string | null;
  operator_action_candidate_id: string | null;
  suggested_place_id: string | null;
  contact_id: string | null;
  contact_name: string | null;
  proposed_start_at: string | null;
  proposed_end_at: string | null;
  service: string | null;
  confidence: number | null;
  status: "detected" | "dismissed" | "fulfilled";
  escalation_status: "proposed" | "confirmed" | "rejected" | "expired" | "executed" | "failed" | null;
  escalation_delivery_status: "queued" | "sent" | "failed" | "expired" | null;
  ambiguities: { field: string; description: string }[];
  created_at: string;
  evidence: CandidateEvidenceItem[];
}

export interface CandidateListResponse {
  candidates: CandidateDetail[];
}

/** Mirror of the FastAPI ConversationDetail schema. */
export interface ConversationDetail {
  id: string;
  contact_id: string;
  contact_name: string;
  contact_phone: string | null;
  status: string;
  messages: MessageDetail[];
  candidates: CandidateDetail[];
}

/** Mirror of the FastAPI ConversationSummary schema. */
export interface ConversationSummary {
  id: string;
  contact_id: string;
  contact_name: string;
  contact_phone: string | null;
  last_message_at: string | null;
  status: string;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
}

/** Response for GET /api/dev/mock-conversation. */
export interface MockConversationInfo {
  conversation_id: string;
  instructor_phone: string;
  customer_phone: string;
}

/** Mirror of the FastAPI TenantSummary schema — one tile in the admin grid. */
export interface TenantSummary {
  id: string;
  name: string;
  status: string;
  assistant_phone: string | null;
  contact_count: number;
  appointment_count: number;
  commercial_financials_enabled: boolean;
  assistant_temperature: number;
  assistant_memory_window_messages: number;
}

export interface TenantListResponse {
  tenants: TenantSummary[];
}

export interface TenantFeatureState {
  feature_key: "commercial_financials";
  enabled: boolean;
}

/** Mirror of the FastAPI AssistantSettingsState schema. */
export interface AssistantSettingsState {
  temperature: number;
  memory_window_messages: number;
}

export type CommercialStatus = "active" | "waiting" | "paused";
export type FinancialValueSource = "customer" | "group" | "place" | "tenant" | "unset";

export interface CommercialOverrideInput {
  commercial_status?: CommercialStatus | null;
  hourly_rate_cents?: number | null;
}

export interface EffectiveCommercialValues {
  commercial_status: CommercialStatus | null;
  hourly_rate_cents: number | null;
  effective_commercial_status: CommercialStatus;
  commercial_status_source: FinancialValueSource;
  effective_hourly_rate_cents: number | null;
  hourly_rate_source: FinancialValueSource;
}

export interface CustomerFinancialDetail extends EffectiveCommercialValues {
  contact_id: string;
  contact_name: string;
}

export type GroupParticipantFinancialDetail = CustomerFinancialDetail;

export interface GroupFinancialDetail extends EffectiveCommercialValues {
  group_id: string;
  label: string | null;
  participant_count: number;
  participants: GroupParticipantFinancialDetail[];
}

export interface GlobalRateDetail {
  participant_count: number;
  hourly_rate_cents: number | null;
}

export interface FinancialSettingsDetail {
  default_commercial_status: CommercialStatus;
  currency: string;
  rates: GlobalRateDetail[];
}

export interface PrimeTimeWindowInput {
  days_of_week: number[];
  start_time: string;
  end_time: string;
}

export interface PrimeTimeWindowDetail extends PrimeTimeWindowInput {
  id: string | null;
  is_default: boolean;
}

export type FinancialTimeCategory = "regular" | "prime";

export interface PlaceRateInput {
  time_category: FinancialTimeCategory;
  participant_count: number;
  hourly_rate_cents: number | null;
}

export interface PlaceRateDetail extends PlaceRateInput {
  effective_hourly_rate_cents: number | null;
  source: "place" | "generic" | "tenant" | "unset";
}

export interface PlaceRateMatrixDetail {
  place_id: string;
  place_name: string;
  rates: PlaceRateDetail[];
}

export interface GenericPlaceRateMatrixDetail {
  rates: PlaceRateDetail[];
}

export interface WorkJourneyIntervalInput {
  day_of_week: number;
  interval_type: "work" | "break";
  start_time: string;
  end_time: string;
}

export interface WorkJourneyIntervalDetail extends WorkJourneyIntervalInput {
  id: string;
}

export interface FinancialConfigurationDetail {
  prime_time_windows: PrimeTimeWindowDetail[];
  generic_place: GenericPlaceRateMatrixDetail;
  places: PlaceRateMatrixDetail[];
}

export interface CancellationNoticeHoursDetail {
  cancellation_notice_hours: number;
}

export interface FinancialAnalyticsAssumptions {
  period_start: string;
  period_end: string;
  timezone: string;
  revenue_basis: string;
  capacity_basis: string;
  excluded_constraints: string[];
}

export interface FinancialMetricBreakdown {
  key: string;
  label: string;
  available_minutes: number;
  booked_minutes: number;
  unused_minutes: number;
  occupancy_pct: number;
  projected_revenue_cents: number;
}

export interface FinancialTimeSeriesPoint {
  date: string;
  available_minutes: number;
  booked_minutes: number;
  projected_revenue_cents: number;
}

export interface MonthlyRevenuePoint {
  month: string;
  label: string;
  projected_revenue_cents: number;
}

export interface ParticipantMixItem {
  participant_count: number;
  percentage: number;
}

export interface CapacityPresetDetail {
  key: "all_individual" | "observed_demand" | "full_groups";
  label: string;
  participant_mix: ParticipantMixItem[];
  occupancy_pct: number;
  participant_hours: number;
  projected_revenue_cents: number;
}

export interface FinancialDashboardDetail {
  assumptions: FinancialAnalyticsAssumptions;
  available_minutes: number;
  booked_minutes: number;
  unused_minutes: number;
  occupancy_pct: number;
  participant_hours: number;
  projected_revenue_cents: number;
  unpriced_booking_count: number;
  observed_participant_mix: ParticipantMixItem[];
  time_series: FinancialTimeSeriesPoint[];
  by_place: FinancialMetricBreakdown[];
  by_part_of_day: FinancialMetricBreakdown[];
  by_weekday: FinancialMetricBreakdown[];
  by_time_category: FinancialMetricBreakdown[];
  capacity_presets: CapacityPresetDetail[];
}

export type FinancialScenarioMode =
  | "all_individual"
  | "observed_demand"
  | "full_groups"
  | "individual_regular_groups_prime"
  | "groups_regular_individual_prime"
  | "custom";

export interface ScenarioRateOverride {
  time_category: FinancialTimeCategory;
  participant_count: number;
  hourly_rate_cents: number;
}

export interface FinancialScenarioInput {
  name: string;
  date_from: string;
  date_to: string;
  place_ids?: string[] | null;
  mode: FinancialScenarioMode;
  occupancy_pct: number;
  participant_mix?: ParticipantMixItem[] | null;
  rate_overrides: ScenarioRateOverride[];
}

export interface FinancialScenarioMetric {
  available_minutes: number;
  utilized_minutes: number;
  occupancy_pct: number;
  participant_hours: number;
  projected_revenue_cents: number;
}

export interface FinancialTradeoffDetail {
  participant_count: number;
  average_hourly_rate_cents: number | null;
  full_class_revenue_cents: number | null;
  revenue_vs_individual_pct: number | null;
  break_even_occupancy_pct: number | null;
}

export interface FinancialScenarioScheduleEvent {
  id: string;
  local_date: string;
  place_name: string;
  start_time: string;
  end_time: string;
  participant_count: number;
  time_category: FinancialTimeCategory;
  hourly_rate_cents: number | null;
  total_revenue_cents: number | null;
}

export interface FinancialScenarioCustomerEstimate {
  calendar_weeks: number;
  weekly_participant_hours: number;
  minimum_customers: number;
  maximum_customers: number;
}

export interface FinancialScenarioResult {
  assumptions: FinancialAnalyticsAssumptions;
  mode: FinancialScenarioMode;
  participant_mix: ParticipantMixItem[];
  baseline: FinancialScenarioMetric;
  scenario: FinancialScenarioMetric;
  incremental_revenue_cents: number;
  incremental_participant_hours: number;
  tradeoffs: FinancialTradeoffDetail[];
  simulated_schedule: FinancialScenarioScheduleEvent[];
  customer_estimate: FinancialScenarioCustomerEstimate | null;
}

export interface FinancialScenarioDetail {
  id: string;
  name: string;
  input_snapshot: FinancialScenarioInput;
  result_snapshot: FinancialScenarioResult;
  created_at: string;
}

export interface FinancialScenarioList {
  scenarios: FinancialScenarioDetail[];
}

export type AttendanceStatus = "attended" | "no_show" | "cancelled";
export type RevenueSourceType = "appointment" | "recurring_slot";
export type RevenueRateSource =
  | "customer"
  | "group"
  | "place"
  | "generic"
  | "tenant"
  | "unset";

export interface RevenueCandidateParticipant {
  contact_id: string;
  contact_name: string;
}

export interface RevenueCandidateDetail {
  source_type: RevenueSourceType;
  source_id: string;
  occurrence_date: string;
  starts_at: string;
  ends_at: string;
  source_label: string;
  place_id: string | null;
  place_name: string | null;
  participants: RevenueCandidateParticipant[];
  recognized_occurrence_id: string | null;
  can_confirm: boolean;
  billing_type?: "billable" | "courtesy" | null;
}

export interface RevenuePreviewDetail {
  estimated_revenue_cents: number | null;
  participant_count: number;
  capacity_revenue_cents?: number | null;
}

export interface RevenueCandidateList {
  total: number;
  limit: number;
  offset: number;
  candidates: RevenueCandidateDetail[];
}

export interface RevenueParticipantOutcomeInput {
  contact_id: string;
  attendance_status: AttendanceStatus;
  billable: boolean;
  non_billable_reason?: string | null;
}

export interface RevenueOccurrenceCreateInput {
  source_type: RevenueSourceType;
  source_id: string;
  occurrence_date: string;
  participant_outcomes: RevenueParticipantOutcomeInput[];
  adjustment_cents: number;
  note: string | null;
}

export interface RevenuePricingLineDetail {
  id: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  time_category: FinancialTimeCategory;
  hourly_rate_cents: number | null;
  rate_source: RevenueRateSource;
  billable: boolean;
  quoted_amount_cents: number;
  billed_amount_cents: number;
  pricing_context: Record<string, unknown>;
}

export interface RevenueOccurrenceParticipantDetail {
  id: string;
  contact_id: string;
  contact_name: string;
  attendance_status: AttendanceStatus;
  billable: boolean;
  non_billable_reason: string | null;
  quoted_amount_cents: number;
  billed_amount_cents: number;
  pricing_lines: RevenuePricingLineDetail[];
}

export interface RevenueOccurrenceDetail {
  id: string;
  source_type: RevenueSourceType;
  source_id: string;
  occurrence_date: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  source_label: string;
  place_id: string | null;
  place_name: string | null;
  outcome_status: AttendanceStatus | "mixed";
  participant_count: number;
  billable_participant_count: number;
  currency: string;
  quoted_total_cents: number;
  subtotal_cents: number;
  adjustment_cents: number;
  total_cents: number;
  note: string | null;
  confirmed_at: string;
  participants: RevenueOccurrenceParticipantDetail[];
}

export interface RevenueSummaryBreakdown {
  key: string;
  label: string;
  occurrence_count: number;
  total_cents: number;
}

export interface RevenueSummaryTimePoint {
  date: string;
  occurrence_count: number;
  total_cents: number;
}

export interface RevenueSummaryDetail {
  period_start: string;
  period_end: string;
  currency: string;
  revenue_basis: string;
  occurrence_count: number;
  participant_count: number;
  billable_participant_count: number;
  quoted_total_cents: number;
  subtotal_cents: number;
  adjustment_cents: number;
  total_cents: number;
  event_income_cents: number;
  event_count: number;
  by_place: RevenueSummaryBreakdown[];
  by_customer: RevenueSummaryBreakdown[];
  by_group: RevenueSummaryBreakdown[];
  time_series: RevenueSummaryTimePoint[];
  occurrences: RevenueOccurrenceDetail[];
}

/** Mapped event for FullCalendar. */
export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  backgroundColor: string;
  borderColor: string;
  textColor: string;
  extendedProps: {
    contactName: string;
    service: string;
    placeName: string | null;
    status: string;
    source: string;
  };
}

// ---------------------------------------------------------------------------
// Customer ontology — Places, RecurringSlots, Contacts
// ---------------------------------------------------------------------------

/** Mirror of the FastAPI PlaceDetail schema ("Local"). */
export interface Place {
  id: string;
  name: string;
  address_line: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  created_at: string;
  updated_at: string;
}

export interface PlaceListResponse {
  places: Place[];
}

export interface PlaceInput {
  name: string;
  address_line?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

// day_of_week: 0=Monday .. 6=Sunday (Python date.weekday() convention).
export const CLASS_TYPES = ["individual", "group"] as const;
export type ClassType = (typeof CLASS_TYPES)[number];

/** Mirror of the FastAPI RecurringSlotDetail schema ("Horário Fixo"). */
export interface RecurringSlot {
  id: string;
  place_id: string;
  place_name: string;
  day_of_week: number;
  start_time: string; // "HH:MM:SS"
  end_time: string;
  label: string | null;
  class_type: ClassType;
  level: string | null;
  max_participants: number;
  recurrence_type: "weekly" | "once";
  scheduled_date: string | null;
  status: string;
  participant_count: number;
}

export interface RecurringSlotListResponse {
  slots: RecurringSlot[];
}

export interface RecurringSlotInput {
  place_id: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  label?: string | null;
  class_type?: ClassType;
  level?: string | null;
  max_participants?: number;
  recurrence_type?: "weekly" | "once";
  scheduled_date?: string | null;
}

export interface RecurringSlotBulkInput extends Omit<RecurringSlotInput, "day_of_week"> {
  days_of_week: number[];
}

export interface RecurringGroupInput {
  place_id: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  label?: string | null;
  level: string;
  max_participants: number;
  contact_ids: string[];
  recurrence_type: "weekly" | "once";
  scheduled_date?: string | null;
}

export interface RecurringSlotParticipant {
  id: string;
  contact_id: string;
  contact_name: string;
}

export interface RecurringGroupDetail extends RecurringSlot {
  participants: RecurringSlotParticipant[];
}

// Plain string, not a fixed union, so new levels can be added without a
// frontend code change beyond this list (matches backend "modular" decision).
export const CONTACT_LEVELS = ["beginner", "intermediate", "advanced"] as const;
export type ContactLevel = (typeof CONTACT_LEVELS)[number];

/** Mirror of the FastAPI ContactSummary schema ("Clientes" list row). */
export interface ContactSummary {
  id: string;
  display_name: string;
  phone: string | null;
  level: string | null;
  home_place_id: string | null;
  home_place_name: string | null;
  makeup_credits_available: number;
}

export interface ContactListResponse {
  contacts: ContactSummary[];
}

/** Mirror of the FastAPI ContactDetail schema. */
export interface ContactDetailData extends ContactSummary {
  address_line: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  makeup_credits_available: number;
  created_at: string;
  fixed_slots: RecurringSlot[];
  courtesy_appointments: CourtesyAppointmentSummary[];
}

export interface CourtesyAppointmentSummary {
  id: string;
  start_at: string;
  end_at: string;
  place_name: string | null;
  service: string;
  status: string;
}

export interface ContactUpdateInput {
  display_name?: string;
  level?: string | null;
  address_line?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  home_place_id?: string | null;
}

/** Mirror of the FastAPI AssistantMessage schema. */
export interface AssistantMessage {
  role: "user" | "assistant";
  content: string;
}

/** Mirror of the FastAPI ToolCallTraceDetail schema. */
export interface AssistantToolCallTrace {
  name: string;
  arguments: Record<string, unknown>;
  result_summary: string;
}

/** Mirror of the FastAPI PendingActionCandidate schema (Phase 3). */
export interface PendingActionCandidate {
  id: string;
  preview_text: string;
  affected_entities: { entity_type: string; entity_id: string; label: string }[];
  expires_at: string;
}

/** Mirror of the FastAPI AssistantChatResponse schema. */
export interface AssistantChatResponse {
  reply: string;
  tool_calls: AssistantToolCallTrace[];
  pending_candidate: PendingActionCandidate | null;
}

/** Mirror of the FastAPI ActionCandidateResultResponse schema. */
export interface ActionCandidateResultResponse {
  status: string;
  summary: string;
}

// Fila de Espera (waitlist roadmap v0.1, Phase 1) — a contact wants a
// specific slot that doesn't exist yet. Not to be confused with
// ContactSummary/commercial "waiting" status ("Em espera"), an unrelated
// paused-billing concept from the financial module.
export type WaitlistEntryStatus = "open" | "matched" | "fulfilled" | "cancelled" | "expired";

/** Mirror of the FastAPI WaitlistEntryDetail schema. */
export interface WaitlistEntry {
  id: string;
  contact_id: string;
  contact_name: string;
  place_id: string | null;
  place_name: string | null;
  desired_date: string; // "YYYY-MM-DD"
  desired_start_time: string; // "HH:MM:SS"
  desired_end_time: string;
  class_type: ClassType | null;
  duration_minutes: number;
  status: WaitlistEntryStatus;
  note: string | null;
  created_at: string;
}

export interface WaitlistEntryListResponse {
  entries: WaitlistEntry[];
}

/** Mirror of the FastAPI WaitlistEntryCreate schema. */
export interface WaitlistEntryInput {
  contact_id: string;
  place_id?: string | null;
  desired_date: string;
  desired_start_time: string;
  desired_end_time: string;
  class_type?: ClassType | null;
  duration_minutes?: number | null;
  note?: string | null;
}

/** Mirror of the FastAPI CandidateFulfillWaitlist schema. */
export interface CandidateFulfillWaitlistInput {
  place_id?: string | null;
  desired_date: string;
  desired_start_time: string;
  desired_end_time: string;
  class_type?: ClassType | null;
  duration_minutes?: number | null;
  note?: string | null;
}
