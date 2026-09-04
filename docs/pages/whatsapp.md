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

## Activation boundary

This page must remain truthful while the provider partnership is unavailable.
The future YCloud/provider-neutral onboarding work remains governed by the
[tenant WhatsApp connection roadmap](../ROADMAPS/ycloud_tenant_whatsapp_connection_roadmap_v0.1_2026-09-02.md).
Activating a connection button requires that roadmap's partnership, security,
backend contract, tenant-isolation, and rollout gates to be completed first.
