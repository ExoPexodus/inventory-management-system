# Storefront API — Developer Guide

This guide is for developers building headless storefronts on top of IMS. It covers authentication, the full shopping flow, and SDK usage.

---

## Prerequisites

Before you can use the storefront API, a merchant must:

1. **Create an inventory pool** — Admin Web → Inventory Pools → New pool (assign shops)
2. **Create a headless channel** — Admin Web → Channels → New channel (type: Headless, assign the pool)
3. **Configure payment** — Admin Web → Channels → Payment tab → Set up Stripe or Razorpay
4. **Note the Channel ID** — UUID shown in the channels list, used in every API request

---

## Base URL and channel header

Every storefront request includes:

```
X-Channel-Id: <your-channel-uuid>
```

Base URL: `https://api.yourims.com` (or `http://localhost:8001` locally).

All storefront routes live under `/v1/storefront/`.

---

## TypeScript SDK

The fastest way to get started. Copy `packages/storefront-sdk/` into your project.

```typescript
import { StorefrontClient } from "@ims/storefront-sdk";

const client = new StorefrontClient({
  baseUrl: "https://api.yourims.com",
  channelId: "your-channel-uuid",
});
```

The SDK handles the `X-Channel-Id` header, customer token management, and error parsing automatically.

---

## Shopping flow

### 1. Browse products

```typescript
// List all active products (paginated)
const { items, total } = await client.listProducts({
  page: 1,
  per_page: 20,
  status: "active",
});

// Get a single product by slug or UUID
const product = await client.getProduct("my-product-slug");
```

**Response shape:**
```typescript
{
  id: string;
  name: string;
  slug: string | null;
  unit_price_cents: number;
  discount_price_cents: number | null;
  currency_code: string;
  image_url: string | null;
  description: string | null;
  product_type: "physical" | "digital" | "service" | "gift_card" | "donation";
  tags: string[] | null;
}
```

### 2. Create a cart

```typescript
const cart = await client.createCart();
// cart.cart_token is your session identifier — store it (localStorage, cookie, etc.)
```

### 3. Add items to cart

```typescript
const updatedCart = await client.addToCart(
  cart.cart_token,
  product.id,
  2  // quantity
);
```

`addToCart` returns the full updated cart. If the product already exists in the cart, quantity is incremented.

### 4. View cart and apply discount

```typescript
// Get current cart
const cart = await client.getCart(cartToken);

// Get totals summary (with discount/tax/shipping)
const summary = await client.getCartSummary(cartToken);

// Apply a discount code
const result = await client.applyDiscount(cartToken, "SAVE10");
// result.discount_cents = applied savings
// result.is_free_shipping = boolean
```

### 5. Checkout

**Option A — Hosted checkout (simplest):**

```typescript
const session = await client.createCheckoutSession(cartToken);
// Redirect the customer:
window.location.href = session.checkout_url;
// IMS handles payment collection and redirects back to checkout_success_url
```

**Option B — Custom checkout UI with Stripe:**

```typescript
// 1. Create checkout session
const session = await client.createCheckoutSession(cartToken);

// 2. Create payment intent (get client_secret for Stripe.js)
const intent = await client.createPaymentIntent(
  session.session_token,
  "customer@example.com",
  { city: "Mumbai", country: "IN" }
);

// 3. Mount Stripe Elements with intent.client_secret
// (use Stripe.js as normal)

// 4. After payment confirms, complete the checkout:
const order = await client.completeCheckout(session.session_token, {
  payment_intent_id: "pi_...",
  customer_email: "customer@example.com",
});
window.location.href = order.redirect_url;
```

**Option C — Direct order submit (your own payment flow):**

```typescript
const order = await client.submitOrder({
  cart_token: cartToken,
  payment_provider: "stripe",
  payment_reference: "pi_xxx",  // your payment intent ID
  customer_email: "customer@example.com",
});
```

---

## Customer authentication

Customers log in with a 6-digit OTP sent to their email.

```typescript
// Step 1: Request OTP
const { sent, message } = await client.requestOTP("customer@example.com");

// Step 2: Verify OTP (customer enters the code from their email)
const auth = await client.verifyOTP("customer@example.com", "123456");
// auth.access_token is stored automatically by the SDK
// auth.expires_in = 604800 (7 days)
```

To restore a session on page load:
```typescript
const client = new StorefrontClient({
  baseUrl: "...",
  channelId: "...",
  customerToken: localStorage.getItem("ims_customer_token") ?? undefined,
});
```

### Customer portal

Requires a valid customer token:

```typescript
const profile = await client.getCustomerProfile();
// { email, name, customer_id }

const orders = await client.getOrderHistory({ limit: 10 });
// Array of {
//   id, status, fulfillment_status, total_cents, currency_code, placed_at,
//   awb_code, tracking_url, carrier_name, shipped_at, delivered_at, lines[]
// }
```

