# Page: Minhas Regras (Operational Rules)

**Route:** `/minhas-regras`
**File:** `frontend/src/app/(protected)/minhas-regras/page.tsx`
**Feature-gated:** No — reachable by every tenant regardless of the
`commercial_financials` feature flag.

---

## Overview

Minhas Regras holds operational settings that scheduling and make-up
credit logic enforce for every tenant, independent of whether the
Financeiro module is enabled:

- `assert_within_work_journey` (`app/services/appointments.py`) reads the
  work journey directly and fails open (unrestricted) only if no rows
  exist.
- `grant_credit_if_eligible` (`app/services/makeup_credits.py`) reads
  `cancellation_notice_hours` directly, defaulting to 24h if unset.

Both settings previously lived only inside Financeiro's Configuração tab,
which meant a tenant without `commercial_financials` could never see or
change values that were still being enforced against them. This page
fixes that by exposing them ungated, via `require_professional_id` alone.

`PrimeTimeWindow` stays in Financeiro — it's a pricing/billing
categorization construct, not a scheduling/eligibility gate.

---

## Key Components

| Component | File | Purpose |
|---|---|---|
| `WorkJourneySection` | `components/rules/work-journey-section.tsx` | Define work and break intervals per weekday |
| `CancellationNoticeSection` | `components/rules/cancellation-notice-section.tsx` | Set the make-up credit cancellation notice window |

---

## Sections

### Jornada de Trabalho (Work Journey)

- For each day of week (0-6), define work and break intervals
- Work intervals: when the instructor is available for classes
- Break intervals: mid-day gaps where no classes are scheduled; must be
  fully contained within a work interval for that day. A day may have multiple
  pauses, provided they do not overlap.
- Endpoints: `GET /api/rules/work-journey`, `PUT /api/rules/work-journey`

### Aviso Prévio para Reposição (Cancellation Notice)

- Single numeric input: hours of notice required for a cancellation to
  earn a make-up credit (0-168, default 24)
- Endpoints: `GET /api/rules/cancellation-notice-hours`,
  `PATCH /api/rules/cancellation-notice-hours`

---

## Data Sources

| Data | Endpoint |
|---|---|
| Work journey | `GET /api/rules/work-journey` |
| Cancellation notice hours | `GET /api/rules/cancellation-notice-hours` |

---

## Visual Design

The page uses a compact tab control to separate **Jornada de trabalho** from
**Reposições**. Each tab retains its own save button. Work-journey days allow
adding and removing pause rows; client-side validation prevents a pause outside
the daily journey or overlapping pauses before the backend repeats the same
enforcement.
