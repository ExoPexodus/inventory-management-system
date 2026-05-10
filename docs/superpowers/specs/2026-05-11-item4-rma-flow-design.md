# Item 4 — RMA Flow Implementation Spec

**Date:** 2026-05-11
**Effort:** 7-10 days (largest of the four; cross-cutting payment + inventory + email + admin + storefront + cashier)

## Goal
Unified Return Merchandise Authorization system covering refund-only, return+refund, and exchange flows. Customer-initiated from storefront for ecommerce, cashier-initiated for POS. Merchant approves with line-level restock decisions, auto-refund executes on approval (cash sales mark manually), email sent at every status change.

## Locked decisions
- Refund types: refund-only, return+refund, exchange — all three.
- Restock: merchant decides per approval; tenant-level default (`default_restock_on_refund`).
- Return shipping: merchant toggle per approval; uses Shiprocket return-AWB when configured.
- Unified POS + ecommerce inbox.
- Auto-refund on approval (Stripe/Razorpay); cash sales mark "cash returned" manually.
- Structured reason taxonomy: `damaged | wrong_item | doesnt_fit | changed_mind | other` (with free-text note when `other`).
- Line-level granularity AND partial-quantity within a line.
- Configurable window: `refund_window_days` (default 30, per-tenant).
- Statuses: `requested → approved | rejected → received (sub-state for return+refund) → refunded → closed`. `cancelled` terminal from `requested`.
- Email at every status change.
- Customer can cancel before approval.
- Shipping cost refund: merchant decides per approval (toggle on approve dialog).
- Tax refund: merchant adjusts manually (no auto-proportional).
- POS cashier app: gets its own initiate-refund screen.
- Auto-approve threshold per tenant: `rma_auto_approve_under_cents`.
- Customer-facing: SDK methods (no demo page — there's no storefront demo app to host one).
- Cash sales CAN use RMA; auto-refund step skipped, manual "cash returned" close step.

## Schema

### `tenants` (extend)
| Column | Type | Default | Notes |
|---|---|---|---|
| default_restock_on_refund | Boolean | true | Default toggle when merchant approves |
| refund_window_days | Integer | 30 | Customer cannot request after delivery + N days |
| rma_auto_approve_under_cents | Integer | NULL | If line-total < this, approves on submit |

### `refund_requests` (new)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK | RLS |
| order_id | UUID FK orders SET NULL | nullable for POS sales (uses sale_transaction_id instead) |
| sale_transaction_id | UUID FK transactions SET NULL | nullable for ecommerce orders |
| channel_id | UUID FK channels SET NULL | for ecommerce; null for POS |
| customer_id | UUID FK customers SET NULL | nullable |
| customer_email | String(255) | cached for POS sales without customer_id |
| customer_name | String(255) | cached |
| refund_type | String(16) | `refund_only | return_refund | exchange` |
| status | String(16) | `requested | approved | rejected | received | refunded | closed | cancelled` |
| reason_code | String(32) | `damaged | wrong_item | doesnt_fit | changed_mind | other` |
| reason_note | Text | required when reason_code = "other" |
| refund_shipping | Boolean | merchant-set on approval; default false |
| return_shipping_required | Boolean | depends on refund_type |
| return_shipping_awb | String(128) | populated when Shiprocket return-AWB issued |
| approved_by_user_id | UUID FK users SET NULL | nullable |
| approved_at | timestamptz | nullable |
| rejected_reason | Text | nullable |
| rejected_at | timestamptz | nullable |
| cancelled_at | timestamptz | nullable |
| received_at | timestamptz | nullable; for return+refund flow |
| refunded_at | timestamptz | nullable |
| closed_at | timestamptz | nullable |
| total_refund_cents | Integer default 0 | sum of approved line refund amounts (incl. shipping if refund_shipping) |
| currency_code | String(3) | from order/transaction |
| provider_refund_ref | String(255) | Stripe refund_id / Razorpay refund_id |
| cash_returned | Boolean default false | for cash payment path |
| cash_returned_at | timestamptz | when merchant clicked "Mark cash returned" |
| auto_approved | Boolean default false | true when below threshold |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### `refund_request_lines` (new)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| refund_request_id | UUID FK CASCADE | |
| order_line_id | UUID FK order_lines SET NULL | nullable for POS |
| transaction_line_id | UUID FK transaction_lines SET NULL | nullable for ecommerce |
| product_id | UUID FK | |
| product_name | String(255) | snapshot |
| product_sku | String(64) | snapshot |
| quantity_requested | Integer | customer-requested quantity to refund |
| quantity_approved | Integer default 0 | merchant-set on approval |
| unit_price_cents | Integer | snapshot |
| restock_on_approval | Boolean | merchant-set on approval; defaults to tenant.default_restock_on_refund |
| line_refund_cents | Integer default 0 | quantity_approved × unit_price (set on approval) |
| exchange_for_product_id | UUID FK products SET NULL | nullable; for `exchange` type |
| created_at | timestamptz | |

### `refund_request_events` (new — audit/timeline)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK | |
| refund_request_id | UUID FK CASCADE | |
| event_type | String(32) | `created, status_changed, comment, email_sent, refund_executed, awb_issued, ...` |
| from_status | String(16) | nullable |
| to_status | String(16) | nullable |
| actor_user_id | UUID FK users SET NULL | nullable (null = customer/system) |
| actor_kind | String(16) | `customer | merchant | system` |
| metadata | JSONB | nullable; structured details (e.g., provider response) |
| created_at | timestamptz | |

### Migration `20260602000001_rma_flow.py`
Chain from latest IMS head `20260601000001`. Creates 3 tables + extends tenants with the 3 RMA settings.

## State machine

```
requested ─approve─> approved ─execute_refund(card)─> refunded ─close─> closed
   │           ├─reject──> rejected ─close──> closed
   │           ├─cancel (by customer)──> cancelled
   │           └─wait_for_return (return+refund) ──> received ─execute_refund──> refunded
   │
   └─auto_approve (if under threshold)──> approved (same downstream paths)
```

For cash sales: `approved` → manually `Mark cash returned` → `refunded` → `closed`.

For exchange type: refund is $0 (or partial top-up amount); approved means "send replacement"; status moves to `closed` after replacement is shipped (separately tracked via existing fulfillment system — out of scope here, future enhancement).

## Service — `services/api/app/services/rma_service.py` (NEW)

Functions:
```python
def create_refund_request(db, *, tenant_id, order=None, sale_transaction=None, refund_type, reason_code, reason_note=None, lines: list[CreateLineInput], customer_id=None, customer_email=None, customer_name=None) -> RefundRequest:
    # validates window (order delivery_at + refund_window_days >= now)
    # creates refund_request + lines (status=requested)
    # writes "created" event
    # if tenant.rma_auto_approve_under_cents and total < threshold: auto-approve (recurse into approve_refund_request)
    # sends "rma_received" email

def approve_refund_request(db, *, request, approving_user_id, line_approvals: dict[UUID, ApprovalInput], refund_shipping: bool):
    # for each line: set quantity_approved, restock_on_approval, line_refund_cents
    # compute total_refund_cents (sum of line_refund_cents + shipping if refund_shipping)
    # transition status: approved (or directly to received/refunded based on refund_type)
    # for refund_only: trigger execute_refund immediately
    # for return_refund: status → approved (waits for received)
    # for exchange: status → approved (separately tracked)
    # writes event + sends email

def reject_refund_request(db, *, request, rejecting_user_id, reason: str)
    # status → rejected
    # writes event + sends email

def cancel_refund_request(db, *, request, by_customer=False)
    # only valid from status=requested
    # status → cancelled
    # writes event + sends email

def mark_received(db, *, request, receiving_user_id)
    # only valid for return_refund type, status=approved
    # status → received
    # restock per-line if line.restock_on_approval (creates StockMovement transfer_in to first fulfillment shop)
    # then triggers execute_refund

def execute_refund(db, *, request)
    # determines payment provider from OrderPayment / Transaction
    # for stripe: stripe.Refund.create(payment_intent=..., amount=...)
    # for razorpay: razorpay refunds.create
    # for cash: skip (sets a flag waiting_cash_return)
    # for other (already refunded out-of-band): just mark refunded
    # status → refunded
    # provider_refund_ref stored
    # OrderRefund row created (reuses existing OrderRefund infrastructure)
    # writes event + sends email

def mark_cash_returned(db, *, request, user_id)
    # cash payment path; flips cash_returned=True
    # status → refunded
    # writes event

def close_refund_request(db, *, request)
    # any refunded status can be closed (closing is a final ack — no auto-action)
    # status → closed
```

## API — admin

New router `services/api/app/routers/admin_rma.py`:
```
GET    /v1/admin/rma                         → list/inbox (filters: status, channel, date_range, customer_email, q)
GET    /v1/admin/rma/{id}                    → detail with events
POST   /v1/admin/rma/{id}/approve            → body: {line_approvals: [{line_id, quantity_approved, restock?}], refund_shipping: bool}
POST   /v1/admin/rma/{id}/reject             → body: {reason}
POST   /v1/admin/rma/{id}/mark-received      → for return+refund
POST   /v1/admin/rma/{id}/mark-cash-returned → cash payment path
POST   /v1/admin/rma/{id}/close              → final ack
POST   /v1/admin/rma/{id}/issue-return-awb   → Shiprocket return-AWB
GET    /v1/admin/rma/{id}/events             → timeline
POST   /v1/admin/rma                         → admin-initiated (e.g., on behalf of a phone-in customer)
```

Permission: new `rma:read` + `rma:write` permissions. Seed onto owner role via the same migration.

Settings endpoints (extend admin_platform.py or add admin_rma_settings.py):
```
GET  /v1/admin/tenant-settings/rma
PATCH /v1/admin/tenant-settings/rma
```

## API — storefront (customer)

New router `services/api/app/routers/storefront/rma.py`:
```
POST   /v1/storefront/refund-requests              → create (customer-auth required)
GET    /v1/storefront/refund-requests              → list mine
GET    /v1/storefront/refund-requests/{id}         → mine only
POST   /v1/storefront/refund-requests/{id}/cancel  → cancel (only in `requested` status)
```

Auth: customer JWT (existing).

## API — cashier

New router `services/api/app/routers/cashier_rma.py` (or extend existing cashier router):
```
POST   /v1/cashier/refund-requests   → cashier-initiated against a transaction
```

Auth: device JWT (existing). Permission via the user assigned to the device.

## Payment provider integration

New helper `services/api/app/services/payment_refund.py`:
```python
def execute_provider_refund(db, *, order: Order | None, transaction: Transaction | None, amount_cents: int) -> dict:
    """Returns {provider_ref, status: 'completed'|'pending'|'failed'|'manual_cash'}.
    Looks up channel.config for stripe_secret_key / razorpay_key_secret (already encrypted).
    Calls Stripe Refund API or Razorpay refunds API.
    For cash payments, returns ('manual_cash', None) and the caller marks status accordingly.
    """
```

Uses existing `decrypt_secret` from `email_service.py` to retrieve keys.

## Email

4 new templates in `services/api/email_templates/`:
- `rma_received.html` — "We received your refund request"
- `rma_approved.html` — "Your refund has been approved"
- `rma_rejected.html` — "Your refund request was declined"
- `rma_refunded.html` — "Your refund has been processed"

Use existing email_service.py send mechanism with TenantEmailConfig.

## Shiprocket return-AWB

When merchant clicks "Issue return AWB" on an approved return+refund request:
- Call existing Shiprocket provider with reverse-shipment payload
- Store the AWB on `refund_request.return_shipping_awb`
- Email customer with the AWB + pickup details

## Storefront SDK

Add to `packages/storefront-sdk/src/client.ts`:
```typescript
async requestRefund(input: RefundRequestInput): Promise<RefundRequest>
async listRefundRequests(): Promise<RefundRequest[]>
async getRefundRequest(id: string): Promise<RefundRequest>
async cancelRefundRequest(id: string): Promise<RefundRequest>
```

Types in `packages/storefront-sdk/src/types.ts`:
- `RefundRequestInput` (order_id, refund_type, reason_code, reason_note?, lines: [{order_line_id, quantity_requested, exchange_for_product_id?}])
- `RefundRequest` (full response shape)
- `RefundRequestLine`

## Admin UI

### `apps/admin-web/src/app/(main)/rma/page.tsx` — inbox
- Filter chips: status, channel, date range, customer email/name search
- Table: ID, customer, refund_type, total_amount, status badge, created
- "New RMA" button (admin-initiated)
- Pagination

### `apps/admin-web/src/app/(main)/rma/[id]/page.tsx` — detail
- Header: ID, customer, original order link, status badge, total
- Lines table with quantity_requested + approval input (quantity_approved) per line, restock checkbox per line, line-refund-amount
- Refund shipping toggle (with current shipping_cents shown for reference)
- Status-dependent action buttons:
  - `requested`: Approve / Reject / Cancel
  - `approved` (return_refund): Mark received / Issue return AWB
  - `approved` (refund_only): Execute refund (auto-fired) — show provider response
  - `approved` (cash): Mark cash returned
  - `received`: Execute refund (auto on transition)
  - `refunded`: Close
  - All: Add comment (writes event)
- Timeline column showing all events chronologically

### `apps/admin-web/src/app/(main)/settings/rma/page.tsx` — settings
- `default_restock_on_refund` toggle
- `refund_window_days` number input
- `rma_auto_approve_under_cents` currency input

### AppShell nav
- "Refunds" entry in Sales group (where Orders lives). Icon: `keyboard_return` or `move_down`. Permission: `rma:read`. allowedTypes: all.

## Cashier UI

New screen in `apps/cashier/lib/`:
- "Refund" entry on the main menu
- Sale lookup (by transaction ID or customer phone)
- Pick lines + quantities to refund
- Pick reason from dropdown
- Submit → creates a refund_request via `POST /v1/cashier/refund-requests`
- Shows status on a follow-up screen

Out of scope: full cashier-side detail view; just submission flow + a "Refund history" screen showing the cashier's recent submissions.

## Files

| File | Status |
|---|---|
| Backend | |
| `services/api/alembic/versions/20260602000001_rma_flow.py` | NEW migration (3 tables + tenant cols + 2 permissions) |
| `services/api/app/models/tables.py` | Add RefundRequest, RefundRequestLine, RefundRequestEvent; extend Tenant |
| `services/api/app/models/__init__.py` | Export new models |
| `services/api/app/services/rma_service.py` | NEW state machine service |
| `services/api/app/services/payment_refund.py` | NEW provider abstraction |
| `services/api/app/routers/admin_rma.py` | NEW admin endpoints |
| `services/api/app/routers/storefront/rma.py` | NEW storefront endpoints |
| `services/api/app/routers/cashier_rma.py` | NEW cashier endpoint |
| `services/api/app/main.py` | Register routers |
| `services/api/email_templates/rma_*.html` | 4 NEW templates |
| `services/api/app/routers/admin_platform.py` | Add RMA settings endpoints |
| Frontend (admin-web) | |
| `apps/admin-web/src/app/(main)/rma/page.tsx` | NEW inbox |
| `apps/admin-web/src/app/(main)/rma/[id]/page.tsx` | NEW detail |
| `apps/admin-web/src/app/(main)/settings/rma/page.tsx` | NEW settings |
| `apps/admin-web/src/app/(main)/settings/page.tsx` | Add RMA settings card |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Add Refunds nav |
| Frontend (cashier) | |
| `apps/cashier/lib/screens/refund_create_screen.dart` (or similar) | NEW Flutter screen |
| `apps/cashier/lib/screens/refund_history_screen.dart` | NEW Flutter screen |
| Frontend (cashier menu entry / routing wiring) | |
| SDK | |
| `packages/storefront-sdk/src/types.ts` | Add RefundRequest types |
| `packages/storefront-sdk/src/client.ts` | Add 4 SDK methods |

## Out of scope
- Exchange fulfillment automation (manual for v1)
- Refund disputes (Stripe chargeback flow)
- Multi-party refunds (split across multiple payment methods on one order)
- Audit log automatic export
- Refund analytics dashboard
- Storefront demo app (none exists)
