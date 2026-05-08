# E-commerce Architecture

Deep dive on the e-commerce layer built on top of the IMS inventory backend. Covers channels, storefront, checkout, payments, shipping, tax, discounts, webhooks, and customer auth.

See also:
- `docs/storefront-api.md` — practical guide for headless storefront developers
- `docs/architecture.md` — full system architecture

---

## 1. Channels

A **channel** is the fundamental abstraction — a named sales surface that connects inventory to buyers.

```
Tenant
└── Channel (type: headless | shopify | woocommerce | pos | manual)
    ├── inventory_pool_id → InventoryPool → shops[]
    ├── currency_code
    ├── config: {
    │   payment_provider: "stripe" | "razorpay",
    │   stripe_secret_key: "<encrypted>",
    │   stripe_publishable_key: "pk_...",
    │   checkout_success_url: "https://...",
    │   checkout_domain: "checkout.yourstore.com",  # optional CNAME
    │   razorpay_key_id: "rzp_...",
    │   razorpay_key_secret: "<encrypted>",
    │   shopify_shop_domain: "...",                 # if type=shopify
    │   woocommerce_store_url: "...",               # if type=woocommerce
    │ }
    └── tax_included_in_price: bool | null
```

**Before creating a channel**, create an inventory pool and assign shops to it. This determines which physical locations fulfil online orders.

### Channel admin API

```
GET    /v1/admin/channels
POST   /v1/admin/channels
PATCH  /v1/admin/channels/{id}
DELETE /v1/admin/channels/{id}

POST   /v1/admin/channels/{id}/payment/setup-stripe
POST   /v1/admin/channels/{id}/payment/setup-razorpay
GET    /v1/admin/channels/{id}/payment/config

POST   /v1/admin/channels/{id}/shopify/connect
POST   /v1/admin/channels/{id}/shopify/sync-catalog
POST   /v1/admin/channels/{id}/shopify/sync-inventory
POST   /v1/admin/channels/{id}/shopify/import-catalog

POST   /v1/admin/channels/{id}/woocommerce/connect
POST   /v1/admin/channels/{id}/woocommerce/sync-catalog
POST   /v1/admin/channels/{id}/woocommerce/import-catalog
```

---

## 2. Inventory pools

An inventory pool groups one or more shops. When a storefront order comes in, stock is drawn from the pool's shops according to the fulfillment policy.

```
InventoryPool
├── name
├── fulfillment_policy: "fulfill_from_primary" | "split_proportionally" | "manual_at_fulfillment"
└── shop_ids[]  (via inventory_pool_shops junction)
```

Stock availability for a channel = sum of stock movements across all shops in the pool, minus active reservations:

```python
# services/api/app/services/inventory_pool_service.py
available_stock_for_channel(db, channel, product_id)
```

**Soft reservations:** When a product is added to cart, stock is soft-reserved for 15 minutes (configurable). On checkout completion, the reservation is committed and converted to a sale movement. On session expiry, `sweep_expired_reservations` releases the reservation.

---

## 3. Storefront API

All endpoints under `/v1/storefront/` are public-facing. They require only an `X-Channel-Id` header (UUID of the channel). Rate limited at 120 req/min per IP.

### 3.1 Catalog

```
GET /v1/storefront/products?q=&status=&page=&per_page=
GET /v1/storefront/products/{slug_or_id}
```

Returns `StorefrontProductOut` — a subset of the internal `Product` model suitable for display.

### 3.2 Cart

```
POST   /v1/storefront/cart                        → create cart, get cart_token
GET    /v1/storefront/cart/{cart_token}           → fetch cart with items
POST   /v1/storefront/cart/{cart_token}/items     → add item (qty + price resolved server-side)
DELETE /v1/storefront/cart/{cart_token}/items/{id} → remove item
GET    /v1/storefront/cart/{cart_token}/summary   → totals with discount/tax/shipping
POST   /v1/storefront/cart/{cart_token}/discount  → apply discount code
```

### 3.3 Checkout (direct order submit)

For storefronts handling their own payment UI:
```
POST /v1/storefront/orders   → submit order with payment_provider + payment_reference
```

### 3.4 Customer auth

