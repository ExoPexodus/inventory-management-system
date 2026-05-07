# @ims/storefront-sdk

TypeScript SDK for the IMS Storefront API. Works in any JavaScript environment (Next.js, Vite, Node.js, vanilla browser).

## Quick start

```typescript
import { StorefrontClient } from "@ims/storefront-sdk";

const client = new StorefrontClient({
  baseUrl: "https://api.yourims.com",
  channelId: "your-headless-channel-uuid",
});

// Browse products
const { items } = await client.listProducts({ page: 1, per_page: 20 });

// Add to cart
const cart = await client.createCart();
await client.addToCart(cart.cart_token, items[0].id, 1);
const summary = await client.getCartSummary(cart.cart_token);

// Hosted checkout
const session = await client.createCheckoutSession(cart.cart_token);
window.location.href = session.checkout_url; // redirect to IMS checkout page

// Customer login
await client.requestOTP("customer@example.com");
const auth = await client.verifyOTP("customer@example.com", "123456");
// Token is set automatically — subsequent calls are authenticated

const profile = await client.getCustomerProfile();
const orders = await client.getOrderHistory({ limit: 10 });
```

## API reference

### Catalog
| Method | Description |
|--------|-------------|
| `listProducts(params?)` | Paginated catalog — `q`, `status`, `page`, `per_page` |
| `getProduct(slugOrId)` | Single product by slug or UUID |

### Cart
| Method | Description |
|--------|-------------|
| `createCart()` | Start a new cart |
| `getCart(token)` | Fetch cart with items |
| `addToCart(token, productId, qty)` | Add product to cart |
| `removeFromCart(token, itemId)` | Remove cart line item |
| `getCartSummary(token)` | Totals with discount / tax / shipping |
| `applyDiscount(token, code)` | Apply a discount code |

### Hosted checkout
| Method | Description |
|--------|-------------|
| `createCheckoutSession(cartToken)` | Start IMS-hosted checkout, get redirect URL |
| `createPaymentIntent(session, email, address?)` | Create Stripe / Razorpay intent |
| `completeCheckout(session, payload)` | Confirm payment, create order |

### Direct order
| Method | Description |
|--------|-------------|
| `submitOrder(payload)` | Submit order directly (BYO payment UI) |

### Customer auth
| Method | Description |
|--------|-------------|
| `requestOTP(email)` | Send 6-digit login code |
| `verifyOTP(email, code)` | Verify code, store customer JWT automatically |

### Customer portal
| Method | Description |
|--------|-------------|
| `getCustomerProfile()` | Name, email, customer ID |
| `getOrderHistory(params?)` | Past orders with line items |

## Notes

- All money values are in integer minor units (cents). Format with the currency's exponent.
- The channel ID is fixed per storefront — use a separate `StorefrontClient` instance per channel if you serve multiple storefronts.
- `setCustomerToken(token)` lets you restore a persisted customer session on page load.
