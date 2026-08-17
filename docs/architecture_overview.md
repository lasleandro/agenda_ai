# Tennis OS -- Platform Architecture Overview

**Version:** 0.1.0
**Last updated:** 2026-08-07

---

## 1. What is Tennis OS?

Tennis OS is an operational platform for tennis academies and independent
instructors. It combines a web dashboard for scheduling/management with an
AI assistant that understands natural language and can perform actions on
the instructor's behalf.

The platform serves two primary interaction modes:

- **Dashboard (Next.js SPA):** A visual calendar, client management,
  financial configuration, and revenue tracking interface.
- **AI Chat (WhatsApp + web UI):** An instructor can message the assistant
  ("remarca a aula da Mariana para quinta") and the assistant proposes
  validated, confirmable actions.

A third mode -- passive observation -- is architecturally prepared: the
system can observe an instructor-customer WhatsApp conversation and
auto-detect scheduling intent without either party addressing the AI
directly.

---

## 2. High-Level Architecture

```
+------------------------------------------------------------------+
|                        FRONTEND (Next.js)                         |
|  Port 3010  |  Dashboard SPA  |  Chat UI  |  Admin Panel          |
+------------------------------------------------------------------+
        |  REST API (JSON)           |  SSE / polling
        v                            v
+------------------------------------------------------------------+
|                    BACKEND (FastAPI, Port 8005)                    |
|                                                                    |
|  +-------------+  +------------+  +---------------------------+  |
|  | REST API    |  | AI Agent   |  | WhatsApp Webhook          |  |
|  | (13 files,  |  | Orchestr.  |  | (Cloud API / YCloud)      |  |
|  |  57 routes) |  |            |  |                           |  |
|  +-------------+  +------------+  +---------------------------+  |
|        |                |                     |                   |
|        v                v                     v                   |
|  +----------------------------------------------------------+   |
|  |                    SERVICE LAYER                           |   |
|  |  appointments | scheduling | financial_capacity           |   |
|  |  schedule_overrides | makeup_credits | makeup_recommender |   |
|  |  revenue_occurrences | contacts | participants            |   |
|  +----------------------------------------------------------+   |
|        |                                                        |
|        v                                                        |
|  +----------------------------------------------------------+   |
|  |               SQLAlchemy ORM (PostgreSQL)                  |   |
|  |               36 models, Alembic migrations                 |   |
|  +----------------------------------------------------------+   |
+------------------------------------------------------------------+
        |
        v
+------------------------------------------------------------------+
|                    PostgreSQL (Docker)                            |
|                    Database: agenda_db                            |
+------------------------------------------------------------------+
```

---

## 3. Technology Stack

| Layer | Technology |
|---|---|
| Backend framework | Python 3.11, FastAPI |
| ORM / DB | SQLAlchemy 2.0, PostgreSQL (Docker container) |
| Migrations | Alembic |
| AI / LLM | Azure OpenAI (never plain OpenAI/Claude — hard project constraint), via `AZURE_OPENAI_*` in `.env` |
| WhatsApp | Cloud API (production) / YCloud (local dev) |
| Frontend | Next.js 16 (not 15 — breaking changes from training data, see `frontend/AGENTS.md`), TypeScript, Tailwind CSS, shadcn/ui |
| Calendar widget | FullCalendar v6 |
| Auth | JWT in httpOnly cookies, bcrypt password hashing |
| Dev environment | Conda environment `agenda` |

---

## 4. Project Structure

