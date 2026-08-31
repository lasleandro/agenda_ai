# Page: Agenda (Calendar)

**Route:** `/` (home page, protected)
**File:** `frontend/src/app/(protected)/page.tsx`

---

## Overview

The Agenda is the primary landing page and main scheduling interface.
It displays a weekly calendar with calendar items (appointments, recurring
classes, and instructor events) over place-stay background blocks. Tenants
with `commercial_financials` also receive a **Confirmações** subtab for
closing out completed schedule occurrences.

---

## Key Components

| Component | File | Purpose |
|---|---|---|
| `WeekCalendar` | `components/calendar/week-calendar.tsx` | FullCalendar-based week view. Click-to-create, click-to-view — no drag-to-reschedule; rescheduling a single occurrence is currently an AI-assistant-only action (`propose_reschedule_occurrence`) |
| `RevenueConfirmationQueue` | `components/calendar/revenue-confirmation-queue.tsx` | Finance-enabled queue of completed, unrecognized schedule occurrences; opens the existing attendance/billing confirmation dialog |
| `AppointmentFormDialog` | `components/calendar/appointment-form-dialog.tsx` | Modal form with an Aula/Evento toggle. Aula has an Individual/Grupo choice before customer selection; a group can start empty or with up to four customers. Evento creates a non-class `InstructorEvent` (event-type dropdown, optional income). |
| `AppointmentPanel` | `components/calendar/appointment-panel.tsx` | Slide-over read-only detail panel for a single appointment (date/time, place, service, participants, estimated revenue using the Financial rules, a "Reagendado" badge when viewing a rescheduled occurrence) — no cancel/edit actions live here |
| `InstructorEventPanel` | `components/calendar/instructor-event-panel.tsx` | Read-only details for a non-class event: type, date/time, location, optional income, and note |
| `StatusBadge` | `components/calendar/status-badge.tsx` | Tailwind-class-per-status pill (tentative/confirmed/cancelled/completed) |
| `GroupDetailsDialog` | `components/ontology/group-details-dialog.tsx` | Modal showing participants of a recurring group |
| `RecurringGroupDialog` | `components/ontology/recurring-group-dialog.tsx` | Form to create new recurring groups |

---

## Data Sources

| Data | Endpoint |
|---|---|
| Calendar events (appointments + instructor events) | `GET /api/calendar?start_date=&end_date=` |
| Contacts | `GET /api/contacts` |
| Places | `GET /api/places` |
| Recurring slots | `GET /api/recurring-slots` |
| Waitlist entries (open + matched) | `GET /api/waitlist-entries` |
| Completed financial confirmation candidates (feature-gated) | `GET /api/financial/revenue/candidates?date_from=&date_to=` |

---

## User Actions

| Action | How | Endpoint |
|---|---|---|
| View week | Default view, navigate with arrows or date picker | `GET /api/calendar` |
| Create appointment | Click empty slot → fill form (Aula mode) → save | `POST /api/appointments` |
| Create instructor event | Click empty slot → switch to Evento mode → fill form → save | `POST /api/instructor-events` |
| View appointment | Click event → slide-over panel opens (read-only) | `GET /api/appointments/{id}[?occurrence_date=]` |
| View non-class event | Click the amber event → detail panel opens (read-only) | Already-loaded calendar event data |
| View estimated appointment revenue | Open an appointment panel | `GET /api/financial/revenue/preview?source_type=appointment&source_id=&occurrence_date=` |
| Cancel / reschedule an occurrence | **Not available from the dashboard yet** — currently only via the AI assistant (`propose_cancel_schedule`, `propose_reschedule_occurrence`, `propose_note_participant_absence`) | Creates a `ScheduleOccurrenceOverride` (cancel/reschedule) or nothing on the schedule itself (single-participant absence) |
| Create group | "Criar grupo" button → `RecurringGroupDialog` | `POST /api/recurring-slots/groups` |
| View group | Click group event → `GroupDetailsDialog` | `GET /api/recurring-slots/{id}` |
| Refresh | Manual refresh button (spinning-icon button next to the event count), or automatically right after the AI assistant confirms a mutation | Re-fetches recurring slots + the visible date range |
| Toggle Fila de Espera overlay | "Fila de espera" chip next to the event count (default off) | Client-side only, toggles the grey ghost cards already fetched |
| Filter group capacity | "Turmas com vagas" chip next to the event count (default off) | Client-side only; shows projected group occurrences where effective occupancy is below configured capacity, including `0/N`. |
| Confirm a completed occurrence | Agenda → Confirmações → select a completed unrecognized class, record attendance/billing outcome, then confirm | `POST /api/financial/revenue/occurrences` |
| Book a waitlisted contact | Click a grey ghost card → `AppointmentFormDialog` opens pre-filled (contact/place/time) → save | `POST /api/appointments` then `POST /api/waitlist-entries/{id}/fulfill` |
| Fill a group seat from the waitlist | Open the dated group card → choose a compatible waitlist request and **Nesta aula** or **Todas as semanas** under “Preencher vaga da fila” | `POST /api/waitlist-entries/{id}/fulfill-group` |

---

## Visual Design

- **Visible time range**: The week and day grids display 07:00 through 22:00,
  including appointments scheduled from 21:00 to 22:00.
- **Place stays** (`slot_kind="availability"`): Light indigo background blocks
- **Work-journey pauses**: Light slate background blocks labeled "Pausa";
  non-interactive and visually subordinate to appointments and classes
- **Recurring classes** (`slot_kind="class"`): Purple scheduled-class events;
  roster size never determines their calendar meaning
- **Appointments**: Color-coded by status (confirmed=blue, cancelled=gray,
  completed=green)
- **Courtesy appointments**: Title includes "(Cortesia)" suffix
- **Overlap indication**: Events that overlap slightly dim in opacity
- **Empty state**: Clean calendar grid with no events
- **Waitlist ghost cards**: Grey background, dashed border (`.agenda-waitlist-entry`
  in `globals.css`) — deliberately distinct from every status color so they
  read unmistakably as "not a real booking." Hidden by default behind the
  Fila de Espera toggle.
- **Instructor events**: Solid amber blocks, always visible (no toggle) —
  distinct from appointment-status colors and the grey waitlist cards.
  Read-only on click for now; no edit/cancel UI wired up yet.
- **Confirmações subtab**: Available only with `commercial_financials`; it
  lists completed, unrecognized occurrences from the current month in newest
  first order. Future classes are intentionally excluded, even though they are
  scheduled in Agenda.

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
