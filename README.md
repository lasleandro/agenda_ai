# Tennis OS — WhatsApp Schedule Copilot

A passive WhatsApp Business copilot that converts conversations between independent professionals and their customers into an auditable, automatically maintained schedule. Initial vertical: independent tennis instructors in Brazil.

## Documentation

### Platform Architecture

- [Architecture overview](docs/architecture_overview.md) — high-level system design, technology stack, project structure, and core architectural patterns (propose-confirm-execute lifecycle, event ledger, tenant isolation).
- [Data architecture](docs/data_architecture.md) — complete data model with Mermaid ERDs for all 33 database tables grouped by domain (identity, contacts, scheduling, financial, audit).
- [Capacity evaluation & make-up slot recommender](docs/capacity_and_recommendations.md) — the financial dashboard's occupancy/what-if math and the make-up-credit slot recommender's scoring algorithm, verified against the shipped code (not the pre-implementation plan).
- [Ontology & chat architecture](docs/ontology_chat_architecture.md) — how the AI agent reads and writes the instructor's ontology, the WhatsApp → extraction → agent pipeline, tool taxonomy (read + mutation tools), entity resolution, and temporal resolution.
- [AI agent modes](docs/ai_agent_modes.md) — distinction between the active instructor agent (direct chat → propose → confirm → execute) and the passive observer (detects scheduling intent in instructor-customer WhatsApp conversations without being addressed).
- [Business rules](docs/business_rules.md) — catalog of all encoded business rules: scheduling constraints, makeup credit lifecycle, revenue rules, multi-tenancy, agent guardrails, data integrity, and WhatsApp pipeline rules.
- [Google Cloud Run & Cloud SQL deployment assessment](docs/google_cloud_run_cloud_sql_deployment_assessment.md) — current production-readiness assessment, target architecture, Cloud SQL design, security controls, and staged delivery plan.

### Page Documentation

- [Agenda (Calendar)](docs/pages/agenda.md) — primary scheduling interface with FullCalendar week view, appointment creation, group management.
- [Clientes (Contacts)](docs/pages/clientes.md) — customer list with search/groups, and detail page with level, address, courtesy appointments, fixed slots.
- [Financeiro (Financial)](docs/pages/financeiro.md) — financial dashboard with revenue projections, rate configuration, what-if scenarios, and revenue occurrence confirmation.
- [Minhas Regras (Operational Rules)](docs/pages/minhas_regras.md) — work journey and make-up cancellation notice window, ungated by the commercial_financials feature flag.
- [Chat / AI Assistant](docs/pages/chat.md) — floating chat panel accessible from every page, with tool call transparency and action confirmation.

### Roadmaps & Guides

