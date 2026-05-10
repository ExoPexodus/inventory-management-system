# M4 — Bulk Actions Toolbar Design

**Date:** 2026-05-10
**Phase:** Audit M4 (~½ day, scoped from 4-6 day full sweep)

## Problem
Products has row-selection + a bulk reorder-point input but the visual treatment is ad-hoc. Other pages have nothing. M4's full scope (apply to Products, Orders, Customers, Discounts) is multi-day; let's land the primitive + a second bulk action on Products as proof of pattern.

## Solution
1. Build a `<BulkActionsBar>` primitive — sticky toolbar showing "N selected" with action slots.
2. Refactor Products to use it — keeping the existing bulk-reorder action and adding bulk archive.
3. New backend endpoint `POST /v1/admin/products/bulk-archive`.

## Component shape
```tsx
<BulkActionsBar
  selectedCount={selected.size}
  onClear={() => setSelected(new Set())}
>
  {/* action buttons as children */}
  <button onClick={...}>Archive</button>
  <input value={bulkReorderPt} ... /> <button>Apply reorder</button>
</BulkActionsBar>
```

The bar:
- Hidden when `selectedCount === 0`
- Sticky at top of the list (or above the table)
- Shows "N selected" with a "Clear" button
- Children are action controls (rendered as a flex group)

## Backend
**New endpoint:** `POST /v1/admin/products/bulk-archive`
**Body:** `{ product_ids: UUID[] }`
**Response:** `{ archived: int, skipped: list[{ id, reason }] }`

Logic: validate tenant ownership, set `status = "archived"` on each, write one audit row.

## Files
| File | Status |
|---|---|
| `apps/admin-web/src/components/ui/BulkActionsBar.tsx` | NEW — primitive |
| `services/api/app/routers/admin_catalog.py` | New bulk-archive endpoint |
| `apps/admin-web/src/app/(main)/products/page.tsx` | Use BulkActionsBar; add Archive button |

## Out of scope
Applying BulkActionsBar to Orders, Customers, Discounts — follow-up work.
