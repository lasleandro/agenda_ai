# Google Cloud Run and Cloud SQL Deployment Assessment

**Assessment date:** 2026-08-11  
**Repository reviewed:** `agenda_ai`  
**Scope:** production deployment of the existing Next.js frontend, FastAPI API/webhook, candidate-processing worker, and PostgreSQL database on Google Cloud.

## 1. Executive recommendation

Deploy this application as four separately managed workloads:

1. **Cloud Run service — frontend:** Next.js production server, public.
2. **Cloud Run service — API:** FastAPI REST API and YCloud webhook endpoint, public only where required.
3. **Cloud Run worker pool — candidate worker:** one continuously running copy of `app.chat.candidate_worker`; it must not be a request-serving service or a one-shot Cloud Run job.
4. **Cloud SQL for PostgreSQL:** the durable system of record, connected privately from the API and worker.

Use Artifact Registry for images, Secret Manager for runtime secrets, a distinct user-managed service account per workload, and Cloud Run/Cloud SQL in the same Google Cloud region. Run Alembic migrations as a separate, single-task Cloud Run Job as part of the release process.

The database and application model are suitable for Cloud SQL. The repository is **not deployment-ready today** because it lacks production container definitions, an environment-neutral database configuration, production CORS/cookie settings, and a safe worker deployment artifact. These are small, bounded preparation tasks; no domain-model rewrite is necessary.

## 2. Evidence-based current-state map

| Concern | Current implementation | Deployment implication |
|---|---|---|
| Frontend | Next.js 16 production scripts exist in `frontend/package.json`; `/api/*` is rewritten using `NEXT_PUBLIC_API_URL`. | Package as a dedicated Cloud Run service, or change the browser API base to same-origin behind a custom domain/proxy. |
| API | FastAPI application exposes `/health`, REST routes, auth, and `POST /webhooks/ycloud`. | Package as a public Cloud Run service listening on Cloud Run's injected `PORT`. |
| Async processing | `candidate_worker.py` is an infinite five-second database-polling loop. | Run exactly one durable worker instance. A Cloud Run service with request-based CPU is unsuitable while idle; a Cloud Run worker pool is the closest managed fit. |
| Database | SQLAlchemy/PostgreSQL + Alembic; current migration head is `a9d2e5f8c1b3`. | Cloud SQL for PostgreSQL is compatible. Migrations must be serialized before application rollout. |
| PostgreSQL features | UUIDs, `JSONB`, timezone-aware timestamps, partial indexes, `FOR UPDATE SKIP LOCKED`, and `pg_trgm`. | Select a supported Cloud SQL PostgreSQL version and enable `pg_trgm` before/through migration. |
| External services | Azure OpenAI, YCloud WhatsApp, Langfuse. | Keep credentials in Secret Manager; allow controlled outbound HTTPS egress. |
| Local configuration | `database.py` only builds a DSN from `PG_LOCAL_*`; `.env` is loaded from the project root. | Add production `DATABASE_URL`/Cloud SQL connection handling and validate required configuration at startup. |

## 3. Target production architecture

```text
Internet users                         YCloud
      |                                  |
      v                                  v
Cloud Run: frontend                Cloud Run: API
Next.js, public                    FastAPI, public webhook route
      |                                  |
      +------------ HTTPS REST ----------+
                                         |
                                 Direct VPC egress
                                         |
                                 Cloud SQL PostgreSQL
                                 private IP, no public IP
                                         ^
                                         |
Cloud Run worker pool -------------------+
one `candidate_worker` process

All runtime secrets: Secret Manager
All images: Artifact Registry
Logs/metrics: Cloud Logging and Cloud Monitoring
Schema changes: one-task Cloud Run migration Job -> Alembic upgrade head
```

### Workload boundaries

| Workload | Entry command | Scaling / availability | Notes |
|---|---|---|---|
| `agenda-frontend` service | `npm run start` | Cloud Run service; scale to zero is acceptable initially. | Must listen on `$PORT`; configured public custom domain serves the web app. |
| `agenda-api` service | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Start with max 2 instances and modest concurrency (for example, 10), then tune with load data. | It serves browser/API traffic and YCloud's signed webhook. Do not run the polling worker in this container. |
| `agenda-candidate-worker` worker pool | `python -m app.chat.candidate_worker` | Exactly one worker instance initially. | Its `FOR UPDATE SKIP LOCKED` claim makes later horizontal scaling technically feasible, but initial parallelism would increase Azure OpenAI traffic and is unneeded. |
| `agenda-migrate` job | `alembic -c backend/alembic.ini upgrade head` | One task, one retry policy appropriate to release operations. | Execute once per release before routing API traffic to a revision that requires the new schema. |

