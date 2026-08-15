# Passive Confirmation Detection and Ambiguity Escalation Roadmap v0.1 — 2026-08-10

**Status: Implemented locally. Phases 1-5 are available for local validation; full autonomy remains explicitly out of scope.**

## What this is

Today the passive observer (`docs/ai_agent_modes.md` Mode 2) watches the
instructor-customer WhatsApp conversation, detects scheduling intent, and
silently creates a mostly dismiss-only `AppointmentCandidate` — the
instructor only learns about it if they happen to open Clientes → Detectados.
This roadmap closes that review gap while preserving a clear distinction
between two decisions:

1. **Conversational confirmation detection:** did the instructor clearly
   assert that a specific scheduling operation is confirmed?
2. **Platform execution:** should the detected operation now create or change
   an appointment in the platform?

An explicit, unambiguous instructor confirmation is sufficient for the first
decision. Mutual agreement remains useful evidence, but is not required: the
instructor is the authoritative party for their own schedule. A clear
instructor confirmation becomes a confirmed detected event without causing
an additional WhatsApp prompt.

The agent proactively contacts the instructor on the private agent channel
(`Professional.agent_phone`) only when a plausible scheduling assertion is
genuinely ambiguous and can be resolved safely with a focused question. A
simple `sim`/`não` prompt is used only when all data needed for the proposed
operation is already resolved. If customer, date, time, place, or appointment
reference is missing, the agent must ask for that information or leave the
candidate for dashboard review instead of presenting an unsafe binary choice.

Clientes → Detectados becomes a first-class execution surface: eligible
candidates receive a **Confirmar agendamento** action with a deterministic,
editable preview. This gives the instructor a reliable platform fallback
whether or not a WhatsApp escalation was sent.

**Explicitly out of scope for this roadmap:** treating conversational
confirmation as authorization to write automatically. Clear instructor
language is enough to classify the event as confirmed, but a platform action
or an explicit reply to an ambiguity prompt is still required to execute it.
Fully autonomous booking remains a possible later step; see "Future: full
autonomy" at the bottom.

## Product decision table

| Conversation result | Detection result | Private-agent behavior | Platform behavior |
|---|---|---|---|
| Instructor clearly confirms a fully resolved operation | Confirmed scheduling event | No prompt | Show executable review action in Detectados |
| Both parties clearly agree on a fully resolved operation | Confirmed scheduling event | No prompt | Show executable review action in Detectados |
| Customer confirms but the instructor does not | Proposed/unconfirmed event | No prompt unless the meaning is genuinely ambiguous | Show for review; do not label instructor-confirmed |
| Confirmation wording is genuinely unclear, but all operation fields are resolved | Ambiguous candidate | Send a focused `sim`/`não` prompt when delivery gates pass | Keep available in Detectados |
| A required field is unresolved | Incomplete candidate | Do not push in the first release | Require editable dashboard review |

In this roadmap, **ambiguous** means the extractor cannot reliably determine
the meaning of the scheduling assertion. It does not mean merely
"customer-only," low business priority, or lacking mutual agreement.

## What already exists to build on

Several existing pieces can be reused, but the work also needs new schema,
review UI, linkage, and durable delivery state:

- **The propose → confirm → execute state machine is channel-agnostic.**
  `app.agent.candidates.propose()` (`backend/app/agent/candidates.py`)
  takes a `tool_name`, resolved `arguments`, a `preview_text`, and a
  `channel` — it has no idea whether the caller is the LLM orchestrator or
  a batch job. The state machine can execute a passive-originated proposal,
  while operation-specific validation and origin/idempotency metadata still
  need a safe integration layer.
- **The `sim`/`não` reply flow already resolves against "most recent
  pending proposal on this channel," not "most recent agent turn."**
  `_handle_confirmation_reply` / `_latest_pending_candidate` /
  `_pending_candidates_for_turn` (`backend/app/chat/agent_channel.py:131-210`)
  query `OperatorActionCandidate` by `channel="whatsapp"` +
  `status="proposed"` — they don't care who created the row. A
  passive-originated proposal is compatible with a plain `sim` reply. The
  handler still needs reply-association safeguards once delayed outbound
  delivery is introduced.
