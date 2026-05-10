# Q6 — Type-ahead Supplier Search Design

**Date:** 2026-05-10
**Phase:** Audit Q6 (~3 hour quick win)

## Problem
The Purchase Order create form uses a static `<SelectInput>` for picking a supplier. With many suppliers, this is a long scroll list — friction for tenants with 50+ suppliers.

## Solution
Build a small reusable `<Typeahead>` component and use it for the supplier picker. Type to filter, click to select, arrow keys to navigate.

## Component shape
```ts
<Typeahead
  value={supplierId}
  onChange={setSupplierId}
  options={[{ value, label }]}
  placeholder="Search suppliers..."
/>
```

Visual: text input that displays the selected option's label. On focus, shows a dropdown of filtered options. Filter is case-insensitive substring match on label.

## Behaviour
- Click input → dropdown opens with all options
- Type → filter options live by `label` substring match
- Arrow up/down → navigate options
- Enter → select highlighted option
- Esc / click outside → close without selecting
- Selected option's label appears in the input

## Files
| File | Change |
|---|---|
| `apps/admin-web/src/components/ui/Typeahead.tsx` | NEW — reusable component |
| `apps/admin-web/src/app/(main)/purchase-orders/page.tsx` | Swap supplier `<SelectInput>` → `<Typeahead>` |

## Out of scope
- Product line dropdown on PO (would benefit from same typeahead, but tracked separately)
- Server-side search (client-side filter is sufficient for typical supplier counts)
