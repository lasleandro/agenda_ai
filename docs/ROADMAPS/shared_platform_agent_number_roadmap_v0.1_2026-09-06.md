# Shared Platform AI Agent Number Roadmap v0.1 — 2026-09-06

**Status: implemented locally 2026-09-06 (Phases A–J).** This roadmap replaces
the former *per-tenant* instructor agent number (`Professional.agent_phone`,
now dropped) with **one shared platform agent number**
(`PLATFORM_AGENT_WHATSAPP_NUMBER`) in the same YCloud account as every tenant's
customer-facing number. Tenant resolution on the agent channel inverted from
"which number was this addressed to" to "which known instructor sent this",
plus a challenge-code binding second factor. Remaining before production: the
Phase C production-data preflight, a Phase G Playwright e2e spec, and the
cutover runbook — all operator actions, noted per phase. Full backend suite
green (405); frontend typecheck + lint clean; migration chain
`a1f4c7e9b2d6` → `b2e5d8f1a4c7` up/down verified on local `agenda_db`.

It also fixes a data-integrity defect that exists **today**, independently of
this migration: nothing stops the passive-observer pipeline from ingesting the
instructor's private agent-channel traffic as if it were a student
conversation.

Design discussion that produced this plan:

- The platform runs on **YCloud Coexistence** (see
  `docs/whatsapp_schedule_copilot_poc_project_brief_v0.1.md` §261, §327, §350).
  A tenant's number stays on the instructor's WhatsApp Business *app*; the
  platform observes `whatsapp.inbound_message.received` (student) and
  `whatsapp.smb.message.echoes` (instructor). This is the fact that makes a
  shared agent number viable at all — because the tenant number is a live app
  number and not API-only, the instructor can send messages *to* the platform
  agent number from their own phone.
- One YCloud account, one WABA. Each tenant gets one manually registered
  number (`assistant_phone`, instructor ↔ students). The platform agent number
  is registered once, in that same account, and is shared by all tenants.
- Tenant isolation does not weaken. It moves from
  `uq_professionals_agent_phone` to `uq_professionals_assistant_phone` — the
  same unique-number invariant, one column over, and that constraint already
  exists.
- **Authentication does weaken**, and this is accepted with a mitigation.
  Today two independent gates must pass: a semi-private per-tenant agent
  number *and* a matching sender. With a public shared number, `from_phone`
  becomes both the tenant discriminator and the sole authenticator. Phase F
  restores a second factor via a one-time, audited binding handshake.
- Interaction on the agent channel is **instructor-initiated** (confirmed
  decision). That keeps free-form replies inside WhatsApp's 24-hour customer
  service window by construction. It does *not* cover the two genuinely
  proactive flows that already exist — daily agenda summary and passive
  escalation — which Phase H handles explicitly.

## 1. Goal and product outcome

Onboard a new tenant by registering **one** WhatsApp number, not two, and let
every instructor talk to the same platform assistant number without any tenant
seeing another tenant's data.

After implementation:

- A single `PLATFORM_AGENT_WHATSAPP_NUMBER` serves every tenant's Mode 1
  (active instructor agent) traffic over WhatsApp.
- An inbound message to that number resolves its tenant by matching
  `from_phone` against `Professional.assistant_phone`, filtered to
  `status == "active"` and to tenants that have completed the binding
  handshake. An unrecognized or unbound sender is silently dropped.
- `Professional.agent_phone` and `uq_professionals_agent_phone` no longer
  exist. Onboarding a tenant requires exactly one number.
- The passive observer never ingests agent-channel traffic. No Contact,
  Conversation, or Message row is ever created for a platform-owned number.
- A platform admin can view and correct a tenant's WhatsApp number and see its
  binding state from the admin tenant grid.
- Mode 2 (passive observer) behaviour over `assistant_phone` is unchanged.

## 2. Scope and non-goals

### In scope

- `PLATFORM_AGENT_WHATSAPP_NUMBER` as externalized configuration, with a
  single accessor used by every call site.
- A hard exclusion guard keeping platform-owned numbers out of the observer
  lane, plus detection and cleanup of rows already contaminated.
- Sender-keyed tenant resolution in `agent_channel.try_handle`.
- Dropping `Professional.agent_phone` and updating every reader
  (`passive_escalation`, `scheduled_tasks`, `admin`).
- A one-time instructor binding handshake and its revocation path.
- Admin UI to read/edit a tenant's `assistant_phone` and see binding state.
- Correcting the outbound `from_phone` on both proactive flows, and giving
  passive escalation a template so it survives the 24-hour window.

