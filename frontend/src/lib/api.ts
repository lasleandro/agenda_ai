import type {
  ActionCandidateResultResponse,
  AppointmentDetail,
  AppointmentFormatInput,
  OccurrenceClassFormatDetail,
  AppointmentCreateInput,
  AssistantChatResponse,
  AssistantMessage,
  AssistantSettingsState,
  CalendarResponse,
  CancellationNoticeHoursDetail,
  CandidateDetail,
  ContactDetailData,
  CommercialOverrideInput,
  CustomerFinancialDetail,
  FinancialConfigurationDetail,
  FinancialDashboardDetail,
  FinancialOperationalAnalyticsDetail,
  FinancialScenarioDetail,
  FinancialScenarioInput,
  FinancialScenarioList,
  FinancialScenarioResult,
  FinancialSettingsDetail,
  ContactListResponse,
  ContactUpdateInput,
  ConversationDetail,
  ConversationListResponse,
  MockCustomer,
  MockCustomerListResponse,
  MockConversationInfo,
  GroupFinancialDetail,
  PlaceRateInput,
  PlaceRateMatrixDetail,
  Place,
  PlaceInput,
  PlaceListResponse,
  RecurringSlot,
  RecurringSlotBulkInput,
  RecurringGroupInput,
  RecurringGroupDetail,
  RecurringSlotInput,
  RecurringSlotListResponse,
  RecurringSlotParticipant,
  RecurringSlotOccurrenceParticipant,
  RecurringGroupOccurrenceDetail,
  SlotKind,
  RevenueCandidateList,
  RevenueOccurrenceCreateInput,
  RevenueOccurrenceDetail,
  RevenuePreviewDetail,
  RevenueSummaryDetail,
  ScheduledTaskAdminListResponse,
  ScheduledTaskAdminSummary,
  ScheduledTaskHistoryResponse,
  ScheduledTaskRunLogResponse,
  ScheduledTaskTenantSuggestionResponse,
  PrimeTimeWindowDetail,
  PrimeTimeWindowInput,
  CandidateFulfillWaitlistInput,
  CandidateListResponse,
  InstructorEvent,
  InstructorEventInput,
  InstructorEventListResponse,
  TenantListResponse,
  TenantFeatureState,
  WaitlistEntry,
  WaitlistEntryInput,
  WaitlistEntryListResponse,
  WorkJourneyIntervalDetail,
  WorkJourneyIntervalInput,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export const sendAssistantMessage = (messages: AssistantMessage[]) =>
  apiRequest<AssistantChatResponse>("/api/assistant/messages", {
    method: "POST",
    body: { messages },
  });

export const confirmAssistantCandidate = (candidateId: string) =>
  apiRequest<ActionCandidateResultResponse>(
    `/api/assistant/candidates/${candidateId}/confirm`,
    { method: "POST" }
  );

export const rejectAssistantCandidate = (candidateId: string) =>
  apiRequest<ActionCandidateResultResponse>(
    `/api/assistant/candidates/${candidateId}/reject`,
    { method: "POST" }
  );

export async function fetchCalendar(
  startDate: string,
  endDate: string
): Promise<CalendarResponse> {
  const url = `${API_BASE}/api/calendar?start_date=${startDate}&end_date=${endDate}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`Failed to fetch calendar: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchAppointment(
  id: string,
  occurrenceDate?: string
): Promise<AppointmentDetail> {
  const query = occurrenceDate
    ? `?occurrence_date=${encodeURIComponent(occurrenceDate)}`
    : "";
  const url = `${API_BASE}/api/appointments/${id}${query}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`Failed to fetch appointment: ${res.statusText}`);
  }
  return res.json();
}

export const createAppointment = (body: AppointmentCreateInput) =>
  apiRequest<AppointmentDetail>("/api/appointments", { method: "POST", body });

export const updateAppointmentFormat = (id: string, body: AppointmentFormatInput) =>
  apiRequest<AppointmentDetail>(`/api/appointments/${id}/format`, {
    method: "PATCH",
    body,
  });

export const updateOccurrenceClassFormat = (
  sourceType: "appointment" | "recurring_slot",
  sourceId: string,
  occurrenceDate: string,
  body: AppointmentFormatInput
) =>
  apiRequest<OccurrenceClassFormatDetail>(
    `/api/schedule-occurrences/${sourceType}/${sourceId}/${occurrenceDate}/format`,
    { method: "PATCH", body }
  );

// ---------------------------------------------------------------------------
// Dev-only mock WhatsApp chat (DEBUG=true backend only, see app/api/dev_mock.py)
// ---------------------------------------------------------------------------

export async function fetchMockConversation(
  customerPhone?: string
): Promise<MockConversationInfo> {
  const query = customerPhone ? `?customer_phone=${encodeURIComponent(customerPhone)}` : "";
  const res = await fetch(`${API_BASE}/api/dev/mock-conversation${query}`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch mock conversation: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchMockCustomers(): Promise<MockCustomerListResponse> {
  const res = await fetch(`${API_BASE}/api/dev/mock-customers`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch mock customers: ${res.statusText}`);
  }
  return res.json();
}

