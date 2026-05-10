# Item 1 — Transfer Orders Implementation Spec

**Date:** 2026-05-11
**Effort:** 4-6 days

## Problem
Merchants with multiple shops (retail/hybrid tenants) need to move inventory between shops with a proper paper trail: who created it, who approved it, when it shipped, what was received vs what was sent. Today the `TransferOrder` and `TransferOrderLine` models exist as bare stubs — no API, no UI, no business logic.

## Locked decisions
- New `transfers:approve` permission gates approval.
- Tenant settings: `transfer_auto_approve_under_cents` (null = no auto-approve), `transfer_allow_self_approval` (bool, default false).
- Stock during `in_transit`: soft-deducted at source via a query against pending transfer quantities (no separate Reservation row needed — simpler). UI surfaces "X units committed to outgoing transfers".
- Destination confirms receipt per line with `quantity_received`. Partial receipts allowed.
- `unit_cost_at_transfer_cents` snapshotted on `TransferOrderLine` at approval time.

## Schema changes

### `tenants` (extend)
| Column | Type | Default | Notes |
|---|---|---|---|
| transfer_auto_approve_under_cents | Integer | NULL | When line-total < this, transfer auto-approves on submit |
| transfer_allow_self_approval | Boolean | false | When false, creator cannot approve their own transfer |

### `transfer_orders` (extend existing)
Add columns to the existing model:
| Column | Type | Notes |
|---|---|---|
| approved_by_user_id | UUID FK users SET NULL | nullable |
| approved_at | timestamptz | nullable |
| rejected_at | timestamptz | nullable |
| rejection_reason | Text | nullable |
| shipped_at | timestamptz | nullable |
| received_at | timestamptz | nullable |
| cancelled_at | timestamptz | nullable |
| notes | Text | nullable; merchant notes |

Status enum (string, not DB enum for flexibility): `draft | pending_approval | approved | in_transit | completed | rejected | cancelled`.

State transitions:
```
draft ──submit──> pending_approval ──approve──> approved ──ship──> in_transit ──receive──> completed
        │                  │                                                       ▲
        │                  └──reject──> rejected                                   │
        └──submit (auto-approved)──> approved ──────────────────────────────────────┘
draft|pending_approval|approved ──cancel──> cancelled
```

### `transfer_order_lines` (extend existing)
| Column | Type | Notes |
|---|---|---|
| unit_cost_at_transfer_cents | Integer | NULL until approved; snapshotted at approval from `Product.cost_price_cents` |
| line_notes | Text | optional per-line notes (e.g., damage on receipt) |

### Migration `20260530000001_transfer_orders.py`
Chain from `20260529000001`. Add the tenant columns + transfer_orders columns + transfer_order_lines columns. No data migration needed (existing transfer_orders rows from demo seed are stub-state).

## Business logic

### Soft-deduct calculation
"Available stock at shop S for product P" historically = `SUM(stock_movements.quantity_delta WHERE shop_id=S AND product_id=P)`.

After this work, when display-time stock is requested, also subtract:
```
SUM(line.quantity_requested - line.quantity_shipped) 
  FROM transfer_order_lines line
  JOIN transfer_orders t ON t.id = line.transfer_order_id
  WHERE t.from_shop_id = S AND line.product_id = P
    AND t.status IN ('approved', 'in_transit')
```

This is a NEW column in the response — `committed_to_transfers` — alongside `available` (which already gets reduced by storefront reservations). The merchant sees both. The `available` value used for new transfers + sales should be `physical - committed_to_transfers - reservations`.

Add helper `app/services/stock.py::get_committed_to_transfers(db, shop_id, product_id)` and integrate into stock-query call sites (admin stock view, inventory page).

### Cost snapshot on approval
On `approve()`, for each line, set `unit_cost_at_transfer_cents = Product.cost_price_cents` (current value at approval moment).

### Movement creation on receive
On `receive(quantity_received_by_line)`:
- For each line where `quantity_received > 0`:
  - Create `StockMovement(shop_id=from_shop, product_id, quantity_delta=-line.quantity_received, movement_type="transfer_out", reference_id=transfer.id)`
  - Create `StockMovement(shop_id=to_shop, product_id, quantity_delta=+line.quantity_received, movement_type="transfer_in", reference_id=transfer.id)`
  - Both movements use the line's `unit_cost_at_transfer_cents` for cost basis (new field on StockMovement? Or reference the line for cost?).

If `quantity_received < quantity_shipped`, the difference is a "loss in transit" — record as a separate StockMovement with `movement_type="transfer_loss"` on the source shop? OR just leave the source shop short and create an adjustment ticket. **Decision:** simplest is to skip the transfer_out for the unreceived qty (so source keeps the missing units on paper), and surface a warning that says "X units unaccounted for — create a manual adjustment". Don't auto-create a loss movement.

### Auto-approval
On submit (`draft → pending_approval`), if tenant has `transfer_auto_approve_under_cents` set AND the total line cost (sum of `quantity_requested * Product.cost_price_cents`) is below it, immediately transition to `approved` and snapshot costs. `approved_by_user_id` stays NULL with note "auto-approved".

