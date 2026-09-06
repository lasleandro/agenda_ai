# Assistant, Sidebar, and Admin Controls Roadmap v0.1 — 2026-09-05

**Status: implemented locally on 2026-09-05.** This roadmap covers three
related platform-surface improvements: minimizing the floating assistant
through an outside click, anchoring WhatsApp as the bottom navigation item,
and restricting Mock Chat to platform administrators.

**Amendment 2026-09-06:** the "not exposed in production" boundary below is
superseded. With every `/api/dev/*` handler now gated on a platform admin
with a selected tenant, Mock Chat may run in a deployed environment. The
router is registered when `DEBUG=true` **or** `ENABLE_MOCK_CHAT=true`; Azure
sets `ENABLE_MOCK_CHAT=true` (it cannot set `DEBUG=true`). References to a
`DEBUG`-only registration boundary in the sections below should be read as
"`DEBUG=true` or `ENABLE_MOCK_CHAT=true`".

Implementation notes:

- Lob now has a transparent `z-[69]` dismissal boundary beneath its ball and
  panel (`z-[70]`), plus Escape minimization. The panel remains mounted, so
  the draft and conversation are retained.
- The shared desktop/mobile sidebar separates primary navigation from a
  bottom-anchored WhatsApp action above the account tray.
- Mock Chat is hidden from professionals, redirects direct professional and
  unscoped-admin route visits, and every `/api/dev/*` handler now requires a
  platform admin with a JWT-derived selected tenant.

## 1. Goal and product outcome

Make the in-platform assistant feel lightweight rather than modal, make the
left navigation reflect WhatsApp's operational priority, and stop exposing a
developer-only Mock Chat surface to tenant professionals.

After implementation:

- An open **Lob** panel minimizes when the user clicks or taps outside it;
  its in-memory conversation and draft remain available when reopened.
- **WhatsApp** is the final, bottom-anchored navigation action immediately
  above the account tray in both the desktop sidebar and mobile drawer.
- **Mock Chat** is visible and usable only to a `platform_admin` who is
  impersonating/has selected a tenant. Professionals cannot discover it via
  navigation, load its route, or call its development API endpoints.

## 2. Scope and non-goals

### In scope

- Outside-click/tap dismissal of the floating assistant, including mobile
  touch interaction and keyboard Escape dismissal.
- A sidebar layout split that places WhatsApp at the bottom without changing
  its route or connection behaviour.
- Frontend route protection and server-side RBAC for every Mock Chat API
  endpoint.
- Regression coverage and documentation updates for the changed access rule.

### Out of scope

- Changing the assistant's prompts, message persistence, AI tools, drag
  behaviour, or candidate-confirmation flow.
- Converting the assistant into a full-screen mobile dialog.
- Changing WhatsApp provider configuration, connection flow, or tenant
  feature flags.
- ~~Exposing Mock Chat in production.~~ Superseded by the 2026-09-06
  amendment: the router is registered when `DEBUG=true` or
  `ENABLE_MOCK_CHAT=true`, and platform-admin RBAC is the guard that makes a
  deployed environment acceptable.
- A general permissions framework or a new role. The existing
  `platform_admin` role is sufficient.

## 3. Current state and reusable assets

- The draggable ball and panel are implemented in
  [floating-chat.tsx](../../frontend/src/components/assistant/floating-chat.tsx).
  The panel is rendered inline in `AppShell`, at `z-[70]`, and is hidden
  rather than unmounted when closed. Its only close action today is the
  `onClose` handler passed to [assistant-panel.tsx](../../frontend/src/components/assistant/assistant-panel.tsx).
- [sidebar.tsx](../../frontend/src/components/layout/sidebar.tsx) supplies
  both the desktop sidebar and the mobile drawer. It currently has one
  `flex-1` navigation list; WhatsApp appears before **Minha Operação**, and
  Mock Chat is unconditionally listed.
- `/dev/mock-chat` lives outside the protected route group and performs its
  own client session check in
  [page.tsx](../../frontend/src/app/dev/mock-chat/page.tsx). That check only
  redirects an unscoped platform admin to tenant selection; it currently lets
  a professional render the tool.
