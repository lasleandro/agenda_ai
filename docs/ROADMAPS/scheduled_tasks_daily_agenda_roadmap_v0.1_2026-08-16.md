# Scheduled Tasks: Daily Agenda Roadmap v0.1 — 2026-08-16

**Status: proposed for review; no implementation started.**

## 1. Goal and first-release outcome

Build a tenant-aware scheduled-tasks panel for platform administrators and
ship its first task: once each morning, the platform sends the instructor a
WhatsApp summary of that tenant's agenda for the local day.

The first release is successful when a platform administrator can enable the
daily agenda for one tenant, choose its local send time, and see the latest
delivery state; the instructor then receives exactly one chronological list
containing both customer appointments/classes and confirmed instructor events.
No instructor can configure this task yet.

## 2. Scope

### In scope

- One task type: `daily_agenda_summary`.
- One configuration per tenant (`Professional`).
- Platform-admin-only enable/disable and local-time configuration.
- The tenant's `Professional.timezone` determines both the due time and which
  calendar day is summarized.
- WhatsApp delivery from `Professional.agent_phone` to the instructor's known
  `Professional.assistant_phone`, matching the existing private agent channel.
- Confirmed/active customer schedule occurrences plus confirmed
  `InstructorEvent` rows, merged chronologically.
- Durable execution state, bounded retries, provider-status reconciliation,
  delivery history, and an auditable configuration trail.
- A provider-neutral WhatsApp boundary used by existing inbound/outbound flows
  and the new scheduled sender, with YCloud retained as the first adapter.
- Empty-day delivery so the message is also a reliable daily operational
  heartbeat.
- pt-BR message content and admin labels.

### Out of scope for v0.1

- Instructor self-service configuration.
- Arbitrary cron expressions, multiple times per day, weekly/monthly rules, or
  user-authored task definitions.
- Additional task types, email/SMS channels, broadcast recipients, or customer
  reminders.
- LLM-generated summaries. Rendering is deterministic.
- A general workflow automation engine, Celery, or Redis.
- Simultaneously operating different WhatsApp providers per tenant. The first
  abstraction supports one configured provider at a time while preserving the
  provider identity on persisted messages and runs.
- A production deployment migration in this planning pass, and any write to
  the Azure remote PostgreSQL database.

## 3. Product decisions for the MVP

1. **Send one message even when the agenda is empty.** Use a clear
   `Nenhum compromisso agendado para hoje.` body. This makes enablement and
   delivery observable instead of making silence ambiguous.
2. **A local date gets at most one scheduled delivery intent per tenant.**
   Disabling/re-enabling or changing the time after a run was created must not
   create a second morning summary for the same day.
3. **Late enablement is not backfilled.** If an admin enables the task after
   today's configured time, the first automatic run is the next local day.
   A future explicit “Enviar agora” action can be planned separately.
4. **Schedule edits race safely with delivery.** The agenda snapshot is built
   when the run is claimed. Changes committed before that point appear in the
   message; later changes do not trigger another daily summary.
5. **Only active, fully provisioned tenants run.** An inactive tenant, missing
   sender number, missing instructor destination number, invalid timezone, or
   unapproved WhatsApp template is shown as ineligible and is never silently
   treated as another tenant.
6. **The message remains operational and concise.** It includes times,
   customer/participant names for classes, event title/type for instructor
   events, and optionally the known place. It excludes notes, income, phone
   numbers, and internal IDs.
7. **The current manual “hoje” answer and the scheduled message share the same
   read model and formatter.** This closes the existing gap where
   `agent_channel._handle_hoje()` lists classes but not instructor events and
   prevents two versions of “today's agenda” from drifting.

Proposed output:

```text
Agenda de hoje — 16/08

07:00 — Aula — Ana e Bruno — Clube Central
10:30 — Evento — Clínica de saque — Arena Norte
15:00 — Aula — Carlos

3 compromissos: 2 aulas e 1 evento.
```

For an event without a title, use the existing pt-BR event-type label. For an
item without a place, omit the final place segment rather than displaying an
empty placeholder.

## 4. What already exists and what must change

### Reuse

- `Professional` is the tenant root and already stores `timezone`,
  `assistant_phone`, `agent_phone`, `status`, and an unused
  `daily_summary_time` string defaulting to `07:00`.
- `services/scheduling.py::list_schedule_occurrences()` is the authoritative
  tenant-scoped projection for one-off appointments, recurring classes, and
  occurrence overrides.
- `services/instructor_events.py::list_events()` already filters events by
  `professional_id`, overlap range, and status.
- `chat/agent_channel.py` already authorizes the private instructor channel
  and formats deterministic schedule answers.
- `chat/ycloud_provider.py` centralizes outbound YCloud calls, while the
  passive-escalation subsystem demonstrates durable queued/retry state and
  `FOR UPDATE SKIP LOCKED` processing.
- `/api/admin/tenants`, `/admin/select-tenant`, and the existing assistant
  settings controls provide the platform-admin authorization and optimistic
  UI patterns to follow.

### Gaps to close

- `daily_summary_time` has no enabled state, validation boundary, admin API,
  admin UI, execution history, or worker.
- The field is a `String(5)`, while due-time comparisons should use a database
  `TIME` value or an equally strict schema contract.
- Schedule projection uses a global `America/Sao_Paulo` `TIMEZONE` constant in
  important paths despite `Professional.timezone` being tenant data. The new
  task must not calculate one tenant's day using another tenant's timezone.
- The manual `hoje` path only reads `list_schedule_occurrences()` and therefore
  omits instructor events.
