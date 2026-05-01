# Domain 1 — Customer Management (CRM)

**Date:** 2026-05-01
**Author:** Rushil Rana
**Status:** Approved

## Context

No `Customer` model exists anywhere in the codebase. Transactions are fully anonymous — the only human reference on a `Transaction` is `user_id` (the cashier). This spec builds the full CRM foundation: customer profiles, configurable groups, purchase history, POS attachment, and post-sale admin linking. It is explicitly Chunk 1 because it is the keystone that unlocks Khata (Domain 26), Returns tied to a customer (Domain 2), WhatsApp receipts (Domain 25), and Loyalty (Domain 7).

## What Is Already Built

- `Transaction` model: `tenant_id`, `shop_id`, `device_id`, `user_id`, `kind`, `status`, `total_cents`, `tax_cents`, `client_mutation_id`, `created_at`. No customer fields.
- `sync_push.py::apply_sale_completed` — creates Transaction from a device `sale_completed` event. No customer data extracted or stored.
- Admin orders page (`/orders`) — shows transactions by cashier/timestamp. No customer column.
- Device auth (`typ=device`) for cashier endpoints; operator auth (`typ=operator`) for admin endpoints.
- Permissions: `catalog:read/write`, `inventory:read/write`, `analytics:read`, `settings:read/write`, `shops:read/write`. No customer permissions yet.

---

## Design

### 1. Data Model — 2 new tables + 2 new columns on transactions

#### `customer_groups`

```python
class CustomerGroup(Base):
    __tablename__ = "customer_groups"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_customer_group_tenant_name"),)

    id:         UUID, PK
    tenant_id:  UUID, FK tenants(CASCADE)
    name:       String(100), NOT NULL          # e.g. "VIP", "Regular", "Staff"
    colour:     String(7), nullable            # hex e.g. "#7C3AED" — used for badge in UI
    created_at: DateTime(timezone=True)
```

No system defaults. Each tenant creates groups that match their business vocabulary.

#### `customers`

```python
class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "phone", name="uq_customer_tenant_phone"),)

    id:            UUID, PK
    tenant_id:     UUID, FK tenants(CASCADE)
    group_id:      UUID, FK customer_groups(SET NULL), nullable
    phone:         String(20), NOT NULL        # required — primary lookup key
    name:          String(255), nullable       # optional at creation
    email:         String(255), nullable
    address_line1: String(255), nullable
    city:          String(128), nullable
    notes:         Text, nullable
    created_at:    DateTime(timezone=True)
    updated_at:    DateTime(timezone=True), onupdate=func.now()
```

`(tenant_id, phone)` unique constraint: one customer record per phone per tenant.

#### `transactions` table — 2 new columns

- `customer_id: UUID, FK customers(SET NULL), nullable` — resolved customer link
- `customer_phone: String(20), nullable` — raw offline-captured phone (unresolved)

`customer_id` and `customer_phone` are mutually exclusive in practice:
- Once resolved, `customer_id` is set and `customer_phone` is cleared
- Unresolved (offline capture where phone has no match): `customer_phone` set, `customer_id` null

### 2. New Permissions

Two new permission codenames added via migration seed:
- `customers:read`
- `customers:write`

These are seeded as `Permission` records in the migration and granted to the system `admin` role automatically (same pattern as existing permissions). Tenant operator roles inherit from the admin role.

### 3. Sync Protocol — `sale_completed` event extensions

The cashier `sale_completed` event gains three optional fields:

```json
{
  "customer_id":    "uuid-string | null",
  "customer_phone": "9876543210 | null",
  "customer_name":  "Rajesh Kumar | null"
}
```

**Server resolution in `apply_sale_completed`:**

1. Extract `customer_id`, `customer_phone`, `customer_name` from event (all default to `None`).
2. If `customer_id` provided → validate it belongs to `tenant_id` → set `txn.customer_id = customer_id`.
3. Elif `customer_phone` provided:
   a. Look up `Customer` by `(tenant_id, phone)`.
   b. If found → set `txn.customer_id = customer.id` (online resolution complete).
   c. If not found AND `customer_name` provided → create a new `Customer(tenant_id, phone, name)` → set `txn.customer_id`.
   d. If not found AND no name → set `txn.customer_phone = customer_phone` (unlinked; visible in admin for manual resolution).
