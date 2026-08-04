/** Mirror of the FastAPI AppointmentSummary schema. */
export interface AppointmentSummary {
  id: string;
  contact_name: string;
  contact_id: string;
  service: string;
  start_at: string; // ISO 8601
  end_at: string; // ISO 8601
  status: "tentative" | "confirmed" | "cancelled" | "completed";
  source: string;
}

/** Mirror of the FastAPI AppointmentDetail schema. */
export interface AppointmentDetail {
  id: string;
  professional_id: string;
  contact_id: string;
  contact_name: string;
  service: string;
  start_at: string;
  end_at: string;
  timezone: string;
  status: string;
  source: string;
  recurrence_rule: string | null;
  created_at: string;
  updated_at: string;
}

export interface CalendarResponse {
  appointments: AppointmentSummary[];
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
    status: string;
    source: string;
  };
}