- `list_schedule_occurrences()` documents a cross-window override limitation:
  an occurrence rescheduled from another original date into today may not
  appear in a query for today. That correctness gap must be closed before a
  daily summary can be treated as authoritative.
- Existing `send_text_message()` sends free-form text and intentionally hides
  errors. A durable scheduled sender needs a provider method that returns the
  queued message ID and raises failures to the run state machine.
- YCloud delivery-status events are currently ignored by `normalize_event()`.
  Scheduled runs need those webhooks reconciled separately from inbound chat
  ingestion.
- The provider boundary promised by the original project brief is incomplete:
  `agent_channel.py`, `ingestion.py`, `passive_escalation.py`, tests, and the
  dev mock import YCloud functions or `NormalizedMessage` directly.
- The dev mock builds YCloud-shaped JSON and then re-enters provider parsing.
  Application tests should construct canonical WhatsApp events instead, while
  adapter contract tests alone own YCloud fixtures.
- `Message.provider_message_id` is globally unique without a provider key.
  That can collide or lose provenance during a future provider migration.

## 5. Recommended architecture

Keep the design narrow: one generic task-configuration table, one durable run
table, a deterministic daily-agenda service, and a one-tick processor that can
be called by either a polling worker or a managed scheduler.

```text
Platform admin panel
        |
        v
Admin-only task API -----> ScheduledTask (tenant configuration)
                                  |
                         due-task processor
                                  |
                 claim/create one ScheduledTaskRun
                                  |
                 tenant-scoped daily agenda service
                    /                         \
     schedule occurrences              instructor events
                    \                         /
                     deterministic formatter
                                  |
                    approved WhatsApp template
                                  |
             WhatsApp provider port + status webhook
                                  |
                         YCloud adapter (v0.1)
                                  |
                     ScheduledTaskRun status
```

### 5.1 Daily-agenda read model

Add a small `services/daily_agenda.py` module rather than teaching
`list_schedule_occurrences()` that every calendar occupant is a class. It
should:

1. Load the requested `Professional` by the supplied `professional_id`.
2. Resolve and validate `ZoneInfo(professional.timezone)`.
3. Calculate `[local midnight, next local midnight)` for the target date.
4. Read schedule occurrences with the same `professional_id` and target date.
5. Read overlapping confirmed instructor events with the same
   `professional_id` and UTC/local boundaries.
6. Normalize both into a typed `DailyAgendaItem` (`kind`, source ID, start/end,
   label, participants, place), sort by absolute start time, and render pt-BR.

This service is read-only and receives the tenant ID explicitly. The worker,
manual WhatsApp command, and future preview endpoint all call it; none should
query `Appointment` or `InstructorEvent` independently.

An event that starts before midnight and continues into the target day is
included because it overlaps that day's interval. Its displayed time should
make the continuation clear instead of showing an incorrect new start time.

### 5.2 No LLM in the delivery path

The scheduled job must not call Azure OpenAI. The source records are already
structured, and deterministic output is cheaper, testable, repeatable, and
does not expose agenda data to an unnecessary processor.

### 5.3 General WhatsApp provider boundary

The application must depend on WhatsApp capabilities, not YCloud functions or
payload shapes. YCloud remains the first concrete adapter, but it is selected
at the composition boundary and can later be replaced without changing agenda,
agent, escalation, ingestion, or scheduled-task business logic.

Recommended package shape:

```text
backend/app/integrations/whatsapp/
  contracts.py              canonical requests, results, events, errors
  provider.py               WhatsAppProvider protocol
  registry.py               strict configured-provider factory
  ycloud.py                 YCloud HTTP, signature, payload mappings
```

Keep this as one shallow integration package. Do not create separate abstract
classes for every message type or build a plugin framework before a second
provider exists.

#### Canonical data contracts

Move `NormalizedMessage` out of `ycloud_provider.py` and replace it with
provider-neutral, typed contracts:

- `WhatsAppMessageEvent`: provider key/message ID, direction, sender,
  recipient, text, timestamp, optional contact name, and optional raw payload.
- `WhatsAppDeliveryUpdated`: provider key/message ID, optional external ID,
  canonical status (`accepted`, `sent`, `delivered`, `read`, `failed`), event
  timestamp, and sanitized provider error fields.
- `WhatsAppTextRequest`: sender, recipient, body, and optional external ID.
- `WhatsAppTemplateRequest`: sender, recipient, logical template key, language,
  named/ordered parameters, external ID, and optional TTL.
- `WhatsAppSendResult`: provider key, provider message ID, external ID, and
  accepted timestamp/status.

Raw vendor payloads may be retained in the existing message/audit storage for
forensics, but they stop at the integration boundary. Business services never
index `whatsappInboundMessage`, YCloud event names, headers, or response JSON.

#### Provider protocol

The minimal `WhatsAppProvider` protocol should expose capabilities already
needed by the platform:

```python
class WhatsAppProvider(Protocol):
    key: str

    def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> bool: ...
    def parse_webhook(self, raw_body: bytes) -> list[WhatsAppEvent]: ...
    def send_text(self, request: WhatsAppTextRequest) -> WhatsAppSendResult: ...
    def send_template(self, request: WhatsAppTemplateRequest) -> WhatsAppSendResult: ...
```

`WhatsAppEvent` is the closed union of canonical inbound/echo message and
delivery-update types currently supported. Media, interactive buttons, contact
sync, and provider onboarding do not enter the interface until an actual
feature requires them.

