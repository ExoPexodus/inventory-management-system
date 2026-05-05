# E-commerce Pivot Design

**Date:** 2026-05-06
**Status:** Draft (awaiting user review)
**Related:**
- [2026-04-23 Feature Gap Analysis](./2026-04-23-feature-gap-analysis-design.md)
- [2026-04-24 Domain Tracker](./2026-04-24-domain-tracker.md)

---

## 1. Executive Summary

The IMS pivots from a **retail-first POS + inventory backend** to an **e-commerce-first multi-channel commerce backend**, with retail/POS as a secondary (still supported) surface.

The product becomes:

> A backend that e-commerce merchants use to manage catalog, stock, customers, orders, and analytics — exposing those primitives to **Shopify**, **WooCommerce**, and **custom storefronts** equally — while continuing to power the **in-store cashier POS** for merchants who also operate physical retail.

Strategic posture: integration hub + headless commerce backend, **not** a full storefront builder, **not** a merchant of record at launch.

---

## 2. Locked Strategic Decisions

These were settled during brainstorming; the rest of the design assumes them.

| Decision | Choice |
|---|---|
| Pivot scope | E-commerce primary, retail secondary; both supported |
| Architecture pattern | Integration hub (Shopify, Woo) + headless commerce backend (custom sites) |
| Channel priority | Shopify, WooCommerce, custom storefronts — equal priority |
| Source of truth | IMS is master for catalog, stock, customers, orders, money totals |
| Inventory model | Channels pull from a configurable shared pool of shops |
| Catalog flow | Hybrid — import on first connect, IMS-master afterward |
| Stock reservation | Soft reservation with TTL (default 15 min cart, 24 hr pending payment) |
| Returns / RMA scope | Inbound-only stock movements at launch; full RMA workflow as a later domain |
| Multi-currency | Full multi-currency from day 1 (per-listing prices, shopper-switchable, FX rules engine) |
| Custom storefront paths | Both — IMS-hosted checkout AND raw APIs for merchants who run their own checkout |
| Payment processing | BYO (merchant brings own Stripe / Razorpay / PayPal) at launch; MoR revisited post-Phase 3 |
| Order data ingestion | Full store (customer + line items) for unified analytics + CRM |
| Online-only merchants | Hide shop concept in UI; backend always uses a virtual shop; conversion path to add physical stores later |
| 56-domain retail roadmap | Cherry-pick — only build features serving both retail + e-commerce |
| Build sequencing | Foundations-first phased rollout (Phase 0 → 3) |
| Geographic scope at launch | India + global (English / generic). Indonesia and Canada deferred to post-Phase 3 |

---

## 3. Architecture Overview

### 3.1 Top-level shape

The IMS becomes a multi-channel commerce backend with three concurrent client surfaces:

1. **Existing clients** — admin web, cashier POS (Flutter), admin mobile (unchanged in shape; expanded in features)
2. **Channel connectors** — Shopify and WooCommerce (outbound: catalog/stock push; inbound: order/refund webhooks)
3. **Headless commerce API** — public REST/GraphQL endpoints for custom storefronts (catalog, cart, checkout, orders, shipping/tax calc)

### 3.2 Component layout (proposed)

```
services/api/app/
├── (existing) catalog, stock, sales, suppliers, transfers, etc.
├── channels/                ← NEW — channel registry, sync orchestration
│   ├── shopify/             ← Shopify connector (auth, sync, webhooks)
│   ├── woocommerce/         ← WooCommerce connector
│   └── headless/            ← "channel" type for custom storefronts
├── ecommerce/               ← NEW — e-commerce primitives
│   ├── shipping/            ← zones, rates, conditions, calc API
│   ├── tax/                 ← regions, rules, inclusivity engine
│   ├── reservations/        ← soft-TTL stock holds
│   ├── checkout/            ← hosted checkout, cart sessions
│   ├── payments/            ← BYO provider connectors (Stripe, Razorpay, PayPal)
│   ├── currency/            ← FX rules, multi-currency pricing
│   └── storefront_api/      ← public REST/GraphQL for custom sites
├── email/                   ← NEW — transactional email + domain auth
└── (refactored) products/   ← extended for digital/service/donation/giftcard types
```

### 3.3 Key invariants

- IMS is the single source of truth for catalog, stock, customers (after first connect), orders, and money totals.
- Every order — regardless of channel — lands in the same `orders` table with a `channel_id` foreign key.
- Every stock change — regardless of source — is a row in `stock_movements` (the existing immutable ledger), with a `source_channel_id` field added.
- Channels are configurable in two dimensions: which inventory pool they pull from, and which catalog subset they publish.

### 3.4 Example request flows

**Flow A — Shopper buys on a custom site (hosted checkout):**
1. Custom site frontend calls `GET /v1/storefront/products` → IMS returns published catalog
2. Shopper adds to cart → `POST /v1/storefront/cart` → IMS creates a soft reservation
3. Shopper proceeds to checkout → site redirects to IMS hosted checkout (with cart token)
4. Hosted checkout collects shipping, calculates tax, charges via merchant's BYO Stripe/Razorpay/PayPal
5. On payment success → IMS creates order, converts soft reservation to stock movement, fires `order.created` webhook to merchant
6. IMS sends transactional emails (order confirmation, etc.)

**Flow B — Shopper buys on the merchant's Shopify store:**
1. Catalog/stock has been pushed from IMS to Shopify on a schedule
2. Order placed entirely on Shopify
3. Shopify webhook fires to IMS → IMS records the order, creates stock movements, attributes to the Shopify channel

**Flow C — Cashier sells in-store (existing flow, augmented):**
1. Cashier app records sale → syncs to IMS → IMS creates stock movements attributed to the POS channel
2. Stock change broadcast to all online channels (push to Shopify/Woo, available via API)

---

## 4. Channel & Inventory Model

### 4.1 Channels

A **channel** is a sales surface. Every order, stock movement, and analytics row attributes to one.

| Channel type | Examples | Connection method |
|---|---|---|
| `pos` | In-store cashier (existing) | Built-in (per shop) |
| `shopify` | A merchant's Shopify store | OAuth app install |
| `woocommerce` | A merchant's Woo store | API key + URL |
| `headless` | Merchant's own custom site | API key (per channel) |
| `manual` | Admin-created order (phone / B2B) | Built-in |

