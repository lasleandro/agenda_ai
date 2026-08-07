# Operational Ontology & AI Agent Roadmap v0.2 — 2026-08-05

**Status: Phase 0 (semantic hardening) and Phase 1 (occurrence projection
and exceptions) implemented 2026-08-06. Phase 2 not started.**

## Phase 1 implementation notes (2026-08-06)

- Added `ScheduleOccurrenceOverride` — a dated cancel/reschedule exception
  keyed to one occurrence of an `Appointment` or `RecurringSlot`. One active
  override per parent occurrence is enforced by two partial unique indexes
  (Postgres can't express "unique among rows where column X is not null"
  with a plain constraint). Migration:
  `backend/migrations/versions/e2b7c5a1f048_schedule_occurrence_override.py`.
- Consolidated four independent reimplementations of "expand
  Appointment + RecurringSlot into calendar occurrences" (in the old
  `revenue_schedule.py`, `financial_capacity.py`, and two places in
  `calendar.py`) into one service: `revenue_schedule.py` was promoted and
  renamed to `app/services/scheduling.py`, gained the interval-math and
  availability-range primitives previously duplicated in
  `financial_capacity.py`, and now merges `ScheduleOccurrenceOverride` rows
  into `list_schedule_occurrences`'s output (cancelled → dropped,
  rescheduled → replacement time/place, `is_exception=True`).
  `financial_capacity.load_booking_occurrences` is now a thin filter over
  the shared list instead of its own expansion, so overrides are
  automatically respected in capacity/revenue calculations.
- **`GET /api/calendar` and its conflict checks were deliberately left
  unchanged** — checked the frontend before touching this and found
  `week-calendar.tsx` relies on FullCalendar's own client-side recurrence
  expansion (`daysOfWeek`/`startRecur`) plus a separate `RecurringSlot`
  fetch merged client-side; one raw row per `Appointment` is the *correct*
  contract for that rendering approach, not a gap. Rewiring the endpoint to
  return pre-expanded occurrences would have broken FullCalendar's
  recurrence rendering with no frontend change to match. Overrides exist in
  the data model and are respected by every other consumer of the
  projection, but aren't yet surfaced in the dashboard calendar UI —
  deferred to whichever later phase adds the mutation UX (and frontend
  support) to create them outside tests.
- Overrides are matched by their parent's *original* `occurrence_date`; a
  reschedule only surfaces at its new date when that new date falls inside
  the same query window as the original. Moving an occurrence to a date
  outside the queried window won't yet make it appear in a separate query
  for that window — documented as a known limitation in `scheduling.py`,
  deferred to the calendar-mutation phase.

## Phase 0 implementation notes (2026-08-06)

## Phase 0 implementation notes (2026-08-06)

- `RecurringSlot` gained `slot_kind` ("availability" | "class", CHECK
  constraint), `valid_from`/`valid_until`, and `group_name` (separate from
  the resource/court `label`). `class_type` ("individual" | "group") is
  unchanged and orthogonal.