### Out of scope

- **Per-tenant provider credentials or per-tenant provider choice.** One
  YCloud account, one API key, as today.
  `docs/whatsapp_provider_portability_assessment.md` §47 parks this as a
  separate approved initiative; nothing here should pre-empt it.
- **Self-service WhatsApp connection.** Numbers stay manually registered by
  the team during rollout; `/configuracoes/whatsapp` keeps its
  request-connection flow.
- **A durable outbound outbox.** The portability assessment flags direct
  `send_text` as a medium-severity gap. It is a real gap and it gets worse
  with a shared number, but it is a separate initiative — see §8.
- **Multiple instructors per tenant.** `assistant_phone` is one number and
  `_resolve_actor_user` resolves one `professional`-role user. Unchanged
  known limit.
- Media, reactions, replies, or interactive buttons on the agent channel.

## 3. Current state and reusable assets

### What already works and must not regress

| Concern | Where | Reuse approach |
| --- | --- | --- |
| Tenant lookup by number | `ingestion.get_professional_by_phone()` | Already filters `status == "active"` and refuses to default to another tenant. This becomes the agent channel's resolver too — no new query. |
| Number uniqueness | `uq_professionals_assistant_phone` | Already guarantees one tenant per number. It becomes the sole isolation invariant. |
| Provider boundary | `integrations/whatsapp/{provider,contracts,registry}.py` | `from_phone` is already a per-request field, not config. Swapping which number the platform sends from needs **no adapter change**. |
| Webhook durability | `webhook_receipts` + `webhook_processor.process_receipt` | Idempotent on the receipt; unchanged. |
| Message idempotency | `Message.provider_message_id` unique | Protects against webhook retries; unchanged. |
| Propose → confirm → execute | `app/agent/candidates.py`, `mutations.py` | The agent channel keeps proposing and never writes directly. Unchanged. |
| Agent conversation history | `AgentChannelMessage`, windowed by `memory_window_messages` + `HISTORY_MAX_AGE` | Already keyed by `professional_id`, not by number. Survives the migration untouched. |
| Admin authorization | `require_platform_admin` | Required on every new admin endpoint. |
| Phone canonicalization | `services/phone_numbers.normalize_mobile_phone()` | Reuse for any admin-entered number; never store an unnormalized value. |
| Admin number input | `frontend/src/components/ui/whatsapp-field.tsx` | Already used by the create-tenant dialog; reuse in the edit dialog. |
| Audit | `services/operational_events.record_event()` | Every binding, unbinding, and admin number change records an event. |

### The defect this roadmap also fixes

