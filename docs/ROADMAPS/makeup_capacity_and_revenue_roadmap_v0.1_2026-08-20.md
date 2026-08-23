# Makeup Capacity and Revenue Roadmap v0.1 — 2026-08-20

**Status: implemented locally on 2026-08-20; pending visual acceptance.**

## Implementation record

Redeemed credits now create courtesy appointments and are identified from the
persisted `redeemed_appointment_id` relationship during financial projection.
They remain booked capacity and participant time, but are excluded from new
projected revenue and unpriced-booking warnings. Financeiro now shows the
selected-period redeemed count, occupied hours, and current-price opportunity
cost.

Focused financial regression passes (7 tests), frontend type-check passes,
and diff validation passes. Existing makeup-credit tests with fixed past dates
remain separately failing because their notice-window fixtures no longer
generate credits as time advances.

## 1. Product decision

A redeemed makeup credit represents delivery already owed from a prior class.
Its appointment occupies the instructor's calendar and capacity, but it must
not create a second projected or recognized class revenue amount.

The Financeiro overview will expose the operational cost of this commitment as
a separate **Reposições** section:

- reposições agendadas;
- horas comprometidas;
- receita potencial comprometida, valued at current pricing rules.

“Receita potencial comprometida” is an opportunity-cost reference, not money
lost or guaranteed revenue: the occupied slot might otherwise remain empty.

## 2. Target semantics

| Concern | Redeemed makeup appointment behavior |
|---|---|
| Calendar and availability | Occupies the slot exactly like a normal appointment. |
| Capacity and occupancy | Counts as booked time and participant-hours. |
| Projected class revenue | Excluded; the original cancelled class already established the commercial obligation. |
| Recognized revenue | Non-billable by default; it must not be recognized as a second payment. |
| Makeup operational counts | Included as a separate aggregate, not as a cancellation count. |
| Opportunity-cost metric | Current-rule price equivalent of its occupied time, clearly labeled as potential. |

The existing `MakeupClassCredit.redeemed_appointment_id` relationship is the
authoritative marker. Do not infer makeup status from the appointment service
label, source, or free-text content.

## 3. Implementation phases

### Phase 1 — Correct financial semantics

1. Create redeemed makeup appointments with `billing_type="courtesy"`.
2. Extend the financial booking projection input with authoritative makeup
   identity derived from redeemed credits.
3. Keep makeup appointments in booked minutes and participant-hours while
   excluding their price contribution from projected revenue and unpriced
   booking warnings.
4. Confirm the existing revenue-confirmation flow retains the courtesy
   non-billable default.

**Verification:** a normal appointment and a redeemed makeup occupying the
same priced duration contribute equal capacity but only the normal appointment
contributes projected/recognized revenue.

### Phase 2 — Operational aggregate and UI

1. Add selected-period makeup count, occupied minutes, and current-rule
   opportunity-cost cents to operational financial analytics.
2. Add a compact **Reposições** section after class outcomes in Financeiro.
3. Explain that potential value is a capacity reference and not lost income.

**Verification:** aggregate is tenant-scoped, date-bounded, and links only to
persisted redeemed credits; empty and zero states are explicit.

### Phase 3 — Regression coverage and documentation

1. Add service/API tests for redemption, pricing exclusion, capacity inclusion,
   tenant isolation, and aggregate valuation.
2. Update Financeiro, makeup-credit, and business-rule documentation.
3. Link this roadmap from the README and update the operational-intelligence
   roadmap implementation record.

**Verification:** financial, revenue, makeup, and agent regression suites
pass; no migration is required because the existing redeemed-appointment link
is reused.

## 4. Guardrails

- Do not alter the original cancellation/credit eligibility policy.
- Do not estimate opportunity cost from a historical rate snapshot; use the
  clearly labeled current configured pricing rules.
- Do not remove makeup appointments from capacity or the calendar.
- Do not classify unredeemed credits as scheduled makeups.
- Do not expose a combined revenue total that hides the distinction between
  projected, realized, and potential values.
