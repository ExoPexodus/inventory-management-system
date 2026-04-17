# Entries Page Redesign

**Date:** 2026-04-18
**Status:** Approved

## Problem

The current `/entries` "New Entry Hub" page has three issues:

1. **Currency symbol is hardcoded** — the price label always says "USD" regardless of tenant settings.
2. **Create Shop is buried inside the product form** — confuses users into thinking they must create a shop with every product.
3. **Three-tab layout (Details / Provenance / Logistics) is fragmented** — users have to navigate tabs to fill in logically related fields, and the Logistics tab is just a read-only summary that doesn't need its own tab.

## Intended Outcome

A cleaner, single-scroll product creation form with a dropdown-based entry point that clearly separates "create product" from "create shop".

---

## Changes

### 1. "New Entry" button becomes a dropdown

Clicking the sidebar "New Entry" button opens a small dropdown menu with two items:

- **Create Product** → navigates to `/entries` (the product form)
- **Create Shop** → navigates to `/shops` (existing shop management, or a dedicated create page)

The dropdown replaces the current direct navigation to `/entries`.

**File:** `apps/admin-web/src/app/(main)/layout.tsx` or wherever the sidebar "New Entry" button is rendered.

### 2. Remove Create Shop from the entries page

The `CREATE SHOP` section (shop name input + "Create shop" button, currently lines ~213–232 of `entries/page.tsx`) is removed entirely. Shop creation belongs on its own page.

### 3. Collapse tabs into a single scrollable form

Remove the `Tabs` component and the three tab panels. Replace with a single vertical form divided by section headers:

| Section | Fields | Source |
|---------|--------|--------|
| **PRODUCT DETAILS** | SKU, Category, Display name, Price | was Details tab |
| **PRODUCT IMAGE** | Drop zone (2000×2000 JPG/PNG) | was Provenance tab |
| **VARIANTS** *(optional)* | Product group dropdown, Variant label, Create new group inline | was Provenance tab |
| *(Commit button)* | "Commit product" | was Logistics tab |

The Logistics tab's read-only summary moves to the right panel (see below).

### 4. Right panel: Live Preview + Summary

The right-side panel stacks two cards vertically:

1. **LIVE PREVIEW** — existing dark card (product name, price, SKU/category badges). No change in behaviour.
2. **SUMMARY** — new card showing SKU, Category, Variant, Group as a live key-value list. Updates reactively as the user types. Replaces the Logistics tab.

### 5. Currency symbol from tenant settings

The price field label currently reads "Price (USD)". Change it to read the currency code from `useCurrency()` and display the correct symbol/code:

```tsx
const currency = useCurrency();
// Label: `Price (${currency.code})`
// Preview: formatMoney(previewPriceCents, currency)  ← already correct
```

The live preview already uses `formatMoney` correctly; only the form label needs fixing.

---

## Files to Change

| File | What changes |
|------|-------------|
| `apps/admin-web/src/app/(main)/entries/page.tsx` | Remove tabs, remove Create Shop section, reorganise into single-scroll form, add Summary card to right panel, fix currency label |
| Sidebar component (wherever "New Entry" button lives — likely `apps/admin-web/src/app/(main)/layout.tsx` or a nav component) | Convert button to dropdown with two items |

---

## Out of Scope

- The actual Create Shop page/flow — this redesign only removes it from the entries page and ensures the dropdown routes to the right place. If no dedicated shop creation page exists yet, the dropdown item can link to `/shops` (the shop list) as a placeholder.
- Any backend changes — all data and API calls remain the same.

---

## Verification

1. Click "New Entry" in the sidebar → dropdown appears with "Create Product" and "Create Shop"
2. Click "Create Product" → lands on `/entries`, single-scroll form, no tabs visible
3. The price label shows the tenant's currency code (e.g. "Price (INR)" for the showcase demo)
4. Fill in SKU, name, price → Summary card on the right updates live
5. Drop an image → preview updates
6. Select/create a product group → group name appears in Summary
7. Click "Commit product" → product is created (same API call as before)
8. Click "Create Shop" from dropdown → navigates away from the product form (no shop form on this page)
