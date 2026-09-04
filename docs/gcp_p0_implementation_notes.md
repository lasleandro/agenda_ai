# GCP P0 implementation notes

Implementation of the P0 gates from
[google_cloud_run_cloud_sql_deployment_assessment.md](google_cloud_run_cloud_sql_deployment_assessment.md)
Section 5. Everything here is designed so local development
(`python start_server.py [--tunnel] [--worker]` and `/dev/mock-chat`) keeps
working unchanged; production-only behaviour is gated on
`APP_ENV`/`ENVIRONMENT` = `production`.

- **Date:** 2026-09-02
- **Test baseline:** `pytest backend/tests -q --ignore=backend/tests/test_extraction.py`
  — 303 passing. The 6 failing `test_makeup_credits.py` tests are pre-existing
  (introduced by commit `e265c35` "suspender/archivar tenant") and are not in
  P0 scope.
- **Alembic head after this work:** `35214a28e1d5` (was `f2b9a1c8d3e7` in the
  assessment text, already `c7e1a9d3b5f8` on disk before this work).

## What changed, by P0 item

### 1. Reproducible containers

Dockerfiles authored, styled after `horah/Dockerfile` (apt deps block,
`useradd -ms /bin/bash appuser`, `HEALTHCHECK` with curl, `ENTRYPOINT` shell
script). **Image build is left to the operator** — no image is produced by
this work.

- `Dockerfile` — one multi-stage image for every workload. Stage 1
  (`node:20-bookworm-slim`) builds the Next.js standalone server
  (`output: "standalone"` added to `frontend/next.config.ts`); stage 2
  (`python:3.11-slim-bookworm`) installs `requirements.txt`, copies the
  backend and the standalone frontend, and adds a single `node` binary
  copied from stage 1 (same bookworm base, so no npm/libs needed). Non-root
  `appuser`.
- `scripts/deploy/entrypoint.sh` — selects the workload from `$ROLE`:
  `platform` (default) execs the supervisor; `api`, `migrate`,
  `webhook-processor`, `candidate-worker`, `escalation-worker`,
  `scheduled-task-worker`, `email-worker` each exec one process from the
  backend package. Optional `DB_WAIT_HOST` TCP readiness wait.
- `scripts/deploy/supervisor.py` — `platform` role PID 1. Starts Next.js on
  `0.0.0.0:$PORT` and Uvicorn on `127.0.0.1:$INTERNAL_API_PORT`, forwards
  `SIGTERM`/`SIGINT` to both, and exits non-zero as soon as either child
  exits so the orchestrator replaces the instance.
- `scripts/deploy/healthcheck.sh` — `/health` for `platform`/`api`, no-op
  for worker roles.
- `.dockerignore` — excludes VCS, Python/Node caches, `node_modules`,
  `.next`, `backend/tests/`, `docs/`, `*.md`, `.env*` (keeps
  `.env.example`), `start_server.py`, `godaddy_landing_page/`, `infra/`.
- A backend-only image (no Node) is still an option per assessment §5 P0.1;
  the single role-based image is the simpler default and the assessment
  allows either.
- Fixed a pre-existing blocker: `/admin/scheduled-tasks` used
  `useSearchParams()` without a `<Suspense>` boundary, which fails
  `next build`. Wrapped it. `npm run build` now passes (required for any
  container build).

### 2. Deployment-neutral database configuration

- `backend/app/database.py` — resolves `DATABASE_URL` first (verbatim
  SQLAlchemy URL, supports Cloud SQL socket via `?host=/cloudsql/...`),
  falls back to the existing `PG_LOCAL_*` parts for local dev. Normalises
  the legacy `postgres://` scheme. Pool sizing is read from
  `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` / `DB_POOL_RECYCLE`
  (defaults unchanged: 5 / 10 / 30 / 1800). `pool_pre_ping=True` added.
- Alembic (`backend/migrations/env.py`) already imports `DATABASE_URL` and
  already uses `NullPool`, so it inherits this with no change.

### 3. Validated configuration

- `backend/app/core/settings.py` — `environment_name()` accepts `APP_ENV`
  or `ENVIRONMENT`. `validate_startup_settings()` (runs on API startup) now
  also requires, in production: `DATABASE_URL`,
  `YCLOUD_WEBHOOK_SIGNING_SECRET`, `AZURE_OPENAI_API_KEY`,
  `AZURE_OPENAI_ENDPOINT` — in addition to the existing `JWT_SECRET_KEY`,
  CORS, `FRONTEND_BASE_URL`, `AUTH_COOKIE_SECURE`, `EMAIL_ENABLED` checks.
- `.env.example` extended with every new variable (all commented/defaulted).

### 4. Webhook durable handoff + idempotency

- New `webhook_receipts` table (`backend/app/models/webhook_receipt.py`,
  migration `35214a28e1d5`): one row per verified delivery, unique on
  `event_key` (= `provider_key` + SHA-256 of the exact verified body),
  status `received → processing → done | failed | dead`, with a claim lease.
- `backend/app/integrations/tasks/` — `WebhookTaskQueue` abstraction.
  `LocalReceiptQueue` (default) inserts a receipt with
  `ON CONFLICT DO NOTHING` and, when `WEBHOOK_INLINE_PROCESSING` is on
  (default: on unless production), processes it synchronously so the local
  loop stays instant. `CloudTasksQueue` is a documented deploy-time
  skeleton. Both funnel through the same `process_receipt` +
  `webhook_receipts` path, so swapping to Cloud Tasks changes no logic.
