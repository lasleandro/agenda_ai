# Aulas de Reposição (Make-up Class Credits) Roadmap v0.1 — 2026-08-07

**Status: All phases (1-5) and Addendum implemented. 2026-08-07.**

**2026-08-07 update:** eligibility policy decided (see "Open product
questions") — every cancellation grants a credit automatically *except*
one made inside a configurable notice window before the class (default
example given: 24h), which the instructor sets in the Financeiro area.
This removed the need to capture *who* cancelled or *why* — eligibility
is now a pure time comparison the system already has both sides of.
Phase 1 below was rewritten accordingly.

## What this is

A student who cancels a recurring class shouldn't just lose that slot —
in most tennis-academy commercial models, a cancelled *recurring* class
earns the student a "reposição" (make-up) credit: one class they're owed,
to be rescheduled into any open slot later. This roadmap covers detecting
that a credit was earned, tracking it, showing it to the instructor, and
suggesting where to slot the make-up class.

Requested capabilities (from the 2026-08-07 conversation):

1. Detect when a class is cancelled.
2. Determine whether the affected customer is a *recurring* customer
   (only recurring students earn reposição credits — drop-in/one-off
   bookings don't).
3. Tally the credit onto that customer's reposição balance.
4. Surface the balance on the Clientes page, per customer row.
5. A simple recommender that ranks candidate make-up slots, favoring
   low-occupancy ("low flow") and low-cost slots.

## What already exists to build on

This module doesn't start from zero — three pieces of infrastructure
built in the operational-ontology and financial-module roadmaps cover
most of the hard part:

- **Cancellation is already a first-class, audited event.**
  `propose_cancel_schedule` → `schedule_overrides.cancel_occurrence`
  writes a `ScheduleOccurrenceOverride(override_type="cancelled")` row
  and `_execute_cancel_schedule` records an `OperationalEvent` with
  `event_type="schedule.occurrence.cancelled"` (`app/agent/mutations.py`,
  `app/services/schedule_overrides.py`). Detection (requirement #1) is a
  **listener on an event that already fires reliably**, not new
  instrumentation.
- **"Recurring customer" already has a deterministic definition.**
  A contact is a recurring customer if they have an active
  `RecurringSlotParticipant` row on a `RecurringSlot` with
  `slot_kind="class"` (`app/agent/entity_resolution.resolve_groups`
  already does this lookup pattern). Requirement #2 is a membership
  check, not new modeling.
- **The financial/capacity module already computes what a recommender
  needs.** `app/services/financial_capacity.build_capacity_segments`
  already classifies every open time segment as `"prime"` or `"regular"`
  (`PrimeTimeWindow`) and prices it (`FinancialRate`/
  `PlaceFinancialRate`/`Contact.hourly_rate_cents`), and
  `find_instructor_openings` (`app/agent/tools.py`) already turns that
  into a list of free slots for a given date/duration/place. The "low
  cost" half of requirement #5 is close to a direct reuse of this.
- **The state-machine and audit patterns to copy are already proven.**
  `OperatorActionCandidate`'s propose → confirm → executed lifecycle
  (`app/agent/candidates.py`) and `OperationalEvent`'s append-only ledger
  are the established idioms in this codebase for "something that
  changes state and must be auditable." A credits ledger should follow
  the same shape, not invent a new one.

## What's genuinely missing

- **No configurable notice-window threshold exists yet.**
  Eligibility is decided (see below) to be a pure time comparison —
  minutes/hours between when the cancellation happened
  (`OperationalEvent.occurred_at` on the `schedule.occurrence.cancelled`
  event, already recorded) and the cancelled occurrence's original
  `starts_at` (already known via `schedule_overrides.get_target_occurrence`)
  — against a per-tenant threshold that doesn't exist anywhere in the
  data model yet. Both sides of the comparison already exist; only the
  threshold setting is new.
- **No "flow"/occupancy signal exists anywhere in the codebase.**
  "Low-flow slot" isn't a concept the data model has today — there's
  booked-vs-open capacity (which the financial module already computes),
  but no notion of *how consistently* a given weekday/hour tends to fill
  up over time. This needs a lightweight heuristic (below), not a new
  analytics subsystem.
- **No credits ledger table, no Clientes-page surface, no recommender
  endpoint.** All new, scoped below.

## Open product questions

Q1 and Q2 were resolved in the 2026-08-07 conversation; Q3–Q5 remain
open and would change the data model, so worth deciding before Phase 2:

1. ~~Automatic or reviewed?~~ **Resolved: automatic.** Every cancellation
   grants a credit unless it falls inside the notice window (Q2) — no
   instructor confirmation step. Simpler than the `propose_*` confirm
   pattern used elsewhere in this app, and deliberately so: this is a
   passive bookkeeping entry, not a schedule mutation with real-world
   side effects, so it doesn't need the same confirm-before-it-happens
   safeguard.
2. ~~Does a late cancellation still count?~~ **Resolved: no, based purely
   on notice given, not on who cancelled or why.** A single configurable
   threshold, per tenant, set by the instructor in the Financeiro area
   (default example given: 24h). Concretely: add
   `cancellation_notice_hours: int` (default `24`) to
   `ProfessionalFinancialSettings` — the existing "tenant defaults for
   the commercial/financial module" table (`app/models/
   professional_financial_settings.py`), the natural home for this,
   next to `default_commercial_status`/`currency`. No new table needed
   for the setting itself.
3. **Do credits expire?** Unlimited accrual invites abuse/hoarding; most
   real policies expire a credit after N days or N classes.
4. **Does redeeming a credit cost the instructor a "free" slot, or is it
   billed like a normal class?** This is a financial-module question
   (`commercial_financial_module_roadmap_v0.2_2026-08-05.md`), not
   something to improvise here — flagging the dependency rather than
   deciding it in this document.
5. **Group class only, or also one-off recurring appointments?**
   Requirement #2 specifically says "recurring customer," which this
   roadmap reads as: only cancellations of a `RecurringSlot` class
   membership earn a credit, not one-off `Appointment` cancellations
   (matches the "customer ontology" distinction already established
   between the two entities). Worth confirming.

## Phased plan

### Phase 1 — Configurable notice-window setting

- Add `cancellation_notice_hours: int` (`nullable=False, default=24`) to
  `ProfessionalFinancialSettings`, with a small migration (follow the
  established constraint-name-length-check habit from prior migrations
  in this codebase). A `CheckConstraint` bounding it to a sane range
  (e.g. `0`–`168`) avoids a nonsense value like a negative or
  multi-week threshold.
- Financeiro settings UI: one numeric input next to the existing
  Jornada/rates sections (`frontend/src/components/financial/`), same
  save-on-blur pattern already used by `WorkJourneySection` and the
  assistant-settings admin row built earlier this session.
- Service helper `has_sufficient_cancellation_notice(occurrence_starts_at,
  cancelled_at, notice_hours) -> bool` — a pure function, trivially unit
  testable, no DB access. Lives in the new `app/services/makeup_credits.py`
  from Phase 2 (or a shared `_notice.py` if it ends up needed elsewhere).
- No changes to `propose_cancel_schedule`'s tool schema or the
  orchestrator's prompt — the agent doesn't need to ask anything new;
  eligibility is computed entirely from data already captured
  (occurrence's original `starts_at` + the cancellation event's
  `occurred_at`).

### Phase 2 — Reposição credit ledger

- New model, e.g. `MakeupClassCredit`: `id`, `professional_id`,
  `contact_id`, `origin_event_id` (FK `operational_events.id`, since that
  row already has the correlation/causation chain and
  `before_state`/`after_state`), `origin_recurring_slot_id`,
  `origin_occurrence_date`, `status`
  (`available` | `redeemed` | `expired` | `forfeited`), `granted_at`,
  `expires_at` (nullable, per Q3 above), `redeemed_at` (nullable),
  `redeemed_appointment_id` (nullable FK), `created_at`/`updated_at`.
  Mirrors `OperatorActionCandidate`'s status-column + audit-trail shape.
- Service `app/services/makeup_credits.py`:
  `grant_credit_if_eligible(db, professional_id, contact_id, override,
  cancelled_at)` — called right after a confirmed cancel executes (either
  inline in `_execute_cancel_schedule`, or as a small listener keyed off
  the `schedule.occurrence.cancelled` event so the eligibility logic
  stays out of the mutation executor). Checks, in order: is the contact a
  recurring member of the cancelled slot (per the existing
  `RecurringSlotParticipant` lookup); does
  `has_sufficient_cancellation_notice` (Phase 1) pass using the tenant's
  `cancellation_notice_hours`; no double-granting for the same
  `(professional_id, origin_event_id)` pair. All three are cheap,
  synchronous checks — no new async/background step needed.
- One new `OperationalEvent` type: `makeup_credit.granted` (and
  `makeup_credit.redeemed`/`makeup_credit.expired` for the later phases)
  extending the existing closed vocabulary in
  `app/models/operational_event.py`.
- Read endpoint: `GET /api/clientes/{id}` (or extend the existing contact
  detail response) with `makeup_credits_available: int` and enough detail
  for a tooltip (origin date, granted date).

### Phase 3 — Clientes page surface

- Small badge on the customer row (`app/(protected)/clientes/page.tsx`)
  showing the available-credit count when > 0 — same visual weight as
  the existing level/place chips, not a new dense column. A "1"
  shouldn't look like a warning; treat it as informational (blue/neutral,
  not red/amber, to avoid implying something's wrong).
- `ContactSummary`/`ContactDetailData` (`frontend/src/lib/types.ts`) gain
  `makeup_credits_available: number`.

### Phase 4 — Recommender (heuristic, not ML)

Deliberately simple, per the ask — a weighted ranking over candidate
slots, not a learned model:

- **Candidate generation**: reuse `find_instructor_openings`
  (`app/agent/tools.py`) for a lookback/lookahead window (e.g. the next
  14 days), constrained to slots long enough for the customer's usual
  class duration and (if relevant) their usual place/level.
- **Cost score**: already available — `financial_capacity`'s
  `prime`/`regular` categorization plus the resolved hourly rate per
  candidate slot. Rank ascending by rate; prime-time slots sort lower
  by definition.
- **Flow score (new, small)**: since no occupancy-history table exists,
  compute it on the fly rather than building a new analytics pipeline —
  for each candidate weekday+hour bucket, look at the trailing N weeks
  (e.g. 4) via `scheduling.list_schedule_occurrences` and compute
  booked-count ÷ total-capacity-minutes for that bucket. Lower ratio
  ranks better ("low flow" = historically quiet). This is a query over
  existing data, not a new table — revisit with a materialized/cached
  version only if it's ever slow enough to matter.
- **Combine**: `score = w_cost * cost_percentile + w_flow * flow_percentile`,
  both weights configurable (sensible default: equal weight), return the
  top N ranked candidates.
- Surface this as a new read-only agent tool
  (`recommend_makeup_slots(contact_id)`) so the instructor can ask the
  assistant directly ("onde encaixo a reposição da Mariana?"), consistent
  with every other read tool in `app/agent/tools.py`.

### Phase 5 (later, optional) — Book the make-up class from chat

- `propose_redeem_makeup_credit(credit_id, place_id, start_at, end_at)` —
  a new `propose_*` mutation tool that both creates the appointment (via
  the existing `appointments.create_appointment` service, already shared
  with the dashboard) *and* marks the credit `redeemed` in the same
  confirm transaction, same pattern as every other mutation tool in
  `app/agent/mutations.py`. Natural finishing move once Phases 1–4 are
  live and validated with real usage.

## Complementary ideas (not required, worth having on record)

- **Tell the instructor why no credit was granted.** When a cancellation
  misses the notice window, have the agent's confirmation reply say so
  explicitly ("cancelamento a menos de 24h do horário — sem crédito de
  reposição gerado") rather than silently granting nothing — same
  transparency principle as `assert_within_work_journey`'s clear-reason
  rejections added for work-journey validation earlier this session.
- **Optionally capture `reason_code`/`note` anyway** (the columns already
  exist on `ScheduleOccurrenceOverride`) purely for the instructor's own
  record-keeping/reporting — no longer needed for the eligibility
  decision itself (Q1/Q2 resolved to pure notice-window timing), but
  still could be useful context on the credits view (complementary idea
  below) if the instructor wants to see *why* a student cancelled, not
  just whether they got a credit.
- **A dedicated "Créditos de Reposição" view**, not just the Clientes-row
  badge — a small table listing every outstanding credit across all
  customers, useful for an instructor doing weekly planning. Complements
  #4 rather than replacing it.
- **Expiry reminders**: if credits expire (Q3), a background check
  (mirroring `app/chat/pipeline.py`'s existing debounce/scheduled-worker
  pattern) that surfaces "these N credits expire this week" — either in
  the dashboard or, once the WhatsApp assistant channel exists, proactively
  to the instructor.
- **Cap per customer**: a simple `MAX_OUTSTANDING_CREDITS` guard in
  `grant_credit_if_eligible` prevents unbounded accrual from a student who
  cancels constantly — cheap insurance, worth including from Phase 2.
- **WhatsApp portability**: this entire module is channel-agnostic by
  construction if it's built as agent tools + services (same reasoning as
  the WhatsApp-portability discussion earlier this session) — nothing
  here should need rework when the instructor's WhatsApp assistant number
  exists.

## Suggested sequencing

Phase 1 → Phase 2 → Phase 3 ship together well as one pass (they're small
and Phase 3 is trivial once Phase 2's endpoint exists) — the eligibility
policy itself (Q1/Q2) is now settled, so this pass isn't blocked on a
product decision anymore. Phase 4 is a separate, slightly heavier pass —
worth building only after Phases 1–3 are live and you've seen a few real
credits accrue, so expiry (Q3) and the flow-score weighting can be tuned
against real cancellation/booking patterns rather than guessed upfront.
Phase 5 is speculative until then.

---

## Addendum: Aula Cortesia (no-charge classes) — 2026-08-07

**Independent from the credit system above.** Raised in the same
conversation but explicitly a separate feature: a generic classification
for any class that shouldn't generate revenue — the canonical Brazilian
example being a free trial class ("aula teste") for a prospective
student, but the ask was deliberately generic ("slots that do not
generate money"), not scoped to trial classes only.

### What already exists to build on

The revenue-confirmation flow (`app/services/revenue_occurrences.py`,
Financeiro module) already has a **per-participant, per-occurrence**
`billable: bool` on `RevenueOccurrenceParticipant` — an instructor
confirming revenue for a past class can already mark a participant as
non-billable, producing `billed_amount_cents = 0` for them. So "a class
that generates no money" is partially representable today.

### The actual gap

That existing `billable` flag is:

- **Set after the fact**, during monthly/periodic revenue confirmation —
  not visible or decidable at booking time. An instructor booking an
  "aula teste" today has no way to mark it as such on the calendar; they'd
  have to remember, weeks later while reconciling revenue, which
  occurrence was the free one.
- **Unlabeled** — a bare boolean with no reason attached, so a courtesy
  class and a genuine billing dispute/write-off look identical in
  reporting. There's no way to answer "quantas aulas cortesia demos esse
  mês?" without manually re-deriving it.
- **Easy to confuse with "unset" pricing.** `_participant_rate` already
  returns `(None, "unset")` when no rate rule resolves — that's a
  *pricing configuration gap* the instructor should probably fix, not a
  deliberate freebie. Conflating the two in reporting would hide real
  pricing gaps behind intentional courtesy classes, or vice versa.

### Proposed shape

- **`billing_type: str`** (`"billable"` | `"courtesy"`, default
  `"billable"`, `CheckConstraint`) on `Appointment` — same pattern as
  `class_type` added earlier this session (`app/models/appointment.py`).
  Scoped to `Appointment` only for now: the driving use case (trial
  classes for a new contact) is inherently one-off; extending this to
  `RecurringSlot` occurrences can follow later if a real need shows up,
  same "don't build for hypothetical requirements" call made elsewhere
  in this roadmap.
- **Booking-time capture, both surfaces**: a "Cortesia" checkbox in the
  dashboard's `AppointmentFormDialog`, and an optional `is_courtesy: bool`
  param on the agent's `propose_create_appointment` tool — system prompt
  taught to recognize "aula teste," "cortesia," "de graça," "sem cobrar"
  and set it without being asked explicitly.
- **Calendar/detail visibility**: a small badge, same visual treatment as
  the "Reagendado" badge added to `AppointmentPanel` for rescheduled
  occurrences — informational, not a warning color.
- **Revenue module integration (the important part)**: when
  `create_revenue_occurrence` processes an occurrence whose `Appointment.
  billing_type == "courtesy"`, default every participant's outcome to
  `billable=False` (the instructor can still override at confirmation
  time — courtesy status shouldn't be permanently locked in). Add a
  small `non_billable_reason: str | None` column to
  `RevenueOccurrenceParticipant` (e.g. `"courtesy"` | `"write_off"` |
  `null`) so financial reporting can distinguish "we chose not to charge"
  from "this pricing rule was never configured" — closing the exact
  ambiguity described above.
- **Clientes page (optional)**: surface "aula-teste utilizada em DD/MM"
  on the contact detail so the instructor doesn't accidentally offer a
  second free trial to the same prospect — nice-to-have, not required
  for the first pass.

### Sequencing note

This can ship independently of, and in either order relative to, the
make-up-credit work above — the only shared surface is `Appointment`
gaining another small classification column (`class_type` from the
participants work, `billing_type` here), which is additive and doesn't
conflict.

### Implementation Progress — 2026-08-07

- [x] Model: `billing_type` on `Appointment` (with `CheckConstraint`)
- [x] Model: `non_billable_reason` on `RevenueOccurrenceParticipant`
- [x] Migration: `7a48cebd571f_courtesy_billing_type` (applied)
- [x] Agent: `billing_type` param in `propose_create_appointment` TOOL_SPEC
- [x] Agent: `_execute_create_appointment` sets `appointment.billing_type`
- [x] Agent: `propose_create_appointment` accepts and forwards `billing_type`
- [x] API: `AppointmentCreate` schema + `billing_type`
- [x] API: `AppointmentSummary` + `AppointmentDetail` schemas + `billing_type`
- [x] API: `POST /api/appointments` passes `billing_type` to service
- [x] API: `GET /api/calendar` returns `billing_type` in summaries
- [x] API: `GET /api/appointments/{id}` returns `billing_type` in detail
- [x] Service: `create_appointment` accepts and stores `billing_type`
- [x] Service: `create_revenue_occurrence` auto-detects courtesy appointments and forces `billable=False`
- [x] Service: `ScheduleOccurrence` dataclass + `billing_type` propagation
- [x] Frontend: `AppointmentCreateInput` + `AppointmentSummary` types + `billing_type`
- [x] Frontend: `AppointmentFormDialog` "Cortesia" checkbox
- [x] Frontend: Calendar "(Cortesia)" badge in event titles
- [x] Frontend: Optimistic UI includes `billing_type`
- [x] Frontend: Contact detail page shows courtesy appointments list