```
POST /v1/storefront/auth/otp/request   { "email": "..." }
POST /v1/storefront/auth/otp/verify    { "email": "...", "code": "123456" }
```

Verification returns a customer JWT. Include it as `Authorization: Bearer <token>` for authenticated endpoints.

### 3.5 Customer portal

```
GET /v1/storefront/customers/me                        → profile (email, name, customer_id)
GET /v1/storefront/customers/me/orders                 → order history with tracking fields
GET /v1/storefront/customers/me/orders/{id}/tracking   → shipment event timeline
```

Order history includes: `fulfillment_status`, `awb_code`, `tracking_url`, `carrier_name`, `shipped_at`, `delivered_at` — customers can track their shipments directly from the storefront.

---

## 4. Hosted checkout

IMS can host the checkout page itself — useful when you don't want to build a custom payment UI.

### Flow

```
POST /v1/storefront/checkout/session   { cart_token }
  → { session_token, checkout_url, expires_at }

# Redirect user to checkout_url (or embed it)
GET /checkout/{session_token}
  → HTML page with coupon field, customer info, Stripe/Razorpay payment form

# After payment:
POST /v1/checkout/{session_token}/complete
  → { status: "completed", order_id, redirect_url }
```

### Discount codes in hosted checkout

The hosted checkout page has a coupon field. On "Apply":
```
POST /v1/checkout/{session_token}/apply-discount  { code: "SAVE10" }
DELETE /v1/checkout/{session_token}/discount       → remove applied discount
```

Stripe payment intent is created **lazily** (when "Pay" is clicked, not on page load), so the final amount after discount is used.

### Custom checkout domain (CNAME)

Set `checkout_domain` in channel config to serve checkout from your own domain:
```
PATCH /v1/admin/channels/{id}  { "config": { "checkout_domain": "checkout.yourstore.com" } }
```

The merchant must point their domain to the API via DNS/reverse proxy. IMS builds the `checkout_url` using this domain automatically.

### Templates

`services/api/templates/checkout.html` — Jinja2 template rendered server-side. Supports both Stripe Elements (inline card input) and Razorpay (modal).

---

## 5. Payment providers

Payment credentials are stored **encrypted** in `channel.config` using `encrypt_secret()`/`decrypt_secret()` from `services/api/app/services/email_service.py`. Never store plaintext secrets.

### Stripe setup

```
POST /v1/admin/channels/{id}/payment/setup-stripe
{
  "stripe_secret_key": "sk_live_...",
  "stripe_publishable_key": "pk_live_...",
  "checkout_success_url": "https://yourstore.com/order/success"
}
```

Stripe payment intent is created with `automatic_payment_methods: { enabled: True }` — supports cards, wallets, UPI, etc. depending on region.

### Razorpay setup

```
POST /v1/admin/channels/{id}/payment/setup-razorpay
{
  "razorpay_key_id": "rzp_live_...",
  "razorpay_key_secret": "...",
  "checkout_success_url": "https://yourstore.com/order/success"
}
```

Razorpay opens a modal checkout on the hosted page.

---

## 6. Discounts

Discounts support three types: `percentage` (value in basis points), `fixed_amount` (value in cents), `free_shipping`.

```python
# Discount model key fields:
code: str | None        # None = automatic (no code required)
discount_type: str      # percentage | fixed_amount | free_shipping
value_bps: int | None   # 1000 = 10%
value_cents: int | None # 500 = ₹5.00
channel_id: UUID | None # None = applies to all channels
min_subtotal_cents: int | None
max_uses_total: int | None
max_uses_per_customer: int | None
starts_at: datetime | None
expires_at: datetime | None
```

### Admin API

```
GET    /v1/admin/discounts
POST   /v1/admin/discounts
PATCH  /v1/admin/discounts/{id}   → toggle active/archived, update limits
DELETE /v1/admin/discounts/{id}
```

Usage is recorded in `discount_uses` on every order completion. The apply logic lives in `services/api/app/services/discount_service.py`.

---

## 7. Shipping

IMS has two shipping layers:

1. **Static zones/rates** — rate tables configured per channel for checkout price display
2. **Carrier dispatch** — actual shipment creation via a carrier API (Shiprocket first)

### 7.1 Static zones and rates