- `backend/app/api/whatsapp.py` rewritten: resolve provider → read body →
  verify signature → `enqueue` → return. No ingestion, LLM, or outbound
  send in the request. 401 on bad signature, 503 if the handoff fails.
- `backend/app/chat/webhook_processor.py` (`process_receipt`) +
  `backend/app/chat/webhook_processor_worker.py` (5th polling worker,
  claim-lease, bounded retries, `dead` after `WEBHOOK_PROCESSOR_MAX_ATTEMPTS`).
- Timestamp freshness: `YCloudWhatsAppProvider.verify_webhook` now rejects a
  correctly-signed callback whose signed `t=` is outside
  `YCLOUD_WEBHOOK_TOLERANCE_SECONDS` (default 300); bypassed under `DEBUG`.
- Atomic message + debounce write: `ingest_normalized_message` commits the
  message and its `pending_processing` row in one transaction. A duplicate
  delivery now runs `ensure_processing_scheduled` (insert-if-missing, never
  bumps an existing window) so a lost debounce row is recovered.
- Agent-channel replay: covered by the receipt. A byte-identical retry
  collides on `event_key` and the LLM turn / outbound send never re-runs.
- `start_server.py --worker` now also starts the webhook processor worker.
- Trade-off: a malformed payload is now detected asynchronously
  (receipt → `dead`) instead of a synchronous 400, because the endpoint
  deliberately does not parse the envelope before acknowledging.
- Tests: `backend/tests/test_webhook_receipt.py`,
  new cases in `test_whatsapp_provider.py` and `test_ingestion.py`.

### 5. Recoverable candidate claims

- `pending_processing` gains `claimed_at` + `attempts` (migration
  `a1b2c3d4e5f6`). `candidate_worker` now claims a row
  (`claimed_at = now`, `attempts += 1`) before extraction and deletes it
  only on success. A worker that dies mid-extraction leaves a claimed row
  that becomes reclaimable after `CANDIDATE_CLAIM_LEASE_SECONDS` (300).
  A conversation is dropped with an error log after
  `CANDIDATE_MAX_ATTEMPTS` (5) — bounded, instead of the previous
  delete-before-process which lost work on any crash.
- Tests: `backend/tests/test_candidate_worker.py`.

### 7 & 10. Same-origin routing / internal API URL

- `frontend/next.config.ts` — the server-side `/api/*` rewrite now reads
  `INTERNAL_API_URL` first (falls back to `NEXT_PUBLIC_API_URL`, then
  `http://localhost:8005`). Production points it at the loopback FastAPI
  process; it is never emitted into the browser bundle.

### 8. Authentication hardening

- CSRF (double-submit cookie), **enforced in production only**
  (`backend/app/core/csrf.py` + a middleware in `app.main`). The backend
  sets a non-HttpOnly `agenda_csrf_token` cookie on login / impersonate /
  `stop-impersonating`, and backfills it on `/me` when absent (never
  rotates mid-session). Unsafe `/api/*` requests that carry the session
  cookie must echo it in `X-CSRF-Token`. `/webhooks/*` and the
  unauthenticated auth bootstrap endpoints are exempt.
- Frontend: `frontend/src/lib/csrf.ts` (`csrfHeaders(method)`), wired into
  the `apiRequest` chokepoint in `lib/api.ts`, the dev-mock POST helpers,
  and the authenticated writes in `lib/auth.ts`.
- Cookie attribute alignment: `logout` now deletes the session cookie with
  the same `samesite` / `secure` / `httponly` it was set with, and clears
  the CSRF cookie.
- Write-endpoint rate limiting: a per-instance sliding-window guard
  (`backend/app/core/rate_limit.py`) on unsafe `/api/*` methods,
  **production only**, `WRITE_RATE_LIMIT_MAX` per
  `WRITE_RATE_LIMIT_WINDOW_SECONDS` (120 / 60s). This is a first burst
  guard, not a replacement for Cloud Armor or the DB-backed login limiter.
- `/docs`, `/redoc`, `/openapi.json` return `None` (disabled) in production.
- Tests: `backend/tests/test_csrf.py`.

### 9. Release-safe migrations

- Three new migrations, single linear head, downgrade/upgrade round-trip
  verified. The `migrate` entrypoint role runs `alembic ... upgrade head`
  as a one-shot job. No dependency added to `requirements.txt`
  (`google-cloud-tasks` is only needed if/when `CloudTasksQueue` is wired
  up — noted in that module).

## Not done here (still open before production)

- P0 #6 (bounded worst-case connection math against the chosen Cloud SQL
  tier) is a deployment-time calculation; the code hooks (env-driven pools,
  `pool_pre_ping`, `NullPool` for Alembic, the 5th worker) are in place.
- `CloudTasksQueue`, the separate webhook-ingress/processor Cloud Run
  services, IAM, VPC, Terraform, and Cloud Armor are infrastructure, not
  application code — see assessment Sections 8–10.
- P1 items (security headers on HTML routes, dependency/image scanning,
  retention policy, worker liveness metrics) are unchanged.
- Pre-existing: 6 `test_makeup_credits.py` failures from commit `e265c35`.
