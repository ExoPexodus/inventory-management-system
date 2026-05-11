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

Movement types in active use: `sale`, `purchase_receipt`, `manual_adjustment`, `transfer_in`, `transfer_out`, `rma_return`. New flows that move stock MUST create paired or single movements rather than touching computed quantities. Batch reads use `current_quantities(db, shop_id, product_ids)` and `get_committed_to_transfers_batch()` from `services/api/app/services/stock.py` — single-product helpers exist but produce N+1 on multi-row listings.

### Catalog Taxonomy

Two parallel concepts, both per-tenant:
- **Categories** — hierarchical via `categories` table (parent_id self-FK) joined to products via `product_categories`. Use for browse/breadcrumb navigation. Storefront category pages include descendants automatically. Admin tree manager at `/categories`.
- **Tags** — flat JSONB list on `Product.tags`. Use for marketing labels, filters, and discount targeting.

The legacy `Product.category` string column was dropped in migration `20260527000001`. Code looking up a product's categories should join `product_categories` or use `Product.category_slugs` on admin responses.

### Full-Text Search
`Product.search_vector` (PostgreSQL `tsvector`, GIN-indexed) is populated by trigger from product name (weight A), sku (B), joined category names + tags (C), and short_description + description (D). Both admin `/v1/admin/products` and storefront `/v1/storefront/products` use `make_tsquery()` (`app/services/product_search.py`) when `q` is set, with `ts_rank` ordering when no explicit `sort_by` is provided. The trigger handles non-array `tags` JSONB defensively. ILIKE remains the path for transaction search and other minor surfaces.

### Transfer Orders
Cross-shop inventory moves with approval workflow. Status flow: `draft → pending_approval → approved → in_transit → completed`, plus `rejected` and `cancelled` terminal states. Approval is gated by the new `transfers:approve` permission. Two tenant settings: `transfer_auto_approve_under_cents` (line-total below this auto-approves on submit) and `transfer_allow_self_approval` (default false). On approval, each `TransferOrderLine.unit_cost_at_transfer_cents` is snapshotted from the current `Product.cost_price_cents` so per-shop COGS stays accurate. Source stock is soft-deducted via `get_committed_to_transfers_batch()` while a transfer is approved or in-transit; on receive, paired `transfer_out`/`transfer_in` `StockMovement` rows are written with unique idempotency keys per line direction.

### RMA Flow (Returns / Refunds / Exchanges)
Three refund types — `refund_only`, `return_refund`, `exchange` — unified across e-commerce and POS. Storefront customers initiate via `POST /v1/storefront/refund-requests`; cashiers initiate against POS transactions via `POST /v1/cashier/refund-requests`; merchant approves in admin-web `/rma`. On approval the system calls Stripe/Razorpay refund APIs automatically (`payment_refund.py`); cash sales mark a manual "cash returned" step. Status flow: `requested → approved/rejected → received (return+refund) → refunded → closed`, plus `cancelled` and `exchange_shipped` for exchange-type. Tenant settings: `default_restock_on_refund`, `refund_window_days` (default 30), `rma_auto_approve_under_cents`. Every status transition writes a `RefundRequestEvent` audit row and (where applicable) fires an email — email send/failure is itself a timeline event. Shiprocket return-AWB issuance is wired through `ShiprocketProvider.create_reverse_shipment`. Permissions: `rma:read`, `rma:write`.

### Plan & Entitlement Resolution
Plan-feature mapping (`max_channels`, `shopify_connector`, etc.) lives in the platform service `plan_features` table — NOT in IMS code constants. The legacy `PLAN_FEATURES` dict in `services/api/app/billing/plans.py` was deleted. At license sync time, the platform's `/v1/platform/license/{tenant_id}` response includes a `plan_features` map which `_upsert_cache()` writes into `TenantLicenseCache.plan_features` (JSONB). The resolver `resolve_plan_value(db, tenant_id, feature_key)` reads from the cache first, falling back to `FEATURE_CATALOG` defaults in `app/billing/features.py`. Per-tenant overrides live in `tenant_limit_overrides` on the platform side and are merged into the response. Bulk cohort overrides: `POST /v1/platform/overrides/bulk`. The platform exposes the IMS feature catalog at `/v1/internal/platform/plan-features` (schema only) and accepts a cascade trigger at `/v1/internal/license-sync-trigger` (HMAC-authenticated) for immediate re-sync after a plan change.

### Advanced RBAC
Roles (`Role`) are tenant-scoped with system-role protection (`is_system=true` cannot be deleted). Role builder UI in admin-web at Team → Roles. Each role's permission set is editable; cache is invalidated automatically via `invalidate_role_cache(role_id)`. Three less-obvious endpoints worth knowing:
- `POST /v1/admin/roles/{id}/clone` — duplicates a role with `{name}_copy` suffix
- `GET /v1/admin/roles/{id}/assigned-users` — lists users for the reassignment flow
- `POST /v1/admin/roles/{id}/reassign-and-delete` — atomic bulk reassign + delete (required when the role has users)

Permission codenames are seeded via migrations using `INSERT INTO permissions ... ON CONFLICT DO NOTHING` paired with `INSERT INTO role_permissions ... WHERE role.name = 'owner'`. See `20260518000001_email_manage_permission.py` as the canonical template.

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