4. If none provided → transaction is anonymous.

This preserves the offline-first architecture: the cashier never needs a separate "create customer" HTTP call. A new customer with a name typed at POS is created server-side when the transaction syncs.

**OpenAPI spec update:** Add `customer_id`, `customer_phone`, `customer_name` as optional fields to the `SaleCompletedEvent` schema in `packages/sync-protocol/openapi.yaml`.

### 4. Customer lookup endpoint (device auth)

Cashiers need to search for existing customers before a sale. Since cashiers use device JWT (not operator JWT), a dedicated device-auth endpoint is required:

```
GET /v1/sync/customers/lookup?q=<phone_or_name>
```

- Auth: device JWT (`typ=device`), scoped to `tenant_id`
- Query `q`: searched against `phone` (prefix match) and `name` (ilike)
- Returns: up to 10 matching customers `[{id, phone, name, group_name}]`
- Read-only — no write operations from device auth

This endpoint lives in `services/api/app/routers/sync.py` (same file as `/v1/sync/pull`).

### 5. Admin API — new router `admin_customers.py`

Prefix: `/v1/admin/customers`

```
GET    /v1/admin/customers               customers:read   list, search (q= phone/name), cursor-paginated
POST   /v1/admin/customers               customers:write  create (phone required, all else optional)
GET    /v1/admin/customers/lookup        customers:read   phone/name lookup — for admin web search
GET    /v1/admin/customers/{id}          customers:read   profile + last 50 transactions
PATCH  /v1/admin/customers/{id}          customers:write  update any field
DELETE /v1/admin/customers/{id}          customers:write  hard delete (FK cascade nullifies transaction.customer_id)

GET    /v1/admin/customer-groups         customers:read   list groups for tenant
POST   /v1/admin/customer-groups         customers:write  create group
PATCH  /v1/admin/customer-groups/{id}    customers:write  rename / change colour
DELETE /v1/admin/customer-groups/{id}    customers:write  delete (nullifies customer.group_id)
```

**Transaction attachment** — added to existing `admin_web.py`:

```
PATCH /v1/admin/transactions/{id}/customer
Body: { "customer_id": "uuid | null" }
Permission: customers:write
```

Attaches or detaches a customer from a transaction post-sale. When attaching, clears `customer_phone` and sets `customer_id`. When detaching (null), clears both.

### 6. Response shapes

**`CustomerGroupOut`**
```python
{ id, tenant_id, name, colour, created_at }
```

**`CustomerOut`** (list view)
```python
{ id, tenant_id, group_id, group_name, phone, name, email, city, created_at }
```

**`CustomerDetailOut`** (profile view)
```python
{ id, tenant_id, group_id, group_name, phone, name, email,
  address_line1, city, notes, created_at, updated_at,
  transactions: [{ id, created_at, shop_name, total_cents, status }]  # last 50
}
```

**`TransactionOut` additions** (in existing `transactions.py` response):
```python
{ ..., customer_id, customer_name, customer_phone }
```

### 7. Admin web — new pages + existing page updates

**New: `/customers` page**
- Searchable list (combined phone + name search field)
- Group filter dropdown
- Columns: Name, Phone, Group (coloured badge), City, Last visit, Total spend
- "New customer" button → opens create modal
- Row click → navigates to `/customers/[id]`

**New: Customer create/edit modal**
- Phone (required), Name (optional), Email (optional), City (optional), Group (dropdown from tenant groups), Notes (optional)
- Follows the same modal pattern as `EditProductDialog` in `products/page.tsx`

**New: `/customers/[id]` profile page**
- Details card (all profile fields + Edit button)
- Purchase history table (last 50 transactions: date, shop, items summary, total, status)
- Group badge

**Modified: `/orders` page**
- New "Customer" column: shows `customer_name` / `customer_phone` / "—"
- "Attach customer" action on rows where `customer_id` is null — opens a phone/name search modal that calls `GET /v1/admin/customers/lookup`

**Modified: `/settings` page**
- New "Customer Groups" section: list current groups + create/edit/delete inline

### 8. Flutter cashier — customer attachment at POS

**New widget: `CustomerPickerWidget`** (`apps/cashier/lib/widgets/customer_picker_widget.dart`)

