import type { AppointmentDetail, CalendarResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8005";

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
  id: string
): Promise<AppointmentDetail> {
  const url = `${API_BASE}/api/appointments/${id}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`Failed to fetch appointment: ${res.statusText}`);
  }
  return res.json();
}