- **The extraction schema already distinguishes proposal from
  confirmation, conceptually.** `SchedulingEvent` (`backend/app/schemas/
  extraction.py`) has `action: Literal[..., "confirm", ...]` and an
  `Ambiguity.field` value of `"confirmation_status"`, and the extraction
  prompt's rule 3 (`backend/app/chat/prompt.py:18`) already instructs the
  model: *"Distinga PROPOSTAS de CONFIRMACOES. Uma proposta sem confirmacao
  NAO e um agendamento confirmado."* The concept exists, but `action`
  currently mixes the underlying operation (`create`/`reschedule`) with its
  conversational state (`confirm`). Those dimensions must be separated
  before they can safely drive execution or escalation.
- **Contact already has an optional place default.** `Contact.home_place_id`
  (`backend/app/models/contact.py:54`) can resolve the place without asking
  the extraction LLM when it is configured. It is nullable, however, and
  `SchedulingEvent` has no place field today while
  `propose_create_appointment` hard-requires `place_id`
  (`backend/app/agent/mutations.py:653`).
- **Fingerprint-based extraction dedup already exists.** `pipeline.py`'s
  `event_fingerprint()` (`backend/app/chat/pipeline.py:114-125`) already
  prevents the same detected event from creating duplicate
  `AppointmentCandidate` rows across repeated extraction runs with the same
  fingerprint. This is useful, but it is not sufficient for outbound-message
  or execution idempotency; those need their own durable keys and state.

## What's genuinely missing

- **Operation and conversational confirmation are conflated.** `action`
  may be `create`, `reschedule`, or `confirm`, even though a newly agreed
  appointment is both a create operation and a confirmed assertion.
  `confidence` (0.0-1.0) also conflates field parsing with confirmation
  meaning. Phase 1 separates the operation from who, if anyone, confirmed it.
- **No place on the extracted event, and no fallback chain for when even
  `home_place_id` is empty.** Needs a deterministic resolution step
  (Phase 2), with editable Detectados review when it cannot be resolved.
- **No executable review path for ordinary appointment candidates.** The
  Detectados API and UI can dismiss candidates and fulfill waitlist requests,
  but cannot create or reschedule an appointment from a detected event.
  This is the first missing bridge to close, before proactive messaging.
- **No bridge from `chat/pipeline.py` to a validated proposal flow.** These
  two subsystems (passive extraction and active-agent proposals) have never
  called each other. The bridge must use the existing operation-specific
  validation and deterministic preview logic rather than calling the
  low-level `candidates.propose()` function with hand-built arguments.
- **No handling for a passive push landing while an unrelated proposal is
  already pending on the same channel.** `_latest_pending_candidate` only
  ever resolves the single most recent `correlation_id` group — if a
  passive push arrives while the instructor already has a live, unrelated
  `sim`/`não` exchange in flight from the active agent, a `sim` reply would
  silently confirm the wrong thing. Needs an explicit collision rule
  (Phase 5).
- **No durable delivery/retry state.** `candidate_worker.py` deletes the
  `PendingProcessing` row before extraction. A collision-skipped or failed
  outbound message therefore has no automatic "next worker tick" retry.
  Delivery needs a persisted queued/sent/failed state or a small outbox that
  is polled independently from conversation extraction.
- **No link from `AppointmentCandidate` (passive detection row) to its
  operation outcome.** `docs/ai_agent_modes.md` already notes these are two
  separate state machines. A durable link to an `OperatorActionCandidate`
  and, after execution, the resulting appointment is necessary for
  idempotency, retries, audit, and Detectados outcome display.

## Product decisions and remaining parameters

The behavioral decisions are fixed below. Exact phrase coverage, TTL length,
and retry counts should be tuned from fixtures and production observations:

