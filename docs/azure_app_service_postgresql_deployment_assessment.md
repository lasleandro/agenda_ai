# Azure App Service and PostgreSQL Deployment Assessment

- **Assessment updated:** 2026-09-04
- **Repository reviewed:** `agenda_ai`
- **Scope:** deployment planning for the current Next.js landing/application frontend, FastAPI API and YCloud webhook, five continuous background workers, PostgreSQL database, and Azure OpenAI integration.
- **Change status:** assessment only. No Azure resources, infrastructure-as-code, application changes, database migration, or remote database changes are included.

## 1. Executive recommendation

Azure is the preferred cloud for this application. The repository already uses Azure OpenAI, the owner has Azure credits and operating experience, and the application maps cleanly to the familiar **Azure App Service + Azure Database for PostgreSQL Flexible Server** model. Azure Kubernetes Service, virtual machines, and a full Container Apps microservice split would add operational surface without solving an MVP requirement.

The recommended first production shape is:

1. **Azure App Service on Linux — unified platform:** deploy the existing production image from Azure Container Registry. Its supervisor runs Next.js as the public process and FastAPI on loopback in the same container.
2. **App Service continuous WebJobs — background processing:** run the webhook processor, candidate, passive-escalation, scheduled-task, and authentication-email pollers continuously. Keep each as an independently restartable WebJob and configure one active instance for the MVP.
3. **App Service triggered WebJob — migrations:** run Alembic once from the release artifact before promoting a schema-dependent application revision.
4. **Azure Database for PostgreSQL Flexible Server:** host `agenda_db` privately in the same region as App Service.
5. **Azure Container Registry, Key Vault, Azure Monitor, Log Analytics, and Application Insights:** image storage, secret delivery, metrics, logs, traces, and alerts.
6. **GitHub Actions or Azure DevOps + Bicep:** build once, deploy an immutable image digest to a staging slot, migrate, smoke-test, and swap into production.
7. **Direct App Service custom domain and managed certificate initially:** preserve one origin for the landing page, authenticated UI, API, and webhook. Add Azure Front Door Standard and WAF when public traffic or abuse risk justifies its fixed cost.

This design deliberately uses the Azure service the team already knows. App Service supports custom Linux containers and exposes one HTTP port; the current image already matches that constraint by exposing only Next.js and keeping FastAPI on `127.0.0.1`. Set `WEBSITES_PORT=8080`, leave `PORT=8080`, and set `INTERNAL_API_URL=http://127.0.0.1:8005`. [Configure a custom container in App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container)

The initial design also deliberately does **not** require Azure Service Bus. The repository now writes every verified webhook to an idempotent PostgreSQL `webhook_receipts` ledger and returns before domain, LLM, or outbound-provider work runs. A continuous worker claims and processes those receipts with leases and bounded retries. Service Bus becomes useful when webhook volume, database-outage isolation, or independent processor autoscaling makes a broker worth its extra code and operations.

Use **Brazil South** by default for App Service, PostgreSQL, registry, vault, and monitoring, subject to confirming SKU quota and availability in the credited subscription before provisioning. Azure Database for PostgreSQL Flexible Server is available there, including zone-redundant HA for supported production SKUs; geo-redundant backup is not currently listed for Brazil South. [Azure Database for PostgreSQL regions and capabilities](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview)

The repository is materially closer to deployment-ready than the earlier Google Cloud assessment described. It now has a multi-stage production Dockerfile, non-root runtime, process supervisor, environment-neutral `DATABASE_URL`, configurable connection pools, production startup validation, CSRF protection, secure-cookie controls, durable webhook receipts, and recoverable candidate claims. The remaining P0 work is primarily Azure packaging and infrastructure, plus a few concrete application gates identified below.

### Google-to-Azure translation

| Google Cloud assessment component | Recommended Azure component | Agenda use |
|---|---|---|
| Cloud Run unified platform | Azure App Service for Linux, custom container | Supervised Next.js + FastAPI platform |
| Cloud Run worker pool | App Service continuous WebJobs initially | Five existing database pollers |
| Cloud Run Job | Triggered WebJob initially | Alembic migration per release |
| Cloud SQL for PostgreSQL | Azure Database for PostgreSQL Flexible Server | Private `agenda_db` |
| Artifact Registry | Azure Container Registry | Immutable platform image tags and digests |
| Secret Manager | Azure Key Vault references | Database, JWT, YCloud, email, Azure OpenAI, and Langfuse secrets |
| Cloud Logging / Monitoring / Trace | Azure Monitor + Log Analytics + Application Insights | Logs, dashboards, alerts, traces |
| Cloud Tasks | Existing PostgreSQL receipt queue initially; Azure Service Bus later | Durable webhook handoff and controlled retries |
| Global external Application Load Balancer + Cloud Armor | App Service custom domain initially; Azure Front Door Standard + WAF later | TLS, optional edge routing and protection |
| Cloud Build | GitHub Actions or Azure DevOps | Build, scan, deploy, migrate, verify, and promote |

## 2. Evidence-based current-state map

