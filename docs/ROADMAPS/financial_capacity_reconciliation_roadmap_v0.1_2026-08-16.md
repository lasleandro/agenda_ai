# Financial Capacity Reconciliation Roadmap v0.1 — 2026-08-16

## Status

**Roadmap state:** Phases 0–3 completed and verified for the changed surfaces.

This roadmap reconciles the Financeiro month summary, capacity valuation, and
dependent platform surfaces with the canonical place-stay model established in
`place_stays_and_schedule_overlay_roadmap_v0.1_2026-08-15.md`.

Status notation:

- `[ ]` not started
- `[-]` in progress
- `[x]` completed and verified
- `[!]` blocked; the blocker must be written beside the item

## Executive decision

Financeiro will preserve two valid kinds of work-journey capacity:

- **Capacity at defined places:** work-journey time covered by an active place
  stay, valued with that place's regular/prime rate inheritance.
- **Capacity without a defined place:** remaining work-journey time, surfaced as
  `Sem local definido` and valued with the generic-location matrix, falling back
  to tenant-global rates.

The month capacity card will show the combined observed-demand potential and a
visible split between these two sources. Calendar items continue to own actual
demand and revenue; place stays only attribute potential capacity to venues.

## Reproduced defect and baseline

The local Joao tenant for August 2026 reproduces the reported summary exactly:

| Measure | Current value | Evidence |
|---|---:|---|
| Scheduled through August 16 | R$ 10,920.00 | Agenda-based operational estimate through today |
| Scheduled month projection | R$ 31,740.00 | 86 booked hours |
| Observed-mix capacity potential | R$ 6,714.60 | Only 20 stay-attributed hours receive a price |
| Work-journey capacity | 370 hours | 20 stay-attributed + 350 unattributed |
| Bookings overlapping matching stays | 6 hours | The remaining booked time is valid explicit-place demand outside stays |

The tenant has a complete generic-location regular/prime rate matrix and no
tenant-global rates. Before this roadmap, `_potential_metric()` bypassed
`PricingRules.resolve(None, ...)` for unattributed capacity and read only the
empty global-rate table. It therefore gave 350 valid hours a zero monetary
value. The corrected generic resolution produces an observed-mix capacity
potential of R$ 140,339.38.

A separate semantic ambiguity exists in the month summary: the original
`Realizado no mês` value sums scheduled dashboard points through today, while
the immutable, explicitly confirmed revenue ledger answers a different
accounting question. For the same local period, confirmed participant revenue
was R$ 0.00 and confirmed event income was R$ 3,000.00. The card must preserve
the useful agenda-based estimate under an explicit label and show recognized
revenue separately.

## Locked business rules

1. Work Journey remains the professional-wide capacity envelope.
2. Active place stays attribute parts of that envelope to named places; they
   do not create bookings, demand, revenue, or busy time.
3. Work-journey time without a covering stay remains valid generic capacity.
4. Generic capacity uses the generic regular/prime rate matrix first and then
   tenant-global rates. It must not inherit a named place's rate.
5. Actual scheduled revenue follows each calendar item's persisted place and
   current projection rules, even when the item was explicitly created outside
   a stay.
6. Recognized revenue comes only from immutable confirmed revenue occurrences.
   Confirmed instructor-event income remains a separate amount.
7. The month capacity headline uses 100% occupancy with the observed participant
   mix. Its copy must identify that assumption; it is not the maximum possible
   groups-of-four scenario.
8. A split must reconcile exactly: named-place potential plus generic potential
   equals the capacity headline, and their hours equal total capacity hours.
9. Place filters must not assign generic capacity to the selected place.
10. No fix may rewrite historical revenue or mutate place/calendar data.

## Platform touchpoint assessment

