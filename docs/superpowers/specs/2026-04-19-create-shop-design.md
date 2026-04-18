# Create Shop Feature — Design Spec

**Date:** 2026-04-19  
**Status:** Approved  
**Scope:** Frontend only (backend endpoints already exist)

---

## Overview

Allow operators to create and view shops via a dedicated page flow. Accessible only through the "New Entry" dropdown in the AppShell sidebar — not in the main navigation.

---

## Routes

| Route | Purpose |
|---|---|
| `/shops` | Lists all existing shops for the tenant |
| `/shops/new` | Form to create a new shop |

Both routes live under `apps/admin-web/src/app/(main)/shops/`.

---

## AppShell Change

In `apps/admin-web/src/components/dashboard/AppShell.tsx`, the "Create Shop" entry in the "New Entry" dropdown is currently disabled with a "Soon" badge. Change it to:

- Remove disabled styling (`text-on-surface/40 cursor-not-allowed select-none`)
- Remove the "Soon" badge
- Make it a clickable link navigating to `/shops/new`
- Match the styling of the active "Create Product" entry

---

## `/shops/new` — Creation Page

**Entry point:** "Create Shop" in the AppShell "New Entry" dropdown.

**Form fields:**
- **Name** — text input, required, max 255 characters

**Submission:**
- Calls `POST /api/ims/v1/admin/shops` with `{ name: string }`
- On success: redirect to `/shops`
- On error — name taken (unique constraint violation from API): show inline field error "A shop with this name already exists"
- On error — server error: show a toast/banner error message

**Navigation:**
- Cancel button or back navigation goes to `/shops`

**Layout:** Single-scroll form, consistent with the entries page style.

---

## `/shops` — Listing Page

**Entry point:** Redirect from `/shops/new` after successful creation. Also reachable via direct URL.

**Content:**
- Page header: "Shops"
- "New Shop" button (top-right) linking to `/shops/new`
- Table with columns: **Name**, **Created** (formatted date)
- Data fetched from `GET /api/ims/v1/admin/shops`
- Empty state: message indicating no shops exist yet, with a prompt to create the first one

**No edit or delete actions** — deferred to a future iteration.

---

## API Endpoints Used

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/ims/v1/admin/shops` | Fetch shop list for listing page |
| `POST` | `/api/ims/v1/admin/shops` | Create a new shop |

Both endpoints already exist in the backend. No backend changes required.

---

## Out of Scope

- Default tax rate field (deferred — tax architecture not yet decided)
- Edit shop name
- Delete shop
- Shop detail page
- Sidebar nav entry for shops
- Currency handling changes
