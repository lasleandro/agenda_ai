# Google Cloud MVP Deployment Assessment and Roadmap

- **Assessment updated:** 2026-09-01
- **Repository reviewed:** `agenda_ai`
- **Scope:** deployment planning for the current Next.js frontend/landing page, FastAPI API, YCloud webhook, three background workers, and PostgreSQL database.
- **Change status:** assessment only. No application, landing-page, infrastructure, database, or dependency implementation is included.

## 1. Executive recommendation

The application is a good fit for Google Cloud's managed serverless stack. The closest equivalent to the familiar Azure Web App + Azure Database for PostgreSQL model is **Cloud Run + Cloud SQL for PostgreSQL**. GKE, Compute Engine, AlloyDB, and App Engine would add cost or operational surface without solving a requirement the MVP currently has.

The recommended MVP production shape is:

1. **Global external Application Load Balancer:** one HTTPS domain, managed certificate, and path routing between the platform and webhook ingress.
2. **Cloud Run service — unified platform:** one Docker image and one Cloud Run container running two supervised processes. Next.js is the public process for the landing page, protected UI, and same-origin routing; FastAPI listens only on an internal localhost port for `/api/*` and health checks.
3. **Cloud Run service — webhook ingress:** a deliberately small public handler that verifies YCloud, durably enqueues the event in Cloud Tasks, and returns quickly. It remains separate from the unified platform.
4. **Cloud Tasks + private Cloud Run processor:** authenticated, retryable processing of webhook events away from the provider request. This is the most important adaptation for webhook reliability.
5. **Cloud Run worker pool:** one manually scaled instance initially, running the candidate, passive-escalation, and scheduled-task polling processes as separate containers. Worker pools are now generally available and available in São Paulo. [Cloud Run release notes](https://cloud.google.com/run/docs/release-notes)
6. **Cloud Run Job — migrations:** one Alembic task per release, completed before application traffic moves to a schema-dependent revision.
7. **Cloud SQL for PostgreSQL:** the private, durable system of record in the same region as Cloud Run.
8. **Artifact Registry, Secret Manager, Cloud Logging, Cloud Monitoring, and Cloud Build or GitHub Actions:** image storage, secret delivery, operations, and repeatable releases.

The unified platform uses **one combined image** containing the production Next.js build, Node runtime, FastAPI application, Python runtime, and a production process supervisor. The supervisor is PID 1, starts both processes, forwards termination signals, and terminates the container if either critical process dies. Next.js listens on Cloud Run's injected `PORT`; FastAPI listens on a fixed localhost port such as `8005`. Cloud Run requires the ingress process to follow its container contract but does not prohibit additional internal processes. [Cloud Run container contract](https://cloud.google.com/run/docs/container-contract)

Webhook, worker, and migration deployments may share a separate backend-only image so those workloads do not carry the Node/frontend runtime. That does not change the platform decision: browser frontend and authenticated API deploy as one image, container, revision, scaling unit, and rollback unit.

Use `southamerica-east1` (São Paulo) as the default region unless data-residency, provider latency, or price analysis gives a concrete reason not to. Cloud Run services, worker pools, Cloud Tasks, and Cloud SQL are available there. The load balancer is global, but its serverless backends and database remain regional. [Cloud Run worker-pool locations](https://cloud.google.com/run/docs/deploy-worker-pools), [Cloud SQL regions](https://cloud.google.com/sql/docs/postgres/region-availability-overview)

The repository is **not ready for a public production deployment today**. The main blockers are not domain-model changes: they are reproducible containers, environment-neutral database configuration, production authentication/browser controls, bounded database connections, reliable background claims, and a webhook fast path that cannot execute LLM or outbound-provider work synchronously.

### Azure-to-Google Cloud translation

| Familiar Azure component | Recommended Google Cloud component | Agenda use |
|---|---|---|
| Azure Web App | Cloud Run service with one combined container image | Supervised Next.js + FastAPI platform; separate webhook services |
| Azure Database for PostgreSQL | Cloud SQL for PostgreSQL | `agenda_db` |
| Azure Container Registry | Artifact Registry | Versioned combined-platform and backend-operational images |
| Azure Key Vault | Secret Manager | Database, JWT, YCloud, Azure OpenAI, and Langfuse secrets |
| Azure Service Bus queue | Cloud Tasks | Reliable HTTP delivery for webhook processing |
| Azure Functions / WebJobs | Cloud Run Job / worker pool | Alembic migrations / continuous pollers |
| Application Insights | Cloud Logging, Monitoring, Error Reporting, Trace | Logs, alerts, dashboards, request tracing |
| Application Gateway / Front Door | Global external Application Load Balancer + optional Cloud Armor | TLS, domain and path routing, edge protection |

## 2. Evidence-based current-state map

| Concern | Current implementation | Deployment implication |
|---|---|---|
| Frontend | Next.js 16 contains the public landing page, login, and protected application. Browser API calls use `NEXT_PUBLIC_API_URL` or relative `/api/*`; `next.config.ts` already defaults rewrites to local port `8005`. | Build Next.js into the combined platform image and make it the container's ingress process. Browser calls remain relative and Next proxies `/api/*` to the internal FastAPI process on localhost. |
| API | FastAPI exposes `/health`, authenticated REST routes, and two webhook routes. CORS is localhost-only. | Build FastAPI into the same platform image and run it as a second supervised process for API traffic. Extract the public webhook fast path into its own service so webhook bursts and provider latency remain isolated. |
| Webhook authentication | Outside `DEBUG=true`, the YCloud adapter rejects missing or invalid timestamped HMAC signatures and compares signatures in constant time. | This is a sound base. Production startup must also reject a missing signing secret, and verification should enforce timestamp freshness to reduce replay risk. |
| Webhook processing | `/webhooks/ycloud` and `/webhooks/whatsapp/{provider_key}` process events before replying. Customer messages write to PostgreSQL; private agent messages can call Azure OpenAI, execute confirmations, and send a YCloud response in the provider request. | This is the largest production risk. The provider callback must verify and durably enqueue only; all domain/LLM/outbound work must run asynchronously. |
| Webhook idempotency | Normal customer messages have a unique `(provider_key, provider_message_id)` constraint. Delivery updates are monotonic. Private agent-channel messages are handled before durable deduplication. | Add an envelope/event receipt ledger that covers every event path, especially private-agent messages and retries after partial failure. |
| Ingestion transaction | A normal message is committed first; the `pending_processing` debounce upsert is committed separately. A retry that sees the duplicate returns before recreating a missing debounce row. | Make message persistence and downstream-work registration atomic, or add a deterministic recovery path. |
| Background processing | Three infinite polling loops exist: `candidate_worker` (5 seconds), `passive_escalation_worker` (10 seconds by default), and `scheduled_task_worker` (30 seconds by default). | Run all three continuously. An initial one-instance, three-container Cloud Run worker pool matches the code and avoids three public endpoints. |
| Candidate reliability | `candidate_worker` deletes and commits its `PendingProcessing` row before extraction. | A termination or extraction failure can lose work. Introduce claim state plus a recoverable lease/retry before public launch. |
| Database | SQLAlchemy/PostgreSQL + Alembic; current migration head is `f2b9a1c8d3e7`. The schema uses UUID, JSONB, partial indexes, `FOR UPDATE SKIP LOCKED`, timezone-aware timestamps, and `pg_trgm`. | Cloud SQL for PostgreSQL is compatible. `pg_trgm` is supported, but its creation needs a migration identity with `cloudsqlsuperuser`. |
| Database connections | Every process currently allows `pool_size=5` plus `max_overflow=10`, or up to 15 connections. | Every unified platform instance includes one API process; platform scale-out plus three workers and the processor can exhaust a small Cloud SQL instance. Externalize and reduce pool limits before deployment. |
| Authentication/browser security | JWT auth uses an HTTP-only `SameSite=Lax` cookie, but it is not marked `Secure`; a missing JWT secret creates a random process-local key. There is no explicit CSRF control or production login/write rate limit. | Fail startup when secrets are absent, use secure cookies, add CSRF protection, keep same-origin routing, and rate-limit login/write paths. |
| Configuration | Runtime settings are read directly from the root `.env`; database settings are limited to `PG_LOCAL_*`. | Introduce validated environment-specific settings and a production database connection path. Do not copy the local `.env` wholesale. |
| Deployment artifacts | No production Dockerfile, `.dockerignore`, Cloud Build definition, CI workflow, or infrastructure-as-code is present. | Reproducible builds and reviewed deployment definitions are P0 work. `start_server.py` remains local-development-only. |
| Observability | Standard Python logging and a shallow `/health` endpoint exist; worker progress and queue age are not exported. | Add structured/redacted logs, request/event correlation, queue-age metrics, and actionable alerts before cutover. |
| PostgreSQL features | UUIDs, `JSONB`, timezone-aware timestamps, partial indexes, `FOR UPDATE SKIP LOCKED`, and `pg_trgm`. | Select a supported Cloud SQL PostgreSQL version and enable `pg_trgm` before/through migration. |
| External services | Azure OpenAI, YCloud WhatsApp, Langfuse. | Keep credentials in Secret Manager; allow controlled outbound HTTPS egress. |
| Local configuration | `database.py` only builds a DSN from `PG_LOCAL_*`; `.env` is loaded from the project root. | Add production `DATABASE_URL`/Cloud SQL connection handling and validate required configuration at startup. |

## 3. Target production architecture

```text
Browser / YCloud
       |
       v
Global external Application Load Balancer + managed TLS + optional Cloud Armor
       |
       +-- /* except /webhooks ----------> Cloud Run: unified platform
       |                                    one image / one container
       |                                    supervisor (PID 1)
       |                                      |-- Next.js (0.0.0.0:$PORT)
       |                                      |      |
       |                                      |      +-- /api/* proxy
       |                                      |             |
       |                                      |             v
       |                                      |        FastAPI (127.0.0.1:8005)
       |                                      +-- monitors both processes
       +-- /webhooks/* -----------------> Cloud Run: webhook ingress
                                               |
                                    verify + durable enqueue
                                               v
                                         Cloud Tasks
                                               |
                                      OIDC-authenticated call
                                               v
                                 Cloud Run: webhook processor
                                 (internal ingress, no public URL path)
                                               |
                                               v
Unified platform FastAPI process --------+
Webhook processor -----------------------+--> Cloud SQL for PostgreSQL
Cloud Run worker pool -------------------+    private IP, `agenda_db`
  - candidate worker                     |
  - passive escalation worker            |
  - scheduled task worker                |
Cloud Run migration Job -----------------+

Images: Artifact Registry        Secrets: Secret Manager
Build/release: Cloud Build or GitHub Actions + Terraform
Operations: Cloud Logging, Monitoring, Error Reporting, Trace
```

### Recommended request and workload boundaries

| Workload | Entry command | Scaling / availability | Notes |
|---|---|---|---|
| `agenda-platform` service | One supervisor starts Next.js on `0.0.0.0:$PORT` and Uvicorn on `127.0.0.1:8005`. | Scale to zero initially; set low maximum instances and tested concurrency. Both processes always scale, deploy, and terminate together. | Next serves landing/UI and proxies relative `/api/*` plus health routes over localhost. FastAPI is not independently public and does not handle provider callbacks. |
| `agenda-webhook-ingress` service | A narrow FastAPI/ASGI entrypoint | Minimum one instance is recommended for real webhook traffic; short timeout and bounded concurrency. | It needs the signing secret and Cloud Tasks enqueue permission, but no database or Azure OpenAI credential. |
| `agenda-webhook-processor` service | Authenticated task-handler entrypoint | Scale from zero; Cloud Tasks controls dispatch rate and retries; cap instances from the DB connection budget. | Internal ingress, OIDC authentication, durable idempotency, and all existing event dispatch/business work. |
| `agenda-workers` worker pool | Three containers with the existing candidate, passive-escalation, and scheduled-task commands | Exactly one worker-pool instance for the MVP; worker pools scale manually. | One pool reduces fixed MVP overhead. Split processes into separate pools later only when resource isolation or independent scaling is justified. |
| `agenda-migrate` job | `alembic -c backend/alembic.ini upgrade head` from the correct working directory | One task; fail the release if it does not complete. | Run with the migration DB role before traffic reaches code requiring the new schema. |

Only the unified platform's Next.js process receives external requests and must listen on the injected `PORT`. FastAPI listens on loopback and is reached only through the container-local proxy. The supervisor must not report the platform ready until both processes are healthy, and it must exit non-zero if either critical process exits unexpectedly so Cloud Run replaces the instance. Jobs terminate after bounded work; worker pools are for continuous non-request work, have no public endpoint, and do not autoscale. [Cloud Run container contract](https://cloud.google.com/run/docs/container-contract), [worker-pool resource model](https://cloud.google.com/run/docs/resource-model)

The consolidation is an MVP operational choice, not a claim that the workloads are identical. It removes one public service/backend and makes same-origin routing natural, but frontend and API share an image, runtime environment, filesystem, CPU/memory allocation, instance count, logs, revision rollout, service identity, lifecycle, and failure domain. If later metrics show API load, release cadence, image size, or security boundaries require independence, split the combined Dockerfile into frontend/backend images and deploy separate services without changing the webhook architecture.

### Why these services, and not the common alternatives

| Alternative | Assessment for this MVP |
|---|---|
| App Engine | Viable, but Cloud Run maps more directly to the existing containers and supports services, jobs, and continuous worker pools in one model. |
| GKE | Unnecessary cluster, networking, patching, and autoscaling complexity for several small stateless workloads. Reconsider only if future workloads require Kubernetes-specific scheduling or service-mesh features. |
| Compute Engine | Would recreate server/patch/process supervision responsibilities that Cloud Run removes. |
| Cloud Run functions | Suitable for isolated functions, but the existing FastAPI application, shared domain modules, and multiple routes are cleaner as containers. |
| Firebase Hosting | Could host a separate static landing site, but the landing page is currently part of the same Next.js app. Splitting it now creates two release paths without an MVP requirement. |
| Pub/Sub | Better for event fan-out and streaming. The current need is one controlled, retryable HTTP consumer, for which Cloud Tasks is simpler and provides queue-level rate control. |
| Cloud Scheduler | Useful later for invoking periodic work, but it does not replace the debounce, retry, and per-tenant scheduling state already stored in PostgreSQL. |
| AlloyDB | Unneeded for current scale and cost posture. Cloud SQL supports the PostgreSQL features used by the application. |

## 4. Webhook assessment and recommended design

### What is already sound

- Production requests fail closed when the signature is absent or invalid; only explicit `DEBUG=true` accepts an unverified callback.
- The adapter signs the exact raw body and uses constant-time HMAC comparison.
- Regular WhatsApp messages use a provider-namespaced unique identifier, so ordinary provider retries do not create duplicate `messages` rows.
- Tenant resolution is derived from the provisioned WhatsApp number and rejects unknown numbers rather than selecting a default tenant.
- Delivery-state updates do not regress a message from a later state to an earlier one.

These controls should be preserved. The deployment problem is what happens **after** signature verification, not whether Cloud Run can expose an HTTPS URL.

### Current production risks

| Risk | Current behavior | Failure mode |
|---|---|---|
| Slow acknowledgement | Private-agent events may run an LLM turn, database mutations, and a YCloud send before returning `200`. | YCloud times out/retries while the first request is still executing. |
| Partial commit | Message insert and debounce scheduling use separate commits. | The message can exist without a future extraction job; retry sees a duplicate and does not repair it. |
| Incomplete deduplication | Agent-channel events bypass the normal message insert before acting. | A retry can repeat an answer, proposal confirmation, mutation attempt, or outbound message. |
| Lost background work | Candidate worker deletes the pending row before extraction completes. | A termination after the delete loses the extraction trigger. |
| Replay window | The signature contains a timestamp, but current verification does not reject an old signed timestamp. | A captured valid request can be replayed indefinitely unless deduplication catches that event path. |
| Shared capacity | Webhook and browser API use one FastAPI service and database pool. | Provider bursts or slow agent turns consume normal application capacity and DB connections. |
| Database dependency | The provider receives success only after current database/business handling. | A Cloud SQL incident directly becomes a webhook-delivery incident. |

### Recommended webhook lifecycle

1. YCloud sends the exact request to `/webhooks/ycloud` through the load balancer.
2. `agenda-webhook-ingress` enforces request method/content type and a conservative body-size limit, reads the raw bytes once, verifies the HMAC, and rejects a timestamp outside a documented tolerance.
3. It derives a deterministic task identity from provider + provider event/message ID. If the envelope has no stable ID, use a versioned SHA-256 digest of the verified raw body.
4. It creates a Cloud Task containing the required raw payload and provider metadata. It returns `2xx` only after Cloud Tasks accepts the task. A duplicate task is also acknowledged; a transient enqueue failure returns `503` so YCloud can retry.
5. Cloud Tasks calls `agenda-webhook-processor` using OIDC and an identity allowed to invoke only that service. The processor is not exposed through the public load balancer.
6. The processor records/claims a durable `webhook_receipt` with a unique provider event key, then parses and dispatches the event. Receipt state should distinguish received, processing, completed, retryable failure, and terminal failure.
7. Message persistence and registration of downstream work occur in one database transaction. Private-agent work is covered by the same event receipt before any LLM call, mutation, or outbound send.
8. The processor returns `2xx` only after the idempotent unit completes. Retryable failures return non-`2xx`; Cloud Tasks applies bounded exponential retry and dispatch-rate limits.

Google documents Cloud Run as a webhook target and recommends Cloud Tasks or Pub/Sub when processing must be handed off before provider timeouts. Cloud Tasks is at-least-once: duplicate execution is rare but expected, so the receipt and domain operations must remain idempotent. [Cloud Run webhook guidance](https://cloud.google.com/run/docs/triggering/webhooks), [Cloud Tasks delivery semantics](https://cloud.google.com/tasks/docs/dual-overview), [duplicate execution guidance](https://cloud.google.com/tasks/docs/common-pitfalls)

### Webhook response and retry contract

| Condition | Ingress response | Expected result |
|---|---:|---|
| Valid signature and task created | `204` | Provider stops retrying; task owns delivery. |
| Valid duplicate already enqueued/received | `204` | No duplicate business effect. |
| Missing/invalid/stale signature | `401` | Reject and record a metric without logging payload or secret. |
| Malformed or unsupported request envelope | `400` | Terminal provider input error. |
| Cloud Tasks unavailable or enqueue fails transiently | `503` | Provider retry remains the safety net. |
| Processor has a retryable DB/provider/LLM error | Task handler `5xx` | Cloud Tasks retries under queue policy. |
| Processor recognizes an already-completed receipt | Task handler `204` | Duplicate delivery completes harmlessly. |

Do not rely on source-IP allowlisting as the primary authentication control unless YCloud publishes stable, complete egress ranges. HMAC verification remains authoritative. Cloud Armor can provide conservative path-specific throttling, first in preview mode, but limits must allow legitimate provider bursts and retries. [Cloud Armor rate limiting](https://cloud.google.com/armor/docs/rate-limiting-overview)

### Webhook verification gates

Before changing the provider's production URL, staging must prove:

- valid, invalid, missing, and stale signatures;
- exact raw-body verification, including whitespace/encoding differences;
- duplicate event, concurrent duplicate, and out-of-order delivery handling;
- successful enqueue followed by an ingress response interruption;
- Cloud SQL unavailable while ingress continues to enqueue;
- task retry after processor termination at each transaction boundary;
- private-agent duplicate does not repeat mutation or outbound reply;
- customer-message insert and debounce registration are atomic;
- queue rate limiting protects Cloud SQL and Azure OpenAI;
- no raw webhook body, phone number, token, or message text appears in normal logs;
- an alert fires for oldest-task age and receipts stuck in processing.

## 5. Deployment readiness gaps

These are implementation gates for a public MVP. They are roadmap items, not changes made by this assessment.

### P0 — required before public traffic

1. **Reproducible containers:** add a tested multi-stage platform Dockerfile that builds both runtimes into one final image, plus `.dockerignore`, pinned lock files, and a non-root runtime user. A backend-only image may serve webhook/worker/job workloads. `start_server.py`, `uvicorn --reload`, and the Cloudflare development tunnel must remain local-only.
2. **Production entrypoint and supervision:** use a production-grade PID 1/supervisor to start Next.js on `0.0.0.0:$PORT` and FastAPI on loopback, forward `SIGTERM`, reap children, fail the container when either process dies, and expose combined readiness. Add separate webhook-ingress and webhook-processor entrypoints without copying business logic.
3. **Validated configuration:** introduce explicit `ENVIRONMENT`, production startup validation, a non-secret `.env.example`, and a deployment-neutral database connection configuration. Production must fail startup when JWT, database, YCloud, or required Azure OpenAI settings are missing.
4. **Webhook handoff and idempotency:** implement the lifecycle in Section 4, including timestamp freshness, durable receipt state, atomic message/debounce writes, and idempotent private-agent handling.
5. **Recoverable candidate claims:** replace delete-before-process with a claimed/leased state that can be retried after termination. Verify process restarts and concurrent claims.
6. **Database connection budget:** externalize SQLAlchemy pool settings, enable `pool_pre_ping`, use `NullPool` for migrations, cap unified-platform instances/Cloud Tasks dispatch, and verify the worst-case connection calculation against the selected Cloud SQL tier.
7. **Same-origin browser deployment:** keep browser API calls relative and configure a server-only Next.js rewrite/proxy to the internal FastAPI process on `localhost`; do not expose that internal URL through `NEXT_PUBLIC_*`. Make CORS environment-specific and never use wildcard credentialed CORS.
8. **Authentication hardening:** set `Secure`, `HttpOnly`, and appropriate `SameSite` cookie attributes; implement CSRF protection on state-changing browser endpoints; align cookie deletion attributes; rate-limit login and write endpoints; disable or restrict `/docs` in production.
9. **Release-safe migrations:** build one immutable backend image, run its Alembic migration job once, and stop deployment if migration or schema verification fails. Use backward-compatible expand/migrate/contract changes when zero-downtime compatibility matters.
10. **Basic operations:** structured/redacted logs that identify the originating process, request/event IDs, combined startup/liveness/readiness, supervisor and child-exit metrics, graceful SIGTERM handling, and initial alerts must exist before cutover.

### P1 — complete during staging or immediately after launch

1. Add security headers (CSP appropriate to the landing/app assets, HSTS at the edge, frame restrictions, referrer and content-type policies).
2. Add bounded timeouts/retries for transient Cloud SQL connections and all external HTTP calls; distinguish safe retry from delivery-unknown outcomes.
3. Add software dependency and container-image vulnerability scanning to CI; keep `requirements.txt` and the frontend lock file authoritative.
4. Define retention for raw WhatsApp payloads and operational logs according to LGPD needs; minimize stored/logged message content.
5. Add worker liveness/progress signals and a manual replay/recovery runbook for failed receipts and queues.

## 6. Cloud SQL for PostgreSQL design

### Recommended baseline

- Create one Cloud SQL for PostgreSQL instance in `southamerica-east1`, colocated with Cloud Run and Cloud Tasks. PostgreSQL 16 is a conservative first compatibility target; confirm the final supported major version with a staging import and full test suite rather than upgrading during production cutover.
- Use a dedicated VPC, Private Services Access, **private IP only**, and Direct VPC egress with private-ranges routing from the unified platform, processor, worker pool, and migration Job. The webhook ingress does not need VPC/database access.
- Create `agenda_db` and separate least-privilege roles for application runtime and migrations. The migration identity may install the supported extension; runtime identities must not have schema-owner or extension privileges.
- Preserve the `pg_trgm` migration. Cloud SQL supports `pg_trgm`, but extension creation requires membership in `cloudsqlsuperuser`. [Cloud SQL PostgreSQL extensions](https://cloud.google.com/sql/docs/postgres/extensions)
- Enable automated backups, point-in-time recovery (PITR), retained backups after deletion where appropriate, deletion protection, automatic storage increase, and a controlled maintenance window. PITR configuration differs depending on whether the console or IaC creates the instance, so Terraform must set it explicitly. [Cloud SQL restore and PITR](https://cloud.google.com/sql/docs/postgres/backup-recovery/restore)
- Rehearse a PITR restore into a **new** instance and validate application access before launch; a configured backup that has never been restored is not a verified recovery plan.

### Availability decision

For staging, a single-zone instance is sufficient. For production carrying real customer conversations, **regional high availability is recommended** if the budget allows it: the primary and standby use synchronous replication across two zones and Cloud SQL can fail over automatically. If MVP budget requires single-zone production, document the longer recovery time and accept that restoration is manual; keep Cloud Tasks retry retention and rate limits long enough to absorb a database interruption. [Cloud SQL high availability](https://cloud.google.com/sql/docs/postgres/high-availability)

### Connection model

Use private-IP PostgreSQL connections over Direct VPC egress. This avoids public authorized networks; external HTTPS to YCloud, Azure OpenAI, and Langfuse can continue through normal Cloud Run egress when only private ranges are routed through the VPC. Add Cloud NAT with a static address only if an external provider later requires fixed outbound IP allowlisting. [Connect Cloud Run to Cloud SQL](https://cloud.google.com/sql/docs/postgres/connect-run), [configure Cloud SQL private IP](https://cloud.google.com/sql/docs/postgres/configure-private-ip)

The current engine permits 15 connections **per Python process**. One platform FastAPI process, one webhook processor, and the three worker containers could therefore request 75 connections before any platform scale-out. The deployment must calculate:

```text
maximum possible connections =
  unified platform max instances × FastAPI process pool cap
  + processor max instances × processor pool cap
  + candidate worker pool cap
  + escalation worker pool cap
  + scheduled worker pool cap
  + release/administration reserve
```

Start with deliberately small pools (for example, 2–5 total connections per process), `pool_pre_ping=True`, bounded pool checkout time, `NullPool` for Alembic, a low processor dispatch rate, and low Cloud Run maximum instances. The exact values are outputs of staging load tests and the selected Cloud SQL tier, not constants to copy from this assessment.

### Data migration approach

The repository currently reports one Alembic head, `f2b9a1c8d3e7`. For an MVP-sized local database, `pg_dump`/`pg_restore` is simpler than introducing Database Migration Service unless the measured cutover window is unacceptable.

1. Record source PostgreSQL version, Alembic revision, extensions, database size, and row counts for critical tenant tables.
2. Create an empty staging Cloud SQL database and required roles/extensions through reviewed automation.
3. Rehearse the selected order: restore a logical dump, then run the same immutable image's migration Job to `head` (or migrate an empty schema then data-load only, if explicitly scripted and verified).
4. Run backend tests and tenant-scoped smoke checks against the restored staging copy; compare row counts and key aggregates.
5. Perform and validate a staging PITR restore.
6. For production, take a final source backup, pause application/webhook writes for the documented cutover window, repeat the rehearsed import/migration, and verify before switching DNS/provider configuration.
7. Keep source data and logical exports intact through acceptance. Do not perform destructive operations on the existing local or Azure PostgreSQL databases as part of this rollout.

## 7. Configuration and secret inventory

Store sensitive values in Secret Manager and expose each secret only to the workload that consumes it. When secrets are injected as environment variables, pin an explicit Secret Manager version in the Cloud Run revision rather than using `latest`; rotate by deploying a new revision, verify it, then retire the old version. [Cloud Run secret configuration](https://cloud.google.com/run/docs/configuring/services/secrets)

| Configuration group | Unified platform container | Webhook ingress | Processor | Workers | Migration | Classification |
|---|---:|---:|---:|---:|---:|---|
| Database URL/host/user/password, pool settings | Yes — consumed by FastAPI | **No** | Yes | Yes | Yes | Credentials secret; pool values configuration |
| `JWT_SECRET_KEY`, `AUTH_COOKIE_NAME` | Yes — consumed by FastAPI | No | Only if agent handling requires it | No | No | JWT secret; name configuration |
| `YCLOUD_WEBHOOK_SIGNING_SECRET` | No | Yes | No | No | No | Secret |
| `YCLOUD_API_KEY` and template configuration | If platform API sends | No | Yes | Escalation/scheduled processes | No | API key secret; template values configuration |
| Azure OpenAI settings | Active-agent FastAPI process | No | Private-agent processing | Candidate process | No | API key secret; endpoint/model configuration |
| Langfuse settings | If traced | No | If traced | Candidate if traced | No | Keys secret; host configuration |
| `ENVIRONMENT`, log level, CORS, trusted hosts, cookie/CSRF settings | Yes | Environment/log/trusted-host subset | Environment/log subset | Environment/log subset | Environment/log subset | Non-secret |
| Cloud Tasks project/location/queue/audience | No | Yes | Expected audience | No | No | Non-secret resource identifiers |
| Debounce, escalation, and scheduled-task timings | No | No | No | Relevant process only | No | Non-secret |
| Internal API URL, for example `INTERNAL_API_URL` | Next uses `http://127.0.0.1:8005` | No | No | No | No | Non-secret; never expose through `NEXT_PUBLIC_*` |
| `NEXT_PUBLIC_API_URL` | Prefer omitted for same-origin | No | No | No | No | Public build-time value; never a secret |

One container means one injected environment, mounted filesystem, and service identity. Next.js and FastAPI processes can technically access the same environment variables, mounted secret files, and `agenda-platform-sa` metadata credentials even when only FastAPI is intended to consume them. This is an accepted consolidation trade-off. Production code must never serialize server environment values into the browser bundle; only deliberately public values may use the `NEXT_PUBLIC_*` prefix. Reconsider the one-container design if the frontend later executes untrusted server-side code or needs a materially narrower trust boundary.

The current `.env` also contains legacy or future-service values for Azure PostgreSQL, storage providers, speech providers, Supabase, and Sentry. Do not copy it into Google Cloud or build images. Create a workload-by-workload production inventory from settings actually consumed by each deployed process, and keep `.env` for local development only.

## 8. IAM, network, domain, and exposure controls

Use separate user-managed service accounts and grant permissions to individual secrets/resources where practical:

| Identity | Minimum intended access |
|---|---|
| `agenda-platform-sa` | Read API/JWT/DB secrets, connect to Cloud SQL, and write logs/metrics. No task enqueue or migration privilege. Both Next.js and FastAPI processes run inside the same container and can access this identity and the container's mounted/injected secrets. |
| `agenda-webhook-ingress-sa` | Read only the YCloud signing secret and create tasks in the selected queue. No DB, YCloud-send, JWT, or Azure OpenAI access. |
| `agenda-webhook-processor-sa` | Be invoked only by the Cloud Tasks caller; read processor DB/YCloud/Azure OpenAI secrets as required; connect to Cloud SQL. |
| `agenda-workers-sa` | Read DB plus the provider/AI secrets required by each worker container; connect to Cloud SQL. A later split into multiple pools should also split identities. |
| `agenda-migrate-sa` | Read only the migration credential and connect to Cloud SQL; database role owns schema/extension work. Restrict job execution to release automation. |
| `agenda-cloud-tasks-caller-sa` | Invoke only `agenda-webhook-processor`; no secret or database access. |
| CI/CD deployer | Push images, deploy revisions/jobs/pools, update service configuration, and impersonate runtime identities as required. It must not read application secret payloads. |

### Domain and ingress recommendation

Use one production host initially, for example `app.example.com`:

| Path | Backend |
|---|---|
| `/webhooks/*` | Webhook-ingress serverless NEG |
| All other paths, including `/api/*` and platform health | Unified-platform serverless NEG; Next.js proxies API/health paths to the container-local FastAPI process |

This preserves relative browser URLs, avoids cross-origin cookies, and lets the landing page, application, and API ship as one Cloud Run revision. CSRF protection is still required because same-origin routing does not eliminate every browser-origin threat.

Use a **global external Application Load Balancer** with a Google-managed certificate. Direct Cloud Run domain mapping is preview, is not recommended by Google for production, and is not available in `southamerica-east1`; the load balancer is therefore a requirement for a production custom domain in São Paulo, not optional architecture decoration. [Cloud Run custom-domain options](https://cloud.google.com/run/docs/mapping-custom-domains)

Configure the unified platform and webhook ingress as `internal-and-cloud-load-balancing`, and disable their default `run.app` URLs after validation so clients cannot bypass load-balancer routing or Cloud Armor. FastAPI binds to loopback and has no independent Cloud Run URL. The processor uses internal ingress plus authenticated Cloud Tasks invocation. Cloud SQL remains private-IP-only. [Cloud Run ingress controls](https://cloud.google.com/run/docs/securing/ingress), [Cloud Armor with serverless backends](https://cloud.google.com/armor/docs/integrating-cloud-armor)

Keep DNS at the current registrar if preferred; Cloud DNS is not required. Add Cloud Armor first in preview/observe mode, then enforce tuned rules for obvious abuse and login rate limiting. Do not add CDN caching to authenticated/API/webhook responses; CDN can be evaluated later for immutable public landing assets.

## 9. Observability, recovery, and operational acceptance

### Logging and traceability

- Emit structured JSON with service/revision, request ID, provider key, hashed or internal event ID, task attempt, tenant ID where safe, duration, and outcome.
- Never log signing/API/JWT secrets, authorization/cookie headers, raw webhook bodies, phone numbers, message text, password inputs, or database URLs.
- Propagate one correlation ID from webhook ingress to Cloud Task, receipt, domain events, outbound provider call, and task completion.
- Apply explicit log retention and access controls; production payload investigation should be an audited exception, not normal logging.

### Initial metrics and alerts

| Area | Minimum signals |
|---|---|
| Webhook ingress | Request count by status, signature rejection count, enqueue failures, p95 acknowledgement latency, cold starts |
| Cloud Tasks/processor | Queue depth, oldest task age, dispatch/retry count, processor 5xx, terminal/stuck receipt count |
| Workers | Process restarts, last successful iteration, `pending_processing` oldest age/count, escalation backlog, scheduled-run delay/failure |
| Unified platform | Next.js and FastAPI process 5xx/latency separately, supervisor/child exits, combined readiness, instance count, authentication failures/rate limits, landing/application availability |
| Cloud SQL | CPU, memory where available, active/max connections, disk and WAL growth, replication/failover, backup/PITR health |
| Release | Failed builds, vulnerability findings, failed migration Job, failed smoke test, revision rollback |
| External dependencies | Azure OpenAI and YCloud latency/error categories without request/response payloads |

Create an unauthenticated shallow liveness endpoint that proves only that the process can serve, and a protected or internal readiness check that verifies critical dependencies. A worker process needs a progress/heartbeat signal; a process that is alive but no longer advancing queue state is unhealthy.

### Required runbooks

- webhook signature rejection spike and signing-secret rotation;
- Cloud Tasks backlog and safe pause/resume/rate reduction;
- replay of a failed receipt without duplicate domain effects;
- worker stuck/restart and recovery of expired claims;
- Cloud SQL failover/PITR restore and application reconnection;
- forward-fix or revision rollback after a migration;
- YCloud outage/delivery-unknown and Azure OpenAI outage;
- secret rotation and suspected credential disclosure.

### Staging acceptance criteria

A production cutover is allowed only after staging has:

1. built the immutable combined-platform image and backend operational image, then run the existing test suites;
2. migrated a realistic sanitized database at the current Alembic head;
3. served landing, login, protected navigation, and representative CRUD flows through the production-like load balancer/domain;
4. passed the complete webhook verification gates in Section 4, including DB outage and private-agent duplicate tests;
5. processed all three worker categories and demonstrated recovery after forced termination;
6. stayed within the database connection budget under a representative concurrency test;
7. completed a Cloud SQL PITR restore and application verification;
8. demonstrated alerts and runbooks with named owners;
9. confirmed `DEBUG=false`, dev mock routes absent, `/docs` policy applied, secure cookies/CSRF working, and default `run.app` bypass disabled.

## 10. Incremental implementation roadmap

Each phase is intentionally small and has an explicit verification gate. Do not provision production first and adapt the code against it.

### Phase 0 — decisions and baselines

**Work**

- Confirm project ownership/billing, `southamerica-east1`, staging/production project separation, domain, and budget alerts.
- Choose production Cloud SQL single-zone versus regional HA and document RPO/RTO.
- Approve the one-image/two-process unified-platform service, separate webhook path, Cloud Tasks handoff, one three-container worker pool, Terraform, and the CI/CD system.
- Record current local database version/size/head and a baseline test result without altering data.

**Verify:** decisions are recorded, owners are named, required APIs/quotas are identified, and no production resource has been created ad hoc.

### Phase 1 — deployment foundation

**Work**

- Add one multi-stage platform Dockerfile that builds Node and Python artifacts into one non-root runtime image; add `.dockerignore`, environment validation, and health/shutdown behavior. Add a backend-only image for non-platform workloads if the size/attack-surface benefit justifies it.
- Define the production PID 1/supervisor, localhost API proxy, child failure policy, combined probes, aggregate resource allocation, process-tagged logs, and shared environment/service identity.
- Add deployment-neutral Cloud SQL settings and explicit pool configuration.
- Make platform API routing same-origin through the Next ingress; harden cookies, CSRF, CORS, trusted hosts, `/docs`, and security headers.
- Add unit/integration tests for production configuration failures and browser security contracts.

**Verify:** the combined platform image builds reproducibly; one container serves landing/UI and proxies `/api/*` to FastAPI; forced termination of either process terminates/restarts the container; a failed API startup keeps the platform unready; targeted tests and existing backend/frontend checks pass.

### Phase 2 — webhook and worker reliability

**Work**

- Create the narrow webhook ingress, Cloud Tasks publisher, authenticated processor, receipt/idempotency state, and atomic message/debounce transaction.
- Add timestamp freshness and full duplicate/replay tests.
- Move private-agent LLM/provider work out of the provider callback.
- Add recoverable leases/retries for candidate processing and progress signals for all workers.

**Verify:** every webhook gate in Section 4 passes locally/in integration; forced termination cannot lose or duplicate a business action; queue dispatch can be limited independently of incoming callbacks.

### Phase 3 — staging infrastructure

**Work**

- Provision with Terraform: APIs, Artifact Registry, service accounts/IAM, Secret Manager references, VPC/Private Services Access, Cloud SQL, Cloud Tasks, Cloud Run services/worker pool/job, load balancer/certificate, logging, alerts, and budgets.
- Deploy by immutable image digest, not mutable `latest` tags.
- Set ingress/default-URL restrictions only after health and load-balancer routing have been verified.

**Verify:** Terraform plan is reviewed; a clean apply can reproduce staging; least-privilege checks confirm each identity cannot access unrelated secrets/services.

### Phase 4 — data and release rehearsal

**Work**

- Import a sanitized realistic copy, run migrations, compare data, and exercise all critical product paths.
- Execute concurrency/connection tests and tune service maxima, queue dispatch, worker resources, and SQL pools.
- Perform PITR restore, revision rollback, failed migration, webhook backlog, and secret-rotation drills.
- Automate build → scan/test → push → migrate → deploy → smoke-test, with a manual production approval gate.

**Verify:** all staging acceptance criteria in Section 9 pass and the exact cutover/runback procedure is timed and documented.

### Phase 5 — production cutover

**Work**

- Freeze the approved source revision and infrastructure plan; take and verify the final source backup.
- Pause writes/webhook registration for the rehearsed migration window, import/migrate/verify, then deploy the tested image digests.
- Switch DNS/load-balancer and YCloud callback only after API, DB, workers, and task processor pass smoke checks.
- Observe webhook acknowledgement, queue age, worker progress, API errors, database connections, and external-provider failures continuously through the agreed stabilization window.

**Verify:** signed production test events complete once end-to-end; secure login and representative tenant flows pass; alerts remain healthy; rollback authority remains available.

### Phase 6 — post-launch hardening

**Work**

- Tune Cloud Armor from observed traffic, retention, autoscaling limits, queue dispatch, and Cloud SQL capacity.
- Review costs after a full usage cycle; remove unused secrets/revisions/images under a retention policy.
- Decide from metrics whether to split frontend/API services, split the three worker containers, keep a warm unified-platform instance, add Cloud CDN for public assets, or move any polling flow to an event-driven design.

**Verify:** the first operational review records incidents, costs, capacity headroom, security findings, and the next prioritized changes.

## 11. Decisions required before implementation

| Decision | Recommendation | Trade-off / consequence |
|---|---|---|
| Region | `southamerica-east1` | Lowest likely latency for Brazilian users and colocated managed services; Tier 2 regional pricing must be budgeted. |
| Environment layout | Separate staging and production GCP projects | Stronger IAM, quota, billing, and accidental-change isolation than one project with naming conventions. |
| Platform layout | One combined image/container with supervised Next.js and FastAPI processes | Closest to the familiar Azure Web App container model; frontend/API share runtime, secrets, resources, logs, scaling, rollback, and failure domain. |
| Domain topology | One host with load-balancer path routing | Simplifies browser cookies/CORS and matches the integrated landing page; load balancer adds a fixed cost and Terraform resources. |
| Webhook compute | Dedicated ingress + Cloud Tasks + private processor | More resources than one endpoint, but provider acknowledgement no longer depends on PostgreSQL, LLM, or outbound YCloud latency. |
| Cloud SQL production availability | Regional HA for real customer traffic | Higher recurring cost; single-zone is acceptable only with explicitly accepted downtime/RTO. |
| Worker layout | One worker pool instance with three containers | Lower MVP overhead; a pool-level issue affects all three. Split when metrics justify isolation. |
| Infrastructure definition | Terraform | Reviewable/repeatable and suited to load balancer, IAM, VPC, Cloud SQL, and Cloud Run dependencies. |
| Release runner | Existing GitHub Actions preference, otherwise Cloud Build | Either is valid; choose one source of deployment authority and use workload identity rather than stored service-account keys. |
| Data cutover | Rehearsed logical dump/restore | Simplest for an MVP-sized DB; use Database Migration Service only if measured downtime exceeds the accepted window. |
| RPO/RTO and retention | Decide before sizing/configuration | Drives HA, PITR window, task retry duration, backups, and operational cost. |

## 12. Cost posture

Do not estimate the bill from request volume alone. The likely recurring cost drivers are:

1. Cloud SQL, especially regional HA, storage/backups, and chosen machine tier;
2. the always-running worker-pool instance and its three container allocations;
3. one warm webhook-ingress instance if minimum instances is set to one;
4. global external load balancer and Cloud Armor policy/rules;
5. logging volume and retention;
6. Cloud Run unified-platform and processor usage, Cloud Tasks operations, Artifact Registry, build minutes, and network egress.

Start with small measured allocations, low maximum instances, queue dispatch limits, log exclusions for noisy low-value records, and budget alerts. Each platform instance allocates one CPU/memory envelope shared by Next.js and FastAPI, so size it for their aggregate peak and observe per-process use inside the container. Do not reduce reliability by removing the durable webhook handoff; if cost must be cut, first evaluate a single-zone database, zero-minimum platform, and right-sized worker resources with the corresponding availability trade-offs documented.

A quantified estimate is in Section 14.

## 13. Final assessment

Cloud Run plus Cloud SQL is the recommended Google Cloud equivalent of the team's Azure pattern. For the MVP, Next.js and FastAPI should be built into one `agenda-platform` image and run as two supervised processes in one Cloud Run container: Next.js is the ingress and same-origin proxy, while FastAPI remains loopback-only. This consolidation does not require a domain rewrite, PostgreSQL features are compatible, and the three existing pollers have a suitable managed home in generally available Cloud Run worker pools.

The webhook remains intentionally separate from the unified platform. Its HTTPS exposure and signature base are good, but synchronous private-agent work, incomplete event-path deduplication, a two-commit ingestion gap, and delete-before-process worker semantics make retries unsafe. The recommended ingress → Cloud Tasks → private processor design is the central MVP deployment adaptation. After that reliability work and the P0 production controls are verified in staging, the remaining deployment is a conventional managed-container, managed-PostgreSQL rollout.

## 14. Estimated monthly cost (Google Cloud only)

This estimate covers **Google Cloud infrastructure only**. It excludes WhatsApp/YCloud provider fees, Azure OpenAI token consumption (which stays on the Azure invoice unless the model provider is also migrated — see Section 15), one-time data-migration effort, applicable Brazilian taxes, and any free-trial or committed-use discount credits.

### Basis and caveats

- **Prices are public list prices** for region `southamerica-east1` (São Paulo), which carries a Tier-2 premium of roughly 40–50% over `us-central1`. Treat every figure as an order-of-magnitude planning number, not a quote.
- The estimate assumes **MVP traffic**: one active tenant plus onboarding, low request volume, WhatsApp bursts measured in messages-per-minute rather than per-second, and a database well under 10 GB.
- Cloud Run **worker pools bill for allocated CPU and memory continuously** (no scale-to-zero). This, together with Cloud SQL and the load balancer, forms the fixed monthly floor regardless of traffic.
- The final numbers are outputs of the Phase 4 staging load tests in Section 10, not constants to copy forward.
- **Worker count correction:** Sections 1–3 describe three pollers. The repository currently runs **four** continuous workers — `candidate_worker`, `passive_escalation_worker`, `scheduled_task_worker`, and `email_delivery_worker` (authentication email delivery). The worker pool must host four containers, and the connection-budget math in Section 6 must use four worker processes, not three.

### Recurring cost by component

| Component | Configuration assumed | Lean MVP (USD/mo) | Standard production (USD/mo) |
|---|---|---:|---:|
| Cloud SQL for PostgreSQL | Lean: `db-custom-1-3840` (1 vCPU / 3.75 GB), single-zone, ~20–30 GB SSD, automated backups + PITR. Standard: same tier with **regional HA** (synchronous standby). | 60–85 | 130–180 |
| Cloud Run worker pool | One always-on instance, four poller containers, ~1 vCPU / 2 GiB allocated continuously (instance-based billing). | 70–95 | 80–110 |
| Cloud Run — unified platform | Next.js + FastAPI, 1 vCPU / 1–2 GiB. Lean: scale-to-zero. Standard: `min-instances=1` warm. | 5–15 | 25–50 |
| Cloud Run — webhook ingress | One warm small instance (`min-instances=1`), 0.5 vCPU / 512 MiB, short timeout. | 8–15 | 8–18 |
| Cloud Run — webhook processor | Scale-to-zero, dispatched by Cloud Tasks, low volume. | 2–6 | 3–10 |
| Cloud Run — migration job | Seconds of execution per release. | <1 | <1 |
| Global external Application Load Balancer | One forwarding rule (~$0.025/hr) plus modest request/data processing. | 18–25 | 20–30 |
| Cloud Armor | Deferred in the lean profile. Standard: one policy + a small rule set + request charges. | 0 | 8–25 |
| Cloud Tasks | Within the 1M free operations/month tier at MVP volume. | 0 | 0–2 |
| Artifact Registry | A handful of multi-stage image versions under a retention policy. | 1–3 | 2–6 |
| Secret Manager | ~15 active secret versions plus access operations. | 1–3 | 1–4 |
| Cloud Logging + Monitoring | Near the 50 GiB/month free logging tier with exclusions for noisy low-value logs. | 0–12 | 10–35 |
| Network egress (excl. WhatsApp) | Small JSON to Azure OpenAI, Langfuse, and clients; database traffic is in-VPC and free. | 2–10 | 5–20 |
| Cloud NAT | Not needed with Direct VPC egress. Add only if a provider later requires a fixed outbound IP. | 0 | 0–35 |
| Cloud Build | Within the free build-minute tier, or GitHub Actions free minutes. | 0 | 0–10 |
| **Estimated monthly total** | | **~US$ 170–235** | **~US$ 320–450** |

### Headline figures

- **Lean MVP** (single-zone database, platform scaled to zero, no Cloud Armor, Direct VPC egress): **roughly US$ 200/month**.
- **Standard production** (regional-HA database, one warm platform instance, Cloud Armor enabled, higher log retention): **roughly US$ 350–420/month**.
- The single largest lever is **Cloud SQL regional HA** (about +US$ 70–100/month). The second is the **always-on worker pool**; right-sizing its CPU/memory or, later, moving a poller to an event-driven trigger is the main way to reduce it without losing reliability.

### Not included

- **Azure OpenAI usage** — billed by Azure on token volume. If the agent and extraction pipeline stay on Azure OpenAI, that cost is unchanged by this migration and does not appear on the Google Cloud bill. Egress for those calls is the only Google-side cost, already counted above.
- **YCloud / WhatsApp** — per-message and per-conversation fees, excluded by request.
- **One-time migration and staging** — the staging environment duplicates the worker pool, Cloud SQL, and load balancer for the duration of Phases 3–4; budget a second near-full monthly total while staging is live.

## 15. Managed LLM platform on Google Cloud (Azure OpenAI equivalent)

Google Cloud's equivalent of Azure OpenAI / Azure AI Foundry is **Vertex AI**. The mapping is close enough that the application's current `openai`-plus-`instructor` structured-output pattern has a direct counterpart, and migrating the model provider is **optional** — the deployment in this document assumes Azure OpenAI is kept and reached over normal Cloud Run egress.

### Azure-to-Vertex AI translation

| Azure AI concept | Vertex AI equivalent |
|---|---|
| Azure AI Foundry portal / project | Vertex AI Studio (prompt design, comparison, evaluation) in the Google Cloud console |
| Azure OpenAI model deployment | A Vertex AI model endpoint: Google first-party (Gemini) or a partner model served as Model-as-a-Service |
| Foundry model catalog | **Vertex AI Model Garden** — Gemini, Imagen, Veo, plus partner models including Anthropic Claude, Meta Llama, Mistral, AI21, Qwen, and open-weight models |
| `AzureOpenAI` client (via the `openai` SDK) | `google-genai` / Vertex AI SDK for Gemini; the Anthropic SDK's `AnthropicVertex` client for Claude on Vertex |
| Provisioned Throughput Units (PTUs) | Vertex AI **Provisioned Throughput** (reserved, committed capacity) |
| Azure OpenAI "On Your Data" / Azure AI Search | Vertex AI **RAG Engine** and Vertex AI Search for grounding |
| Content filters | Vertex AI safety filters plus **Model Armor** |
| Key Vault–stored API key | Vertex AI authenticates with **IAM / service-account credentials**, not a static key — no secret to store or rotate for first-party and MaaS models |
| Batch deployments | Vertex AI **batch prediction** |
| Fine-tuning | Vertex AI supervised tuning (Gemini) and tuning for selected partner models |

### Relevance to this application

- **Structured extraction** (`instructor`) works with Gemini on Vertex AI and with Claude on Vertex AI, so the propose-confirm-execute extraction pipeline could move without a rewrite of its output-schema approach.
- **No API key to manage.** Vertex AI calls from Cloud Run use the workload's service-account identity. This removes the `AZURE_OPENAI_*` key from the Secret Manager inventory in Section 7 for any model moved to Vertex, and replaces it with an IAM role (`roles/aiplatform.user`) on `agenda-webhook-processor-sa` and `agenda-workers-sa`.
- **Regional availability matters.** Gemini models are available from `southamerica-east1` and from a multi-region global endpoint, keeping model traffic in-region. **Partner models (Claude, Llama) served as MaaS are currently offered mainly from US and EU regions**; using Claude on Vertex from São Paulo means cross-region calls and a data-residency decision. Confirm the exact region list for the chosen model before committing.
- **If Azure OpenAI is kept**, the only change for Google Cloud is allowing outbound HTTPS egress to the Azure endpoint (already assumed in Sections 6 and 8) and keeping the `AZURE_OPENAI_*` values in Secret Manager. No Vertex AI resource is required.
- **Decision to record** (add to Section 11 if pursued): keep Azure OpenAI, or migrate extraction/agent inference to Vertex AI (Gemini in-region, or Claude on Vertex cross-region). This is independent of the compute and database migration and should not block the MVP cutover.
