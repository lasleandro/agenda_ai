# YCloud Tenant WhatsApp Connection Roadmap v0.1 — 2026-09-02

**Status:** initial discovery UI implemented locally; provider connection work
remains proposed and disabled pending partnership access.
**Scope:** a Tennis OS-native page where a tenant can understand, start, and
monitor the connection of its existing WhatsApp Business account. Build the
experience against a mock onboarding provider first, then activate YCloud's
partner flow without replacing the page or its application contracts.

## 1. Recommendation

Build this now, but treat it as a real onboarding product with a replaceable
mock transport—not as a clickable design that invents YCloud behavior.

The appropriate future YCloud product is **Tech Partner + Embedded Signup**.
YCloud's separate **white-label partner** offering is a branded copy of the
YCloud console and is not required merely to let Tennis OS tenants connect
from inside Tennis OS. The native connection page can remain entirely in our
design system; the Meta authorization surface opened from it will retain the
identity and disclosures required by Meta/YCloud.

The implementation should therefore separate rollout availability from the
selected provider:

- `demo` availability uses a mock onboarding adapter to exercise the Tennis OS UI,
  API, tenant isolation, lifecycle, audit, and failure recovery without an
  external call;
- `live` availability uses the platform-selected provider—initially `ycloud`—
  through the same canonical contracts.

Production must default to `disabled` until partnership, legal, billing, and
support gates are cleared. A tenant must never see a simulated connection as a
real WhatsApp connection.

## 2. Product outcome and success criteria

An authenticated professional can open **WhatsApp** in Tennis OS and see one
truthful connection state, the next required action, and any operational issue
that needs attention. After the real provider is activated, the professional
can authorize Meta, connect an existing WhatsApp Business App account through
Coexistence where eligible, and return to Tennis OS without handling YCloud
credentials.

Success means:

- The mock page renders every supported lifecycle state and works on desktop
  and mobile using the existing Tennis OS visual language.
- Mock actions are visibly labelled as a demonstration and cannot enable real
  message ingestion or delivery.
- Connection state is tenant-scoped and derived from the authenticated
  session; the browser never submits a `professional_id`.
- Only a professional belonging to that tenant, or a platform admin acting
  through the existing impersonation boundary, can view or mutate it.
- Provider identifiers and one-time authorization results are accepted only
  through the backend; API keys and exchanged tokens never reach browser
  storage, URLs, logs, or analytics.
- The real onboarding adapter can replace the mock without changing page state
  names or core API response shapes.
- A connected phone becomes the tenant's customer-conversation routing number
  (`Professional.assistant_phone`) in one transaction. It never overwrites the
  platform/private-agent number (`Professional.agent_phone`).
- Duplicate callbacks, refreshes, and completion requests are idempotent.
- Disconnect/reconnect, provider removal, and degraded-number events have an
  auditable state transition and do not silently reroute another tenant.
- All environment-specific IDs, domains, secrets, and rollout modes are read
  from `.env`; no partner value is hardcoded.

## 3. Scope and non-goals

In scope for v0.1:

- A dedicated tenant-facing WhatsApp connection page.
- A small onboarding state machine and provider-neutral onboarding contract.
- A mock onboarding adapter and deterministic demo scenarios.
- One customer-conversation WABA/phone connection per tenant.
- WhatsApp Business App Coexistence only, because the passive copilot depends
  on the professional continuing to use the Business App. A new pure API
  account flow is added only if a real customer need appears.
- Server-side capture of Embedded Signup results, YCloud binding/registration,
  status refresh, provider lifecycle webhooks, and audit in the real phase.
- One provider selection at the application composition boundary, so Tennis OS
  can replace YCloud globally without changing tenant-facing or domain code.
- Feature/availability gates, tests, operations, and activation documentation.

Out of scope for v0.1:

- Recreating or embedding the complete YCloud console.
- A template manager, campaign builder, shared inbox, contact sync, billing
  portal, or analytics suite.
- A tenant-facing provider marketplace or letting professionals choose an
  arbitrary provider. Provider enablement and migration remain controlled by
  Tennis OS administrators.
- Provisioning the separate `agent_phone`; that remains a platform-managed
  number and lifecycle.
- Storing a YCloud API key per tenant. The future partner credential is a
  server-side platform secret; tenant ownership is represented by the bound
  WABA/phone identifiers.
- Promising that every existing number is eligible for Coexistence. Eligibility
  and limitations must come from the live Meta/YCloud flow.
- Executing a real disconnect before YCloud documents the exact offboarding
  operation, effects, and reversibility for partner-managed accounts.
- Any write to the remote PostgreSQL database. Schema work is developed and
  tested on local `agenda_db`; remote migration requires a separate approved
  rollout.

## 4. Verified starting point

### Existing Tennis OS assets to reuse

- `backend/app/integrations/whatsapp/provider.py` and `contracts.py` already
  isolate message sending and webhook normalization from the YCloud payload.
- `YCloudWhatsAppProvider` already verifies signed callbacks, normalizes
  inbound messages/outbound echoes/delivery updates, and sends text/templates.
- `POST /webhooks/whatsapp/{provider_key}` plus the durable webhook receipt
  path already provide the provider entry boundary.
- Incoming conversations are tenant-routed by the receiving
  `Professional.assistant_phone`; unknown numbers fail closed.
- `Professional.agent_phone` is intentionally separate and must remain so.
- Authentication derives the tenant from the session, supports explicit
  platform-admin impersonation, and exposes tenant feature flags.
- State-changing APIs already use CSRF/origin protection, rate limiting, and
  operational audit patterns.
- The frontend already has a responsive app shell, feature-aware sidebar,
  cards, dialogs, notices, and optimistic CRUD patterns to reuse.

This means message transport should not be redesigned. Onboarding is a new
responsibility beside the existing `WhatsAppProvider`, because starting,
binding, refreshing, and observing account lifecycle changes differ from
sending and parsing messages.

This keeps the deployment-wide replacement strategy already recommended in
[the WhatsApp provider portability assessment](../whatsapp_provider_portability_assessment.md):
one provider for the platform, with provider-specific code behind narrow
contracts.