```
ShippingZone
├── channel_id
├── name
├── countries: ["IN", "US", ...]   # empty = global
├── is_catch_all: bool             # fallback when no specific zone matches
└── ShippingRate[]
    ├── name
    ├── base_price_cents
    ├── currency_code
    ├── free_above_cents: int | null   # free shipping threshold
    └── condition_type: "none"
```

**Admin API:**
```
GET    /v1/admin/shipping/zones
POST   /v1/admin/shipping/zones
DELETE /v1/admin/shipping/zones/{id}

GET    /v1/admin/shipping/zones/{id}/rates
POST   /v1/admin/shipping/zones/{id}/rates
DELETE /v1/admin/shipping/zones/{id}/rates/{rate_id}

POST   /v1/shipping/calculate   → list of applicable rates
```

### 7.2 Carrier dispatch (Shiprocket)

When a channel has `shipping_provider: "shiprocket"` in its config, every confirmed order is automatically dispatched via RQ:

```
order.confirmed
    └── dispatch_shipment (RQ task)
            └── ShiprocketProvider.create_shipment()
                    ├── POST /orders/create/adhoc   → Shiprocket order
                    ├── POST /courier/assign/awb    → AWB code + carrier
                    ├── POST /courier/generate/pickup
                    └── GET  /courier/generate/label
            └── persists AWB, tracking_url, carrier_name, label_url on order
            └── sets fulfillment_status = "processing"
            └── sends shipping notification email
            └── fires order.shipped outbound webhook
```

**Order fulfillment_status values:**

| Status | Meaning |
|--------|---------|
| `pending` | Not yet dispatched |
| `processing` | Dispatched, awaiting pickup |
| `shipped` | In transit |
| `out_for_delivery` | Out for delivery |
| `delivered` | Delivered to customer |
| `cancelled` | Cancelled before pickup |
| `returned` | RTO / return to origin |
| `failed` | Dispatch failed — retry via admin API |

**Inbound webhook (Shiprocket → IMS):**
```
POST /v1/webhooks/shiprocket/{channel_id}
Headers: X-Api-Key: <shiprocket_webhook_secret>
Body: { "awb": "...", "current_status": "Delivered", "updated_at": "...", "location": "..." }
```

Events are deduplicated on `(order_id, provider_event_id)` — safe to receive duplicates. On delivery, fires `order.shipped` outbound webhook to merchant backends.

**Admin setup API:**
```
POST   /v1/admin/channels/{id}/shipping/setup-shiprocket
       Body: { email, password, pickup_location }
       → validates credentials against Shiprocket API before storing (encrypted)

GET    /v1/admin/channels/{id}/shipping/config
DELETE /v1/admin/channels/{id}/shipping/config

POST   /v1/admin/ecommerce-orders/{id}/dispatch        → manual re-dispatch
POST   /v1/admin/ecommerce-orders/{id}/cancel-shipment → cancel before pickup
```

**Channel config keys added by Shiprocket setup:**
```json
{
  "shipping_provider": "shiprocket",
  "shiprocket_email": "store@example.com",
  "shiprocket_password": "<encrypted>",
  "shiprocket_pickup_location": "Warehouse-Mumbai",
  "shiprocket_channel_id": "",
  "shiprocket_webhook_secret": "<shared secret for webhook verification>"
}
```

**Adding a new carrier:**

The provider abstraction is in `services/api/app/services/shipping/`. To add Delhivery:
1. Create `services/api/app/services/shipping/delhivery/provider.py` implementing `ShippingProvider`
2. Register `"delhivery"` in `registry.py`
3. Done — the dispatch hook, webhook receiver pattern, and admin APIs are all generic

---

## 8. Tax

### Regions and rules

```
TaxRegion
├── name
├── country_code: "IN"
├── state_code: "MH" | null
└── TaxRule[]
    ├── tax_class: "standard" | "reduced" | "zero" | custom
    ├── label: "GST 18%"
    └── components: [
        { "label": "CGST", "rate_bps": 900 },   # 9%
        { "label": "SGST", "rate_bps": 900 }    # 9%
      ]
```

Tax components use basis points: 100 bps = 1%. Total GST 18% = CGST 9% (900 bps) + SGST 9% (900 bps).

### Admin API

