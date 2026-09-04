# Page: Clientes (Contacts)

**Route (list):** `/clientes`
**File (list):** `frontend/src/app/(protected)/clientes/page.tsx`

**Route (detail):** `/clientes/[id]`
**File (detail):** `frontend/src/app/(protected)/clientes/[id]/page.tsx`

---

## Overview

The Clientes module provides the instructor's customer relationship
management. Two pages: a searchable list with group management, and
a detail page for editing individual contact profiles.

---

## Clientes List

### Key Components

| Component | File | Purpose |
|---|---|---|
| `GroupsTab` | `components/ontology/groups-tab.tsx` | Groups tab showing all recurring groups |
| `RecurringGroupDialog` | `components/ontology/recurring-group-dialog.tsx` | Form to create a new group with selected contacts |
| `AddToGroupDialog` | `components/ontology/add-to-group-dialog.tsx` | Per-contact dialog to add to existing group |
| `AddToWaitlistDialog` | `components/ontology/add-to-waitlist-dialog.tsx` | Per-contact dialog to add to the Fila de Espera (waitlist roadmap v0.1) |
| `DetectedCandidatesTab` | `components/ontology/detected-candidates-tab.tsx` | Review surface for passive-observer-detected scheduling events |
| `ContactFormDialog` | `components/ontology/contact-form-dialog.tsx` | Manual customer registration with an international phone input (Brazil selected by default) |

### Three-Tab Layout

- **Clientes tab:** Search/filter list, multi-select for group creation, Fila de Espera filter chip
- **Grupos tab:** All group-type recurring slots, with standing participant
  management. The Agenda remains the dated operational view for empty seats
  and one-date guests.
- **Detectados tab:** `AppointmentCandidate` rows (status `detected`) from the passive observer — dismiss, create a reviewed appointment, or for `waitlist_request` candidates, complete/confirm into a real waitlist entry. The card explains whether the location came from a place stay, a valid home-place tie-break, or needs explicit review.

### Data Sources

| Data | Endpoint |
|---|---|
| Contacts | `GET /api/contacts` |
| Create contact | `POST /api/contacts` |
| Places | `GET /api/places` |
| Recurring slots | `GET /api/recurring-slots` |
| Waitlist entries (open + matched) | `GET /api/waitlist-entries` |
| Detected candidates | `GET /api/appointment-candidates?status=detected` |

### User Actions

| Action | How |
|---|---|
| Register customer | Click **Novo cliente**, enter a name and mobile/WhatsApp number; Brazil is preselected and foreign numbers require their calling code |
| Search contacts | Type in search field (client-side filter by name, phone, place) |
| Select for group | Check checkboxes (max 4), click "Criar grupo" |
| Add to group | Per-row `UserPlus` button → select group in dialog |
| Navigate to detail | Click row → `/clientes/[id]` |
| Call contact | Per-row `Phone` button |
| Filter to waitlisted contacts | "Fila de espera" chip next to search |
| Add/remove from waitlist | Per-row `Clock` button — toggles based on current state, opens `AddToWaitlistDialog` |
| Review a detected event | Detectados tab → dismiss; confirm a create after reviewing time/service/place; or add a `waitlist_request` to the waitlist |

### Visual Design

- Each row: display name, phone, home place (MapPin icon), level badge,
  makeup credits badge (blue, shows count), Fila de Espera badge (grey,
  clock icon) when the contact has an open/matched waitlist entry
- Client-side pagination, 10 per page
- Search filters in real-time as user types
- Registration inserts an optimistic row immediately; a server rejection removes
  it and restores the entered values. A duplicate WhatsApp number shows the
  API conflict without adding another customer.

---

## Contact Detail

### Key Components

| Component | File | Purpose |
|---|---|---|
| `AddressAutocomplete` | `components/ontology/address-autocomplete.tsx` | Geocoded address input |
| `AssignSlotDialog` | `components/ontology/assign-slot-dialog.tsx` | Assign recurring slot to contact |
| `CommercialFieldsCard` | `components/financial/commercial-fields-card.tsx` | Hourly rate override + commercial status |

### Data Sources

| Data | Endpoint |
|---|---|
| Contact detail | `GET /api/contacts/{id}` |
| Places | `GET /api/places` |
| Customer financials | `GET /api/financial/customers/{id}` (if feature enabled) |

### Editable Fields

| Field | Component | Save Endpoint |
|---|---|---|
| Level | Dropdown (`CONTACT_LEVELS`) | `PATCH /api/contacts/{id}` |
| Home place | Dropdown of places | `PATCH /api/contacts/{id}` |
| Address | `AddressAutocomplete` with geocoding | `PATCH /api/contacts/{id}` |
| Hourly rate override | `CommercialFieldsCard` (feature-gated) | `PATCH /api/financial/customers/{id}` |
| Commercial status | `CommercialFieldsCard` (feature-gated) | `PATCH /api/financial/customers/{id}` |

### Read-Only Sections

- **Courtesy appointments:** Amber info box listing all `aula cortesia`
  appointments with date, time, place, service, and status. Hidden when
  empty.
- **Fixed slots (Horarios fixos):** List of assigned recurring slots with
  day, time, place. Each has an "X" remove button. "Atribuir horario fixo"
  button opens `AssignSlotDialog`.

### Optimistic UI

- Assigning a slot immediately adds it to the UI before the API call.
- Saving contact fields updates state immediately, reverting on failure.
- Financial save uses optimistic state update.

### Visual Design

- Breadcrumb: `← Voltar para Clientes`
- Contact name as page title
- Form sections with card-style borders
- Courtesy section with amber/gold accent
- Fixed slots as a list of chips with remove buttons
