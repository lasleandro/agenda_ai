# WhatsApp

## Initial release

The protected `/configuracoes/whatsapp` page introduces the planned WhatsApp
Business connection to authenticated users. It is intentionally informational:
there is no provider configuration, onboarding flow, API request, or persisted
connection state in this release.

## Navigation and experience

- **Navigation label:** WhatsApp
- **Route:** `/configuracoes/whatsapp`
- **Implementation:** `frontend/src/app/(protected)/configuracoes/whatsapp/page.tsx`
- **Sidebar:** the existing shared `SidebarContent`, which also renders in the
  mobile drawer.

The item appears immediately above **Configurações** and reuses the landing
page asset at `frontend/public/landing/whatsapp.png`. The page shows an
**Em breve** status, the expected connection steps, and an explicit notice that
there is nothing to configure yet.

## Agent-channel binding

The page also carries the opt-in for the **shared platform AI agent number**
(Shared Platform AI Agent Number Roadmap v0.1, Phase F). When
`PLATFORM_AGENT_WHATSAPP_NUMBER` is configured, an "Assistente por WhatsApp"
card lets the instructor:

- **Ativar assistente** — `POST /api/whatsapp/agent-binding/challenge` issues a
  one-time `ATIVAR-NNNNNN` code. The instructor sends it to the platform number
  from their own WhatsApp; the backend confirms it came from the tenant's
  `assistant_phone`, stamps `Professional.agent_binding_confirmed_at`, and
  records an `agent.binding.confirmed` audit event. A "Já enviei" button
  rechecks `GET /api/whatsapp/agent-binding`.
- **Desativar** — `DELETE /api/whatsapp/agent-binding` clears the binding
  optimistically and drops any pending code.

Until the binding is confirmed, the agent channel drops every message from the
tenant except the code. A platform-admin number change (Phase G) also clears
the binding, so the instructor must re-activate.

## Activation boundary

This page must remain truthful while the provider partnership is unavailable.
The future YCloud/provider-neutral onboarding work remains governed by the
[tenant WhatsApp connection roadmap](../ROADMAPS/ycloud_tenant_whatsapp_connection_roadmap_v0.1_2026-09-02.md).
Activating a connection button requires that roadmap's partnership, security,
backend contract, tenant-isolation, and rollout gates to be completed first.
