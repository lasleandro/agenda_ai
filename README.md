# Agenda AI — WhatsApp Schedule Copilot

A passive WhatsApp Business copilot that converts conversations between independent professionals and their customers into an auditable, automatically maintained schedule. Initial vertical: independent tennis instructors in Brazil.

## Documentation

- [Project brief](docs/whatsapp_schedule_copilot_poc_project_brief_v0.1.md) — product thesis, architecture, domain model, and design principles. Source of truth for *why* decisions were made.
- [Implementation roadmap](docs/ROADMAPS/whatsapp_schedule_copilot_poc_roadmap_v0.1.md) — phased, actionable plan for *what to build next*. Start here.

## Status

Phase 0 (offline extraction prototype) in progress. Repository structure, schemas, prompt, extraction service, temporal validator, labeled fixtures, CLI, and calibration script are built — see the roadmap's "Phase 0 — Offline Extraction Prototype" section. Needs `ANTHROPIC_API_KEY` set in `.env` to run.

## Phase 0 — Running the extraction CLI

```bash
conda activate agenda
python -m scripts.extraction_cli --fixture create_001
python -m scripts.calibrate  # runs the full labeled dataset and reports confidence calibration
```
