# Q4 — Inventory Journal Filters Design

**Date:** 2026-05-10
**Phase:** Audit Q4 (~1 day)

## Problem
The Movement Journal section on `/inventory` only filters by `movement_type` today. Tenants with multiple shops or many products can't narrow the journal to find specific movements. The backend already supports `shop_id` and `product_id` filters; the frontend doesn't wire them.

## Solution
Add four filters in a row above the journal table:
1. **Movement type** (existing, keep as-is)
2. **Shop** — dropdown of all shops (`SelectInput` is fine; few shops per tenant)
3. **Product** — typeahead (uses the `<Typeahead>` component built in Q6 — many products possible)
4. **Date range** — uses `<DateRangePicker>` (built in Q5)

## Files
| File | Change |
|---|---|
| `services/api/app/routers/admin_web.py` | Extend `/v1/admin/inventory/movements` with `date_from`/`date_to` query params, filter on `StockMovement.created_at` |
| `apps/admin-web/src/app/(main)/inventory/page.tsx` | Add three new filter inputs + state + wire into existing fetchMovements URL |

## Backend
Add to `list_stock_movements`:
```python
date_from: str | None = Query(default=None)
date_to: str | None = Query(default=None)
```
Convert to UTC datetimes (start-of-day for `from`, end-of-day for `to`); filter `StockMovement.created_at`. Same pattern as Q5.

## Frontend
- Reuse existing `<Typeahead>` (Q6) for product picker — fetch `/api/ims/v1/admin/products` once on mount
- Reuse existing `<DateRangePicker>` (Q5) for date filter
- Reuse existing `<SelectInput>` for shop (already fetched in inventory page state — verify)
- All four filter values → URL search params on every fetch
- Filter changes invalidate the cached movement pages and reset to page 1

## Out of scope
Filter persistence in URL params (current filters are local React state — keeping that pattern).
