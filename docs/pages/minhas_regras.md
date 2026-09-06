# Page: Configurações (Tenant Definitions)

**Route:** `/minhas-regras`
**File:** `frontend/src/app/(protected)/minhas-regras/page.tsx`
**Feature-gated:** No — reachable by every tenant regardless of the
`commercial_financials` feature flag.

---

## Overview

The `/minhas-regras` route is presented as **Configurações** in the product.
It is the tenant-facing home for operational definitions and, when enabled,
financial definitions. The route name remains unchanged for bookmark
compatibility.

Operational settings are available to every tenant independently of whether
the Financeiro module is enabled:

- Work journey guides scheduling recommendations and financial capacity. It
  does not reject a conflict-free confirmed booking; the assistant displays an
  advisory for an exception.
- `grant_credit_if_eligible` (`app/services/makeup_credits.py`) reads
  `cancellation_notice_hours` directly, defaulting to 24h if unset.

Both settings previously lived only inside Financeiro's Configuração tab,
which meant a tenant without `commercial_financials` could never see or
change values that were still being enforced against them. This page
fixes that by exposing them ungated, via `require_professional_id` alone.
Finance-enabled tenants additionally see the existing financial configuration
forms without changing their API or audit behavior.

---

## Key Components

| Component | File | Purpose |
|---|---|---|
| `WorkJourneySection` | `components/rules/work-journey-section.tsx` | Define work and break intervals per weekday |
| `CancellationNoticeSection` | `components/rules/cancellation-notice-section.tsx` | Set the make-up credit cancellation notice window |
| `GlobalRatesSection` | `components/financial/global-rates-section.tsx` | Set default commercial status and participant rates |
| `PrimeTimeSection` | `components/financial/prime-time-section.tsx` | Set premium-time windows |
| `PlaceRatesSection` | `components/financial/place-rates-section.tsx` | Set generic and place-specific rate matrices |

---

## Sections

### Jornada de Trabalho (Work Journey)

- For each day of week (0-6), define work and break intervals
- Work intervals: usual hours used in recommendations and capacity estimates.
- Break intervals: usual mid-day gaps; they must be fully contained within a
  work interval for that day. A day may have multiple pauses, provided they do
  not overlap. An exception can still be confirmed after the assistant warns
  the instructor.
- Endpoints: `GET /api/rules/work-journey`, `PUT /api/rules/work-journey`

### Aviso Prévio para Reposição (Cancellation Notice)

- Single numeric input: hours of notice required for a cancellation to
  earn a make-up credit (0-168, default 24)
- Endpoints: `GET /api/rules/cancellation-notice-hours`,
  `PATCH /api/rules/cancellation-notice-hours`

### Finance-enabled definitions

Tenants with `commercial_financials` see three additional tabs:

- **Valores globais** — default commercial status and hourly rates by
  participant count; `GET`/`PATCH /api/financial/settings`.
- **Horários nobres** — weekday/time premium windows;
  `PUT /api/financial/prime-time-windows`.
- **Valores por local** — generic and per-place regular/prime rate matrices;
  `GET /api/financial/configuration` plus the existing rates replacement
  endpoints.

These tabs are not rendered for a tenant without the financial module. Their
existing server-side feature checks remain the authoritative protection.

---

## Data Sources

| Data | Endpoint |
|---|---|
| Work journey | `GET /api/rules/work-journey` |
| Cancellation notice hours | `GET /api/rules/cancellation-notice-hours` |
| Financial settings (feature-gated) | `GET /api/financial/settings` |
| Financial configuration (feature-gated) | `GET /api/financial/configuration` |

---

## Visual Design

The page uses a compact tab control. Every tenant sees **Jornada de trabalho**
and **Reposições**; finance-enabled tenants additionally see the three
financial-definition tabs. Each tab retains its own save button. Work-journey
days allow adding and removing pause rows; client-side validation prevents a
pause outside the daily journey or overlapping pauses before the backend
repeats the same enforcement.

---

## First-session setup

`GET /api/auth/me` returns `operation_configured` for a tenant-scoped session.
It is `true` once the tenant has at least one Local and at least one `work`
interval in the weekly journey, and absent for platform-admin sessions with no
tenant selected. While it is `false`:

- **Minha Operação** is hoisted to the first position in the sidebar and
  carries a **"Comece aqui"** badge.
- Logging in lands on `/minhas-regras` instead of `/agenda`, and an `/agenda`
  landing (bookmark, reload, direct URL) is redirected once to `/minhas-regras`.
- `/agenda` shows a setup prompt instead of the week grid; navigation is never
  blocked.

All three affordances clear automatically once `operation_configured` turns
`true` — there is no persistent "done" state. See
[the roadmap](../ROADMAPS/first_user_onboarding_operation_setup_roadmap_v0.1_2026-09-06.md).