| Concern | Current implementation | Azure deployment implication |
|---|---|---|
| Frontend | Next.js 16 contains the public landing page, login, and protected application. Browser calls use relative `/api/*`; the production build is standalone. | Build the existing Dockerfile and run Next.js as the App Service ingress process. Keep all browser calls same-origin. |
| API | FastAPI exposes `/health`, authenticated REST routes, and webhook routes. In the production container it binds to loopback under a supervisor. | Next.js must proxy `/api/*`, `/webhooks/*`, and the selected health/readiness path to loopback. Only `/api/*` is proxied today, so the missing webhook/health routes are a P0 fix. |
| Container | A multi-stage Debian-based image builds Next.js, installs pinned Python requirements, runs as `appuser`, and selects workload by `ROLE`. | Compatible with App Service Linux custom containers and WebJobs; use ACR managed-identity pulls and immutable digests. |
| Process lifecycle | `scripts/deploy/supervisor.py` starts Next.js and FastAPI, forwards termination signals, and exits if either child dies. | Appropriate for one App Service main container. Verify App Service stop/start and slot-swap behavior under forced child failure. |
| Webhook authentication | Outside debug mode, YCloud timestamped HMAC is required, compared in constant time, and rejected outside a configurable freshness window. | Preserve the exact raw request body through the Next.js proxy and test signatures end-to-end at the public Azure URL. |
| Webhook handoff | The request verifies then inserts an idempotent `webhook_receipts` row. Production processing is asynchronous. A Cloud Tasks adapter exists only as an unfinished skeleton. | Use the shipped PostgreSQL receipt path for the first Azure release. Do not select `cloud_tasks`; no Azure Service Bus adapter exists yet. |
| Webhook recovery | Receipt states are `received`, `processing`, `done`, `failed`, and `dead`, with claims, leases, attempts, and byte-stable event keys. | Run `webhook_processor_worker` continuously and alert on oldest receipt, repeated failure, dead receipts, and stalled claims. |
| Background work | Five infinite pollers exist: webhook processor, candidate extraction, passive escalation, scheduled tasks, and authentication email. | Package five continuous WebJobs from the same release commit. Configure one-instance execution initially and prevent staging-slot workers from running. |
| Candidate reliability | Candidate rows are claimed before processing, reclaimed after lease expiry, and deleted only after success. | App Service restarts are recoverable. Forced-stop tests must prove lease recovery and maximum-attempt behavior. |
| Database | SQLAlchemy/PostgreSQL + Alembic; current working-tree head is `d4e5f6a7b8c9`. The schema uses UUID, JSONB, partial indexes, `FOR UPDATE SKIP LOCKED`, timezone-aware timestamps, and `pg_trgm`. | Flexible Server is compatible. Allow `pg_trgm` in the `azure.extensions` server parameter before migrations. |
| Database configuration | Production requires a complete `DATABASE_URL`; local development falls back to `PG_LOCAL_*`. Pool limits are environment-controlled and `pool_pre_ping=True`; Alembic uses `NullPool`. | Use a Key Vault-backed TLS URL and small pool settings. Existing legacy `AZURE_PG_*` variables are not consumed by deployed code and must not replace `DATABASE_URL`. |
| Authentication/browser security | Production validates JWT/CORS/frontend settings, requires secure cookies and email delivery, enforces double-submit CSRF, rate-limits unsafe API requests, and disables API docs. | Preserve same-origin routing and test cookie/CSRF behavior through the custom domain and slot swap. Edge or distributed rate limiting is still needed beyond one instance. |
| Deployment artifacts | Dockerfile, `.dockerignore`, role entrypoint, supervisor, and health script exist. No Azure Bicep, pipeline, or WebJob packages exist. | Application container groundwork is complete; Azure release automation and worker packaging remain P0. |
| Observability | Standard application logs exist, but worker progress, receipt age, connection budget, and actionable Azure alerts are not complete. | Stream stdout/stderr to Log Analytics, add structured/redacted telemetry, and instrument Python/Node with OpenTelemetry/Application Insights in a later small step. |
| External services | Azure OpenAI, YCloud WhatsApp, GoDaddy SMTP, and optional Langfuse. | Keep outbound HTTPS available. Prefer managed identity for Azure OpenAI later; retain provider credentials in Key Vault meanwhile. |
| Existing Azure database settings | The local `.env` contains legacy `AZURE_PG_*` names, but the assessment did not connect to or inspect that remote database. | Inventory it read-only before deciding whether it is reusable. Never overwrite, drop, or migrate it destructively; restore/rehearse into a new staging target first. |

## 3. Target production architecture

```text
Browser / YCloud
       |
       v
Custom domain + App Service managed TLS
(optional later: Azure Front Door Standard + WAF)
       |
       v
Azure App Service: agenda-platform
  Linux custom container from ACR
  supervisor (PID 1)
    |-- Next.js (0.0.0.0:8080, public App Service port)
    |      |-- /api/* ----------+
    |      |-- /webhooks/* -----+--> FastAPI (127.0.0.1:8005)
    |      +-- readiness -------+
    +-- exits if either process fails
       |
       +-- continuous WebJobs (one active instance each)
       |     |-- webhook processor
       |     |-- candidate worker
       |     |-- passive-escalation worker
       |     |-- scheduled-task worker
       |     +-- authentication-email worker
       |
       +-- triggered WebJob: Alembic migration per release
       |
       +-- regional VNet integration
                    |
                    v
Azure Database for PostgreSQL Flexible Server
  private networking + private DNS, TLS, agenda_db

Images: Azure Container Registry       Secrets: Azure Key Vault
Build/release: GitHub Actions or Azure DevOps + Bicep
Operations: Azure Monitor + Log Analytics + Application Insights
AI: existing Azure OpenAI deployment; Microsoft Foundry is optional
```

The smallest credible production deployment is one App Service instance. This keeps continuous WebJobs singleton-like and makes database connection budgeting predictable. It also creates one failure domain: platform requests and workers share plan CPU, memory, maintenance events, and restarts. That trade-off is acceptable for a low-volume MVP only after load and restart tests show that LLM workers cannot starve the web process.

