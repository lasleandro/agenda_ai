# WhatsApp Schedule Copilot — Implementation Roadmap

**Status:** Active  
**Version:** 0.1  
**Source of truth for product/architecture decisions:** [../whatsapp_schedule_copilot_poc_project_brief_v0.1.md](../whatsapp_schedule_copilot_poc_project_brief_v0.1.md)  
**Repository state at time of writing:** empty — no backend, no frontend, no infra yet.

---

## How to use this document

This roadmap turns the brief's Section 27 (Implementation Plan) and Section 33 (Immediate Development Backlog) into an ordered, actionable sequence. It does not repeat product rationale — see the brief for *why*; this document is about *what to do next, in what order, and what each step needs to be considered done*.

Each phase lists:

- **Goal** — the one thing this phase proves or delivers.
- **Prerequisites** — what must already be true before starting.
- **Tasks** — concrete, small, verifiable steps.
- **Credentials needed** — cross-referenced to `.env` (see Section "Credentials Checklist" at the end).
- **Exit criterion** — the check that must pass before moving to the next phase.

Phases are sequential and intentionally gated. Do not start a phase whose prerequisites are not met — the brief's Final Design Principles (Section 34) call for validating the narrow workflow before expanding it, and skipping a gate here has historically been how PoCs like this quietly become unbuildable.

---

## Phase -1 — Environment & Tooling Setup

**Goal:** a working local dev environment, with nothing product-specific built yet.

**Prerequisites:** none.

**Tasks:**

- [x] Create the conda environment `agenda` (Python 3.11, per project instructions) and confirm it activates: `conda activate agenda`.
- [ ] Confirm the shared local PostgreSQL container is reachable at `PG_LOCAL_HOST:PG_LOCAL_PORT` from `.env`. Do **not** create the `agenda_db` database yet — see the note below.
- [x] Scaffold the repository structure from the brief's Section 26 (`backend/`, `frontend/`, `infra/`, `docs/`) — empty directories with placeholder `__init__.py` / `README` stubs are enough at this stage; do not build features yet.
- [x] Initialize `requirements.txt` (project convention) with FastAPI, Pydantic, SQLAlchemy, Alembic, `dateparser`, and `instructor`.
- [ ] Create `requirements.txt` at the project root and keep it in sync going forward (project convention — update it every time a dependency is added, not in a batch later).
- [ ] Confirm `.env` is in `.gitignore` (never commit it).

**Database creation note:** the local `agenda_db` database does not need to exist yet. It becomes necessary at the start of **Phase 1**, when the first Alembic migration creates the `professional`, `contact`, `conversation`, and `message` tables. Phase 0 is an offline CLI with no database dependency. Tell me when you're ready to start Phase 1 and I'll create the database in the running container at that point.

**Exit criterion:** `conda activate agenda`, a FastAPI app boots locally (even an empty `/health` endpoint), and the repo structure matches Section 26 of the brief.

---

## Day 0 — Provider Capability Spike

**Goal:** confirm the single riskiest technical assumption in the entire product before writing any extraction logic.

**Prerequisites:** Phase -1 environment ready.

**Tasks:**

