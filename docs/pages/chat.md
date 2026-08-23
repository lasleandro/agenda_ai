# Chat / AI Assistant

**Surface:** Floating panel on every protected page
**Component:** `frontend/src/components/assistant/floating-chat.tsx`
**Panel:** `frontend/src/components/assistant/assistant-panel.tsx`

**Mock Chat (dev):** `/dev/mock-chat`
**File:** `frontend/src/app/dev/mock-chat/page.tsx`

---

## Overview

The AI assistant is accessible from every page via a floating chat button
(tennis ball icon) positioned at the bottom-right corner. It is NOT a
separate route -- it lives in the `AppShell` layout so it persists across
page navigation.

Additionally, a `/dev/mock-chat` page is available for testing WhatsApp
integration without a real phone.

---

## Floating Chat

### Entry Point

- A draggable floating button at `z-[70]` (topmost layer)
- Tennis ball icon
- Click opens the `AssistantPanel`

### AssistantPanel

- 600px tall, 384px wide chat panel
- Messages sent to `POST /api/assistant/messages`
- Displays:
  - **Assistant text replies:** Rendered as chat bubbles
  - **Tool call traces:** Expandable section showing which tools were
    called and their results (collapsed by default, for debugging)
  - **Pending action candidates:** A structured preview card showing
    exactly what action is proposed, with **Confirm** and **Reject** buttons
- Confirming: `POST /api/assistant/candidates/{id}/confirm`
- Rejecting: `POST /api/assistant/candidates/{id}/reject`
- On confirm/reject, dispatches `AGENDA_REFRESH_EVENT` so the calendar
  updates immediately

### Empty State

When no messages have been sent, the panel shows example suggestions:
- "Quem tenho amanha?"
- "Remarca a aula da Mariana para sexta as 15h"
- "Busca lugares disponiveis na quarta de manha"
- "Quais turmas tenho?"
- "Quais turmas ainda têm vagas esta semana?"
- "Abra uma turma toda terça às 18h no Clube"

### Conversation History

- Messages persist per session (not across page reloads currently)
- The `AppShell` `FloatingChat` component holds the `AssistantPanel` open
  state and conversation state
- Each message sent includes the full conversation history for context

### Tool Call Visibility

When the agent calls tools, the panel shows a collapsible "Ferramentas
utilizadas" section listing each tool name and a summary of its response.
This gives the instructor transparency into what the agent is doing.

### Group Capacity

The agent distinguishes a genuinely free opening from a seat in an existing
group. It can offer the latter with its effective occupancy and capacity, then
requires confirmation before creating an empty group, promoting an individual
class, or adding a dated guest. If a request could mean one occurrence or all
weeks, the confirmation preview names the scope instead of inferring it.

---

## Chat Flow Example

```
Instructor: "quem tenho amanha?"
  ↓
AssistantPanel sends POST /api/assistant/messages
  ↓
Agent orchestrator:
  1. Calls get_schedule(tomorrow) → returns 3 appointments
  2. Returns reply: "Voce tem 3 aulas amanha: ..."
  ↓
AssistantPanel displays:
  - Chat bubble with the assistant's reply
  - Expandable "Ferramentas utilizadas (1)" showing get_schedule result

Instructor: "remarca a da Mariana para 16h na Quadra 1"
  ↓
Agent orchestrator:
  1. Calls search_contacts("Mariana") → finds Mariana Silva
  2. Calls get_schedule(tomorrow) → finds Mariana's 10h slot
  3. Calls propose_reschedule_occurrence(...) → creates candidate
  4. Returns reply: "Vou reagendar a aula da Mariana Silva de amanha 10h
     para amanha 16h na Quadra 1. Confirma?"
  ↓
AssistantPanel displays:
  - Chat bubble with the assistant's explanation
  - Pending candidate card: "Reagendar aula" with Confirm/Reject buttons
  ↓
Instructor clicks Confirm → POST /api/assistant/candidates/{id}/confirm
  ↓
Panel shows success message, dispatches AGENDA_REFRESH_EVENT
Calendar re-fetches data, new time appears
```

---

## Mock Chat (Dev Only)

**Route:** `/dev/mock-chat`

A development tool for testing the WhatsApp extraction pipeline without
a real WhatsApp integration:

### Modes

- **Mock mode:** Simulated two-way conversation. Type as either
  "Cliente" or "Professor" and see the full conversation. Use **Novo cliente**
  to generate an isolated mock customer, then select any generated customer to
  resume its own conversation.
- **Live mode:** View real conversations from the database.

### Features

- Polls for new messages every 1.5 seconds in live mode
- Mock customers are tenant-scoped and retain separate message history
- "Processar conversa" button triggers `POST /api/dev/conversations/{id}/process-now`
  to force the extraction pipeline to run immediately
- Shows extracted `AppointmentCandidate` results with confidence scores
- Displays linked evidence messages

---

## Technical Notes

- The floating chat is a plain fixed-position element rendered inline in
  `AppShell` (no `React Portal`) — `z-[70]` alone is what keeps it above
  every `Dialog`/`Popover`/`Select`/`DropdownMenu` in the app, all of
  which render at `z-50`
- The chat button is draggable (custom pointer-event drag implementation);
  while the panel is open, dragging also live-updates the panel's anchor
  side so it never renders off-screen
- Conversation history is sent with every message (stateless backend)
- Tool call traces are parsed from the API response and displayed
  collapsed for developer transparency
