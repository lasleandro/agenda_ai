# Business Rules

This document catalogs the key business rules encoded in the platform.
Rules are enforced at three levels: database constraints, service-layer
validation, and agent prompt instructions.

---

## 1. Scheduling Rules

### 1.1 Conflict Prevention

- An appointment cannot overlap with another appointment for the same
  instructor at the same time.
- An appointment cannot overlap with a recurring slot at the same place
  if it would exceed capacity.
- When rescheduling, the target time slot is validated for availability.
- Validation happens at propose time (fast-fail check) and again at
  execute time (re-validated inside the transaction, since state may have
  changed).

### 1.2 Work Journey Guidance

- Work intervals and pauses (`WorkJourneyInterval` rows) describe the
  instructor's usual working preference. Each day has zero or more work
  intervals and optionally break intervals.
- A conflict-free appointment may be created outside a configured work interval
  or during a configured pause. The active assistant shows a non-blocking
  advisory before confirmation; real appointment, class, and event conflicts
  remain hard failures.
- Open-ended availability recommendations use the configured journey. If no
  journey exists for a weekday, the assistant explains that it has no preferred
  openings to recommend and directs the instructor to Configurações.

### 1.3 Recurrence Expansion

- Recurring appointments (with RRULE) are expanded into per-date
  occurrences by the scheduling engine.
- `ScheduleOccurrenceOverride` cancels or reschedules a single occurrence
  without changing the template.
- A single occurrence can have at most one active override
  (409 Conflict if attempting double-cancel).

### 1.4 Class Types

- `individual`: One-on-one class. No additional participants.
- `group`: A real class commitment with one to four seats, including when its
  effective roster is empty or has one customer.
- Format and occupancy are independent: a group remains a group until an
  explicit format change. An individual can be explicitly opened as a group
  without replacing its booking or its existing customer.
- Recurring groups may have standing members and one-date guests. A dated
  guest belongs only to that occurrence and never earns recurring-member
  benefits such as make-up credits.
- A group seat is not free instructor time. It may be offered as joinable
  capacity, while its class still blocks availability searches.

### 1.5 Billing Types

- `billable`: Standard appointment.
- `courtesy` (Aula Cortesia): Free/trial class. When confirming revenue
  for a courtesy appointment, the dashboard *defaults* every participant
  to `billable=False` with `non_billable_reason="courtesy"` — the
  instructor can still override per participant at confirmation time
  (the backend never forces it; it only backfills the reason when the
  instructor leaves it non-billable).

---

## 2. Makeup Credit Rules

### 2.1 Earning Credits

A credit is earned by a **recurring group student** (a `RecurringSlot`
participant — never a one-off appointment student) with **sufficient
notice**, via either of two distinct actions:

- `propose_cancel_schedule` on a `recurring_slot` occurrence — cancels
  the class for *every* enrolled participant and grants each of them a
  credit (if eligible). Correct when the class itself doesn't happen.
- `propose_note_participant_absence` — records that *one* participant
  will miss a dated occurrence without cancelling it for the group; only
  that participant is considered for a credit.

- Notice window: configurable via `ProfessionalFinancialSettings.cancellation_notice_hours` (default 24h, 0–168 range), in the Financeiro settings UI.
- Formula: `occurrence_start - cancel_time > notice_hours * 3600` seconds.

### 2.2 Credit Limits

- Maximum outstanding credits per contact: **10** (`MAX_OUTSTANDING_CREDITS`).
- One credit per origin event (duplicate guard: cannot earn two credits
  for the same cancelled class/absence).
- If a student is already at the limit, no credit is granted for the new
  event — nothing is written, and the `forfeited` status (present in the
  schema) is never actually set by anything in the codebase today.

### 2.3 Credit Lifecycle

| State | Description | Currently set by the code? |
|---|---|---|
| `available` | Ready to redeem | Yes — on grant |
| `redeemed` | Used for a make-up class | Yes — on redemption |
| `expired` | Past the `expires_at` date | **No** — `expires_at` is never populated (always NULL); nothing expires credits yet |
| `forfeited` | Would exceed the max-outstanding limit | **No** — see §2.2; going over the limit just means no credit is granted, not a forfeited row |

- To discover a real `credit_id` for redemption, call the
  `list_makeup_credits` agent tool first — no tool or endpoint exposes an
  individual credit's ID any other way. Credits are then redeemed via
  `propose_redeem_makeup_credit(credit_id, place_id, start_at, end_at)`,
  which books the appointment and marks the credit `redeemed` in the same
  transaction.

