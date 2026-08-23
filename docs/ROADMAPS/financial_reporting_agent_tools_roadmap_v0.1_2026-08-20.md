# Financial Reporting and Agent Tools Roadmap v0.1 — 2026-08-20

**Status: proposed; awaiting implementation approval.**

## 1. Product decisions

Create a canonical, read-only financial reporting service as the single source
for instructor-facing financial answers. The conversational agent, Financeiro
screen, and future periodic reports consume that service or bounded views of
it; none of them recompute money from raw agenda data.

The following rules are fixed:

1. `get_financial_summary(date_from, date_to)` is the agent's superset tool.
2. Smaller tools provide focused, bounded detail while delegating to the same
   reporting service.
3. Revenue projections, realized class revenue, and event income remain
   separate fields with explicit bases. They are never silently combined.
4. All reads retain authenticated tenant scope and the existing
   `commercial_financials` feature boundary.
5. Periodic reports will call the reporting service directly; an LLM may
   explain the result but is never the source of the figures.

## 2. Goal and success definition

An instructor should be able to ask natural questions such as:

- “Quantas aulas tenho na próxima semana?”
- “Quanto tenho para receber neste mês?”
- “Quanto realizei no mês passado?”
- “Qual local está mais ocupado?”
- “Quem mais cancelou neste período?”

The agent must answer only from deterministic, date-bounded data returned by
tools. The answer must name the relevant period and distinguish a projection
from realized revenue. When a request is ambiguous, it should return the
most useful clearly labeled measure or ask a concise clarifying question;
it must never invent a financial total.

The work succeeds when the same input period produces consistent financial
figures in the reporting service, agent tools, and future scheduled-report
caller, while existing Financeiro behavior and immutable recognized revenue
remain unchanged.

## 3. Scope boundaries

### In scope

- A tenant-scoped canonical financial-report service and typed schemas.
- A read-only API/report contract suitable for internal callers.
- A superset agent tool plus focused financial agent tools.
- Explicit report metadata: period, timezone, as-of timestamp, currency, and
  revenue bases.
- Bounded detail, ranking, trend, and recognized-occurrence responses.
- Agent orchestration instructions for financial vocabulary and ambiguity.
- Tests for calculations, authorization, tenant isolation, date boundaries,
  empty data, and tool dispatch.
- Documentation for the agent contract and periodic-report reuse.

### Out of scope

- Any write, pricing, cancellation, revenue-confirmation, or scenario action
  from financial read tools.
- Changing the Financeiro calculations or the semantics of recognized revenue.
- Invoice, payment, receivable, tax, expense, or bank-account functionality.
- Automated report scheduling or delivery itself; this roadmap only prepares
  its deterministic data foundation.
- Unbounded exports or raw customer PII in agent responses.

## 4. Canonical reporting architecture

Create `app.services.financial_reporting` as a composition layer. It does not
duplicate existing formulas. Instead it calls the current authoritative
services and maps their typed outputs into a stable report contract:

```text
financial_reporting.build_report(db, professional_id, date_from, date_to)
 ├─ financial_analytics.build_financial_dashboard(...)       projection/capacity
 ├─ revenue_occurrences.build_revenue_summary(...)            immutable realized revenue
 └─ financial_operational_analytics.build_...(...)            class/event outcomes and rankings
```

The report service owns only composition, labels, report metadata, limits, and
cross-source consistency. Pricing resolution stays in the financial dashboard;
recognized revenue stays in its immutable occurrence service; operational
outcomes stay in their existing aggregate service.

### 4.1 Report metadata and top-level contract

Every response includes:

```text
report: {
  period: { date_from, date_to },
  timezone: "America/Sao_Paulo",
  as_of: timestamp,
  currency: "BRL",
  bases: {
    projected_class_revenue: "active agenda priced by current rules",
    realized_class_revenue: "immutable confirmed class occurrences",
    event_income: "confirmed instructor events with a stated amount"
  }
}
```

The summary payload then exposes distinct named sections:

- `projection` — scheduled class revenue, occupancy, capacity, free hours,
  participant-hours, and unpriced-booking count.
- `realized` — immutable class revenue, adjustment, occurrence, participant,
  and recognized-event-income values.
- `operations` — class slots/outcomes, event outcomes, and customer rankings.
- `assumptions` — the existing dashboard calculation assumptions.

No top-level `total_revenue` is returned in Phase 1. A future accounting
feature may define a consolidated total explicitly; until then, combining
projected and realized class revenue would double-count work.

### 4.2 Period and limit rules

- Inputs are inclusive ISO calendar dates and retain the existing maximum
  366-day analytics period.
- The service uses the instructor's application timezone for `as_of`, past
  versus upcoming classification, and date boundaries.
- Detail lists use fixed conservative defaults and explicit maximums. Summary
  calls remain bounded even for a full-year period.
- A period in the future may have projected revenue and upcoming classes but
  no realized class revenue; this is a valid, explained result.

## 5. Agent read-tool surface

All financial tools are read-only, execute immediately, and receive the
professional ID from the authenticated agent context. They never accept a
tenant/professional ID from the model.

| Tool | Purpose | Bounded output |
|---|---|---|
| `get_financial_summary` | Superset financial report for one date range | top-level report sections, no occurrence history |
| `get_financial_breakdown` | One selected breakdown: location, weekday, part of day, time category, customer, or group | max 20 rows |
| `get_financial_trend` | Projected or realized daily/monthly evolution | max 366 daily points or 24 monthly points |
| `get_financial_customer_insights` | Attendance-frequency and cancellation-rate rankings | max 5 rows per ranking |
| `get_financial_occurrences` | Immutable realized class-occurrence history | paginated, max 20 rows |
| `get_financial_capacity_summary` | Capacity, occupancy, free hours, unpriced bookings, and potential references | aggregate only |

