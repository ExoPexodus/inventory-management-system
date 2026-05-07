# Architecture Overview

Quick-reference snapshot of the IMS platform.

For full detail: `docs/architecture.md` and `docs/ecommerce-architecture.md`.

---

## What it is

A **multi-tenant inventory and e-commerce backend** that serves two roles simultaneously:

- **POS backend** — Offline-first cashier sync, multi-shop stock ledger, transaction history
- **E-commerce backend** — Multi-channel storefronts, hosted checkout, webhooks, customer portal

---

## Components

| Component | Stack | Port | Role |
|-----------|-------|------|------|
| `services/api` | FastAPI (Python 3.12) | 8001 | Core backend — all business logic |
| `apps/admin-web` | Next.js 15 | 3100 | Merchant admin dashboard |
| `apps/cashier` | Flutter | — | Offline-first POS app |
| `apps/admin_mobile` | Flutter | — | Admin companion app |
| `apps/platform-web` | Next.js 15 | 3200 | Platform operator dashboard |
| `packages/storefront-sdk` | TypeScript | — | SDK for headless storefronts |
| PostgreSQL | — | 5432 | Primary database with RLS |
| Redis | — | 6379 | Cache + RQ job queue |
| RQ Worker | Python | — | Background jobs |

---

## Key design principles

1. **Immutable ledger** — Stock is derived from `StockMovements`. Never mutable.
2. **Integer money** — All amounts in minor units (`*_cents`). No floats.
3. **RLS everywhere** — PostgreSQL row-level security on every tenant-scoped table.
4. **BYO credentials** — Merchants bring their own payment and email providers.
5. **Async post-creation** — Email + webhook delivery never block order creation.

---

## Traffic flow

```
Cashier ──── device JWT ────────► /v1/sync/*          (pull/push)
                                   /v1/transactions

Admin Web ── operator JWT ──────► /v1/admin/*          (all merchant ops)

Storefront ─ X-Channel-Id ──────► /v1/storefront/*     (public catalog/cart/checkout)
                                   /checkout/*          (hosted checkout page)

Shopify/Woo ─ HMAC ─────────────► /v1/webhooks/*       (inbound orders)

Platform ─── X-Admin-Token ─────► /v1/internal/*       (plan/license management)
```

---

## Admin dashboard pages

| Page | Permission | What it manages |
|------|-----------|-----------------|
| Dashboard | — | KPIs, recent activity |
| Inventory | `inventory:read` | Stock holdings, movements, adjustments |
| Orders | `sales:read` | POS transaction ledger |
| E-comm Orders | `orders:manage` | Online orders + refunds |
| Products | `catalog:read` | Product catalog, variants, prices |
| Channels | `channels:manage` | Sales channels + payment setup |
| Inventory Pools | `inventory_pools:manage` | Shop groupings for fulfilment |
| Discounts | `discounts:read` | Discount codes and automatic promotions |
| Tax | `tax:manage` | Tax regions and rules |
| E-commerce | `settings:read` | Email, webhooks, FX rates, shipping |
| Integrations | `integrations:read` | Shopify, WooCommerce, API tokens |
| Settings | `settings:read` | Currency, device security, business type |

---

## Maturity snapshot

| Area | Status |
|------|--------|
| POS core (sync, ledger, cashier) | ✅ Production-ready |
| Multi-tenant RLS + auth | ✅ Production-ready |
| E-commerce channels + storefront API | ✅ Production-ready |
| Hosted checkout (Stripe + Razorpay) | ✅ Production-ready |
| Shopify + WooCommerce connectors | ✅ Production-ready |
| Discounts, shipping, tax | ✅ Production-ready |
| Multi-currency + FX auto-sync | ✅ Production-ready |
| Email (SMTP + Resend) | ✅ Production-ready |
| Outbound webhooks | ✅ Production-ready |
| Customer OTP auth + portal | ✅ Production-ready |
| Product variants | ✅ Production-ready |
| Storefront SDK (TypeScript) | ✅ Published |
| Admin dashboard UI | ✅ Full coverage |
| Returns/refund flow | ✅ Production-ready |
| Advanced RBAC (custom roles) | 🔄 Iteration planned |
| Transfer orders (cross-shop) | 🔄 Planned |
| Storefront magic-link auth (alternatives to OTP) | 🔄 Planned |