- [Project brief](docs/whatsapp_schedule_copilot_poc_project_brief_v0.1.md) — product thesis, architecture, domain model, and design principles. Source of truth for *why* decisions were made.
- [Implementation roadmap](docs/ROADMAPS/whatsapp_schedule_copilot_poc_roadmap_v0.1.md) — phased, actionable plan for *what to build next*. Start here.
- [Multi-tenancy roadmap](docs/ROADMAPS/multi_tenancy_roadmap_v0.1_2026-08-04.md) — assessment and phased plan for onboarding a second instructor (tenant isolation, auth, admin impersonation).
- [Operational ontology & AI agent roadmap](docs/ROADMAPS/operational_ontology_and_agent_roadmap_v0.2_2026-08-05.md) — canonical plan for explicit schedule semantics, occurrence history, availability, and safe instructor-operated tools across the platform and WhatsApp.
- [Place stays & schedule overlay roadmap](docs/ROADMAPS/place_stays_and_schedule_overlay_roadmap_v0.1_2026-08-15.md) — approved, trackable plan to make Meus Locais a neutral place/time/pricing substrate beneath classes and events, including Agenda, Financeiro, waitlist, makeup, and active/passive agent migration.
- [Commercial & financial module roadmap](docs/ROADMAPS/commercial_financial_module_roadmap_v0.2_2026-08-05.md) — one-customer groups, inherited pricing, tenant feature controls, financial capacity scenarios, and the path to auditable revenue.
- [Make-up class credits & courtesy classes roadmap](docs/ROADMAPS/makeup_class_credits_roadmap_v0.1_2026-08-07.md) — completed: credit ledger, recommender, redemption through chat, courtesy classification, and contact detail surface.
- [Mobile readiness & PWA "Add to Home Screen" roadmap](docs/ROADMAPS/mobile_pwa_readiness_roadmap_v0.1_2026-08-08.md) — draft: mapped touch points for mobile-responsive screens and installable-app (manifest, icons, home-screen launch) support.
- [Waitlist ("Fila de Espera") roadmap](docs/ROADMAPS/waitlist_roadmap_v0.1_2026-08-09.md) — completed: data model, on-demand and event-driven matching, active-agent tools, passive-observer candidate review, and Clientes/Agenda UI for tracking customer demand with no open slot yet.
- [Instructor Events roadmap](docs/ROADMAPS/instructor_events_roadmap_v0.1_2026-08-09.md) — completed: non-class calendar entries (tournament refereeing, workshops, clinics) with conflict checking, revenue summary integration, dashboard toggle, and active-agent tools.
- [Passive confirmation detection and ambiguity escalation roadmap](docs/ROADMAPS/passive_confirmation_push_roadmap_v0.1_2026-08-10.md) — implemented locally: authoritative, fully resolved creates autoexecute; ambiguous fully resolved creates/reschedules use a durable, private-agent confirmation prompt. Detectados remains the exception-review surface. Full autonomy is intentionally out of scope.
- [Local dev webhook tunnel](docs/local_dev_webhook_tunnel.md) — current YCloud webhook tunnel URL and how to restart it during Phase 1 development.

## Running the platform

```bash
conda activate agenda
python start_server.py [--tunnel] [--worker]
```

Always starts the FastAPI backend (`:8005`) and the Next.js frontend (`:3010`, pinned — see `start_server.py`). Optional flags add more:

| Flag | What it adds | When you need it |
|---|---|---|
| `--tunnel` | A `cloudflared` quick tunnel exposing the backend, with the webhook URL printed once connected and auto-recorded in [docs/local_dev_webhook_tunnel.md](docs/local_dev_webhook_tunnel.md) | Registering/testing the real YCloud webhook |
| `--worker` | The candidate worker plus the durable passive-escalation worker, polling `pending_processing` and queued ambiguity deliveries | Running the passive confirmation pipeline against real or mock traffic |

Both are additive and commonly used together: `python start_server.py --tunnel --worker`. Press `Ctrl+C` to stop everything started.

## Status

The platform is in active development. All modules (calendar/agenda, contacts/places ontology, recurring groups, financial configuration & revenue, makeup class credits, courtesy appointments) are implemented end-to-end across the FastAPI backend and Next.js frontend. 91 backend tests pass consistently (run `pytest backend/tests -q --ignore=backend/tests/test_extraction.py` for the current count — this number drifts as features land).

The AI agent supports both read tools (search, schedule lookup, availability) and mutation tools (create/cancel/reschedule appointments, manage participants, redeem makeup credits) with a propose-confirm-execute lifecycle. The passive WhatsApp extraction pipeline detects scheduling intent from instructor-customer conversations.

See individual roadmaps for module-specific implementation status.

## Dev tool — mock WhatsApp chat

`http://localhost:3010/dev/mock-chat` simulates both sides of a WhatsApp conversation (instructor + customer) to exercise the real ingestion → debounce → extraction pipeline without a live WhatsApp connection. Messages are built into the same event shape YCloud sends and go through the exact same code path as the real webhook (`backend/app/chat/ingestion.py`). Only available when `DEBUG=true` (`backend/app/api/dev_mock.py`) — never exposed in a would-be production deployment. Requires `python start_server.py` running; log in with the admin credentials from `.env`.

## Phase 0 — Running the extraction CLI

```bash
conda activate agenda
python -m scripts.extraction_cli --fixture create_001
python -m scripts.calibrate  # runs the full labeled dataset and reports confidence calibration
```
