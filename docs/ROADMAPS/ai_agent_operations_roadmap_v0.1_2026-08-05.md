# AI Agent Operations Roadmap v0.1 — 2026-08-05

> **Superseded for future planning.** The canonical continuation is
> [Operational Ontology & AI Agent Roadmap v0.2](operational_ontology_and_agent_roadmap_v0.2_2026-08-05.md).
> This document remains as design provenance.

**Status: future work, not scheduled.** This is a design doc to think through the shape of the problem now, while the ontology is fresh, so later implementation doesn't have to rediscover these decisions.

## The idea

Today the instructor operates the platform through the web dashboard (Agenda, Meus Locais, Clientes). The ask here is a second interface: natural-language commands like

```
o aluno Fulano cancelou as aulas
agora estou com horário fixo no clube harmonia de segunda a sexta, das 8h às 12h
```

that the platform interprets and turns into real mutations — cancelling a `Contact`'s slots, creating `RecurringSlot` rows — without the instructor touching a form.

## Two interaction modes — not one

The platform has two structurally different agent-mediated interactions, and it's worth naming them explicitly because they have almost opposite trust models. Everything below is about mode 2; mode 1 is the existing PoC and is unchanged by this doc.

**Mode 1 — Instructor ↔ Customer, agent invisible.** The original PoC scope. The agent only *observes* (passively extracts scheduling events from a conversation it doesn't participate in) and *proposes* (an `AppointmentCandidate` the instructor confirms). It never speaks as the instructor and never speaks to the customer — it's a silent extraction layer over a human conversation it can't interrupt or clarify with. Low agent authority, high human-in-the-loop friction by design (brief §5.4 Trust).

**Mode 2 — Instructor ↔ Agent, agent visible and operated directly.** What this doc is about. The instructor knowingly talks to the platform itself — reads (`"quais alunos tenho hoje"`) or writes (`"o aluno Fulano cancelou as aulas"`). The agent is a first-class conversational partner, not an invisible extractor. Reads can answer immediately with no confirmation; writes go through confirm-before-apply, but the interaction shape is "instructor commands the system," not "system quietly watches a human conversation it isn't part of."

The split matters architecturally, not just conceptually:
- **Different channels** — Mode 1 rides the customer-facing WhatsApp number already wired; Mode 2 belongs on the separate assistant number the brief already reserved (§17, `ASSISTANT_WHATSAPP_NUMBER`), never the customer-facing one.
- **Different LLM tasks** — Mode 1 is extraction-from-observed-dialogue (infer intent from two other people talking); Mode 2 is tool-calling-from-direct-command (the instructor is talking *to* the agent).
- **Different ambiguity sources, different resolution options** — Mode 1's ambiguity comes from a third party's words the agent can't interrupt to clarify (hence conservative defaults, "prefer uncertainty over a false positive," and confidence-gated automation). Mode 2's ambiguity is the instructor's own shorthand, and — this is the key asymmetry — the agent *can* just ask the instructor directly ("qual Fulano, o das terças ou o das quintas?") instead of inferring silently. Mode 2 can afford to be more interactive precisely because there's no third party being talked over.

## Why this is tractable now, and wasn't before

This is a **direct payoff of the customer ontology work** ([roadmap](customer_ontology_places_roadmap_v0.1_2026-08-05.md)). Before that work, "cancel Fulano's classes" had nothing structured to resolve "Fulano" or "classes" against — `Contact` was a flat WhatsApp record. Now there's a `Place`/`RecurringSlot`/`RecurringSlotParticipant`/`Contact` graph with typed relationships an LLM tool call can target precisely instead of guessing at free text. This doc is really "how do we expose that ontology as an LLM-operable surface," not a new extraction problem.

It's also not a new *channel* concept — the original project brief already scoped a **"WhatsApp Assistant Channel"** ([project brief §17](../whatsapp_schedule_copilot_poc_project_brief_v0.1.md)): a private number the professional talks to, distinct from the number they use with customers, already reserved via `ASSISTANT_WHATSAPP_NUMBER` in `.env`. That doc explicitly listed only deterministic query commands (`hoje`, `amanha`, `esta semana`, `proxima aula`) and said outright: *"A general conversational assistant is outside the first scope."* This roadmap is that deferred scope, now made concrete.

## Architectural approach

**Tool-calling, not freeform generation.** The LLM should never generate SQL or freeform text describing a mutation — it should select from a small, fixed set of typed "operator tools" (Pydantic schemas, same `instructor` + Azure OpenAI + Langfuse stack already wired in [extraction.py](../../backend/app/services/extraction.py)/[prompt.py](../../backend/app/services/prompt.py)) and the backend executes exactly that tool with validated, resolved arguments. This bounds what an LLM mistake can do to "call the wrong known tool with wrong-but-typed arguments," never "do something unbounded." Sketch:

```python
CancelContactSlots(contact_name: str, scope: Literal["all_recurring", "next_occurrence_only"])
CreateRecurringSlot(place_name: str, days: list[Weekday], start_time: time, end_time: time)
UpdateContactLevel(contact_name: str, level: str)
QuerySchedule(range: Literal["today", "tomorrow", "this_week", "next_class"])
```

**Entity resolution is a first-class step, not an LLM guess.** "Fulano" and "clube harmonia" are strings the LLM extracts; resolving them to a `Contact.id`/`Place.id` is a deterministic backend lookup (fuzzy match on `normalized_name`) — mirrors `get_or_create_contact`'s existing normalized-name matching. Zero matches or multiple matches must produce a clarifying question back to the instructor, never a guess — this is the same philosophy already encoded in the extraction prompt ("Prefira incerteza a um falso positivo") and in `AppointmentCandidate.ambiguities`. Reuse that pattern rather than inventing a new one.

**Confirm before applying, always — mirror the existing `AppointmentCandidate` state machine.** The platform already has a proven propose → confirm → apply flow for customer-facing scheduling (candidate created, instructor gets a WhatsApp message with buttons, confirms, `Appointment` is written). Operator commands should work identically: an `OperatorActionCandidate` (tool + resolved arguments + a human-readable preview) is created, sent back to the instructor for confirmation, and only executed on explicit reply. This is not optional for anything destructive (cancelling a student, deleting a recurring commitment) — per CLAUDE.md's "confirm before destructive actions" and the brief's own §5.4 Trust principle. Even for low-risk writes, starting with confirmation and relaxing it later (once accuracy is proven) is the safer default than the reverse.

**Audit everything.** Every executed tool call — who (the professional, resolved from the assistant number the same way Phase A of the multi-tenancy roadmap resolves tenant), what tool, what arguments, what changed — gets logged. This is CLAUDE.md's audit/accountability rule, and it's what makes an eventual "the agent did something wrong" conversation debuggable instead of a mystery.

**Tenant scoping is free, not a new mechanism.** The assistant number is 1:1 with a `Professional`, resolved exactly like Phase A of the multi-tenancy roadmap resolves the customer-facing number — every tool call is automatically scoped to that professional's own data, no new isolation logic needed.

## Open design question worth resolving before building, not during

Your own example exposes a real ontology gap: *"horário fixo no clube harmonia de segunda a sexta, das 8h às 12h"* is a 4-hour block, Monday–Friday. Today's `RecurringSlot` models a single bounded lesson (one day, one time range, a `class_type`, a participant cap) — it's the right shape for "Tuesday 8–9am, group of 4," but not obviously the right shape for "I'm generally at this club all morning." Two honest options, not resolved here:

1. Treat it as literal — decompose into 5 `RecurringSlot` rows, one per weekday, each spanning 8h–12h, with no participants yet (an empty slot waiting to be filled). Simple, reuses the existing model as-is.
2. Introduce a separate "availability window" concept distinct from a bookable `RecurringSlot`, and let individual lesson slots be carved out of it later. More correct long-term, more to build.

Recommend deciding this by looking at how instructors actually talk about their schedules once you have a few real usage examples, rather than guessing now.

## Phases (staged by risk, not by calendar)

### Phase 0 — Channel + read-only queries — **implemented 2026-08-08**
Stand up the assistant WhatsApp number as its own ingestion path (same tenant-resolution pattern as the customer channel, different message handling). Implement exactly the brief's original scope: `hoje`, `amanha`, `esta semana`, `proxima aula` as deterministic queries against `Appointment`. Zero mutation risk — this phase is about proving the channel and tenant-resolution plumbing work, and giving the instructor a reason to use the number at all before asking them to trust it with writes.

Implementation: `Professional.agent_phone` (new column, separate from `assistant_phone`), `app/chat/agent_channel.py` (command matching + reply formatting), `ycloud_provider.send_text_message()` (outbound YCloud send, didn't exist before this phase), routed from `chat/ingestion.py:ingest_event` before it reaches the passive-observer pipeline. Env: `YCLOUD_AGENT_CHANNEL_ID`, `AGENT_WHATSAPP_NUMBER` (renamed from `ASSISTANT_WHATSAPP_NUMBER` for clarity against `assistant_phone`'s existing, unrelated meaning).

### Phases 1–2 — full tool parity — **implemented 2026-08-08, ahead of the original narrow scope**
When this got built, the full mutation tool set (`app/agent/mutations.py`) already existed for the web chat (Phases 4–5 of the operational ontology roadmap, done earlier) — every mutation already goes through the same propose → confirm → execute gate regardless of caller. That made the originally-planned narrow tool subset (just `UpdateContactLevel` + participant add/remove) mostly moot: the gate is what bounds risk, not the tool list. Decision (confirmed with the instructor before building): give WhatsApp the same full tool set as web chat rather than forking a restricted list to revisit later.

What changed: `run_agent_turn()` and every `propose_*` tool in `mutations.py` now accept a `channel` parameter (default `"web"`), threaded through so `OperatorActionCandidate.channel` — and therefore `operational_events.source_channel` — correctly reflects `"whatsapp"` for agent-channel proposals, not just for confirm/execute (which already read `candidate.channel`). `app/chat/agent_channel.py` resolves the professional's own `User` row as `actor_user_id` (no login session exists over WhatsApp) and calls `run_agent_turn(..., channel="whatsapp")` for any message that isn't a Phase 0 command.

Confirmation UX (also confirmed with the instructor): reply keywords, not YCloud interactive buttons — `sim`/`confirmar`/`confirmo`/`confirma`/`ok` to confirm, `nao`/`cancelar`/`cancela`/`cancelo` to reject, resolved against the professional's most recent `status="proposed"` candidate on `channel="whatsapp"`. Simpler than interactive buttons and matches natural WhatsApp usage; revisit if ambiguity in practice (e.g. two pending proposals) turns out to be a real problem.

### Phase 3 — Multi-turn conversation state — **implemented 2026-08-08**
New `AgentChannelMessage` table (professional_id, role, content, created_at) — a lightweight per-professional turn log, deliberately not a reuse of the customer-facing `Message`/`Conversation`/`PendingProcessing` machinery, per this doc's own earlier note that the interaction shape differs (synchronous back-and-forth vs. buffered batch extraction).

`agent_channel._load_history()` replays the windowed history (same `AssistantSettings.memory_window_messages` knob the web chat uses) as the `messages` argument to `run_agent_turn`; `agent_channel._record_turn()` persists both the instructor's message and the agent's reply after every non-Phase-0 exchange (both free-text agent turns and sim/nao confirmation replies). Phase 0 deterministic commands are deliberately not recorded — they stay a separate fast lane outside the LLM conversation, keeping context focused on the actual back-and-forth. No explicit session reset exists; history is simply windowed, matching how the web chat already behaves.

### Phase 4 — Web chat as a second entry point
Already true as a side effect of Phases 1–2 above: the same orchestrator, tools, and `OperatorActionCandidate` state machine serve both channels today, `channel` merely tags which one originated a given proposal. Nothing further needed here.

**All phases of this roadmap are now implemented.** Remaining known gaps: no WhatsApp-native session reset/timeout for stale conversation history, and no interactive-button confirmation (reply-keyword only, per the confirmed decision above) — neither blocks real usage, both are candidates for a future pass based on actual usage patterns.

### Phase 1 — Low-risk single-entity writes, always confirmed
`UpdateContactLevel`, add/remove a `RecurringSlotParticipant` for an already-existing slot. Small blast radius if wrong (easy to undo), good place to prove out the tool-calling + entity-resolution + confirmation loop end to end.

### Phase 2 — Structural writes
`CreateRecurringSlot` (resolving or creating a `Place`), `CancelContactSlots`. This is where the availability-window question above needs to be settled, and where clarifying-question UX (ambiguous name matches, ambiguous scope — "all their classes or just this week's?") needs to be solid, not best-effort.

### Phase 3 — Multi-turn conversation state
Everything above assumes single command → single confirmation. Real usage will produce follow-ups ("na verdade era terça, não segunda") and corrections mid-flow. Needs a lightweight per-professional conversation state (pending clarification / pending confirmation) — likely a new lightweight model, not a reuse of the customer-facing debounce/`PendingProcessing` machinery, since the interaction shape is different (synchronous back-and-forth vs. buffered batch extraction).

### Phase 4 — Web chat as a second entry point (optional)
Everything above is channel-agnostic at the tool-calling layer — the same `OperatorActionCandidate` flow could be driven from a chat panel in the dashboard instead of (or alongside) WhatsApp. Worth doing once the WhatsApp path is proven, not before — two channels to validate simultaneously would slow down getting the core loop right.

## What this deliberately does not do

Per the original brief's excluded scope (§6.2) — still holds here — this is an operator/back-office command surface for the *instructor*, not "an AI agent that negotiates directly with students." Customers still go through the existing passive extraction pipeline. No RAG, no vector DB, no multi-agent orchestration — a fixed small tool set with deterministic entity resolution is enough for this problem and keeps behavior auditable, matching the brief's explicit exclusions.

## Open questions for you (when this becomes real)

1. WhatsApp-only, or do you also want the web-chat entry point (Phase 4) in the first real build?
2. On the availability-window question above — once you have a handful of real instructor phrasings, which of the two options (or a third) fits better?
3. How much confirmation friction is acceptable? Every single action confirmed is safest but chattier; you may want "batch" confirmations for multi-part commands (e.g. the 5-day example above as one confirmation, not five).
