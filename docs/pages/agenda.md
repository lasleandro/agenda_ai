# Page: Agenda (Calendar)

**Route:** `/` (home page, protected)
**File:** `frontend/src/app/(protected)/page.tsx`

---

## Overview

The Agenda is the primary landing page and main scheduling interface.
It displays a weekly calendar with all appointments, recurring group
slots, and availability blocks.

---

## Key Components

| Component | File | Purpose |
|---|---|---|
| `WeekCalendar` | `components/calendar/week-calendar.tsx` | FullCalendar-based week view. Click-to-create, click-to-view — no drag-to-reschedule; rescheduling a single occurrence is currently an AI-assistant-only action (`propose_reschedule_occurrence`) |
| `AppointmentFormDialog` | `components/calendar/appointment-form-dialog.tsx` | Modal form to create appointments (recurring checkbox, courtesy checkbox) — there's no edit form; editing an existing appointment isn't wired up in the dashboard yet |
| `AppointmentPanel` | `components/calendar/appointment-panel.tsx` | Slide-over read-only detail panel for a single appointment (date/time, place, service, participants, a "Reagendado" badge when viewing a rescheduled occurrence) — no cancel/edit actions live here |
| `StatusBadge` | `components/calendar/status-badge.tsx` | Tailwind-class-per-status pill (tentative/confirmed/cancelled/completed) |
| `GroupDetailsDialog` | `components/ontology/group-details-dialog.tsx` | Modal showing participants of a recurring group |
| `RecurringGroupDialog` | `components/ontology/recurring-group-dialog.tsx` | Form to create new recurring groups |

---

## Data Sources

| Data | Endpoint |
|---|---|
| Calendar events | `GET /api/calendar?start_date=&end_date=` |
| Contacts | `GET /api/contacts` |
| Places | `GET /api/places` |
| Recurring slots | `GET /api/recurring-slots` |

---

## User Actions

| Action | How | Endpoint |
|---|---|---|
| View week | Default view, navigate with arrows or date picker | `GET /api/calendar` |
| Create appointment | Click empty slot → fill form → save | `POST /api/appointments` |
| View appointment | Click event → slide-over panel opens (read-only) | `GET /api/appointments/{id}[?occurrence_date=]` |
| Cancel / reschedule an occurrence | **Not available from the dashboard yet** — currently only via the AI assistant (`propose_cancel_schedule`, `propose_reschedule_occurrence`, `propose_note_participant_absence`) | Creates a `ScheduleOccurrenceOverride` (cancel/reschedule) or nothing on the schedule itself (single-participant absence) |
| Create group | "Criar grupo" button → `RecurringGroupDialog` | `POST /api/recurring-slots/groups` |
| View group | Click group event → `GroupDetailsDialog` | `GET /api/recurring-slots/{id}` |
| Refresh | Manual refresh button (spinning-icon button next to the event count), or automatically right after the AI assistant confirms a mutation | Re-fetches recurring slots + the visible date range |

---

## Visual Design

- **Recurring slots** (no participants): Light indigo background blocks
- **Recurring slots** (with participants): Purple scheduled-group events
- **Appointments**: Color-coded by status (confirmed=blue, cancelled=gray,
  completed=green)
- **Courtesy appointments**: Title includes "(Cortesia)" suffix
- **Overlap indication**: Events that overlap slightly dim in opacity
- **Empty state**: Clean calendar grid with no events

---

## Event Flow

1. User opens Agenda → calendar fetches `fetchCalendar(start, end)` +
   `fetchContacts()` + `fetchPlaces()` + `fetchRecurringSlots()`
2. FullCalendar renders events from the merged data
3. When the assistant *successfully executes* a confirmed action in the
   floating chat, a plain `window` `CustomEvent` (`AGENDA_REFRESH_EVENT`,
   `frontend/src/lib/agenda-events.ts`) is dispatched → `WeekCalendar`
   listens for it and re-fetches recurring slots + the visible range. No
   portal, no tab-focus/`visibilitychange` listener — just this one event
   plus the manual refresh button.