---

## Raw HTTP reference

If not using the TypeScript SDK:

### Catalog

```
GET /v1/storefront/products
    ?q=           text search
    ?status=      active | draft | archived
    ?page=        (default: 1)
    ?per_page=    (default: 20, max: 100)

GET /v1/storefront/products/{slug_or_uuid}
```

### Cart

```
POST   /v1/storefront/cart
       → 201 { cart_token, items: [], subtotal_cents, total_cents, currency_code }

GET    /v1/storefront/cart/{cart_token}

POST   /v1/storefront/cart/{cart_token}/items
       Body: { "product_id": "uuid", "quantity": 2 }

DELETE /v1/storefront/cart/{cart_token}/items/{item_id}

GET    /v1/storefront/cart/{cart_token}/summary
       → { subtotal_cents, discount_cents, tax_cents, shipping_cents, total_cents, discount_code }

POST   /v1/storefront/cart/{cart_token}/discount
       Body: { "code": "SAVE10" }
```

### Checkout (hosted)

```
POST   /v1/storefront/checkout/session
       Body: { "cart_token": "..." }
       → { session_token, checkout_url, expires_at }

POST   /v1/checkout/{session_token}/payment-intent
       Body: { "customer_email": "...", "shipping_address": { "city": "...", "country": "IN" } }
       → { provider, payment_intent_id, client_secret, ... }

POST   /v1/checkout/{session_token}/complete
       Body: { "payment_intent_id": "...", "customer_email": "..." }
       → { status: "completed", order_id, redirect_url }

POST   /v1/checkout/{session_token}/apply-discount
       Body: { "code": "..." }
       → { code, discount_name, discount_cents, total_cents, ... }

DELETE /v1/checkout/{session_token}/discount
```

### Orders (direct submit)

```
POST   /v1/storefront/orders
       Body: {
         "cart_token": "...",
         "payment_provider": "stripe",
         "payment_reference": "pi_...",
         "customer_email": "...",
         "customer_phone": "...",      # optional
         "shipping_address": { ... }, # optional
         "discount_code": "..."       # optional
       }
```

### Customer auth

```
POST   /v1/storefront/auth/otp/request
       Headers: X-Channel-Id
       Body: { "email": "..." }
       → { sent: bool, message: str }

POST   /v1/storefront/auth/otp/verify
       Headers: X-Channel-Id
       Body: { "email": "...", "code": "123456" }
       → { access_token, token_type: "bearer", expires_in: 604800 }
```

### Customer portal (requires `Authorization: Bearer <customer_token>`)

```
GET    /v1/storefront/customers/me
       → { email, name, customer_id }

GET    /v1/storefront/customers/me/orders
       ?limit=   (default: 20, max: 100)
       ?offset=  (default: 0)
       → [ {
             id, status, fulfillment_status,
             total_cents, currency_code, placed_at,
             awb_code, tracking_url, carrier_name,
             shipped_at, delivered_at,
             lines: [...]
           } ]

GET    /v1/storefront/customers/me/orders/{order_id}/tracking
       → [ { status, occurred_at, location, description } ]
       (shipment event timeline, sorted oldest-first)
```

---

## Error responses

All errors follow the same shape:

```json
{ "detail": "Human-readable error message" }
```

Common status codes:

| Code | Meaning |
|------|---------|
| 400 | Bad request (validation error, business rule violation) |
| 401 | Missing or invalid customer token |
| 404 | Resource not found |
| 410 | Checkout session expired or completed |
| 422 | Invalid request body (field validation) |
| 429 | Rate limited — slow down (120 req/min per IP) |
| 502 | Upstream error (payment provider, FX service) |

---

## Money values

All `*_cents` values are **integer minor units**:
- INR: 999 = ₹9.99 (exponent 2)
- USD: 999 = $9.99 (exponent 2)
- JPY: 999 = ¥999 (exponent 0)

Use the Intl API to format for display:
```typescript
function formatMoney(amountCents: number, currencyCode: string): string {
  const exp = new Intl.NumberFormat(undefined, { style: "currency", currency: currencyCode })
    .resolvedOptions().minimumFractionDigits ?? 2;
  return (amountCents / 10 ** exp).toLocaleString(undefined, {
    style: "currency",
    currency: currencyCode,
  });
}
```

---

## Testing locally

```bash
# Start the stack:
docker compose up --build

# API is at http://localhost:8001
# Swagger UI: http://localhost:8001/docs

# Your client:
const client = new StorefrontClient({
  baseUrl: "http://localhost:8001",
  channelId: "paste-your-channel-uuid-here",
});
```

Create a test channel and configure payment (use Stripe test keys) via Admin Web at `http://localhost:3100`.
