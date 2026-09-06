# Agent Navigability Map

This is a code-first guide to the two agent systems currently implemented in
Tennis OS: the **active instructor agent** and the **passive WhatsApp
observer**. Use it to locate the right entry point, tool, domain record, and
execution boundary before changing agent behavior.

It describes shipped code, not future roadmap scope. For product context, see
[AI agent modes](ai_agent_modes.md) and [Ontology & chat architecture](ontology_chat_architecture.md).

## 1. Fast orientation

| If you need to understand or change… | Start here | Then follow |
|---|---|---|
| Web chat request or confirmation | `backend/app/api/assistant.py` | `agent/orchestrator.py` → `agent/tools.py` or `agent/mutations.py` → `agent/candidates.py` |
| Private instructor WhatsApp agent | `backend/app/chat/agent_channel.py` | same orchestrator and candidate lifecycle as web chat |
| Customer/instructor WhatsApp observation | `backend/app/chat/ingestion.py` | `chat/pipeline.py` → `chat/extraction.py` → candidate review/escalation |
| Debounced passive processing | `backend/app/chat/candidate_worker.py` | `PendingProcessing` → `pipeline.process_conversation()` |
| Passive ambiguity confirmation | `backend/app/services/passive_escalation.py` | `OperatorActionCandidate` → private WhatsApp confirmation |
| Shared scheduling truth and validations | `backend/app/services/scheduling.py` | appointments, recurring slots, place stays, conflicts |
| Candidate review UI/API | `backend/app/api/appointment_candidates.py` | `services/candidate_resolution.py`, `services/candidate_execution.py` |

### The two paths at a glance

```text
ACTIVE — instructor explicitly asks
web / private agent WhatsApp
  → run_agent_turn()
  → read tool: return data
  → propose_* tool: OperatorActionCandidate
  → instructor confirms
  → executor re-validates, writes, and records OperationalEvent

PASSIVE — customer/instructor conversation is observed
customer-facing WhatsApp
  → persist Conversation + Message; debounce
  → structured extraction + temporal validation
  → AppointmentCandidate + AppointmentEvidence
  → auto-execute only authoritative, fully resolved create/reschedule
    OR private confirmation for eligible unclear resolution
    OR leave it for Detectados/place review
```

