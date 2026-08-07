# Tennis OS — WhatsApp Schedule Copilot

A passive WhatsApp Business copilot that converts conversations between independent professionals and their customers into an auditable, automatically maintained schedule. Initial vertical: independent tennis instructors in Brazil.

## Documentation

- [Project brief](docs/whatsapp_schedule_copilot_poc_project_brief_v0.1.md) — product thesis, architecture, domain model, and design principles. Source of truth for *why* decisions were made.
- [Implementation roadmap](docs/ROADMAPS/whatsapp_schedule_copilot_poc_roadmap_v0.1.md) — phased, actionable plan for *what to build next*. Start here.
- [Multi-tenancy roadmap](docs/ROADMAPS/multi_tenancy_roadmap_v0.1_2026-08-04.md) — assessment and phased plan for onboarding a second instructor (tenant isolation, auth, admin impersonation).
- [Operational ontology & AI agent roadmap](docs/ROADMAPS/operational_ontology_and_agent_roadmap_v0.2_2026-08-05.md) — canonical plan for explicit schedule semantics, occurrence history, availability, and safe instructor-operated tools across the platform and WhatsApp.
- [Commercial & financial module roadmap](docs/ROADMAPS/commercial_financial_module_roadmap_v0.2_2026-08-05.md) — one-customer groups, inherited pricing, tenant feature controls, financial capacity scenarios, and the path to auditable revenue.
- [Make-up class credits & courtesy classes roadmap](docs/ROADMAPS/makeup_class_credits_roadmap_v0.1_2026-08-07.md) — assessment and phased plan for detecting cancellations, tracking "aulas de reposição" credits for recurring customers, recommending make-up slots, and (independently) classifying no-charge "aula cortesia" bookings for financial reporting.
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
| `--worker` | The appointment candidate worker (`backend/app/chat/candidate_worker.py`), polling `pending_processing` every 5s | Testing or running the Phase 2 debounce → extraction pipeline against real or mock traffic |

Both are additive and commonly used together: `python start_server.py --tunnel --worker`. Press `Ctrl+C` to stop everything started.

## Status

Phase 0 (offline extraction prototype) complete. Day 0 provider spike passed — inbound and outbound-echo messages confirmed via webhook. Phase 1 (message ingestion) and Phase 2 (candidate pipeline) are largely built: `agenda_db` schema is live, the YCloud webhook (`backend/app/api/whatsapp.py`) persists messages idempotently, and the debounce → extraction → candidate pipeline (`backend/app/chat/pipeline.py`, `backend/app/chat/candidate_worker.py`) is wired and verified end-to-end. See the roadmap for what's still open (LGPD consent gate, outbound-echo live test, shadow mode).

## Dev tool — mock WhatsApp chat

`http://localhost:3010/dev/mock-chat` simulates both sides of a WhatsApp conversation (instructor + customer) to exercise the real ingestion → debounce → extraction pipeline without a live WhatsApp connection. Messages are built into the same event shape YCloud sends and go through the exact same code path as the real webhook (`backend/app/chat/ingestion.py`). Only available when `DEBUG=true` (`backend/app/api/dev_mock.py`) — never exposed in a would-be production deployment. Requires `python start_server.py` running; log in with the admin credentials from `.env`.

## Phase 0 — Running the extraction CLI

```bash
conda activate agenda
python -m scripts.extraction_cli --fixture create_001
python -m scripts.calibrate  # runs the full labeled dataset and reports confidence calibration
```
