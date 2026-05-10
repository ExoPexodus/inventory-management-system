# Q5 — Date Range Picker on Orders + E-comm Orders Design

**Date:** 2026-05-10
**Phase:** Audit Q5 (~1 day)

## Problem
- `/orders` already has `<DateInput>` from/to fields, but no preset buttons (Today / 7d / 30d).
- `/ecommerce-orders` has no date filter at all — neither UI nor backend support.

## Solution
1. Build a small reusable `<DateRangePicker>` component with preset buttons (Today, 7d, 30d, Custom) plus the existing from/to date inputs.
2. Use it on `/orders` (replaces today's two DateInputs).
3. Use it on `/ecommerce-orders` (new filter section).
4. Add `date_from` / `date_to` query params to the ecommerce-orders GET endpoint.

## Files
| File | Change |
|---|---|
| `services/api/app/routers/admin_ecommerce_orders.py` | Add `date_from`/`date_to` query params, filter `Order.placed_at` |
| `apps/admin-web/src/components/ui/DateRangePicker.tsx` | NEW — reusable component |
| `apps/admin-web/src/app/(main)/orders/page.tsx` | Replace existing DateInput pair with `<DateRangePicker>` |
| `apps/admin-web/src/app/(main)/ecommerce-orders/page.tsx` | Add `<DateRangePicker>` + send `date_from`/`date_to` query params |

## DateRangePicker shape
```tsx
<DateRangePicker
  from={dateFrom}
  to={dateTo}
  onChange={(from, to) => { setDateFrom(from); setDateTo(to); }}
/>
```

Preset buttons set both `from` and `to` to ISO date strings:
- **Today** → both = today
- **Last 7 days** → from = today - 7d, to = today
- **Last 30 days** → from = today - 30d, to = today
- **Custom** → reveals the two `<DateInput>` fields

## Backend
Extend `/v1/admin/ecommerce-orders` GET:
```python
date_from: str | None = Query(default=None)  # YYYY-MM-DD
date_to: str | None = Query(default=None)    # YYYY-MM-DD
```
Convert to UTC datetimes (start-of-day for `from`, end-of-day for `to`) and add to the SQLAlchemy `where()` filtering on `Order.placed_at`.