The number pairing is the routing boundary. A message **to** the shared
platform agent number (`PLATFORM_AGENT_WHATSAPP_NUMBER`) goes to the active
channel first, and its tenant is resolved from the **sender** (an active
tenant's `assistant_phone`); an unrecognized sender is claimed and dropped.
Messages to a tenant's `assistant_phone` continue into passive ingestion. The
active channel additionally requires a confirmed binding
(`Professional.agent_binding_confirmed_at`).

## 2. Ontology: records agents can navigate

The active agent reads and proposes changes against the instructor-scoped
operational ontology. `professional_id` is always derived from the authenticated
request or the receiving number; it is never supplied by the model.

```text
Professional (tenant)
├── User                         actor for authenticated/WhatsApp actions
├── Contact ── EntityAlias        student/customer identity and fuzzy lookup
├── Place ── PlaceStay            venue and coverage for a time interval
├── WorkJourneyInterval           instructor working availability
├── RecurringSlot ── participants weekly group class template
│   └── ScheduleOccurrenceOverride dated cancellation/reschedule/absence effects
├── Appointment ── participants   one-off class/booking
├── InstructorEvent               non-class work (clinic, workshop, referee)
├── MakeupClassCredit             credit grant/redemption lifecycle
├── WaitlistEntry                 unmet demand for a dated time window
└── OperationalEvent              append-only audit trail of domain/agent events

Agent-control records
├── OperatorActionCandidate       active/proposed write awaiting confirmation
├── AgentChannelMessage           persisted active WhatsApp LLM history
├── Conversation ── Message        customer-facing WhatsApp history
├── PendingProcessing             passive debounce work item
├── AppointmentCandidate          extracted scheduling interpretation
├── AppointmentEvidence           source messages supporting extraction
└── PassiveEscalation             durable private-confirmation delivery state
```

Two candidate types deliberately serve different purposes:

| Record | Created by | Meaning | Primary states |
|---|---|---|---|
| `OperatorActionCandidate` | `propose_*` tools, including eligible passive escalations | Deterministic, executable change with preview and resolved arguments | `proposed` → `confirmed` → `executed`, or `rejected` / `expired` / `failed` |
| `AppointmentCandidate` | Passive extraction | Evidence-backed interpretation of a WhatsApp conversation | `detected`, `dismissed`, `fulfilled` |

An `AppointmentCandidate` can link to the `OperatorActionCandidate` created
for a passive escalation, but it is not itself the active-agent confirmation
record.

## 3. Active agent: entry points and action boundary

### 3.1 Entry points

| Channel | Entry point | Context and confirmation |
|---|---|---|
| Web chat | `POST /api/assistant/messages` in `api/assistant.py` | Client supplies the message history. A preview card invokes the confirm/reject endpoints. |
| Active WhatsApp | `chat/ingestion.dispatch_whatsapp_event()` → `chat/agent_channel.try_handle()` | Claims messages to the shared platform agent number, resolves the tenant from the sender, requires a confirmed binding, persists recent `AgentChannelMessage` history for up to 12 hours, and accepts reply keywords such as `sim` / `nao`. |
| Fast WhatsApp lane | `agent_channel.COMMANDS` | `hoje`, `amanha`, `esta semana`, and `proxima aula` are deterministic schedule queries; no LLM or history write. |

All non-fast-path active requests converge in
`agent/orchestrator.run_agent_turn()`. It builds the Portuguese system prompt,
passes `TOOL_SPECS + MUTATION_TOOL_SPECS` to Azure OpenAI, and runs at most six
tool iterations.

### 3.2 Tool catalogue

Tool schemas and dispatch maps are the canonical catalogue:
`agent/tools.py` (`TOOL_SPECS`, `TOOL_DISPATCH`) and `agent/mutations.py`
(`MUTATION_TOOL_SPECS`, `MUTATION_TOOL_DISPATCH`).

| Tool family | Tools | Result |
|---|---|---|
| Entity lookup | `search_contacts`, `search_places`, `find_groups` | Returns tenant-scoped IDs needed by later tools. |
| Schedule and time | `get_schedule`, `get_next_session`, `resolve_date_phrase`, `find_instructor_openings` | Returns schedule truth, deterministic relative-date resolution, or real calendar gaps. |
| Makeup and waitlist | `list_makeup_credits`, `recommend_makeup_slots`, `list_waitlist_entries`, `find_waitlist_matches` | Reads credit availability and unmet/fillable demand. |
| Events | `list_events` | Reads non-class work commitments. |
| Appointment/group changes | `propose_create_appointment`, `propose_cancel_schedule`, `propose_reschedule_occurrence`, `propose_add_appointment_participant`, `propose_remove_appointment_participant`, `propose_add_group_member`, `propose_remove_group_member` | Creates a confirmation candidate; no immediate mutation. |
| Customer and credit changes | `propose_update_contact`, `propose_note_participant_absence`, `propose_redeem_makeup_credit` | Creates a confirmation candidate; no immediate mutation. |
| Demand and work events | `propose_add_waitlist_entry`, `propose_remove_waitlist_entry`, `propose_create_event` | Creates a confirmation candidate; no immediate mutation. |

Important navigation rule: names are resolved by a search/list tool first.
Mutation tools consume actual UUIDs and their executors repeat tenancy,
availability, and conflict validation at execution time.

### 3.3 Active write lifecycle

```text
model calls propose_*
  → mutations.py performs early validation
  → candidates.propose() writes OperatorActionCandidate(status=proposed)
     + agent.action.proposed OperationalEvent
  → orchestrator returns deterministic preview (and stops tool use)
  → confirmation surface invokes candidates.confirm(), or reject()
  → registered MUTATION_EXECUTOR revalidates and applies domain service work
  → candidate becomes executed + agent.action.executed event

Failure: executor transaction rolls back; candidate is separately marked failed.
Expiry: a proposed candidate is lazily marked expired at confirm/reject time
(passive escalation also checks sent proposal expiry in its worker).
```

The executor registry is intentionally inverted: `agent/candidates.py` owns
`MUTATION_EXECUTORS`, while `agent/mutations.py` registers tool-specific
executors. When adding a mutation, add its schema, propose function, executor,
dispatch entry, and executor registration together.

## 4. Passive observer: extraction, resolution, and escalation

### 4.1 Ingestion to evidence

```text
provider webhook (`api/whatsapp.py`)
  → provider normalizes into WhatsAppEvent
  → ingestion.dispatch_whatsapp_event()
      ├── to the platform agent number: agent_channel.try_handle() owns it
      │   (tenant resolved from sender; drops platform-owned numbers)
      └── customer-facing phone: ingest_normalized_message()
          → tenant/contact/conversation lookup or creation
          → idempotent Message insert (provider_message_id)
          → PendingProcessing upsert with a moved debounce deadline

candidate_worker.process_due_conversations()
  → pipeline.process_conversation()
  → build last 20 messages + contact/professional/upcoming booking context
  → extraction.extract_scheduling_events() (structured LLM output)
  → chat.temporal.validate_temporal()
  → upsert AppointmentCandidate by event fingerprint
  → link AppointmentEvidence rows to supporting messages
```

`PendingProcessing` is a durable debounce queue, not an external broker.
`candidate_worker.py` polls due rows using `FOR UPDATE SKIP LOCKED`; its loop
is separate from `passive_escalation_worker.py`, which delivers queued private
confirmations. Run both in development through `python start_server.py --worker`
or through their individual module entry points.

### 4.2 Decision gate after extraction

Each extracted candidate is passed to two independent decisions in
`pipeline.process_conversation()`:

| Gate | Implementation | Outcome |
|---|---|---|
| Authoritative automatic execution | `_auto_execute_authoritative_candidate()` | A `detected` candidate marked `instructor_confirmed` or `mutually_confirmed`, with a resolved create/reschedule operation, may execute inside a nested transaction. Failures leave the source candidate reviewable. |
| Private ambiguity escalation | `passive_escalation.queue_if_eligible()` | An `unclear`, detected create/reschedule that is sufficiently resolvable can be queued for a private active-WhatsApp confirmation. |
| Explicit dashboard review | `api/appointment_candidates.py` and candidate-resolution/execution services | Candidates with missing or ambiguous place context, and any remaining detected items, stay in the review surface. |

Place resolution is a safety boundary: `services/candidate_resolution.py` and
`services/place_stays.py` require a covering, tenant-owned place context.
The contact's home place can break a tie between covering stays; it does not
by itself establish availability.

### 4.3 Passive-to-active handoff

`PassiveEscalation` makes an eligible unclear passive result durable before it
sends a message. Its worker:

1. refuses delivery while an unrelated pending WhatsApp proposal exists;
2. resolves the candidate again, moving unresolved venue cases to
   `needs_place_review`;
3. calls the same `propose_create_appointment` or
   `propose_reschedule_occurrence` code as the active agent, using a stable
   idempotency key;
4. links the resulting `OperatorActionCandidate` back to the
   `AppointmentCandidate` and sends its deterministic preview from the
   platform agent number to the tenant's `assistant_phone`;
5. lets the ordinary WhatsApp `sim` / `nao` confirmation flow execute or
   reject it.

This is the only intentional convergence of the two agents: the passive
system may prepare a candidate, but the active candidate lifecycle remains
the execution boundary for unclear cases.

## 5. Runtime, configuration, and verification map

| Concern | Source of truth | What to check before changing it |
|---|---|---|
| Azure model/client | `services/azure_openai.py` and `.env` | Active function calls and passive structured extraction use different call patterns. |
| Assistant memory/temperature | `models/assistant_settings.py`, `services/assistant_settings.py` | Web history is provided by the client; WhatsApp history is server-persisted and age-bounded. |
| Passive debounce | `PIPELINE_DEBOUNCE_SECONDS` in `chat/pipeline.py` | Worker must be running for queued conversations to process. |
| Passive delivery TTL/retry | `PASSIVE_ESCALATION_TTL_MINUTES`, `PASSIVE_ESCALATION_RETRY_SECONDS` in `services/passive_escalation.py` | A proposal can expire; failed deliveries remain durable for retry. |
| WhatsApp provider boundary | `integrations/whatsapp/contracts.py`, `registry.py`, `ycloud.py` | Keep provider payload parsing outside agent and domain code. |
| Shared agent number + binding | `integrations/whatsapp/platform_number.py` (`PLATFORM_AGENT_WHATSAPP_NUMBER`), `services/agent_binding.py`, `Professional.agent_binding_confirmed_at` | One number for every tenant; tenant resolved from the sender; normal handling gated on a confirmed binding. |
| Audit | `services/operational_events.py`, `OperationalEvent` | Every confirmed active mutation should record the proposal and final outcome chain. |
| Tests | `backend/tests/test_agent.py`, `test_agent_channel.py`, `test_action_candidates.py`, `test_ingestion.py`, `test_pipeline.py`, `test_passive_escalation.py` | Run targeted tests first, then the backend suite under the `agenda` conda environment. |

## 6. Change checklist

1. Classify the request: active agent, passive observer, shared ontology, or
   provider/runtime plumbing.
2. Preserve tenant derivation from authentication/phone routing; never accept
   it from LLM arguments or a client request body.
3. For a new read capability, add a tenant-scoped function in `agent/tools.py`,
   its schema and dispatch mapping, then a behavior-level test.
4. For a new active mutation, implement the full proposal/executor lifecycle
   described in section 3.3; do not let an LLM-facing function write directly.
5. For passive behavior, update structured extraction schema/prompt, temporal
   validation, candidate resolution, and the post-extraction safety decision
   together; extraction confidence alone is not authorization to write.
6. Reuse domain services already used by REST endpoints so conflict, place,
   credit, and audit rules stay consistent.
7. Update this map and the more detailed architecture document if the routing,
   ontology, or execution boundary changes.

## 7. Conversational flow: intents, entities, and outcomes

The system has two conversational interpretations with different contracts:

| Conversation | Intent contract | Entity source | Outcome |
|---|---|---|---|
| Active instructor agent | No closed intent enum. The LLM chooses one or more registered tools from the system prompt. | Search/list read tools resolve real IDs before a mutation tool is called. | Answer, clarification, or `OperatorActionCandidate`. |
| Passive observer | `SchedulingEvent` Pydantic schema with a closed `operation` and `confirmation_status`. | The conversation's tenant/contact plus the customer's upcoming appointments; later services resolve the target and place. | `AppointmentCandidate`, evidence, and a guarded review/execution decision. |

### 7.1 Active conversation turn

```text
Instructor message
  → choose route: web API or active WhatsApp number
  → optional fast command (`hoje`, `amanha`, `esta semana`, `proxima aula`)
     → deterministic text reply
  → otherwise, run_agent_turn(history + current message)
     → intent inferred by model from prompt and tool schemas
     → 0..N read tools: resolve entities / inspect schedule / calculate availability
     → no adequate entity result? ask a targeted clarification
     → write requested? call one or more propose_* tools
        → preview + explicit confirmation required
     → otherwise return grounded Portuguese reply
```

The active system prompt imposes these conversational controls:

- Relative date language must go through `resolve_date_phrase`; the model does
  not calculate dates itself.
- A zero-result or multi-result contact/place/group search requires
  clarification rather than guesswork.
- The agent should use `find_instructor_openings` for open-ended availability;
  a specifically requested booking goes straight to the validating proposal.
- It must distinguish cancelling a whole group occurrence from recording one
  participant's absence, and it must use a real credit/waitlist ID discovered
  through the corresponding list tool.
- Once a mutation creates a candidate, the orchestrator stops further tool
  calls and requests final wording for the deterministic preview.

### 7.2 Active intent-to-tool map

These are conversational intent families, not persisted enum values. They map
to the tools the current prompt and tool registry make available.

| Instructor intent | Required/typical entities | Navigation sequence | Result |
|---|---|---|---|
| Find a student, place, or group | contact/place/group name; optional place or weekday | `search_contacts` / `search_places` / `find_groups` | Match list or clarification. |
| Ask about agenda or next lesson | date/range or contact | `resolve_date_phrase` when relative; then `get_schedule` or `get_next_session` | Grounded agenda reply. |
| Ask when free | date, optional period/duration/place | `resolve_date_phrase`; `find_instructor_openings` | All usable calendar gaps, including whether configured places cover them. |
| Create one-off lesson | contact, start/end, service, place (or one uniquely covering stay), optional billing type | resolve contact/date/place as needed; `propose_create_appointment` | Candidate to create appointment. |
| Change/cancel an existing occurrence | target occurrence, occurrence date, new time/place when rescheduling | `get_schedule` to identify `source_type` + `source_id`; `propose_reschedule_occurrence` or `propose_cancel_schedule` | Candidate for a dated override/cancellation. |
| Manage group or one-off participants | contact plus recurring slot or appointment | search contact; `find_groups` or `get_schedule`; participant proposal | Candidate to update roster. |
| Record one student's group absence | contact, recurring slot, occurrence date | resolve contact/group/date; `propose_note_participant_absence` | Candidate; executor may grant eligible makeup credit. |
| Redeem makeup credit | contact, available credit, time/place | `list_makeup_credits`; optionally `recommend_makeup_slots`; proposal | Candidate that consumes the selected credit atomically. |
| Track unmet scheduling demand | contact, explicit desired date/time, optional place | resolve contact/date/place; `propose_add_waitlist_entry` | Candidate to create a `WaitlistEntry`. |
| Remove waitlist demand | waitlist entry | `list_waitlist_entries`; `propose_remove_waitlist_entry` | Candidate to cancel entry. |
| Update customer details | contact and allow-listed changes | `search_contacts`; `propose_update_contact` | Candidate to update `Contact`. |
| Record non-class work | event type, time; optional place/title/income/note | date/place resolution as required; `propose_create_event` | Candidate to create `InstructorEvent`. |

Entity reference rules:

```text
Natural-language name/phrase
  → read tool returns UUID and display context
  → proposal stores UUIDs in resolved_arguments
  → executor reads those UUIDs again under professional_id scope
  → domain service validates current state before it writes
```

The proposal preview, affected-entity list, and executor arguments originate
from the stored candidate—not from the assistant's natural-language reply.

### 7.3 Active clarification and confirmation states

```text
unknown/ambiguous entity or missing scheduling detail
  → assistant asks a question; no write candidate exists

fully resolved, read-only request
  → assistant reply; tool trace may be shown in web chat

valid mutation request
  → proposed candidate (10-minute default TTL)
  → web: Confirm / Reject endpoint
     WhatsApp: `sim` / `nao` resolves all proposals from that turn's correlation ID
  → executed, rejected, expired, or failed
```

The active WhatsApp conversation stores only non-fast-path user/assistant
turns. Web history instead comes from the request body, so conversational
context is deliberately channel-specific even though the tool loop is shared.

### 7.4 Passive extraction intent schema

`schemas/extraction.py` defines the passive vocabulary. One conversation
window can yield multiple distinct events; when none apply, it must yield one
`none` event.

| `operation` | Meaning in a customer/professional conversation | Key fields |
|---|---|---|
| `create` | A new one-off scheduling decision | `customer_name`, `start_at`, `end_at`, `service` |
| `reschedule` | A change to an existing booking | new time fields plus `existing_appointment_id` when identifiable |
| `cancel` | A cancellation of an existing booking | appointment reference and relevant timing/context |
| `recurrence` | An explicitly requested recurring arrangement | `recurrence_rule` and scheduling fields |
| `waitlist_request` | Demand exists but no available time is currently offered | desired `start_at`/`end_at` when stated; otherwise date/time ambiguity |
| `none` | No scheduling decision to act on | explanation and evidence only |

`confirmation_status` is independent of `operation`:

| Status | Extractor meaning | Downstream relevance |
|---|---|---|
| `instructor_confirmed` | The professional explicitly confirms a specific operation/time. | May qualify a resolved create/reschedule for automatic execution. |
| `customer_confirmed` | Only the customer clearly confirms, including an unambiguous cancellation/reschedule of their own existing booking. | Preserved as evidence; does not by itself authorize a new booking. |
| `mutually_confirmed` | Both sides clearly accept a concrete operation. | May qualify a resolved create/reschedule for automatic execution. |
| `unclear` | Confirmation language or reference cannot be safely tied to the event. | May qualify for a private confirmation only after resolution gates pass. |
| `not_confirmed` | Request, proposal, question, or otherwise no explicit confirmation. | Remains evidence/review material; it does not trigger an automatic write. |

The extraction prompt deliberately treats a customer's standalone request for
a **new** lesson as `none`, not `create`; a professional confirmation is
needed because the request consumes their time. In contrast, a customer's
clear cancellation/reschedule of their known existing appointment is still an
event worth extracting. Relative dates are resolved using each message's
timestamp and the professional's timezone before persistence.

### 7.5 Passive entity and evidence map

```text
ConversationWindow
├── ProfessionalContext: timezone, default duration, default service
├── ContactContext: customer display name
├── last 20 Message rows: direction, timestamp, text, IDs
└── customer's future Appointment rows: ID, start/end, service

SchedulingEvent
├── intent: operation + confirmation_status
├── temporal fields: start_at, end_at, duration_minutes, recurrence_rule
├── identity/reference fields: customer_name, existing_appointment_id
├── quality: confidence, ambiguities, explanation
└── provenance: evidence_message_ids

AppointmentCandidate
├── stores operation/confirmation status and proposed timing
├── records confidence/ambiguities/fingerprint
└── joins its supporting messages through AppointmentEvidence
```

The passive extractor does not receive a general contacts/places/groups search
toolbox. It receives the conversation's already-routed tenant and contact plus
that contact's upcoming appointments. `candidate_resolution.py` subsequently
turns the extracted timing and reference into a resolvable domain operation,
including the place-stay checks.

### 7.6 Passive conversation outcome states

```text
new messages
  → debounced window is extracted and temporally validated
  → AppointmentCandidate(status=detected) + evidence
  → fingerprint matches a prior candidate? update it rather than duplicate it
  → resolve target, place, and operation
      ├── authoritative + resolved create/reschedule
      │   → revalidate and execute; failure remains detected for review
      ├── unclear + eligible create/reschedule
      │   → PassiveEscalation queued → private active-agent confirmation
      ├── waitlist_request
      │   → dashboard may fulfill it as a real WaitlistEntry
      └── unresolved/other operation
          → Detectados dashboard review or dismissal
```

The current explicit review API can create an appointment from a detected
create candidate and fulfill a `waitlist_request`; reschedule, cancel, and
recurrence candidates remain dismiss-only there unless they take one of the
safe automatic/private-confirmation paths. This distinction is important when
adding a new passive intent: an extractor schema change alone does not create
a review or execution contract.