```
GET    /v1/admin/tax/regions
POST   /v1/admin/tax/regions
DELETE /v1/admin/tax/regions/{id}

GET    /v1/admin/tax/regions/{id}/rules
POST   /v1/admin/tax/regions/{id}/rules
DELETE /v1/admin/tax/regions/{id}/rules/{rule_id}
```

### Tax-inclusive pricing

Set `channel.tax_included_in_price = True` for regions where prices are displayed tax-inclusive (e.g. Europe VAT). Calculation happens in `services/api/app/services/tax_service.py`.

---

## 9. Multi-currency pricing

Products have a base `unit_price_cents` in the tenant's default currency. Overrides for other currencies are in `product_prices`:

```
ProductPrice
├── product_id
├── channel_id: UUID | null   # null = applies to all channels
├── currency_code: "USD"
└── amount_cents: 999
```

### Admin API

```
GET    /v1/admin/products/{id}/prices
POST   /v1/admin/products/{id}/prices   { currency_code, amount_cents, channel_id }
DELETE /v1/admin/products/{id}/prices/{price_id}
```

FX rate auto-sync (ECB via frankfurter.app, ~30 currencies):
```
POST /v1/admin/fx-rates/sync   { "base": "INR", "targets": [] }
GET  /v1/admin/fx-rates/supported-currencies
```

---

## 10. Product variants

Products can have structured variants (size/colour/etc.) via `ProductVariant`:

```
ProductVariant
├── product_id              # parent product (display grouping)
├── sku                     # unique per tenant
├── name
├── options: { "size": "M", "colour": "Black" }   # JSONB, any key-value
├── unit_price_cents
├── status: "active" | "archived"
├── barcode | null
└── sort_order
```

### Admin API

```
GET    /v1/admin/products/{id}/variants
POST   /v1/admin/products/{id}/variants
PATCH  /v1/admin/products/{id}/variants/{vid}
DELETE /v1/admin/products/{id}/variants/{vid}
```

---

## 11. Order lifecycle

### Creation paths

Orders are created by four paths — all fire identical post-creation hooks:

| Path | Endpoint | Auth |
|------|---------|------|
| Hosted checkout | `POST /v1/checkout/{session}/complete` | Payment verification |
| Headless storefront | `POST /v1/storefront/orders` | Channel ID |
| Shopify webhook | `POST /v1/webhooks/shopify` | HMAC |
| WooCommerce webhook | `POST /v1/webhooks/woocommerce` | HMAC |

### Post-creation hooks (all paths)

1. Send order confirmation email (`send_order_confirmation`)
2. Fire `order.confirmed` outbound webhook to all subscribed endpoints
3. Record discount use (if discount was applied)
4. Enqueue `dispatch_shipment` RQ task if channel has `shipping_provider` configured (silent no-op if not)

### Refunds

```
GET  /v1/admin/ecommerce-orders          → list orders (filterable by status)
GET  /v1/admin/ecommerce-orders/{id}     → detail with lines, payments, refunds
POST /v1/admin/ecommerce-orders/{id}/refund   { amount_cents, reason }
```

Refund validation:
- Cannot refund cancelled or fully-refunded orders
- Cannot refund more than the remaining refundable amount (total - already refunded)
- Full refund → `order.status = "refunded"`
- Partial refund → `order.status = "partially_refunded"`

---

## 12. Outbound webhooks

Merchants register endpoints that IMS POSTs to when events occur.

```
POST   /v1/admin/webhooks/endpoints              → register (returns signing secret)
GET    /v1/admin/webhooks/endpoints
PATCH  /v1/admin/webhooks/endpoints/{id}         → enable/disable
DELETE /v1/admin/webhooks/endpoints/{id}
POST   /v1/admin/webhooks/endpoints/{id}/rotate-secret
GET    /v1/admin/webhooks/deliveries             → delivery log
GET    /v1/admin/webhooks/supported-events
```

**Supported events:**

| Event | Fired when |
|-------|-----------|
| `order.confirmed` | Order is created (all channels) |
| `order.shipped` | Shipment dispatch confirmed OR delivery confirmed via Shiprocket webhook |
| `order.updated` | Order status changes |

### Signing and verification

