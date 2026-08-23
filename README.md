# Tennis OS — WhatsApp Schedule Copilot

A passive WhatsApp Business copilot that converts conversations between independent professionals and their customers into an auditable, automatically maintained schedule. Initial vertical: independent tennis instructors in Brazil.

## Documentation

### Platform Architecture

- [Architecture overview](docs/architecture_overview.md) — high-level system design, technology stack, project structure, and core architectural patterns (propose-confirm-execute lifecycle, event ledger, tenant isolation).
- [Scheduled tasks architecture](docs/scheduled_tasks_architecture.md) — daily agenda configuration, tenant isolation, durable execution service, provider boundary, state transitions, and operating runbook.
- [Data architecture](docs/data_architecture.md) — complete data model with Mermaid ERDs for all 33 database tables grouped by domain (identity, contacts, scheduling, financial, audit).
- [Capacity evaluation & make-up slot recommender](docs/capacity_and_recommendations.md) — the financial dashboard's occupancy/what-if math and the make-up-credit slot recommender's scoring algorithm, verified against the shipped code (not the pre-implementation plan).
- [Ontology & chat architecture](docs/ontology_chat_architecture.md) — how the AI agent reads and writes the instructor's ontology, the WhatsApp → extraction → agent pipeline, tool taxonomy (read + mutation tools), entity resolution, and temporal resolution.
- [AI agent modes](docs/ai_agent_modes.md) — distinction between the active instructor agent (direct chat → propose → confirm → execute) and the passive observer (detects scheduling intent in instructor-customer WhatsApp conversations without being addressed).
- [Agent navigability map](docs/agent_navigability.md) — code-first map of active and passive agent entry points, tool/action boundaries, ontology records, candidate lifecycles, and runtime workers.
- [Business rules](docs/business_rules.md) — catalog of all encoded business rules: scheduling constraints, makeup credit lifecycle, revenue rules, multi-tenancy, agent guardrails, data integrity, and WhatsApp pipeline rules.
- [Google Cloud Run & Cloud SQL deployment assessment](docs/google_cloud_run_cloud_sql_deployment_assessment.md) — current production-readiness assessment, target architecture, Cloud SQL design, security controls, and staged delivery plan.

### Page Documentation

- [Agenda (Calendar)](docs/pages/agenda.md) — primary scheduling interface with FullCalendar week view, appointment creation, group management.
- [Clientes (Contacts)](docs/pages/clientes.md) — customer list with search/groups, and detail page with level, address, courtesy appointments, fixed slots.
- [Financeiro (Financial)](docs/pages/financeiro.md) — operational financial workspace with projections, capacity, and recognized-revenue history.
- [Simulador financeiro](docs/pages/simulador_financeiro.md) — dedicated what-if workspace for capacity, mix, and temporary price scenarios.
- [Configurações (Tenant Definitions)](docs/pages/minhas_regras.md) — operational rules for every tenant plus financial definitions when the commercial_financials module is enabled.
- [Chat / AI Assistant](docs/pages/chat.md) — floating chat panel accessible from every page, with tool call transparency and action confirmation.

### Roadmaps & Guides