App Service WebJobs support continuous jobs on Linux containers and are intended for work such as queue polling. For Linux apps, keep Always On enabled and set `WEBSITE_SKIP_RUNNING_KUDUAGENT=false`; package an explicit executable `run.sh` for every job. WebJobs are managed by Kudu rather than the main site process, so Phase 2 must prove the current custom-container filesystem/runtime behavior instead of assuming a thin wrapper can see `/app/backend`. If a self-contained WebJob artifact would duplicate most of the image or weaken release traceability, use ingress-disabled Container Apps for the workers. [App Service WebJobs overview](https://learn.microsoft.com/en-us/azure/app-service/overview-webjobs), [how WebJobs execute](https://learn.microsoft.com/en-us/azure/app-service/webjobs-execution), [create and operate WebJobs](https://learn.microsoft.com/en-us/azure/app-service/webjobs-create)

If worker resource contention or independent scaling becomes real, move the five worker commands unchanged to one or more ingress-disabled Azure Container Apps. Continuously running processors belong in Container Apps **apps**, not Container Apps Jobs; jobs are finite tasks that stop. [Azure Container Apps jobs and apps](https://learn.microsoft.com/en-us/azure/container-apps/jobs), [background-job hosting guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/background-jobs)

### Recommended workload boundaries

| Workload | Azure host | Initial scale | Release and runtime notes |
|---|---|---:|---|
| `agenda-platform` | App Service Linux custom container | 1 instance | Existing supervisor; `WEBSITES_PORT=8080`; Always On; health check; staging slot on Standard tier or better. |
| `agenda-webhook-processor` | Continuous WebJob | 1 active instance | Explicit `run.sh`; DB/AI/YCloud access. Packaging must prove whether it can invoke image-bundled code or needs a self-contained release payload. |
| `agenda-candidate-worker` | Continuous WebJob | 1 active instance | Candidate claims are leased and recoverable. Resource-heavy LLM work makes this the first candidate to move to Container Apps. |
| `agenda-escalation-worker` | Continuous WebJob | 1 active instance | Provider/AI/DB access as required by current implementation. |
| `agenda-scheduled-task-worker` | Continuous WebJob | 1 active instance | Preserve database-backed scheduling semantics; do not replace it with a platform CRON without redesigning the domain workflow. |
| `agenda-email-worker` | Continuous WebJob | 1 active instance | SMTP and DB access; monitor retry age and terminal failures. |
| `agenda-migrate` | Triggered WebJob in the release slot | On demand, one run | `alembic -c alembic.ini upgrade head`; CI must poll for success and stop promotion on failure. |

Use WebJob settings so continuous jobs run as a single active instance. If App Service later scales to two or more instances, explicitly decide whether each worker should remain singleton or run on every instance. The current database claims make duplicate execution safer, but they do not remove capacity, provider-rate, or scheduling consequences.

### Why these services, and not the common alternatives

| Alternative | Assessment for this MVP |
|---|---|
| Azure Container Apps for everything | Technically strong, including scale-to-zero HTTP and KEDA rules, but it discards the team's App Service familiarity and introduces a second deployment model before it is needed. Reconsider for worker isolation or burst scaling. |
| Azure Functions | A natural future Service Bus consumer, but the existing workers are long-running Python polling modules rather than Functions triggers. Adapting them now adds code and a second runtime contract. |
| Azure Kubernetes Service | Unnecessary cluster, node, ingress, policy, and upgrade responsibility for one web container and several low-volume workers. |
| Azure Virtual Machines | Reintroduces OS patching, process management, capacity planning, and deployment mechanics that App Service removes. |
| Azure Container Instances | Useful for a one-off command or diagnostic container, not a preferred continuously supervised production worker platform. |
| App Service sidecars | Possible, but the platform container already supervises two critical processes. Adding five worker sidecars would tie every worker to web scale and revision lifecycle while making health and resource attribution less clear than WebJobs. |
| Azure Service Bus immediately | Valuable at scale, but the database receipt ledger already provides durable handoff, deduplication, claims, and retries. A broker now would duplicate those semantics and needs a new adapter. |
| Azure Front Door Premium | Provides WAF and private origin support, but its fixed monthly fee is disproportionate for this MVP. Start with direct App Service TLS or Front Door Standard; revisit Premium only for a concrete private-origin/security requirement. |

## 4. Webhook assessment and Azure recommendation

### What is already sound

- Production requests fail closed when the signature is missing, invalid, or too old; only explicit debug mode permits unverified callbacks.
- Signature verification uses the exact raw body and constant-time comparison.
- A deterministic event key covers all event paths, including private-agent messages, before business processing occurs.
- The endpoint returns after the verified delivery is durably recorded, so LLM and outbound WhatsApp latency is not part of acknowledgement time.
- Receipt claims, leases, retries, `dead` state, normal-message deduplication, and atomic message/debounce registration address the principal retry and crash risks identified by the Google assessment.

### Remaining Azure-specific gates

| Gate | Current state | Required outcome |
|---|---|---|
| Public route | Next.js proxies `/api/*` only. | Add server-side `/webhooks/:path*` routing to loopback FastAPI without parsing or changing the raw body. |
| Request-size control | No explicit conservative webhook body limit was found at the ingress boundary. | Reject oversized bodies before retaining them; keep the limit above documented YCloud payload sizes. |
| Readiness route | FastAPI `/health` is not reachable through current Next.js rewrites. | Expose separate shallow liveness and dependency-aware readiness paths suitable for App Service Health Check and release smoke tests. |
| Database interruption | The receipt insert depends on PostgreSQL. | Return `503` so YCloud retries; verify provider retry duration against the database RTO. Adopt Service Bus only if this coupling is unacceptable. |
| Worker operation | Processor exists as a Python module, not a packaged WebJob. | Package, deploy, start, stop, log, and recover it under App Service/Kudu automation. |
| Distributed abuse controls | Current write limiter is per process and applies under `/api/*`. | Add edge or shared-store controls for login and abusive traffic before meaningful public scale; never rely on webhook rate limiting instead of signatures/idempotency. |

### Recommended MVP lifecycle

1. YCloud posts to `https://app.example.com/webhooks/ycloud`.
2. App Service terminates TLS and sends the request to Next.js on port `8080`.
3. The server-side rewrite proxies the method, headers, and untouched request bytes to FastAPI on `127.0.0.1:8005`.
4. FastAPI applies method/content-type/body-size rules, reads the bytes once, verifies the timestamped HMAC, and derives the event key.
5. It inserts `webhook_receipts` with `ON CONFLICT DO NOTHING`, commits, and returns `200`. Invalid signatures return `401`; a failed durable insert returns `503`.
6. The webhook-processor WebJob claims due receipts with `FOR UPDATE SKIP LOCKED`, performs ingestion/agent/provider work, and records `done`, retryable `failed`, or terminal `dead`.
7. Metrics and alerts expose oldest unprocessed receipt, lease expiry, retry count, dead receipts, and acknowledgement latency.

The public response contract should stay intentionally small:

| Condition | Response | Retry meaning |
|---|---:|---|
| Invalid/expired signature, unsupported provider, or disallowed request | `4xx` | Permanent; do not process. |
| Existing event key | `200` | Already accepted; no duplicate business effect. |
| New receipt committed | `200` | Durably accepted for asynchronous work. |
| Database unavailable or commit outcome is not confirmed | `503` | Provider should retry; event key makes an uncertain prior commit safe. |
| Downstream LLM/YCloud/domain failure | Not part of request response | Receipt retry/dead-letter workflow handles it. |

### When to add Azure Service Bus

Add a Service Bus **Standard** queue only when at least one of these is measured or required:

- the webhook must remain available while PostgreSQL is unavailable;
- queue age or throughput can no longer be handled efficiently by database polling;
- the processor must scale independently from the App Service plan;
- a formal broker dead-letter queue, controlled dispatch, or operational pause is required;
- multiple consumers or event fan-out becomes a real feature.

At that point, implement an Azure queue adapter behind `WebhookTaskQueue`, use deterministic `MessageId` values, Peek Lock delivery, bounded retry, and an idempotent database receipt/consumer. Service Bus Standard supports broker-side duplicate detection, but duplicate detection does not replace consumer idempotency. [Service Bus duplicate detection](https://learn.microsoft.com/en-us/azure/service-bus-messaging/duplicate-detection), [prevent message loss and duplicate processing](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-message-loss-and-duplicates)

## 5. Deployment readiness gaps

### Already implemented in the repository

1. Multi-stage production image with pinned Python and Node dependencies, non-root runtime, and one public port.
2. Supervised Next.js + FastAPI process lifecycle and role-based commands for all five workers and migrations.
3. Deployment-neutral `DATABASE_URL`, environment-controlled pools, pre-ping, and Alembic `NullPool`.
4. Production startup checks for JWT, database, webhook, Azure OpenAI, frontend/CORS, secure cookies, and email settings.
5. Durable webhook receipt ledger, timestamp freshness, idempotent event keys, asynchronous processing, claim leases, and bounded retries.
6. Atomic normal-message/debounce registration and recoverable candidate-worker claims.
7. Same-origin browser API routing, production CSRF protection, secure cookie alignment, write throttling, and disabled production API docs.

### P0 — required before public traffic

1. **Fix ingress routes:** proxy `/webhooks/*` and health/readiness routes through Next.js to loopback FastAPI; prove raw-body signature verification through App Service.
2. **Add request bounds:** enforce webhook body size and appropriate request timeouts.
3. **Create Azure infrastructure as code:** resource groups, ACR, App Service plan/app/slot, Key Vault, VNet/subnets/private DNS, Flexible Server, Log Analytics, Application Insights, budgets, and alerts in Bicep.
4. **Package WebJobs:** prove Kudu/custom-container execution, then create five continuous `run.sh` artifacts and one triggered migration artifact, all traceable to the same release commit/image; configure `WEBSITE_SKIP_RUNNING_KUDUAGENT=false`, Always On, graceful stop behavior, and slot-specific worker controls. If this duplicates the application runtime, select Container Apps instead.
5. **Build a release pipeline:** test, build, scan, push by immutable digest, deploy to slot, run migration, smoke-test, then swap. Do not deploy mutable `latest` tags.
6. **Calculate the connection ceiling:** include FastAPI workers, all five WebJobs, slot overlap during deployment, migration, administration reserve, and any future scale-out. Set small `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` values.
7. **Complete Azure network/security setup:** private PostgreSQL access, TLS validation, managed identities, least-privilege Key Vault/ACR access, HTTPS-only, minimum TLS version, disabled FTP/basic deployment credentials where possible, and production CORS/cookie validation.
8. **Make health accurate:** App Service readiness must detect a dead FastAPI child and deployment smoke checks must test both web and API paths. Worker heartbeat/age alerts must detect a live-but-stalled loop.
9. **Rehearse database migration and restore:** use a new staging Flexible Server, never the existing remote server; validate row counts, Alembic head, `pg_trgm`, smoke flows, and PITR restoration.
10. **Define rollback:** distinguish image/slot rollback from schema rollback; prefer forward fixes and backward-compatible expand/migrate/contract changes.

### P1 — complete during staging or immediately after launch

1. Add CSP, HSTS, frame, referrer, and content-type security headers appropriate to public and authenticated routes.
2. Add shared or edge rate limiting for login and write endpoints; the current per-instance limiter is only a burst guard.
3. Add bounded timeouts and retry classification for PostgreSQL, Azure OpenAI, YCloud, SMTP, geocoding, and Langfuse.
4. Add dependency/container scanning and secret scanning to CI; keep `requirements.txt` and `package-lock.json` authoritative.
5. Define LGPD-aware retention and access policies for WhatsApp receipt payloads, logs, traces, authentication events, and backups.
6. Add OpenTelemetry/Application Insights incrementally, avoiding duplicate Node/Python telemetry from the combined container.
7. Create tested runbooks for receipt replay, worker stalls, SMTP/provider outages, secret rotation, database failover/PITR, slot rollback, and migration forward-fix.

## 6. Azure Database for PostgreSQL Flexible Server design

### Recommended baseline

- Use PostgreSQL 16 initially unless a staging restore and the full regression suite explicitly approve a newer major version. Do not combine a cloud move with an untested major-version upgrade.
- Create `agenda_db` in Brazil South, colocated with the App Service plan.
- Use private networking and private DNS. App Service reaches it through regional VNet integration; the database should not accept unrestricted public ingress. App Service VNet integration is for outbound access to private resources. [App Service VNet integration](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration)
- Create separate least-privilege runtime and migration roles. The runtime identity must not own the schema or manage extensions.
- Add `pg_trgm` to the `azure.extensions` server parameter before the migration role runs `CREATE EXTENSION`. Flexible Server supports `pg_trgm` on PostgreSQL 16. [Supported extension versions](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions), [`azure.extensions` parameter](https://learn.microsoft.com/en-us/azure/postgresql/server-parameters/param-customized-options)
- Use `sslmode=require` at minimum; prefer certificate verification once the chosen driver/certificate deployment has been exercised in the image.
- Configure 7–35 days of automated backup retention according to the agreed RPO and rehearse PITR. A restore creates a new server rather than overwriting the source. [Flexible Server backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)
- Apply a resource lock and IaC deletion safeguards to production PostgreSQL, Key Vault, and ACR.

### Availability choice

Use a burstable single-server SKU for staging and possibly for a tightly monitored lean MVP. Burstable compute does not support HA and is more susceptible to CPU-credit behavior. For real customer conversations where database downtime would also block webhook acknowledgement, prefer a General Purpose SKU with zone-redundant HA when credits permit.

Flexible Server documents these service levels: no-HA single server at 99.9%, same-zone HA at 99.95%, and zone-redundant HA at 99.99%. Zone-redundant HA uses synchronous primary/standby commits and normally provides automatic failover, but logical mistakes still require PITR. [Flexible Server creation and SLA choices](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/quickstart-create-server), [high-availability behavior](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-high-availability)

Brazil South currently supports zone-redundant HA but does not list geo-redundant backup. Treat regional disaster recovery as a separate decision: retain encrypted logical exports in an approved second location or design a cross-region strategy after the MVP's RPO/RTO and LGPD requirements are explicit.

### Connection model and budget

Start with direct TLS connections on port `5432` and small SQLAlchemy pools. Flexible Server also offers built-in PgBouncer on port `6432`, but enable it only after testing transaction-pooling behavior with migrations, session settings, and every worker. The service overview documents the built-in pooler; it is an optimization, not a substitute for bounding application pools. [Flexible Server overview](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview)

Calculate the hard upper bound as:

```text
maximum possible connections =
  App Service production instances × FastAPI process pool cap
  + five continuous WebJobs × pool cap
  + staging-slot FastAPI and any accidentally enabled staging WebJobs
  + migration connection
  + operational/admin reserve
```

With the current defaults, each Python process can request 15 connections (`pool_size=5`, `max_overflow=10`). One API plus five workers could therefore request 90 connections before staging overlap or scale-out. Do not deploy those defaults to a small server. Begin with measured values such as `DB_POOL_SIZE=2` and `DB_MAX_OVERFLOW=1`, then tune from observed checkout time, query latency, and server connection headroom.

### Data migration approach

The working tree currently has one Alembic head, `d4e5f6a7b8c9`. Verify it again from `backend/` at release time because uncommitted migration work is present.

1. Inventory the source version, size, extensions, Alembic head, tenant counts, and critical-table row counts using read-only commands.
2. Create a **new** staging Flexible Server, private networking, roles, `agenda_db`, and allowed `pg_trgm` extension.
3. Take a logical `pg_dump` without altering the source and restore it with `pg_restore` into staging.
4. Run the release artifact's migration WebJob once to `head`.
5. Run the backend suite and tenant-scoped browser/API/webhook smoke tests against staging; compare counts and key financial/scheduling aggregates.
6. Perform a PITR into another new server and verify application access and data.
7. For production, schedule a write freeze, take a final source backup/dump, repeat the rehearsed restore/migration, verify, and only then switch application/provider traffic.
8. Retain the source and exports through acceptance. Do not delete, overwrite, downgrade, or repurpose any existing Azure PostgreSQL server during this rollout.

## 7. Configuration and secret inventory

App Service settings are exposed to the main container and its WebJobs. Put secret values in Key Vault and use Key Vault references as App Service settings; keep ordinary resource names, ports, feature flags, and timing values as normal slot-scoped settings. Key Vault references use the app's managed identity and let application code continue reading ordinary environment variables. [Key Vault references for App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references)

| Configuration group | Platform | WebJobs | Migration | Storage and notes |
|---|---:|---:|---:|---|
| `DATABASE_URL` | Yes — FastAPI | All five | Yes | Key Vault; separate runtime and migration credentials if packaging allows; include TLS settings. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` | Yes | Yes | No practical effect with Alembic `NullPool` | App/slot settings, sized from the connection budget. |
| `JWT_SECRET_KEY`, `AUTH_COOKIE_NAME`, CSRF/cookie settings | Yes | Generally no | No | JWT in Key Vault; names/flags as settings. |
| `YCLOUD_WEBHOOK_SIGNING_SECRET` | Yes — webhook verification | No | No | Key Vault. Shared platform environment means Next.js can technically see it server-side; never expose it through `NEXT_PUBLIC_*`. |
| `YCLOUD_API_KEY`, template/provider settings | If API sends | Processor, escalation, scheduled worker | No | Key Vault for API key; template names as settings. |
| Azure OpenAI endpoint, deployment/model, API version | FastAPI | Candidate/processor as used | No | Non-secret settings; validate regional deployment availability and quotas. |
| `AZURE_OPENAI_API_KEY` | FastAPI | Candidate/processor as used | No | Key Vault initially. Replace with managed identity only after code and tests support token authentication. |
| SMTP host/user/password/from settings | Authentication API as used | Email worker | No | Password in Key Vault; routing configuration as settings. |
| Langfuse keys/host | Traced processes | Traced workers | No | Keys in Key Vault; host as setting. |
| `APP_ENV` / `ENVIRONMENT`, `DEBUG` | Yes | Yes | Yes | Set production explicitly; `DEBUG=false`. |
| `FRONTEND_BASE_URL`, `CORS_ALLOWED_ORIGINS`, trusted hosts | Yes | No | No | Exact HTTPS origin; no wildcard credentialed CORS. |
| `PORT`, `WEBSITES_PORT`, `INTERNAL_API_PORT`, `INTERNAL_API_URL` | Yes | No | No | `8080`, `8080`, `8005`, `http://127.0.0.1:8005`. |
| Receipt/candidate lease, batch, attempt, and poll settings | No | Relevant workers | No | Ordinary settings; tune from staging recovery tests. |
| `WEBHOOK_TASK_QUEUE`, `WEBHOOK_INLINE_PROCESSING` | Yes | Processor reads receipts | No | Use `local`/`receipt` and `false` in production. Do not select the unfinished Cloud Tasks adapter. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Instrumented processes | Instrumented workers | Optional | Key Vault or protected setting; telemetry setup is incremental. |
| `WEBSITE_SKIP_RUNNING_KUDUAGENT`, `WEBJOBS_STOPPED`, `WEBJOBS_DISABLE_SCHEDULE` | App Service platform settings | Control WebJobs | Control migration job | Keep worker-disable settings sticky on staging slots except during an intentional migration execution. |

Do not copy the root `.env` into the image, App Service, or CI. The local file contains development and legacy values, including `PG_LOCAL_*` and `AZURE_PG_*`; production code requires `DATABASE_URL`. Build a minimal environment contract per workload and never print resolved Key Vault values in pipeline logs.

Because Next.js and FastAPI share one container environment, server-side Next.js code can access settings intended for FastAPI. This is an accepted MVP trust-boundary compromise. Only values deliberately safe for browsers may use `NEXT_PUBLIC_*`, and `NEXT_PUBLIC_API_URL` should remain unset for the same-origin production build.

## 8. Identity, network, domain, and exposure controls

### Managed identities and minimum access

Use managed identities for Azure resource access and keep CI/CD separate from runtime identities:

| Identity | Minimum intended access |
|---|---|
| App Service runtime identity | `AcrPull` on the selected repository/registry scope; read only the Key Vault secrets needed by platform and WebJobs; write telemetry; no Azure resource-management permissions. |
| Deployment identity | Push to ACR, deploy App Service configuration/slots and WebJobs, start/query the migration WebJob, swap slots, and apply approved Bicep. It must not read application secret payloads. |
| Database runtime role | Connect to `agenda_db` and perform only application DML on the application schema. No role, extension, or schema-owner privileges. |
| Database migration role | Own/alter the application schema and create only pre-approved extensions. Used only by the migration WebJob. |
| Human operator groups | Separate read-only operations, deployment, database administration, and security roles through Microsoft Entra groups; require MFA and time-bound privilege where available. |

App Service can pull a private ACR image through managed identity, avoiding registry admin credentials. Pin the deployed image by digest even when a human-friendly release tag is also created. [Managed-identity ACR pulls from App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container#use-managed-identity-to-pull-image-from-azure-container-registry)

The present application uses an Azure OpenAI API key. A later hardening change can use the App Service managed identity with the narrow inference role and remove `AZURE_OPENAI_API_KEY`; Microsoft recommends keyless Microsoft Entra authentication for production model endpoints. This is a code/config migration, not an infrastructure toggle to make silently. [Microsoft Foundry model endpoints and keyless authentication](https://learn.microsoft.com/en-us/azure/ai-studio/ai-services/concepts/endpoints)

### Network layout

Use one regional VNet with distinct subnets for:

1. App Service outbound VNet integration;
2. Flexible Server private access/delegation or private endpoints, according to the selected networking mode;
3. optional private endpoints for Key Vault, ACR, and Azure OpenAI after their operational trade-offs are tested.

Associate the required private DNS zones with the VNet and verify name resolution from both the main container and WebJobs. Keep outbound HTTPS to YCloud, SMTP, geocoding, and Langfuse. Add NAT Gateway and a stable outbound IP only if a provider requires allowlisting; it is not an MVP default.

Avoid a design that makes container startup depend on private ACR/Key Vault networking before DNS and routing are proven. Start with managed identity and tightly controlled public service endpoints if necessary, then move individual services behind private endpoints with staging validation. App Service supports routing image pulls through VNet integration when ACR is network-protected. [Network-protected ACR image pulls](https://learn.microsoft.com/en-us/azure/app-service/configure-custom-container#use-an-image-from-a-network-protected-registry)

### Domain and ingress recommendation

For the lean MVP, bind one host such as `app.example.com` directly to App Service, enable HTTPS-only and a free App Service managed certificate, and redirect HTTP to HTTPS. Managed certificates are automatically renewed while their domain/DNS prerequisites remain satisfied. [App Service managed certificates](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate#create-a-free-managed-certificate) All routes remain same-origin:

| Path | Destination inside the container |
|---|---|
| `/`, landing assets, login, protected pages | Next.js |
| `/api/*` | Next.js server rewrite to FastAPI loopback |
| `/webhooks/*` | New Next.js server rewrite to FastAPI loopback |
| chosen liveness/readiness paths | Next.js or rewrite to FastAPI, with explicit semantics |

Add Azure Front Door Standard before broader public launch when global edge routing, managed WAF, more capable rate limiting, or origin shielding is worth the cost. Restrict App Service ingress to the `AzureFrontDoor.Backend` service tag **and** the specific `X-Azure-FDID` header so the default origin cannot bypass Front Door. [Restrict App Service to a specific Front Door](https://learn.microsoft.com/en-us/azure/app-service/app-service-ip-restrictions#restrict-access-to-a-specific-azure-front-door-instance), [secure Front Door origins](https://learn.microsoft.com/en-us/azure/frontdoor/origin-security)

Front Door Standard currently has a USD 35/month base fee before traffic and WAF-related charges; Premium has a much higher fixed floor and is not recommended for this MVP without a specific private-origin requirement. [Azure Front Door pricing](https://azure.microsoft.com/en-us/pricing/details/frontdoor/)

Do not cache authenticated pages, `/api/*`, or `/webhooks/*`. If Front Door caching is introduced, limit it to fingerprinted public static assets and test cookie/cache-key behavior.

## 9. Observability, recovery, and operational acceptance

### Logging and traceability

- Send App Service application/container logs and WebJob logs to a Log Analytics workspace with environment-specific retention.
- Emit structured records with service/job name, release digest, slot, request/correlation ID, internal event/receipt ID, attempt, tenant ID where safe, duration, and outcome.
- Propagate one correlation ID from webhook ingress through receipt processing, domain events, Azure OpenAI calls, outbound YCloud requests, and final receipt state.
- Never log authorization/cookie headers, secrets, database URLs, raw webhook bodies, message content, phone numbers, passwords, or full Azure OpenAI prompts/responses by default.
- Add Python and Node OpenTelemetry in separate small changes and assign distinct cloud role names. Application Insights supports OpenTelemetry for both runtimes. [Application Insights OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable)

### Initial metrics and alerts

| Area | Minimum signals and initial alert intent |
|---|---|
| Public platform | Availability test, HTTP 5xx, p95 latency, CPU/memory, restarts, health-check failures, TLS/certificate expiry, instance count. |
| Combined processes | Separate Next.js/FastAPI latency and errors; supervisor child exit; readiness failure when either critical process is unavailable. |
| Webhook ingress | Status by category, signature rejection, receipt-commit failures, body-limit rejection, p95 acknowledgement latency. |
| Receipt processor | Oldest actionable receipt age, counts by state, attempt count, expired claims, dead receipts, last successful cycle. |
| Other WebJobs | Job state/restart, last successful cycle, oldest pending candidate/escalation/email, scheduled-run lateness/failure. |
| PostgreSQL | CPU/credits where relevant, memory/storage, active/max connections, failed connections, query latency, deadlocks, backup/PITR health, HA/failover events. |
| Release | Failed tests/scans/builds, image digest deployed, migration outcome/head, smoke-test result, slot swap and rollback. |
| Dependencies | Azure OpenAI quota/429/latency/error category; YCloud and SMTP latency/outcome without payloads. |
| Cost | Subscription/resource-group budget thresholds, anomalous daily spend, forecast over credit period. |

### Required runbooks

- invalid-signature spike and YCloud signing-secret rotation;
- receipt backlog, expired claims, safe replay, and dead-receipt investigation;
- worker stopped/stalled and staging-slot worker accidentally enabled;
- Azure OpenAI throttling/outage and YCloud delivery-unknown outcomes;
- SMTP outage and authentication-email recovery;
- App Service child crash, plan saturation, slot swap, and image rollback;
- PostgreSQL connection exhaustion, HA failover, PITR into a new server, and connection-string cutover;
- migration failure and forward-fix after a partially applied schema change;
- Key Vault/ACR/managed-identity failure and secret rotation;
- credit/budget exhaustion and controlled nonproduction shutdown.

### Staging acceptance criteria

Production cutover is allowed only after staging has:

1. built the exact image with the project lock files and passed the backend/frontend suites in the `agenda` conda environment or equivalent clean CI images;
2. deployed the image digest to an App Service staging slot and passed public Next.js, proxied FastAPI, raw webhook signature, liveness, and readiness checks;
3. packaged and exercised all five continuous WebJobs, including forced termination, lease recovery, and disabled execution in the idle staging slot;
4. restored a realistic sanitized database, allowed `pg_trgm`, migrated to the recorded Alembic head, and verified tenant-scoped application flows;
5. remained inside CPU/memory and database connection budgets under representative web, webhook, worker, and email activity;
6. demonstrated duplicate webhook delivery, invalid/expired signature, malformed payload, database outage, processor crash, dead receipt, and recovery behavior;
7. completed a Flexible Server PITR into a new target and verified application access;
8. confirmed managed identity, Key Vault references, ACR pull, private DNS/VNet paths, production cookies/CSRF/CORS, `DEBUG=false`, and disabled docs/dev endpoints;
9. fired and acknowledged the initial alerts and walked through the named runbooks;
10. deployed, migrated, smoke-tested, swapped, and rolled back a no-op release without manual secret copying.

## 10. Incremental implementation roadmap

Each phase is intentionally small and ends in a verifiable gate. Provision staging before production; do not adapt code directly against the production database.

### Phase 0 — decisions and baselines

**Work**

- Confirm the credited subscription, tenant, resource naming/tags, Brazil South quotas, budget alerts, owners, and domain.
- Choose App Service S1 or a justified Premium tier; choose burstable single-server or General Purpose zone-redundant PostgreSQL.
- Approve WebJobs for the first five workers, direct App Service custom domain for the first release, Bicep, and the CI/CD platform.
- Record current tests, database version/size/head, extension list, and connection counts read-only.

**Verify:** decisions, RPO/RTO, cost ceiling, owners, and baseline evidence are recorded; no cloud data has been modified.

### Phase 1 — close application ingress gaps

**Work**

- Add `/webhooks/*` and health/readiness loopback rewrites.
- Add webhook body-size limits and accurate combined-process readiness.
- Write tests for exact raw-body signature preservation, size rejection, and dead FastAPI child behavior.

**Verify:** production-mode container tests show UI/API health, correct webhook `200/401/503`, unchanged signed bytes, and unhealthy status when either critical child is unavailable.

### Phase 2 — package the Azure release artifact

**Work**

- Add explicit `run.sh` packages for five continuous WebJobs and one triggered migration WebJob.
- Ensure every package records the same release commit/image digest and uses the correct working directory.
- Add local packaging validation without embedding `.env`, credentials, tests, or unrelated files.

**Verify:** each job starts the intended Python module under the production image/runtime; migration runs once and exits with the Alembic result.

### Phase 3 — provision staging with Bicep

**Work**

- Provision ACR, App Service plan/app/slot, managed identity/RBAC, Key Vault, VNet/private DNS, staging Flexible Server, monitoring, budgets, and alerts.
- Configure immutable image deployment, Always On, health check, TLS, slot-sticky settings, and stopped staging workers.
- Populate only approved settings and Key Vault secrets.

**Verify:** Bicep what-if is reviewed; repeat deployment is idempotent; ACR pulls and Key Vault references work without static Azure credentials.

### Phase 4 — database and workload rehearsal

**Work**

- Restore a sanitized logical dump into the new staging server and migrate to head.
- Run tests, browser smoke flows, webhook failure matrix, all workers, connection load, and PITR exercise.
- Measure App Service plan saturation and decide whether WebJobs fit or workers should move to Container Apps before launch.

**Verify:** every Section 9 staging criterion has evidence and no existing source/remote database has been changed.

### Phase 5 — production provisioning and cutover

**Work**

- Provision a separate production resource group/server/vault/app configuration from reviewed Bicep.
- Build and scan once, push an immutable digest, deploy it to the staging slot, and keep continuous WebJobs disabled there.
- Freeze writes, take the final logical backup, restore/migrate/verify, configure the domain and YCloud callback, smoke-test, then swap.

**Verify:** production uses the intended digest and migration head; representative tenant, webhook, worker, email, backup, alert, and cost signals are healthy.

### Phase 6 — post-launch hardening

**Work**

- Tune compute, pools, telemetry sampling/retention, and alerts from observed usage.
- Add Front Door Standard/WAF when public exposure warrants it.
- Move workers to ingress-disabled Container Apps or add Service Bus only when measured needs meet the Section 4 triggers.
- Move Azure OpenAI from API key to managed identity in a tested application change.

**Verify:** each added service has a measured reason, owner, budget impact, rollback, and updated runbook.

## 11. Decisions required before implementation

Record these decisions rather than leaving them implicit in portal-created resources:

| Decision | Recommended default | Why it matters |
|---|---|---|
| Azure subscription and ownership | Use the credited subscription; name a billing and technical owner. | Credits expire and quotas/policies differ by offer. |
| Region | Brazil South for application/data plane. | Lowest likely latency for Brazilian users and supported PostgreSQL zone-redundant HA; verify each SKU in the subscription. |
| Environment isolation | Separate staging and production resource groups, databases, vault secrets, settings, and monitoring dimensions. | Avoids accidental data/config sharing while allowing one subscription initially. |
| App Service tier | Standard S1 is the minimum staging candidate; production may require Premium if five WebJobs remain colocated. | Standard provides deployment slots; Basic does not. The combined Node/Python process plus five workers must fit with safe memory headroom. |
| Worker host | Continuous WebJobs for the MVP. | Lowest operational and cost overhead; revisit Container Apps on measured contention or scaling need. |
| Database tier | Burstable for staging; General Purpose zone-redundant HA for production if credits/budget allow. | Directly determines availability, latency consistency, and webhook outage exposure. |
| Database target | New Flexible Server unless the existing Azure server passes a read-only inventory and is explicitly approved. | Prevents accidental damage and avoids inheriting unknown configuration. |
| Initial ingress | Direct App Service custom domain and TLS. | Simple and low fixed cost; Front Door/WAF is a deliberate later security/cost decision. |
| Queue | PostgreSQL receipt ledger initially. | Already implemented and tested; Service Bus is a later reliability/scale adaptation. |
| IaC and CI/CD | Bicep plus the team's preferred GitHub Actions or Azure DevOps. | Makes portal configuration reproducible; choose one pipeline rather than maintaining two. |
| Release model | Immutable ACR digest → staging slot → migration → smoke → swap. | Gives a controlled, observable promotion path. |
| RPO/RTO | Explicit owner-approved values before database SKU selection. | Determines HA, backup retention, provider retry compatibility, and DR spend. |
| Domain | One production application host initially. | Keeps cookies and browser API calls same-origin and limits certificate/routing complexity. |
| Azure OpenAI authentication | Existing key through Key Vault for first release; managed identity in a subsequent tested change. | Avoids coupling deployment to an auth-client refactor while preserving a clear hardening path. |
| Telemetry retention | Short, explicit, LGPD-aware retention with restricted access. | WhatsApp and authentication data can contain personal information. |

Standard App Service tier or better is recommended because deployment slots allow the new image to warm and pass smoke checks before a swap. Microsoft documents slots as a Standard-or-higher feature and recommends deploying production changes through a nonproduction slot. [App Service deployment best practices](https://learn.microsoft.com/en-us/azure/app-service/deploy-best-practices)

## 12. Estimated monthly Azure cost

This is a planning range for **Azure infrastructure only**, in USD per month before tax. It excludes YCloud/WhatsApp fees, SMTP-provider fees, domain registration, Langfuse, engineering effort, and Azure OpenAI model tokens. Credits reduce the cash paid while they remain valid; they do not reduce measured Azure consumption.

### Basis and caveats

- Azure prices vary by agreement, currency, region, hardware generation, reservation, and date. Confirm the exact Brazil South configuration in the Azure Pricing Calculator while signed into the credited subscription.
- The estimate assumes one low-volume production application, one App Service instance, five continuous WebJobs sharing that plan, a database below 32–64 GiB, modest logs, and low internet egress.
- WebJobs have no separate compute fee, but they consume the App Service plan's CPU and memory. If they force a larger plan, their cost appears indirectly in that plan.
- A staging slot shares the App Service plan, but a separate staging database and retained test resources add cost.
- PostgreSQL HA roughly adds standby compute/storage-related cost and requires a production compute tier; exact Brazil South SKUs must be priced in the subscription.
- Azure Front Door Standard has a published USD 35/month base fee before traffic and optional protection charges. It is excluded from the lean profile.

### Recurring cost by component

| Component | Lean MVP assumption | Lean USD/month | Production-oriented assumption | Production USD/month |
|---|---|---:|---|---:|
| App Service Linux | 1 × Standard S1 candidate; platform + five WebJobs | 80–160 | Larger Standard/Premium instance if staging load requires it | 140–300 |
| PostgreSQL Flexible Server | Burstable, single server, 32–64 GiB storage, backups | 25–90 | General Purpose 2 vCore class, zone-redundant HA, backups | 250–550 |
| Azure Container Registry | Basic, low storage/egress | 5–10 | Basic or Standard if retention/throughput requires | 5–25 |
| Key Vault | Low secret-operation volume | <2 | Low secret-operation volume plus private networking if selected | 1–10 |
| Azure Monitor / Log Analytics / Application Insights | Tight retention and sampling | 0–25 | More complete telemetry and retention | 20–80 |
| DNS, bandwidth, minor platform operations | Low volume | 1–15 | Moderate MVP use | 5–30 |
| Azure Front Door + WAF | Deferred | 0 | Standard base, traffic, and a small WAF policy | 50–120 |
| Service Bus | Not deployed | 0 | Standard namespace only if Section 4 criteria are met | 10–30 |
| **Planning total** | Lean, single-region, no Front Door/Service Bus | **110–300** | HA database, stronger edge/telemetry posture | **480–1,145** |

These ranges are deliberately wider than a quote. The two dominant decisions are App Service size—because the web process and five workers share it—and PostgreSQL HA. The Azure Database pricing page shows burstable and production compute as separate choices with independent storage/backup charges; use it with the calculator rather than copying the page's default-region example. [Azure Database for PostgreSQL pricing](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/), [Azure App Service Linux pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/)

### Cost controls from day one

1. Apply tags for application, environment, owner, and cost center to every resource.
2. Create subscription and resource-group budgets at 50%, 75%, 90%, and forecasted 100% of the monthly target and credit expiry horizon.
3. Retain only required ACR images, logs, traces, and staging backups; protect release digests still eligible for rollback.
4. Stop nonproduction PostgreSQL compute when not in use if the selected development workflow permits it; storage continues billing.
5. Keep one App Service instance until load or availability evidence requires more; do not enable autoscale without reviewing singleton WebJobs and connection budgets.
6. Review Azure Cost Management weekly during staging and the first production month.
7. Price one-year savings/reservations only after a stable usage baseline; credits and commitments have offer-specific interactions.

## 13. Azure OpenAI and Microsoft Foundry

Unlike the Google Cloud plan, Azure deployment does not require an LLM-platform migration. The application already uses an Azure OpenAI endpoint, API version, deployment/model name, and API key. Keep that integration unchanged for the first infrastructure release so cloud deployment and model-client migration are separate failure domains.

The current Azure platform name and management direction is **Microsoft Foundry**. Existing Azure OpenAI resources can be upgraded to a Foundry resource while preserving the current Azure OpenAI endpoint, resource state, networking, and access configuration; Microsoft states that existing Azure OpenAI functionality does not gain an added platform charge merely from the upgrade. Foundry adds access to broader model, project, evaluation, tool, and agent capabilities, some of which have separate usage charges or availability status. [What is Microsoft Foundry?](https://learn.microsoft.com/en-us/azure/ai-foundry/azure-openai-in-azure-ai-foundry), [upgrade Azure OpenAI to Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/upgrade-azure-openai)

### Recommendation for this application

1. Keep the existing Azure OpenAI resource and API contract for the first App Service launch.
2. Place its API key in Key Vault and restrict who can read or rotate it.
3. Confirm model deployment region, quota, rate limits, content-filter behavior, latency, and token budget under representative extraction and active-agent traffic.
4. Add explicit handling/metrics for `429`, timeout, content-filter, and delivery-unknown outcomes.
5. In a later application change, add Microsoft Entra/managed-identity authentication and grant the App Service identity only model-inference access; then remove the API key after parallel verification.
6. Consider upgrading to a Foundry resource only if its broader model catalog, evaluations, tracing, projects, or agent features solve an identified need. Do not move the existing orchestration into Foundry Agent Service merely because the platform is available.
7. Use private endpoints only after App Service VNet routing and private DNS are proven in staging. Microsoft recommends private endpoints and managed identity for hardened Azure OpenAI deployments. [Azure AI security best practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/ai-security-best-practices)

The application's proposal/confirmation/execution lifecycle, tenant authorization, audit events, scheduling tools, and database state remain application responsibilities. A managed model or agent platform does not replace those controls.

## 14. Final assessment

Azure App Service plus Azure Database for PostgreSQL Flexible Server is the best fit for the current application and team. It preserves the existing combined Next.js/FastAPI production image, keeps browser traffic same-origin, uses the Azure OpenAI integration already in production shape, and gives the five database pollers a low-friction home in continuous WebJobs. This is simpler and more familiar than recreating the Google Cloud serverless design service for service.

The recommended first release is intentionally modest: one Standard-tier App Service instance, five singleton continuous WebJobs, one triggered migration WebJob, one private Flexible Server, ACR, Key Vault, and Azure Monitor. Direct App Service custom-domain TLS is enough initially; Front Door, Service Bus, Container Apps, and Foundry-specific agent hosting are escalation paths with explicit adoption triggers.

The deployment should not begin with portal provisioning. First close the missing `/webhooks/*` and health/readiness proxy paths, package and test the WebJobs, and calculate the App Service and PostgreSQL connection/resource ceilings. Then provision a new staging environment from Bicep, restore data non-destructively, rehearse migration/PITR/failure recovery, and promote an immutable image through a staging slot.

No existing Azure PostgreSQL resource should be modified until it has been inventoried read-only and explicitly selected. The safe default is a new staging server and a rehearsed logical migration. With those gates complete, Azure is not merely an acceptable alternative to Google Cloud; it is the recommended deployment target for Agenda.
