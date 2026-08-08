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

### Two-Tab Layout

- **Clientes tab:** Search/filter list, multi-select for group creation
- **Grupos tab:** All group-type recurring slots, with participant management

### Data Sources

| Data | Endpoint |
|---|---|
| Contacts | `GET /api/contacts` |
| Places | `GET /api/places` |
| Recurring slots | `GET /api/recurring-slots` |

### User Actions

| Action | How |
|---|---|
| Search contacts | Type in search field (client-side filter by name, phone, place) |
| Select for group | Check checkboxes (max 4), click "Criar grupo" |
| Add to group | Per-row `UserPlus` button → select group in dialog |
| Navigate to detail | Click row → `/clientes/[id]` |
| Call contact | Per-row `Phone` button |

### Visual Design

- Each row: display name, phone, home place (MapPin icon), level badge,
  makeup credits badge (blue, shows count)
- Client-side pagination, 10 per page
- Search filters in real-time as user types

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