`dispatch_whatsapp_event` ([ingestion.py:151-162](../../backend/app/chat/ingestion.py#L151-L162))
routes an event to `agent_channel.try_handle()` first, then falls through to
`ingest_normalized_message`. `try_handle` returns `False` immediately for any
`direction != "inbound"` event
([agent_channel.py:312](../../backend/app/chat/agent_channel.py#L312)).

Because the agent number lives in the same YCloud account, one instructor→agent
message produces **two** webhook events with different
`provider_message_id`s:

1. `inbound_message.received` on the agent number — claimed correctly.
2. `smb.message.echoes` on the tenant number (`from=assistant_phone`,
   `to=`agent number) — falls through to the observer.

In that fallthrough
([ingestion.py:64-115](../../backend/app/chat/ingestion.py#L64-L115)) an
outbound echo computes `assistant_phone = from_phone` (resolves the tenant
correctly) and `contact_phone = to_phone` — **the agent number**. The observer
then creates a Contact for the platform's own number, opens a Conversation,
and feeds the instructor's private agent messages into the extraction pipeline.
The agent's replies arrive on the tenant number as inbound events and
contaminate the same conversation in reverse.

There is no exclusion filter anywhere in the dispatch path. This is a live
defect, not a consequence of the migration; Phases B and C address it and can
ship before anything else.

## 4. Product and architecture decisions

1. **Routing inverts from recipient-keyed to sender-keyed.**

   ```
   today:   tenant = lookup(to_phone -> agent_phone)
            authorize: from_phone == tenant.assistant_phone
   target:  guard:  to_phone == PLATFORM_AGENT_WHATSAPP_NUMBER
            tenant = lookup(from_phone -> assistant_phone, status=active, bound)
   ```

   The `to_phone` guard runs **first** and claims the message regardless of
   whether a tenant resolves. An unknown sender must not fall through to the
   observer lane.

2. **The platform agent number is configuration, not tenant data.** It lives in
   `.env` per project rule 8, behind one accessor. `Professional.agent_phone`
   is dropped rather than kept "just in case" — a future white-label tenant
   number is a new, separately justified feature (YAGNI).

3. **Unknown or unbound senders get no reply.** Preserves the existing
   fail-closed posture at
   [agent_channel.py:324-333](../../backend/app/chat/agent_channel.py#L324-L333):
   silence means an unauthorized sender cannot confirm the number is live or
   enumerate registered tenants.

4. **Binding restores the second factor via a challenge code.** Coexistence
   registration already proves number ownership once, at onboarding. What it
   does not prove is that the number is *still* the tenant's (recycling, SIM
   swap) or that the tenant has opted into WhatsApp agent control. The
   handshake:

   - The authenticated web session at `/configuracoes/whatsapp` displays a
     short code and the platform agent number.
   - The instructor sends that code to the agent number from their phone.
   - The agent channel resolves the pending code → `professional_id`, verifies
     `from_phone == professional.assistant_phone`, stamps
     `agent_binding_confirmed_at`, records an audit event, and replies with a
     confirmation.

   This proves live control of the number at bind time, produces an explicit
   audited opt-in, and — usefully — opens the 24-hour service window as a side
   effect. It fits the confirmed "instructor-initiated" interaction model: the
   first message they ever send is the binding code.

   *Cheaper alternative, if the code flow is judged over-built:* a plain
   "Ativar assistente" button in the web UI that stamps the same column. It
   keeps the audited opt-in but drops the proof of live number control. See
   §9.

5. **Binding is revocable and auto-revokes.** Clearing
   `agent_binding_confirmed_at` disables the channel. Suspend/archive already
   locks it out through the existing `status == "active"` filter, so no extra
   work there.

6. **Proactive sends are the exception to instructor-initiated.** Daily agenda
   already uses `send_template` and stays correct once `from_phone` changes.
   Passive escalation uses free-form `send_text`
   ([passive_escalation.py:148](../../backend/app/services/passive_escalation.py#L148))
   and will be rejected by Meta outside the 24-hour window. It gets its own
   approved template rather than being silently dropped — escalation *is* the
   product value of Mode 2.

7. **Cost model shifts.** Per the project brief §401, Coexistence traffic is
   not billed by Meta; only API sends are. Every agent reply from the shared
   number is an API send, so billed volume now scales with tenant count rather
   than staying a handful of messages per tenant per day. Not a blocker;
   recorded so the pricing model is not surprised.

## 5. Implementation phases

Each phase is independently verifiable and leaves the system working. Phases
A–C are a self-contained data-integrity fix and can ship before any routing
change.

### Phase A — Platform agent number as configuration

**Status: done 2026-09-06.** `PLATFORM_AGENT_WHATSAPP_NUMBER` added to
`.env`/`.env.example`; `backend/app/integrations/whatsapp/platform_number.py`
holds `platform_agent_number()` (E.164 or `None`) and `is_platform_number()`.
Covered by `backend/tests/test_platform_number.py` (10 cases); app boots with
the variable absent and the feature stays inert.

Introduce the number as config with no behaviour change yet.

- Add `PLATFORM_AGENT_WHATSAPP_NUMBER` to `.env` and `.env.example`, in the
  existing WhatsApp block.
- Add one accessor — `platform_agent_number()` — returning the normalized
  E.164 value or `None` when unset. Place it beside the provider boundary
  (`app/integrations/whatsapp/`) so both the chat and services layers can
  import it without a cycle.
- Add `is_platform_number(phone)` on top of it. This is the single predicate
  every later phase asks; no call site compares raw strings.

**Verify:** unit test covering set/unset/unnormalized input; app boots with the
variable absent (feature simply inert).

### Phase B — Lane isolation guard

**Status: done 2026-09-06.** `dispatch_whatsapp_event` now drops any event
touching a platform-owned number (either `from_phone` or `to_phone`) before the
observer lane, logging a masked warning. `_is_platform_owned_number(db, phone)`
in `ingestion.py` ORs `is_platform_number()` with a `Professional.agent_phone`
lookup (the transitional branch Phase E removes). Covered by three cases in
`test_ingestion.py`: echo to the platform number, echo to a per-tenant
`agent_phone`, and an unaffected normal echo. No regression across
ingestion/agent-channel/pipeline/webhook suites.

Stop the observer from ever seeing platform-owned traffic.

- In `dispatch_whatsapp_event`, before the `try_handle` → `ingest` fallthrough,
  drop any `WhatsAppMessageEvent` where **either** `from_phone` or `to_phone`
  is a platform number and the event was not claimed by the agent channel.
  Log at warning with the direction and masked numbers.
- Guard both directions explicitly — the echo case (`to_phone` is the agent
  number) and the agent-reply case (`from_phone` is the agent number).
- During the transition the per-tenant `agent_phone` values are still live, so
  `is_platform_number()` must also treat any non-null `Professional.agent_phone`
  as platform-owned until Phase E drops the column.

**Verify:** tests asserting that an `smb.message.echoes` event addressed to the
platform number creates **no** Contact, Conversation, or Message; and that a
normal student echo still ingests exactly as before.

### Phase C — Contamination forensics and cleanup

**Status: done locally 2026-09-06; production preflight pending operator.**
`scripts/audit_agent_channel_contamination.py` reports contaminated
Contacts/Conversations/Messages/candidates (read-only by default,
`SET TRANSACTION READ ONLY`). Local `agenda_db` is **clean** — zero
contaminated rows. `--apply` deletes the debris but refuses when any candidate
was acted on or a contaminated Contact is referenced by a real domain record.
Still to do by the operator: run the read-only report against a restored copy
of production before the Slice 2 cutover (never `--apply` against Azure — rule
2).

Find and remove rows the missing guard already created. Local first, then sync
to Azure per project rule 2 — no destructive action against the remote DB.

- Add `scripts/audit_agent_channel_contamination.py` (project rule 4):
  report Contacts whose `phone` matches any platform-owned number, with their
  Conversations, Message counts, and any `AppointmentCandidate` rows extracted
  from those conversations.
- Run read-only against local, then against a **restored copy** of production
  data. Do not run a mutating pass against Azure.
- Only if the report is non-empty: add an explicit, reviewed cleanup pass to
  the same script, gated behind a `--apply` flag, that deletes the polluted
  Contact/Conversation/Message rows and any candidates derived from them.

**Verify:** the audit script reports zero rows after cleanup; re-running the
Phase B tests confirms no new contamination is possible.

### Phase D — Sender-keyed agent-channel routing

**Status: done 2026-09-06.** `agent_channel.try_handle` now returns `False`
unless `to_phone` is the platform agent number, resolves the tenant with a
lazily-imported `ingestion.get_professional_by_phone(from_phone)`, and claims +
silently drops (`return True`) an unrecognized sender. `get_professional_by_agent_phone`
and the redundant `from_phone == assistant_phone` check are gone; replies now
send `from_phone=platform_agent_number()`. `test_agent_channel.py` reworked to
the sender-keyed model (19 cases), plus a dispatch-level claim test. Phase B's
`_is_platform_owned_number` collapsed back to `is_platform_number`.

The routing inversion itself.

- Rewrite the head of `agent_channel.try_handle`:
  - return `False` for `direction != "inbound"` (unchanged);
  - return `False` unless `to_phone` is the platform agent number;
  - resolve the tenant with `ingestion.get_professional_by_phone(from_phone)`;
  - on no match, log and `return True` — claimed and silently dropped, never
    handed to the observer.
- Delete `get_professional_by_agent_phone` and the now-redundant
  `from_phone == assistant_phone` authorization check; sender identity *is*
  the resolution key.
- Replace `from_phone=normalized.to_phone` in the reply path with the platform
  number accessor.
- Watch the import direction: `ingestion` already imports `agent_channel`. Move
  the shared resolver to a neutral module, or have `agent_channel` import it
  lazily inside the function, to avoid a cycle.

**Verify:** tests for (a) a known instructor routed to their own tenant, (b) an
unknown sender silently dropped with no observer side effects, (c) two tenants
messaging the same number never see each other's data, (d) a suspended tenant
locked out.

### Phase E — Retire `Professional.agent_phone`

**Status: done 2026-09-06.** Migration `a1f4c7e9b2d6` drops
`uq_professionals_agent_phone` and the column (downgrade re-adds both; values
noted as unrecoverable). Model field removed. Readers updated:
`passive_escalation` (eligibility + delivery gates now check
`platform_agent_number()` and `assistant_phone`; `from_phone` is the platform
number), `scheduled_tasks` (readiness issue reworded; `from_phone` is the
platform number), `admin.py` (`sender_phone_masked` reads the platform number;
readiness filters are global on `platform_agent_number()` via
`false()`/`true()`), `scripts/seed.py` (drops `AGENT_WHATSAPP_NUMBER`). The
contamination audit tolerates the column being absent. Migration up/down/up
clean on local `agenda_db`; full backend suite green (389).

Remove the column and every reader, now that nothing resolves by it.

- Alembic migration: drop `uq_professionals_agent_phone`, drop `agent_phone`.
  Downgrade re-adds both (values are not recoverable — note this in the
  docstring, as the existing migrations do).
- Update readers:
  - `passive_escalation.py:35,117` — drop the `not professional.agent_phone`
    guards; `:148,155` — `from_phone` becomes the platform number.
  - `scheduled_tasks.py:37` — remove the "Agent WhatsApp number is not
    configured" readiness issue; `:268` — `from_phone` becomes the platform
    number.
  - `admin.py:102,460` — `sender_phone_masked` reads the platform number;
    `:330-338` — readiness filters drop the `agent_phone` predicates.
  - `scripts/seed.py:79,87` — drop `AGENT_WHATSAPP_NUMBER`.
- Simplify `is_platform_number()` to the config value only (removes the Phase B
  transitional branch).

**Verify:** migration up and down cleanly on local `agenda_db`; full backend
suite green; readiness endpoint returns sensible issues for a tenant with no
`assistant_phone`.

### Phase F — Instructor binding handshake

**Status: done 2026-09-06 (challenge-code flow — open question 1 resolved by
the user).** Migration `b2e5d8f1a4c7` adds `agent_binding_confirmed_at` /
`agent_binding_confirmed_by` to `professionals`, a dedicated
`agent_binding_challenges` table (digest-only, per-tenant, TTL
`AGENT_BINDING_CODE_TTL_MINUTES`=15, rotated on each issue — not globally
unique because a confirm always knows the tenant), and the
`agent.binding.confirmed` / `agent.binding.revoked` event types.
`app/services/agent_binding.py` holds `issue_challenge`, `confirm_from_message`
(`ATIVAR-NNNNNN`), `revoke`, `binding_state`. `agent_channel.try_handle` gates
all normal handling on a confirmed binding; an unbound tenant's only accepted
message is the code (else claimed + silently dropped), and a bound turn logs
its resolved `professional_id`. Endpoints on `whatsapp_connection.py`: `GET`
`/api/whatsapp/agent-binding`, `POST` `/agent-binding/challenge` (503
`AGENT_BINDING_UNAVAILABLE` when the platform number is unset), `DELETE`
`/agent-binding`. Frontend `/configuracoes/whatsapp` shows the code, the
platform number, a "Já enviei" recheck, and an optimistic revoke. Coverage:
`test_agent_binding.py` (6), `test_agent_channel.py` gate tests (2),
`test_whatsapp_connection.py` endpoint tests (3). Full backend suite green
(401).

**Deviation from plan:** the per-turn audit is an INFO log line carrying the
resolved `professional_id`, not an `operational_events` row — the ledger has a
DB-enforced event-type whitelist and is a curated record, not a per-message
firehose; consequential actions already emit `agent.action.*` events with
`source_channel="whatsapp"`, and every turn's content is already in
`AgentChannelMessage`.

Restore the second authentication factor.

- Migration: add `agent_binding_confirmed_at` (nullable timestamptz) and
  `agent_binding_confirmed_by` (nullable FK → `users.id`, `ON DELETE SET NULL`)
  to `professionals`, matching the existing `status_changed_*` pattern.
- Binding challenge storage: a short-lived, single-use code scoped to
  `professional_id` with a TTL (default 15 minutes, env-overridable). Reuse the
  existing auth-token table if its shape fits; otherwise a small dedicated
  table — decide when implementing, do not build an abstraction for one use.
- Backend:
  - `POST /api/whatsapp/agent-binding/challenge` — authenticated, tenant
    scoped; issues (or returns the live) code plus the platform number.
  - `DELETE /api/whatsapp/agent-binding` — revokes; clears the columns.
  - In `agent_channel`, before normal handling: if the message text matches a
    pending code, resolve the code → tenant, require
    `from_phone == professional.assistant_phone`, stamp the columns, record an
    `agent.binding.confirmed` event, reply with confirmation, consume the code.
  - Gate normal agent handling on `agent_binding_confirmed_at is not None`.
- Frontend: extend `/configuracoes/whatsapp` with the code, the platform
  number, and a revoke control. Follow project rule 12 — show the bound state
  optimistically on revoke, reconcile on response.
- Audit: record an event per agent-channel turn carrying the resolved
  `professional_id`, so sender-keyed resolution is reconstructable after the
  fact.

**Verify:** tests for bind happy path; code from a non-matching `from_phone`
rejected; expired and reused codes rejected; unbound tenant silently dropped;
revocation immediately closes the channel.

### Phase G — Admin tenant WhatsApp management

**Status: done 2026-09-06 (e2e spec deferred).** `PUT`
`/api/admin/tenants/{professional_id}/whatsapp-number` (platform-admin only):
canonicalizes via `normalize_mobile_phone`, `409`
`WHATSAPP_NUMBER_ALREADY_IN_USE` when another tenant holds the number, `422`
`INVALID_PHONE` on bad input, clears `agent_binding_confirmed_at/by`, audits
via `auth_security_events` (`tenant_whatsapp_number_updated` —
`operational_events` has no field-update type). `TenantSummary` gains
`agent_binding_confirmed_at`. Frontend `/admin/select-tenant`: tile shows
"assistente ativo/inativo"; the settings dialog's Assistente IA tab has a
`WhatsappField` editor that saves and reconciles from the server's canonical
response. Backend endpoint tests (4) in `test_admin_tenants.py`; frontend
typecheck + lint clean. **Deferred:** a Playwright e2e spec — no admin-tenant
spec exists to extend and the unit/integration layer covers the contract.

Close the onboarding gap: today no UI or API sets a tenant's number after
creation.

- `PUT /api/admin/tenants/{professional_id}/whatsapp-number` — behind
  `require_platform_admin`, canonicalizes via `normalize_mobile_phone`,
  rejects a number already held by another tenant with a `409` mapped through
  `error_codes.py`, records an audit event, and clears
  `agent_binding_confirmed_at` (a new number must re-bind).
- Extend the tenant read contract with `whatsapp_number` and
  `agent_binding_confirmed_at`.
- Frontend `/admin/select-tenant`: show the number and binding state on the
  tenant tile; an edit dialog reusing `WhatsappField`, optimistic per rule 12.

**Verify:** endpoint tests for authorization, canonicalization, duplicate
rejection, and binding reset; an e2e spec covering edit and the displayed
binding state.

### Phase H — Proactive sends and the 24-hour window

**Status: done 2026-09-06. Decision: accept the 24h limitation — no escalation
template.** (Open question 2 resolved by the user 2026-09-06.) Passive
escalations keep using free-form `send_text`. They reach an instructor who has
messaged the platform number within the last 24h; outside that window the
provider returns a `WhatsAppPermanentError`, and `deliver()` now catches it
explicitly: the escalation goes terminal (`status = "expired"`,
`last_error = "permanent: ..."`) instead of retrying every poll indefinitely.
Retryable/unknown failures still retry from durable state as before. Covered by
`test_permanent_send_failure_expires_escalation_without_retrying`.

No new template, no Meta approval cycle, no `_template_name` change. The
daily-agenda template is unaffected — it already uses `send_template` and only
its `from_phone` changed (Phase E). Revisit a dedicated escalation template if
Mode 2 reach proves too weak in practice.

### Phase I — Tests, docs, release check

**Status: done 2026-09-06 (cutover runbook is the operator's).** Updated:
`docs/ai_agent_modes.md` (Mode 1 — shared number, sender-keyed resolution,
binding second factor), `docs/agent_navigability.md` (routing boundary, entry
points, runtime map row), `docs/business_rules.md` §8.1,
`docs/scheduled_tasks_architecture.md` (sender number),
`docs/architecture_overview.md` (ingestion comment), `docs/pages/whatsapp.md`
(binding UI section). `README.md` already lists this roadmap and the flow map.
`requirements.txt` unchanged — no new dependency (`secrets`/`hashlib`/`re` are
stdlib; `phonenumbers` already pinned). The cutover runbook below is an
operator checklist, not a code change.

- Update `docs/ai_agent_modes.md` — the Mode 1 section currently documents the
  per-tenant `agent_phone` and the `from_phone == assistant_phone`
  authorization rule; both change.
- Update `docs/architecture_overview.md`, `docs/agent_navigability.md`,
  `docs/business_rules.md` (WhatsApp pipeline rules), and
  `docs/scheduled_tasks_architecture.md` (sender number, readiness).
- Update `docs/pages/whatsapp.md` for the binding UI.
- Add this roadmap to the roadmap list in `README.md` (project rule 3).
- Refresh `requirements.txt` if anything moved (project rule 5) — no new
  dependency is expected.
- Cutover runbook: register the platform number in YCloud → set the env var in
  Azure App Service settings → deploy → bind the pilot tenant → send one
  command end to end → confirm no observer contamination.

### Phase J — Document the YCloud → platform mechanism

**Status: done 2026-09-06.** `docs/whatsapp_ycloud_platform_flow.md` rewritten
to post-migration truth: §1 (one shared number, tenancy = sender lookup), §2
(one tenant column + one env number; `agent_phone` dropped in `a1f4c7e9b2d6`;
binding column added), §4 (sender-keyed `try_handle` + binding gate + the
dispatch guard), §5 (`from_phone = platform_agent_number()` in all three
rows), §6 (`PLATFORM_AGENT_WHATSAPP_NUMBER`, `AGENT_BINDING_CODE_TTL_MINUTES`;
`AGENT_WHATSAPP_NUMBER` removed), §7 (gaps 1/2/4 closed with the phase that did
it; 3/5/6 kept; a new residual-auth note). Added a binding-handshake sequence
diagram; corrected drifted `ingestion.py` line anchors.

The dedicated map of this flow now exists as
[`docs/whatsapp_ycloud_platform_flow.md`](../whatsapp_ycloud_platform_flow.md),
written against the **pre-migration** code. It is the answer to "where is the
agent defined from YCloud" (§1: it is not — identity is a DB lookup at
[agent_channel.py:315](../../backend/app/chat/agent_channel.py#L315)).

This phase brings it to the post-migration truth. It runs **last**, after
behaviour has settled, so the document describes what shipped rather than what
was planned.

- §1 — restate the YCloud/platform split now that one shared agent number
  serves all tenants.
- §2 — replace the two-number table with one tenant number plus one platform
  number; drop the `uq_professionals_agent_phone` reference and add the binding
  columns.
- §4 — rewrite the fork for sender-keyed resolution, including the
  `to_phone == PLATFORM_AGENT_WHATSAPP_NUMBER` guard and the unknown-sender
  drop.
- §5 — correct the outbound `from_phone` column in all three rows; add the
  escalation template key.
- §6 — add `PLATFORM_AGENT_WHATSAPP_NUMBER` and the binding TTL; remove
  `AGENT_WHATSAPP_NUMBER`.
- §7 — close gaps 1, 2, and 4 with the phase that fixed each; keep gaps 3, 5,
  and 6 open with their current status.
- Add the binding handshake as a new sequence diagram, and update the Mermaid
  inbound diagram if the dispatch order changed.

**Verify:** every file:line reference in the document resolves against the
post-migration tree; the diagrams match the shipped dispatch order; a reader
who has never seen the code can answer "which number is the agent, and how does
a message find its tenant" from this document alone.

## 6. Touch-point matrix

| File | Change | Phase |
| --- | --- | --- |
| `.env`, `.env.example` | `PLATFORM_AGENT_WHATSAPP_NUMBER`, escalation template name | A, H |
| `backend/app/integrations/whatsapp/` (new accessor) | `platform_agent_number()`, `is_platform_number()` | A, E |
| `backend/app/chat/ingestion.py` | Exclusion guard in `dispatch_whatsapp_event` | B |
| `scripts/audit_agent_channel_contamination.py` | New: detect, optionally clean | C |
| `backend/app/chat/agent_channel.py` | Sender-keyed routing; delete `get_professional_by_agent_phone`; binding branch; reply `from_phone` | D, F |
| `backend/migrations/versions/` | Drop `agent_phone` + constraint; add binding columns | E, F |
| `backend/app/models/professional.py` | Drop `agent_phone`; add binding columns | E, F |
| `backend/app/services/passive_escalation.py` | Guards, `from_phone`, template send | E, H |
| `backend/app/services/scheduled_tasks.py` | Readiness, `from_phone` | E |
| `backend/app/api/admin.py` | Masked sender, readiness filters, number endpoint | E, G |
| `backend/app/api/whatsapp_connection.py` | Binding challenge / revoke endpoints | F |
| `backend/app/core/error_codes.py` | Duplicate-number and binding errors | F, G |
| `backend/app/integrations/whatsapp/ycloud.py` | New template key in `_template_name` | H |
| `scripts/seed.py` | Drop `AGENT_WHATSAPP_NUMBER` | E |
| `frontend/src/app/(protected)/configuracoes/whatsapp/page.tsx` | Binding UI | F |
| `frontend/src/app/admin/select-tenant/page.tsx` | Number + binding state, edit dialog | G |
| `frontend/src/lib/{api,types}.ts` | New contracts | F, G |
| `docs/` + `README.md` | Documentation | I |
| `docs/whatsapp_ycloud_platform_flow.md` | Bring the flow map to post-migration truth | J |

## 7. Sequencing and smallest shippable slice

**All five slices implemented locally 2026-09-06** in order (A–C, D–E, F–G, H,
I–J). Open operator items: Phase C production preflight, Phase G e2e spec, the
cutover runbook.

**Slice 1 — data integrity (A + B + C).** Independent of the migration, fixes a
live defect, and can ship immediately. Recommended starting point.

**Slice 2 — the inversion (D + E).** Ship together: Phase D stops reading
`agent_phone`, Phase E removes it. Splitting them across deploys leaves a
column nothing reads.

**Slice 3 — security and onboarding (F + G).** F must land before the shared
number is given to more than the pilot tenant — until then the channel runs on
one factor. G unblocks onboarding tenant number two.

**Slice 4 — proactive sends (H).** Independent; sequence by whether escalation
volume matters before the next tenants arrive.

**Slice 5 — documentation (I + J).** J runs last of all: the flow map should
describe what shipped, not what was planned.

Hard ordering constraints: B before C (cleanup is pointless while
recontamination is possible); D before E; F before onboarding a second tenant.

## 8. Risks and resolved trade-offs

| Risk | Assessment | Handling |
| --- | --- | --- |
| Sender spoofing on a public number | `from_phone` is attested by Meta/YCloud — the same trust anchor WhatsApp itself relies on. Not spoofable by an ordinary third party. | Accepted, with Phase F's binding as the second factor and per-turn audit events. |
| SIM swap or carrier number recycling | Brazilian carriers recycle numbers; a recycled number would resolve to the old tenant. | Binding is revocable; admin number edit (G) clears it; tenant suspend/archive already locks out via the `status` filter. |
| Observer/agent cross-contamination | Confirmed live defect, both directions. | Phase B guard plus Phase C cleanup, verified by tests that assert zero Contact creation. |
| Unknown sender falling through to the observer | Would create a Contact for a stranger under an arbitrary tenant. | Phase D claims the message (`return True`) even when no tenant resolves. |
| Escalations rejected outside the 24-hour window | Real today for free-form `send_text`; the shared number does not cause it but makes it more visible. | Phase H template. Errors surface in `last_error` rather than silent expiry. |
| Non-durable outbound sends | Flagged medium in `docs/whatsapp_provider_portability_assessment.md`; a shared number widens the blast radius of a provider outage from one tenant to all. | Out of scope here. Escalations and scheduled tasks already retry from durable state; interactive replies do not. Raise as its own outbox initiative if reply loss is observed. |
| Import cycle (`ingestion` ↔ `agent_channel`) | `ingestion` already imports `agent_channel`; Phase D adds the reverse need. | Neutral module for the shared resolver, or a lazy in-function import. Decide at implementation. |
| Migration is irreversible in practice | Dropping `agent_phone` loses the values. | Only the pilot tenant has one, and it is re-derivable from YCloud. Note it in the migration docstring. |
| Billing scales with tenant count | Every agent reply becomes a billed API send. | Recorded in §4.7; no action, but pricing should account for it. |

## 9. Open questions

1. **Binding handshake depth.** *Resolved 2026-09-06: challenge-code flow
   (§4.4).* The button-only variant was rejected — it cannot detect a recycled
   or SIM-swapped number.
2. **Escalation template.** *Resolved 2026-09-06: accept the 24-hour
   limitation.* No template, no Meta cycle; a permanent out-of-window send now
   expires the escalation cleanly with the provider error recorded (Phase H).
3. **Challenge-code storage.** Whether the existing auth-token table fits or a
   small dedicated table is cleaner. Resolve by reading that table's shape at
   the start of Phase F rather than deciding now.
4. **Contamination blast radius.** Unknown until the Phase C audit runs. If
   polluted conversations already produced `AppointmentCandidate` rows that
   were acted on, cleanup needs a review pass, not just a delete.