| Surface | Assessment | Required action |
|---|---|---|
| Financeiro capacity presets | Generic capacity is incorrectly priced from global rates only | Use the canonical generic-to-global resolver and return a reconciled source split |
| Financeiro month summary | Capacity assumption is hidden and agenda estimates can be confused with accounting recognition | Show the capacity split, label the agenda-based month-to-date estimate explicitly, and surface recognized revenue separately from the confirmed ledger |
| Financeiro detailed dashboard | Place breakdown correctly uses stays, but generic capacity is absent from its explanatory summary | Add explicit generic-versus-place capacity explanation without assigning generic hours to a place |
| Simulator | Its scenario aggregate models and prices `Sem local definido` correctly; the real-agenda view needed an explicit period contract and recurrence bounds | Preserve scenario pricing, pass one complete period, and honor effective dates in the read-only real view |
| Revenue tab | Correct source of immutable recognized participant revenue and separate event income | Reuse its summary contract; do not duplicate recognition logic |
| Agenda and place resolution | Correctly treats stays as background context and permits audited explicit-place exceptions, but direct FullCalendar recurrence rendering omitted effective-date bounds | Preserve exception semantics and bound weekly rows with inclusive `valid_from`/`valid_until` dates |
| Meus Locais | Correctly owns venue identity, stays, and place pricing, but its stay form omits the supported effective-date fields | Expose the optional inclusive date range without reintroducing class fields |
| Shared weekly expansion | Place resolution honors `valid_from`/`valid_until`, but financial capacity and recurring-class projection still expand from `created_at` without the new end bound | Apply the effective-date contract consistently to stays and recurring classes |
| Waitlist and make-up recommender | Correctly require concrete stay-attributed openings because they must recommend a real place/time | No generic-capacity candidates; update stale documentation that still calls this surprising behavior a legacy `RecurringSlot` caveat |
| Active/passive agent scheduling | Correctly resolves unique stays and requires clarification or explicit exceptions when uncovered/ambiguous | No change to capacity pricing; retain current resolution rules |
| Documentation | Business/capacity docs still say uncovered time uses global rates only | Align with the completed place-stay roadmap and document the visible split |

## Delivery phases

### [x] Phase 0 — Reproduce and define the contract

- Reproduce all three month-summary values from local tenant data.
- Reconcile work-journey, stay-attributed, unattributed, booked, and overlapping
  hours.
- Confirm the generic matrix is configured and the tenant-global table is empty.
- Lock the capacity and recognized-revenue semantics above.

**Verification:** read-only local calculations reconcile the current
R$ 6,714.60 value and the corrected R$ 140,339.38 value.

### [x] Phase 1 — Backend capacity source reconciliation

- Price unattributed capacity through `PricingRules.resolve(None, ...)`.
- Extend the dashboard response with an explicit capacity-source breakdown for
  named-place and generic capacity, including minutes and observed-mix revenue.
- Keep place-filter behavior unchanged: filtered responses contain no generic
  source contribution.
- Use existing financial schemas and error conventions; no migration is needed.

**Verification:** backend tests cover generic-over-global precedence, fallback
to global rates, exact split reconciliation, place filters, and tenant scope.

### [x] Phase 2 — Month summary semantics and split UI

- Display the observed-mix capacity assumption in the headline card.
- Explain the 100%-occupancy, participant-mix, price, and place-source
  assumptions in an accessible tooltip on `Capacidade total do mês`.
- Show named-place and `Sem local definido` hours and monetary contributions.
- Keep the agenda-based estimate through today as the operational headline,
  with copy that does not imply accounting recognition.
- Fetch the existing confirmed-revenue summary for the current month and show
  recognized participant revenue and event income as separate details.
- Keep scheduled month projection sourced from the dashboard.
- Preserve responsive behavior and accessible explanatory copy.

**Verification:** the typed API contract covers both sources and recognized
revenue; TypeScript compilation and focused linting pass. The repository has no
configured frontend component-test runner.

### [x] Phase 3 — Cross-platform alignment

- Make shared weekly expansion honor inclusive `valid_from`/`valid_until`
  bounds for both stay capacity and recurring classes while preserving
  `created_at` as the fallback start for legacy rows.
- Apply the same inclusive effective dates to weekly rows rendered directly by
  the main Agenda and the simulator's read-only real-agenda view.
- Expose the optional effective-date range in the neutral Meus Locais stay form.
- Verify simulator totals reconcile with the same generic rate resolution.
- Verify Agenda, place resolution, waitlist, makeup, and active/passive agent
  flows still distinguish stays, generic capacity, and explicit exceptions.
