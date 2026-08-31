# Mobile Readiness Audit — 2026-08-31

## Verdict

The product has the core mobile foundations and the code remediation for the
identified phone defects is implemented. It is **not yet proven ready for a
production mobile release** because an installed-PWA pass on physical iOS and
Android devices remains outstanding.

## Scope and evidence

This was a code-level audit of the current Next.js frontend, targeting
360–430px wide phones. It reviewed protected pages, the shared app shell,
agenda, financial screens, dialogs, and PWA setup. It did not include a
physical iOS or Android device walkthrough.

The existing baseline is good:

- The desktop sidebar is replaced with a 56px mobile header and slide-over
  navigation below 768px.
- The agenda changes from a week grid to FullCalendar's `listWeek` view
  below 768px.
- Clientes, Locais, Financeiro, and the simulator use responsive stacking or
  single-column layouts for their primary content.
- The app has a manifest, 192px/512px/maskable icon routes, iOS web-app
  metadata, and a registered service worker.

These foundations mean the remaining work is a focused mobile-hardening pass,
not a redesign.

## Pain points, prioritized

### Resolved P0 — Agenda filter controls overflow horizontally

`week-calendar.tsx` places the appointment count, two filter pills, and the
refresh action in one non-wrapping flex row. At 360px this content is wider
than its available space, leaving the rightmost controls inaccessible or
forcing page-level horizontal overflow. This is on the primary daily workflow.

**Fix:** use `flex-wrap` with a small row gap, or make the count a full-width
line on phones. Keep the filters and refresh button in the next row.

### Resolved P0 — The assistant cannot fit on a 360px phone

`floating-chat.tsx` fixes the panel width at `w-96` (384px). The standard
360px viewport is narrower than the panel before accounting for any browser
safe area, so opening the assistant clips it horizontally. Its height also
uses `100vh`, which is unreliable while mobile browser chrome expands or
collapses.

**Fix:** use a mobile width such as `w-[calc(100vw-2rem)]` and retain `w-96`
from `sm` upward. Replace viewport-dependent height/placement with dynamic
viewport units (`dvh`) and safe-area-aware offsets.

### Resolved P1 — Long scheduling dialogs can leave controls below the viewport

The shared `DialogContent` caps width but not height and does not provide an
internal scroll region. `AppointmentFormDialog`, `GroupDetailsDialog`,
`RecurringSlotFormDialog`, and `PlaceFormDialog` can all exceed a short phone
viewport; the group-details dialog is especially likely to do so once
financial fields and participant actions are present. The save/close actions
can become unreachable with the on-screen keyboard open.

**Fix:** establish a shared dialog pattern: a `max-h-[calc(100dvh-2rem)]`
container with a scrollable body and a sticky or persistent footer. Apply it
first to appointment creation and group details.

### Resolved P1 — Full-height shell is vulnerable to mobile browser chrome

The protected app shell uses `h-screen`/`100vh`. On iOS Safari and Android
Chrome this can size the application against a stale viewport while address
or keyboard chrome is visible, causing clipped bottoms or nested-scroll
friction.

**Fix:** use `min-h-dvh`/`h-dvh` where the shell and its fixed child panels
need the actual visible viewport. Validate focus and scroll behavior with a
keyboard open.

### P2 — Finance tables need real-device confirmation

Place rates and scenario trade-offs deliberately use horizontally scrollable
tables with 620px minimum widths. This prevents layout breakage, but hides
key values until users discover the horizontal gesture. The simulator's rate
table also keeps three columns visible at once, making values dense at 360px.

**Fix:** retain horizontal scrolling for now, add an affordance such as a
fade/scroll hint, and consider a mobile card representation only if device
testing confirms the tables are a frequently used phone workflow.

### Resolved P2 — Installed-app safe areas have not been handled explicitly

The manifest and iOS metadata are present, but fixed elements (notably the
assistant launcher) use fixed `bottom-6`/`right-6` offsets. They can sit too
close to a device's home indicator or rounded corners in standalone mode.

**Fix:** add CSS safe-area insets to fixed launcher, panel, and mobile header
spacing, then verify in iOS standalone mode.

## Release gate and recommended sequence

Do not describe the platform as mobile-ready until P0 issues are fixed and
the following checks pass at 360px, 375px, and 430px widths:

1. Open every primary route through the mobile drawer; no page has horizontal
   document scroll.
2. In Agenda, toggle both filters, refresh, change week, create an
   appointment, open a group, and dismiss each dialog with the virtual
   keyboard visible.
3. Open, use, drag, and close the assistant without clipped content or a
   launcher colliding with device safe areas.
4. Review Clientes, Locais, Financeiro, and the simulator; horizontally
   scroll the intentional rate/trade-off tables and confirm no controls are
   obscured.
5. Install on Android Chrome and iOS Safari, then launch standalone and
   repeat the Agenda and assistant checks.

Recommended order: fix the agenda row and assistant first, introduce the
shared dialog-height pattern, update dynamic-viewport/safe-area handling, and
then conduct the two-device walkthrough. This keeps the release-critical work
small and makes device testing meaningful.

## Verification note

At the start of the audit, `conda run -n agenda npm run lint` failed on a
`react-hooks/set-state-in-effect` error in
`frontend/src/components/ontology/place-form-dialog.tsx:54`. The issue was
resolved as part of the release-validation work below.

## Implementation update — 2026-08-31

The code remediation described above is now implemented:

- Agenda controls wrap below the appointment count on phone widths.
- The assistant panel has a viewport-relative width/height, safe-area-aware
  launcher placement, and constrained drag/panel placement.
- The app shell, mobile drawer, login, and admin surfaces use dynamic viewport
  units; the admin task tabs can scroll horizontally when necessary.
- Shared dialogs have a dynamic viewport height cap, internal scrolling, and
  a persistent footer. Long appointment and group flows now retain reachable
  controls.
- Phone-only instructions identify horizontally scrollable rate and trade-off
  tables; the regions are keyboard-focusable and labelled.
- The prior frontend lint error was resolved by mounting place forms only while
  open, which also resets their draft state on every opening.

`npm run lint`, `npx tsc --noEmit`, and a Webpack production build pass in the
`agenda` conda environment. A physical iOS/Android installed-PWA walkthrough
remains the final release gate; it cannot be established from this workspace.

## Browser verification — 2026-08-31

The running local application was rendered in headless Chrome at 360×740,
375×812, and 430×932 viewports. The mobile login flow fits each viewport with
no horizontal clipping. The local runtime also served all required installable
app resources successfully:

- `/manifest.webmanifest` returns a standalone manifest with 192px, 512px,
  and maskable PNG icon declarations.
- `/sw.js` returns the cache-safe service worker.
- `/pwa-icon-192`, `/pwa-icon-512`, `/pwa-icon-512-maskable`, and
  `/apple-icon` each return PNG responses.

Authenticated Agenda, assistant, dialog, and install-from-home-screen paths
still require a final check on physical iOS and Android devices. Browser
emulation cannot reproduce mobile virtual keyboards, Safari standalone mode,
or device safe-area behavior with sufficient confidence.