Cloud Run services require their ingress container to listen on `0.0.0.0` and the injected `PORT`; they may handle multiple requests concurrently. Cloud Run Jobs, by contrast, should terminate when work completes. This is why Alembic fits a Job, while the current endless polling process fits a worker pool rather than a Job. [Cloud Run container contract](https://cloud.google.com/run/docs/container-contract), [Cloud Run concurrency](https://cloud.google.com/run/docs/about-concurrency)

## 4. Required application changes before first deployment

These changes are release blockers. They are intentionally narrow and can be implemented without changing user-facing behavior.

### P0 — deployment blockers

1. **Add reproducible container builds.** There is no `Dockerfile`, `.dockerignore`, or CI/build configuration. Add independent frontend and backend Dockerfiles (or a tested monorepo multi-stage build), both with production-only entrypoints. Never use `start_server.py` in Cloud Run: it launches development servers, `--reload`, local ports, and optional local tooling.
2. **Make database configuration deployment-neutral.** Replace the hard-coded `PG_LOCAL_*` assembly with a validated `DATABASE_URL` production path while retaining the existing local variables as the local fallback. Configure SQLAlchemy `pool_pre_ping=True`; set small, explicit pool limits based on Cloud SQL capacity; ensure migrations use the same connection source.
3. **Bind Uvicorn to Cloud Run's port.** The backend production command must consume `$PORT`, bind `0.0.0.0`, and omit `--reload`. The frontend production server must do the same.
4. **Make browser/API origins explicit.** `main.py` currently permits only the two localhost origins. Add a comma-separated `CORS_ALLOWED_ORIGINS` setting and set it to the production dashboard domain(s). Do not use `*`, because the API uses credentialed cookies.
5. **Harden session cookies for HTTPS.** `set_cookie` currently omits `secure=True`. Set `secure` from an explicit production environment setting (true in Cloud Run), retain `httponly`, and choose the cookie/domain strategy based on the selected frontend/API hostname design. The lowest-risk design is one parent custom domain with same-site subdomains, such as `app.example.com` and `api.example.com`.
6. **Fail closed for the YCloud signing secret in production.** The endpoint currently accepts unsigned events when `YCLOUD_WEBHOOK_SIGNING_SECRET` is absent. Permit that only in explicit local development; production startup/deployment must reject missing webhook credentials.
7. **Add a production environment template and startup validation.** `.env` is correctly ignored, but no `.env.example` exists. Add a non-secret template documenting every required variable and reject missing production-critical settings before accepting traffic.

### P1 — strongly recommended before public launch

1. Add FastAPI security headers, request IDs, structured logs, and an authenticated/readiness-aware health endpoint. Keep `/health` lightweight for Cloud Run liveness.
2. Give the API graceful shutdown handling: dispose SQLAlchemy connections when the instance receives `SIGTERM`.
3. Add bounded retries/timeouts for database operations affected by transient Cloud Run/Cloud SQL connection resets, and retain the existing 10-second YCloud outbound timeout.
4. Add an idempotent migration preflight to the delivery pipeline: build image, run tests, execute migration Job, verify API `/health`, then route traffic.
5. Decide whether the API’s `/docs` should remain exposed in production. Restrict it or disable it if it is not an intentional operational interface.

### Important non-blocker observation

The current `candidate_worker` deletes its `PendingProcessing` row and commits before running extraction. If the process dies after that commit, the message window is not retried. This is pre-existing application behavior, not a Cloud Run incompatibility, but it becomes more likely during managed-instance termination. Before relying on the worker for production workflows, redesign its claim/retry state or add a recoverable lease.

## 5. Cloud SQL for PostgreSQL design

### Recommended baseline

- Create one Cloud SQL for PostgreSQL primary instance in the same region as all Cloud Run workloads. Choose the currently supported PostgreSQL major version approved by the team; PostgreSQL 16 is a conservative starting point for this application.
- Use a dedicated VPC, Private Services Access, **private IP only**, and Direct VPC egress from the API, worker, and migration Job. Do not assign a public IP to the database.
- Create a dedicated application database (`agenda_db`) and separate roles for runtime application access and migrations. The migration role needs permission to create the supported extension; the runtime role should not.
- Preserve the existing `pg_trgm` migration. `pg_trgm` is a supported Cloud SQL PostgreSQL extension, but extensions can only be created by a user with the `cloudsqlsuperuser` role. Run the migration Job with the migration credential/role, not with the normal runtime credential. [Supported Cloud SQL extensions](https://cloud.google.com/sql/docs/postgres/extensions)
- Enable automated backups, point-in-time recovery, deletion protection, storage auto-increase, and a maintenance window. Test a restore into a separate instance before production launch. Cloud SQL supports automated backups and PITR. [Cloud SQL backup and recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr)

### Connection model

Use private-IP PostgreSQL connections over Direct VPC egress as the primary production design. This avoids exposing the database and does not require public authorized networks. Cloud SQL private IP requires Private Services Access; serverless workloads such as Cloud Run connect through their configured VPC path. [Configure Cloud SQL private IP](https://cloud.google.com/sql/docs/postgres/configure-private-ip)

The application must cap connections deliberately. Its current SQLAlchemy engine uses `pool_size=5` plus `max_overflow=10`, which allows up to 15 connections **per process**. With an API service, a worker pool, and a migration Job, and any API scale-out, that is excessive for an initial small Cloud SQL instance. Start with a pool such as API `pool_size=3`, `max_overflow=2`; worker `pool_size=2`, `max_overflow=0`; migration `NullPool`. Set Cloud Run maximum instances so the total worst-case pool count stays well below the instance connection limit, then adjust from observed database metrics.

### Data migration approach

The repository has a linear Alembic history and validates at migration head (`a9d2e5f8c1b3`). Recommended cutover steps:

1. Create the new empty Cloud SQL database and migration role.
2. Execute the migration Job to `upgrade head`; verify `pg_trgm` and Alembic version.
3. Quiesce local writes for the final cutover window.
4. Export the local `agenda_db` with a PostgreSQL-compatible logical dump and import it into the already-migrated Cloud SQL database, or restore data first then run migrations, according to the source schema version. Verify row counts and critical tenant data in a non-production rehearsal first.
5. Create/verify production users (with the existing `scripts/create_user.py` only after confirming it targets Cloud SQL), deploy the services, switch the custom domain/webhook, and run smoke tests.
6. Retain the local source and a logical Cloud SQL export until acceptance criteria pass. Do not run destructive commands against the source or the remote instance during this process.

## 6. Configuration and secret inventory

Place values marked **secret** in Secret Manager and mount them into the relevant workload as environment variables. Use ordinary Cloud Run environment variables only for non-sensitive deployment settings.

| Variable / setting | API | Worker | Migration Job | Frontend build/runtime | Classification |
|---|---:|---:|---:|---:|---|
| `DATABASE_URL` (new) | Yes | Yes | Yes | No | **Secret** — Cloud SQL database credentials/host |
| `JWT_SECRET_KEY` | Yes | No | No | No | **Secret** |
| `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_MODEL` | Yes | Yes | No | No | API key secret; remaining values configuration |
| `YCLOUD_API_KEY`, `YCLOUD_WEBHOOK_SIGNING_SECRET` | Yes | No | No | No | **Secret** |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | API if tracing is enabled | Worker if tracing is enabled | No | No | Keys secret; host configuration |
| `CORS_ALLOWED_ORIGINS` (new), `COOKIE_SECURE` (new), `ENVIRONMENT` (new) | Yes | No | No | No | Non-secret configuration |
| `PIPELINE_DEBOUNCE_SECONDS` | No | Yes | No | No | Non-secret configuration |
| `NEXT_PUBLIC_API_URL` | No | No | No | Yes | Public build-time setting; never place a secret in `NEXT_PUBLIC_*` |

The repository’s `.env` currently contains several unrelated or legacy settings (Azure PostgreSQL, S3, Supabase, Sentry, speech, and local-only controls). They should not be copied automatically into Google Cloud. Build the production configuration from the variables consumed by the deployed workload only.

## 7. IAM, network, and exposure controls

Use separate user-managed service accounts:

| Identity | Minimum intended access |
|---|---|
| `agenda-api-sa` | Read only its required Secret Manager versions; connect to Cloud SQL; write logs/metrics. |
| `agenda-worker-sa` | Read Azure OpenAI/observability/DB secrets; connect to Cloud SQL; write logs/metrics. It should not need YCloud send credentials unless the active WhatsApp path is intentionally moved into this workload. |
| `agenda-migrate-sa` | Read migration DB credential; connect to Cloud SQL. Restrict use to deployment automation. |
| CI/CD deployer | Push Artifact Registry images; deploy Cloud Run revisions/jobs; execute the migration Job; impersonate runtime identities as needed. It should not read application secrets. |

Keep Cloud SQL inaccessible from the public internet. Restrict the frontend service to public ingress. Keep the API public only because YCloud must reach its webhook; protect all non-webhook routes with the existing application authentication and use a custom API domain. If YCloud supplies stable source ranges, consider an edge protection policy only after confirming it will not block valid webhook traffic. Ensure the signed webhook check is mandatory in production.

## 8. Observability and operational acceptance criteria

Before production traffic is enabled, configure:

- Cloud Logging for API, worker, and migration Job; include request/correlation IDs without logging webhook payloads, tokens, or PII.
- Cloud Monitoring alerts for API 5xx rate, latency, instance restarts, worker restarts, Cloud SQL CPU/storage/connections, failed migration Jobs, and backup failure.
- An uptime check for the public API `/health` endpoint and a separate authenticated smoke test covering login, one calendar read, and one signed webhook ingestion.
- A worker health signal: record and alert on the age/count of `pending_processing` items, because an HTTP health check cannot prove an independent worker is processing messages.
- A runbook for Cloud SQL PITR restore, migration rollback policy (forward-fix preferred once a migration has run), YCloud webhook verification failure, and Azure OpenAI outage.

Acceptance is complete when a staging deployment has: (a) migrated a realistic sanitized backup, (b) processed a signed YCloud test event through the worker, (c) logged in from the production-like frontend origin with a secure cookie, (d) completed a database restore exercise, and (e) passed the existing backend suite.

## 9. Delivery plan and decisions required

### Incremental implementation plan

1. **Container and configuration foundation** — add Dockerfiles, `.dockerignore`, `.env.example`, deployment-neutral DB settings, CORS/cookie settings, startup validation, and tests for production configuration. Verify locally by building both production images and calling the API `/health` on a supplied `PORT`.
2. **Reliability/security fixes** — make the webhook fail closed in production, make candidate-work claiming recoverable, add shutdown/connection handling, and add an environment-aware health/readiness contract. Verify with focused unit/integration tests.
3. **Staging infrastructure** — provision Artifact Registry, VPC/private services access, Cloud SQL, secrets, workload identities, Cloud Run services, worker pool, migration Job, custom domains, logging, and alerts using reviewed infrastructure-as-code. Verify an end-to-end staging flow.
4. **Data rehearsal and release automation** — rehearse import and restoration with a sanitized copy, automate build → test → migration Job → deploy → smoke test, and document rollback/restore ownership.
5. **Production cutover** — take a final backup, run the validated import/migration process, deploy the known staging revision, register the YCloud webhook URL, monitor the worker queue and API errors, and retain a rollback window.

### Decisions the project owner must make

1. **Google Cloud project and region:** select a production project and a region close to Brazilian users and any required data-residency commitments. Cloud Run and Cloud SQL must be colocated.
2. **Domain topology:** choose same-origin routing versus `app.`/`api.` subdomains. This determines the final CORS and cookie-domain settings. The assessment assumes `app.example.com` + `api.example.com`.
3. **Cloud SQL availability/cost posture:** choose a single-zone baseline for an early-stage service or high availability for the production SLA. The final instance size, backup retention, and maximum Cloud Run instances follow from expected traffic and recovery objectives.
4. **Worker product choice:** approve Cloud Run worker pools for the continuous worker. If the organization does not want worker pools, the code must change to use an event-driven queue/scheduled job; deploying the current infinite loop to a scale-to-zero Cloud Run service would not be reliable.
5. **Infrastructure delivery tool:** Terraform is recommended for reviewable, repeatable environments, but this repository currently contains no IaC. Select Terraform or an organization-standard equivalent before provisioning.

## 10. Assessment conclusion

The project is a good fit for Cloud Run plus Cloud SQL: it is stateless at the HTTP layer, already uses PostgreSQL and Alembic, and its only persistent state belongs in the database. The clean deployment boundary is not a single container: it is two request-serving services, a continuous worker, and a migration Job sharing one private Cloud SQL database.

The P0 preparation work should be completed before provisioning production. Once it is complete, the remaining cloud work is a conventional staging-first rollout with no database-engine incompatibility identified in this review.
