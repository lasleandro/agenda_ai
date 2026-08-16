# AI Agent Modes

The platform defines two distinct AI interaction modes, each with different
autonomy levels, tools, and user interfaces.

---

## Mode 1: Instructor Agent (Active / Direct)

```
Instructor → talks TO the AI assistant → Assistant proposes, instructor confirms → Action executed
```

### Overview

The instructor interacts directly with the AI assistant via the
**web chat UI** (the floating panel — see `docs/pages/chat.md`) and via a
**dedicated WhatsApp agent number** (`Professional.agent_phone`, distinct
from the customer-facing `assistant_phone` — see `app/chat/agent_channel.py`).
Both channels now share the same tool-calling orchestrator
(`app/agent/orchestrator.py`) and the same propose → confirm → execute
safety model — full tool parity, not a restricted subset.

WhatsApp-specific behavior:
- Four deterministic commands (`hoje`, `amanha`, `esta semana`, `proxima
  aula`) are answered directly against `Appointment`, no LLM call — kept
  as a fast path since they're the most common asks.
- Anything else is sent to `run_agent_turn(..., channel="whatsapp")`,
  same as the web chat, tagging any resulting `OperatorActionCandidate`
  with `channel="whatsapp"` for correct audit attribution
  (`app/services/operational_events.py`).
- WhatsApp has no buttons, so confirmation is reply-keyword based: a
  proposal's preview text is appended with "responda *sim* para confirmar
  ou *nao* para cancelar"; a following `sim`/`confirmar`/etc. or
  `nao`/`cancelar`/etc. reply resolves the professional's most recent
  `proposed` candidate on the `whatsapp` channel.
- Conversation history persists across separate WhatsApp messages via
  `AgentChannelMessage`, windowed by message count the same way as the web
  chat (`AssistantSettings.memory_window_messages`) and additionally by age
  (`HISTORY_MAX_AGE`, 12h, since this history — unlike the web chat's — is
  persisted server-side and would otherwise replay stale relative dates)
  — follow-ups and corrections ("não, era terça") have the prior turn as
  context. Deterministic Phase 0 commands are not recorded into this
  history.
- The actor for WhatsApp-originated mutations is resolved as the
  `professional`-role `User` row owning the tenant (no login session
  exists over WhatsApp) — see `agent_channel._resolve_actor_user`.
- The agent number is private to the instructor: an inbound message is
  only processed if its sender (`from_phone`) matches
  `Professional.assistant_phone` — the instructor's own known number
  (the same phone that runs the customer-facing side). Messages from any
  other sender are silently dropped (no reply), so an unauthorized sender
  can't even confirm the number is live. Fails closed if
  `assistant_phone` isn't configured.

Don't confuse either of these with the *passive observer* (Mode 2 below),
which runs over the customer-facing number and never talks back or
proposes anything.

The assistant has full access to the instructor's ontology (contacts,
places, schedule, financial configuration) and can both answer questions
and propose actions.

### Capabilities

- **Read:** Search contacts/places/groups, view schedule, check availability,
  recommend makeup slots, resolve dates
- **Propose mutations:** Create appointments, cancel, reschedule, add
  participants, enroll in groups, redeem makeup credits, update contacts

### Safety Model

The agent NEVER executes mutations autonomously. Every write action follows:

```
propose → show deterministic preview → user confirms → execute in transaction → audit event
```

See `docs/ontology_chat_architecture.md` for the full tool taxonomy and
orchestration loop.

### User Experience

In the chat UI, when the agent proposes an action, the user sees:
- The agent's natural-language explanation
- A **structured preview card** showing exactly what will happen
- **Confirm** and **Reject** buttons (web chat only — see the WhatsApp
  caveat above; there's no equivalent WhatsApp confirmation UI today)

Confirming triggers `POST /api/assistant/candidates/{id}/confirm`, which
runs the executor in a single transaction and returns the result.

---

## Mode 2: Passive Observer (Watch & Surface)

```
Customer → messages the instructor → Extraction observes → Candidate surfaced → Instructor confirms or dismisses
```

### Overview

This mode does **not** involve the instructor talking to the AI. Instead,
the system observes the natural conversation between the instructor and
their customer on WhatsApp and detects scheduling intent automatically.

### How It Works

1. A WhatsApp message arrives from a customer (not the assistant number).
2. The ingestion pipeline (`chat/ingestion.py`) stores it in the
   conversation.
3. After a 30-second debounce, the extraction pipeline
   (`chat/extraction.py`) analyzes the conversation window via Azure
   OpenAI, using the `instructor` library to enforce a `SchedulingEvent`
   Pydantic schema for structured output.
4. The extraction identifies potential scheduling events: dates, contacts,
   actions (create/reschedule/cancel).
5. Temporal validation (`chat/temporal.py`) resolves date expressions
   against the instructor's timezone.
6. An `AppointmentCandidate` is created with status `detected`, linked to
   the supporting messages via `AppointmentEvidence`.
7. The candidate resolves its location only when exactly one place stay covers
   the full interval. A customer's home place can break a tie between valid
   stays, but never proves availability.
8. An authoritative, fully resolved create can be recorded automatically;
   an unclear but resolved create/reschedule is sent to the instructor's
   private agent for confirmation. Missing or ambiguous place context remains
   in Detectados for explicit review.

### Autonomy Level

The passive observer has deliberately bounded autonomy:

- It autoexecutes only authoritative creates with a reproducible covering
  place stay and revalidates before writing.
- It may create a private `OperatorActionCandidate` confirmation for unclear,
  fully resolved requests.
- It never autoexecutes a candidate with no covering stay or multiple matching
  stays. Those candidates require an instructor-selected place in Detectados.
- It never sends messages to customers.

### Technical Distinction

| | Active Agent | Passive Observer |
|---|---|---|
| Trigger | Instructor messages assistant | Customer messages instructor |
| LLM Call | Agent orchestrator (manual tool loop) | Instructor structured extraction |
| Output | Agent reply + PendingCandidate (proposed) | AppointmentCandidate (detected), optionally a private confirmation |
| Write access | Can propose mutations (requires confirm) | Limited to authoritative, uniquely place-resolved creates |
| UI surface | Chat UI + confirmation cards | Dashboard notification / candidate list |

---

## How They Complement Each Other

The two modes are designed to work together in a typical day:

1. **Passive observer** catches scheduling intent that happens organically
   in instructor-customer chats. The instructor doesn't need to remember to
   tell the assistant -- the system already detected it.

2. **Active agent** handles explicit requests: the instructor can ask
   questions ("quem tenho amanha?"), look up information, and initiate
   actions directly.

3. **They converge only for safe passive escalations.** A passive candidate
can create a private `OperatorActionCandidate` after full resolution, while
manual Detectados review remains the path for place ambiguity and explicit
exceptions.

---

## Guardrail: Place Review

Candidates missing only location context transition to
`needs_place_review` and do not poll the delivery worker. A change to place
stays reevaluates them and requeues only those that now resolve uniquely.