`get_financial_summary` is sufficient for most questions and is the preferred
first call. Focused tools are for follow-up questions, avoiding a large
payload or an agent-side calculation.

### 5.1 Agent wording rules

Add explicit instructions to the orchestrator:

- For “quanto tenho para receber”, call `get_financial_summary` and describe
  `projection.scheduled_class_revenue_cents` as **receita prevista**, never as
  realized or guaranteed income.
- For “quanto realizei”, use `realized.class_revenue_cents`; explain that it
  comes from immutable confirmed occurrences.
- Event income is a separate `realized.confirmed_event_income_cents` value.
  Do not add it to class values unless the instructor expressly asks for both
  categories; if added, label the arithmetic transparently.
- For “quantas aulas”, prefer the existing `get_schedule` when the user wants
  a list of appointments/classes. Use financial summary operations for a
  dashboard-style count or a period longer than the schedule tool’s 31-day
  range.
- Resolve relative dates through `resolve_date_phrase` before every financial
  tool call. The tool output, not model arithmetic, establishes the answer.
- State the resolved date range and use Brazilian currency formatting in prose.

### 5.2 Data minimization

Summary and aggregate tools return no customer contact details beyond the
existing display-safe name in the five-row rankings. Occurrence history is
limited, paginated, and returns only the fields already appropriate to the
instructor's recognized-revenue history. No phone, email, notes, internal
audit data, pricing-rule internals, or unbounded roster is exposed.

## 6. Periodic-report foundation

The reporting service is intentionally independent of the conversational
agent. A future scheduled task follows this sequence:

```text
scheduled task → financial_reporting.build_report(...) → deterministic payload
               → optional LLM narration → delivery channel
```

The deterministic payload is persisted or audited according to the future
delivery design before any LLM narration. A failed narration must not change
the values, period, or ability to retry delivery. The reporting service must
therefore expose labels and bases sufficient for a template-only report.

Suggested future report periods are last closed month, current month to date,
and next 30 days. Their date selection belongs to the scheduled-task feature,
not to the financial reporting service.

## 7. Implementation phases

### Phase 0 — Contract reconciliation

1. Trace the existing dashboard, revenue-summary, and operational-analytics
   schemas to identify every value and its source-of-truth service.
2. Decide exact field names for projected class revenue, realized class
   revenue, and confirmed event income.
3. Define detail-tool pagination and breakdown dimensions against existing
   endpoint capabilities; defer any unsupported dimension rather than
   recomputing it in the agent layer.

**Verification:** a written field-to-source mapping is included in the PR;
no formula is copied into the report service.

### Phase 1 — Canonical report service and API contract

1. Add report schemas and `financial_reporting.build_report`.
2. Compose existing services under one tenant-scoped validated period.
3. Add a feature-gated read endpoint only if it is needed by non-agent
   consumers now; otherwise keep the service as the first internal contract.
4. Test empty, past, current, and future periods; ensure projections and
   realized values remain distinct.

**Verification:** service/API tests prove tenant isolation, feature rejection,
date bounds, field provenance, and no double-counted revenue.

### Phase 2 — Agent superset tool

1. Add `get_financial_summary` to `agent/tools.py` and its tool specification.
2. Add orchestration wording rules and relative-date handling.
3. Add agent-channel tests for projected, realized, ambiguous, empty, and
   future-period questions.

**Verification:** the tool returns deterministic cents/metadata and the agent
does not calculate totals from raw appointments.

### Phase 3 — Focused tools

1. Add bounded breakdown, trend, customer-insight, occurrence-history, and
   capacity-summary tools, one at a time.
2. Reuse canonical report views where practical; use their authoritative
   underlying service only when a focused request would otherwise overfetch.
3. Add authorization, pagination, dimension validation, and data-minimization
   tests per tool.

**Verification:** every tool has a narrow contract, a fixed upper result
bound, and no write path.

### Phase 4 — Documentation and periodic-report handoff

1. Document agent examples, terminology, and response semantics.
2. Document the canonical report contract as the future scheduled-report input.
3. Link the implementation to Financeiro and scheduled-task documentation.

**Verification:** a template-only monthly report can be assembled from the
canonical payload without querying raw operational tables.

## 8. Risks and acceptance checklist

| Risk | Guardrail |
|---|---|
| Projection and realized revenue are conflated | Separate fields, bases, labels, and agent instructions; no implicit total. |
| Agent exposes unrelated customer data | Tenant-scoped service, display-safe bounded rows, and no raw contact PII. |
| Tool output becomes too large | Fixed limits, pagination, and dimensions validated against a closed vocabulary. |
| Periodic report and UI disagree | Both call the same canonical composition service. |
| Agent invents arithmetic or date ranges | Require `resolve_date_phrase`; tools return resolved periods and cents. |
| Existing Financeiro changes unexpectedly | Compose existing authoritative services without modifying their formulas. |

- [ ] Canonical report carries period, timezone, as-of timestamp, currency, and
      explicit revenue bases.
- [ ] Projected class, realized class, and confirmed event income are separate.
- [ ] Every report/tool read is authenticated, feature-gated, tenant-scoped,
      date-bounded, and read-only.
- [ ] `get_financial_summary` answers the primary instructor questions without
      model-side financial calculation.
- [ ] Focused tools are bounded and return no unnecessary PII.
- [ ] Agent tests cover Portuguese relative dates and ambiguous “receber”
      wording.
- [ ] Existing financial, revenue, operational, and agent regression suites
      pass.
- [ ] The payload can support a future template-only periodic report.