- The `/api/dev/*` router is conditionally registered when `DEBUG=true` in
  [main.py](../../backend/app/main.py). Its endpoints use
  `require_professional_id`, which gives tenant scoping but does **not** check
  the actor role. `require_platform_admin` in
  [dependencies.py](../../backend/app/api/dependencies.py) is the existing
  role guard to reuse.
- Session data already exposes both `role` and `professional_id` through
  [auth.ts](../../frontend/src/lib/auth.ts), so neither schema nor database
  changes are needed.

## 4. Product and security decisions

1. **Outside click minimizes; it does not click through.** A click/tap outside
   the panel closes it and consumes that first interaction. The user may then
   interact with the underlying control. This prevents an accidental create,
   delete, navigation, or confirmation while merely trying to minimize Lob.
2. **Inside interaction is preserved.** Clicking, tapping, selecting text,
   scrolling, sending a message, confirming/rejecting a candidate, or dragging
   the ball never dismisses the panel. The existing close button remains.
3. **Dismissal preserves local state.** The panel stays mounted as it does
   today, so messages, a partially typed draft, and candidate state remain on
   reopen. Escape has the same minimize behaviour as an outside click.
4. **WhatsApp is physically bottom-anchored.** It becomes the sole secondary
   navigation item directly above the account tray, not merely the last entry
   in a top-aligned list. Mock Chat remains in the primary group for eligible
   admins, above that final WhatsApp action.
5. **Mock Chat requires two conditions.** A caller must have
   `role == "platform_admin"` **and** a selected `professional_id`. The latter
   retains the current tenant isolation: a global admin first chooses a tenant,
   then operates that tenant's isolated mock data.
6. **Authorization is server-enforced.** Hiding the link and redirecting the
   page improves UX; every `/api/dev/*` handler must also reject a professional
   with 403. No client-provided role or tenant is trusted.

## 5. Implementation phases

### Phase A — Floating-assistant dismissal boundary

In [floating-chat.tsx](../../frontend/src/components/assistant/floating-chat.tsx):

- Add a full-viewport, transparent dismissal layer only while `open` is true.
  It sits below the ball/panel (`z-[69]`) and above all application surfaces
  (`z-50` and below), calls `setOpen(false)`, and consumes the outside click.
- Keep the launcher and chat panel at `z-[70]`. The launcher remains usable
  for open/close and dragging; the panel remains the only interactive region
  above the dismissal layer.
- Register an Escape-key handler while the panel is open, remove it on close
  and unmount, and use the same `setOpen(false)` path.
- Do not alter `AssistantPanel` state ownership or unmount it. The existing
  `hidden={!open}` implementation deliberately retains the conversation and
  draft.
- Ensure panel pointer/touch interactions cannot reach the dismissal layer;
  this is naturally guaranteed by stacking order, but must be manually
  checked for scrolling and the Popover used by candidate actions.

**Verify:** open Lob, type a draft, click/tap outside, and reopen: the draft
and history remain. Confirm that clicks inside the composer, a message bubble,
a candidate button, and the drag ball do not close it. Press Escape to minimize
it. On a narrow touch viewport, confirm the transparent boundary spans the
whole viewport but the ball remains draggable and on top.

### Phase B — Sidebar navigation grouping and WhatsApp placement

Refactor only [sidebar.tsx](../../frontend/src/components/layout/sidebar.tsx):

- Separate the current list into a primary item collection and a single
  WhatsApp item. Preserve each existing `href`, icon, active-prefix rule, and
  commercial-financial feature filter.
- Render the primary group at the top of the existing `flex-1` `<nav>`.
  Render WhatsApp with `mt-auto` in the same nav, immediately before the
  account-tray divider. This makes it the actual bottom navigation action on
  desktop and in `MobileNav`'s shared `SidebarContent`.
- Keep **Mock Chat** in the primary collection (when authorized), so it never
  displaces WhatsApp from the bottom position.
- Preserve `onNavigate` on every item so the mobile drawer closes after
  navigation. Do not change the sign-out/account-tray layout.
- Check short desktop heights and mobile landscape: the primary group may
  scroll within the nav if necessary, while the WhatsApp action and account
  tray remain reachable. Use only the minimal overflow class required by that
  check; do not change general sidebar sizing.

**Verify:** desktop and mobile drawer show the same ordering; WhatsApp is the
last navigational action above the account tray; active styling still works on
`/configuracoes/whatsapp`; commercial-financial visibility is unchanged.