```
agenda_ai/
  AGENTS.md              # AI coding assistant instructions
  README.md              # Project README
  requirements.txt       # Python dependencies (pinned)
  start_server.py        # Dev server launcher

  backend/
    alembic.ini          # Alembic config (points to .env)
    app/
      main.py            # FastAPI app entry point
      database.py        # SQLAlchemy engine + SessionLocal

      agent/             # AI Agent module
        __init__.py
        orchestrator.py  # LLM call + tool orchestration
        tools.py         # Read + write tool definitions (TOOL_SPECS)
        mutations.py     # Propose → confirm → execute lifecycle
        candidates.py    # OperatorActionCandidate CRUD
        entity_resolution.py  # Fuzzy contact/place matching
        temporal.py      # Date/time parsing from NL

      api/               # REST API route handlers
        auth.py          # Login, logout, impersonation
        admin.py         # Platform admin (tenant toggles)
        assistant.py     # Chat → agent interaction (web)
        appointment_candidates.py  # Passive-observer review (dismiss, reviewed appointment, waitlist)
        calendar.py      # Calendar query + appointment CRUD
        contacts.py      # Customer ontology
        conversations.py # Dev-only conversation viewer (list + detail, via Swagger) — also
                          # exports candidate_with_evidence(), reused by appointment_candidates.py
        places.py        # Locations
        recurring_slots.py  # Weekly schedule template
        financial.py     # Financial configuration
        financial_analytics.py  # Analytics endpoints
        instructor_events.py  # Non-class calendar entries (refereeing, workshops, clinics)
        revenue.py       # Revenue confirmation flow
        rules.py         # Operational rules — work journey, make-up cancellation notice window (ungated)
        waitlist.py      # Fila de Espera CRUD (list/create/cancel/fulfill)
        whatsapp.py      # Inbound webhook handler (routes to both the passive
                          # pipeline and the active agent channel by receiving number)
        dev_mock.py      # Dev-only mock WhatsApp conversation
        dependencies.py  # Shared auth depends

      chat/              # WhatsApp pipeline
        pipeline.py      # Message processing pipeline (passive observer)
        ingestion.py     # Inbound message parsing + dedup, routes to agent_channel
                          # first when the receiving number is Professional.agent_phone
        agent_channel.py # Active agent over WhatsApp — deterministic fast-path
                          # commands, sim/nao confirmation, full orchestrator for
                          # everything else (AI Agent Operations Roadmap v0.1)
        extraction.py    # Intent extraction from NL (passive observer)
        candidate_worker.py  # Background candidate processing and safe passive escalation delivery
        temporal.py      # Date/time NL extraction
        prompt.py        # LLM prompt templates
        scheduled_task_worker.py # Polls and delivers durable tenant task runs
        ycloud_provider.py   # Temporary compatibility imports for old callers

      integrations/
        whatsapp/           # Provider-neutral contracts, registry, and YCloud adapter

      core/
        security.py      # Password hashing, JWT creation/verify

      domain/            # Domain types and enums
      models/            # SQLAlchemy ORM models (36 models)
      schemas/           # Pydantic request/response schemas
      services/          # Business logic layer, including daily_agenda and scheduled_tasks
      repositories/      # (reserved for future data access patterns)
      observability/     # Logging/tracing (reserved)

    migrations/          # Alembic versions
    tests/               # pytest test suite

  frontend/
    src/
      app/               # Next.js App Router pages
        (protected)/     # Auth-gated dashboard pages
      components/        # Reusable UI components
        ui/              # shadcn/ui primitives
        calendar/        # Calendar-specific components
        financial/       # Financeiro-specific components
        ontology/        # Contacts & places components
        chat/            # Chat UI components
      lib/               # Shared utilities, types, API client

  infra/                 # Docker, deployment configs
  scripts/               # CLI tools (seed, calibrate, etc.)
  docs/                  # Documentation (you are here)
    ROADMAPS/            # Feature roadmaps
```

---

## 5. Core Architectural Patterns

### 5.1 Propose → Confirm → Execute (Action Lifecycle)

Every state-changing action the AI agent can perform follows a three-step
pattern designed for safety and auditability:

```
User says "remarca a aula da Mariana"
  → Agent proposes the action (creates OperatorActionCandidate, status=proposed)
  → User sees preview: "Reagendar aula da Mariana para 15/08 10:00, Quadra 1"
  → User confirms → _execute_* function runs in a single transaction
  → OperationalEvent recorded (immutable audit ledger)
```

Key principles:
- The agent NEVER executes mutations autonomously -- it only proposes.
- Validation happens twice: at propose time (fast-fail) and at execute time
  (re-validation inside the transaction, in case state changed).
- Every executed mutation records an `OperationalEvent` with `before_state`
  and `after_state` for full auditability.
- All of this happens in the `backend/app/agent/mutations.py` file.

### 5.2 Operational Event Ledger

The `operational_events` table is an append-only audit log inspired by
event sourcing. Every state change records:

- `event_type` -- a closed vocabulary of 25 event types (grows with new
  features — check `EVENT_TYPES` in `app/models/operational_event.py` for
  the current list rather than trusting this number)
  (e.g., `schedule.appointment.created`, `schedule.occurrence.cancelled`,
  `makeup_credit.granted`, `makeup_credit.redeemed`)
- `occurred_at` -- wall clock time of the event
- `actor_type` / `actor_id` -- who caused it (user or system)
- `source_channel` -- where it came from (dashboard, assistant, whatsapp)
- `before_state` / `after_state` -- JSONB snapshots of the changed entity
- `correlation_id` -- groups related events from one interaction

### 5.3 Tenant Isolation

Every table scoped to a tenant carries `professional_id`. The auth
dependency `require_professional_id` extracts it from the JWT and every
query filters by it. No endpoint can access another tenant's data.

### 5.4 Optimistic UI

The frontend follows an optimistic pattern: show the expected result
immediately, reconcile on server response, roll back on failure. This
applies to appointment creation, cancellations, reschedules, and contact
updates.

---

## 6. Key Modules

### Scheduling Engine (`app/services/scheduling.py`)

