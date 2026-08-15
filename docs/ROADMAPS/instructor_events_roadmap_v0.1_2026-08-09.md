# Instructor Events Roadmap v0.1 — 2026-08-09

**Status: implemented 2026-08-09 (all 3 phases).** Decisions confirmed before build: cancelling an event frees its conflict slot immediately (same as `Appointment.status` filtering); pt-BR labels required on the frontend for `event_type`; initial `event_type` set kept as scoped (tournament_referee/workshop/clinic/other).

## The idea

Instructors sometimes do paid work that isn't a class: refereeing a tournament, running a workshop or clinic. Today the only way to occupy the calendar is `Appointment`, which requires a client (`contact_id` is NOT NULL) and routes income through the participant-priced revenue engine — neither fits "I'm refereeing a tournament Saturday, no client involved, flat fee." This adds a second, lightweight kind of calendar occupant: `InstructorEvent`.

Explicitly out of scope for this pass, per instructor decision: passive-observer extraction (no `SchedulingEvent.action == "event"`) — platform dashboard and active agent only.

## Naming

`InstructorEvent`, not `Event` — the codebase already has `OperationalEvent` (the audit ledger, with its own `EVENT_TYPES`). Two things both called "Event" invites import/grep confusion.

## Data model

A new standalone table, not a variant of `Appointment`:

```python
class InstructorEvent(Base):
    __tablename__ = "instructor_events"

    id: UUID
    professional_id: UUID   # FK professionals.id, tenant scope
    place_id: UUID | None   # FK places.id — nullable, may be off-site (a
                             # tournament venue that isn't a registered Place)
    event_type: str         # "tournament_referee" | "workshop" | "clinic" | "other"
                             # plain string, not a DB enum — same "modular"
                             # convention as Contact.level / RecurringSlot.class_type
    title: str | None       # free text, e.g. "Clínica de saque"
    start_at: datetime
    end_at: datetime
    income_cents: int | None
    note: str | None
    status: str              # "confirmed" | "cancelled" — simpler than
                              # Appointment's tentative/confirmed/completed;
                              # no client to confirm attendance with
    created_at: datetime
    updated_at: datetime
```

No `AppointmentParticipant`-equivalent, no billing_type, no recurrence — a one-off block of time with an optional flat fee. If recurring events turn out to be common (a monthly clinic), extend later; YAGNI for v1.

## Conflict checking — events and classes share one busy-time set

If the instructor is refereeing 15:00–20:00, the system must not let a class also get booked then, and vice versa. Extend `app/services/appointments.py::assert_no_conflict` with a new `has_event_overlap` check (mirrors `has_appointment_overlap`), and add the symmetric check to event creation (checks `has_appointment_overlap`/`has_scheduled_class_overlap` too). One unified "is the instructor already busy" rule, regardless of which table the busy time lives in.

**Events are exempt from `assert_within_work_journey`.** A Saturday tournament is by definition outside normal teaching hours — that's the point of it. Work-journey enforcement stays specific to classes/appointments.

## Calendar surface

Extend `GET /api/calendar` to also return `events: InstructorEventSummary[]` for the queried range (same endpoint the Agenda screen already fetches, rather than a third separate fetch+merge — `week-calendar.tsx` already merges `Appointment` + `RecurringSlot` client-side; events become a third source into the same `calendarEvents` array). Rendered in a distinct color, not confusable with appointment-status colors or the grey waitlist ghost cards.

## Revenue integration — confirmed summary, not the projection dashboard

Two different "financial" surfaces exist today, and event income belongs in only one of them:

- **`app/services/financial_analytics.py` (Financeiro tab, `GET /api/financial/dashboard`)** is a *projected* revenue tool — it buckets available capacity segments (by place/weekday/part-of-day/prime-time category) and projects what classes could earn if booked. An event isn't a capacity segment being filled; it doesn't fit this model and won't be added to it.
- **`GET /api/revenue/summary` (`RevenueSummaryDetail`)** is the *confirmed/actual* revenue tracker — the natural home. Add a top-level `event_income_cents` (summed from `InstructorEvent.income_cents` where `status="confirmed"` and `start_at` falls in the queried period), surfaced alongside — not merged into — the existing participant-priced `by_place`/`by_customer`/`by_group` breakdowns, which are specifically about billing individual clients and don't apply to a flat-fee event.
- No confirmation step needed for event income the way class revenue needs participant-outcome confirmation (`RevenueOccurrence`'s whole immutable-snapshot flow) — the income is the instructor's own money, entered directly, no attendance ambiguity to resolve.

## Frontend

Toggle at the top of `AppointmentFormDialog`: "Aula" / "Evento". Switching to Evento swaps the client picker for an event-type dropdown + optional income input (R$), keeps place (now optional) and the start/end time already selected from the calendar click/drag. Submits to a new `POST /api/instructor-events` instead of `POST /api/appointments`.

## Agent tools

Both channel-agnostic (web chat + WhatsApp, same orchestrator, no extra work per channel):

- `list_events(date_from?, date_to?)` (read) — companion read tool, same read/write pairing convention every other domain in this codebase follows.
- `propose_create_event(event_type, start_at, end_at, place_id?, title?, income_cents?, note?)` (write, requires confirm) — e.g. *"Amanha das 15 às 20h vou dar uma clinica. Vou receber R$ 2000."* Date/time resolved via the existing `resolve_date_phrase` tool (same as appointments); `event_type` inferred from wording ("clínica"→clinic, "arbitrar"/"arbitragem"→tournament_referee, "workshop"/"oficina"→workshop, else "other"); income parsed from "R$ 2000" → `income_cents=200000`. Same propose→confirm→execute flow as every other mutation — nothing new to build on the safety side.

## Phasing

**Phase 1 — Data model + conflict checking + dashboard form toggle — implemented 2026-08-09.**
`InstructorEvent` model + migration (`app/models/instructor_event.py`); `app/services/instructor_events.py` (create/list/cancel + `assert_no_event_conflict`); `has_event_overlap` added to `app/services/appointments.py` and wired into `assert_no_conflict` (symmetric — an event blocks a class and vice versa; cancelled events/appointments don't block, per the confirmed decision); `app/api/instructor_events.py` (list/create/cancel, registered in `main.py`); `GET /api/calendar` extended with an `events` array (`CalendarResponse.events`); `AppointmentFormDialog` gained an Aula/Evento toggle (event-type dropdown, optional income field, place now optional); `week-calendar.tsx` renders events as a distinct amber block (`instructorEventToEvent`), read-only for now (no edit/cancel UI built). pt-BR labels in `ontology-utils.ts::EVENT_TYPE_LABELS`. 11 tests.

**Phase 2 — Revenue summary integration — implemented 2026-08-09.**
`RevenueSummaryDetail.event_income_cents`/`event_count` (backend: `build_revenue_summary` in `revenue_occurrences.py`, summing confirmed `InstructorEvent.income_cents` in the queried period — surfaced alongside, not merged into, `total_cents`). Frontend: new "Renda de eventos" stat tile in `revenue-section.tsx`. 1 new test (plus verifies a cancelled event's income is excluded).

**Phase 3 — Agent tools — implemented 2026-08-09.**
`list_events` (read, `agent/tools.py`) and `propose_create_event` (write + `_execute_create_event` executor, `agent/mutations.py`) — same propose→confirm→execute flow as every other mutation, so both web chat and WhatsApp get it for free. Orchestrator system prompt (`orchestrator.py`) teaches `event_type` inference from Portuguese wording (clínica→clinic, arbitrar/arbitragem→tournament_referee, workshop/oficina→workshop) and to never invent `income_cents`/`place_id` the instructor didn't state. New `OperationalEvent` type `instructor_event.created` (migration `a9d2e5f8c1b3`). 4 new tests, including a full propose→confirm cycle.

**All phases implemented.** 16 tests in `test_instructor_events.py`; full backend suite 158 passed; frontend typechecks and lints clean.

Not built, deliberately out of scope for this pass: editing/cancelling an event from the Agenda UI (API supports cancel; no frontend wired to it yet), recurring events, and passive-observer extraction (per the original decision above).