### Phase C — Mock Chat role guard in the frontend

Update both discoverability and direct-route behaviour:

- In [sidebar.tsx](../../frontend/src/components/layout/sidebar.tsx), render
  **Mock Chat** only after `fetchSession()` resolves a user with
  `role === "platform_admin"`. Do not use a feature flag for this.
- In [dev/mock-chat/page.tsx](../../frontend/src/app/dev/mock-chat/page.tsx),
  make the existing session check explicit:
  - no session → `/login`;
  - professional → `/agenda`;
  - platform admin without `professional_id` → `/admin/select-tenant`;
  - platform admin with selected tenant → render Mock Chat.
- Keep the existing selected-tenant requirement in the UI. It explains why an
  admin must impersonate before operating tenant-scoped mock conversations and
  prevents a blank/ambiguous workspace.
- Keep the app-shell ownership in this route unchanged unless a focused review
  finds a duplicate shell. This roadmap does not move route folders merely to
  share a guard.

**Verify:** a professional never sees the menu item and a pasted
`/dev/mock-chat` URL lands at `/agenda`; a global admin lands at tenant
selection; an impersonating admin sees the menu and can load the workspace.

### Phase D — Mock Chat server-side RBAC

Create one narrowly named dependency in
[dependencies.py](../../backend/app/api/dependencies.py), built on the
existing `require_platform_admin` result:

```text
require_platform_admin_professional_id() -> UUID
```

- It first confirms the authenticated user has `platform_admin` role, then
  returns the JWT-derived `professional_id` or raises 403 if no tenant is
  selected. It must never accept a professional ID from a route, query, or
  request body.
- Replace `require_professional_id` with this dependency on every handler in
  [dev_mock.py](../../backend/app/api/dev_mock.py): read conversation, list
  and create mock customers, send a message, reset conversation, and process
  now.
- Preserve all current per-query `professional_id` filters. RBAC reduces who
  may enter; it does not replace tenant isolation after entry.
- Reuse the existing dependency-layer 403 behaviour; do not introduce a new
  client-facing error format or disclose whether another tenant owns a
  resource.
- Do not change `main.py`'s `DEBUG=true` router-registration condition. In a
  non-debug deployment, the route remains absent; in a debug deployment, a
  professional receives 403 rather than being able to create or inspect mock
  data.

**Verify:** authenticated professional requests to every `/api/dev/*` route
return 403; a platform admin without impersonation returns 403; a platform
admin who has selected a tenant retains the current 200/creation behaviour.
For each test, ensure a requested conversation/customer from another tenant is
still 404 or inaccessible under the selected tenant, as it is today.

### Phase E — Tests and accessibility checks

Write tests alongside their phase, not as a final clean-up:

- **Backend:** extend
  [test_dev_mock.py](../../backend/tests/test_dev_mock.py), or add focused
  API-level cases there, for the three authorization states: professional
  denied, unscoped platform admin denied, scoped platform admin allowed. Cover
  at least one read and one state-changing dev endpoint; parameterize the
  remaining route matrix if that keeps the test concise.
- **Frontend/e2e:** add a Playwright spec or extend the existing authenticated
  fixture pattern to verify role-based navigation and direct route redirects.
  It must use test identities/session fixtures, never a real admin credential.
- **Assistant manual/e2e interaction:** verify pointer and touch outside-click
  minimization, Escape, no click-through to a representative destructive
  action, and draft/history preservation. Use the actual draggable launcher;
  avoid a brittle assertion tied to implementation-specific DOM order.
- **Accessibility:** the dismissal layer has an accessible name or is hidden
  from the accessibility tree as appropriate, Escape works, focus remains
  usable after minimize/reopen, and the close button's existing accessible
  name is retained. Validate keyboard navigation around the ball and panel.
- Name backend tests `test_<unit>_<scenario>_<expected_result>` and run the
  relevant local subset before the full regression suite.

### Phase F — Documentation and release readiness

- Update [docs/pages/chat.md](../../docs/pages/chat.md) to describe outside
  click/tap and Escape minimization, including state preservation.
- Update the **Dev tool — mock WhatsApp chat** section in
  [README.md](../../README.md) and the Mock Chat page documentation: it is
  `DEBUG=true` only **and** requires a platform admin with a selected tenant.