export async function createMockCustomer(): Promise<MockCustomer> {
  const res = await fetch(`${API_BASE}/api/dev/mock-customers`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to create mock customer: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch conversation: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchConversations(): Promise<ConversationListResponse> {
  const res = await fetch(`${API_BASE}/api/conversations`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch conversations: ${res.statusText}`);
  }
  return res.json();
}

export async function sendMockMessage(
  sender: "instructor" | "customer",
  text: string,
  customerPhone: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/dev/mock-messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ sender, text, customer_phone: customerPhone }),
  });
  if (!res.ok) {
    throw new Error(`Failed to send mock message: ${res.statusText}`);
  }
}

export async function resetMockConversation(customerPhone: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/dev/mock-conversation/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ customer_phone: customerPhone }),
  });
  if (!res.ok) {
    throw new Error(`Failed to reset mock conversation: ${res.statusText}`);
  }
}

export async function processConversationNow(
  conversationId: string
): Promise<CandidateDetail[]> {
  const res = await fetch(
    `${API_BASE}/api/dev/conversations/${conversationId}/process-now`,
    { method: "POST", credentials: "include" }
  );
  if (!res.ok) {
    throw new Error(`Failed to process conversation: ${res.statusText}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Platform admin — tenant tile grid (multi-tenancy roadmap Phase D)
// ---------------------------------------------------------------------------

export async function fetchTenants(): Promise<TenantListResponse> {
  const res = await fetch(`${API_BASE}/api/admin/tenants`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch tenants: ${res.statusText}`);
  }
  return res.json();
}

export const updateCommercialFinancials = (tenantId: string, enabled: boolean) =>
  apiRequest<TenantFeatureState>(
    `/api/admin/tenants/${tenantId}/features/commercial-financials`,
    { method: "PATCH", body: { enabled } }
  );

export const updateAssistantSettings = (
  tenantId: string,
  temperature: number,
  memoryWindowMessages: number
) =>
  apiRequest<AssistantSettingsState>(
    `/api/admin/tenants/${tenantId}/assistant-settings`,
    {
      method: "PUT",
      body: {
        temperature,
        memory_window_messages: memoryWindowMessages,
      },
    }
  );

export type ScheduledTaskQuery = {
  q?: string;
  enabled?: boolean;
  tenant_status?: string;
  readiness?: "ready" | "blocked";
  latest_run_status?: string;
  page?: number;
  page_size?: number;
};

export const fetchScheduledTasks = (query: ScheduledTaskQuery = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const suffix = params.toString();
  return apiRequest<ScheduledTaskAdminListResponse>(
    `/api/admin/scheduled-tasks${suffix ? `?${suffix}` : ""}`
  );
};

export const searchScheduledTaskTenants = (q: string) =>
  apiRequest<ScheduledTaskTenantSuggestionResponse>(
    `/api/admin/scheduled-task-tenants?q=${encodeURIComponent(q)}&limit=20`
  );

export type ScheduledTaskRunLogQuery = {
  q?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  provider_key?: string;
  has_error?: boolean;
  page?: number;
  page_size?: number;
};

export const fetchScheduledTaskRuns = (query: ScheduledTaskRunLogQuery = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const suffix = params.toString();
  return apiRequest<ScheduledTaskRunLogResponse>(
    `/api/admin/scheduled-task-runs${suffix ? `?${suffix}` : ""}`
  );
};

export const updateDailyAgendaTask = (
  tenantId: string,
  input: { enabled: boolean; local_time: string; consent_confirmed: boolean }
) =>
  apiRequest<ScheduledTaskAdminSummary>(
    `/api/admin/tenants/${tenantId}/scheduled-tasks/daily-agenda`,
    { method: "PUT", body: input }
  );

export const fetchDailyAgendaTaskRuns = (tenantId: string) =>
  apiRequest<ScheduledTaskHistoryResponse>(
    `/api/admin/tenants/${tenantId}/scheduled-tasks/daily-agenda/runs`
  );

// ---------------------------------------------------------------------------
// Customer ontology — Places, RecurringSlots, Contacts
// ---------------------------------------------------------------------------

async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: unknown } = {}
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    credentials: "include",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `Request failed: ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const fetchPlaces = () => apiRequest<PlaceListResponse>("/api/places");
export const fetchPlace = (id: string) => apiRequest<Place>(`/api/places/${id}`);
export const createPlace = (body: PlaceInput) =>
  apiRequest<Place>("/api/places", { method: "POST", body });
export const updatePlace = (id: string, body: Partial<PlaceInput>) =>
  apiRequest<Place>(`/api/places/${id}`, { method: "PATCH", body });
export const deletePlace = (id: string) =>
  apiRequest<void>(`/api/places/${id}`, { method: "DELETE" });

export const fetchRecurringSlots = (placeId?: string, slotKind?: SlotKind) => {
  const params = new URLSearchParams();
  if (placeId) params.set("place_id", placeId);
  if (slotKind) params.set("slot_kind", slotKind);
  const query = params.toString();
  return apiRequest<RecurringSlotListResponse>(
    `/api/recurring-slots${query ? `?${query}` : ""}`
  );
};
export const fetchRecurringGroup = (id: string) =>
  apiRequest<RecurringGroupDetail>(`/api/recurring-slots/${id}`);
export const fetchRecurringGroupOccurrence = (id: string, occurrenceDate: string) =>
  apiRequest<RecurringGroupOccurrenceDetail>(
    `/api/recurring-slots/${id}/occurrences/${occurrenceDate}`
  );
export const createRecurringSlot = (body: RecurringSlotInput) =>
  apiRequest<RecurringSlot>("/api/recurring-slots", { method: "POST", body });
export const createRecurringSlots = (body: RecurringSlotBulkInput) =>
  apiRequest<RecurringSlot[]>("/api/recurring-slots/bulk", { method: "POST", body });
export const createRecurringGroup = (body: RecurringGroupInput) =>
  apiRequest<RecurringSlot>("/api/recurring-slots/groups", { method: "POST", body });
export const updateRecurringSlot = (id: string, body: Partial<RecurringSlotInput>) =>
  apiRequest<RecurringSlot>(`/api/recurring-slots/${id}`, { method: "PATCH", body });
export const deleteRecurringSlot = (id: string) =>
  apiRequest<void>(`/api/recurring-slots/${id}`, { method: "DELETE" });
export const addSlotParticipant = (slotId: string, contactId: string) =>
  apiRequest<RecurringSlotParticipant>(`/api/recurring-slots/${slotId}/participants`, {
    method: "POST",
    body: { contact_id: contactId },
  });
export const removeSlotParticipant = (slotId: string, contactId: string) =>
  apiRequest<void>(`/api/recurring-slots/${slotId}/participants/${contactId}`, {
    method: "DELETE",
  });
export const addOccurrenceParticipant = (
  slotId: string,
  occurrenceDate: string,
  contactId: string
) =>
  apiRequest<RecurringSlotOccurrenceParticipant>(
    `/api/recurring-slots/${slotId}/occurrences/${occurrenceDate}/participants`,
    { method: "POST", body: { contact_id: contactId } }
  );
export const removeOccurrenceParticipant = (
  slotId: string,
  occurrenceDate: string,
  contactId: string
) =>
  apiRequest<void>(
    `/api/recurring-slots/${slotId}/occurrences/${occurrenceDate}/participants/${contactId}`,
    { method: "DELETE" }
  );

export const fetchWaitlistEntries = (params?: { status?: string; contactId?: string }) => {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.contactId) query.set("contact_id", params.contactId);
  const qs = query.toString();
  return apiRequest<WaitlistEntryListResponse>(
    `/api/waitlist-entries${qs ? `?${qs}` : ""}`
  );
};
export const createWaitlistEntry = (body: WaitlistEntryInput) =>
  apiRequest<WaitlistEntry>("/api/waitlist-entries", { method: "POST", body });
export const cancelWaitlistEntry = (id: string) =>
  apiRequest<WaitlistEntry>(`/api/waitlist-entries/${id}/cancel`, { method: "POST" });
export const fulfillWaitlistEntry = (id: string, appointmentId: string) =>
  apiRequest<WaitlistEntry>(`/api/waitlist-entries/${id}/fulfill`, {
    method: "POST",
    body: { appointment_id: appointmentId },
  });
export const fulfillWaitlistEntryWithGroup = (
  id: string,
  recurringSlotId: string,
  occurrenceDate: string,
  enrollmentScope: "occurrence" | "series"
) =>
  apiRequest<WaitlistEntry>(`/api/waitlist-entries/${id}/fulfill-group`, {
    method: "POST",
    body: {
      recurring_slot_id: recurringSlotId,
      occurrence_date: occurrenceDate,
      enrollment_scope: enrollmentScope,
    },
  });

export const fetchAppointmentCandidates = (status = "detected") =>
  apiRequest<CandidateListResponse>(`/api/appointment-candidates?status=${encodeURIComponent(status)}`);
export const dismissAppointmentCandidate = (id: string) =>
  apiRequest<CandidateDetail>(`/api/appointment-candidates/${id}/dismiss`, { method: "POST" });
export const confirmAppointmentFromCandidate = (
  id: string,
  body: {
    place_id?: string | null;
    start_at?: string | null;
    end_at?: string | null;
    service?: string | null;
  }
) =>
  apiRequest<CandidateDetail>(`/api/appointment-candidates/${id}/confirm-appointment`, {
    method: "POST",
    body,
  });
export const fulfillWaitlistFromCandidate = (id: string, body: CandidateFulfillWaitlistInput) =>
  apiRequest<WaitlistEntry>(`/api/appointment-candidates/${id}/fulfill-waitlist`, {
    method: "POST",
    body,
  });

export const fetchInstructorEvents = () =>
  apiRequest<InstructorEventListResponse>("/api/instructor-events");
export const createInstructorEvent = (body: InstructorEventInput) =>
  apiRequest<InstructorEvent>("/api/instructor-events", { method: "POST", body });
export const cancelInstructorEvent = (id: string) =>
  apiRequest<InstructorEvent>(`/api/instructor-events/${id}/cancel`, { method: "POST" });

export const fetchContacts = () => apiRequest<ContactListResponse>("/api/contacts");
export const fetchContact = (id: string) => apiRequest<ContactDetailData>(`/api/contacts/${id}`);
export const updateContact = (id: string, body: ContactUpdateInput) =>
  apiRequest<ContactDetailData>(`/api/contacts/${id}`, { method: "PATCH", body });

export const fetchCustomerFinancials = (id: string) =>
  apiRequest<CustomerFinancialDetail>(`/api/financial/customers/${id}`);
export const updateCustomerFinancials = (
  id: string,
  body: CommercialOverrideInput
) =>
  apiRequest<CustomerFinancialDetail>(`/api/financial/customers/${id}`, {
    method: "PATCH",
    body,
  });
export const fetchGroupFinancials = (id: string) =>
  apiRequest<GroupFinancialDetail>(`/api/financial/groups/${id}`);
export const updateGroupFinancials = (
  id: string,
  body: CommercialOverrideInput
) =>
  apiRequest<GroupFinancialDetail>(`/api/financial/groups/${id}`, {
    method: "PATCH",
    body,
  });

export const fetchFinancialSettings = () =>
  apiRequest<FinancialSettingsDetail>("/api/financial/settings");
export const updateFinancialSettings = (body: {
  default_commercial_status?: string;
}) =>
  apiRequest<FinancialSettingsDetail>("/api/financial/settings", {
    method: "PATCH",
    body,
  });
export const fetchFinancialConfiguration = () =>
  apiRequest<FinancialConfigurationDetail>("/api/financial/configuration");
export const replacePrimeTimeWindows = (windows: PrimeTimeWindowInput[]) =>
  apiRequest<PrimeTimeWindowDetail[]>("/api/financial/prime-time-windows", {
    method: "PUT",
    body: { windows },
  });
export const replacePlaceRates = (placeId: string, rates: PlaceRateInput[]) =>
  apiRequest<PlaceRateMatrixDetail>(`/api/financial/places/${placeId}/rates`, {
    method: "PUT",
    body: { rates },
  });
export const replaceDefaultRates = (rates: PlaceRateInput[]) =>
  apiRequest<PlaceRateMatrixDetail>("/api/financial/rates/default", {
    method: "PUT",
    body: { rates },
  });

export const fetchWorkJourney = () =>
  apiRequest<WorkJourneyIntervalDetail[]>("/api/rules/work-journey");
export const replaceWorkJourney = (intervals: WorkJourneyIntervalInput[]) =>
  apiRequest<WorkJourneyIntervalDetail[]>("/api/rules/work-journey", {
    method: "PUT",
    body: { intervals },
  });
export const fetchCancellationNoticeHours = () =>
  apiRequest<CancellationNoticeHoursDetail>(
    "/api/rules/cancellation-notice-hours"
  );
export const updateCancellationNoticeHours = (hours: number) =>
  apiRequest<CancellationNoticeHoursDetail>(
    "/api/rules/cancellation-notice-hours",
    {
      method: "PATCH",
      body: { cancellation_notice_hours: hours },
    }
  );

export const fetchFinancialDashboard = (
  dateFrom: string,
  dateTo: string,
  placeIds: string[] = []
) => {
  const params = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
  });
  placeIds.forEach((placeId) => params.append("place_id", placeId));
  return apiRequest<FinancialDashboardDetail>(
    `/api/financial/dashboard?${params.toString()}`
  );
};

export const fetchFinancialOperationalAnalytics = (
  dateFrom: string,
  dateTo: string
) => {
  const params = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
  });
  return apiRequest<FinancialOperationalAnalyticsDetail>(
    `/api/financial/operational-analytics?${params.toString()}`
  );
};

export const evaluateFinancialScenario = (body: FinancialScenarioInput) =>
  apiRequest<FinancialScenarioResult>("/api/financial/scenarios/evaluate", {
    method: "POST",
    body,
  });

export const saveFinancialScenario = (body: FinancialScenarioInput) =>
  apiRequest<FinancialScenarioDetail>("/api/financial/scenarios", {
    method: "POST",
    body,
  });

export const fetchFinancialScenarios = () =>
  apiRequest<FinancialScenarioList>("/api/financial/scenarios");

export const fetchRevenueCandidates = (
  dateFrom: string,
  dateTo: string,
  limit = 100,
  offset = 0
) => {
  const params = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
    limit: String(limit),
    offset: String(offset),
  });
  return apiRequest<RevenueCandidateList>(
    `/api/financial/revenue/candidates?${params.toString()}`
  );
};

export const fetchRevenuePreview = (
  sourceType: "appointment" | "recurring_slot",
  sourceId: string,
  occurrenceDate: string
) => {
  const params = new URLSearchParams({
    source_type: sourceType,
    source_id: sourceId,
    occurrence_date: occurrenceDate,
  });
  return apiRequest<RevenuePreviewDetail>(
    `/api/financial/revenue/preview?${params.toString()}`
  );
};

export const confirmRevenueOccurrence = (
  body: RevenueOccurrenceCreateInput
) =>
  apiRequest<RevenueOccurrenceDetail>(
    "/api/financial/revenue/occurrences",
    { method: "POST", body }
  );

export const fetchRevenueSummary = (
  dateFrom: string,
  dateTo: string,
  occurrenceLimit = 100
) => {
  const params = new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
    occurrence_limit: String(occurrenceLimit),
  });
  return apiRequest<RevenueSummaryDetail>(
    `/api/financial/revenue/summary?${params.toString()}`
  );
};

export const fetchRevenueOccurrence = (id: string) =>
  apiRequest<RevenueOccurrenceDetail>(
    `/api/financial/revenue/occurrences/${id}`
  );