- Correct stale business, page, architecture, and capacity documentation.
- Add a visible warning when named-place coverage is sparse only if the source
  split proves users cannot otherwise understand the result.

The explicit source rows make sparse named-place coverage visible, so no
additional warning or scheduling restriction was added.

**Verification:** targeted backend suites and frontend type checks pass; the
touchpoint table is updated with final evidence and no unsupported migrations or
data rewrites are introduced.

## Acceptance criteria

- Joao's August observed-mix capacity reads R$ 140,339.38 with the current local
  configuration and splits into 20 named-place hours plus 350 generic hours.
- The two monetary split values add exactly to the capacity headline.
- Scheduled projection remains R$ 31,740.00 unless source calendar or pricing
  data changes.
- The operational month-to-date estimate derives from scheduled dashboard
  points through today and is never labeled as recognized revenue.
- Recognized participant revenue derives only from immutable confirmed
  occurrences and remains visible even when it is zero.
- Named-place capacity continues to come only from active stay rows; recurring
  classes never inflate it.
- Weekly stays and recurring classes contribute only within their inclusive
  effective-date bounds.
- Generic capacity is never offered as a concrete waitlist or make-up slot.
- No remote database writes or historical revenue rewrites occur.

## Verification commands

Run from the repository root with the required `agenda` conda environment:

```bash
conda run -n agenda pytest backend/tests/test_financial.py backend/tests/test_schedule_projection.py -q
conda run -n agenda pytest backend/tests/test_place_stays.py backend/tests/test_waitlist.py backend/tests/test_calendar_mutations.py backend/tests/test_ontology.py -q
(cd frontend && conda run -n agenda npx tsc --noEmit)
(cd frontend && conda run -n agenda npx eslint 'src/app/(protected)/financeiro/page.tsx' src/components/financial/financial-month-summary.tsx src/components/ontology/recurring-slot-form-dialog.tsx src/lib/types.ts)
git diff --check
```

The frontend has no configured component-test runner, so the changed summary is
covered by its typed API contract, TypeScript compilation, and focused linting.
The repository-wide lint command retains unrelated pre-existing
`react-hooks/set-state-in-effect` failures outside the changed files.

## Rollback

The backend change is response-additive and calculation-only. Roll back the
generic resolver call and new response fields together with the matching UI.
Do not alter financial configuration, place stays, calendar items, or recognized
revenue records during rollback.

## Progress log

| Date | Phase | Status | Evidence |
|---|---|---|---|
| 2026-08-16 | Phase 0 | Completed | Reproduced local summary, isolated the generic-rate bypass, reconciled 370 capacity hours, and identified the agenda-estimate versus recognized-revenue ambiguity. |
| 2026-08-16 | Phase 1 | Completed | Generic capacity now uses generic-to-global resolution; the dashboard returns an exact two-source split. Financeiro and schedule-projection suites: 12 passed. |
| 2026-08-16 | Phase 2 | Completed | Month cards now distinguish the agenda-based estimate, recognized revenue, scheduled projection, and observed-mix potential; the capacity card shows hours and revenue for both sources. TypeScript and focused lint checks passed. |
| 2026-08-16 | Phase 3 | Completed | Weekly stay/class expansion now honors effective dates and Meus Locais exposes them; place-stay, waitlist, calendar, and ontology coverage passed. The unchanged makeup suite has five clock-sensitive failures because its fixed August 17 examples are now inside the configured 24-hour notice window. |
| 2026-08-16 | Follow-up | Completed | Added the capacity-scenario tooltip, replaced the simulator agenda's loose date bounds with an explicit period contract, and bounded weekly calendar rows by their effective dates. Live local `/api/auth/me` checks returned 200 for every active user role. |
| 2026-08-16 | Revenue follow-up | Completed | Reconciled João's 39 August agenda occurrences with an empty recognition ledger. Restored the R$ 10,920.00 agenda-based estimate as an explicitly labeled headline and retained R$ 0.00 recognized participant revenue as a separate detail. |
