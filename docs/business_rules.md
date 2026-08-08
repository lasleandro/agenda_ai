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

### 1.2 Work Journey Boundaries

- Appointments must fall within the instructor's configured work journey
  intervals (`WorkJourneyInterval` rows), and must not overlap a break
  interval.
- Each day of week has zero or more work intervals and optionally break
  intervals.
- **Fails open until configured:** a professional who has never added any
  `WorkJourneyInterval` row (any day) is left unrestricted — the check
  only starts enforcing once they've actually set working hours, so
  onboarding isn't blocked by a screen they haven't visited yet. Once at
  least one row exists, appointments outside the configured intervals for
  that weekday are rejected.

### 1.3 Recurrence Expansion

- Recurring appointments (with RRULE) are expanded into per-date
  occurrences by the scheduling engine.
- `ScheduleOccurrenceOverride` cancels or reschedules a single occurrence
  without changing the template.
- A single occurrence can have at most one active override
  (409 Conflict if attempting double-cancel).

### 1.4 Class Types

- `individual`: One-on-one class. No additional participants.
- `group`: Multi-student class. Additional participants can be added.
- Adding a participant to an individual appointment auto-promotes it to
  group.

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

- **Global rates** (`FinancialRate`): Per-participant-count (1-4 students).
- **Place-specific rates** (`PlaceFinancialRate`): Per-place, per-time-category
  (regular/prime), per-participant-count.
- Place rates override global rates for the same (place, time_category, count).
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
against the **global rate only** (`FinancialRate`, no place to resolve a
`PlaceFinancialRate` override against) — a tenant with no global rate
configured gets 0 revenue credit for that uncovered time, same
"unpriced contributes 0, not an error" convention used everywhere else in
this dashboard. This only applies to the unfiltered "all places" view,
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
| `platform_admin` | Admin panel (`/api/admin/*`), impersonation, tenant management |
| `professional` | Own tenant data only, all regular endpoints |

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
- Slot kind: `availability` (open time block) or `class` (enrolled group).
- Adding a participant to an `availability` slot auto-promotes it to
  `class`.

### 9.3 Place Deletion

- Deleting a place cascades to:
  - Its recurring slots (and their participants)
  - Appointment references become orphaned (place_id set to NULL, name
    snapshot retained in revenue occurrences)