- [x] Create a YCloud sandbox/pilot account and a WhatsApp channel in Coexistence mode (see brief Section 9 and "Provider cost economics"). Channel "Meu Coach", WABA ID `106700875646601`.
- [x] Connect a real WhatsApp Business number (a throwaway test number is fine at this stage — it does not need to be the pilot instructor's number). `+5511949408816`, status Connected.
- [x] Send a message from that number's WhatsApp Business App to a test contact, and confirm the **outbound echo arrives via webhook** — this is the assumption everything else depends on (Open Question 16 in the brief). Confirmed via `whatsapp.smb.message.echoes` event.
- [x] Confirm inbound messages from the test contact also arrive via webhook. Confirmed via `whatsapp.inbound_message.received` event.
- [x] Record the result (pass/fail, plus any YCloud plan tier requirement) directly in this roadmap's Risk Register at the end.

**Credentials needed:** `YCLOUD_API_KEY`, `YCLOUD_WHATSAPP_CHANNEL_ID`, `YCLOUD_WEBHOOK_VERIFY_TOKEN` (see Credentials Checklist).

**Exit criterion:** both inbound and outbound-echo messages observed via webhook in the YCloud sandbox. **If this fails, stop and re-evaluate the provider or the Coexistence architecture before any further investment** — do not proceed to Phase 0 on the assumption it will work out later.

---

## Phase 0 — Offline Extraction Prototype

**Goal:** validate the semantic extraction problem in isolation, with no WhatsApp connection and no database.

**Prerequisites:** Day 0 spike passed.

**Tasks:**

- [x] Define the `SchedulingEvent` and `Ambiguity` Pydantic schemas (brief Section 13) in `backend/app/schemas/`.
- [x] Write the extraction prompt in pt-BR (brief Section 13, "Prompt responsibilities" / "Prompt non-responsibilities").
- [x] Wire up `Instructor` against Anthropic (chosen provider — `ANTHROPIC_API_KEY` in `.env`; remove `OPENAI_API_KEY` line once confirmed unused).
- [x] Build the labeled fixture dataset (started with 11 examples covering all required categories from brief Section 24 — grow toward the full 160-example target as a permanent regression suite).
- [x] Build the standalone extraction CLI: paste a conversation in, get a `SchedulingEvent` JSON out (`scripts/extraction_cli.py`).
- [x] Add the temporal validator: cross-check LLM output against `dateparser` (pt-BR locale) per brief Section 13 (`backend/app/services/temporal.py`).
- [x] Wire up Langfuse tracing for every extraction call (prompt version, tokens, latency, cost) — integrated in `backend/app/services/extraction.py`, active once `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set.
- [x] Run the confidence-calibration check from brief Section 15 (`scripts/calibrate.py` built, executed against the 11-fixture dataset — **11/11, 100% accuracy**, see Risk Register).

**Credentials needed:** Azure OpenAI credentials (`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`) — pattern reused from `geoedge_municipios/backend/common/llm_provider.py`. Langfuse (`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`).

**Exit criterion (all three, per brief Section 27):**

- acceptable precision on the manually labeled pt-BR dataset;
- the CLI correctly handles Brazilian Portuguese temporal expressions and colloquialisms;
- confidence thresholds have been calibrated against actual accuracy, not left at the brief's illustrative defaults.

Run this phase entirely offline. No YCloud webhook, no database, no instructor involved yet.

---

## Phase 1 — Message Ingestion

**Goal:** reliably reconstruct both sides of a real WhatsApp conversation in the database.

**Prerequisites:** Phase 0 passed. **LGPD consent framework and privacy policy must exist before any real conversation is processed** (brief Section 22 — this is a hard legal gate, not a formality).

**Tasks:**

- [x] Create the local `agenda_db` database in the running Postgres container. Confirmed live in `cityfoundry_local_pg` (port 5433), owner `cityfoundry`.
- [x] Write the first Alembic migration: `professional`, `contact`, `conversation`, `message` tables (brief Section 10.1–10.4). `e257381e7350_initial_domain_models` covers the full schema (all 8 domain tables incl. `appointment_candidate`/`appointment_evidence`/`appointment`/`appointment_transition`) and is applied — `alembic current` shows `agenda_db` at head.
- [x] Implement the `MessagingProvider` protocol (brief Section 9, "Architecture guidance") and a YCloud implementation behind it. `backend/app/services/ycloud_provider.py` — signature verification (`YCloud-Signature: t=...,s=...`, HMAC-SHA256) and event normalization for both inbound and echo events.
- [x] Build the webhook endpoint: verify signature → persist raw event → normalize → enforce idempotency on `provider_message_id` → acknowledge quickly (brief Section 12.1). `backend/app/api/whatsapp.py` (`POST /webhooks/ycloud`). No synchronous LLM calls. Idempotency confirmed by replaying a duplicate `provider_message_id` — no second row created. **Async processing scheduling (`pending_processing`) is not wired yet — that's Phase 2's debounce work, not required for Phase 1's ingestion goal.**
- [~] Handle both inbound customer messages and instructor outbound-echoes. Inbound confirmed end-to-end with a real WhatsApp message (persisted correctly, contact auto-created with WhatsApp profile name from `customerProfile.name`). Outbound-echo normalization is implemented (`whatsapp.smb.message.echoes`) but not yet exercised with a real echo since the live-code changes — still needs one real test send from the instructor's own WhatsApp Business App to confirm end-to-end.
- [x] Build a bare developer-only conversation view (no UI polish needed) to visually confirm reconstruction. Implemented as backend-only endpoints (Swagger at `/docs`) rather than a frontend page, since the frontend's routing is mid-refactor — `GET /api/conversations` (list) and `GET /api/conversations/{id}` (messages in order), both auth-gated like the calendar API. Verified against the real test message.
- [ ] Draft the LGPD consent flow and instructor-facing privacy policy (brief Section 22) — **deferred for now**, per explicit call — must still complete before connecting the real pilot number / any non-test student conversation.

**Credentials needed:** `YCLOUD_API_KEY`, `YCLOUD_WHATSAPP_CHANNEL_ID`, `YCLOUD_WEBHOOK_VERIFY_TOKEN`, `YCLOUD_WEBHOOK_SIGNING_SECRET`, local Postgres (already in `.env`), `SENTRY_DSN`.

**Exit criterion:** a real instructor–student conversation (test number is fine) is reconstructed in order in the database, with no duplicate records on webhook retry, and the LGPD consent/privacy-policy prerequisite is signed off.

---

## Phase 2 — Appointment Candidate Pipeline

**Goal:** detect real appointment candidates from live conversations, without the instructor seeing anything yet (shadow mode).

**Prerequisites:** Phase 1 passed.

**Tasks:**

- [x] Implement conversation buffering / debounce (brief Section 12.2): `pending_processing` table with `process_after`, worker polls with `FOR UPDATE SKIP LOCKED`, debounce reset on new messages. `backend/app/models/pending_processing.py`, `backend/app/services/pipeline.py::schedule_processing`, `backend/app/workers/candidate_worker.py`. Debounce configurable via `PIPELINE_DEBOUNCE_SECONDS` (default 30s). Wired into the webhook handler, but only on a genuinely new message — not on a deduped retry.
- [x] Wire the Phase 0 extraction logic into the live pipeline (`build_conversation_window` → `extract_scheduling_event` → `validate_temporal`). `backend/app/services/pipeline.py::build_conversation_window` / `process_conversation`. Required fixing a pre-existing import inconsistency: `extraction.py`/`temporal.py` used `backend.app.X` imports (only worked from the Phase 0 CLI's run context) — changed to `app.X` to match how the FastAPI app itself resolves imports, and added a `sys.path` shim to `scripts/extraction_cli.py` so the CLI still works unchanged. Re-verified `python -m scripts.extraction_cli --fixture create_001` still passes after the change.
- [x] Implement `appointment_candidate` and `appointment_evidence` tables (brief Section 10.5, 10.7) and persist every extraction result, including `none` results. Tables already existed from the Phase 1 migration; `process_conversation` persists unconditionally regardless of `action`. Verified end-to-end with a real test message: correctly extracted `action=create`, proposed time, service, confidence 0.9, with evidence correctly linked to the source message.
- [x] Support multiple distinct scheduling events from one conversation window and deduplicate repeated extraction runs by a stable event fingerprint. One conversation can now yield multiple candidates (for example, separate confirmed 10h and 12h lessons) without creating duplicate candidates on subsequent runs.
- [x] Build a manual inspection page (internal/developer-only) to review candidates against evidence. Extended `GET /api/conversations/{id}` to include `candidates`, each with its linked evidence messages (`backend/app/api/conversations.py::_candidate_with_evidence`). Verified against the real test candidate — correctly shows the `action=create` candidate linked back to its source message.
- [ ] Run in shadow mode: let it detect candidates for at least a few days of real conversation without notifying anyone, and manually compare against the instructor's actual schedule. Not started — needs the worker running continuously against real (or realistic) conversation traffic first.

**Credentials needed:** none new — reuses Phase 0/1 credentials.

**Exit criterion:** candidates are detected with message evidence attached, precision looks reasonable against a manual spot-check, and nothing has been sent to the instructor yet.

---

## Phase 3 — Instructor Feedback Loop

**Goal:** the instructor can confirm, reject, or correct a candidate entirely from WhatsApp, no web UI required.

**Prerequisites:** Phase 2 passed and shadow-mode results look trustworthy.

**Tasks:**

- [ ] Implement the `appointment` and `appointment_transition` tables (brief Section 10.6, 10.8) and the state machine (brief Section 11).
- [ ] Implement the outbox pattern (brief Section 20) with retry/exponential backoff and dead-letter state.
- [ ] Build the private assistant notification channel (a number controlled by the product, not the instructor's own — brief Section 17).
- [ ] Implement the three initial notification types: new appointment detected, rescheduling detected, cancellation detected, each with `[Confirmar] [Corrigir]` / `[Confirmar alteracao] [Revisar]` actions.
- [ ] Implement confirm / reject / correct as API endpoints (brief Section 19) triggered by the WhatsApp interactive buttons.
- [ ] Log every correction as both a UX event and an evaluation label (brief Section 34, principle 6).

**Credentials needed:** `ASSISTANT_WHATSAPP_NUMBER` (config, not secret — set once the assistant number is provisioned in YCloud).

**Exit criterion:** the pilot instructor (or a test user standing in for them) can validate every candidate through WhatsApp alone, with no web interface involved.

---

## Phase 4 — Weekly Calendar

**Goal:** a secondary, correction-capable web surface — not the primary interface (brief Section 34, principle 7).

**Prerequisites:** Phase 3 passed.

**Tasks:**

- [ ] Set up authentication (Supabase Auth or Lucia — pick one, see Credentials Checklist).
- [ ] Scaffold the Next.js frontend per brief Section 26 (`/login`, `/agenda`, `/appointments/:id`, `/settings`).
- [ ] Integrate FullCalendar weekly time-grid view against `GET /api/calendar`.
- [ ] Build the appointment detail page with evidence, audit trail, and correction action (brief Section 18.3).
- [ ] Build the settings page (brief Section 18.4).
- [ ] Confirm mobile-responsive layout — the instructor's primary device is a phone.

**Credentials needed:** `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` (or Lucia's local session-secret equivalent if that path is chosen instead).

**Exit criterion:** the instructor can inspect and correct the complete weekly schedule from the web app.

---

## Phase 5 — Daily Operation

**Goal:** the product runs unattended for a real pilot, not just in developer testing.

**Prerequisites:** Phase 4 passed.

**Tasks:**

- [ ] Implement the daily summary job (brief Section 7.3) at the configured `daily_summary_time`.
- [ ] Implement deterministic `hoje` / `amanha` / `esta semana` / `proxima aula` commands (brief Section 17, "Command scope") — not a general conversational agent.
- [ ] Finish cancellation and rescheduling transition logic end-to-end, including the "retrieve the customer's relevant appointment as LLM context, don't let the LLM search the database" rule (brief Section 14).
- [ ] Build a basic metrics dashboard covering the core metrics in brief Section 23 (precision, recall, no-edit confirmation rate, false-positive rate, processing latency).
- [ ] Plan the local-to-remote Azure Postgres sync (per project convention: develop locally, sync to remote after — never operate destructively on the Azure remote DB directly).

**Credentials needed:** `AZURE_PG_*` (only once ready to sync pilot data to the remote environment — not needed for local development).

**Exit criterion:** one instructor can use the system for at least two consecutive weeks without manual intervention from the team.

**Forward-looking note (not a Phase 5 task):** the current single-instructor pilot uses YCloud's self-serve dashboard flow, where the team connects the instructor's number manually. This does not scale to onboarding a second instructor without them going through YCloud's own login. Before adding instructor #2, apply for YCloud's **Tech Partner** program (see Credentials Checklist and Risk Register) to get API-driven, embedded-signup-style onboarding instead.

**Admin/impersonation note (also not a Phase 5 task, deferred until multi-tenant):** once there's more than one professional, revisit `geoedge_municipios`'s admin-impersonation pattern (`backend/api/routes/auth.py:197-246`) as the reference: a `kognita_admin`-equivalent role calls `POST /impersonate` with a `tenant_id`/`professional_id`, gets a new JWT scoped to that tenant, and every subsequent query derives its scope from the token, never the request body. Not built now — the current PoC has exactly one professional and one hardcoded admin login, so there's no tenant to impersonate into yet, and the calendar API doesn't scope by `professional_id` at all (fine for one tenant, would need to change first).

---

## Phase 6 — Voice Messages

**Goal:** audio-based scheduling decisions are included in detection.

**Prerequisites:** Phase 5 stable — brief Section 21 explicitly notes this should be supported early but not necessarily in the first milestone.

**Tasks:**

- [ ] Implement media download and temporary storage for inbound audio.
- [ ] Benchmark Google Cloud Speech-to-Text vs. Azure Speech on informal pt-BR (contractions, slang, outdoor/sports background noise) before committing to one (brief Section 21).
- [ ] Wire transcription output into the existing extraction pipeline (no separate code path).
- [ ] Implement the short audio-retention/deletion policy (brief Section 21).
- [ ] Add audio examples to the Phase 0 labeled dataset and re-run the regression suite.

**Credentials needed:** whichever of `GOOGLE_SPEECH_TO_TEXT_CREDENTIALS_JSON` / `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` wins the benchmark.

**Exit criterion:** audio-based scheduling decisions appear correctly in the evaluation dataset and the calendar.

---

## Credentials Checklist

All of these have been added as empty placeholders in `.env`, grouped by the phase that first needs them. See `.env` for the exact variable names and where to obtain each one.

| Phase | Credential | Where to get it |
|---|---|---|
| Day 0 | YCloud API key, channel ID, webhook verify token | ycloud.com — create a Coexistence WhatsApp channel |
| Phase 0 | Azure OpenAI key, endpoint, model name | `.env` — configured; pattern reused from `geoedge_municipios/backend/common/llm_provider.py` |
| Phase 0 | Langfuse public/secret key | Self-hosted instance or langfuse.com free tier |
| Phase 1 | YCloud webhook signing secret | YCloud dashboard, same channel as Day 0 |
| Phase 1 | Sentry DSN | sentry.io — free project tier is enough for the PoC |
| Phase 3 | Assistant WhatsApp number | Provision a second number/channel in YCloud |
| Phase 4 | Supabase Auth keys, or Lucia session secret | supabase.com project, or generate a local secret if using Lucia |
| Phase 5 | Azure PostgreSQL connection details | Only once ready to sync pilot data — not needed for local dev |
| Post-pilot (multi-tenant) | YCloud Tech Partner credentials (partner ID, embedded-signup config) | Only once onboarding a second instructor — apply via `ycloud.com/tech-partner`, ask specifically about Meta Embedded Signup support. Not needed for the single-instructor PoC. |
| Phase 6 | Google Speech-to-Text or Azure Speech key | Whichever wins the pt-BR accuracy benchmark |

---

## Milestone Mapping (MVP Acceptance Criteria)

Brief Section 28 defines readiness for a real pilot. Each item maps to a phase above:

- WhatsApp Coexistence connected, both directions verified → **Day 0 / Phase 1**
- Duplicated webhooks don't create duplicated records → **Phase 1**
- Conversations reconstructed in order → **Phase 1**
- Scheduling events returned through a strict schema → **Phase 0**
- Candidates contain message evidence → **Phase 2**
- Instructor can confirm/reject/correct a candidate → **Phase 3**
- Confirmed appointments appear on a weekly calendar → **Phase 4**
- Cancellations/reschedules preserve an audit trail → **Phase 3**
- Daily summaries can be sent → **Phase 5**
- Errors and LLM traces are observable → **Phase 0 / Phase 1**
- Data can be deleted for the pilot user → **Phase 1 (LGPD gate)**
- Product can run in shadow mode → **Phase 2**

Once all of the above are checked, proceed to the Pilot Plan (brief Section 29): Week 1 shadow mode, Week 2 assisted mode, Weeks 3–4 operational mode.

---

## Risk Register

Tracked here so the highest-uncertainty items stay visible instead of buried in a phase checklist.

| Risk | Status | Notes |
|---|---|---|
| Provider delivers instructor-sent echoes via webhook | **Passed — 2026-08-04** | Tested via webhook.site against channel "Meu Coach" (WABA ID `106700875646601`, number `+5511949408816`, free/self-serve tier). Outbound echo confirmed as event type `whatsapp.smb.message.echoes`; inbound confirmed as `whatsapp.inbound_message.received`. Both include `wabaId`, `from`/`to`, message body, and (inbound) `customerProfile.name`. Go/no-go passed — proceed to Phase 0 exit / Phase 1. |
| LLM confidence scores are miscalibrated | **Checked — 11/11 (100%) on 11-fixture dataset** | Model confidence 0.90+ matched 100% actual accuracy on the 11-sample dataset. Need the full 160-example dataset for statistical significance. Model correctly returns `none` for ambiguous cases (bare "Consegue as cinco?"). `create` vs `confirm` distinction is semantic — conversations ending in "confirmado"/"Otimo." are interpreted as `confirm`; this is valid given the action semantics. |
| LGPD consent chain (instructor consent vs. each student's own consent) | **Open — legal review required before Phase 1** | See brief Section 22. Blocking, not a formality. |
| Per-professional provider + LLM cost at real volume | **Open — track from Phase 1 onward** | Brief Open Question 17. |
| Voice transcription accuracy on informal pt-BR | **Deferred to Phase 6** | Benchmark before committing to a vendor. |
| YCloud's self-serve tier does not support onboarding multiple end-customers without each one touching YCloud's own login | **Checked — resolved for the PoC, deferred for multi-tenant** | YCloud's free/self-serve dashboard flow assumes *you* are the business connecting *your own* number — fine for one pilot instructor (Day 0–Phase 5). Real multi-tenant onboarding (many instructors, none of whom should see a YCloud login) requires YCloud's **Tech Partner** program (`ycloud.com/tech-partner`), which exposes APIs to provision a WABA per end-customer, equivalent to Meta's official Embedded Signup. Do not apply for Tech Partner status until onboarding a second instructor — premature for the current one-instructor pilot scope. |

---
