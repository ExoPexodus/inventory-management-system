# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

Monorepo with multiple runtimes:

| Path | Runtime | Role |
|------|---------|------|
| `services/api/` | FastAPI (Python 3.12) | Multi-tenant backend — ledger, e-commerce, sync |
| `apps/admin-web/` | Next.js 15 (TypeScript) | Merchant admin dashboard |
| `apps/cashier/` | Flutter | Offline-first POS app |
| `apps/admin_mobile/` | Flutter | Admin companion app |
| `apps/platform-web/` | Next.js 15 (TypeScript) | Platform operator dashboard (plans, tenants) |
| `packages/sync-protocol/` | OpenAPI YAML | Sync contract between backend and cashier |
| `packages/storefront-sdk/` | TypeScript | SDK for headless storefront developers |
| `docs/` | Markdown | Architecture docs and ADRs — read before large changes |

## Running the Full Stack

```bash
docker compose up --build
# API:           http://localhost:8001  (Swagger: /docs)
# Admin Web:     http://localhost:3100
# Platform Web:  http://localhost:3200
```

Seed demo data (wipes tenant data, keeps operators):
```bash
docker compose exec -e IMS_DEMO_RESET_OK=1 api python -m app.scripts.reset_demo_showcase
```

## Service-Specific Commands

### API (`services/api/`)
```bash
python -m venv .venv && pip install -r requirements.txt
alembic upgrade head          # run migrations
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
python -m app.worker          # RQ background worker
```

Required env vars (copy from `.env.example`): `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ADMIN_API_TOKEN`.

### Admin Web (`apps/admin-web/`)
```bash
npm install
npm run dev        # port 3000
npm run build
npm run lint
```

### Flutter Apps (`apps/cashier/`, `apps/admin_mobile/`)
```bash
# Flutter SDK is NOT bundled — clone it first:
git clone -b stable --depth 1 https://github.com/flutter/flutter.git tools/flutter

cd apps/cashier   # or apps/admin_mobile
../../tools/flutter/bin/flutter pub get
../../tools/flutter/bin/flutter analyze
../../tools/flutter/bin/flutter build apk --release
../../tools/flutter/bin/flutter run -d windows        # or -d chrome / -d android
```

**Flutter Android Build — Windows Gotcha:** `path_provider_android 2.3.x` pulls in `jni 1.0.0` which breaks Gradle. Fix:
```yaml
# in pubspec.yaml
dependency_overrides:
  path_provider_android: "2.2.22"
```

---

## Architecture

### Multi-tenancy & Row-Level Security
Every tenant-scoped table is protected by PostgreSQL RLS. Each request sets session variables (`ims.tenant_id`, `ims.is_admin`) via `app/db/rls.py:set_rls_context()`. **Never bypass this** — queries that skip RLS context leak cross-tenant data.

### Authentication — Three Token Types

| Type | `typ` claim | Used by | Issued at |
|------|-------------|---------|-----------|
| Device | `device` | Cashier, Admin Mobile | `POST /v1/devices/enroll` |
| Operator | `operator` | Admin Web | `POST /v1/admin/auth/login` or `X-Admin-Token` header |
| Customer | `customer` | Headless storefronts | `POST /v1/storefront/auth/otp/verify` |

Customer JWTs carry `customer_id`, `tenant_id`, `channel_id`, `email`. Device JWTs carry `device_id`, `tenant_id`, `shop_ids`.

Auth dependencies: `services/api/app/auth/deps.py`, `app/auth/admin_deps.py`, `app/routers/storefront/auth.py`.

### Inventory Ledger
Stock is **never a mutable field** — it is derived from `StockMovements` (immutable ledger rows). Direct stock updates must create movement records, not UPDATE quantities. Adjustments flow through `StockAdjustments` (pending → approved workflow).

### Offline Sync (Cashier ↔ API)
- Pull: `GET /v1/sync/pull` — delta bundle (products, stock snapshots, policies)
- Push: `POST /v1/sync/push` — batch of events (`sale_completed`, `ledger_adjustment`) with idempotency keys
- Conflicts return structured `conflict` objects (e.g. `insufficient_stock`, `card_requires_connectivity`)
- Full protocol in `docs/sync-architecture.md` and `packages/sync-protocol/openapi.yaml`

### Channels (E-commerce)
A **channel** is a sales surface. Types: `pos`, `headless`, `shopify`, `woocommerce`, `manual`. Every channel belongs to one tenant and one inventory pool. Storefront API requests carry `X-Channel-Id`.

