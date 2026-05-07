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
GET /v1/storefront/customers/me           → profile (email, name, customer_id)
GET /v1/storefront/customers/me/orders    → order history with lines
```

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

### Zones and rates

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

### Admin API

```
GET    /v1/admin/shipping/zones
POST   /v1/admin/shipping/zones
DELETE /v1/admin/shipping/zones/{id}

GET    /v1/admin/shipping/zones/{id}/rates
POST   /v1/admin/shipping/zones/{id}/rates
DELETE /v1/admin/shipping/zones/{id}/rates/{rate_id}
```

### Calculate shipping options

```
POST /v1/shipping/calculate
{
  "channel_id": "...",
  "destination": { "country": "IN", "state": "MH" },
  "cart_lines": [ { "product_id": "...", "quantity": 2, "unit_price_cents": 999 } ],
  "currency": "INR"
}
```

Returns list of applicable rates sorted by price.

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
2. Fire `order.confirmed` webhook to all subscribed endpoints
3. Record discount use (if discount was applied)

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
