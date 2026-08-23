# Ontology & Chat Architecture

---

## 1. Conceptual Overview

The platform operates on a **customer ontology** -- a structured
representation of the instructor's world:

```
Instructor
  |-- Contacts (alunos/clientes)  ──  level, address, home place, financial settings
  |-- Places (quadras / locais) ──  name, address, coordinates
  |-- Groups (turmas / slots recorrentes)  ──  participants, schedule, place
  |-- Appointments (aulas / compromissos)  ──  student, place, service, time
  |-- Financial rates  ──  per-place, per-participant-count, prime vs regular
```

The AI assistant can **read** this ontology (search contacts, places,
groups, check the schedule, find open slots) and **propose mutations**
(create appointments, cancel, reschedule, add participants, grant/redeem
makeup credits). Both modes are exposed as OpenAI function-calling tools.

---

## 2. Chat Pipeline (WhatsApp → Agent)

### 2.1 High-Level Flow

```
WhatsApp message arrives
  → POST /webhooks/whatsapp (whatsapp.py)
  → chat/ingestion.py: deduplicate message, upsert Conversation + Message
  → chat/pipeline.py: schedule_processing() sets debounce timer

Debounce timer fires (30s after last message):
  → chat/pipeline.py: build_conversation_window()
    collects last 20 messages + contact context + upcoming appointments
  → chat/extraction.py: extract_scheduling_events()
    LLM (Instructor + Azure OpenAI) extracts structured SchedulingEvents
    with date/time slots, contact names, action intent
  → chat/temporal.py: validate_temporal()
    calls tools.resolve_date_phrase for every date expression
    returns validated events with concrete timestamps
  → chat/pipeline.py: persists AppointmentCandidate + AppointmentEvidence

AppointmentCandidate is created (status=detected):
  → candidate_worker.py: process_due_conversations() polls
    pending_processing (FOR UPDATE SKIP LOCKED) and calls
    chat/pipeline.py: process_conversation() for each due conversation
  → The shared place-stay resolver permits automatic creation only for an
    authoritative create with one covering stay. An unclear, fully resolved
    candidate can create a private OperatorActionCandidate confirmation.
    Uncovered or ambiguous candidates remain in Detectados for explicit
    location review; see docs/ai_agent_modes.md.
```

### 2.2 Key Design Decisions

- **Debouncing:** Messages are not processed one-by-one. A 30-second
  debounce window waits after the last message before extracting intent,
  so "remarca" followed by "na quinta as 15h" 5 seconds later is processed
  as a single window.
- **Fingerprint dedup:** Each candidate carries an `event_fingerprint`
  (SHA-256 of normalized date+contact+action), preventing duplicate
  candidates from the same conversation window.
- **Evidence linking:** Each candidate links back to the exact messages
  that support it via `AppointmentEvidence`, enabling traceability from
  action back to the conversation that triggered it.

---

## 3. AI Agent Tool Taxonomy

The agent has access to a set of tools split into two categories. This
taxonomy is defined in `backend/app/agent/tools.py` (read tools) and
`backend/app/agent/mutations.py` (write tools).

### 3.1 Read Tools (tools.py)