Use domain-level exceptions such as `WhatsAppRetryableError`,
`WhatsAppPermanentError`, and `WhatsAppDeliveryUnknownError`. YCloud/httpx
errors are translated inside the adapter; worker and escalation services make
retry decisions without importing `httpx` or knowing vendor error codes.
Provider send methods always expose failures. Whether an immediate agent reply
logs-and-continues or a durable worker persists/retries is application policy,
not a second pair of provider methods such as today's
`send_text_message()`/`send_text_message_or_raise()`.

#### Selection, configuration, and template mapping

- Add `WHATSAPP_PROVIDER=ycloud` to `.env.example` and resolve it through a
  strict allowlisted factory. Missing/unsupported values fail at startup in
  non-development environments.
- Resolve the configured adapter at API/worker composition roots and pass the
  `WhatsAppProvider` port into lower-level services. Avoid a hidden service
  locator inside business functions; explicit injection keeps tests and future
  provider replacement straightforward.
- Keep vendor credentials under vendor-prefixed variables such as
  `YCLOUD_API_KEY` and `YCLOUD_WEBHOOK_SIGNING_SECRET`.
- Business code sends the logical template key `daily_agenda`; the YCloud
  adapter maps that key to its approved vendor template name/language from
  YCloud-prefixed configuration. A future adapter can map the same logical
  request to its own template identifier.
- Do not store provider clients or the “current tenant” in mutable globals.
  A stateless configured adapter may be shared, but every request contains its
  explicit sender/recipient and every application query remains tenant-scoped.

#### Webhook boundary

Expose a provider-aware endpoint such as
`POST /webhooks/whatsapp/{provider_key}`. The route must:

1. Resolve `provider_key` through the strict registry; unknown providers get
   `404` without payload processing.
2. Verify the signature using that adapter before JSON parsing or persistence.
3. Normalize one raw webhook into zero or more canonical events.
4. Dispatch messages to provider-neutral ingestion/agent routing and delivery
   updates to provider-neutral reconciliation.
5. Acknowledge idempotently and quickly.

Keep `/webhooks/ycloud` as a temporary compatibility alias during rollout,
delegating to the same YCloud adapter, then remove it only after the registered
callback has moved and staging/production checks pass. Production continues to
fail closed when the selected provider's signing secret is absent.

#### Persistence provenance

- Add `provider_key` to `Message` and make message deduplication unique on
  `(provider_key, provider_message_id)` instead of assuming globally unique
  vendor IDs.
- Store `provider_key` on `ScheduledTaskRun` beside provider/external message
  IDs so delivery webhooks remain reconcilable after a provider switch.
- Backfill existing messages as `ycloud`; this is provenance only and must not
  reprocess historical messages.
- A provider change affects new sends/webhooks only. Historical rows remain
  attributed to the adapter that created them.

#### Application migration

- `agent_channel.py` receives a canonical message and calls an injected or
  resolved `WhatsAppProvider.send_text()`; it no longer imports YCloud.
- `passive_escalation.py` sends canonical text requests and handles generic
  provider exceptions.
- `ingestion.py` ingests canonical events only. Provider parsing moves entirely
  to the webhook adapter/route.
- The dev mock constructs `WhatsAppMessageEvent` directly and calls the
  canonical ingestion function; it no longer fabricates a YCloud webhook.
- Business tests use a small fake/recording provider. Only YCloud adapter tests
  know YCloud headers, JSON fields, endpoints, or error payloads.

This migration must preserve current agent replies and passive escalations
before the scheduled-task sender is added. That makes the first new scheduled
message a consumer of the abstraction rather than another source of coupling.

## 6. Data model and migration

### 6.1 `scheduled_tasks`

Create a tenant-scoped configuration table:

| Field | Purpose |
|---|---|
| `id` | UUID primary key. |
| `professional_id` | Required FK and tenant boundary. |
| `task_type` | Initially only `daily_agenda_summary`. |
| `enabled` | Admin-controlled switch; default `false`. |
| `local_time` | Strict SQL `TIME`, minute precision. |
| `channel` | Fixed to `whatsapp` in v0.1. |
| `consent_confirmed_at` | When instructor opt-in was confirmed before proactive messaging. |
| `consent_confirmed_by_user_id` | Platform admin who recorded that confirmation. |
| `enabled_at` | Used to prevent same-day backfill after late enablement. |
| `updated_by_user_id` | Last platform admin to change configuration. |
| `created_at`, `updated_at` | Audit timestamps. |

Constraints:

- Unique `(professional_id, task_type)`.
- `task_type` and `channel` check constraints for the currently supported
  values.
- An enabled task must have recorded consent at the service-validation layer.
- Add an index starting with `professional_id`; all task lookups and updates
  include this scope even when the caller is a platform admin.

Do not store a second timezone on the task. `Professional.timezone` remains
the source of truth, and the admin panel displays it beside `local_time`.

The existing `Professional.daily_summary_time` should be migrated into the
new row's `local_time` for every tenant, with `enabled=false`; no tenant starts
receiving messages just because a migration ran. After compatibility checks,
remove the old string column in the same migration series or a short follow-up
migration rather than keeping two writable schedule settings.

### 6.2 `scheduled_task_runs`

Create a second tenant-scoped table for durable execution and delivery state:

