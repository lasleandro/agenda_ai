# Waitlist ("Fila de Espera") Roadmap v0.1 — 2026-08-09

**Status: planned, not started.** Design doc + phasing, written before implementation so the shape of the feature is agreed first.

## The idea

Today, when an instructor has no open slot for a customer, that demand is lost — remembered informally (or not at all) until the instructor happens to think of that customer again. This roadmap adds a **"Fila de Espera"**: a structured record of "this contact wants a slot at this specific time, and none exists yet," visible on both the Clientes and Agenda screens, and eventually operable through the AI agent (both active and passive modes).

Originally scoped as a future idea in [customer_ontology_places_roadmap_v0.1](customer_ontology_places_roadmap_v0.1_2026-08-05.md) ("waitlist for full group slots") and in `MEU_DIARIO.md` (2026-08-05: *"Pensar em construir uma tela de fila/demanda/clientes que querem entrar em algum horário que não tem liberado ainda"*). This doc broadens the original narrower idea (waitlist only for a specific full group slot) into a general demand queue: a desired time slot that may or may not correspond to an existing `RecurringSlot`.

## Naming — a collision to watch, not a blocker

`Contact.commercial_status` and `RecurringSlot.commercial_status` already use the value `"waiting"`, displayed in the UI as **"Em espera"** — a paused/inactive billing relationship (commercial/financial module, unrelated to scheduling demand). This feature is deliberately named **"Fila de Espera"** instead, per instructor decision, accepting the visual similarity to "Em espera" as a known risk rather than renaming the existing commercial status. Mitigate at UI-copy time: keep the two concepts in visually distinct places (Fila de Espera lives on Clientes/Agenda as its own filter/badge, not folded into the existing commercial-status chip), and never abbreviate "Fila de Espera" down to just "Espera" in labels.

## Scope decision — specific desired time only

A `WaitlistEntry` always has a concrete desired time (date/weekday + time range), not a vague "sometime this week" or "mornings only" request. This keeps matching a direct extension of the existing capacity-search logic (`find_instructor_openings`) instead of a new fuzzy-search engine, and keeps the Agenda-screen card rendering simple (one entry = one calendar card, using the same event mechanism as `Appointment`/`RecurringSlot`). If "any time" requests turn out to be common in practice, loosen this later — starting precise is the safer, smaller first cut.

## Data model

A new standalone table, not a repurposed field on `Contact` — a single contact can have more than one live request (e.g. wants a Tuesday evening slot *and* wants into a specific existing group), and each request has its own lifecycle independent of the contact's own record.

```python
class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id: UUID
    professional_id: UUID  # FK professionals.id, tenant scope
    contact_id: UUID       # FK contacts.id
    place_id: UUID | None  # FK places.id — nullable, "any place" is valid

    # Specific desired time (scope decision above) — mirrors how a one-off
    # Appointment or a scheduled_date RecurringSlot expresses a concrete
    # slot, not a recurrence rule.
    desired_date: date
    desired_start_time: time
    desired_end_time: time

    class_type: str | None  # "individual" | "group", nullable if either works
    duration_minutes: int   # defaults from Professional.default_duration_minutes

    status: str  # "open" | "matched" | "fulfilled" | "cancelled" | "expired"
    note: str | None  # free text, e.g. "prefere com a Ana", "só depois das 18h"

    matched_at: datetime | None
    fulfilled_appointment_id: UUID | None  # FK appointments.id, set on fulfil
    created_at: datetime
    updated_at: datetime
```

Status transitions: `open` → `matched` (a fitting opening was found and offered to the instructor) → `fulfilled` (booked — `fulfilled_appointment_id` set) or back to `open` (offer declined/expired without booking) → `cancelled` (instructor or contact no longer wants it) or `expired` (desired_date passed without being filled). This mirrors the existing `AppointmentCandidate`/`OperatorActionCandidate` pattern already used elsewhere in the codebase — a lightweight, purpose-built state machine rather than overloading an existing table's status field.