The scheduling module is the central projection engine. It takes recurring
classes + appointments + overrides and projects them onto a calendar grid;
place stays are a separate background context consumed by capacity and place
resolution:

- `list_schedule_occurrences(db, professional_id, date_from, date_to)` --
  expands recurring appointments into per-date occurrences, applies
  `ScheduleOccurrenceOverride` rows (cancellations, reschedules), returns
  a unified `ScheduleOccurrence` list ready for the calendar grid or the
  agent's tools. Weekly stays and recurring classes honor inclusive
  `valid_from`/`valid_until` bounds, falling back to `created_at` for legacy
  rows with no explicit start.

### Financial Capacity (`app/services/financial_capacity.py`)

Classifies open time into prime/regular segments and prices them using
the instructor's configured rates:

- `build_capacity_segments(...)` -- intersects work-journey intervals with
  active place-stay windows, splits the result at
  part-of-day/prime-time boundaries. This is the shared foundation behind
  both the Financeiro capacity dashboard and the make-up slot
  recommender -- see `docs/capacity_and_recommendations.md` for the full
  algorithm on both sides, verified against the shipped code.
- Work-journey time outside all stays remains generic `Sem local definido`
  financial capacity. Financeiro values it with the generic regular/prime
  matrix and tenant-global fallback, but concrete slot recommenders omit it
  until a place stay supplies a real venue.
- `find_instructor_openings(...)` (defined in `app/agent/tools.py`, built
  on top of this module) -- the agent read tool answering "when am I
  free?". Computed from `compute_free_calendar_ranges(...)` (Work Journey
  minus every booking), *not* from per-place capacity windows: those are a
  revenue-projection concept, and using them as the availability answer
  hides real calendar gaps at hours no place has configured. Each opening
  is annotated with the places whose window covers it, so a place can still
  be suggested -- but a missing window never removes an opening.
- `compute_free_ranges_by_place(...)` -- unbooked capacity per place,
  shared by that annotation, the Financeiro dashboard, and the waitlist
  matcher (`app/services/waitlist.py::find_matches`).
- `load_net_work_ranges(...)` -- a date's Work Journey (work minus breaks),
  used to tell "no journey configured for this weekday" apart from
  "journey fully booked" when there are no openings to report.

### Waitlist Matching (`app/services/waitlist.py`)

Fila de Espera ("waitlist") entries record a contact's demand for a
specific date/time slot that doesn't exist yet. `find_matches(...)` reuses
`compute_free_ranges_by_place` to check open entries against real
capacity, on demand (agent tool `find_waitlist_matches`) or automatically
right after a cancellation frees a slot (`mark_matches_for_date`, called
from `_execute_cancel_schedule` in the same transaction — see §5.1).
Surfaced through the existing confirmation-summary text, not a separate
notification system.

### Revenue Occurrences (`app/services/revenue_occurrences.py`)

Immutable snapshots of past schedule occurrences converted to financial
records. Once confirmed, revenue occurrences are read-only. Supports
per-participant billable/non-billable classification with reasons.

### Makeup Credits (`app/services/makeup_credits.py`, `makeup_recommender.py`)

`makeup_credits.py` tracks reposição (make-up class) credits earned when
a *recurring group student* cancels a class with sufficient notice, or
when a single group participant's absence is noted (without cancelling
the class for the rest of the group — see `propose_note_participant_absence`
vs. `propose_cancel_schedule` in the tool taxonomy doc). One-off
appointment cancellations never earn a credit. `expires_at` and the
`forfeited` status exist in the schema but nothing currently sets them —
credits don't expire and never auto-forfeit in this pass; they're simply
not granted once `MAX_OUTSTANDING_CREDITS` (10) is reached.
`makeup_recommender.py` is a separate module that ranks candidate
make-up slots by cost, historical occupancy, place preference, and level
match — see `docs/capacity_and_recommendations.md` for the exact scoring
formula (percentile ranks, weights, and the three flat bonuses),
verified against the shipped code.

---

## 7. Authentication & Authorization

- **JWT** in httpOnly, Secure, SameSite=Strict cookies.
- Two roles: `platform_admin` (cross-tenant) and `professional`
  (single-tenant).
- Platform admins can impersonate any tenant (audit-logged).
- Feature gating via `tenant_features` table (e.g., `commercial_financials`
  controls Financeiro visibility).

---

## 8. Deployment

The platform runs as two processes:

1. **FastAPI server** (`uvicorn app.main:app --port 8005`) -- API + agent
2. **Next.js dev server** (`npm run dev -- --port 3010`) -- dashboard SPA

In production, the Next.js app is built to static files and served
alongside the API behind nginx or similar.

PostgreSQL runs in a Docker container named `agenda_db`.

See `docs/local_dev_webhook_tunnel.md` for WhatsApp webhook testing setup.