| Field | Purpose |
|---|---|
| `id` | UUID primary key and local correlation handle. |
| `professional_id` | Required tenant scope, repeated deliberately for safe direct queries. |
| `scheduled_task_id` | Required FK to the configuration. |
| `target_local_date` | The agenda date in the tenant timezone. |
| `scheduled_for_at` | UTC instant calculated for the configured local time. |
| `status` | `queued`, `processing`, `retry_wait`, `provider_accepted`, `sent`, `delivered`, `read`, `delivery_unknown`, `failed`, or `skipped`. |
| `attempt_count`, `next_attempt_at` | Bounded retry state. |
| `provider_key`, `provider_message_id`, `provider_external_id` | Provider-neutral reconciliation identity and vendor provenance. |
| `agenda_item_count`, `class_count`, `event_count` | Operational diagnostics without reparsing text. |
| `rendered_body` | Exact tenant-scoped pt-BR snapshot submitted to the provider. |
| `last_error_code`, `last_error_detail` | Sanitized failure metadata; never credentials or raw provider payloads. |
| `started_at`, `accepted_at`, `sent_at`, `delivered_at`, `read_at`, `finished_at`, `created_at`, `updated_at` | Lifecycle timestamps. |

Constraints and indexes:

- Unique `(scheduled_task_id, target_local_date)` is the primary duplicate
  barrier.
- Validate run/task `professional_id` equality in the service and enforce it
  with a composite FK if the migration remains simple enough.
- Index `(status, next_attempt_at)` for worker claims and
  `(professional_id, created_at)` for the admin history view.
- Keep `rendered_body` out of application logs and error telemetry. It contains
  customer names and should follow the platform's data-retention policy.

This run table is the delivery audit record. Configuration mutations also add
one tenant-scoped `OperationalEvent` such as
`scheduled_task.configuration.updated`, with `actor_type=platform_admin`, the
admin user ID, source IP/user agent where available, and before/after state.

## 7. Tenant isolation and authorization contract

Tenant isolation is not only an API concern; the cross-tenant worker is the
highest-risk path in this feature.

- Admin endpoints depend on `require_platform_admin`. A professional session
  receives `403`, and platform-admin impersonation is not required.
- The path tenant ID is used only after loading that exact `Professional`;
  `professional_id` is never accepted from the request body.
- Every config, run, appointment occurrence, event, place, and delivery-history
  query includes the same resolved `professional_id`.
- Worker functions have signatures such as
  `build_daily_agenda(db, professional_id, target_date)` and
  `deliver_run(db, professional_id, run_id)`. Loading by bare `run_id` is not
  an allowed service pattern.
- Sender and recipient are loaded from the run's tenant immediately before
  delivery. They are never reused from a previous loop iteration or global
  mutable state.
- A task/run ownership mismatch fails closed, is marked failed with a generic
  reason, and triggers an internal alert without sending anything.
- List/history endpoints paginate and always scope before ordering/limiting.
- Admin responses may show the full tenant name but should mask phone numbers
  except for the last four digits.

Tenant-isolation tests must create two due tasks at the same local time with
different appointments, events, sender numbers, and recipients, then prove
that each rendered body and provider call contains only its own tenant data.

## 8. Platform-admin API and panel

### 8.1 API surface

Add narrow platform-admin routes:

```text
GET /api/admin/scheduled-tasks
PUT /api/admin/tenants/{professional_id}/scheduled-tasks/daily-agenda
GET /api/admin/tenants/{professional_id}/scheduled-tasks/daily-agenda/runs
```

`GET /api/admin/scheduled-tasks` is paginated and returns one daily-agenda row
per tenant, including an implicit disabled/default configuration when the row
has not been created yet. Each item includes tenant name/status, masked sender
and recipient readiness, timezone, enabled state, local time, eligibility
issues, computed next run, and latest run status/timestamp.

The `PUT` contract accepts the full desired configuration (`enabled`, strict
`HH:MM` local time, and explicit consent confirmation) and returns the
persisted state plus computed eligibility/next run. It must:

- reject unknown tenants with `404`;
- reject unsupported time/timezone or missing consent with `400`;
- reject enablement when sender/recipient provisioning is incomplete with
  `409` while still allowing a disabled configuration to be saved;
- update one tenant only and record the platform-admin audit event in the same
  transaction; and
- use the project's standard safe error response convention rather than
  returning provider or database details.

The run-history endpoint is paginated, newest first, and returns counts,
scheduled/delivery timestamps, state, and sanitized failure information. It
does not return `rendered_body` in the first UI contract; exact content remains
available for controlled support/audit use without exposing all customer names
in the cross-tenant overview.

### 8.2 Admin UX

Create `/admin/scheduled-tasks` and add a clear `Tarefas agendadas` navigation
entry from the existing admin area. A dedicated page is preferable to adding
another dense row to each tenant tile, and it leaves room for future task types
without turning `/admin/select-tenant` into a settings form.

The first panel has one card/table row per tenant with:

- tenant name and active/inactive badge;
- task label `Resumo diário da agenda`;
- enable switch;
- native time input;
- displayed timezone and computed next execution in local time;
- sender/recipient readiness with masked numbers;
- consent-confirmed control;
- latest state (`Entregue`, `Aceito pelo provedor`, `Falhou`, `Ignorado`, etc.);
- latest execution time and a compact history drawer.

Follow the existing optimistic UI rule: immediately reflect enable/time
changes, save in the background, and roll back the exact tenant row with a
clear error if the API rejects the mutation. Disable only the control being
saved; do not block or dim unrelated tenants. Changes to time should be saved
on an explicit compact `Salvar` action so partially typed values never become
server state.

Accessibility and responsive behavior are acceptance criteria: labeled
switches, keyboard-operable controls, status conveyed by text as well as color,
and card layout on narrow screens.

## 9. Due-task execution and failure semantics

### 9.1 One-tick service and runner