---

## 3. Revenue Rules

### 3.1 Immutable Snapshots

- Revenue occurrences are immutable once confirmed (frozen).
- `POST /api/financial/revenue/occurrences` (`occurrence_date` is a field
  in the JSON body, not part of the path) confirms one occurrence at a
  time: rejects if that `(source_type, source_id, occurrence_date)` was
  already confirmed, rejects if the occurrence hasn't ended yet, resolves
  pricing per participant, and inserts the frozen
  `RevenueOccurrence`/`RevenueOccurrenceParticipant`/`RevenueOccurrenceLine`
  rows.

### 3.2 Pricing

- **Unified rate matrix** (`PlaceFinancialRate`): keyed by
  `(professional_id, place_id, time_category, participant_count)`, with
  `place_id IS NULL` rows holding the tenant-wide default (1-4 participants,
  regular/prime). Place-specific rows (`place_id` set) override the default
  for the same (place, time_category, count).
- **Prime time** is determined by `PrimeTimeWindow` rows (day-of-week +
  time range).

### 3.3 Billable Classification

- Each `RevenueOccurrenceParticipant` carries `billable: bool`.
- Courtesy appointments force all participants to `billable=False` with
  `non_billable_reason="courtesy"`.
- Attendance status is tracked per-participant but does not affect billing
  classification (billability is determined at booking time).

### 3.4 Revenue Lines

- Each participant generates one or more `RevenueOccurrenceLine` rows
  splitting the class duration by time category (regular/prime).
- Prime overrides are tracked per line for audit.

### 3.5 Financial Capacity vs. Work Journey

The Financeiro dashboard (`GET /api/financial/dashboard`) reports capacity
at two different granularities, deliberately built from two different
sources:

- **Top-line figures** (`available_minutes`, `booked_minutes`,
  `unused_minutes`, `occupancy_pct`) are computed from the instructor's
  raw **Work Journey** (`WorkJourneyInterval`, work minus break intervals —
  see 1.2 above) — professional-wide, with no place attribution.
  `booked_minutes` here is the raw sum of every booked occurrence's
  duration, uncapped to any place-specific window.
- **Breakdowns** (`by_place`, `by_weekday`, `by_part_of_day`,
  `by_time_category`, and the daily `time_series`) require an explicit
  `RecurringSlot` covering that place/weekday, because `WorkJourneyInterval`
  has no `place_id` — a place with zero `RecurringSlot` rows on a given
  weekday contributes zero capacity to *those breakdowns* for that
  weekday, no matter how broad the Work Journey is. Same caveat applies to
  the make-up slot recommender (`docs/capacity_and_recommendations.md`).

**Why not require RecurringSlot for the top line too:** an instructor who
hasn't (or hasn't fully) declared per-place availability windows would
otherwise see a near-zero denominator and a misleading ~100% occupancy on
real bookings that simply fall outside those narrow windows — this was
observed on a live tenant (Joao) whose top-line occupancy showed 100% from
3h of RecurringSlot-covered capacity while 90% of his actual bookings
weren't being counted at all. The by-place breakdown still needs
RecurringSlot for place attribution and is correctly sparse until the
instructor configures it — the fix only changes what the *aggregate*
number is measured against.

Every booked occurrence must have a `place_id` to be counted at all
(`load_booking_occurrences` in `app/services/financial_capacity.py`) — the
dashboard/agent appointment creation paths always require a place, so this
should never happen in real usage, but if it ever does the occurrence is
silently excluded from both capacity and revenue.

**Simulator estimate before configuration:** the standard Financeiro dashboard
remains configured-only. The Financial Simulator may request
`capacity_mode=estimated_when_unconfigured`; only when the tenant has zero
journey rows, it uses generic capacity of 8 regular-price hours per day from
Monday through Saturday (48 hours per full week), with Sunday excluded. It is
not assigned to a place or a clock time, so the simulated agenda stays empty
until the instructor configures Jornada de trabalho. Any configured interval,
including a partial week, is authoritative and is never supplemented with
default days.

**Place filter narrows both sides together:** when `GET
/api/financial/dashboard` is called with `place_id` (viewing one or more
specific places instead of "all places"), the top-line figures fall back
to the same `RecurringSlot`-scoped accounting as the breakdowns, instead
of the place-agnostic Work Journey total — otherwise a place-filtered
`booked_minutes` would be compared against a tenant-wide
`available_minutes`, understating occupancy. Only the unfiltered "all
places" view uses the place-agnostic top line.