Each delivery includes:
```
X-IMS-Signature: sha256=<hmac_hex>
X-IMS-Event: order.confirmed
X-IMS-Delivery: <delivery_id>
```

To verify in your backend:
```python
import hashlib, hmac

def verify(body: bytes, secret: str, header_sig: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_sig)
```

### Delivery guarantee

- Max 3 attempts per delivery
- Retry delays: 5 minutes, then 30 minutes
- Status tracked in `webhook_delivery_logs` (pending → delivered / failed)
- Async via RQ — never blocks order creation

---

## 13. Email infrastructure

Merchants use their own email accounts. IMS never sends from a shared platform address.

### Configure email

```
# SMTP (Hostinger, Gmail, any provider):
POST /v1/admin/email/configure/smtp
{
  "provider": "smtp",
  "smtp_host": "smtp.hostinger.com",
  "smtp_port": 587,
  "smtp_username": "orders@yourstore.com",
  "smtp_password": "...",
  "from_email": "orders@yourstore.com",
  "from_name": "Your Store"
}

# Resend:
POST /v1/admin/email/configure/resend
{
  "provider": "resend",
  "resend_api_key": "re_...",
  "from_email": "orders@yourstore.com",
  "from_name": "Your Store"
}

# Test:
POST /v1/admin/email/test-send  { "to_email": "you@example.com" }
```

### Abandoned cart emails