A tenant can have N channels of any type — e.g., three Shopify stores for different brands plus a headless API for their custom site plus per-shop POS channels.

**Schema (new):**

```
channels
├── id (uuid)
├── tenant_id
├── type (pos | shopify | woocommerce | headless | manual)
├── name (e.g. "Main Shopify store", "B2B portal")
├── status (active | paused | disconnected)
├── config (jsonb — type-specific: shop URL, API tokens, webhook secret, etc.)
├── inventory_pool_id (FK)
├── catalog_filter_id (nullable FK — null = publish full catalog)
├── currency_code (the channel's selling currency)
├── created_at, updated_at
```

### 4.2 Inventory pools

An **inventory pool** is a configurable set of shops whose stock is visible and sellable to a given channel.

```
inventory_pools
├── id (uuid)
├── tenant_id
├── name (e.g. "Online warehouse", "All stores", "Mumbai + Delhi only")

inventory_pool_shops  ← join
├── pool_id
├── shop_id
```

Rules:
- Multiple channels can share a pool.
- Multiple pools can include the same shop.
- A shop can be in zero pools (POS-only).
- Available stock for channel X = `sum(current_stock) across pool shops − sum(active reservations)`
- When a channel order lands, the resulting stock movement attributes to a specific shop (configurable per pool: "fulfill from primary first," "split proportionally," or "manual selection at fulfillment").
- Online-only merchants get an implicit pool of one virtual shop, auto-created on signup (Section 7).

### 4.3 Source-of-truth rules

| Domain | Master | Channel role |
|---|---|---|
| Catalog (products, variants, prices, descriptions) | IMS | Publish-down (push to Shopify/Woo; serve to headless API) |
| Stock | IMS | Read-only from channel side |
| Orders | IMS | Channel creates them; IMS stores forever |
| Customers | IMS | Channel orders create/match customers in IMS CRM |
| Refunds / returns (stock impact) | IMS | Channel notifies; IMS records `return_received` movement |
| Order fulfillment status | Channel (for now) | IMS reflects channel's status; doesn't drive it |
| Discounts / coupons | IMS | Pushed to channels where supported |
| Shipping rates | IMS (engine) | Shopify/Woo use their own native rates; headless consumes ours |
| Tax rates / rules | IMS (engine) | Shopify/Woo use their own; headless consumes ours |

### 4.4 Hybrid catalog flow

1. **At connect time:** Connector reads the channel's existing catalog. For each product:
   - **Match by SKU** → link channel product to existing IMS product
   - **No match** → create a new IMS product (flagged `imported_from_channel=<channel_id>`, status `pending_review`)
2. **Reconciliation queue** in admin web: merchant merges duplicates, fills missing fields, approves
3. **After approval:** Channel switches to "IMS-master" mode. Future catalog edits flow IMS → channel only. Channel-side edits are detected and either rejected (with notification) or auto-overwritten on next sync.
4. **Conflict policy:** Configurable per channel — `ims_wins` (default), `manual_resolve` (queue conflicts), `channel_wins` (merchant explicitly opts in for one channel)

### 4.5 Connector boundaries

- **Shopify connector:** catalog push, inventory level push, products/variants/collections sync, orders pull (webhooks), refunds pull (webhooks), customers sync. Does NOT drive Shopify shipping/tax — Shopify uses its own.
- **WooCommerce connector:** equivalent shape via Woo REST API + webhooks; same boundary as Shopify.
- **Headless API:** serves IMS catalog/cart/order/shipping/tax to a custom frontend; powers our hosted checkout or a merchant-built one; uses IMS shipping engine + tax engine (unlike Shopify/Woo).

---

## 5. Phase 0 Foundations

Phase 0 builds the primitives every channel will consume. All ship behind feature flags + entitlements; retail merchants exercise them before any e-commerce launch. Nothing in Phase 0 is merchant-visible as "e-commerce."

### 5.1 Channel & Inventory Pool model

Tables: `channels`, `inventory_pools`, `inventory_pool_shops`. New columns: `source_channel_id` on `stock_movements`, `channel_id` on `orders`, `customers` (created-via), and analytics rollups.

Rationale: every other primitive references this. Bolting it on after channels exist means rewriting every order/stock/analytics query.

### 5.2 Stock reservation engine (soft TTL)

```
stock_reservations
├── id, tenant_id
├── product_id, variant_id, shop_id
├── quantity
├── channel_id, cart_token
├── expires_at, status (active | committed | released | expired)
├── created_at, updated_at
```

- Hooks into "available stock" calculation: `available = sum(current_stock) − sum(active_reservations)`
- Background sweeper releases expired holds
- TTL configurable per channel (default 15 min cart, 24 hr pending payment)
- On order completion: reservation → `committed`, replaced by a real stock movement
- On order cancel/timeout: reservation → `released`

Rationale: every channel that lets shoppers race for stock needs this. Schema-level concern.

### 5.3 Multi-currency engine

Three layers:

1. **Per-row currency** — every monetary column gets an explicit `currency_code` sibling. `unit_price_cents` always co-exists with `unit_price_currency`. No more implicit tenant currency.
2. **Per-listing pricing** — products/variants can have prices in multiple currencies:
   ```
   product_prices
   ├── product_id, variant_id
   ├── currency_code
   ├── amount_cents
   ├── channel_id (nullable — for channel-specific overrides)
   ```
3. **FX rules engine** — for currencies without explicit per-listing prices, derive from a base currency via FX rules. `fx_rates` table updated by scheduled job from a public source (ECB / openexchangerates); manual override allowed. Order rows freeze the FX snapshot used at order time so reports are stable.

**Shopper-facing:** the headless storefront API and hosted checkout accept a `?currency=USD` query param; return prices using either explicit listing price for that currency or FX-derived fallback.

Rationale: schema-level decision. Adding `currency_code` to every money column later is a migration nightmare touching dozens of tables.

### 5.4 Shipping engine

Configurable shipping calculator exposed as an internal service and a public API.

