# WhatsApp Provider Portability Assessment

**Status:** Code-first assessment  
**Assessed:** 2026-08-27  
**Scope:** Current WhatsApp Business provider integration and the smallest safe path to make provider replacement routine.

## 1. Executive assessment

The application already has a sound provider boundary. `app.integrations.whatsapp` isolates the current YCloud implementation behind a small `WhatsAppProvider` protocol, and both inbound webhooks and the durable daily-agenda sender use its canonical contracts. Message identifiers are namespaced by `provider_key`, so historical messages from a future provider will not collide with YCloud identifiers.

This makes a **deployment-wide provider replacement** practical: implement a new adapter, register it, add provider-specific environment variables, configure its webhook, and run the contract and integration tests. The scheduling, extraction, agent, tenant-routing, and persistence domains should not need provider JSON or HTTP changes.

The boundary is not yet sufficient for **per-tenant provider selection** or for an unrestricted provider feature set. Those are separate product decisions and should not be introduced merely to replace YCloud for the whole deployment.

The current implementation is therefore **partially modularized and on the right architectural path**. The recommended next step is a contained hardening pass, not a wholesale redesign.

## 2. Verified current boundary

| Concern | Current boundary | Assessment |
|---|---|---|
| Provider contract | `backend/app/integrations/whatsapp/provider.py` | Good. It exposes verification, canonical parsing, text delivery, template delivery, and typed results/errors. |
| Canonical data | `backend/app/integrations/whatsapp/contracts.py` | Good for the implemented text, echo, and delivery-status flows. |
| YCloud mapping | `backend/app/integrations/whatsapp/ycloud.py` | Good. HMAC, payload parsing, HTTP, headers, error translation, and template-name mapping are contained here. |
| Provider resolution | `backend/app/integrations/whatsapp/registry.py` | Adequate for one provider across the deployment; only `ycloud` is registered today. |
| Webhook dispatch | `backend/app/api/whatsapp.py`, `backend/app/chat/ingestion.py` | Good. Provider payloads are normalized before business routing. A generic path and a YCloud compatibility alias exist. |
| Inbound persistence | `backend/app/models/message.py` | Good. `(provider_key, provider_message_id)` is the deduplication boundary. |
| Scheduled delivery | `backend/app/services/scheduled_tasks.py` | Good. It receives the protocol, records provider results, and reconciles canonical delivery updates. |
| Active and passive agent messages | `backend/app/chat/agent_channel.py`, `backend/app/services/passive_escalation.py` | Mostly good. They call the provider contract, but retain legacy helper seams for tests and direct callers. |

The provider-neutral portion is actively used, not merely planned. The existing `docs/scheduled_tasks_architecture.md` remains the closest implementation document; this assessment adds the portability decision, remaining gaps, and migration sequence.

## 3. What can be switched now

### Deployment-wide replacement

This is the recommended near-term interpretation of “switch provider.” One selected provider serves all tenants. Add an adapter that implements the existing protocol, register its key, provide its secrets through `.env`, then configure its callback as `/webhooks/whatsapp/<provider-key>`. Existing domain services continue to receive canonical messages and send requests.

The required implementation surface is deliberately small:

1. `integrations/whatsapp/<provider>.py` implements signature verification, webhook parsing, `send_text`, and `send_template`.
2. `registry.py` registers the key selected by `WHATSAPP_PROVIDER`.
3. Provider-specific configuration stays inside that adapter or a provider-scoped settings module.
4. Contract tests prove the adapter emits canonical events and error classes; integration tests prove webhook-to-persistence and send-to-delivery-state behavior.

No data migration is required for a clean global cutover because existing rows retain `provider_key="ycloud"`. Historical webhooks remain attributable, and the composite uniqueness constraint prevents identifier collisions between providers.

### Per-tenant provider choice

This is **not implemented** and should be deferred unless the commercial requirement is explicit. It needs a tenant-owned provider connection model, encrypted credentials/references, routing of a webhook to a provider *then* to a tenant, outbound provider resolution by tenant, and a strategy for changing a tenant without losing outstanding delivery reconciliation. It also turns provider onboarding and credential rotation into product features.

The current global `WHATSAPP_PROVIDER` setting is the correct simpler choice for the present deployment.

## 4. Gaps before calling the boundary fully portable