- Lives in the cart/checkout screen, collapsed by default
- Collapsed state: "Add customer" button
- Expanded: single text field accepting phone or name
- On type (debounced 400ms): calls `GET /v1/sync/customers/lookup?q=<input>`
- Result list: each row shows name + phone; tap to select
- "New customer" row at bottom: reveals optional name field; on confirm, stores `(phone, name)` in `CartModel` — server will create the Customer on sync if not found

**`CartModel` additions:**
```dart
String? customerId;
String? customerPhone;
String? customerName;

void setCustomer({ String? id, String? phone, String? name });
void clearCustomer();
String? get customerDisplayLabel; // "Rajesh Kumar" or "+91 9876543210" or null
```

**`sale_completed` event updated:**
```dart
if (cart.customerId != null) {
  event['customer_id'] = cart.customerId;
} else if (cart.customerPhone != null) {
  event['customer_phone'] = cart.customerPhone;
  if (cart.customerName != null) event['customer_name'] = cart.customerName;
}
```

### 9. Migration structure

One Alembic migration (`20260501000001_crm_customer_model.py`):
1. Create `customer_groups` table
2. Create `customers` table
3. Add `customer_id` (nullable FK) and `customer_phone` (nullable String) to `transactions`
4. Seed `customers:read` and `customers:write` into the `permissions` table
5. Seed `customers:read` and `customers:write` `Permission` records; grant `customers:read` to all roles that already have `catalog:read`; grant `customers:write` to all roles that already have `catalog:write`

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `services/api/alembic/versions/20260501000001_crm_customer_model.py` | Create | Migration: 2 new tables, 2 new transaction columns, permission seeds |
| `services/api/app/models/tables.py` | Modify | `CustomerGroup`, `Customer` models; `Transaction.customer_id`, `Transaction.customer_phone` |
| `services/api/app/routers/admin_customers.py` | Create | Full customer + customer-group CRUD |
| `services/api/app/routers/admin_web.py` | Modify | `PATCH /v1/admin/transactions/{id}/customer` endpoint; `TransactionOut` gains customer fields |
| `services/api/app/routers/sync.py` | Modify | `GET /v1/sync/customers/lookup` endpoint |
| `services/api/app/services/sync_push.py` | Modify | `apply_sale_completed` customer resolution logic |
| `services/api/app/main.py` | Modify | Register `admin_customers` router |
| `packages/sync-protocol/openapi.yaml` | Modify | `SaleCompletedEvent` + customer lookup response schema |
| `apps/admin-web/src/app/(main)/customers/page.tsx` | Create | Customer list page |
| `apps/admin-web/src/app/(main)/customers/[id]/page.tsx` | Create | Customer profile page |
| `apps/admin-web/src/app/(main)/orders/page.tsx` | Modify | Customer column + attach action |
| `apps/admin-web/src/app/(main)/settings/page.tsx` | Modify | Customer groups card |
| `apps/cashier/lib/widgets/customer_picker_widget.dart` | Create | Customer search/select widget |
| `apps/cashier/lib/models/cart_model.dart` | Modify | `customerId`, `customerPhone`, `customerName` fields + helpers |
| `apps/cashier/lib/services/inventory_api.dart` | Modify | `customerLookup()` API method |

---

## Testing

**Contract tests (no DB):**
- `test_customer_out_schema` — CustomerOut and CustomerDetailOut serialise correctly
- `test_customer_group_out_schema` — CustomerGroupOut serialises correctly
- `test_sale_completed_customer_resolution` — all 4 resolution paths (customer_id, phone+found, phone+name+notfound, anonymous)

**Key invariants:**
- `(tenant_id, phone)` is unique — duplicate phone returns 409
- `customer_id` on Transaction must belong to the same `tenant_id` — cross-tenant attach returns 403
- Deleting a CustomerGroup nullifies `customer.group_id`, never deletes customers
- Deleting a Customer sets `transaction.customer_id = NULL` (CASCADE SET NULL)

---

## Out of Scope (Chunk 2+)

- Khata / credit balance on customer (Domain 26) — requires this CRM first
- Loyalty points (Domain 7) — requires this CRM first
- WhatsApp receipt delivery to customer phone (Domain 25) — requires this CRM first
- Customer birthday field + visit frequency analytics (Domain 46)
- At-risk customer dashboard (Domain 46)
- Store credit / customer wallet (Domain 1 Chunk 2)
- Customer CSV import