**Concepts:**
- **Shipping zones** — zone = (channel) + (set of country/state/postal-code rules). Multiple zones per channel.
- **Rates** — each zone has 1–N rates ("Standard," "Express"). A rate has a base price + conditions:
  - By cart total (flat / tiered / free above N)
  - By total weight (flat / per-kg / tiered)
  - By number of items (flat / per-item)
  - By postal code/region (sub-zone overrides)
- **Per-product shipping class** (optional) — products tagged "fragile" / "oversized" / "digital-no-shipping" map to specific rates
- **Free-shipping thresholds** — first-class concept (`free_above_cents` per zone-rate)

**API:** `POST /v1/shipping/calculate { cart_lines, destination, channel_id, currency }` → available rates with prices in requested currency.

Rationale: custom storefronts and hosted checkout cannot ship without this. Shopify/Woo have their own native shipping (we don't replace it for those channels), but headless needs ours.

### 5.5 Tax engine (with inclusivity toggle)

Region-based tax rules with two cross-cutting toggles:

1. **Tax inclusivity per channel** — `tax_included_in_price = true | false`. When true, listed prices include tax (common in EU, India); checkout displays "incl. tax of X." When false, tax is added at checkout (common in US, generic).
2. **Per-product tax class** — products map to tax classes (`standard`, `reduced`, `zero-rated`, `exempt`) which resolve to different rates per region.

**Tables:** `tax_regions`, `tax_rules`, `tax_classes`, `tax_rate_overrides`.

**API:** `POST /v1/tax/calculate { cart_lines, destination, channel_id, currency, tax_included }` → line-item tax + total. Headless storefronts + hosted checkout consume this. Shopify/Woo orders carry their own tax breakdowns; we store them as-is.

**At launch:** ships with India (GST: CGST/SGST/IGST + slabs) + a generic country-agnostic mode. PPN (Indonesia) and Canadian provincial tax → post-Phase 3 layers using the same engine. The engine is designed pluggable so adding markets later is additive, not a rewrite.

Rationale: same as shipping — headless can't checkout without it; the inclusivity toggle is schema-level (changes how product prices are interpreted).

### 5.6 Product type expansion

Today: physical only. Add four more: `physical | digital | service | donation | gift_card`.

**Common fields across all types** (from the Hostinger Horizons-inspired UX):
- Title, Subtitle, Ribbon (visual badge: "NEW" / "SALE" / "BESTSELLER")
- Description (rich text)
- Image gallery
- Pricing block: price + optional discount price + SKU
- `track_quantity` toggle (optional even for physical — e.g., made-to-order)
- Additional info sections (merchant-defined collapsible blocks: shipping policy, FAQ, returns, sizing — reusable across products)
- Status (active | draft | archived)

**Per-type additions:**

| Type | Type-specific fields |
|---|---|
| **Physical** | Weight, dimensions, shipping class, options/variants |
| **Digital** | File uploads (up to 10, ~100MB total) OR external link; auto-email download link on order; optional license-key pool |
| **Service** | Options/variants (e.g., 30-min vs 60-min, basic/premium tier); no shipping; scheduling deferred to later domain |
| **Donation** | Customer-defined amount (variable); no inventory; tax-exempt by default |
| **Gift card** | Predefined amount tiers (e.g., $25 / $50 / $100 / custom); expiry toggle (never-expires vs expires-after-N-months); generates redeemable codes; redeemable as a payment method |

AI-generation of product copy from images (also seen in Horizons) is reserved for a later "polish" item; UI space reserved.

Rationale: product type is a discriminator on the `products` table — affects order-line rendering, shipping eligibility, tax behavior, fulfillment. Adding it after channels exist means refactoring every channel's catalog publisher.

### 5.7 Discounts module

First-class discounts (`discounts` table) with rule types:

- Code-based vs automatic
- Percentage off / fixed amount off / free shipping / buy-X-get-Y
- **Conditions:** min cart total, specific products/categories, customer segments, date range, usage limits (per-customer + global)
- **Stacking rules:** stackable / exclusive / priority order

Status today: partial. Phase 0 hardens it into a unified module that all channels can call.

Rationale: channels need to push discounts down (Shopify/Woo) or compute them server-side (headless). A consistent module avoids per-channel discount kludges.

### 5.8 Email infrastructure

- **Provider abstraction:** start with **Resend** (clean API, generous free tier, simple domain setup). SES as cost-effective alternative for scale.
- **Domain auth wizard:** during merchant onboarding, walk them through SPF/DKIM/DMARC setup with copyable DNS records and a verification check.
- **Template system:** versioned, mergeable templates (`email_templates` table) for: order confirmation, shipment, refund confirmation, abandoned cart, password reset, magic-link login, invoice, gift card delivery, etc. Templates support per-tenant overrides.
- **Preview + test send** in admin web (Hostinger Horizons-style)
- **Sending log** for support/debugging.

Rationale: hosted checkout can't complete without sending order confirmations. Domain auth has to be in place before merchants invite real customers, or emails go to spam.

### 5.9 Catalog enrichment for e-commerce

Extending the existing catalog module with fields retail-only didn't need:

- Image galleries (today: single image; needed: multiple per product, per variant, ordered)
- Long descriptions + short descriptions (rich text)
- SEO fields: slug, meta title, meta description, OG image
- Variant options (size, color, etc.) — formal "options" model, not free-text variants
- Product status per channel: `draft | active | archived`
- Tags + collections (cross-cuts categories)

Rationale: channels publish these fields. Adding them after channels exist means every channel publisher updates and every existing catalog row backfills.

### 5.10 Online-only mode + conversion path

See Section 7 for full mechanism (auto-created virtual shop, `kind = virtual | physical`, business_type-gated UI, conversion wizard).

### 5.11 Customer model unification

Every channel-incoming order creates or matches a customer in the same `customers` table.

**Match strategy:**
- Match by `email` (canonical) within tenant
- Fall back to `phone` if email missing
- Else create new
- Channel attribution: `customer_channels` join table tracks which channels each customer has bought from

Rationale: foundation for unified analytics + CRM across channels (an explicit user requirement). Adding channel-attribution columns later is fine; the matching logic must be in place at first order ingestion.

### 5.12 Webhooks-out (merchant-facing event bus)

Merchants subscribe to events: `order.created`, `order.updated`, `refund.created`, `inventory.changed`, `customer.created`, etc.

**Standard pattern:** HMAC-signed payloads, retry-on-failure with exponential backoff, dead-letter UI, replay tools.

Rationale: custom storefronts and merchant-side automations (Zapier, n8n, custom CRM/ERP) depend on this.

### 5.13a Plan entitlements (in the billing module)

The billing module gains a feature catalog and plan-to-feature mappings. **This is the source of truth for what a tenant can use** — directly tied to monetary outcomes.

```
plan_features              ← canonical list of toggleable capabilities
├── key (e.g. "shopify_connector", "headless_api", "hosted_checkout",
│           "byo_razorpay", "email_volume_per_month", "max_channels",
│           "max_products", "ai_product_generation", "multi_currency_advanced")
├── name, description (for marketing/admin pages)
├── value_type (boolean | numeric_limit | enum)
├── default_value

plan_feature_values        ← per-plan overrides
├── plan_id
├── feature_key
├── value (jsonb)

tenant_feature_overrides   ← per-tenant overrides (sales-driven, comp accounts, beta)
├── tenant_id
├── feature_key
├── value
├── reason, expires_at
```

**Resolution:** `tenant_override > plan_value > feature_default`. Cached in Redis, invalidated on plan/override change.

**Service-layer API:** every tenant-scoped request resolves entitlements once and attaches to request context. Code calls `entitlements.require("headless_api")` or `entitlements.limit("max_channels")`. Errors are user-facing and structured: `403 plan_upgrade_required` with `{required_feature, current_plan, suggested_plan}`.

**Pivot examples:**
- Headless API access → Pro/Business-tier feature → entitlement
- Number of channels → numeric metered entitlement
- BYO payment provider availability per plan → enum entitlement
- AI product copy generation → upsell entitlement
- Per-listing multi-currency overrides → tier-gated entitlement

### 5.13b Engineering rollout flags

Separate, simpler concern for gradual launch + experiments:

```
feature_flags
├── key (e.g. "stock_reservations_enabled", "new_checkout_ui")
├── default_state (on | off)
├── rollout_rules (jsonb — % of tenants, allowlist, denylist)
```

**Layering rule:** entitlement check first (does this plan include the feature?), then engineering flag (is it rolled out yet?). Both must pass.

For most Phase 0 primitives we own a pair: an engineering flag during rollout (eventually removed) + an entitlement key (permanent, tied to billing).

---

## 6. Custom Storefront Surface

This is the headless commerce backend — what we expose to merchants who build their own custom site (or use a Next.js/Nuxt starter).

### 6.1 API surface (REST + GraphQL)

Two flavors of the same data, behind the same auth:

- **REST** at `/v1/storefront/...` — pragmatic, easy to call from any frontend, well-documented
- **GraphQL** at `/v1/storefront/graphql` — single endpoint, fetch exactly what PDP/PLP needs

Both use the same underlying service layer.

**Endpoint groups (REST shape; GraphQL mirrors it):**

```
Catalog (read-only, public)
  GET  /v1/storefront/products                   list with filters, search, pagination
  GET  /v1/storefront/products/{slug}            full PDP data
  GET  /v1/storefront/categories                 tree
  GET  /v1/storefront/collections                merchant-curated groups

Cart (session-scoped, soft-reserves stock)
  POST /v1/storefront/cart                       create cart, returns cart_token
  GET  /v1/storefront/cart/{token}               read
  POST /v1/storefront/cart/{token}/items         add line
  PATCH /v1/storefront/cart/{token}/items/{id}   update qty
  DELETE /v1/storefront/cart/{token}/items/{id}  remove
  POST /v1/storefront/cart/{token}/discount      apply code

Pricing helpers
  POST /v1/shipping/calculate                    rates for destination
  POST /v1/tax/calculate                         line-item taxes
  GET  /v1/storefront/currencies                 supported + FX

Checkout (two paths)
  POST /v1/storefront/checkout/session           returns hosted-checkout URL
  POST /v1/storefront/orders                     create order from cart, payment_intent_id

Customer (optional — merchants can use their own auth instead)
  POST /v1/storefront/customers                  signup
  POST /v1/storefront/customers/login            email+password OR magic-link
  GET  /v1/storefront/customers/me               profile
  GET  /v1/storefront/customers/me/orders        order history

Misc
  GET  /v1/storefront/policies                   shipping/returns/privacy/T&C content
  GET  /v1/storefront/store                      merchant store info
```

### 6.2 Authentication

Two auth contexts:

1. **Storefront API key** — public, shipped in merchant frontend code. Scoped to read-only catalog + cart + checkout-session. Rate-limited per origin.
2. **Customer session token** — JWT issued on customer login (email/password or magic-link). Used for order history, saved addresses. Standard refresh-token flow.

Storefront API key is **per-channel** (each headless channel gets its own), so a merchant can rotate keys per site without affecting others.

Server-to-server use (custom site's backend creating orders) uses a separate **secret API key** per channel — full read+write, used only from the merchant's own server.

### 6.3 Hosted checkout

When a custom site uses Path 1 (hosted checkout):

1. Site calls `POST /v1/storefront/checkout/session` with cart token → IMS returns `{checkout_url, expires_at}`
2. Site redirects shopper to `checkout_url` (`checkout.merchantdomain.com/c/abc123` via CNAME, or `pay.ourdomain.com/c/abc123` if no custom domain)
3. Hosted checkout collects:
   - Email
   - Shipping address (or auto-skipped for digital/service/donation)
   - Shipping method (calculated via shipping engine)
   - Tax shown (calculated via tax engine; respects channel's inclusivity setting)
   - Payment via merchant's BYO PSP
4. On payment success → IMS creates order, fires webhooks, sends confirmation email, redirects to merchant-configured success URL with `?order_id=`
5. On abandonment → soft reservation expires after TTL, abandoned-cart email fires (if email captured)

**Customization:** merchant configures logo, color scheme, footer policies, custom CSS hooks. Hosted checkout speaks the channel's currencies and shopper's locale.

### 6.4 BYO payment connectors (launch set)

| Provider | Region | Method |
|---|---|---|
| **Stripe** | Global / generic | OAuth (Stripe Connect Standard) |
| **Razorpay** | India | API key |
| **PayPal** | Global | OAuth |

**Pattern:**
- Merchant connects provider in admin web → IMS stores credentials encrypted
- Hosted checkout uses provider's drop-in/SDK on the client side; IMS confirms charge server-side via webhook
- We never see card data; PCI scope minimized
- 3DS / SCA flows handled by provider SDK
- Failed charges → friendly retry

**Adding a new provider** = implementing a small `PaymentProvider` interface (`create_intent`, `confirm`, `refund`, `webhook_handler`). Easy to extend. Midtrans/Xendit/Interac come back when Indonesia/Canada are reactivated post-Phase 3.

### 6.5 Path 2 — merchant runs their own checkout

For merchants whose custom site fully owns checkout (existing custom flow, specialized PSP, B2B order workflow):

- Merchant's site collects cart, address, tax, payment via their own integration
- Posts `POST /v1/storefront/orders` with the full payload (line items, customer, addresses, totals, payment_status, payment_reference, shipping_method, etc.)
- IMS validates totals against its own calculations; rejects if drift > configurable threshold (catches bugs)
- Creates order, decrements stock, fires webhooks/emails

### 6.6 Storefront SDKs (Phase 2)

- **TypeScript/JavaScript SDK** (browser + Node) — wraps REST API with typed methods
- **Reference Next.js storefront template** — open-source, deployable to Vercel in one click

Phase 2 — but the API is designed *now* with these clients in mind so we don't repaint the bikeshed later.

---

## 7. Online-Only Mode + Conversion Path

### 7.1 Design choice: keep shops always

The `shops` table stays as the canonical location entity for **every** tenant. We do NOT introduce a separate "online-only" branch in the data model. That would split every shop-aware query in two and tangle the codebase forever.

Instead: when a tenant signs up online-only, we **auto-create a single virtual shop**.

```
shops
├── id, tenant_id, name="Online Store" (rename-able later)
├── kind = "virtual" | "physical"  ← NEW column
├── address, timezone, currency_code (defaulted)
└── ...
```

The `kind` field is the discriminator. Stock movements, orders, channels, inventory pools all keep working unchanged — they just reference a virtual shop instead of a physical one.

### 7.2 Onboarding flow

Sign-up wizard asks: **"How will you sell?"**

- Online only (e-commerce, marketplace, custom site)
- In-store only (physical retail / POS)
- Both online and in-store

The answer determines:
- What admin web looks like post-signup
- Which Phase 0 primitives surface in UI
- What the auto-created shop looks like (virtual vs prompts for physical address)
- Which sample channels are pre-created (online-only → one headless channel scaffolded; in-store-only → one POS channel; both → both)

Stored as: `tenant.business_type = "online" | "retail" | "hybrid"`.

### 7.3 UI gating by business_type

| Surface | online | retail | hybrid |
|---|---|---|---|
| Shops management page | hidden | shown | shown |
| Per-shop assignment in Add-Product | auto-pinned to virtual shop | exposed | exposed |
| Transfer Orders | hidden | shown | shown |
| Cashier device enrollment | hidden | shown | shown |
| Shifts management | hidden | shown | shown |
| Inventory Pools UI | simplified | shown if multi-shop | shown |
| Channels page | shown | shown if connectors used | shown |
| POS-specific reports | hidden | shown | shown |
| E-commerce-specific reports | shown | shown if connectors used | shown |

Backend stays uniform — only UI hides surfaces.

### 7.4 Conversion path: online → hybrid

1. Settings → "Enable physical store" CTA
2. Wizard collects physical shop details (address, timezone, currency, opening hours)
3. New shop created with `kind=physical`
4. `tenant.business_type` flips: `online` → `hybrid`
5. Admin web reveals previously-hidden surfaces
6. Original virtual shop **stays** — still where online channel inventory lives
7. Inventory pool UI now meaningfully exposes "which shops feed which channels"
8. Optional first-run guide: "Move existing online inventory to physical store" (creates a transfer order)

**No data migration, no schema changes** — the same shop and inventory model has been there from day 1; UI just opens up.

### 7.5 Reverse path: retail → hybrid online

Mirror flow: retail-only tenant adds an online channel via "Sell Online" CTA → walks through Shopify connect / Woo connect / headless API key creation → `tenant.business_type` flips `retail` → `hybrid`. Existing physical shops remain; an inventory pool gets created bridging them to the new online channel.

### 7.6 Why this design

- **No bifurcated data model** — shop-aware queries stay single-path
- **Reversible** — business_type is a UI hint, not a hard constraint
- **Migrations stay clean** — no `if business_type == online` in schema migrations
- **Onboarding is simple** — three questions become three setup flavors
- **Conversion is a flag flip + reveal**, not a data import

---

## 8. Cherry-Pick from the 56-Domain Retail Roadmap

Disposition for every domain:

- **KEEP** — works for both retail + e-commerce; build it in the new pivot roadmap
- **SUBSUME** — folded into a Phase 0/1 e-commerce primitive (no longer a standalone domain)
- **DEFER** — retail-only or out-of-scope geography; comes back after the pivot stabilizes
- **CUT** — retail-only, unlikely to return unless explicitly re-prioritized
- **DONE** — already shipped

### 8.1 General Retail Domains

| # | Name | Disposition | Rationale |
|---|---|---|---|
| 1 | Customer Management (CRM) | **KEEP** | Foundational for unified cross-channel customer + order analytics (§5.11) |
| 2 | Returns & Refunds | **KEEP** (redesigned) | Stock impact handled by Phase 0 inbound-returns; full UI workflow becomes a unified retail+ecom RMA module (Phase 2/3) |
| 3 | Product Catalog (gaps) | **KEEP** (partial subsume) | UoM, max stock, tags, price history valuable for both; "per-shop availability" subsumed into channel/inventory-pool model |
| 4 | Supplier & Purchasing (gaps) | **KEEP** | E-commerce merchants need POs and supplier management |
| 5 | Inventory Operations (gaps) | **KEEP** | Multi-location stock, low-stock alerts work for both; transfer orders relevant once online merchant goes hybrid |
| 6 | Discounts & Promotions | **SUBSUME** | Folded into Phase 0 §5.7 Discounts module |
| 7 | Loyalty & Rewards | **KEEP** | Cross-channel loyalty is a competitive differentiator |
| 8 | Gift Cards & Vouchers | **SUBSUME** | Folded into Phase 0 §5.6 Gift Card product type |
| 9 | Reporting (gaps) | **KEEP** | P&L, COGS, inventory valuation, dead stock all valuable across channels |
| 10 | Cash Management (gaps) | **DEFER** | POS-only |
| 11 | Notifications & Alerts (gaps) | **SUBSUME** + KEEP | Email/WhatsApp infra subsumed into §5.8 + §5.12; specific alerts keep |
| 12 | Batch / Lot / Expiry Tracking | **KEEP** | E-commerce in food / cosmetics / pharma needs FEFO and expiry tracking too |
| 13 | Invoicing & Credit Notes | **KEEP** (expanded) | Hostinger-style live invoice preview; B2B e-commerce needs invoicing |
| 14 | Receipt & Document Customization | **KEEP** (split) | Receipt template = POS-only; invoice/packing slip customization = both channels |
| 15 | POS Advanced Features | **DEFER** | POS-specific |
| 16 | Tax Management (gaps) | **SUBSUME** | Folded into Phase 0 §5.5 tax engine |
| 17 | Integration Ecosystem (gaps) | **SUBSUME** | Shopify/Woo become core to the pivot; CSV import/export folded into Phase 1; Razorpay folds into payment connectors |
| 18 | Product Bundles & Kits | **KEEP** | Bundles are huge in e-commerce |
| 19 | Auto-reorder & Smart Purchasing | **KEEP** | Online sellers benefit even more from auto-reorder |
| 20 | Security & Compliance | **KEEP** (priority bump) | 2FA, session mgmt, GDPR more critical with public-facing e-commerce data |
| 21 | Platform & Onboarding | **SUBSUME** + KEEP | Onboarding wizard expanded with online/retail/hybrid question (§7.2); usage limits → entitlements (§5.13a); white-labeling stays separate |
| 22 | Staff Scheduling & Time Tracking | **DEFER** | Retail-staff-specific |
| 43 | Product Enrichment | **SUBSUME** + KEEP | Multi-image, image upload subsumed into §5.9; multi-language product names → Phase 1 i18n; price guard + MRP keep |
| 44 | Advanced POS Operations | **DEFER** (mostly) | POS-specific; tax exemption per customer kept (B2B online) |
| 45 | Returns & Exchange (depth) | **KEEP** | Renamed to RMA module; works for both channels |
| 46 | Customer Intelligence | **KEEP** | Birthday automation, CLV, at-risk customers all channel-agnostic |
| 47 | Advanced Inventory Operations | **KEEP** | Stocktakes, blind count, inventory aging, GRN all valuable |
| 48 | Supplier Depth | **KEEP** | Multi-contact, performance notes, invoice matching cross-cut |
| 49 | Device & POS Health | **DEFER** | Cashier-device-specific |
| 50 | Customer Feedback & NPS | **KEEP** (expanded) | E-commerce NPS via post-purchase email |
| 51 | Advanced Analytics & Reporting | **KEEP** (expanded) | ABC, basket affinity, inter-store → inter-channel comparison |
| 52 | Local Delivery Management | **KEEP** | Cross-channel: POS-driven delivery + e-commerce local delivery share the model |
| 53 | Fraud Prevention & Anomaly Detection | **KEEP** (reframed) | Cashier-pattern alerts = POS-only; chargeback / BIN attack / order fraud added for e-commerce |
| 54 | Warranty & After-sales Tracking | **KEEP** | Cross-channel — warranty record on any sale |
| 55 | Customer Self-service & Catalogue Sharing | **KEEP** (expanded) | Self-service portal = huge for e-commerce; catalogue sharing → B2B-friendly |
| 56 | Advanced Promotions | **SUBSUME** | Folded into Phase 0 §5.7 Discounts module |

### 8.2 India-Specific Domains

| # | Name | Disposition | Rationale |
|---|---|---|---|
| 23 | GST Compliance | **SUBSUME** + KEEP | Tax pieces fold into §5.5 tax engine; GST-specific UI/exports stay as India layer |
| 24 | Indian Payment Methods | **SUBSUME** | UPI / Razorpay fold into payment connectors; COD becomes a cross-channel tender |
| 25 | WhatsApp Integration | **KEEP** (priority bump) | Critical for Indian e-commerce — abandoned cart, status updates, ordering via WhatsApp |
| 26 | Khata / Udhar | **KEEP** | Primarily retail, but B2B e-commerce can use credit-terms variant |
| 27 | Barcode Generation & Label Printing | **DEFER** | Retail/warehouse-only |
| 28 | Tally & Accounting Export | **KEEP** | Indian online merchants also need Tally; folds into integrations marketplace |
| 29 | Indian Localisation | **KEEP** | Foundational for any Indian merchant |

### 8.3 i18n Foundation

| # | Name | Disposition | Rationale |
|---|---|---|---|
| 30 | i18n Framework & Translation Infrastructure | **KEEP** (priority bump) | Storefront-facing language becomes critical (per-channel "store language") |
| 31 | Timezone per Tenant & Shop | **DONE** | Already shipped |
| 32 | Country-aware Tax Engine | **SUBSUME** | Folded into §5.5 tax engine (this *is* the engine) |
| 33 | Country-aware Address & Phone Validation | **KEEP** (priority bump) | Critical for e-commerce shipping addresses |

### 8.4 Indonesia-Specific Domains (DEFER ALL)

| # | Name | Disposition | Rationale |
|---|---|---|---|
| 34 | QRIS & Indonesian Payment Methods | **DEFER** | Indonesia out-of-scope at launch; revisit post-Phase 3 |
| 35 | PPN Compliance | **DEFER** | Same |
| 36 | Indonesian E-commerce Integration | **DEFER** | Same |
| 37 | Indonesian Localisation | **DEFER** | Same |

### 8.5 Canada-Specific Domains (DEFER ALL)

| # | Name | Disposition | Rationale |
|---|---|---|---|
| 38 | Province-aware Multi-tax | **DEFER** | Canada out-of-scope at launch; revisit post-Phase 3 |
| 39 | Canadian Payment Methods | **DEFER** | Same |
| 40 | Canadian Compliance & Privacy | **DEFER** | Same |
| 41 | Canadian Localisation & Language | **DEFER** | Same |
| 42 | Canadian Accounting Integrations | **DEFER** | Same |

### 8.6 Disposition summary

| Disposition | Count |
|---|---|
| KEEP | 22 |
| SUBSUME | 11 |
| DEFER | 15 |
| CUT | 0 |
| DONE | 1 |
| **Total** | **49** (some domains carry multiple dispositions split across pieces; counted under primary) |

The retail roadmap mostly survives. Almost everything either keeps as-is, gets folded into a more general e-commerce primitive (a net positive — fewer separate domains to track), or defers as POS-specific or out-of-scope-geography. Nothing gets cut entirely.

The tax engine, currency engine, and payment connector framework stay **designed for multi-country pluggability**. Deferring Indonesia and Canada ≠ baking in single-country assumptions; reactivating those markets post-Phase 3 is additive, not a rewrite.

---

## 9. Phasing Breakdown

Four phases. **No time estimates** — those go in the implementation plan.

### 9.1 Phase 0 — Foundations (no merchant-visible launch)

**Goal:** build primitives every channel will consume; ship behind feature flags + entitlements; validate with retail merchants before any e-commerce launch.

**Includes:**
- 5.1 Channel & inventory pool model
- 5.2 Stock reservation engine
- 5.3 Multi-currency engine
- 5.4 Shipping engine
- 5.5 Tax engine + inclusivity toggle (India + generic at launch)
- 5.6 Product type expansion
- 5.7 Discounts module
- 5.8 Email infrastructure + domain auth wizard
- 5.9 Catalog enrichment for e-commerce
- 5.10 Online-only mode + conversion path (Section 7)
- 5.11 Customer model unification across channels
- 5.12 Webhooks-out (merchant-facing event bus)
- 5.13a Plan entitlements in billing module
- 5.13b Engineering rollout flags

**Exit criteria:**
- All primitives behind flags + entitlements, in production
- Retail merchants exercising new product types, multi-currency, discounts, email infra
- Internal smoke tests passing on `cart → reservation → order → stock movement → webhook → email` end-to-end (using a test channel)
- No data-model migrations remaining for the primitives

**Dependencies:** None.

### 9.2 Phase 1 — Channel Launch

**Goal:** three channels live in parallel — Shopify, WooCommerce, headless API. First paying e-commerce customers.

**Includes:**
- Shopify connector (OAuth, catalog push, stock push, order/refund pull, customer sync, hybrid catalog import + reconciliation queue)
- WooCommerce connector (equivalent shape via Woo REST API + webhooks)
- Headless API (REST + GraphQL surface from Section 6: catalog, cart, orders, shipping calc, tax calc, customer; storefront API key + secret API key; rate limiting)
- Path 2 thin endpoint (`POST /v1/storefront/orders` with totals reconciliation)
- CSV import for bulk catalog and customer onboarding (Domain 17 piece)
- Onboarding wizard with online/retail/hybrid question + setup flows
- Channels admin UI (connect, status, sync logs, conflict queue)
- Inbound returns hooks (Shopify/Woo refund webhooks → `return_received` movements)
- Engineering flag flip: Phase 0 primitives become default-on for new merchants

**Exit criteria:**
- All three channels independently usable
- A test merchant can fully onboard online-only and start taking orders on a custom site (Path 2) and on Shopify
- Inventory stays consistent across POS + Shopify + Woo + headless under concurrent load
- Webhook reliability >99% with retry / dead-letter

**Dependencies:** Phase 0 complete.

### 9.3 Phase 2 — Hosted Checkout + Payments + Polish

**Goal:** hosted checkout product launches with BYO payment integrations, completing the headless backend offering.

**Includes:**
- Hosted checkout UI (branded, mobile-optimized, supports inclusive vs exclusive tax, currency switching, multi-language)
- Payment connector framework (`PaymentProvider` interface)
- Provider integrations: Stripe Connect Standard, Razorpay, PayPal
- Custom domain support (CNAME mapping for `checkout.merchantdomain.com` per channel)
- Abandoned cart emails (uses Phase 0 email infra + reservation TTL)
- Order confirmation, shipment, refund emails with template editor + live preview
- Customer self-service portal (Domain 55) — account, order history, magic-link login
- TypeScript SDK for the storefront API
- Reference Next.js storefront template (open-source)

**Exit criteria:**
- Hosted checkout end-to-end working in test mode for all 3 launch payment providers
- A merchant who only knows JavaScript can install the Next.js template, connect their IMS, and have a working store in <1 hour

**Dependencies:** Phase 1 complete (storefront API stable, channels working).

### 9.4 Phase 3 — Cross-Channel Polish & Advanced Features

**Goal:** unified analytics, advanced commerce features, integrations marketplace.

**Includes:**
- Unified channel + shop analytics (every report adds a channel filter; new "by channel" rollups; inter-channel comparison)
- Customer 360 across channels (CLV, channel attribution, online + offline activity in one view)
- Integrations marketplace UI (Shopify, Woo, Tally, Razorpay, Stripe, Xero/Zoho via webhooks, etc.)
- WhatsApp integration (Domain 25): abandoned cart, order status, marketing — using same patterns as email infra
- Customer-side intelligence (Domain 46): birthday automation, at-risk dashboards, CLV
- Advanced analytics (Domain 51): ABC, basket affinity, inter-channel comparison
- Loyalty & rewards (Domain 7): points across channels, store credit cross-channel
- Bundles & kits (Domain 18): unified bundle product type
- Auto-reorder (Domain 19)
- Returns/RMA depth (Domain 45): full workflow on top of inbound-returns foundation
- Local delivery management (Domain 52)
- NPS / customer feedback (Domain 50)
- Indian-specific final pieces: Tally export (Domain 28)
- Live invoice preview UX (Hostinger-inspired)

**Exit criteria:** each sub-feature ships independently behind entitlements; no global cutover gate.

**Dependencies:** Phase 2 complete.

### 9.5 Phase 4+ — Deferred Domains (post-pivot)

Domains parked from §8's DEFER bucket — picked up after the pivot is stable:

**Retail/POS-only:**
- POS Advanced Features (Domain 15)
- Cash Management (Domain 10)
- Staff Scheduling (Domain 22)
- Advanced POS Operations (Domain 44 mostly)
- Device & POS Health (Domain 49)
- Barcode Generation & Label Printing (Domain 27)

**Indonesia (reactivation):**
- Domains 34, 35, 36, 37 (QRIS, PPN, Shopee/Tokopedia/TikTok connectors, Indonesian localisation)
- Add Midtrans, Xendit to payment connector launch set

**Canada (reactivation):**
- Domains 38, 39, 40, 41, 42 (provincial tax, Interac/Apple Pay/Google Pay, BN/CASL/PIPEDA compliance, Canadian localisation, QuickBooks/Wave/FreshBooks)

These come back when retail merchants demand them or when Indonesia/Canada are re-prioritized as markets.

### 9.6 Cross-cutting concerns (active across all phases)

- Migrations stay backwards-compatible; every schema change ships behind a flag; dual-write during cutover
- Existing retail merchants are never broken — every Phase 0 primitive must coexist with existing single-currency-per-tenant, single-channel, physical-only flows
- Documentation lands with the code — API docs, migration notes, merchant-facing setup guides per phase
- Each phase has a launch checklist baked into the implementation plan: load test, security review, billing entitlement audit, support docs

---

## 10. Non-Goals

These are choices, not omissions.

- **Merchant of record / acquiring license.** Funds flow through merchants' own PSP accounts (BYO). MoR revisited only post-Phase 3 on demand.
- **Full storefront builder / themes engine.** No drag-and-drop site builder. Merchant builds their own site (or uses our Next.js template).
- **Full RMA workflow at launch.** Phase 0 lays the foundation (inbound returns → stock movements). Customer-initiated returns with reason codes, condition assessment, restocking workflow = later domain.
- **Order fulfillment workflow.** No pick/pack/warehouse-management module. Channels keep their own fulfillment status; we mirror it.
- **Subscriptions / recurring billing for shoppers.** Out of scope. (Tenant subscriptions to our SaaS are a separate, existing concern.)
- **Marketplaces** (B2C marketplace where many sellers list under one merchant). Out of scope.
- **Built-in shipping label printing / carrier integration.** We calculate rates; we don't generate ShipStation/EasyPost-style labels. Future via integrations marketplace.
- **Live chat / customer support tooling.** Out of scope; integrate via webhooks + third-party (Intercom, Zendesk).
- **POS depth features during the pivot window.** Domains 10, 15, 22, 27, 44, 49 are parked.
- **Multi-tenant per shopper / shopper accounts that span tenants.** Each tenant's customers are isolated.
- **Indonesia + Canada market features at launch.** Deferred to post-Phase 3.

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Phase 0 scope creep — primitives keep growing as edge cases surface | High | Slows everything | Spec lock + dedicated implementation plan per primitive; defer scope to Phase 1+ aggressively |
| Multi-currency complexity bleeds into every feature | Medium | Pervasive bugs | Strict rule: every monetary column has currency_code sibling; never trust tenant-wide currency; FX snapshot frozen on order rows |
| Stock reservation race conditions under concurrent channel load | Medium | Oversells / drift | Postgres-level locking on reservation insert; load-test the reservation engine before Phase 1 ship |
| Hybrid catalog reconciliation gets confusing on first connect | Medium | Onboarding friction | Reconciliation queue UI is first-class; clear "imported from Shopify" badges; bulk merge tools |
| Webhook reliability to merchants (custom storefronts depend on it) | Medium | Stale UI on merchant side | Standard pattern: HMAC, retries with exponential backoff, dead-letter, replay UI |
| Email deliverability when merchants don't complete domain auth | High | Spam folder, support tickets | Domain auth wizard mandatory in onboarding; can't send from merchant's domain until verified; fallback to shared sending domain with warnings |
| Payment provider flakiness (Razorpay has less mature APIs than Stripe) | Medium | Failed checkouts in regions | Per-provider integration tests; circuit breakers; fallback to manual order creation; monitoring per provider |
| Existing retail merchants resist Phase 0 changes | Low | Support burden | All changes additive + flagged; existing flows unchanged; entitlements gate visibility |
| Entitlement vs engineering flag layering bugs | Medium | Wrong access / billing leaks | Strict order: entitlement → engineering flag; service-layer enforces; integration tests for plan × flag matrix |
| Shopify/Woo API rate limits during initial sync of large catalogs | Medium | Slow first connect | Rate-aware sync with checkpointing; resumable; UI shows progress |
| Online-only → hybrid conversion surprises merchants (UI suddenly grows) | Low | Confusion | Conversion wizard explains what's about to appear; opt-out per surface for the first 30 days |
| Custom storefront API key leakage (public key shipped in frontend) | High (by design) | Abuse / scraping | Strict scope on public key (read-only catalog + cart only); server-side secret key for write ops; rate limiting per origin; bot detection |
| Multi-currency FX drift between order time and refund time | Medium | Refund mismatch | Refund uses original FX snapshot from order row, not current rate; merchant-visible reconciliation report |
| Indian tax law edge cases (reverse-charge GST, composition scheme) | Medium | Compliance issues | Engine designed for compound + region rules; tax-class per product handles edge cases; manual override always available |

---

## 12. Open Questions (parked for later)

These don't block the spec but should be revisited during/after Phase 1:

- Headless API rate limit per plan tier — TBD when real usage patterns emerge
- Whether to offer a "lite" hosted checkout (no domain customization, no template branding) for free-tier merchants
- Storefront SDK language coverage beyond TypeScript (Python? PHP? — likely WontFix unless customer demand)
- MoR offering — revisit after Phase 3 once we see how many merchants get stuck on PSP setup
- When to reactivate Indonesia / Canada — depends on Phase 3 stability + go-to-market signals

---

*End of design. Implementation plan to follow via writing-plans skill.*