```python
# Channel types
channel.type in {"pos", "headless", "shopify", "woocommerce", "manual"}
```

### Inventory Pools
An inventory pool is a named set of shops used to fulfil online orders. Channels reference pools, not individual shops. Create pools in admin before creating channels.

### Money
All amounts are stored as **integer minor units** (`*_cents` field names). Use `formatMoney(cents, currency)` for all display. Never store floats for money.

**Multi-currency:** Per-product prices in multiple currencies are stored in `product_prices`. FX rates are in `fx_rates` and can be auto-synced from frankfurter.app (`POST /v1/admin/fx-rates/sync`).

### Storefront API
Public-facing endpoints under `/v1/storefront/` are unauthenticated (channel-scoped via `X-Channel-Id`). Rate limited at 120 req/min per IP. Key flows:

```
GET  /v1/storefront/products           → product catalog
POST /v1/storefront/cart               → create cart
POST /v1/storefront/cart/{t}/items     → add item
POST /v1/storefront/checkout/session   → start hosted checkout
POST /v1/storefront/auth/otp/request   → customer login
POST /v1/storefront/auth/otp/verify    → verify → customer JWT
GET  /v1/storefront/customers/me       → customer profile (auth required)
```

### Hosted Checkout
The hosted checkout HTML page lives at `GET /checkout/{session_token}`. Templates in `services/api/templates/`. Payment providers (Stripe/Razorpay) are configured per channel — keys are stored encrypted in `channel.config`.

### Email
Transactional email uses `TenantEmailConfig` (per-tenant). Supported providers: `smtp` (Hostinger, any SMTP), `resend`. Configure via `POST /v1/admin/email/configure/smtp` or `/configure/resend`. Templates in `services/api/email_templates/`.

### Webhooks-Out
Merchants register HTTP endpoints via `POST /v1/admin/webhooks/endpoints`. Events are delivered asynchronously via RQ with exponential backoff (3 attempts: immediate, 5 min, 30 min). Payloads are HMAC-SHA256 signed. Currently supported event: `order.confirmed`.

### Background Jobs
RQ worker (`python -m app.worker`) processes:

| Task | Trigger | Description |
|------|---------|-------------|
| `deliver_webhook` | On order creation | Delivers one webhook event with retry |
| `sweep_expired_reservations` | Scheduled | Expires idle stock reservations |
| `sweep_abandoned_carts` | Scheduled (2h) | Sends cart recovery emails |
| `sync_all_tenant_licenses` | Scheduled | Syncs plan/license from platform service |
| `aggregate_report_placeholder` | Admin-triggered | Analytics placeholder |

### Payment Key Encryption
Stripe `stripe_secret_key` and Razorpay `razorpay_key_secret` are encrypted at rest in `channel.config` using `encrypt_secret()`/`decrypt_secret()` from `email_service.py`. Plain-text keys in config will fail decryption — reconfigure channels after any key rotation.

---

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Migration files: `services/api/alembic/versions/`. Naming convention: `YYYYMMDDNNNNNN_description.py`. The API container runs `alembic upgrade head` automatically on start.

Latest head as of writing: `20260522000001` (product_variants).

---

## Frontend Patterns

### Admin Web
- All pages: `"use client"` directive, components from `@/components/ui/primitives`
- API calls: `fetch("/api/ims/v1/admin/...")` — BFF proxy handles auth
- Currency: `useCurrency()` hook from `@/lib/currency-context` + `formatMoney(cents, currency)`
- New nav items require entry in both `ROOT_ROUTES` and `NAV` in `apps/admin-web/src/components/dashboard/AppShell.tsx`

### Storefront SDK
`packages/storefront-sdk/src/client.ts` — `StorefrontClient` class wraps all storefront endpoints:
```typescript
const client = new StorefrontClient({ baseUrl, channelId });
const products = await client.listProducts();
const cart = await client.createCart();
await client.addToCart(cart.cart_token, productId, 1);
const session = await client.createCheckoutSession(cart.cart_token);
```

---

## Key Docs to Read Before Large Changes

| Doc | When to read |
|-----|-------------|
| `docs/architecture.md` | Any backend change |
| `docs/ecommerce-architecture.md` | Any e-commerce / storefront change |
| `docs/storefront-api.md` | Building headless storefronts |
| `docs/sync-architecture.md` | Cashier sync, conflict semantics |
| `docs/client-architecture.md` | Cashier or admin app changes |
| `docs/adr-index.md` | Before making a new architectural decision |