**"Potencial com 100% da capacidade" and the Simulador scenario**
(`_capacity_presets`, `evaluate_financial_scenario`'s `scenario` metric)
also fold in the Work Journey time that falls outside any place's
`RecurringSlot` coverage (`build_uncovered_capacity_minutes`), priced
against the **default (`place_id IS NULL`) regular/prime matrix**. No
named-place override applies because the time has no attributed place; an
unpriced entry still contributes 0 revenue rather than raising an error. This
only applies to the unfiltered "all places" view,
for the same reason the top-line figures don't place-filter it: time not
covered by the filtered place(s) may be covered by a place the user
filtered out, so crediting it to the filtered place(s) would overstate
their potential. `_tradeoffs` (the group-vs-individual break-even
comparison) is intentionally **not** extended this way — it answers "of
my *configured* places/rates, what's the average rate," a narrower
question where diluting it with the global-rate-only uncovered time would
be misleading.

---

## 4. Multi-Tenancy Rules

### 4.1 Tenant Isolation

- Every data query is scoped to the authenticated tenant via `professional_id`.
- `professional_id` is always derived from the JWT session -- never from
  request body or URL parameter.
- Platform admins (`role=platform_admin`) have cross-tenant access but
  every impersonation is logged.

### 4.2 Feature Gating

- The `commercial_financials` feature flag controls visibility of:
  - Financeiro module (financial configuration, revenue tracking)
  - Financial rates in the calendar context
- Feature toggles are managed by the platform admin panel and audited.

### 4.3 Tenant Lifecycle

`Professional.status` has exactly three values, enforced by the
`ck_professionals_status` check constraint:

| Status | Meaning | Effect |
|---|---|---|
| `active` | Normal operation | — |
| `suspended` | Reversible full lockout | Tenant users cannot log in; inbound WhatsApp / agent messages are dropped at number resolution; daily-agenda tasks are skipped; platform-admin impersonation requires an explicit confirm |
| `archived` | Reversible soft delete | Same lockout as `suspended`, plus the tile is hidden from the default admin grid (`GET /api/admin/tenants?include_archived=true` to see it) |

- Transitions are platform-admin only, via `POST /api/admin/tenants/{id}/{suspend,reactivate,archive,restore}`.
- Any transition out of `active` bumps `auth_version` for every user of that
  tenant, invalidating live sessions.
- Every transition writes `status_changed_at/_by/_reason` on the row and one
  `tenant.{suspended,reactivated,archived,restored}` row in the operational
  event ledger. Impersonating an inactive tenant logs
  `tenant.impersonated_while_inactive`.
- Nothing is ever physically deleted; a hard purge is not implemented.

---

## 5. Authentication & Authorization Rules

### 5.1 Session Management

- JWT stored in `httpOnly`, `Secure`, `SameSite=Strict` cookie.
- Passwords hashed with `bcrypt`.
- `POST /api/auth/impersonate`: Platform admin can swap into a tenant
  session. Each impersonation is logged in `impersonation_logs`.

### 5.2 Role-Based Access

| Role | Access |
|---|---|
| `platform_admin` | Admin panel (`/api/admin/*`), impersonation, tenant management (feature gating, assistant tuning, scheduled tasks, lifecycle — see 4.3) |
| `professional` | Own tenant data only, all regular endpoints; blocked entirely while the tenant is `suspended` / `archived` |

---

## 6. Agent Guardrails (Prompt-Enforced)

These rules are enforced through the system prompt in `orchestrator.py`:

- **Never invent data:** The agent must not fabricate names, times, or
  availability not returned by a tool.
- **Always resolve dates:** For any relative date expression, call
  `resolve_date_phrase` -- never calculate dates independently.
- **Use is_past for filtering:** The `get_schedule` tool returns `is_past`
  booleans. The agent uses these rather than calculating elapsed time.
- **Clarify ambiguity:** When searching for a contact/place/group returns
  zero or multiple results, ask the instructor for clarification.
- **Write tools require confirmation:** The agent never executes mutations.
  It only proposes. The instructor must explicitly confirm.
- **Always mention the place:** When presenting schedule results, include
  the place (quadra) name.

---

## 7. Data Integrity Rules

### 7.1 Unique Constraints

- `(appointment_id, contact_id)` on `appointment_participants` -- a contact
  can't be added twice to the same appointment.
- `(recurring_slot_id, contact_id)` on `recurring_slot_participants` -- a
  contact can't be enrolled twice in the same group.
- `provider_message_id` on `messages` -- WhatsApp deduplication guard.
- `(appointment_candidate_id, message_id)` on `appointment_evidence` --
  each message links to a candidate at most once per role.
- `conversation_id` on `pending_processing` -- one debounce timer per
  conversation.
- `billing_type` on `appointments` has a CHECK constraint: must be
  `billable` or `courtesy`.

### 7.2 Polymorphic Entity IDs

- `EntityAlias.entity_id` and `RevenueOccurrence.source_id` do not have
  foreign key constraints (polymorphic relationships).
- `ScheduleOccurrenceOverride` uses `appointment_id` (nullable) and
  `recurring_slot_id` (nullable) with an application-level constraint:
  exactly one must be non-null.

### 7.3 Audit Trail

- All state-changing operations record an `OperationalEvent` with
  `before_state` and `after_state` JSONB snapshots.
- Financial configuration changes are tracked in `FinancialChangeAuditLog`.
- Feature flag changes are tracked in `TenantFeatureAuditLog`.
- Impersonation sessions are tracked in `ImpersonationLog`.

---

## 8. WhatsApp Pipeline Rules

- **Debounce:** Messages are processed in windows after a 30-second
  quiet period (configurable via `PIPELINE_DEBOUNCE_SECONDS`).
- **Dedup:** Messages are deduplicated by `provider_message_id` (UNIQUE).
- **Fingerprint:** Candidates are deduplicated by `event_fingerprint`
  (SHA-256 of normalized date + contact + action).
- **Window size:** Last 20 messages are used for extraction context.
- **Processing status:** Each message tracks `processing_status`
  (pending/processed/failed).

### 8.1 Instructor Agent WhatsApp Channel

Distinct from the passive-observer pipeline above — this is the *active*
agent (Mode 1) reachable over WhatsApp on a separate number
(`Professional.agent_phone`), not the customer-facing one
(`Professional.assistant_phone`).

- **Sender authorization:** Only messages whose sender matches
  `Professional.assistant_phone` (the instructor's own known number) are
  processed; anyone else messaging the agent number is silently dropped —
  no reply, so an unauthorized sender can't even confirm the number is
  live. Fails closed if `assistant_phone` isn't configured.
- **Deterministic fast path:** `hoje`/`amanha`/`esta semana`/`proxima
  aula` are answered directly against `Appointment`, no LLM call.
- **Confirmation by reply keyword:** No buttons over WhatsApp — `sim` /
  `confirmar` / `confirmo` / `confirma` / `ok` confirms, `nao` / `cancelar`
  / `cancela` / `cancelo` rejects.
- **Multi-proposal turns confirm together:** If one instructor message
  produces more than one pending proposal (e.g. "cancela as duas aulas de
  hoje" → two `propose_cancel_schedule` calls), a single `sim` confirms
  *all* of them — resolved via the shared `correlation_id` every proposal
  from one `run_agent_turn()` call carries, not just "the most recently
  created candidate." (Getting this wrong was a real bug: only the last
  proposal executed and the rest silently expired unconfirmed.)
- **Conversation history is windowed, not unbounded:** `AgentChannelMessage`
  rows replay through `AssistantSettings.memory_window_messages`, same
  knob the web chat uses, **and** through an age bound
  (`agent_channel.HISTORY_MAX_AGE`, 12h). The age bound exists because this
  history — unlike the web chat's, which lives in the browser tab and dies
  on reload — is persisted server-side forever: a count-only window let a
  days-old turn saying "amanhã, dia 9 de agosto" make the model answer
  today's "e amanhã?" for that stale date. Deterministic fast-path
  exchanges are not recorded into this history.

---

## 9. Dashboard Validation Rules

### 9.1 Appointment Creation (via Dashboard)

- `start_at` must be before `end_at`.
- `billing_type` must be `billable` or `courtesy` (regex validated in
  Pydantic schema).
- Service, place, and contact must belong to the authenticated tenant.
- Overlap validation: conflicts with existing schedule rejected.

### 9.2 Recurring Slot Creation

- Single slot: validated for overlap with existing slots.
- Bulk creation: same slot copied to multiple days, each validated
  independently.
- Slot kind: `availability` (a place stay) or `class` (a recurring class).
- An `availability` row is neutral: it has no roster, group name, level, or
  class capacity. Its stored legacy fields are `class_type="individual"` and
  `max_participants=1`.
- Participants can be assigned only to an explicitly created `class`; an
  availability row is never converted into a class.

### 9.3 Place Deletion

- Deletion removes only neutral place stays and place-specific rate settings,
  and clears matching customer home-place preferences.
- A place referenced by a recurring class, appointment, instructor event,
  occurrence reschedule, or waitlist entry cannot be removed. Resolve or move
  those records first; historical and scheduled items are never silently
  rewritten.

---

## 10. Waitlist ("Fila de Espera") Rules

- **Specific time only:** A `WaitlistEntry` always has a concrete desired
  date + start/end time, never a vague "sometime this week" request —
  deliberate scope decision so matching stays a direct extension of the
  existing capacity-search math rather than a fuzzy-search engine.
- **Status lifecycle:** `open` → `matched` (capacity now fits — set
  automatically, see below, or via the on-demand `find_waitlist_matches`
  agent tool) → `fulfilled` (booked, `fulfilled_appointment_id` set) or
  back to `open`; `cancelled`/`expired` are terminal. Cancel/fulfill are
  status transitions, not row deletes.
- **Event-driven auto-matching:** Cancelling an occurrence
  (`schedule_overrides.cancel_occurrence`, the only call site that
  currently frees capacity) runs `waitlist.mark_matches_for_date()` in the
  same transaction — never a separate commit, since it must roll back
  together with the cancellation if anything downstream fails. Only
  currently-`open` entries are affected; already-matched/fulfilled ones
  are left alone.
- **No new notification system:** A match is surfaced through the
  existing confirmation-summary text the instructor already sees (web
  chat or WhatsApp), not a separate alert — reusing plumbing rather than
  inventing one.
- **Not the same as commercial "waiting" status:** `Contact.commercial_status
  == "waiting"` ("Em espera") is an unrelated paused-billing concept from
  the financial module. Keep the two out of the same UI element.
- **Passive-observer entries need review:** `SchedulingEvent.action ==
  "waitlist_request"` becomes an `AppointmentCandidate`
  (status=`detected`), never a `WaitlistEntry` directly — the instructor
  completes/confirms it via the Clientes "Detectados" tab
  (`POST /api/appointment-candidates/{id}/fulfill-waitlist`). If the
  customer didn't state a specific time, the event still fires (flagged
  with an ambiguity) rather than being dropped — the instructor fills the
  gap during review, not the model guessing it.

### 10.4 Passive candidates and place context

- A passive appointment candidate inherits a place only from one stay that
  fully covers its interval. `Contact.home_place_id` can break a tie between
  covering stays but never creates availability.
- Authoritative creates autoexecute only after that unique resolution and a
  confirmation-time revalidation. Ambiguous or uncovered candidates cannot
  autoexecute.
- A candidate missing only place context uses `PassiveEscalation.status =
  "needs_place_review"`; it does not retry on the delivery worker. Creating,
  editing, or deleting a place stay reevaluates it and requeues it only if the
  place decision becomes unique.
- In Clientes > Detectados, an uncovered candidate begins with no selected
  place. The instructor must make an explicit choice, which is recorded as an
  exception when it lies outside a stay.

---

## 11. Instructor Events Rules

- **Not a class:** `InstructorEvent` is for paid work with no client —
  refereeing a tournament, running a workshop or clinic. Never reuse
  `Appointment` for this (`contact_id` is NOT NULL there) and never route
  its income through the participant-priced `RevenueOccurrence` engine.
- **Shared busy-time set:** An event and a class can't overlap, checked
  symmetrically both ways (`services/appointments.py::has_event_overlap`,
  `services/instructor_events.py::assert_no_event_conflict`). A
  `cancelled` event or appointment never blocks — same convention as
  `Appointment.status` filtering elsewhere. Confirmed events are also
  subtracted from the agent's free-time and place-availability answers.
- **Journey-independent:** An event can be created outside the professional's
  configured work journey — as can a conflict-free appointment after an
  advisory. A Saturday tournament is still a normal example of work outside
  usual teaching hours.
- **Revenue integration is additive, not merged:** Confirmed events'
  `income_cents` are summed into `RevenueSummaryDetail.event_income_cents`
  (`GET /api/revenue/summary`) — surfaced alongside, never merged into,
  `total_cents` or the participant-priced `by_place`/`by_customer`/
  `by_group` breakdowns, which are specifically about billing clients. Not
  added to the *projected*-revenue Financeiro dashboard
  (`financial_analytics.py`) at all — that tool buckets capacity segments,
  which an event isn't.
- **No passive-observer extraction:** Unlike waitlist entries, there is no
  `SchedulingEvent.action == "event"` — instructor events are dashboard
  and active-agent (web chat + WhatsApp) only, by explicit decision.