`sweep_abandoned_carts` scans for carts with a pending `CheckoutSession` (meaning the customer entered their email but didn't complete payment) that haven't been updated for 2+ hours. Run it as a cron job or schedule with rq-scheduler:

```python
from app.worker.tasks import sweep_abandoned_carts
task_queue().enqueue(sweep_abandoned_carts, job_id="sweep-carts")
```

---

## 14. Shopify and WooCommerce integration

### Shopify

1. Create a headless or manual channel in IMS
2. Connect: `POST /v1/admin/channels/{id}/shopify/connect` with shop domain, access token, API secret
3. Sync products: `POST /v1/admin/channels/{id}/shopify/sync-catalog`
4. Register webhook in Shopify dashboard pointing to `POST /v1/webhooks/shopify`
5. IMS ingests Shopify `orders/create` and `orders/updated` events automatically

### WooCommerce

1. Create a channel in IMS
2. Connect: `POST /v1/admin/channels/{id}/woocommerce/connect` with store URL, consumer key, consumer secret, webhook secret
3. Sync products: `POST /v1/admin/channels/{id}/woocommerce/sync-catalog`
4. Register webhook in WooCommerce admin pointing to `POST /v1/webhooks/woocommerce`

### Inbound webhook authentication

- Shopify: HMAC-SHA256 of request body with `shopify_api_secret`
- WooCommerce: HMAC-SHA256 of request body with `woocommerce_webhook_secret`

Both are verified before processing. Invalid signatures return 401.

---

## 15. Platform and entitlements

### Plan-feature matrix

Features are defined in `services/api/app/billing/features.py` and plan values in `plans.py`. View the full matrix:

```
GET /v1/internal/platform/plan-features   (X-Admin-Token required)
```

### Per-tenant overrides

Platform admins can override individual features for specific tenants:
```
GET    /v1/admin/entitlements/overrides
POST   /v1/admin/entitlements/overrides   { feature_key, value, expires_at }
DELETE /v1/admin/entitlements/overrides/{id}
```

### Resolution order

```
tenant_feature_overrides > PLAN_FEATURES[plan_codename] > FEATURE_CATALOG default
```

Resolution is cached in Redis for 5 minutes. Writes invalidate the cache automatically.

---

## 16. Image storage (Cloudflare R2)

Product images are stored in Cloudflare R2 (S3-compatible object storage). Uploads go
**directly from the merchant's browser to R2** — image bytes never pass through the IMS
API server.

### Two storage modes

Every tenant is created with one of two modes:

| Mode | Who owns the bucket | When to use |
|------|-------------------|-------------|
| `platform` (default) | IMS — one shared bucket, prefixed `{tenant_id}/` | Most merchants |
| `byo` | The merchant — their own R2 or S3-compatible bucket | Enterprise / regulatory requirements |

Set the mode at tenant creation time in the platform-web create-tenant modal, or change
it later via:

```
GET  /v1/admin/tenant-settings/storage   → { storage_mode, configured, ... }
PUT  /v1/admin/tenant-settings/storage   → change mode and/or BYO credentials
```

BYO bucket credentials (endpoint URL, access key, secret key, public CDN URL) are stored
**encrypted** in the tenant row, identical to how Stripe/Razorpay keys are stored.

### Upload flow

```
1. Browser selects file
2. POST /v1/admin/media/presign-upload   { folder, filename, content_type, file_size_bytes }
        ↓ quota check (platform-mode only)
        ↓ returns { upload_url, public_url, storage_warning? }
3. Browser PUT file bytes → upload_url  (directly to R2, no API involved)
4. POST /v1/admin/catalog/products/{id}/images  { url: public_url, file_size_bytes }
        ↓ increments tenant.storage_bytes_used atomically
```

Presigned PUT URLs expire after 15 minutes. Allowed content types: `image/jpeg`,
`image/png`, `image/webp`, `image/gif`, `image/avif`. Maximum file size: 10 MB.

### Object key structure

| Mode | Key pattern |
|------|------------|
| `platform` | `{tenant_id}/products/{product_id}/{uuid}.{ext}` |
| `byo` | `products/{product_id}/{uuid}.{ext}` |

### Storage quotas (platform-mode only)

BYO tenants are exempt — they manage their own bucket limits.

For platform-mode tenants, the quota comes from `TenantLicenseCache.storage_limit_mb`
which is synced automatically from the billing service when a merchant upgrades or
purchases a storage add-on.

**Enforcement:**

| Threshold | Behaviour |
|-----------|-----------|
| < 80 % | Upload proceeds normally |
| ≥ 80 % | Upload proceeds, presign response includes `storage_warning: { used_pct, used_mb, limit_mb }` — admin-web shows inline warning after upload and a banner on the billing page |
| > 100 % | `POST /presign-upload` returns **HTTP 402** with `{ detail, used_bytes, limit_bytes }` — upload is blocked |

**Counter mechanics:**
- `tenants.storage_bytes_used` — atomic SQL expression updates (`SET col = col + X`), never ORM read-modify-write, safe under concurrent uploads
- Incremented when `POST .../images` is called with `file_size_bytes`
- Decremented when `DELETE .../images/{id}` is called (skipped if `file_size_bytes` is NULL for pre-existing images)
- Accurate even when the same merchant uploads from multiple tabs simultaneously

**Daily reconciliation:**
A background RQ task (`reconcile_storage_usage`) lists every platform tenant's R2 prefix
via `ListObjectsV2` and sets `storage_bytes_used` to the ground truth. This corrects drift
from pre-feature images (NULL sizes) and any edge cases. Interval is configurable:

```
STORAGE_RECONCILE_INTERVAL_HOURS=24   # default, set in docker-compose / .env
```

**Billing page** shows live storage usage (MB used vs MB limit) via the existing
`UsageMeter` component, which now reads the real counter.

### Environment variables

Set in `.env` (required for platform-mode uploads to work):

```bash
R2_ENDPOINT_URL=https://{ACCOUNT_ID}.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_BUCKET_NAME=ims-media
R2_PUBLIC_URL=https://media.yourplatform.com   # CDN domain pointed at your R2 bucket
R2_REGION=auto                                  # always "auto" for Cloudflare R2
STORAGE_RECONCILE_INTERVAL_HOURS=24
```

Leave blank in local development — the presign endpoint returns a `400` with
`"Platform R2 storage is not configured"` which is the expected dev behaviour.

For BYO tenants, their credentials are stored encrypted in the tenant row — no
environment variables needed on the IMS server.

### Admin API reference

```
POST   /v1/admin/media/presign-upload
       Body: { folder, filename, content_type, file_size_bytes }
       → { upload_url, public_url, key, expires_in, storage_warning? }
       → 402 if quota exceeded

GET    /v1/admin/catalog/products/{id}/images
POST   /v1/admin/catalog/products/{id}/images   { url, alt_text?, sort_order?, file_size_bytes? }
DELETE /v1/admin/catalog/products/{id}/images/{image_id}

GET    /v1/admin/tenant-settings/storage
PUT    /v1/admin/tenant-settings/storage   { storage_mode, byo_* fields }
```