### Self-approval guard
On approve, if `tenant.transfer_allow_self_approval = false` AND `approved_by_user_id == created_by_user_id`, reject with 403.

## API — `services/api/app/routers/admin_transfer_orders.py` (new)

All endpoints require `operations:read` or `operations:write` for general access; approval-specific endpoints require `transfers:approve`.

| Endpoint | Permission | Purpose |
|---|---|---|
| `GET /v1/admin/transfer-orders` | `operations:read` | List with filters: status, from_shop, to_shop, date range, q (id/notes search) |
| `POST /v1/admin/transfer-orders` | `operations:write` | Create as `draft` |
| `GET /v1/admin/transfer-orders/{id}` | `operations:read` | Full detail with lines, current stock at from_shop per line, history |
| `PATCH /v1/admin/transfer-orders/{id}` | `operations:write` | Update lines/notes; only allowed in `draft` |
| `POST /v1/admin/transfer-orders/{id}/submit` | `operations:write` | `draft → pending_approval` (or `approved` if auto-approves) |
| `POST /v1/admin/transfer-orders/{id}/approve` | `transfers:approve` | `pending_approval → approved`; snapshots costs |
| `POST /v1/admin/transfer-orders/{id}/reject` | `transfers:approve` | body: `{reason}`. `pending_approval → rejected` |
| `POST /v1/admin/transfer-orders/{id}/ship` | `operations:write` | body: `[{line_id, quantity_shipped}]`. `approved → in_transit` |
| `POST /v1/admin/transfer-orders/{id}/receive` | `operations:write` | body: `[{line_id, quantity_received}]`. `in_transit → completed`. Creates StockMovements. |
| `POST /v1/admin/transfer-orders/{id}/cancel` | `operations:write` | Only valid in `draft`/`pending_approval`/`approved` |

Validation:
- `from_shop_id != to_shop_id`
- All lines product_id belongs to tenant
- On ship: `quantity_shipped <= quantity_requested`
- On receive: `quantity_received <= quantity_shipped`
- On submit: at least one line, all line quantities > 0

## Permission registration
Add new permission `transfers:approve` to the seeded permissions list (find where Owner role gets seeded; should be in `provision_tenant.py` or a permissions migration). All existing Owner / Admin system roles get it automatically; Cashier doesn't.

## Admin UI — `apps/admin-web/src/app/(main)/transfer-orders/`

### Files
- `page.tsx` — list view with filters + status badges + "New transfer" button
- `[id]/page.tsx` — detail view showing all line items, status timeline, action buttons (Approve/Reject/Ship/Receive/Cancel) gated by status + permission

### List page
Columns: ID (short), From shop → To shop, Status badge, # lines, Total cost, Created by, Created at, Updated at.
Filters: status multi-select, from/to shop selects, date range, free-text q.

### Detail page
- Header: transfer ID, status badge, from → to with arrow
- Line items table: product, quantity_requested, quantity_shipped, quantity_received, unit_cost (post-approval), current source stock (live)
- Status timeline: who created, who approved, ship time, receive time
- Action area: status-dependent buttons. The receive UI is a form where the destination operator types `quantity_received` per line then clicks Confirm.

### Stock-soft-deduct UI surfacing
On `/inventory` and `/products/{id}` detail, add a "Committed to transfers" indicator next to the physical-stock number when > 0. Just the number + small tooltip "Pending outbound transfers".

### AppShell nav
Add "Transfer Orders" entry in the Stock nav group (under Inventory). `allowedTypes: ['retail', 'hybrid']` (online tenants don't have shops to transfer between). Permission: `operations:read`. Icon: Material Symbols `compare_arrows`.

## Cashier app
Out of scope. Cashiers don't initiate transfers in v1 — admin-web only.

## Files

| File | Status |
|---|---|
| `services/api/app/models/tables.py` | Extend Tenant, TransferOrder, TransferOrderLine |
| `services/api/alembic/versions/20260530000001_transfer_orders.py` | NEW migration |
| `services/api/app/services/transfer_orders.py` | NEW service (state transitions, auto-approve, cost snapshot, movements creation) |
| `services/api/app/services/stock.py` | Add `get_committed_to_transfers` (or extend existing stock query helper) |
| `services/api/app/routers/admin_transfer_orders.py` | NEW router |
| `services/api/app/main.py` | Register new router |
| `services/api/app/auth/seed_permissions.py` (or equivalent) | Add `transfers:approve` permission |
| `apps/admin-web/src/app/(main)/transfer-orders/page.tsx` | NEW list page |
| `apps/admin-web/src/app/(main)/transfer-orders/[id]/page.tsx` | NEW detail page |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Add nav entry |
| Admin Settings page | Add transfer auto-approve threshold + self-approval toggle inputs |

## Out of scope
- Cashier-app initiated transfers
- Transfer of variant-level stock (we transfer whole products only)
- Bulk import of transfer orders via CSV
- Cross-tenant transfers (impossible by design — RLS prevents)
- Auto-loss movement on under-receipt (merchant creates manual adjustment instead)
