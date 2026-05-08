# IMS Platform Architecture

Full architecture reference for the Inventory Management System — a multi-tenant, offline-first POS and e-commerce backend.

**Related docs:**
- `docs/ecommerce-architecture.md` — Deep dive on channels, storefront, checkout, webhooks
- `docs/storefront-api.md` — Guide for headless storefront developers
- `docs/sync-architecture.md` — Cashier offline sync and conflict semantics
- `docs/client-architecture.md` — Flutter (cashier/mobile) and admin web internals
- `docs/adr-index.md` — Architecture decisions and rationale

---

## 1. System overview

The platform serves two distinct roles simultaneously:

1. **POS backend** — Offline-first cashier sync, immutable stock ledger, multi-shop inventory
2. **E-commerce backend** — Multi-channel storefronts, hosted checkout, webhooks, customer portal

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                             │
│                                                             │
│  Cashier (Flutter)   Admin Web (Next.js)   Storefronts      │
│  Admin Mobile (Flutter)  Platform Web      (custom / SDK)   │
└───────────┬──────────────────┬─────────────────┬───────────┘
            │ device JWT        │ operator JWT     │ channel ID
            ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Monolith                        │
│                   services/api/app/main.py                  │
│                                                             │
│  /v1/sync/*        /v1/admin/*        /v1/storefront/*      │
│  /v1/devices/*     /v1/checkout/*     /v1/internal/*        │
└──────────┬───────────────────┬────────────────────┬─────────┘
           │                   │                    │
     ┌─────▼──────┐    ┌───────▼──────┐    ┌───────▼──────┐
     │ PostgreSQL  │    │    Redis     │    │  RQ Worker   │
     │ + RLS       │    │  (cache +    │    │ (email, wh,  │
     │             │    │   queue)     │    │  reservations)│
     └─────────────┘    └──────────────┘    └──────────────┘
```

---

## 2. Repository layout

```
inventory-management-system/
├── services/
│   └── api/                    # FastAPI backend
│       ├── app/
│       │   ├── main.py         # Router composition
│       │   ├── models/         # SQLAlchemy models
│       │   ├── routers/        # HTTP handlers by domain
│       │   ├── services/       # Business logic
│       │   ├── billing/        # Entitlements, feature flags
│       │   ├── auth/           # JWT + deps
│       │   ├── db/             # Session, RLS
│       │   └── worker/         # RQ tasks
│       ├── alembic/            # Database migrations
│       ├── email_templates/    # Jinja2 HTML email templates
│       └── templates/          # Jinja2 HTML (checkout page)
├── apps/
│   ├── admin-web/              # Next.js 15 merchant dashboard
│   ├── cashier/                # Flutter POS app
│   ├── admin_mobile/           # Flutter admin companion
│   └── platform-web/           # Next.js 15 platform operator dashboard
└── packages/
    ├── sync-protocol/          # OpenAPI contract (backend ↔ cashier)
    └── storefront-sdk/         # TypeScript SDK for headless storefronts
```

---

## 3. Backend — domain boundaries

The API is one FastAPI application assembled in `main.py`. Domains are separated by router + service modules, not by deployment boundary.

### 3.1 Router groups

| Prefix | File(s) | Auth | Purpose |
|--------|---------|------|---------|
| `/health` | `health.py` | None | Liveness probe |
| `/v1/devices/*` | `devices.py` | — | Device enrolment and token refresh |
| `/v1/sync/*` | `sync.py` | Device JWT | Pull/push sync for cashier |
| `/v1/transactions` | `transactions.py` | Device JWT | Transaction history (device view) |
| `/v1/admin/*` | `admin_*.py` (30+ files) | Operator JWT / X-Admin-Token | All merchant admin operations |
| `/v1/storefront/*` | `routers/storefront/` | Channel ID header | Public storefront API |
| `/checkout/*` | `checkout.py` | None | Hosted checkout pages + completion |
| `/v1/internal/*` | `internal_*.py` | X-Admin-Token | Platform service integration |
| `/v1/webhooks/*` | `webhooks_shopify.py`, `webhooks_woocommerce.py` | HMAC | Inbound platform webhooks |

### 3.2 Core domain models

```
tenants ─────┬─── shops ──────── stock_movements (immutable ledger)
             │                         │
             ├─── channels ────── inventory_pools ─── inventory_pool_shops
             │       │
             │       ├── channel_product_mappings (Shopify/WooCommerce IDs)
             │       └── checkout_sessions
             │
             ├─── products ───────── product_variants
             │       │               product_prices (multi-currency)
             │       └── product_images
             │
             ├─── orders ─────────── order_lines
             │       │               order_payments
             │       └── order_refunds
             │
             ├─── customers ──────── storefront_otps
             │
             ├─── discounts ──────── discount_uses
             ├─── shipping_zones ─── shipping_rates
             ├─── tax_regions ────── tax_rules
             ├─── fx_rates
             ├─── cart_items
             ├─── stock_reservations
             ├─── webhook_endpoints ─ webhook_delivery_logs
             └─── tenant_email_configs
```

### 3.3 Immutable stock ledger

**Stock is never stored as a mutable number.** Available stock is computed from the sum of `stock_movements.quantity_delta` rows. This makes every inventory change fully auditable.

```python
# Wrong — never do this:
product.stock_quantity -= sold_qty

# Right — always create a movement:
db.add(StockMovement(
    tenant_id=..., shop_id=..., product_id=...,
    quantity_delta=-sold_qty,
    movement_type="sale",
    idempotency_key=...,
))
```

Movement types: `purchase_receipt`, `sale`, `adjustment`, `transfer_in`, `transfer_out`, `return`.

### 3.4 Multi-tenancy and RLS

Every tenant-scoped table has a `tenant_id` column and a PostgreSQL row-level security policy. Before any DB operation, the request sets:

```python
# services/api/app/db/rls.py
set_rls_context(db, tenant_id=tenant_id, is_admin=False)
```

This prevents cross-tenant data access even if queries forget the `WHERE tenant_id = ?` clause. Never bypass with raw SQL that skips this context.

---

## 4. Authentication

### 4.1 Three token types

All JWTs are signed with `settings.jwt_secret` (HS256) and decoded in `services/api/app/auth/jwt.py`.

**Device token** (`typ=device`):
```json
{ "sub": "<device_id>", "tenant_id": "...", "shop_ids": ["..."], "typ": "device" }
```

**Operator token** (`typ=operator`):
```json
{ "sub": "<user_id>", "tenant_id": "...", "role": "owner", "typ": "operator" }
```

**Customer token** (`typ=customer`):
```json
{ "sub": "<customer_id>", "tenant_id": "...", "channel_id": "...", "email": "...", "typ": "customer" }
```

### 4.2 Permissions

Operator permissions are stored in `roles` → `role_permissions` → `permissions`. The system role `owner` receives all permissions. Check a permission:

```python
from app.auth.admin_deps import require_permission
router = APIRouter(dependencies=[require_permission("channels:manage")])
```

### 4.3 Storefront auth (customer OTP)

Customers authenticate via a 6-digit email OTP:
1. `POST /v1/storefront/auth/otp/request` — generates OTP, stores SHA-256 hash, emails it
2. `POST /v1/storefront/auth/otp/verify` — validates hash, issues customer JWT (7-day TTL)

OTP is generated with `secrets.randbelow(1_000_000)` (cryptographically secure). Row is locked with `SELECT FOR UPDATE` during verification to prevent race conditions.

---

## 5. Money and currency

### 5.1 Storage rules

- All monetary amounts stored as **integer minor units** (e.g. `unit_price_cents = 999` = ₹9.99)
- Column names end in `_cents`
- Never store floats for money

### 5.2 Multi-currency

Tenants have a `default_currency_code`. Per-product prices in additional currencies are in `product_prices`. FX conversion:

```python
# Single conversion seam — always use this:
from app.billing.fx import convert
converted = convert(db, tenant_id, money, target_currency)

# Auto-sync rates from ECB via frankfurter.app:
POST /v1/admin/fx-rates/sync  { "base": "INR", "targets": [] }
```

### 5.3 Display

Admin web uses `formatMoney(cents, { code, exponent })` from `@/lib/format.ts`. Storefront uses `Intl.NumberFormat` with the currency's native exponent.

---

## 6. E-commerce layer

See `docs/ecommerce-architecture.md` for the full e-commerce deep dive. Summary:

### 6.1 Channels

A channel is a named sales surface for a tenant. Every channel has a `type`, a `currency_code`, and an `inventory_pool_id`. Payment credentials (Stripe/Razorpay) are stored encrypted in `channel.config`.

Types: `pos` | `headless` | `shopify` | `woocommerce` | `manual`

### 6.2 Order lifecycle

```
cart_items → checkout_session → order (confirmed)
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                   ▼
             order_refund      dispatch_shipment     order.confirmed
             (partial/full)    (RQ task, if carrier   (outbound webhook)
                               configured)
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                   ▼
             processing         shipment_events      order.shipped
             → shipped          (append-only log)    (outbound webhook)
             → delivered
```

Orders are created by four paths: hosted checkout, headless storefront `/orders`, Shopify webhook, WooCommerce webhook. All paths fire the same post-creation hooks: confirmation email, `order.confirmed` outbound webhook, and dispatch enqueue (silent skip if no carrier configured).

**Fulfillment status** (`order.fulfillment_status`): `pending → processing → shipped → out_for_delivery → delivered | cancelled | returned | failed`

### 6.3 Carrier shipping

`services/api/app/services/shipping/` holds the provider abstraction. Add a new carrier by implementing `ShippingProvider` and registering in `registry.py`. Shiprocket is the first implementation — credentials encrypted in `channel.config`, auth token cached in Redis (9-day TTL).

### 6.4 Storefront rate limiting

`/v1/storefront/*` is rate-limited at **120 requests/minute per IP** using an async Redis counter. Fails open if Redis is unavailable. Admin routes are never rate-limited.

---

## 7. Background jobs

The RQ worker (`python -m app.worker`) processes tasks from the `ims-default` Redis queue.

| Task function | Trigger | What it does |
|--------------|---------|-------------|
| `dispatch_shipment` | Order creation (if carrier set) | Creates shipment in carrier API, assigns AWB, persists tracking data |
| `deliver_webhook` | Order creation / status change | HTTP POST to merchant webhook endpoint (3 attempts, exp. backoff) |
| `sweep_expired_reservations` | Cron / manual | Marks stale stock reservations as expired |
| `sweep_abandoned_carts` | Cron (every 2h) | Emails customers who started checkout but didn't complete |
| `sync_all_tenant_licenses` | Cron | Pulls plan/license state from platform service |

Enqueue: `task_queue().enqueue("app.worker.tasks.TASK_NAME", *args)`.

---

## 8. Email infrastructure

Every tenant configures their own sending credentials in `TenantEmailConfig`. IMS never sends from a shared platform address.

Supported providers: **SMTP** (Hostinger: `smtp.hostinger.com`, port 587/465), **Resend**.

```python
# Transactional emails sent by these service functions:
send_order_confirmation(db, order)          # on every order creation
send_abandoned_cart_email(db, ...)          # by sweep_abandoned_carts task
send_test_email(config, to_email)           # admin test-send
```

Email delivery never raises — a failed send logs a warning but never blocks the calling operation.

---

## 9. Outbound webhooks

Merchants register HTTPS endpoints for IMS to POST to when events occur.

```
POST /v1/admin/webhooks/endpoints   → register endpoint (gets a signing secret)
GET  /v1/admin/webhooks/deliveries  → delivery log
```

Each delivery is HMAC-SHA256 signed. Headers: `X-IMS-Signature: sha256=<hex>`, `X-IMS-Event`, `X-IMS-Delivery`. Delivery is async via RQ; failures retry at 5 min and 30 min.

Currently supported events: `order.confirmed`.

---

## 10. Entitlements and feature flags

Plan-level feature values are defined in `services/api/app/billing/plans.py` (config-as-code). Per-tenant overrides are stored in `tenant_feature_overrides`. Resolution order:

```
tenant override > plan value > catalog default
```

Feature catalog is defined in `services/api/app/billing/features.py`. View the current matrix at `GET /v1/internal/platform/plan-features` (requires `X-Admin-Token`).

---

## 11. Testing

```bash
# Run full API test suite:
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/ -q
docker compose exec api rm -rf /app/tests
```

Current: **489 passing, 1 pre-existing failure** (`test_admin_app_download_redirects` — makes a real HTTP call in CI without network).

Test patterns:
- Fixtures: `db` (transactional rollback), `tenant`, `shop` — defined in `tests/conftest.py`
- Admin auth stub: override `require_admin_context` and `get_db_admin` dependencies
- Storefront auth stub: override `get_db` and `get_current_customer`
- Never use `from __future__ import annotations` in test files — breaks FastAPI dependency resolution

---

## 12. Deployment

```yaml
# docker-compose.yml services:
postgres         # Main PostgreSQL (port 5432)
redis            # Redis (port 6379)
api              # FastAPI (port 8000, exposed as 8001)
worker           # RQ worker (no port)
admin-web        # Next.js (port 3100)
platform-web     # Next.js platform UI (port 3200)
platform         # Platform service
platform-postgres
platform-worker
```

The API container runs `alembic upgrade head` automatically on start. The admin-web container builds at image time.

Required environment variables for API: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ADMIN_API_TOKEN`.