| Priority | Gap | Evidence | Recommended change |
|---|---|---|---|
| High | Provider-specific options leak into application service code. | `scheduled_tasks.py` reads `YCLOUD_DAILY_AGENDA_TEMPLATE_LANGUAGE` and `YCLOUD_DAILY_AGENDA_TTL_SECONDS`. | Move the language/TTL defaults into the YCloud adapter. The domain service should request the logical `daily_agenda` template only. |
| High | Legacy YCloud compatibility module remains importable. | `app/chat/ycloud_provider.py` exposes YCloud-named helpers and is still imported by several tests. | Migrate those tests and any callers to canonical contracts, then remove the module. This prevents new direct provider dependencies. |
| High | Webhook signatures have no replay-age validation. | YCloud verification checks the HMAC but accepts any valid timestamp. | Validate the signed timestamp against a small configurable tolerance and reject stale callbacks. Keep this policy inside each adapter. |
| Medium | The protocol covers only the currently used capabilities. | Canonical events and requests support text, templates, echoes, and delivery status, but not media, reactions, replies, interactive callbacks, or provider webhook challenge flows. | Do not generalize prematurely. Extend the contract only when a concrete product capability needs one of these features, with a canonical test case first. |
| Medium | Active-agent and passive-escalation sends are not durable outbox deliveries. | They catch provider errors after direct `send_text`; delivery reconciliation is durable only for scheduled task runs. | When reliable proactive messages become a product requirement, introduce one provider-neutral outbound-message/outbox record shared by all senders. Do not add it solely for a provider swap. |
| Medium | Only the YCloud adapter has direct tests. | `test_whatsapp_provider.py` verifies YCloud parsing/signature behavior; scheduled-task tests use a minimal fake. | Add provider contract tests that every adapter must satisfy, then reuse the same suite for a second adapter. |
| Low | Defaults still mention YCloud in generic models. | `WhatsAppMessageEvent` and `Message.provider_key` default to `ycloud`. | Remove those defaults once all callers always supply an adapter key; this makes accidental provider attribution impossible. |

## 5. Recommended implementation sequence

1. **Harden the existing seam.** Remove YCloud-named compatibility imports, move the two YCloud settings behind the adapter, make `provider_key` explicit, and add timestamp replay protection. Verify with the existing adapter unit tests plus new boundary tests.
2. **Create a reusable adapter contract suite.** Cover valid/invalid signatures, inbound text, outbound echo, delivery status, malformed payload rejection, retryable/permanent/unknown send failures, and the logical `daily_agenda` template. Verify it against YCloud before adding another provider.
3. **Add one second provider adapter only when selected.** Keep the current global selector. Prove both adapters pass the same suite and execute the same ingestion and scheduled-send integration cases.
4. **Use a controlled cutover.** Preserve `ycloud` on old records, switch `WHATSAPP_PROVIDER` only after the new callback and a test number pass verification, then monitor messages and scheduled-task delivery updates. Do not accept two providers in the normal path unless a migration window genuinely requires it.
5. **Revisit per-tenant connections later.** Make this a separate, approved multi-tenancy initiative—not an incremental registry edit.

## 6. Verification performed

- Read the current `.env` keys without exposing their values. It contains the deployment-wide selector and YCloud-specific credentials/template configuration.
- `conda run -n agenda pytest backend/tests/test_whatsapp_provider.py -q` passed: **2 passed**.
- `conda run -n agenda pytest backend/tests/test_scheduled_tasks.py backend/tests/test_ingestion.py backend/tests/test_agent_channel.py backend/tests/test_passive_escalation.py -q` passed: **28 passed**. These database-backed tests cover tenant routing, scheduled sends and delivery updates, active-agent handling, and passive escalation.
- `conda run -n agenda python -m compileall -q backend/app` passed.
- `git diff --check` passed.
- An initial sandboxed attempt could not reach the local `agenda_db`; rerunning with host-level access confirmed the platform server and local database are healthy. No remote database was contacted or modified.

## 7. Decision

Treat the provider boundary as **ready for a disciplined global provider replacement after the hardening pass**, not as a fully generic multi-provider platform. The narrow, capability-based protocol is the right design. Keeping it small is what will make the next provider adapter genuinely cheap to build and safe to test.