- Add the completed roadmap to the root README's **Roadmaps & Guides** list
  (this roadmap is linked there when it is created).
- No migration, `.env` parameter, dependency, Docker, or Azure database sync
  work is expected. Confirm that `requirements.txt` and the frontend lockfile
  remain untouched.

**Release check:** launch with `DEBUG=false` and verify `/api/dev/*` is absent;
launch local development with `DEBUG=true`, then execute the Phase E admin and
professional checks. The feature is ready only when both deployment absence and
debug-environment RBAC are demonstrated.

## 6. Touch-point matrix

| Area | Files | Change | Safety check |
| --- | --- | --- | --- |
| Assistant interaction | `frontend/src/components/assistant/floating-chat.tsx` | Add dismissal layer and Escape handler while preserving dragged-ball and hidden-panel state. | No click-through; panel content and draft survive minimize. |
| Assistant UI | `frontend/src/components/assistant/assistant-panel.tsx` | No planned code change; retain the explicit close button and current state ownership. | Candidate actions and composer remain interactive. |
| Shared layout | `frontend/src/components/layout/app-shell.tsx` | No planned code change; it remains the assistant mount point. | Assistant still layers over application dialogs. |
| Desktop/mobile navigation | `frontend/src/components/layout/sidebar.tsx` | Split primary navigation from bottom WhatsApp action; conditionally render Mock Chat. | Shared `SidebarContent` maintains identical order in both surfaces. |
| Mock Chat route | `frontend/src/app/dev/mock-chat/page.tsx` | Explicit client redirect matrix based on session role and selected tenant. | Direct URLs do not expose the workspace to professionals. |
| Session contract | `frontend/src/lib/auth.ts` | No schema change; consume existing `role` and `professional_id`. | Do not duplicate or infer authorization from UI state. |
| Dev API access | `backend/app/api/dependencies.py`, `backend/app/api/dev_mock.py` | Add and apply composed admin-plus-tenant dependency. | Every handler rejects a professional, including direct HTTP calls. |
| Dev router deployment boundary | `backend/app/main.py` | No change planned; preserve `DEBUG=true` registration. | Production-like launch does not register `/api/dev/*`. |
| Tests | `backend/tests/test_dev_mock.py`, `frontend/e2e/` | Add RBAC and interaction/route coverage. | Test both denied and allowed actors. |
| Documentation | `docs/pages/chat.md`, `README.md` | Explain new dismissal and admin-only Mock Chat rules; link this roadmap. | Docs match actual `DEBUG` and impersonation prerequisites. |

## 7. Sequencing and smallest shippable slice

Phases A and B are isolated frontend changes and can be implemented in either
order. Phases C and D form one authorization feature and must ship together:
frontend hiding alone is cosmetic, while backend-only authorization leaves a
misleading menu. Phase E tests are written with each phase. Phase F is the
hand-off and release check.

Recommended pull-request order:

1. **PR 1:** Phase A with interaction coverage.
2. **PR 2:** Phase B with desktop/mobile verification.
3. **PR 3:** Phases C + D + role tests, then Phase F documentation updates.

The smallest safe release is all three PRs. Do not deploy the Mock Chat menu
change before its API authorization change.

## 8. Risks and resolved trade-offs

- **Transparent backdrop versus click-through:** consuming the first outside
  click adds one extra click before a background action, but it is the safer
  choice around candidate confirmation and other state-changing UI.
- **Existing high z-index:** the assistant intentionally sits above dialogs.
  The new dismissal layer must be one layer below the ball/panel but still
  above the application's `z-50` overlays; a visual regression check with a
  dialog and popover open is required.
- **Admin is not a tenant:** Mock Chat's data model is tenant-scoped. Requiring
  a selected tenant avoids changing that model or accidentally making mock
  conversations global. It also matches the existing protected-workspace
  convention.
- **Debug-only does not equal authorized:** developers often run with
  `DEBUG=true`; without Phase D, any logged-in professional can mutate mock
  records. This is why RBAC is an API concern, not only sidebar filtering.
- **Sidebar height:** physically anchoring WhatsApp changes the flex layout.
  Verify compact viewport behaviour before adding scrolling; do not introduce
  a general sidebar redesign to solve a single-item placement change.