- Backfill set `slot_kind="class"` for every slot with at least one
  `RecurringSlotParticipant` row (mirroring the prior implicit rule); all
  other slots default to `"availability"`. No ambiguous rows were found in
  local data (a `class_type="group"` slot with zero participants would have
  needed manual review, per the roadmap's gap #1).
- `recurring_slots.py`'s add-participant endpoint promotes a slot from
  `availability` to `class` on its first participant instead of branching
  overlap checks on participant count; removing participants does not
  demote it back.
- `financial_capacity.py` and `revenue_schedule.py` now filter recurring
  occurrences by `slot_kind == "class"` instead of inferring from
  participant count.
- Added `Place.normalized_name` (casefold + whitespace-collapsed via
  `app/services/text_normalization.normalize_name`) and a tenant-scoped,
  polymorphic `EntityAlias` table (`entity_type` + `entity_id`, no FK
  since it spans contacts/places/recurring slots) for future deterministic
  name resolution. No alias-management API was built yet — Phase 2 read
  tools will add it if/when needed.
- Migration: `backend/migrations/versions/d1a4c8e6b930_slot_kind_place_alias.py`.
- Group identity still follows "interpretation 1" (a group is one
  `RecurringSlot`'s participant set) — no `TrainingGroup` entity added.

This roadmap supersedes the future-planning portions of:

- [Customer Ontology & Places Roadmap v0.1](customer_ontology_places_roadmap_v0.1_2026-08-05.md)
- [AI Agent Operations Roadmap v0.1](ai_agent_operations_roadmap_v0.1_2026-08-05.md)

Those documents remain as implementation history and design provenance. This
document is the canonical plan for hardening the platform ontology and exposing
it safely to instructor-operated AI agents.

## Goal

Enable an instructor to query and operate the platform in natural Portuguese
through either an internal platform assistant or the private WhatsApp Assistant
Channel. The same domain services and typed tools must support both channels.

Initial target interactions include:

```text
quais alunos tenho marcado hoje
coloca o Marcelo no Grupo da Maria no clube harmonia
amanhã de tarde tenho vaga que horarios?
```

The objective is not an autonomous agent or a natural-language-to-SQL layer. It
is a small, tenant-scoped, auditable tool surface over an explicit operational
ontology.

## Success criteria

- Schedule reads combine direct appointments and recurring classes into dated
  occurrences, including occurrence-level exceptions.
- Availability queries return bookable intervals after applying working hours,
  place availability, breaks, classes, appointments, and exceptions.
- Names and shorthand resolve deterministically to tenant-owned entities; zero
  or multiple matches produce clarification instead of a guess.
- Read tools execute immediately; every write is previewed and explicitly
  confirmed before execution.
- Every executed write records actor, channel, cause, before/after state, and
  affected entities.
- Web and WhatsApp use the same application services, validation, authorization,
  and audit behavior.

## Current-state assessment

The platform already has most of the nouns needed for an agent-operable
schedule:

- `Professional` provides the tenant boundary, timezone, default service, and
  default lesson duration.
- `Contact` provides normalized customer identity, level, address, home place,
  and commercial configuration.
- `Place` provides the venue identity and structured location.
- `RecurringSlot` represents weekly or one-off time blocks at a place.
- `RecurringSlotParticipant` assigns customers to recurring classes.
- `Appointment` represents direct bookings and a limited weekly recurrence.
- `WorkJourneyInterval` describes weekly working and break intervals.
- `AppointmentCandidate`, messages, and evidence support the passive
  customer-conversation workflow.
- `AppointmentTransition` and the financial/feature audit tables provide
  specialized, but fragmented, history.

This is enough to build deterministic entity lookup and partial schedule reads.
It is not yet enough to answer all three target interactions reliably.

### Gaps that matter before agent writes

1. **`RecurringSlot` has two implicit meanings.** An empty slot is treated as
   place availability, while a participant-backed slot is treated as a class.
   Participant count should not determine entity meaning.
2. **Weekly rules lack an explicit validity interval.** There is no
   `valid_from`/`valid_until`, making "starting next month" and "stop after this
   week" difficult to represent.
3. **There are no occurrence-level exceptions.** A single recurring lesson
   cannot be cancelled or moved without changing or deleting the series.
4. **Calendar reads are fragmented.** The appointment API and recurring-slot API
   expose separate record types; the agent needs one dated occurrence
   projection.
5. **Place and group resolution are weak.** Contacts have normalized names, but
   places have neither a normalized name nor aliases. A group is currently
   identified indirectly through one schedule slot and its members.
6. **Operational history is fragmented.** There is no common causal chain from
   source message through proposed command, confirmation, mutation, and final
   calendar event.

## Ontology decisions

### Store operational meaning in explicit fields

Do not create a generic database catalog that describes the meaning of every
table and column. Those definitions belong in SQLAlchemy models, constraints,
Pydantic schemas, typed agent tools, and this roadmap. A runtime catalog would
be a second source of truth that could drift from executable behavior.

Add narrow metadata only where runtime resolution or tenant customization needs
it:

- add `Place.normalized_name`;
- add a tenant-scoped `EntityAlias` table for contact, place, and group aliases;
- keep configurable language concepts such as the instructor's definition of
  "tarde" in explicit professional preferences only if real usage requires
  customization.

Do not place core schedule semantics in `Contact.metadata` or unvalidated JSON.

### Make schedule-block meaning explicit

Add `RecurringSlot.slot_kind` with an initial closed vocabulary:

- `availability`: the instructor is available at a place during this interval;
- `class`: the interval is a scheduled individual or group class.

Availability rows cannot have participants. Class rows may overlap a containing
availability window but must continue to respect conflicts with other classes
and appointments. Existing rows can be backfilled deterministically from
participant count, followed by a review of empty slots that were intended as
unfilled classes.

Add `valid_from` and `valid_until` to weekly rows. A one-off row continues to use
`scheduled_date`. Keep recurrence calculation in one shared scheduling service
instead of duplicating it across APIs and analytics.

### Decide whether a group is independent from one time slot

There are two legitimate interpretations:

1. A group is exactly one scheduled slot. "Grupo da Maria" resolves to a slot
   containing Maria, optionally filtered by place/day.
2. A group is a stable roster that can meet in multiple weekly slots. In that
   case, introduce `TrainingGroup`, `TrainingGroupMember`, and scheduled
   `RecurringSlot.group_id`.

Use interpretation 1 for the first read-only release. Before group mutation
tools ship, validate whether real instructors expect one roster to span
multiple days. If they do, implement interpretation 2 before exposing
membership writes. Do not duplicate the same membership silently across slots.

Keep `group_name` separate from the current `label`, which represents a resource
or location detail such as "Quadra 2."

## Temporal model: current state, occurrences, and causes

Agents need two different answers:

- **What is true on the calendar?** Read from domain records projected into
  dated occurrences.
- **Why is it true?** Read from immutable operational events.

An event ledger must complement the operational tables, not replace them. This
roadmap does not adopt full event sourcing.

### `ScheduleOccurrenceOverride`

Add a table for exceptions to a recurring appointment or class. Initial fields:

- `id`, `professional_id`;
- one parent reference: `appointment_id` or `recurring_slot_id`;
- `occurrence_date`;
- `override_type`: `cancelled` or `rescheduled`;
- replacement `start_at`, `end_at`, and `place_id` when rescheduled;
- optional structured reason code and human note;
- actor/source fields;
- `created_at`, `updated_at`.

Enforce tenant ownership, one active override per parent occurrence, valid
replacement ranges, and a requirement that reschedule fields are present only
for `rescheduled`.

Attendance, no-show, substitute-instructor, and billing outcomes are deliberately
outside the first implementation. They can extend occurrence state after their
business policies are defined.

### Unified schedule projection

Build a scheduling-domain service that expands and merges:

- direct one-off and recurring `Appointment` records;
- `RecurringSlot` rows with `slot_kind=class`;
- participant rosters or stable groups;
- `ScheduleOccurrenceOverride` rows.

The output is a typed `ScheduleOccurrence` projection containing stable source
references, local start/end datetimes, place, participants, status, recurrence
scope, and whether an exception changed the occurrence.

The same service must power the calendar API, agent reads, conflict validation,
and financial occurrence calculations. A projection may be calculated on
demand initially; a materialized occurrence table is unnecessary until measured
query volume requires it.

### Availability calculation

Extract reusable interval logic from the financial capacity service into the
scheduling domain. For a requested date, duration, and optional place:

```text
work journey
intersection place availability
minus breaks
minus appointment occurrences
minus class occurrences
minus effective occurrence overrides
equals bookable openings
```

Use `Professional.default_duration_minutes` when the instructor does not provide
a duration. Return openings grouped by place when more than one place is
possible. Travel time between places is not inferred in the first release; if
adjacent cross-place commitments create a real problem, add an explicit
professional travel-buffer preference later.

The phrase "tenho vaga" can mean either instructor availability for a new
lesson or an open participant seat in an existing group. The tool schema must
represent these as separate query modes, and the agent must clarify when context
does not disambiguate them.

### `OperationalEvent`

Add one append-only, tenant-scoped event table for cross-domain operational
history:

- `id`, `professional_id`, and an immutable ingestion sequence;
- `event_type` from a versioned application vocabulary;
- `occurred_at`, `recorded_at`, and optional `effective_at`;
- actor type/ID and source channel;
- primary entity type/ID;
- `correlation_id` for the complete interaction;
- `causation_id` for the immediately preceding event or command;
- optional source message and operator-action references;
- structured payload and before/after values;
- idempotency key.

Initial event vocabulary:

- `agent.action.proposed`, `confirmed`, `rejected`, `expired`, `executed`,
  `failed`;
- `schedule.appointment.created`, `updated`, `cancelled`;
- `schedule.series.created`, `updated`, `deactivated`;
- `schedule.occurrence.cancelled`, `rescheduled`;
- `schedule.participant.added`, `removed`;
- `contact.updated`;
- `place.created`, `updated`, `deactivated`.

Event ordering represents ingestion order, while `occurred_at` represents
business time. Causal links must be preserved because WhatsApp events may arrive
late or out of order. Avoid treating timestamps alone as proof of causality.

Do not store raw secrets, full webhook payloads, or unnecessary personal data in
event payloads.

## Agent operating model

### One domain service layer, two channel adapters

The internal platform assistant and WhatsApp Assistant Channel must call the
same application services:

```text
web chat/session ───────┐
                       ├─ agent orchestrator ─ typed tools ─ domain services
WhatsApp assistant ─────┘
```

The web adapter derives tenant, user, and role from the authenticated session.
The WhatsApp adapter derives the professional from the configured assistant
number and verifies the provider webhook signature. Neither adapter accepts a
tenant ID chosen by the model or request body.

Do not implement tools as an LLM calling existing HTTP endpoints. Extract
domain services used by both HTTP APIs and tools so validation, transaction
boundaries, authorization, and audit behavior cannot diverge.

### Resolution before action

Natural-language names are search inputs, never mutation identifiers.

1. Normalize and search tenant-owned aliases and canonical names.
2. Apply explicit context filters such as place, date, member, or phone.
3. Return stable IDs and concise disambiguation details.
4. If zero or multiple valid matches remain, ask the instructor.
5. Pass only resolved IDs into mutation tools.

Fuzzy matching may rank candidates but must not silently select an ambiguous
write target.

### Read tools

- `search_contacts(query, phone?)`
- `search_places(query)`
- `find_groups(member_contact_id?, place_id?, date_or_weekday?)`
- `get_schedule(date_from, date_to, contact_id?, place_id?)`
- `get_next_session(contact_id?)`
- `find_instructor_openings(date, period?, duration_minutes?, place_id?)`
- `find_group_openings(date, period?, place_id?, level?)`
- `get_schedule_history(entity_type?, entity_id?, date_from?, date_to?)`

Read tools return domain data. The model may format it conversationally but
must not invent missing names, places, times, or availability.

### Mutation tools

- `propose_add_group_member(contact_id, group_or_slot_id, effective_from?)`
- `propose_remove_group_member(contact_id, group_or_slot_id, scope)`
- `propose_create_appointment(contact_id, place_id, start_at, end_at, service)`
- `propose_cancel_schedule(target_type, target_id, occurrence_date?, scope)`
- `propose_reschedule_occurrence(target_type, target_id, occurrence_date,
  start_at, end_at, place_id)`
- `propose_create_recurring_class(...)`
- `propose_create_availability_window(...)`
- `propose_update_contact(contact_id, changes)`

Keep proposal tools small and business-specific. Do not expose generic
`update_row`, arbitrary JSON patches, raw SQL, or unrestricted endpoint calls.

### Confirmation and execution

Every write starts as an `OperatorActionCandidate` containing:

- tenant, actor, and channel;
- tool name and schema version;
- resolved arguments;
- human-readable preview;
- expected affected entities;
- status: `proposed`, `confirmed`, `rejected`, `expired`, `executed`, or
  `failed`;
- expiration and idempotency key;
- correlation/causation references.

Confirmation identifies the candidate rather than asking the model to recreate
the arguments. The executor reloads current state and reruns authorization,
capacity, and conflict checks inside the mutation transaction. If state changed
since preview, execution fails safely and the instructor receives a new
explanation or proposal.

One confirmation may cover a clearly previewed atomic batch, such as creating
the same availability window on five weekdays. Partial execution is not allowed
unless the preview explicitly describes independent actions.

## Target interaction walkthroughs

### "quais alunos tenho marcado hoje"

1. Resolve `hoje` using the professional timezone.
2. Call `get_schedule(today, today)`.
3. Merge direct appointments and recurring class occurrences after overrides.
4. Return time, student or roster, place, and relevant class label.

This is read-only and needs no confirmation.

### "coloca o Marcelo no Grupo da Maria no clube harmonia"

1. Resolve Marcelo as a contact.
2. Resolve Clube Harmonia as a place using canonical name and aliases.
3. Resolve Maria, then find groups containing Maria at that place.
4. If multiple groups remain, ask for day/time; if none remain, explain that no
   matching group exists.
5. Check effective date, duplicate membership, capacity, and schedule policy.
6. Create a proposal naming Marcelo, the resolved group, schedule, and place.
7. On confirmation, execute atomically and record the operational events.

The agent must never create a new "Grupo da Maria" merely because resolution
failed.

### "amanhã de tarde tenho vaga que horarios?"

1. Resolve `amanhã` in the professional timezone.
2. Resolve `tarde` using a documented platform default; initially 12:00–18:00.
3. If context does not establish the meaning of `vaga`, ask whether the
   instructor means a free lesson time or a seat in an existing group.
4. For instructor time, call `find_instructor_openings` using the professional's
   default duration.
5. Return exact intervals grouped by place, mentioning the assumed duration.

If there is no registered place availability for that date, report that the
platform lacks enough availability data rather than interpreting an empty
calendar as available time.

## Security, authorization, and reliability

- Every tool derives `professional_id` from trusted channel context.
- Every tool declares the minimum accepted role; reads are not open by default.
- Web writes retain CSRF protection. WhatsApp requests retain signature
  validation, number-to-tenant resolution, replay protection, and rate limits.
- Tool inputs use strict Pydantic schemas and closed action vocabularies.
- Entity queries and writes are tenant-scoped at every repository boundary.
- Mutation execution uses database transactions and idempotency keys.
- State-changing actions log who, what, when, source channel, affected records,
  and before/after values.
- Client messages remain generic and safe; detailed failures are logged
  server-side without secrets or unnecessary personal data.
- Pending confirmations expire and cannot be applied after execution,
  rejection, or material state changes.
- Optimistic UI is appropriate for web-chat proposal and rejection state, but
  confirmed domain mutations reconcile against the server result and roll back
  visibly on failure.

## Delivery phases

Phases are ordered by dependency and mutation risk, not calendar dates.

### Phase 0 — Semantic hardening

- Add `slot_kind`, `valid_from`, and `valid_until`.
- Backfill existing recurring slots and review ambiguous empty rows.
- Add normalized place names and tenant-scoped aliases.
- Separate group name from court/resource label.
- Decide whether stable multi-slot `TrainingGroup` identity is required.
- Document invariants in models, schemas, and API contracts.

**Release gate:** existing calendar, group, capacity, and financial behavior
remains test-covered; every active schedule row has explicit meaning.

### Phase 1 — Occurrence projection and exceptions

- Add `ScheduleOccurrenceOverride`.
- Build the shared schedule projection service.
- Route calendar reads and conflict checks through it.
- Extract availability interval calculation from financial analytics into the
  scheduling domain, retaining financial consumers.
- Add behavior tests for recurrence boundaries, cancellation, rescheduling,
  timezone edges, and cross-tenant isolation.

**Release gate:** one API/service call produces the same correct schedule view
used by the calendar, availability engine, and future agents.

### Phase 2 — Read-only instructor agent

- Stand up the private assistant-number ingestion path separately from customer
  conversations.
- Implement deterministic temporal interpretation and entity resolution.
- Implement the read tools and Portuguese response formatting.
- Add an internal web-chat adapter only if it does not delay proving the shared
  tool layer.
- Measure ambiguity, no-match, and correction rates.

**Release gate:** the three target read paths return evidence-backed results and
never mutate data.

### Phase 3 — Action candidates and event ledger

- Add `OperatorActionCandidate` and its state machine.
- Add `OperationalEvent`.
- Implement preview, confirm, reject, expire, execute, and fail transitions.
- Carry correlation and causation through both channel adapters.
- Enforce idempotency and revalidation at execution time.

**Release gate:** a synthetic write can traverse the complete confirmation and
audit lifecycle without using a production mutation tool.

### Phase 4 — Low-risk writes

- Expose add/remove group participant and selected contact updates.
- Require resolved IDs, confirmation, capacity validation, role checks, and
  complete audit events.
- Support atomic batch confirmation only where the preview is unambiguous.

**Release gate:** duplicate, full-capacity, ambiguous, stale, cross-tenant, and
replayed actions all fail safely; confirmed happy paths are reversible through
normal domain actions.

### Phase 5 — Calendar mutations

- Create one-off and recurring classes or availability.
- Create direct appointments.
- Cancel or reschedule one occurrence, future occurrences, or a complete series.
- Add scope-specific previews that state exactly what will change.

**Release gate:** all mutation scopes preserve correct calendar projections,
conflict validation, and causal audit history.

### Phase 6 — Multi-turn and multi-channel continuity

- Track pending clarification and confirmation per professional/channel.
- Support corrections before confirmation without mutating the original
  candidate.
- Define whether a web-started action can be confirmed in WhatsApp and vice
  versa; default to same-channel confirmation until identity assurance is
  proven.
- Expire abandoned state and provide a deterministic restart path.

**Release gate:** corrections, concurrent commands, delayed replies, and expired
confirmations cannot apply the wrong action.

## Verification strategy

- Unit-test recurrence expansion, interval subtraction, alias normalization,
  ambiguity handling, and action-state transitions.
- Integration-test every tool through domain services, not model internals.
- Test tenant isolation and role enforcement for every tool.
- Test happy path first, then ambiguous identity, conflicting state,
  confirmation expiry, replay, and failure rollback.
- Maintain a labeled Portuguese command set containing temporal shorthand,
  misspelled names, aliases, multiple same-name contacts, and multi-part
  commands.
- Replay the same labeled set through web and WhatsApp adapters and require
  equivalent tool selection and arguments.
- Log instructor corrections as evaluation labels without storing more message
  content than the product requires.

## Deliberate exclusions

- Natural-language-to-SQL or arbitrary API execution.
- Customer-facing negotiation or autonomous outreach.
- A graph database, vector database, RAG layer, or multi-agent framework.
- Full event sourcing or rebuilding all domain state from events.
- Automatic destructive writes based only on model confidence.
- Attendance, no-show, billing recognition, or substitute-instructor policy
  before those business rules are separately approved.

## Product decisions to validate before their dependent phase

1. Whether a group is one slot or a stable roster with multiple meeting times.
2. Whether `tarde` should remain a platform default or become a professional
   preference.
3. Whether write confirmation is always required or can later be relaxed for a
   measured subset of reversible actions. The initial answer is always required.
4. Whether group membership changes take effect immediately, on a specified
   date, or support both.
5. Whether availability must account for configurable travel time between
   places.
6. Whether cross-channel confirmation is permitted after identity and replay
   controls are proven.
