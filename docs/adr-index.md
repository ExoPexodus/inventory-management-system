# ADR Index

This file tracks architecture decisions and their implementation status.

## How to use

- Add one ADR entry per major decision.
- Keep status explicit: `proposed`, `accepted`, `superseded`, `deprecated`.
- Link to implementation files and migration references when available.

## ADR list

### ADR-001: Offline-first ledger as source of truth

- Status: accepted
- Decision:
  - Use immutable stock movement and transaction ledger records.
  - Treat derived stock as computed view, not source of truth.
- Implemented in:
  - `services/api/app/models/tables.py`
  - `services/api/app/services/sync_push.py`

### ADR-002: Modular monolith backend boundaries

- Status: accepted
- Decision:
  - Keep one FastAPI deployment unit while organizing by bounded capability routers/services.
- Implemented in:
  - `services/api/app/main.py`
  - `services/api/app/routers/*`

### ADR-003: Tenant isolation via RLS + context

- Status: accepted
- Decision:
  - Enforce tenant isolation at DB policy layer and request context.
- Implemented in:
  - Alembic RLS migrations
  - `services/api/app/db/rls.py`

### ADR-004: Tenant-level currency metadata

- Status: accepted
- Decision:
  - Keep integer minor units in ledger; add tenant currency semantics for display/meaning.
  - No FX/multi-currency in v1.
- Implemented in:
  - `services/api/app/models/tables.py`
  - tenant currency migration
  - `services/api/app/routers/sync.py`
  - `apps/cashier` money formatter usage

### ADR-005: Card tender requires connectivity (v1)

- Status: accepted
- Decision:
  - Allow offline queue for cash; require online submission for card by default.
- Implemented in:
  - `apps/cashier/lib/screens/cart_screen.dart`
  - `services/api/app/services/sync_push.py`

### ADR-006: Optional product groups for variant UX

- Status: accepted
- Decision:
  - Keep the sellable unit as `products.id` (ledger lines and stock movements unchanged).
  - Add optional `product_groups` and nullable `product_group_id` + `variant_label` on `products` for merchandising and cashier grouping only.
- Implemented in:
  - `services/api/app/models/tables.py`
  - `services/api/alembic/versions/20260326120000_product_groups.py`
  - `services/api/app/routers/sync.py`, `services/api/app/routers/admin_web.py`

## Next ADR candidates

- Advanced RBAC model (role matrix and claims)
- Returns/refunds workflow shape and invariants
- Transfer workflows across shops/warehouse
- Gateway abstraction and PCI-safe card integration strategy