Tenant isolation follows the same pattern as every other ontology table: every query scoped by `professional_id`, sourced from the authenticated session/agent context, never from client input.

## Matching logic — reuse, don't rebuild

`app/agent/tools.py::find_instructor_openings` already computes exactly what's needed: open capacity for a place/date/period/duration, via `financial_capacity` (loads places, prime-time ranges, existing bookings) and `scheduling.subtract_ranges` (pure interval math). A waitlist matcher is this same computation, checked against each `open` `WaitlistEntry`'s desired date/time/place/duration instead of an ad-hoc query — no new interval-math engine required. This is the single highest-leverage reuse in this feature and should anchor the implementation, not be treated as an afterthought.

Two ways to trigger a match check, staged separately (see Phasing):
1. **On-demand** — instructor or agent explicitly asks "tem alguém na fila que caberia nesse horário?" or opens a "check waitlist" action.
2. **Event-driven** — when a cancellation frees a slot, automatically check open waitlist entries against the newly-freed time and surface a match. Higher value, higher complexity (needs a hook into the cancel flow — `agent/mutations.py::_execute_cancel_schedule` and the dashboard's own cancel endpoint both create the opening); staged last.

## Active agent (instructor ↔ agent) tools

Both WhatsApp and web chat share the same orchestrator (`agent/orchestrator.py`), so these tools work identically on both channels once built — no channel-specific code needed, per how the WhatsApp agent channel already shares the full tool set with web chat. Following the existing read-tool / `propose_*` split:

- `list_waitlist_entries` (read) — filterable by place/status/date range.
- `propose_add_waitlist_entry` (write, requires confirm) — "coloca a Marina na fila pra terça às 19h" — resolves the contact via the existing `entity_resolution` fuzzy-match pattern, never a guessed ID.
- `propose_remove_waitlist_entry` (write, requires confirm) — cancel an entry, or mark it fulfilled outside the normal booking flow (e.g. the contact found another instructor).
- `find_waitlist_matches` (read) — "tem vaga essa semana pra alguém da fila?" — runs the on-demand matcher above against all `open` entries for a date range.

All writes go through the existing `OperatorActionCandidate` propose → confirm → execute flow — nothing here needs new safety architecture, only new tool specs/dispatch entries in `tools.py`/`mutations.py`, matching the pattern every existing tool already follows.

## Passive agent (observing instructor ↔ customer chat)

Deferred, per instructor decision, to the phase that handles conversational-flow input generally — deliberately not part of the initial build. Design sketch for when that phase starts:

`SchedulingEvent.action` today is `create | confirm | reschedule | cancel | recurrence | none` — none fit "customer asked for a slot that doesn't exist yet." A new action value, e.g. `waitlist_request`, would be extracted when the conversation shows the instructor telling the customer something like *"no momento não tenho horário, te aviso quando abrir"* — same conservative "prefer uncertainty over a false positive" philosophy already governing the extraction prompt (`chat/prompt.py`). This would surface as a new reviewable candidate (parallel to `AppointmentCandidate`, sharing its evidence-linking pattern via `AppointmentEvidence`) that the instructor confirms via the dashboard — never auto-created, matching the passive observer's existing zero-autonomy design (`docs/ai_agent_modes.md`, Mode 2).

This piece is more speculative than the active-agent tools above — extraction quality for "no slot available" phrasing needs real conversation examples to tune before committing to a schema, which is the concrete reason to defer it rather than build it blind alongside Phase 1.

## Frontend

**Clientes screen.** A status filter (e.g. a chip/segmented control alongside the existing search box in `frontend/src/app/(protected)/clientes/page.tsx`, which already filters client-side by name/phone/place — a "Fila de Espera" filter slots into that same pattern) plus a small badge on the contact row for anyone with an `open` `WaitlistEntry`.

**Agenda screen.** A grey "ghost" calendar card at the desired time window, using the same `FullCalendar` `EventInput` mechanism `week-calendar.tsx` already uses for `RecurringSlot`/`Appointment` (see `slotToEvent`/`appointmentToEvent`) — a third event-mapping function, e.g. `waitlistEntryToEvent`, styled distinctly (grey, dashed border, or similar — distinct from every existing `STATUS_COLORS` entry so it reads unmistakably as "not a real booking"). Default hidden behind a toggle, off by default per instructor's original ask.

Since entries always have a specific desired time (scope decision above), this is a direct one-entry-to-one-card mapping — no "period band" shading needed, unlike what a fuzzier "anytime mornings" request would have required.

Worth deciding at implementation time, not blocking this roadmap: clicking the ghost card should probably jump straight into booking that contact into that slot (pre-filling `propose_create_appointment` or the dashboard's own create-appointment form with the contact/place/time already set), turning it from informational into actually useful. Flagging this now so it isn't an afterthought bolted on later.

## Input methods

Both a Clientes-screen form (direct instructor input) and agent/chat input are wanted long-term — decided explicitly, not deferred as a whole. Sequencing:

- The **form** can land as early as Phase 1, since it needs no LLM/agent work — a normal create-entry dialog on the Clientes screen, same shape as the existing `AddToGroupDialog`/`RecurringGroupDialog` patterns already in `frontend/src/components/ontology/`.
- The **active-agent tools** (`propose_add_waitlist_entry` etc.) are also Phase 1-appropriate — no reason to gate them behind the form.
- The **passive-observer extraction** path is explicitly deferred to the dedicated conversational-flow phase (see above) — not scheduled here.

## Phasing

**Phase 1 — Data model + active-agent tools + Clientes form + Clientes badge/filter — implemented 2026-08-09.**
`WaitlistEntry` table + migration (`app/models/waitlist_entry.py`); shared validation in `app/services/waitlist.py`; dashboard REST API (`app/api/waitlist.py` — list/create/cancel, cancel is a status transition not a row delete); active-agent tools `list_waitlist_entries` (`agent/tools.py`), `propose_add_waitlist_entry`/`propose_remove_waitlist_entry` (`agent/mutations.py`, full propose→confirm→execute cycle, same as every other mutation tool); two new `OperationalEvent` types (`waitlist.entry.added`, `waitlist.entry.cancelled`); orchestrator system-prompt guidance distinguishing Fila de Espera from the unrelated "Em espera" commercial status. Frontend: `AddToWaitlistDialog`, a "Fila de espera" filter chip + count badge, a status badge per contact row, and a toggling add/remove action button on the Clientes screen (`app/(protected)/clientes/page.tsx`). 12 new backend tests (service, API, agent tools) — full suite 125 passed. No matching logic yet — entries are purely recorded and manually reviewed, as scoped.

**Phase 2 — On-demand matching (`find_waitlist_matches`) — implemented 2026-08-09.**
Added `financial_capacity.compute_free_ranges_by_place()` — the "what's actually free" computation factored out of `find_instructor_openings` so both it and the new matcher share one implementation (refactored `find_instructor_openings` itself to call it too; behavior-preserving, existing tests still pass). `services/waitlist.py::find_matches()` groups open entries by desired date, computes free ranges once per date, and checks each entry's exact desired window against them — read-only, never mutates entry status. Agent tool `find_waitlist_matches` (`agent/tools.py`) exposes it ("tem vaga pra alguém da fila essa semana?"); no dashboard button yet (agent-only for now, consistent with keeping this phase minimal). 4 new tests.

**Phase 3 — Agenda ghost-card rendering + toggle + click-to-book — implemented 2026-08-09.**
Added `WaitlistEntry.status = "fulfilled"` transition (`services/waitlist.py::fulfill_entry`, `POST /api/waitlist-entries/{id}/fulfill`) — distinct from cancel, since clicking a ghost card to book it means the demand was met, not abandoned. Frontend: `waitlistEntryToEvent()` maps an entry to a grey, dashed-border `FullCalendar` event (`.agenda-waitlist-entry` in `globals.css`), included in the calendar only when a default-off "Fila de espera" toggle (with live count badge, same visual pattern as the Clientes screen's filter chip) is on. Clicking a ghost card opens the existing `AppointmentFormDialog` pre-filled with the entry's contact/place/time (new optional `initialContactId` prop); on successful booking, the entry is optimistically marked fulfilled and rolled back on failure, matching the codebase's existing optimistic-UI rollback pattern. 3 new backend tests for the fulfill transition.

**Phase 4 — Passive-observer extraction (`waitlist_request`) — implemented 2026-08-09, expanded in scope.**
Building this surfaced a pre-existing gap worth fixing first: `AppointmentCandidate` (what the passive observer has always produced) had **no real review UI** — its only consumer anywhere in the frontend was the dev-only `/dev/mock-chat` page (`api/conversations.py` is explicitly `"Developer-only... no UI polish"`). Extraction without somewhere for its output to go wouldn't have produced anything an instructor could act on, so this phase became two things:

1. **A real review surface for `AppointmentCandidate` generally.** New `status` lifecycle (`detected` → `dismissed`/`fulfilled`, CHECK-constrained) and a new production API, `app/api/appointment_candidates.py` (list/dismiss/fulfill-waitlist), replacing the dev-only dead end. `CandidateDetail` gained `contact_id`/`contact_name` (previously missing — a review list is useless without knowing who it's about). A new "Detectados" tab on the Clientes screen shows pending candidates with their evidence text and lets the instructor dismiss them.
2. **`waitlist_request` extraction**, scoped as originally planned: new `SchedulingEvent.action` value, prompt guidance (`chat/prompt.py`) for when the instructor tells a customer there's no slot and they'll follow up. Per the Phase 1 "specific time only" decision, if the customer gave a concrete desired time it's extracted into `start_at`/`end_at`; if not, the event still fires (with an ambiguity flag) rather than being dropped as `action="none"` — the instructor completes the missing time during review, not the model guessing it.

Deliberately **not** built: auto-execution for the other four action types (create/reschedule/cancel/recurrence) — those stay dismiss-only, since wiring real execution for passively-detected mutations is the separate, larger "Auto-Propose from Passive Observation" initiative your docs already flag as future work, not something to fold into this pass. Only `waitlist_request` got a real confirm action, because `services/waitlist.py` already existed to back it: clicking "Adicionar à fila de espera" on a detected candidate opens the same `AddToWaitlistDialog` used elsewhere, pre-filled with whatever was extracted, for the instructor to review/complete before it becomes a real `WaitlistEntry` — never auto-created, matching the passive observer's zero-autonomy design. 7 new backend tests.

**Phase 5 — Event-driven auto-matching — implemented 2026-08-09.**
Only one call site actually frees calendar capacity today: `agent/mutations.py::_execute_cancel_schedule` (via `schedule_overrides.cancel_occurrence`) — rescheduling was considered but left out, since the roadmap only scoped cancellation. `services/waitlist.py::mark_matches_for_date()` reuses `find_matches`, flips newly-matching `open` entries to `status="matched"` (leaves already-matched/fulfilled entries alone), and does **not** commit itself — it runs inside the same transaction `candidates.confirm()` already owns, matching `cancel_occurrence`'s own "callers own the transaction" convention. No new notification system was built (none existed to build on); instead the match is surfaced through the existing confirmation-summary text the instructor already sees on both web chat and WhatsApp ("Ocorrência cancelada. Marcelo estava na fila de espera e agora cabe nesse horário.") — reusing plumbing rather than inventing a new alert mechanism. Clientes/Agenda screens now fetch `open` + `matched` entries (previously `open` only) so a newly-matched entry doesn't silently vanish from view. 3 new tests, including a full propose→confirm end-to-end check that the summary text and status transition both happen correctly.

**All five phases of this roadmap are now implemented.**