- [Project brief](docs/whatsapp_schedule_copilot_poc_project_brief_v0.1.md) — product thesis, architecture, domain model, and design principles. Source of truth for *why* decisions were made.
- [Implementation roadmap](docs/ROADMAPS/whatsapp_schedule_copilot_poc_roadmap_v0.1.md) — phased, actionable plan for *what to build next*. Start here.
- [Multi-tenancy roadmap](docs/ROADMAPS/multi_tenancy_roadmap_v0.1_2026-08-04.md) — assessment and phased plan for onboarding a second instructor (tenant isolation, auth, admin impersonation).
- [Operational ontology & AI agent roadmap](docs/ROADMAPS/operational_ontology_and_agent_roadmap_v0.2_2026-08-05.md) — historical roadmap; its place-stay semantics are superseded by the roadmap below.
- [Place stays & schedule overlay roadmap](docs/ROADMAPS/place_stays_and_schedule_overlay_roadmap_v0.1_2026-08-15.md) — approved, trackable plan to make Meus Locais a neutral place/time/pricing substrate beneath classes and events, including Agenda, Financeiro, waitlist, makeup, and active/passive agent migration.
- [Group capacity & slot promotion roadmap](docs/ROADMAPS/group_capacity_and_slot_promotion_roadmap_v0.1_2026-08-21.md) — implemented locally: empty and partially occupied group slots, explicit individual-to-group promotion, dated guests, capacity-aware Agenda/agent scheduling, and a separately approved remote rollout checklist.
- [Agent recurring individual-booking correction roadmap](docs/ROADMAPS/agent_recurring_individual_booking_correction_roadmap_v0.1_2026-08-23.md) — proposed correction for the agent routing a named weekly customer booking into an empty group slot.
- [Agent group-vacancy information recovery roadmap](docs/ROADMAPS/agent_group_vacancy_information_recovery_roadmap_v0.1_2026-08-23.md) — proposed correction for group-seat questions being incorrectly answered with free-time/work-journey availability.
- [Active-agent pt-BR conversational resilience roadmap](docs/ROADMAPS/agent_ptbr_conversational_resilience_roadmap_v0.1_2026-08-23.md) — code-first audit and phased plan for informal Brazilian Portuguese dates, post-confirmation context, dated participant removal, atomic waitlist fulfillment, and safe recurring-write scope.
- [Financial capacity reconciliation roadmap](docs/ROADMAPS/financial_capacity_reconciliation_roadmap_v0.1_2026-08-16.md) — corrective plan for generic versus place-attributed capacity, month-summary revenue semantics, and cross-platform alignment with place stays.
- [Financial experience revamp roadmap](docs/ROADMAPS/financial_experience_revamp_roadmap_v0.1_2026-08-20.md) — proposed UX/UI reorganization of Financeiro and extraction of scenario planning into a dedicated `/financeiro/simulador` workspace, with no financial behavior changes.
- [Financial operational intelligence roadmap](docs/ROADMAPS/financial_operational_intelligence_roadmap_v0.1_2026-08-20.md) — next Financeiro iteration: compact period presets, operational class outcomes, customer rankings, Realizado terminology, and moving capacity potential to the simulator.
- [Financial reporting and agent tools roadmap](docs/ROADMAPS/financial_reporting_agent_tools_roadmap_v0.1_2026-08-20.md) — canonical read-only financial report contract for Financeiro, instructor agent tools, and future periodic reports.
- [Makeup capacity and revenue roadmap](docs/ROADMAPS/makeup_capacity_and_revenue_roadmap_v0.1_2026-08-20.md) — preserve makeup capacity while preventing a redeemed credit from creating duplicate projected or recognized revenue.
- [Agenda revenue recommendations roadmap](docs/ROADMAPS/agenda_revenue_recommendations_roadmap_v0.1_2026-08-21.md) — proposed slot-level and Agenda-wide decision-support layer for filling groups, protecting prime capacity, recovering openings, and reviewing future pricing or class format with deterministic financial evidence and optional LLM explanations.
- [Commercial & financial module roadmap](docs/ROADMAPS/commercial_financial_module_roadmap_v0.2_2026-08-05.md) — one-customer groups, inherited pricing, tenant feature controls, financial capacity scenarios, and the path to auditable revenue.
- [Make-up class credits & courtesy classes roadmap](docs/ROADMAPS/makeup_class_credits_roadmap_v0.1_2026-08-07.md) — completed: credit ledger, recommender, redemption through chat, courtesy classification, and contact detail surface.
- [Mobile readiness & PWA "Add to Home Screen" roadmap](docs/ROADMAPS/mobile_pwa_readiness_roadmap_v0.1_2026-08-08.md) — draft: mapped touch points for mobile-responsive screens and installable-app (manifest, icons, home-screen launch) support.
- [Waitlist ("Fila de Espera") roadmap](docs/ROADMAPS/waitlist_roadmap_v0.1_2026-08-09.md) — completed: data model, on-demand and event-driven matching, active-agent tools, passive-observer candidate review, and Clientes/Agenda UI for tracking customer demand with no open slot yet.
- [Instructor Events roadmap](docs/ROADMAPS/instructor_events_roadmap_v0.1_2026-08-09.md) — completed: non-class calendar entries (tournament refereeing, workshops, clinics) with conflict checking, revenue summary integration, dashboard toggle, and active-agent tools.
- [Scheduled tasks: daily agenda roadmap](docs/ROADMAPS/scheduled_tasks_daily_agenda_roadmap_v0.1_2026-08-16.md) — implemented daily agenda task, provider-neutral WhatsApp boundary, tenant-isolated admin panel, and operational setup notes.
- [Tenant configuration centralization roadmap](docs/ROADMAPS/tenant_configuration_centralization_roadmap_v0.1_2026-08-16.md) — proposed relocation of operational and financial definitions into one feature-aware tenant configuration area.
- [Passive confirmation detection and ambiguity escalation roadmap](docs/ROADMAPS/passive_confirmation_push_roadmap_v0.1_2026-08-10.md) — implemented locally: authoritative, fully resolved creates and reschedules autoexecute; ambiguous fully resolved creates/reschedules use a durable, private-agent confirmation prompt. Detectados remains the exception-review surface. Full autonomy is intentionally out of scope.
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
| `--worker` | Candidate, passive-escalation, and scheduled-task workers, polling pending work, ambiguity deliveries, and due tenant tasks | Running WhatsApp processing and scheduled daily agenda delivery |

Both are additive and commonly used together: `python start_server.py --tunnel --worker`. Press `Ctrl+C` to stop everything started.

## Status

The platform is in active development. All modules (calendar/agenda, contacts/places ontology, recurring groups, financial configuration & revenue, makeup class credits, courtesy appointments) are implemented end-to-end across the FastAPI backend and Next.js frontend. Run `pytest backend/tests -q --ignore=backend/tests/test_extraction.py` for the current local regression suite.

The AI agent supports both read tools (search, schedule lookup, availability) and mutation tools (create/cancel/reschedule appointments, manage participants, redeem makeup credits) with a propose-confirm-execute lifecycle. The passive WhatsApp extraction pipeline detects scheduling intent from instructor-customer conversations. Platform admins can configure a tenant-isolated daily WhatsApp agenda under `/admin/scheduled-tasks`; configure the approved daily-agenda template name in `.env` before enabling a task.

See individual roadmaps for module-specific implementation status.

## Dev tool — mock WhatsApp chat

`http://localhost:3010/dev/mock-chat` simulates both sides of a WhatsApp conversation (instructor + customer) to exercise the real ingestion → debounce → extraction pipeline without a live WhatsApp connection. Generate and select tenant-scoped mock customers to keep separate test scenarios. Messages are built into the same event shape YCloud sends and go through the exact same code path as the real webhook (`backend/app/chat/ingestion.py`). Only available when `DEBUG=true` (`backend/app/api/dev_mock.py`) — never exposed in a would-be production deployment. Requires `python start_server.py` running; log in with the admin credentials from `.env`.

## Phase 0 — Running the extraction CLI

```bash
conda activate agenda
python -m scripts.extraction_cli --fixture create_001
python -m scripts.calibrate  # runs the full labeled dataset and reports confidence calibration
```