**Security protections (opt-in per channel):**
- Per-channel CORS Origin allowlist via `channel.config.allowed_origins` — configure in admin-web Channels → Security tab or via `PATCH /v1/admin/channels/{id}`. Requests from unlisted browser origins receive 403; server-to-server calls are always allowed.
- OTP and magic-link per-email rate limit: 5 requests/hour, 30 requests/day per channel. Returns 429 when exceeded. Fails open on Redis errors.
- See `docs/storefront-security.md` for full threat model, configuration recipes, and limits.

### Hosted Checkout
The hosted checkout HTML page lives at `GET /checkout/{session_token}`. Templates in `services/api/templates/`. Payment providers (Stripe/Razorpay) are configured per channel — keys are stored encrypted in `channel.config`.

### Email
Transactional email uses `TenantEmailConfig` (per-tenant). Supported providers: `smtp` (Hostinger, any SMTP), `resend`. Configure via `POST /v1/admin/email/configure/smtp` or `/configure/resend`. Templates in `services/api/email_templates/`.

### Webhooks-Out
Merchants register HTTP endpoints via `POST /v1/admin/webhooks/endpoints`. Events are delivered asynchronously via RQ with exponential backoff (3 attempts: immediate, 5 min, 30 min). Payloads are HMAC-SHA256 signed. Currently supported event: `order.confirmed`.

### Image Storage (Cloudflare R2)
Product images are uploaded **directly from the browser to R2** via presigned PUT URLs — file bytes never pass through the API server.

Two storage modes per tenant:
- `platform` (default) — IMS shared R2 bucket, key prefix `{tenant_id}/products/...`
- `byo` — tenant's own R2 or S3-compatible bucket (credentials encrypted in tenant row)

Upload flow: `POST /v1/admin/media/presign-upload` → browser PUT to R2 → `POST /v1/admin/catalog/products/{id}/images`.

**Storage quotas (platform-mode only):** `TenantLicenseCache.storage_limit_mb` is the limit. The counter `tenants.storage_bytes_used` is incremented atomically on image save and decremented on delete. Presign returns HTTP 402 at 100%, `storage_warning` JSON at 80%. BYO tenants are fully exempt.

Required env vars (set in `.env`): `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`. Configure `STORAGE_RECONCILE_INTERVAL_HOURS` (default `24`) for the daily drift-correction job.

Full reference: `docs/ecommerce-architecture.md §16`.

### Carrier Shipping (Shiprocket)
When a channel has `shipping_provider: "shiprocket"` in `channel.config`, every confirmed order is automatically dispatched:

```python
# Provider abstraction in services/api/app/services/shipping/
# Add new carriers by implementing ShippingProvider and registering in registry.py
from app.services.shipping.registry import get_provider
provider = get_provider("shiprocket")  # or "delhivery", etc.
```

Shiprocket credentials are stored **encrypted** in `channel.config` (same as Stripe/Razorpay). The `fulfillment_status` column on `Order` tracks dispatch state: `pending → processing → shipped → out_for_delivery → delivered`.

### Background Jobs
RQ worker (`python -m app.worker`) processes:

| Task | Trigger | Description |
|------|---------|-------------|
| `deliver_webhook` | On order creation | Delivers one webhook event with retry |
| `dispatch_shipment` | On order creation (if carrier configured) | Creates shipment in carrier API, assigns AWB |
| `reconcile_storage_usage` | Daily (configurable) | Corrects `storage_bytes_used` from real R2 contents |
| `sweep_expired_reservations` | Scheduled | Expires idle stock reservations |
| `sweep_abandoned_carts` | Scheduled (2h) | Sends cart recovery emails |
| `sync_all_tenant_licenses` | Scheduled | Syncs plan/license from platform service |

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

Latest IMS head as of writing: `20260603000001` (RMA exchange tracking).
Latest platform head as of writing: `20260601000001` (plan_features + override JSONB).

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
const products = await client.listProducts({ q: "sticker", categorySlug: "anime" });
const categories = await client.listCategories();
const cart = await client.createCart();
await client.addToCart(cart.cart_token, productId, 1);
const session = await client.createCheckoutSession(cart.cart_token);

// After customer auth (OTP or magic-link):
client.setCustomerToken(jwt);
await client.requestRefund({ order_id, refund_type: "refund_only", reason_code: "damaged", lines: [...] });
const myRefunds = await client.listRefundRequests();
```

---

## Key Docs to Read Before Large Changes

| Doc | When to read |
|-----|-------------|
| `docs/architecture.md` | Any backend change |
| `docs/ecommerce-architecture.md` | Any e-commerce / storefront change |
| `docs/storefront-api.md` | Building headless storefronts |
| `docs/storefront-security.md` | Headless storefront onboarding, OTP limits, CORS allowlist |
| `docs/sync-architecture.md` | Cashier sync, conflict semantics |
| `docs/client-architecture.md` | Cashier or admin app changes |
| `docs/adr-index.md` | Before making a new architectural decision |
| `docs/superpowers/roadmap/` | Recent feature specs and the stickerize / final-four / followup rollouts |