Implement `process_due_scheduled_tasks(db, now_utc)` as a finite unit of work;
put the loop in a thin `app/chat/scheduled_task_worker.py` runner. This keeps
the business logic testable and allows the same tick to run from a local poller
or a future Cloud Scheduler/Cloud Run Job without rewriting task semantics.

Recommended local settings, externalized in `.env`:

```text
SCHEDULED_TASK_POLL_SECONDS=30
SCHEDULED_TASK_MAX_LATENESS_MINUTES=30
SCHEDULED_TASK_MAX_ATTEMPTS=3
SCHEDULED_TASK_RETRY_BASE_SECONDS=60
WHATSAPP_PROVIDER=ycloud
YCLOUD_DAILY_AGENDA_TEMPLATE_NAME=...
YCLOUD_DAILY_AGENDA_TEMPLATE_LANGUAGE=pt_BR
YCLOUD_DAILY_AGENDA_TTL_SECONDS=...
```

Per-tenant send time and timezone remain database configuration, not server
environment parameters.

Each tick:

1. Load enabled task configurations belonging to active tenants.
2. For each task, convert `now_utc` into the tenant's validated timezone and
   calculate today's configured due instant.
3. Ignore a task enabled after today's due instant. If the worker missed the
   configurable lateness window, create one `skipped` run with reason
   `missed_delivery_window` rather than sending a stale agenda at midday.
4. Atomically insert/claim the day's run. Use the unique key plus PostgreSQL
   conflict handling/row locking so multiple workers cannot both own it.
5. Commit `processing` before the network call, build the tenant-scoped
   snapshot, and persist its counts/body.
6. Submit a canonical WhatsApp template request with a run-specific
   `externalId`; the configured adapter returns the provider key/message ID,
   which are stored as `provider_accepted`.
7. Retry only failures known to have happened before provider acceptance.
   Apply bounded exponential backoff and transition to terminal `failed` after
   the configured maximum.

There is no general exactly-once guarantee across a PostgreSQL commit and an
external provider. A timeout after the provider accepted a request is therefore
`delivery_unknown`, not an excuse to send blindly again. Reconcile by provider
ID/external ID where possible and expose the state to the admin. This policy
prefers one missing summary requiring review over duplicate morning messages.

`start_server.py --worker` should start this runner alongside the existing
candidate and passive-escalation workers, and its help text/README description
must be updated. Production should run exactly one instance initially; the
claim and uniqueness rules still make horizontal execution safe later.

### 9.2 WhatsApp template and YCloud adapter

Free-form text can only be sent during WhatsApp's 24-hour customer-service
window; a morning task cannot assume that window is open. YCloud's current
documentation therefore requires a pre-approved template to initiate this
message outside the window. Submit a pt-BR template early in implementation,
targeting the utility category, but treat Meta/YCloud's final approval and
classification as authoritative.

The template should have fixed operational wording with parameters for the
instructor/date and the rendered agenda block. Validate during the provider
spike that the variable layout, multiline agenda length, empty agenda, and
maximum expected customer list are accepted. Define a safe truncation rule
with `... e mais N compromissos` if the provider limit is exceeded; never split
one daily run into multiple messages in v0.1.

Implement these details inside the YCloud adapter behind the neutral provider
protocol. The adapter:

- uses YCloud's asynchronous enqueue endpoint;
- sends the approved template rather than `type=text`;
- supplies `externalId="scheduled-task-run:<run UUID>"`;
- returns the provider message ID and raises typed/sanitized errors;
- maps the logical `daily_agenda` template request to YCloud configuration;
- keeps the API key and vendor template details in `.env`, never in tenant
  records or logs; and
- translates YCloud/httpx results into canonical send results/errors.

The YCloud adapter maps `whatsapp.message.updated` to a canonical delivery
event before the provider-neutral dispatcher calls reconciliation.
Reconciliation matches the run by provider key/message ID/external ID and
applies monotonic state transitions
(`sent` → `delivered` → `read`; a duplicate/out-of-order webhook cannot move a
run backward). Unknown IDs are safely ignored after redacted logging.

Provider references checked for this roadmap:

- [YCloud message sending guide](https://docs.ycloud.com/reference/whatsapp-message-sending-guide)
- [YCloud enqueue API](https://docs.ycloud.com/reference/whatsapp_message-send)
- [YCloud messaging examples](https://docs.ycloud.com/reference/whatsapp-messaging-examples)

## 10. Phased implementation roadmap

Every phase is independently verifiable. Do not begin the next phase until its
exit criterion passes locally in the `agenda` conda environment.

### Phase 0A — General WhatsApp provider boundary

**Build**

- Add canonical WhatsApp requests/results/events/errors, the minimal provider
  protocol, strict registry, and `WHATSAPP_PROVIDER` configuration.
- Move YCloud HTTP/signature/payload logic into the YCloud adapter without
  changing its externally observed behavior.
- Add the provider-aware webhook route and temporary `/webhooks/ycloud` alias.
- Migrate ingestion, agent-channel replies, passive escalations, and delivery
  dispatch away from direct YCloud imports.
- Change the dev mock to emit canonical events directly.
- Add/backfill `Message.provider_key="ycloud"` and change deduplication to
  `(provider_key, provider_message_id)`.

**Verify**

- Run a reusable provider contract suite against the YCloud adapter: valid and
  invalid signature, inbound message, outbound echo, ignored event, delivery
  update, text send, template send, retryable/permanent/unknown failure, and
  redacted logging.
- Existing ingestion, agent-channel, passive-escalation, pipeline, and dev-mock
  behaviors remain unchanged when using a recording fake provider.
- Duplicate message IDs from two different provider keys coexist, while a
  duplicate within one provider remains idempotent.
- No file outside `integrations/whatsapp` and adapter-specific tests imports
  `ycloud`, reads `YCLOUD_*`, or indexes YCloud JSON.

**Exit criterion:** current WhatsApp behavior runs through the neutral port,
YCloud is only an adapter, and business tests no longer depend on YCloud
payloads. The scheduled task must not proceed before this boundary exists.

### Phase 0B — Provider/template feasibility and locked decisions

**Build/decide**

- Create the pt-BR template in the YCloud/WhatsApp manager with representative
  short, empty, multiline, and long agenda examples.
- Confirm approved category, parameter layout, actual character limits, TTL,
  returned message ID, `externalId` echo, and status webhook payloads.
- Confirm the instructor opt-in recording process used by the platform admin.
- Lock the default time, maximum lateness, retry policy, and truncation copy.
- Record required template/worker parameters in `.env.example` without secret
  values.

**Verify**

- Template reaches `APPROVED` and one sandbox/test-recipient message advances
  from provider accepted to delivered through signed webhook handling.
- A long representative message either passes or exercises the agreed
  deterministic truncation.

**Exit criterion:** the team has an approved YCloud template and captured real
adapter fixtures. Do not build the delivery worker against a guessed provider
contract.

### Phase 1 — Authoritative tenant-local daily agenda

**Build**

- Introduce a shared timezone resolver based on `Professional.timezone` and
  remove the daily-query dependency on the global São Paulo constant.
- Fix the central schedule projection so an occurrence rescheduled into the
  queried date appears, and one rescheduled out does not.
- Add `DailyAgendaItem`, `list_daily_agenda_items()`, and the deterministic
  pt-BR formatter.
- Merge confirmed instructor events, including cross-midnight overlap.
- Switch manual `hoje` to this service; preserve the other deterministic
  commands unless extending them is deliberately approved.

**Verify**

- Unit/integration tests cover one-off and recurring classes, groups,
  cancellations, reschedules into/out of the day, event inclusion/cancellation,
  chronological interleaving, empty day, missing place, cross-midnight event,
  accents, and two timezones around local midnight/DST.
- Existing calendar, agent-channel, schedule-projection, and instructor-event
  suites remain green.

**Exit criterion:** asking `hoje` returns the same ordered items that a future
scheduled run would render, with no tenant or timezone leakage.

### Phase 2 — Configuration, run state, admin API, and audit

**Build**

- Add the two models, constraints, indexes, and Alembic migration.
- Backfill each tenant's old `daily_summary_time` into a disabled scheduled-task
  config and retire the old writable field safely.
- Add configuration/run repository or service functions with mandatory tenant
  scope and strict state transitions.
- Add request/response schemas and the three platform-admin endpoints.
- Add `scheduled_task.configuration.updated` to the operational-event allowlist
  and migration constraint.
- Persist the selected `provider_key` on each run; never infer historical run
  provenance from the provider currently selected in `.env`.

**Verify**

- Migration upgrade/downgrade is exercised only against the local
  `agenda_db`; data/backfill assertions prove no task is auto-enabled.
- API tests cover list/default row, create/update/disable, invalid time,
  invalid timezone, missing consent/provisioning, inactive/unknown tenant,
  pagination, audit attribution, professional-role denial, and two-tenant
  isolation.
- Concurrent config creation resolves to one row under the unique constraint.

**Exit criterion:** an admin can configure durable disabled/enabled state via
API, and no process sends a message yet.

### Phase 3 — Durable processor, template delivery, and reconciliation

**Build**

- Implement finite due-task processing, atomic daily run claims, snapshot
  persistence, retries, lateness handling, and terminal states.
- Complete the YCloud adapter's logical `daily_agenda` template mapping using
  the canonical template-send contract established in Phase 0A.
- Dispatch canonical delivery events and reconcile them idempotently without
  provider-specific branches in the run service.
- Add the thin worker runner and wire it into `start_server.py --worker`.
- Add structured metrics/logs using IDs, counts, duration, status, and error
  codes only; never log customer names, rendered bodies, numbers, or secrets.

**Verify**

- Frozen-clock tests cover before/at/after due time, late enablement, timezone
  boundaries, worker downtime, retry exhaustion, and next-day execution.
- Concurrency test starts two processors and proves one run/provider call.
- YCloud adapter tests use captured sanitized fixtures for accepted, rejected,
  timeout/unknown, sent, delivered, read, failed, duplicate, and out-of-order
  events.
- Two tenants due together receive different correctly scoped snapshots at the
  correct sender/recipient pairs.
- Restarting after `provider_accepted` does not send again.

**Exit criterion:** a test tenant receives one real template message, its run
reaches the correct webhook-confirmed state, and injected failures remain
durable and visible.

### Phase 4 — Scheduled-tasks admin panel

**Build**

- Add `/admin/scheduled-tasks`, navigation, tenant rows/cards, configuration
  controls, readiness/next-run/latest-state display, and paginated history.
- Implement optimistic updates with per-row rollback.
- Add professional, responsive styling consistent with the existing admin
  area; use Lucide/SVG icons only.

**Verify**

- Frontend tests cover initial/default state, enable validation, time editing,
  optimistic success, isolated rollback, ineligible tenant, masked numbers,
  history states, keyboard labels, and mobile layout.
- Typecheck and lint pass; manual browser validation covers the full admin
  flow without impersonating a tenant.

**Exit criterion:** a platform admin can safely operate the task for multiple
tenants and understand the latest/next execution without database access.

### Phase 5 — Pilot rollout and operational hardening

**Build/operate**

- Deploy schema and code with every task disabled.
- Configure one internal/test tenant, confirm timezone/numbers/consent, enable
  it, and observe at least three consecutive local mornings.
- Add alerts for failed/unknown runs, no worker heartbeat, and status-webhook
  lag; define the support response for each state.
- Review WhatsApp template cost/quality, opt-outs, message length, lateness,
  and delivery rate before enabling another tenant.
- Update architecture, data architecture, business rules, admin page docs,
  deployment docs, and the original Phase 5 daily-summary checklist.
- Prepare local-to-remote data synchronization separately. Never use this
  feature rollout to perform destructive operations against Azure PostgreSQL.

**Verify**

- Three-day pilot has no duplicate/mis-scoped messages and admin status agrees
  with provider delivery events.
- Disable takes effect before the next due claim, and inactive tenant state
  prevents delivery.
- Full backend regression suite, frontend lint/typecheck/tests, migration
  checks, and a focused OWASP/access-control review pass.

**Exit criterion:** the task runs unattended for the pilot tenant with an
understood failure/support path, then can be enabled tenant by tenant.

## 11. Acceptance criteria

The MVP is done only when all of the following are demonstrably true:

- A platform admin can enable/disable and set a strict local send time for one
  tenant from the admin panel; a professional user cannot access those APIs or
  screens.
- Configuration always names a tenant, uses that tenant's timezone, sender,
  recipient, classes, events, and run history, and never falls back to a
  default/global tenant.
- At the configured local time, one enabled active tenant gets one provider
  submission for that local date, including on server restart or when two
  processors overlap.
- The list includes active appointment/recurring-class occurrences and
  confirmed instructor events, applies cancellations/reschedules correctly,
  orders them by local start time, and omits cancelled items.
- Manual `hoje` and scheduled delivery use the same agenda item projection and
  agree for the same frozen instant/tenant.
- Empty days still produce the approved empty-agenda message.
- A disabled, inactive, unprovisioned, non-consented, or invalid-timezone
  tenant produces no provider call and shows an actionable admin state.
- Provider acceptance is not mislabeled as delivery; signed webhooks advance
  runs idempotently through sent/delivered/read or failed.
- Definite transient pre-acceptance failures retry within bounds; ambiguous
  timeouts do not create blind duplicates.
- No LLM call occurs, no PII appears in logs/metrics, and secrets remain in
  `.env` only.
- Agenda, agent, escalation, ingestion, worker, and API business services
  import only canonical WhatsApp contracts/protocols; YCloud names, payloads,
  credentials, URLs, and `httpx` errors remain inside the adapter boundary.
- Persisted provider IDs are namespaced by `provider_key`, and switching the
  configured provider cannot relabel or mis-reconcile historical messages or
  scheduled runs.
- The focused test suites, full backend regression suite, frontend typecheck,
  lint, and migration checks pass in the `agenda` environment.

## 12. Focused test inventory

Suggested files and behavior-oriented tests:

```text
backend/tests/test_whatsapp_provider_contract.py
  test_provider_normalizes_message_to_canonical_event
  test_provider_normalizes_delivery_to_canonical_event
  test_provider_classifies_retryable_permanent_and_unknown_errors

backend/tests/test_ycloud_adapter.py
  test_ycloud_verifies_valid_signature_and_rejects_invalid_signature
  test_ycloud_maps_inbound_echo_and_delivery_fixtures
  test_ycloud_maps_text_and_template_requests_without_leaking_vendor_types

backend/tests/test_whatsapp_webhook.py
  test_webhook_rejects_unknown_provider
  test_webhook_dispatches_canonical_events_idempotently
  test_legacy_ycloud_alias_uses_same_adapter_during_migration

backend/tests/test_daily_agenda.py
  test_daily_agenda_merges_classes_and_events_chronologically
  test_daily_agenda_reschedule_into_day_is_included
  test_daily_agenda_reschedule_out_of_day_is_excluded
  test_daily_agenda_cross_midnight_event_is_included
  test_daily_agenda_two_tenants_never_mix_items

backend/tests/test_admin_scheduled_tasks.py
  test_admin_updates_one_tenant_task_and_records_audit
  test_professional_cannot_manage_scheduled_tasks
  test_enable_without_consent_or_phone_returns_conflict
  test_task_history_is_tenant_scoped_and_paginated

backend/tests/test_scheduled_task_worker.py
  test_due_task_creates_one_run_and_enqueues_one_message
  test_two_workers_claim_same_day_only_once
  test_late_enablement_starts_next_local_day
  test_missed_window_is_skipped_without_provider_call
  test_retryable_failure_retries_then_succeeds
  test_ambiguous_timeout_is_not_blindly_retried
  test_two_due_tenants_use_own_sender_recipient_and_body

backend/tests/test_scheduled_task_webhooks.py
  test_delivery_webhook_advances_run_monotonically
  test_duplicate_delivery_webhook_is_idempotent
  test_unknown_external_id_does_not_mutate_any_run
```

Keep API tests behavioral and worker clock/provider calls injected; do not
sleep or call the live provider in the normal regression suite.

## 13. Observability and support

Minimum metrics, tagged by task type/status but not by customer data:

- due tasks, claimed runs, provider submissions, delivered runs, failed runs,
  skipped runs, and unknown deliveries;
- claim-to-accept and accept-to-deliver latency;
- retry count and webhook reconciliation lag;
- last successful worker tick/heartbeat.

Logs may include run ID, task ID, tenant UUID, attempt number, state transition,
duration, and sanitized provider error code. Do not include tenant names,
phone numbers, customer names, message body, provider raw payload, API key, or
template parameters.

The admin panel is the first support surface. A terminal/unknown run must say
what the admin can do (check provisioning/template/provider or wait for
reconciliation) without exposing stack traces. “Retry now” is intentionally
not in v0.1 because it needs a separate duplicate-safe product contract.

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cross-tenant data/message leak | Mandatory `professional_id` in both tables and every service query; two-tenant tests at query, render, claim, API, and provider boundaries. |
| Wrong local date/time | Resolve IANA timezone per tenant with `zoneinfo`; freeze clock in boundary/DST tests; fail closed on invalid zones. |
| Missing rescheduled occurrence | Fix the known cross-window schedule-projection gap in Phase 1 before enabling delivery. |
| Duplicate proactive message | Unique task/date run, atomic claim, persisted state before network, provider IDs/external ID, and no blind retry after ambiguous timeout. |
| Message accepted but never delivered | Distinguish provider acceptance from delivery and reconcile signed status webhooks. |
| Free-form message rejected outside 24-hour window | Use an approved template and complete the provider feasibility phase first. |
| Template rejected/reclassified or content too long | Submit early with real examples; use deterministic truncation and configurable approved template metadata. |
| Worker outage sends stale agenda | Maximum-lateness window and visible `skipped` run instead of unlimited catch-up. |
| Agenda changes just after snapshot | Document snapshot-at-claim semantics; do not promise live updates in a once-daily message. |
| Admin enables without instructor authorization | Require and audit explicit consent confirmation before enablement; provide disable/opt-out path. |
| PII leaks through operations tooling | No body/names/numbers in logs or metrics; tenant-scoped snapshot retention and masked admin overview. |
| Provider abstraction becomes an oversized lowest-common-denominator framework | Model only current capabilities: message/echo, delivery update, text, and template send; add new methods only with a real use case. |
| YCloud types leak back into business services | Import-boundary test/lint check plus a single adapter contract suite; business tests use a recording fake provider. |
| Provider switch breaks deduplication or webhook reconciliation | Persist `provider_key` with every vendor identifier and use composite uniqueness/lookups. |

## 15. Decisions to approve before coding

Recommended defaults are listed first so these need not block planning:

1. **Cadence:** every calendar day, including weekends, with an empty-agenda
   message when applicable. Alternative: weekdays only or silence on empty
   days.
2. **Default local time:** preserve the existing `07:00` value, but migrate all
   tenants as disabled. Alternative: require explicit time entry for every
   tenant.
3. **Maximum lateness:** 30 minutes, then mark the run skipped. Alternative:
   send whenever the worker returns that day.
4. **Message detail:** time, kind, participant/event label, and place; no end
   time except where a multi-hour event benefits from a range. Alternative:
   always show start/end.
5. **Consent:** admin must explicitly confirm recorded instructor opt-in before
   enabling. The exact evidence/onboarding process remains a business decision.
6. **Snapshot retention:** retain message bodies for the platform's normal
   operational-data period, then redact/delete the body while preserving run
   counts/status. The exact period should match the still-to-be-finalized data
   retention policy.
7. **Unknown delivery:** surface for support and do not automatically resend.
   Alternative: accept a controlled duplicate risk and retry.
8. **Provider selection:** one deployment-level provider selected through
   `WHATSAPP_PROVIDER` for v0.1. Per-tenant provider selection is deferred until
   a real mixed-provider rollout requires credential/configuration isolation.

## 16. Likely implementation touch points

```text
backend/app/models/scheduled_task.py                 new
backend/app/models/scheduled_task_run.py             new
backend/app/models/message.py                        provider provenance/dedup
backend/app/services/daily_agenda.py                 new
backend/app/services/scheduled_tasks.py              new
backend/app/chat/scheduled_task_worker.py            new
backend/app/integrations/whatsapp/contracts.py       new canonical types/errors
backend/app/integrations/whatsapp/provider.py        new minimal protocol
backend/app/integrations/whatsapp/registry.py        new strict factory
backend/app/integrations/whatsapp/ycloud.py          migrated YCloud adapter
backend/app/chat/ycloud_provider.py                  remove after import migration
backend/app/chat/agent_channel.py                    neutral sender + shared hoje
backend/app/chat/ingestion.py                        canonical event ingestion
backend/app/services/passive_escalation.py           neutral sender/errors
backend/app/api/admin.py                             admin routes or narrow router split
backend/app/api/whatsapp.py                          provider-aware verified dispatch
backend/app/api/dev_mock.py                          canonical mock events
backend/app/schemas/api.py                           admin contracts
backend/app/services/scheduling.py                   timezone/cross-window correctness
backend/app/models/operational_event.py              config audit type
backend/migrations/versions/...                      schema/backfill/constraints
frontend/src/app/admin/scheduled-tasks/page.tsx      new panel
frontend/src/app/admin/select-tenant/page.tsx        navigation entry
frontend/src/lib/api.ts                              admin client calls
frontend/src/lib/types.ts                            response types
start_server.py                                      local worker startup
.env.example                                         non-secret task/provider parameters
README.md and docs/...                               operating/data/business docs
```

No new runtime dependency is expected: SQLAlchemy/PostgreSQL, `zoneinfo`,
FastAPI, `httpx`, and the existing Next.js stack cover this scope. If
implementation proves otherwise, justify and pin the dependency in the root
`requirements.txt` before use.