1. **Which instructor assertions count as explicit confirmation?** Start
   strict with language that clearly applies to a specific operation and
   resolved time (for example, "confirmado", "fechado então", "ok, te
   espero"). Acknowledgements without a clear referent, future promises
   ("vou confirmar depois"), and tentative wording remain unclear or
   unconfirmed. Mutual agreement can increase confidence, but never becomes
   a prerequisite when the instructor's confirmation is explicit.
2. **What happens when `home_place_id` is empty and no place was
   mentioned?** Options: (a) don't push, fall back to the
   `AppointmentCandidate` with an editable Detectados review; (b) send a
   non-binary clarification asking for the place. Default to (a) for the
   first release: never invent a place, and never send a `sim`/`não` prompt
   whose execution arguments are incomplete.
3. **Collision handling: queue or refuse?** When a passive push would
   collide with an already-pending proposal on the same channel (see
   "What's genuinely missing" above), queue the escalation in durable
   delivery state and create/deliver its executable proposal only when the
   channel is clear. This avoids an unseen `proposed` row intercepting a reply
   intended for another interaction and avoids inventing a numbered-reply
   protocol for what should be a rare overlap.
4. **TTL for an ambiguity escalation.** The default
   `DEFAULT_TTL_MINUTES = 10` (`candidates.py:31`) assumes the instructor
   is mid-conversation with the agent and will reply within minutes. An
   ambiguity escalation is unprompted, so use a separately configurable TTL.
   Its expiry must be reflected in Detectados without losing the original
   passive candidate.

## Phased plan

### Phase 1 — Separate operation from conversational confirmation

- Replace the overloaded scheduling meaning with two explicit dimensions in
  `SchedulingEvent` (`backend/app/schemas/extraction.py`):
  - `operation`: the platform operation being discussed (`create`,
    `reschedule`, `cancel`, `recurrence`, `waitlist_request`, or `none`).
  - `confirmation_status`: `instructor_confirmed`, `customer_confirmed`,
    `mutually_confirmed`, `unclear`, or `not_confirmed`.
- Preserve API compatibility during the migration only if required by current
  callers; do not leave two competing sources of truth. `AppointmentCandidate`
  must persist the normalized operation and confirmation status used by later
  phases.
- Treat `instructor_confirmed` and `mutually_confirmed` as confirmed detected
  events. `customer_confirmed` alone is not instructor confirmation, while
  `unclear` is the only confirmation state eligible for ambiguity escalation.
- Keep field-resolution uncertainty separate. Existing `ambiguities` remain
  the source for unresolved customer/date/time/duration/appointment reference;
  add place resolution explicitly in Phase 2. Do not infer "unclear" merely
  from a low aggregate confidence score.
- Extend `EXTRACTION_SYSTEM_PROMPT` rule 3 with pt-BR positive and negative
  examples. Explicit instructor assertions such as "confirmado", "fechado
  então", and "ok, te espero" count when they clearly refer to a resolved
  operation. "Deixa eu ver", "vou confirmar depois", an isolated "beleza",
  or wording with no clear referent does not.
- Include the normalized operation and confirmation status in the event
  identity/update strategy. A later message can legitimately advance an
  existing proposal to instructor-confirmed; the pipeline must update or
  supersede the earlier candidate without creating two independently
  executable cards for the same real-world operation.
- Verify with fixtures covering instructor-only confirmation, mutual
  confirmation, customer-only confirmation, tentative instructor wording,
  an unclear acknowledgement, and proposal-to-confirmation evolution across
  two extraction windows. Human judgment is the acceptance criterion.

### Phase 2 — Deterministic candidate resolution and operation mapping

- Add a small candidate-resolution service that converts an
  `AppointmentCandidate` into either a validated operation-specific input or
  an explicit list of missing fields. Keep it independent from delivery and
  UI concerns.
- Resolve place deterministically from an explicitly extracted place when
  available, otherwise from `Contact.home_place_id`; return unresolved rather
  than inventing a value. Validate that contact, place, and any referenced
  appointment belong to the authenticated professional.
- Map each supported operation to the correct existing mutation path:
  - `create` uses appointment-creation validation and execution.
  - `reschedule` requires `existing_appointment_id` and uses the reschedule
    mutation, never the create executor.
  - Other operations remain review-only until their operation-specific
    behavior is deliberately added to this roadmap.
- Require contact, start/end time, service, and place for create; require the
  referenced appointment plus the reschedule-specific fields for reschedule.
  Return missing fields for editable dashboard review.
- Reuse existing conflict validation and deterministic preview construction
  from the mutation layer. If those functions need passive-specific metadata,
  add narrow optional parameters rather than rebuilding their logic around a
  direct low-level `candidates.propose()` call.
- Verify the pure resolution behavior and each supported mapping with unit
  tests, including tenant mismatch, missing default place, missing appointment
  reference, invalid time range, and schedule conflict.

### Phase 3 — Confirm from Clientes → Detectados

This is the first phase that changes instructor-facing behavior.

- Add `POST /api/appointment-candidates/{id}/confirm-appointment` for
  supported create candidates. Add a separate reschedule endpoint or a
  clearly discriminated request contract when reschedule support lands; do
  not route both operations through appointment creation.
- The request accepts instructor-editable values needed to complete the
  operation, including `place_id` and corrected times. The backend still
  derives professional ownership from the authenticated session and validates
  every referenced entity.
- Execute candidate confirmation as one coherent application operation:
  validate the candidate is still pending, resolve the operation, recheck
  conflicts, execute, record the audit trail, link the resulting appointment,
  and transition the passive candidate out of `detected`. Add the database
  constraint/idempotency key needed to ensure a second click or retry cannot
  create a duplicate appointment; this protection is part of Phase 3, not
  deferred to messaging work.
- Prefer a shared service used by both this endpoint and later WhatsApp
  escalation. Do not call the generic calendar endpoint and then dismiss the
  passive candidate in a separate request, because that permits partial state.
- Extend `CandidateDetail` with normalized operation, confirmation status,
  resolution/missing-field information, delivery/outcome state, and resulting
  appointment information needed by the UI. Keep one source of truth for each
  outcome rather than copying status strings across models.
- In `frontend/src/components/ontology/detected-candidates-tab.tsx`, show
  **Confirmar agendamento** for eligible create candidates. Open a compact
  review dialog prefilled with customer, date, start/end time, service, and
  resolved/default place; allow correction before submission. Reuse the
  existing appointment form components where that can be done without
  coupling the candidate flow to calendar-only state.
- Preserve the existing optimistic UI style: remove the card immediately on
  confirmation, reconcile with the returned appointment, and restore the card
  with a useful error if validation or execution fails.
- Keep dismiss and waitlist behavior unchanged. Show non-executable candidates
  with their missing fields rather than a misleading confirmation button.
- Verify API success, conflict, missing contact/time/place, unsupported
  operation, already-resolved candidate, tenant isolation, and audit/linkage.
  Add frontend tests for button eligibility, prefilled review, optimistic
  success, and rollback on failure.

### Phase 4 — Escalation linkage and lifecycle display

- Retain the Phase 3 link from `AppointmentCandidate` to its resulting
  `Appointment`, and add the nullable link to an `OperatorActionCandidate`
  needed for private-agent escalation. Establish each link as part of the
  workflow that creates the related row, not as later best-effort
  reconciliation.
- Add a stable operator-proposal idempotency key derived from the passive
  candidate and intended operation. Enforce uniqueness at the database
  boundary so worker restarts and delivery retries cannot create parallel
  executable actions.
- Define the passive lifecycle explicitly, for example: detected → under
  review/escalation → executed, dismissed, rejected, expired, or failed.
  Prefer deriving detailed execution state from linked source-of-truth rows;
  add passive status values only where they represent a distinct passive
  lifecycle decision.
- Surface "detected → escalated → confirmed/rejected/expired → executed" in
  Detectados. A WhatsApp rejection or expiry must not erase the evidence card;
  the instructor can still correct and confirm it through the platform if the
  underlying operation remains valid.
- Record origin (`passive_observer`), candidate ID, operation, and delivery
  context in operational-event payloads without logging conversation PII.
- Verify database uniqueness, retry behavior, linked outcome projection, and
  recovery after failures between proposal, execution, and response handling.

### Phase 5 — Ambiguity-only private-agent escalation

- Add a durable escalation/outbox record or equivalent persisted delivery
  state, polled independently from `PendingProcessing`. Extraction success,
  collision deferral, provider failure, and process restart must not lose the
  candidate or create duplicate messages.
- Queue an escalation only when all of these gates pass:
  1. The normalized operation is supported by the shared service.
  2. `confirmation_status == "unclear"`; clear instructor or mutual
     confirmation does not trigger a message.
  3. The candidate has no unresolved execution fields. Customer, date/time,
     service, place, and any required appointment reference are resolved.
  4. `Professional.agent_phone` and the professional-role actor user exist.
  5. No unrelated WhatsApp proposal is currently awaiting a `sim`/`não`
     response for that professional.
- If required fields are missing, do not create a binary proposal. Leave the
  candidate for editable Detectados review in the first release. A future
  non-binary clarification conversation can be added separately after its
  reply-correlation semantics are designed.
- Build the proposal through the same operation-specific validation and
  preview service used by Phase 3. Use the correct create or reschedule
  executor, attach the passive idempotency key and origin metadata, and link
  the rows before delivery.
- Send one focused question containing the deterministic preview plus the
  shared `sim`/`não` instruction. A positive reply executes through the
  existing candidate state machine; a negative reply rejects only the linked
  escalation and leaves the passive evidence available for platform review.
- Update the WhatsApp reply handler as needed to bind replies to the delivered
  escalation safely. Do not rely solely on whichever proposed candidate has
  the newest timestamp when multiple pending groups or delayed deliveries are
  possible.
- Use a separately configurable TTL and retry policy from `.env`. Expiry and
  provider failure must update delivery/outcome state without silently
  dismissing the passive candidate.
- Verify no push for clear instructor confirmation, mutual confirmation,
  customer-only confirmation, or unresolved fields; one push for eligible
  `unclear`; collision deferral and later delivery; send failure/retry;
  idempotency; expiry; positive/negative reply association; and tenant
  isolation.

## Future: full autonomy (removing the confirmation step)

Not scheduled. Conversational confirmation detection and platform execution
remain separate decisions in this roadmap. Treating an instructor's
customer-channel statement as direct authorization to write should be
**earned, not timed**. Before drafting that phase:

- Phases 3-5 need to run long enough to accumulate real platform-confirm,
  correction, dismiss, ambiguity-reply, reject, and ignore rates. Break the
  data down by `confirmation_status` and evidence pattern, while avoiding raw
  conversation content in analytics. If a supposedly explicit instructor
  pattern is frequently corrected, that is an extraction fix, not evidence
  that autonomy is ready.
- A near-zero false-positive rate (booking something the instructor didn't
  actually agree to) is the bar, not "usually right" — a wrong auto-booked
  appointment is a real-world scheduling conflict for a paying customer,
  not a dismissable UI card.
- Even then, "remove confirmation" may mean "confirmation becomes a
  cancel-window notification" (book it, but tell the instructor and let
  them undo within N minutes) rather than a silent write — worth deciding
  as its own roadmap once production data exists to argue from.

## Suggested sequencing

Implement Phase 1 first because every later gate depends on normalized
operation and confirmation semantics. Phase 2 follows with deterministic
resolution and correct operation mapping. Phase 3 then delivers the platform
confirmation fallback with execution idempotency. Phase 4 adds escalation
linkage and makes its lifecycle observable before Phase 5 introduces
asynchronous WhatsApp delivery and retries.

Do not start Phase 5 until Phases 1-4 are verified end to end: ambiguity-only
messaging is safe only when the same candidate can already be reviewed,
executed once, linked to its outcome, and recovered through the platform.
"Future: full autonomy" has no fixed timeline and depends on production data
from the completed roadmap.