Read tools execute immediately and return data. They never change state.
Every ID-typed parameter below (`contact_id`, `place_id`,
`recurring_slot_id`, `credit_id`, ...) must be a real UUID the model
already resolved via a search/list tool earlier in the same turn — no
tool in this codebase accepts a raw name directly; that's a hard,
repeatedly-enforced design rule (see §4's behavioral rules), not a
convention this table can afford to gloss over.

| Tool | What it does |
|---|---|
| `search_contacts(query, place_id?)` | Fuzzy-match (pg_trgm + substring) contacts by name/alias. Returns contact_id, display_name, phone, level, home_place_id |
| `search_places(query)` | Fuzzy-match places by name/alias |
| `find_groups(member_contact_id?, place_id?, weekday?)` | List recurring class groups, optionally filtered by member, place, or weekday (0=Monday..6=Sunday) |
| `get_schedule(date_from, date_to)` | Appointments + recurring-class occurrences in an explicit date range (max 31 days), each with `is_past`/`class_type`/`billing_type` |
| `get_next_session(contact_id)` | This contact's next scheduled occurrence, searching up to 90 days ahead |
| `resolve_date_phrase(phrase)` | Resolve a Portuguese relative-date phrase ("amanha," "terca que vem," "sabado de manha") into a concrete ISO date and, if present, a period-of-day time window |
| `find_instructor_openings(date, period?, duration_minutes?, place_id?)` | The instructor's genuinely free windows on a date: declared Work Journey minus every booking. Each opening carries a `places` list (which places' recurring availability covers it — may be empty without making the window any less free); see §4 |
| `find_group_openings(date_from, date_to, place_id?, ...)` | Joinable dated group occurrences with effective participants, capacity, and remaining seats. They are class commitments, never free time. |
| `recommend_makeup_slots(contact_id)` | Ranks open slots for a contact's make-up credits by cost + historical occupancy. Empty if the contact has no available credits |
| `list_makeup_credits(contact_id)` | Lists a contact's *available* credits with their real `credit_id`s — the only way to discover a `credit_id`; must be called before `propose_redeem_makeup_credit` |
| `list_waitlist_entries(status?, place_id?, contact_id?)` | List Fila de Espera entries — contacts who want a slot at a specific date/time that doesn't exist yet |
| `find_waitlist_matches(date_from?, date_to?)` | Check open waitlist entries against current capacity (reuses `find_instructor_openings`'s free-range computation) and report which now have a fitting opening. Read-only — never books anything |
| `list_events(date_from?, date_to?)` | List `InstructorEvent` rows (tournament refereeing, workshops, clinics — non-class paid work, no client) in an optional date range |

There is no `find_students_by_group`, `get_contact_credits`, or
`get_contact_detail` tool — group membership comes back as part of
`find_groups`'s result, and a contact's full profile is a dashboard
concern (`GET /api/contacts/{id}`), not something the agent looks up.

### 3.2 Mutation Tools (mutations.py)

Mutation tools **never write directly**. They create an
`OperatorActionCandidate` in `proposed` status and return a
`requires_confirmation` result. The orchestrator then stops calling tools
and presents the candidate's deterministic preview to the user.

| Tool | Purpose | Executor |
|---|---|---|
| `propose_create_appointment(contact_id, place_id, start_at, end_at, service, billing_type?)` | Create a one-off booking (`billing_type="courtesy"` for a free/trial class) | `_execute_create_appointment` |
| `propose_cancel_schedule(target_type, target_id, occurrence_date)` | Cancel a single occurrence ENTIRELY — nobody has class that day | `_execute_cancel_schedule` |
| `propose_note_participant_absence(contact_id, recurring_slot_id, occurrence_date)` | Record that ONE group-class participant will miss a dated occurrence — the class still runs for everyone else. May grant that participant a make-up credit; never touches the occurrence itself | `_execute_note_participant_absence` |
| `propose_reschedule_occurrence(target_type, target_id, occurrence_date, new_start_at, new_end_at, new_place_id?)` | Reschedule a single occurrence | `_execute_reschedule_occurrence` |
| `propose_add_appointment_participant(contact_id, appointment_id)` | Add a student to a one-off appointment, turning it into a group session | `_execute_add_appointment_participant` |
| `propose_remove_appointment_participant(contact_id, appointment_id)` | Remove an added (non-primary) participant from a one-off appointment | `_execute_remove_appointment_participant` |
| `propose_add_group_member(contact_id, recurring_slot_id)` | Enroll a student in a recurring class group | `_execute_add_group_member` |
| `propose_remove_group_member(contact_id, recurring_slot_id)` | Remove a student from a recurring class group's roster | `_execute_remove_group_member` |
| `propose_create_group_slot(...)` | Create an empty or seeded one-off/weekly group class after confirmation | `_execute_create_group_slot` |
| `propose_set_appointment_format(...)` / `propose_set_occurrence_class_format(...)` | Explicitly open a class as group with a capacity and named series/occurrence scope | format executor |
| `propose_add_group_occurrence_participant(contact_id, recurring_slot_id, occurrence_date)` | Add a one-date guest without changing standing membership | occurrence participant executor |
| `propose_update_contact(contact_id, changes)` | Update allow-listed contact fields (level, address, home place, ...) | `_execute_update_contact` |
| `propose_redeem_makeup_credit(credit_id, place_id, start_at, end_at)` | Book a make-up class from a real `credit_id` (see `list_makeup_credits`), consuming it in the same transaction | `_execute_redeem_makeup_credit` |
| `propose_add_waitlist_entry(contact_id, desired_date, desired_start_time, desired_end_time, place_id?, class_type?, duration_minutes?, note?)` | Add a contact to the Fila de Espera for a specific desired slot | `_execute_add_waitlist_entry` |
| `propose_remove_waitlist_entry(waitlist_entry_id)` | Cancel a waitlist entry — use `list_waitlist_entries` first, never guess the ID | `_execute_remove_waitlist_entry` |
| `propose_create_event(event_type, start_at, end_at, place_id?, title?, income_cents?, note?)` | Create an `InstructorEvent` — refereeing a tournament, running a workshop or clinic. Use instead of `propose_create_appointment` whenever there's no client involved | `_execute_create_event` |

`target_type` above is always `"appointment"` or `"recurring_slot"`.
Each executor re-validates inside a single SQL transaction, uses the same
service functions as HTTP endpoints, and records an `OperationalEvent`.

**Cancel vs. absence, a common mistake:** `propose_cancel_schedule` on a
`recurring_slot` cancels the occurrence for *every* enrolled participant
and grants each of them a credit (correct when the class itself doesn't
happen — rain, holiday). If only one student can't make it, use
`propose_note_participant_absence` instead — using
`propose_cancel_schedule` there would incorrectly grant credits to
students who never asked to skip.

---

## 4. Agent Orchestration Loop

Defined in `orchestrator.py`, the loop works as follows:

```
1. Build system prompt with current datetime, timezone, and behavioral rules
2. Send conversation history + tool definitions to Azure OpenAI (native
   function-calling wire format, manual tool-call loop — not the
   `instructor` library's structured mode used for extraction)
3. If model returns text → that's the reply (stop)
4. If model returns a tool call:
   a. If it's a READ tool → execute immediately, append result to history, go to step 2
   b. If it's a MUTATION tool → call the propose_* function, which:
      - Runs pre-validation
      - Creates OperatorActionCandidate (status=proposed)
      - Returns requires_confirmation with preview_text
   c. Force one final text completion so the model phrases the confirmation
   d. Return the reply + pending_candidate (stop — max 6 tool iterations)
```

Key behavioral rules from the system prompt:

- The agent never invents data not returned by a tool.
- For relative dates ("hoje," "amanha"), always call `resolve_date_phrase`.
- When search returns zero or more than one match, ask for clarification.
- `find_instructor_openings` is only for open-ended availability queries;
  for direct booking at a specific time, use `propose_create_appointment`
  directly.
- An opening whose `places` list is empty is still a free window — the
  agent must list it and ask which place to use, never report it as "no
  availability". When `openings` comes back empty the result carries a
  `note` saying *why* (no Work Journey configured for that weekday vs. the
  day being fully booked); the agent relays that reason.
- Always mention the place (quadra) when presenting results.

---

## 5. Entity Resolution

The `entity_resolution.py` module provides fuzzy matching for contacts,
places, and groups:

- **Normalized alias matching:** Contact names, place names, and group
  names each have a `normalized_name` column (ASCII-folded, lowercased,
  trimmed) plus optional `EntityAlias` rows for nicknames and variants.
- **Scoring:** Matches are scored by whether the query exactly matches a
  normalized alias, partially matches, or matches with edit distance.
- **Place filtering:** `search_contacts` accepts an optional `place_id` to
  narrow results to students associated with a specific location.

This allows the agent to resolve "Marizinha" → `Maria Silva` and
"quadra 2 coberta" → `Quadra 2 (Coberta)` without the instructor needing
to use exact names.

---

## 6. Temporal Resolution

The `temporal.py` module resolves Portuguese date/time expressions:

| Expression | Resolved |
|---|---|
| "hoje" | Current date |
| "amanha" | Tomorrow |
| "depois de amanha" | Day after tomorrow |
| "terca que vem" | Next Tuesday |
| "segunda da semana que vem" | Monday of next week |
| "de manha" | Time resolution = morning (08:00-12:00) |
| "de tarde" | Time resolution = afternoon (12:00-18:00) |
| "de noite" | Time resolution = evening (18:00+) |
| "sabado de manha" | Saturday morning |

The `resolve_date_phrase` tool is called by the agent for every date
expression in user messages, ensuring timezone-aware, deterministic
resolution rather than relying on the LLM's date arithmetic.

---

## 7. Dual Interaction Paths

The chat architecture supports two distinct interaction paths:

### 7.1 Direct Instructor → Agent (Active)

```
Instructor opens chat (web UI or WhatsApp) and talks TO the agent:
  "remarca a aula da Mariana para quinta as 15h"

  → Agent processes, proposes, instructor confirms
```

This is the **active agent** path. The instructor explicitly addresses the
AI assistant.

### 7.2 Instructor → Customer Conversation (Passive Observer)

```
Customer messages instructor on WhatsApp:
  "Professor, posso trocar minha aula de terça para quinta?"

  Instructor replies directly to customer.
  → Extraction pipeline observes the conversation passively.
  → AppointmentCandidate is created (status=pending).
  → Instructor sees a "detected" suggestion in the dashboard.
```

This is the **passive observer** path. The extraction pipeline analyzes the
conversation between instructor and customer without being addressed. It
detects scheduling intent and surfaces candidates for review. It can act only
within the place-resolution guardrails described above.

---

## 8. Candidate Processing Pipeline

```
candidate_worker.py: process_due_conversations() polls pending_processing
  → chat/pipeline.py: process_conversation()
     - build_conversation_window() + extract_scheduling_events() + validate_temporal()
     - Persists one AppointmentCandidate per distinct extracted event
       (deduplicated by event_fingerprint), confidence and ambiguities
       stored as-is
  → Resolves place context from covering stays, then either autoexecutes a
    safe authoritative create, sends a private confirmation, or keeps the
    candidate in dashboard review
```

Confidence alone never bypasses location and confirmation guardrails.

The `Ambiguities` JSONB field captures unclear elements (e.g., "which
Thursday?" or "which student named Maria?"), which the system surfaces
for the instructor to resolve.

---

## 9. LLM Integration

- **Model:** GPT-4o via Azure OpenAI
- **Extraction:** `instructor` library enforces `SchedulingEvent` Pydantic
  schema for structured output from conversations
- **Agent:** Native OpenAI function-calling with manual tool-call loop
  (not instructor's structured mode)
- **Memory window:** Configurable via `AssistantSettings.memory_window_messages`
  (default: last N messages of the conversation sent as context)
- **Temperature:** Configurable via `AssistantSettings.temperature`
- **Tracing:** Langfuse integration for extraction calls when credentials
  are configured