### Current gaps

- `assistant_phone` is a nullable field on the tenant root; it does not record
  WABA ownership, provider phone ID, connection health, or mode.
- Provider selection is deployment-wide through `WHATSAPP_PROVIDER`; there is
  no tenant-owned provider connection record.
- The frontend has no WhatsApp status/onboarding page.
- No backend contract represents an Embedded Signup attempt or correlates its
  browser result to a user and tenant.
- The YCloud adapter uses one server API key, but the repository has no
  partner-only WABA binding or SMB/Coexistence binding operation.
- Existing YCloud webhook normalization does not yet cover WABA deletion,
  partner removal, account reconnection/offboarding, or phone quality changes.

### What current official documentation confirms

Verified on 2026-09-02:

- YCloud describes its Tech Partner program as the route for SaaS products
  whose customers connect WhatsApp without leaving the product, using
  Embedded Signup: [YCloud Tech Partner program](https://www.ycloud.com/tech-partner).
- The partner onboarding guide says Embedded Signup creates/authorizes the
  customer's WhatsApp assets and that YCloud grants partner permissions before
  customer onboarding: [Technical Development Partner Onboarding](https://helpdocs.ycloud.com/partner-center/english-en-2/ji-shu-kai-fa-huo-ban/ji-shu-kai-fa-huo-ban-ru-men).
- Embedded Signup depends on Meta's JavaScript SDK and HTTPS allowlisted
  domains. Its browser result includes WABA/phone identifiers that must be
  passed to the backend; API-account and Business App Coexistence are distinct
  flows: [YCloud Embedded Signup guide](https://helpdocs.ycloud.com/partner-center/english-en-2/ji-shu-kai-fa-huo-ban/embedded-signup).
- YCloud exposes server APIs to retrieve WABAs, list/retrieve phone numbers,
  and register a verified phone. A registered number transitions toward a
  connected state before sending:
  [WABA retrieval](https://docs.ycloud.com/reference/whatsapp_business_account-retrieve),
  [phone list](https://docs.ycloud.com/reference/whatsapp_phone_number-list),
  and [phone registration](https://docs.ycloud.com/reference/whatsapp_phone_number-register).
- YCloud messaging uses `POST /v2/whatsapp/messages`, returns acceptance before
  delivery, and recommends delivery/inbound webhook subscriptions:
  [WhatsApp Message Sending Guide](https://docs.ycloud.com/reference/whatsapp-message-sending-guide).
- YCloud's white-label partner product is a separately branded YCloud console
  with custom console/API domains, logos, and theme settings. It is not the
  prerequisite for a focused native onboarding screen:
  [White-label partner guide](https://helpdocs.ycloud.com/partner-center/english-en-2/bai-biao-huo-ban/bai-biao-huo-ban-ru-men).

The public material does **not** provide a stable, complete English contract
for every partner binding/offboarding operation. Exact URL, request, response,
error, billing, and revocation semantics must be obtained from YCloud before
the real adapter is implemented. The roadmap intentionally names those calls
by capability rather than guessing an endpoint.

## 5. Product and architecture decisions

1. **Native page, embedded authorization.** Tennis OS owns the page, copy,
   status, recovery, and support entry points. Meta's authorization dialog is
   launched only for the authorization portion.
2. **Coexistence is the default proposed flow.** The current passive-observer
   product expects the professional to keep using WhatsApp Business App while
   echoes arrive through YCloud. A pure API number may be offered only after a
   separate product decision.
3. **Connection is a domain entity.** Do not add more provider fields to
   `Professional`. Keep `assistant_phone` as the denormalized, indexed routing
   pointer needed by ingestion and store lifecycle details in a connection
   record.
4. **Two small provider contracts.** Keep the existing messaging protocol and
   add one onboarding/lifecycle protocol. Register the pair under the globally
   configured provider key. Do not add a general capability framework or base
   class.
5. **One connection row per tenant.** This matches the current product and is
   enough when one provider serves the whole platform. Historical provider
   attribution already belongs on messages/runs and in operational events;
   duplicate connection-history machinery is unnecessary.
6. **Mock and real use the same state machine.** Mock-specific data never
   enters `assistant_phone`, never creates a live scheduled task, and is
   unmistakably labelled in both the response and UI.
7. **Availability, provider selection, and tenant access are separate gates.**
   Deployment availability says disabled/demo/live, `WHATSAPP_PROVIDER`
   selects one provider for the platform, and a tenant feature says whether
   that tenant may use the page. The backend enforces all three.
8. **Provider state is eventually consistent.** Embedded Signup completion is
   not equivalent to operational readiness. The server binds, registers when
   required, retrieves authoritative provider state, and only then marks the
   connection `connected`.
9. **Disconnect is fail-safe.** Clear routing only after confirmed provider
   offboarding or an explicit quarantined state. Never free a phone for another
   tenant while ownership/retry state is uncertain.
10. **No secrets in tenant rows.** The platform API key, Meta app secret, and
    token exchange stay in secret management/environment configuration. If an
    approved provider later requires a durable per-customer credential, stop
    and design that storage explicitly rather than adding it now.
11. **Provider choice never leaks into domain services.** Application code
    asks the global registry for canonical messaging/onboarding operations.
    `if provider == "ycloud"` belongs only in registry composition, never in
    API, tenant, scheduling, or frontend logic.
12. **Cutover has one global sender at a time.** Stop new sends, drain accepted
    work, migrate provider account references, switch `WHATSAPP_PROVIDER`, then
    resume. Old callbacks remain attributable through their stored
    `provider_key` during a bounded drain window.

### Simplicity guardrails

The initial implementation is limited to one new connection model/migration,
one onboarding service, one new provider protocol, one mock onboarding adapter,
one YCloud onboarding adapter when credentials exist, and one frontend page.
Reuse the current messaging adapter, registry style, feature flags, webhook
receipt path, and `OperationalEvent` audit ledger.

Do not add a tenant provider selector, provider capability matrix, connection
history table, separate onboarding-attempt table, new worker/queue, automatic
fallback, or dual-provider runtime. Revisit one of these only when a concrete
requirement cannot be met safely without it.

## 6. Frontend recommendation

### Information architecture

Do not create another sidebar. Add a **WhatsApp** navigation item to the
existing left panel (`SidebarContent`), immediately above **Configurações**,
using the existing landing-page WhatsApp asset and routing to
`/configuracoes/whatsapp`. The shared `SidebarContent` also places the item in
the existing mobile navigation drawer. Although it is configuration, this is a
high-value channel with meaningful operational status; placing it directly in
the current navigation makes it easier to discover than another horizontal tab
inside `/minhas-regras`. Keep the page inside the protected app shell. The
initial informational page is available to every authenticated tenant; apply a
feature filter only when the active onboarding rollout requires it.

Do not expose “YCloud” as the page title. Use **Conexão com WhatsApp Business**.
Provider attribution should appear only where legally or operationally useful,
such as small explanatory text in the real authorization step or support
diagnostics.

Frontend components branch on canonical state and a short server-computed
`allowed_actions` list—not on `provider === "ycloud"`. For example, render
**Atualizar status** only when `refresh` is allowed. The provider key may be
returned for support diagnostics, but changing it must not require page or
component changes.

### Recommended disconnected page

```text
+---------------------------------------------------------------+
| WhatsApp                                      [Não conectado] |
| Conecte sua conta Business para organizar sua agenda.         |
+--------------------------------------+------------------------+
| Conexão com WhatsApp Business        | Antes de começar       |
|                                      |                        |
| Continue usando seu WhatsApp         | [✓] Ser administrador  |
| Business enquanto o Tennis OS        | [✓] Acessar o número   |
| acompanha conversas e sua agenda.    | [✓] Ter conta Meta     |
|                                      |                        |
| [Conectar WhatsApp]                  | Leva cerca de 5 min    |
| Saiba como funciona                  | Seus dados e permissões|
+--------------------------------------+------------------------+
| 1. Autorizar Meta  ->  2. Verificar número  ->  3. Pronto     |
+---------------------------------------------------------------+
```

For mock mode, place a persistent, non-dismissible banner above the content:
**“Demonstração — nenhuma conta ou número real será conectado.”** Change the
primary action to **“Visualizar fluxo de conexão”**. Do not mimic a Meta login
screen or ask for real Meta credentials in the mock.

### Recommended connected page

Show the operational answer first:

- Status badge with icon and text: **Conectado**, **Ação necessária**, or
  **Indisponível**; never rely on colour alone.
- Connected business display name and masked phone, with a copy action only
  when exposing the full value is appropriate to that authenticated user.
- Connection type: **WhatsApp Business App (Coexistência)**.
- Last provider synchronization time and a quiet **Atualizar status** action.
- Three compact health checks: account authorization, phone connection, and
  webhook/message readiness.
- One next-step card. On first connection, ask the professional to send a test
  customer message and explain what will appear in Tennis OS.
- A secondary **Gerenciar conexão** menu for status refresh and support.
  Destructive disconnect stays out of v0.1 and is added only after the provider
  offboarding contract is approved.

Do not show raw WABA IDs, provider phone IDs, API error bodies, webhook URLs,
or secret/configuration fields to tenant users. Put masked identifiers and a
correlation/support code in an expandable diagnostics section for platform
admins only.

### Lifecycle states and copy

| Canonical state | Tenant-facing title | Primary action |
|---|---|---|
| `unavailable` | Conexão ainda não disponível | None; explain controlled rollout |
| `disconnected` | Conecte seu WhatsApp Business | Conectar WhatsApp |
| `authorizing` | Conexão iniciada | Continuar autorização |
| `binding` | Estamos verificando sua conta | None; allow safe status refresh |
| `action_required` | Precisamos de uma ação sua | Retomar conexão / ver orientação |
| `connected` | WhatsApp conectado | Send/verify test or manage connection |
| `degraded` | A conexão precisa de atenção | Corrigir conexão |
| `disconnected_by_provider` | Conta desconectada | Reconectar WhatsApp |

`authorizing` and `binding` are durable server states, not temporary component
flags. If the browser closes, the page resumes from the persisted connection
state.

### Embedded Signup interaction

1. The user selects **Conectar WhatsApp**.
2. Tennis OS immediately stores short-lived onboarding state on the tenant's
   connection row and changes the card to `authorizing` (optimistic UI).
3. After the backend returns the signed/correlated launch configuration, the
   frontend loads the Meta JavaScript SDK and opens Embedded Signup from a
   direct user gesture so popup blockers do not interfere.
4. Accept `postMessage` events only from an exact documented Meta origin
   allowlist, validate the expected event shape, and send the result plus the
   one-time correlation state to the same-origin backend. Do not trust `waba_id`,
   `phone_number_id`, business ID, or completion status merely because the
   browser supplied them.
5. The page moves optimistically to `binding`; a compact inline progress
   message is appropriate because provider work is genuinely pending.
6. The backend performs provider operations and returns/reconciles the
   authoritative connection. On a recoverable failure, preserve connection state
   and offer **Tentar novamente** without forcing the user to restart Meta
   authorization unless required.

### Optimistic UI and failure recovery

- Starting, refreshing, and retrying update the relevant card immediately;
  avoid full-page spinners.
- Initial page load may use a stable card skeleton to prevent layout shift.
- A failed start restores `disconnected` and leaves the explanation/action in
  place.
- A failed refresh retains the last known state and timestamp, displaying a
  non-blocking warning instead of replacing the page with an error.
- Duplicate completion events should resolve to the same connection response
  and should not produce duplicate toasts.

### Responsive and accessible behavior

- Use a two-column layout only at large widths; stack status, CTA, and
  prerequisite content on mobile.
- Convert the horizontal three-step indicator into a vertical sequence when it
  cannot fit without scrolling.
- Keep actions at least 44 CSS pixels on touch layouts, support safe-area
  insets, and avoid hover-only help.
- Move focus into any opened dialog and return it to the launch action on
  close. Announce state changes with a polite live region.
- Every status includes icon, text, and supporting sentence. Error guidance is
  linked to the field/action that can resolve it.
- If the Meta popup is blocked, provide a clear retry action and browser
  guidance; do not automatically relaunch it in a loop.

### Visual direction

Reuse the current white/neutral cards, indigo primary action, subtle borders,
rounded corners, Lucide icons, and compact typography. Use WhatsApp green only
as a restrained channel identifier—not as a new primary theme. Avoid a large
phone illustration; the page's job is confidence and status, and the product
already has enough recognizable WhatsApp context through its icon and copy.

Keep provider attribution in one small reviewed disclosure component. Never
render provider-supplied HTML or raw copy. If the global provider changes, this
is the only tenant-facing copy location that may need an approved update.

## 7. Target backend design

### Provider-neutral adapter pair

Keep the existing small `WhatsAppProvider` messaging protocol and add one
small onboarding/lifecycle protocol:

```python
class WhatsAppOnboardingProvider(Protocol):
    key: str

    def launch_configuration(self, connection: WhatsAppConnection) -> LaunchConfig: ...
    def complete(self, result: SignupResult) -> ProviderConnection: ...
    def retrieve(self, connection: WhatsAppConnection) -> ProviderConnection: ...
```

The global registry exposes `get_whatsapp_provider()` and
`get_whatsapp_onboarding_provider()`. In live mode both resolve the same
`WHATSAPP_PROVIDER` and fail closed for an unknown provider. Demo mode is the
single explicit exception: onboarding returns the mock adapter without
changing the real messaging provider. An explicit provider key remains
accepted only at webhook/delivery-reconciliation boundaries so old callbacks
can drain after a global cutover.

Recommended minimal module shape:

```text
integrations/whatsapp/
  contracts.py
  provider.py
  onboarding.py
  registry.py
  mock_onboarding.py
  ycloud.py
  ycloud_onboarding.py
```

Do not create base classes, capability frameworks, provider factories, or
tenant-level resolvers. A new provider adds its messaging/onboarding modules
and two explicit registry branches. Domain services and frontend components
remain unchanged.

Canonical onboarding values contain only Tennis OS concepts: connection
status, safe action/failure code, normalized phone, external references, and
timestamps. Provider payload types, status strings, SDK event names, headers,
URLs, retry codes, and branding stay inside the relevant adapter.

`LaunchConfig` models the one authorization ceremony currently required:
Meta Embedded Signup. Add another launch shape only if a selected replacement
provider proves it is necessary.

Do not add `disconnect` or other optional operations to the protocol until the
selected provider's documented flow is approved and the product exposes that
action.

Tighten the existing messaging contract as part of this boundary work:

- every event and send result supplies `provider_key` explicitly; remove the
  current implicit YCloud default from canonical message events;
- domain services request logical templates such as `daily_agenda`; provider
  template names, languages/policies, and optional TTL mappings stay in the
  provider adapter/configuration;
- application code handles only canonical retryable, permanent, and
  delivery-unknown failures plus stable safe action codes;
- raw provider payloads may be retained at the verified webhook boundary for
  audit/debugging, but domain code must not index provider-specific fields.

The mock onboarding adapter must be deterministic. Given a configured scenario such as
`success`, `action_required`, or `provider_error`, it should emit the same
canonical responses as the real adapter without network access. Select the
scenario through local/test environment configuration; do not build scenario
controls or accept a tenant-supplied outcome.

The mock and YCloud onboarding adapters must pass the same reusable onboarding
contract suite. Each future real provider must also pass the existing messaging
contract suite. This proves the interfaces are not shaped around YCloud.

### Data model

Add `whatsapp_connections` with the smallest operational fields:

| Field | Purpose |
|---|---|
| `id` | Internal UUID, never a provider ID |
| `professional_id` | Tenant owner; unique because v0.1 has one connection per tenant |
| `provider_key` | Stable registered adapter key such as `ycloud` or `mock`; never a database enum |
| `status` | Canonical lifecycle state from Section 6 |
| `business_phone_e164` | Canonical connected sender/routing phone, nullable until known |
| `meta_business_portfolio_id` | Meta business portfolio identifier when returned |
| `meta_waba_id` | Provider-independent Meta WABA identifier |
| `meta_phone_number_id` | Provider-independent Meta phone-number identifier |
| `business_display_name` | Provider-reported display name for UI |
| `action_code` | Stable internal reason such as `payment_required` or `reauthorization_required` |
| `onboarding_state_hash` / `onboarding_expires_at` | Current short-lived replay/correlation boundary |
| `onboarding_started_by_user_id` | Actor bound to the current attempt |
| `last_synced_at` | Freshness shown on the page |
| `connected_at` / `disconnected_at` | Provider lifecycle timestamps |
| `created_at` / `updated_at` | Normal record timestamps |

Constraints:

- unique `professional_id`;
- unique non-null `(provider_key, meta_waba_id)`,
  `(provider_key, meta_phone_number_id)`;
- unique non-null `business_phone_e164` across tenants;
- a check constraint for known status values;
- no access tokens, authorization codes, API keys, or unbounded raw provider
  JSON in this table.

Do not model `provider_key` as a SQL enum or add YCloud-only columns to the
canonical table. Add another provider reference or extension table only if an
approved provider contract proves it is necessary.

Reuse the existing immutable `OperationalEvent` ledger instead of creating a
new audit table. Add one `whatsapp.connection.updated` event type and record a
bounded operation, actor, previous/new canonical state, safe reason code, and
correlation ID. Do not copy tokens or raw provider bodies. Do not persist the
one-time exchangeable token code after the synchronous server exchange.

### Routing compatibility

When the provider confirms the tenant's first real connection:

```text
lock tenant + connection
  -> prove WABA/phone ownership through server-to-server retrieval
  -> normalize and uniqueness-check business phone
  -> set connection = connected
  -> set Professional.assistant_phone = business_phone_e164
  -> append audit/operational event
  -> commit once
```

For mock connections, keep the mock phone only in the mock connection record
and leave `Professional.assistant_phone` unchanged. Existing mock chat can
continue using its tenant-scoped setup independently.

Outbound code continues using the global provider registry, which is already
the application's composition boundary. Before a tenant send, require its
connection to be `connected` and its `provider_key` to match the configured
`WHATSAPP_PROVIDER`; otherwise fail closed. Domain services never instantiate
YCloud or branch on its key.

Inbound message/echo routing can continue using the receiving
`Professional.assistant_phone`; the webhook path supplies the provider key and
the connection must match the globally active provider. Delivery records keep
their explicit `provider_key`, as they do today, so the old provider's callback
endpoint can remain temporarily available to finish delivery reconciliation
after a global cutover. New inbound messages from the old provider are rejected
once the maintenance cutover begins.

## 8. API contract

Use the existing response/error conventions and add stable codes through
`error_codes.py` / `error_responses.py`. All endpoints require an authenticated
professional role (or explicit platform-admin impersonation), derive the
tenant from the token, enforce CSRF/origin checks on writes, and use write rate
limits.

| Endpoint | Behavior |
|---|---|
| `GET /api/whatsapp-connections/current` | Returns rollout availability plus the tenant's connection or `disconnected` view |
| `POST /api/whatsapp-connections/current/onboarding` | Creates/refreshes the expiring attempt on the tenant connection and returns safe launch configuration |
| `POST /api/whatsapp-connections/current/onboarding-completion` | Accepts the Embedded Signup result once, validates correlation/ownership, and starts bind/register |
| `POST /api/whatsapp-connections/current/refresh` | Idempotently retrieves and reconciles authoritative provider state |

The current-state response should be a discriminated schema, not loosely typed
provider JSON. Example:

```json
{
  "data": {
    "availability": "demo",
    "allowed_actions": ["start_onboarding"],
    "connection": {
      "id": "7aa9c4e7-5b35-4d52-a89e-c2ddf8f4eef5",
      "provider": "mock",
      "status": "disconnected",
      "is_demo": true,
      "phone_masked": null,
      "business_display_name": null,
      "action_code": null,
      "last_synced_at": null
    }
  },
  "error": null
}
```

The backend decides `availability` (`disabled`, `demo`, `live`) and the single
global provider from validated server configuration. Ignore any client attempt
to choose a provider, tenant, status, phone, or mock outcome. `allowed_actions`
is computed from canonical state and the implemented global adapter; the
backend rechecks permission/state for every operation.

Suggested safe error codes include:

- `WHATSAPP_ONBOARDING_UNAVAILABLE`
- `WHATSAPP_ONBOARDING_ATTEMPT_EXPIRED`
- `WHATSAPP_ONBOARDING_RESULT_INVALID`
- `WHATSAPP_PHONE_ALREADY_ASSIGNED`
- `WHATSAPP_CONNECTION_ACTION_REQUIRED`
- `WHATSAPP_PROVIDER_TEMPORARILY_UNAVAILABLE`

Provider error messages are logged server-side with the correlation ID and
mapped to generic client messages. A YCloud/Meta stack trace, response body,
tenant identifier, or token must never appear in a browser response.

## 9. Security, privacy, and operational requirements

- Validate exact Meta message origins and documented event types; never use a
  broad substring/suffix check for a security decision.
- Generate at least 128 bits of random attempt state, bind it to tenant + user +
  session, store only a hash, expire it quickly, and consume it once.
- Re-fetch WABA/phone data server-to-server after browser completion. Browser
  identifiers are claims, not proof of ownership.
- Load the Meta SDK only on the connection page and pin/configure it according
  to Meta's current Embedded Signup guidance. Update Content Security Policy
  narrowly for the required origins.
- Use HTTPS for every real environment and register each exact production/test
  domain with Meta/YCloud. Local mock mode must not need the SDK or HTTPS.
- Keep partner API credentials in the deployed secret manager exposed through
  `.env` names; never commit real values. Startup must fail closed in real mode
  when required values are absent.
- Treat phone, business identity, WABA IDs, provider status, IP, and audit
  metadata as tenant data subject to the existing LGPD retention/access model.
- Do not log full phone numbers in normal operation; use the project's masking
  pattern. Never log authorization codes or tokens, even at debug level.
- Verify every webhook signature before persistence/dispatch, retain replay-age
  checks, deduplicate provider lifecycle events, and reject unknown ownership.
- Paused/degraded/disconnected connection state must prevent tenant customer
  sends and scheduled tasks from using that connection. Do not block the
  separate platform-managed private agent accidentally.
- Define support ownership for Meta verification, payment method, banned
  numbers, quality degradation, and partner removal before pilot rollout.

## 10. Implementation roadmap

Each phase is independently reviewable. Do not begin the real-provider phase
until its YCloud gate is satisfied.

### Phase 0 — Product contract and frontend prototype

**Goal:** approve what the tenant will see before adding persistence or partner
code.

- Confirm that the first supported path is WhatsApp Business App Coexistence
  and that `assistant_phone` is the number being connected.
- Define Portuguese copy for prerequisites, consent/disclosure, connection
  consequences, errors, and support. Legal reviews any claim about data access,
  Meta/YCloud processing, costs, and continued Business App use.
- Build the page from local typed fixtures for `disconnected`, `authorizing`,
  `binding`, `action_required`, `connected`, and `degraded`.
- Add the persistent demonstration banner and a local state gallery available
  only in development/platform-admin preview. Do not connect the sidebar item
  for general tenants yet.
- Review desktop, narrow mobile, long Portuguese copy, keyboard order, focus,
  and light/dark colour contrast.

**Verify:** product sign-off on screenshots/interactive preview for every
state; `conda run -n agenda npm --prefix frontend run lint` and
`conda run -n agenda npm --prefix frontend run build` pass.

### Phase 1 — Canonical lifecycle, persistence, and mock API

**Goal:** make the prototype a tenant-safe product slice with no external
network call.

- Add the single connection model and one local Alembic migration; reuse
  `OperationalEvent` for audit.
- Add typed Pydantic request/response models, canonical transition service,
  global adapter registry, stable error codes, and mock onboarding adapter.
- Add `WHATSAPP_ONBOARDING_AVAILABILITY=disabled|demo|live`, defaulting to
  `disabled`; leave the existing global `WHATSAPP_PROVIDER` unchanged, plus a
  tenant feature key such as `whatsapp_connection` managed through the
  existing admin feature pattern.
- Implement the current/start/complete/refresh endpoints for `mock` mode.
- Ensure mock completion cannot update `Professional.assistant_phone`, even if
  a request is replayed or malformed.
- Create the reusable messaging + onboarding provider contract suite and make
  the mock onboarding adapter pass its suite before adding real onboarding code.
- Audit every mutation and bind attempt/user/session/tenant server-side.

**Verify:** migration upgrade/downgrade on local `agenda_db`; service and API
tests cover transition rules, expiry, idempotency, RBAC, tenant isolation,
admin impersonation, CSRF, rate limiting, forged tenant/provider/status/phone,
duplicate provider ownership, and audit creation. No remote DB access.

### Phase 2 — Production-shaped mock frontend

**Goal:** ship the useful mockup requested now using the same API the real flow
will use.

- Replace fixture reads with `frontend/src/lib/api.ts` calls and add exact
  discriminated TypeScript types in `frontend/src/lib/types.ts`.
- Add `/configuracoes/whatsapp`, the feature-aware sidebar entry, responsive
  cards, status stepper, prerequisites, safe diagnostics, and recovery actions.
- Implement optimistic start/refresh/retry behavior with rollback described in
  Section 6.
- Render actions from canonical state/`allowed_actions` only; add a frontend test
  that fails if changing `provider` changes the visible workflow for otherwise
  identical canonical responses.
- Keep demo scenario controls out of the product UI; local/test configuration
  selects the scenario.
- Add a short page document under `docs/pages/` covering user behavior and
  clearly stating that mock mode does not connect or send messages.

**Verify:** component/interaction tests for each state, optimistic rollback,
duplicate completion, accessibility labels/live regions, and mobile layout.
Because the frontend currently has no test runner, add the smallest pinned
Vitest + Testing Library setup only when these stateful interactions are
implemented, then keep `package-lock.json` synchronized. Also pass lint, type
check/build, and manual 360 px/mobile keyboard review.

### Phase 3 — YCloud/Meta partnership readiness gate

**Goal:** replace assumptions with an approved integration contract. This phase
is blocking for all real-account code.

Obtain and record from YCloud:

- Tech Partner approval/eligibility and the applicable commercial plan;
- required Meta Tech Provider status and business verification;
- ownership and values of Meta App ID, Login Configuration ID, Solution ID,
  and permitted domains;
- exact Business App Coexistence/SMB bind contract;
- whether a code exchange is required, by whom, and its expiry/retry behavior;
- whether Coexistence requires separate number registration; if so, its phone
  ID/OTP inputs, status enum, and retry limits;
- how `paymentMethodAttached`, credit line, tenant billing, taxes, and failed
  payment are represented;
- webhook secret scope, events, retry policy, ordering, and whether one partner
  callback covers all customer WABAs;
- reconnect, partner removal, customer disconnect, phone change, and complete
  offboarding semantics;
- sandbox/test WABA support, rate limits, data residency, SLA, support path,
  and which brand names Meta displays during signup.

Also obtain current Meta Embedded Signup documentation for the approved flow
and freeze representative sanitized request/response/webhook fixtures in tests.

**Verify:** a signed-off contract matrix maps each canonical operation and
state to an official YCloud/Meta request, response, webhook, retry rule, and
support owner. Security/legal approve scopes, privacy disclosure, retention,
and billing copy. Without this matrix, keep availability `demo` or `disabled`.

### Phase 4 — Real YCloud onboarding adapter

**Goal:** connect one internal test tenant through Embedded Signup without
changing the Phase 2 UI contract.

- Add real-mode environment validation and document only placeholder names in
  `.env.example`; keep values in deployed secret management.
- On first live onboarding, reset that tenant's `mock` connection row to a
  clean `ycloud`/`disconnected` state and clear demo identifiers in the same
  audited transaction. Mock mode never changed `assistant_phone`, so no routing
  migration is needed.
- Return public launch IDs from the authenticated backend rather than baking
  deployment values into the frontend bundle.
- Load/configure the Meta SDK on demand, create the correlated attempt, capture
  only documented completion/cancel/error events, and submit completion to the
  backend.
- Implement the YCloud onboarding adapter for Coexistence bind, authoritative
  retrieve, and any required registration branch; keep mappings, endpoints,
  headers, and provider errors inside the adapters.
- Verify provider ownership and atomically connect the tenant/update
  `assistant_phone` as described in Section 7.
- Keep the existing message provider adapter and webhook receipt pipeline;
  extend them only where the frozen partner contract proves necessary.
- Make YCloud onboarding pass the same onboarding suite as mock, while its
  messaging adapter continues to pass the messaging suite.

**Verify:** adapter contract tests use captured sanitized fixtures; browser
tests cover success/cancel/popup-blocked/expired/replayed/cross-tenant cases;
one internal test WABA reaches `connected`; an inbound message, outbound echo,
and provider delivery update traverse the existing pipeline under the correct
tenant. No production tenant is enabled yet.

### Phase 5 — Lifecycle reconciliation and safe offboarding

**Goal:** remain correct after initial signup.

- Subscribe to and normalize the documented WABA/phone update, quality,
  reconnection/offboarding, partner removal, and deletion events needed for the
  canonical state machine.
- Use lifecycle webhooks plus the existing manual status refresh. Add scheduled
  reconciliation only if pilot evidence shows missed events are a real problem.
- Before each tenant customer send, require connection status `connected` and
  connection `provider_key == WHATSAPP_PROVIDER`; keep storing provider key on
  outbound delivery records.
- Block affected tenant sends/tasks when state becomes non-operational and
  present an actionable page state.
- Expose only the masked provider identifiers, timestamps, safe state/error,
  and correlation code needed by platform support. Add provider-management
  tools only when a repeated support task justifies them.

**Verify:** tests cover duplicate and out-of-order lifecycle events, transient
provider failures, stale reads, partner removal, reconnect,
cross-tenant provider IDs, worker retries, and routing fail-closed behavior.

### Phase 6 — Controlled pilot and rollout

**Goal:** prove onboarding and first-message success with a small real cohort.

- Enable real mode only in the intended environment and feature-enable one
  internal tenant, then a small named pilot cohort.
- Track funnel steps: page viewed, signup started, Meta completed, bind
  completed, connected, first inbound received, first echo received, and time
  to resolution for failures. Use internal IDs/correlation IDs, not tokens or
  full phone numbers.
- Create support runbooks for verification, payment/action required, banned or
  low-quality numbers, reconnect, partner removal, and YCloud escalation.
- Define rollback as disabling new attempts while leaving already-connected
  messaging operational unless a security issue requires a wider stop.
- Review observed conversion, failure reasons, support load, message quality,
  cost allocation, and tenant isolation before expanding the feature flag.

**Verify:** agreed pilot completion rate and first-message success threshold,
zero cross-tenant incidents, webhook/delivery monitoring healthy, support can
resolve every observed state, and rollback drill completed.

## 11. Platform-managed provider replacement runbook

Provider modularity makes a switch contained; it cannot guarantee that Meta or
two BSPs allow the same number/WABA to be attached simultaneously. Confirm
number portability, WABA ownership, coexistence, billing, and offboarding rules
with both providers before promising a zero-downtime migration.

1. **Qualify the replacement.** Implement its two adapters, add the two strict
   registry branches, map its payload/status/error values to canonical types,
   and pass the shared contract suite in a non-production environment.
2. **Prepare every tenant account.** Confirm number/WABA portability and create
   the required provider-side bindings. Produce a validated migration mapping
   for all connected tenants; do not change live rows yet.
3. **Enter a maintenance window.** Disable new onboarding and customer-channel
   sends, drain queued/accepted old-provider work, and stop accepting new
   inbound messages from the old provider. The UI explains the temporary
   channel maintenance state.
4. **Apply one reviewed migration.** Update each connection's provider key and
   external account/phone IDs from the validated mapping in a local-tested,
   transactional migration/script. Record platform and per-tenant operational
   events. Remote execution requires separate approval.
5. **Switch globally.** Deploy the new provider credentials and change the one
   `WHATSAPP_PROVIDER` value. Startup/preflight must verify that every connected
   tenant row matches the configured provider before customer traffic resumes.
6. **Verify and resume.** Run a controlled inbound, echo, outbound, and delivery
   check; then re-enable traffic for the platform.
7. **Drain old callbacks.** Keep the old webhook adapter/secret temporarily so
   delivery updates for previously stored old-provider message IDs can finish.
   Do not accept new old-provider conversations and do not rewrite historical
   message/run `provider_key` values.
8. **Rollback if required.** During the agreed rollback window, pause traffic,
   restore the reviewed old connection mapping and global environment value,
   verify, and resume. Offboard the old provider only after the window closes.

This is intentionally a maintenance-window migration. Avoid dual-provider
routing, tenant cohorts, background mirroring, and automatic fallback unless a
future availability requirement demonstrates that the extra complexity is
worth it.

## 12. Test and acceptance matrix

| Layer | Minimum proof before real pilot |
|---|---|
| State machine | Every allowed transition succeeds; every impossible/backward transition fails without partial writes |
| Model/migration | Constraints enforce one tenant connection and unique provider/phone ownership; local upgrade/downgrade succeeds |
| API/RBAC | Professional sees only own connection; normal admin without impersonation cannot mutate it; explicit impersonation is audited |
| Web security | CSRF, origin, state correlation, expiry, single use, exact Meta origin, malformed event, and replay tests |
| Mock safety | Every demo state works; mock completion never changes real routing or enables a real send/task |
| Concurrency | Two starts/completions/refreshes and competing phone assignments converge idempotently |
| Provider contracts | Each provider's messaging/onboarding pair passes the same required cases |
| Provider adapter | Sanitized fixtures cover success, action required, invalid credentials, 4xx, 429, 5xx, timeout, ambiguous delivery, and malformed response |
| Dependency boundary | Provider names/imports/config keys occur only in provider adapter modules, registry, `.env.example`, and provider documentation |
| Webhooks | Valid signature accepted; invalid/stale signature rejected; duplicate/out-of-order lifecycle events converge safely |
| Routing | Global registry selects outbound adapter; connection key must match it; old delivery updates reconcile by stored provider key; `agent_phone` behavior is unchanged |
| Frontend | Every state/copy/action renders; identical canonical responses render identically across provider keys; optimistic rollback, keyboard/live-region/mobile behavior passes |
| Provider cutover | Maintenance stop, validated all-tenant mapping, global switch, verification, old-callback drain, and rollback pass |
| End-to-end | Meta complete → YCloud bind/register → authoritative connected → inbound + echo → tenant conversation, with one correlation trail |
| Operations | Metrics, redacted logs, alerts, retry/reconciliation, support lookup, feature kill switch, and rollback drill work |

Regression runs must use the project's conda environment:

```bash
conda run -n agenda pytest backend/tests -q --ignore=backend/tests/test_extraction.py
conda run -n agenda npm --prefix frontend run lint
conda run -n agenda npm --prefix frontend run build
```

Add focused commands for the new backend/frontend suites as they are created.
Do not claim the feature complete from screenshots alone.

## 13. Proposed environment contract

Names are provisional until Phase 3 confirms YCloud/Meta terminology:

```dotenv
WHATSAPP_ONBOARDING_AVAILABILITY=disabled
WHATSAPP_PROVIDER=ycloud
# WHATSAPP_MOCK_SCENARIO=success

# Required only when availability is live and the selected provider is ycloud
META_WHATSAPP_APP_ID=replace-with-public-app-id
META_WHATSAPP_LOGIN_CONFIGURATION_ID=replace-with-configuration-id
YCLOUD_WHATSAPP_SOLUTION_ID=replace-with-solution-id
YCLOUD_API_KEY=replace-with-server-api-key
YCLOUD_WEBHOOK_SIGNING_SECRET=replace-with-provider-signing-secret
```

`WHATSAPP_PROVIDER` selects the real messaging/onboarding adapter pair for the
whole deployment. Demo availability substitutes only the mock onboarding
adapter and cannot alter messaging or routing. Changing `WHATSAPP_PROVIDER` in
an environment requires the global migration runbook in Section 11; it is not
a routine toggle.

Validate the selected provider's required settings at startup and fail closed
when live configuration is incomplete. Keep provider-prefixed environment
reads inside its adapters or one small provider configuration helper.

Do not expose the server API key/signing secret through `NEXT_PUBLIC_*`. If an
App/Configuration/Solution ID must reach the browser, return it from the
authenticated attempt-start response so deployment validation and feature
gating stay server-owned. Keep `requirements.txt`, `frontend/package.json`, and
the lockfile pinned and synchronized if implementation adds dependencies.

## 14. Observability and support contract

Track state-transition counters and duration histograms by environment,
provider, canonical state, and safe failure code. Do not use
tenant business names or full phone numbers as metric labels.

Minimum alerts:

- sustained bind/register failure rate;
- attempts stuck in `binding` beyond the provider SLA;
- lifecycle webhook signature failures or receipt backlog;
- provider says connected while local routing phone is absent/mismatched;
- provider removal/deletion for an active tenant;
- repeated phone-ownership conflicts;
- scheduled/outbound sends attempted for a non-operational connection.

The tenant UI receives a safe correlation code and a clear next action. The
platform-admin view may show masked WABA/phone identifiers, timestamps,
canonical/provider states, recent safe failure codes, and a reconciliation
action. Full provider responses remain in access-controlled, redacted logs
only when operationally necessary.

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Partnership or endpoint access is delayed | Finish Phases 0–2; keep production mode disabled and avoid provider-specific UI assumptions |
| “White label” is interpreted as cloning YCloud's console | Keep scope on native Embedded Signup; evaluate YCloud's separate white-label console only as a separate commercial initiative |
| Coexistence eligibility varies by tenant/number | Present prerequisites as guidance, rely on authoritative flow/provider state, and map failures to `action_required` |
| Browser result is spoofed or replayed | Short-lived single-use state plus server-to-server ownership retrieval before connection |
| One platform credential can access many customer WABAs | Strict tenant/provider ID ownership constraints, least-privilege secret storage, redacted audit, and cross-tenant tests |
| Existing `assistant_phone` conflicts with a newly connected phone | Read-only preflight, normalized global uniqueness, locked transactional assignment, and explicit conflict recovery; no automatic reassignment |
| Provider state changes after signup | Lifecycle webhooks plus scheduled authoritative reconciliation and fail-closed sending |
| Disconnect semantics cause message loss | Keep tenant-initiated disconnect out of v0.1; add it only after the provider contract and recovery behavior are documented |
| Billing/payment state blocks sending | Confirm responsibility and API signal in Phase 3; expose a specific safe action-required state and support path |
| Meta/YCloud changes SDK payloads or statuses | Keep provider fixtures/versioned adapter mapping, reject unknown shapes safely, and review upstream changelogs before rollout |
| Demo is mistaken for a live connection | Persistent banner, `is_demo`, distinct CTA/copy, no real routing mutation, and production default `disabled` |
| A replacement provider cannot reuse the same WABA/number | Treat portability as a commercial/Meta preflight gate; support tenant reauthorization and a controlled maintenance window rather than hiding the constraint |
| Provider branches spread through domain/UI code | Two canonical protocols, registry/import allowlist check, mock onboarding contract tests, and both suites for every real provider |
| Late old-provider callbacks mutate current state | Accept only delivery updates tied to stored old-provider message IDs; ignore old-provider connection lifecycle/inbound events after cutover |

## 16. Decisions required before Phase 0 implementation

The roadmap currently recommends the following; product approval should make
them explicit before code starts:

1. The connected tenant number is the existing customer-facing
   `assistant_phone`, while `agent_phone` stays platform-managed.
2. WhatsApp Business App Coexistence is the initial supported flow.
3. **WhatsApp** is a dedicated sidebar destination at
   `/configuracoes/whatsapp`, not a tab inside `/minhas-regras`.
4. The first deliverable is an interactive, clearly labelled mock available to
   approved preview users; general production users see nothing until enabled.
5. Tenant v0.1 supports exactly one active WhatsApp customer connection.
6. The YCloud Tech Partner route is pursued for native onboarding. The YCloud
   white-label console is not part of this feature.
7. Provider selection/migration is global and platform-managed; tenants see
   WhatsApp connection state/actions, not a provider picker.

## 17. Definition of done

The **mockup milestone** is done after Phase 2: approved tenants can exercise
the production-shaped UI/API in demo mode, all state/security/mock-isolation
tests pass, mock passes the shared onboarding contract suite, frontend behavior
contains no provider-specific branch, documentation states that no real
account is connected, and no YCloud partnership is needed.

The **real connection milestone** is done only after Phase 6: official partner
contracts are captured, one real Coexistence WABA is connected and reconciled,
inbound/outbound echo behavior is tenant-correct, provider-disconnection
recovery and
support are operational, rollout gates pass, and the production feature is
enabled only for the approved cohort.

The **provider portability milestone** additionally requires both live global
registry lookups to use `WHATSAPP_PROVIDER`; mock and YCloud onboarding to pass
the same onboarding suite; every real provider to pass both contract suites;
each tenant connection to match the global provider before traffic is enabled;
outbound records to retain their provider key; and a non-production global
cutover/drain/rollback drill. Adding a later provider should normally touch
only its two adapter modules, two registry branches, provider-prefixed
environment documentation, and fixtures/tests. Any required domain/frontend
change is an architectural exception that must be explained before
implementation.

Until then, do not describe the feature as live WhatsApp onboarding.
