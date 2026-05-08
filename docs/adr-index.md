# ADR Index

Architecture Decision Records — why things are built the way they are.

**Status values:** `accepted` | `superseded` | `deprecated`

---

## ADR-001: Offline-first immutable stock ledger

**Status:** accepted

**Decision:** Stock is never stored as a mutable quantity. All inventory changes create immutable `StockMovement` rows. Available stock is derived by summing `quantity_delta` values.

**Why:** Provides full audit trail for every inventory change. Eliminates update conflicts when multiple cashiers work simultaneously offline. Reconciliation is always possible.

**Where:**
- `services/api/app/models/tables.py` — `StockMovement` model
- `services/api/app/services/sync_push.py` — applies sale movements
- `services/api/app/routers/admin_inventory.py` — adjustment workflow

---

## ADR-002: Modular monolith backend

**Status:** accepted

**Decision:** One FastAPI deployment unit, organized by bounded-context router and service modules. No microservices split.

**Why:** Avoids distributed systems complexity while maintaining clear domain boundaries. Easier to deploy, test, and debug. Can be split later if a specific domain requires independent scaling.

**Where:**
- `services/api/app/main.py` — router composition
- `services/api/app/routers/` — one file per domain

---

## ADR-003: Tenant isolation via PostgreSQL RLS

**Status:** accepted

**Decision:** Every tenant-scoped table has a PostgreSQL row-level security policy. Application code sets `ims.tenant_id` as a session variable before every query. Defense-in-depth: even if application code forgets to filter by tenant, the DB policy prevents cross-tenant leaks.

**Where:**
- Alembic migrations (RLS policy creation)
- `services/api/app/db/rls.py` — `set_rls_context()`

---

## ADR-004: Integer minor units for all money

**Status:** accepted

**Decision:** All monetary amounts are stored as integers in the currency's minor unit (cents, paise, etc.). Column names end with `_cents`. No floats ever.

**Why:** Eliminates floating-point rounding errors. Arithmetic is exact. Display formatting is deferred to the presentation layer using the currency's exponent.

**Where:** All `*_cents` columns across models.

---

## ADR-005: Card tender requires connectivity (POS)

**Status:** accepted

**Decision:** Card payments in the cashier app require an active connection to the API. Cash sales can queue offline.

**Why:** Card transactions require real-time authorization and cannot be safely queued offline without risk of decline on sync.

**Where:**
- `apps/cashier/lib/screens/cart_screen.dart`
- `services/api/app/services/sync_push.py`

---

## ADR-006: Product groups for variant merchandising (POS)

**Status:** accepted

**Decision:** The sellable unit remains `products.id`. Optional `product_groups` and `product_group_id` + `variant_label` on products allow cashier grouping without changing the ledger model.

**Why:** Variants in POS (e.g. size S/M/L) are primarily a UI concern. Keeping the ledger at the individual SKU level ensures stock accuracy and avoids complex variant-roll-up logic.

**Where:**
- `services/api/app/models/tables.py` — `ProductGroup`, `Product.variant_label`
- `services/api/app/routers/sync.py`

---

## ADR-007: Channel-based multi-surface e-commerce

**Status:** accepted

**Decision:** All e-commerce surfaces (headless storefront, Shopify, WooCommerce, POS) are represented as `Channel` records. Channels carry payment config, currency, and a reference to an inventory pool. The storefront API uses `X-Channel-Id` for routing and scoping.

**Why:** A single merchant may sell through multiple surfaces simultaneously. Channels provide isolation (separate payment configs, currencies) while sharing the same inventory. Adding a new sales surface means adding a new channel type, not refactoring the core.

**Where:**
- `services/api/app/models/tables.py` — `Channel`, `InventoryPool`
- `services/api/app/routers/storefront/auth.py` — `StorefrontChannelDep`
- `services/api/app/routers/admin_channels.py`

---

## ADR-008: Soft-TTL stock reservations for cart

**Status:** accepted

**Decision:** When a product is added to a headless storefront cart, stock is reserved with a 15-minute TTL. Reservations are committed on order completion and released on expiry by a background sweep job.

**Why:** Prevents overselling on concurrent carts without requiring a synchronous lock per add-to-cart call. TTL ensures dead carts don't hold stock indefinitely.

**Where:**
- `services/api/app/models/tables.py` — `StockReservation`
- `services/api/app/services/reservation_service.py`
- `services/api/app/worker/tasks.py` — `sweep_expired_reservations`

---

## ADR-009: Hosted checkout with BYO payment providers

**Status:** accepted

**Decision:** IMS hosts a checkout HTML page (`/checkout/{session_token}`) rendered server-side with Jinja2. Merchants bring their own Stripe or Razorpay accounts — credentials are stored encrypted per channel. IMS never holds payment credentials centrally.

**Why:** Reduces PCI scope for IMS. Merchants keep full control of their payment accounts and revenue. The hosted page eliminates the need for headless merchants to build their own payment UI.

**Where:**
- `services/api/app/routers/checkout.py`
- `services/api/templates/checkout.html`
- `services/api/app/services/payment_service.py`
- `services/api/app/services/email_service.py` — `encrypt_secret()`/`decrypt_secret()`

---

## ADR-010: Customer OTP auth with short-lived customer JWT

**Status:** accepted

**Decision:** Storefront customers authenticate via a 6-digit email OTP (10-minute TTL). Successful verification issues a `typ=customer` JWT (7-day TTL). Customer token is separate from operator and device tokens.

**Why:** Passwordless auth lowers friction for one-time shoppers while still enabling persistent sessions for returning customers. The separate token type ensures storefront auth cannot accidentally grant admin access.

**Security details:** OTP generated with `secrets.randbelow()` (CSPRNG). Stored as SHA-256 hash. Verified with `SELECT FOR UPDATE` to prevent concurrent double-use.

**Where:**
- `services/api/app/models/tables.py` — `StorefrontOTP`
- `services/api/app/routers/storefront/customer_auth.py`
- `services/api/app/auth/jwt.py` — `create_customer_token()`

---

## ADR-011: Async webhook delivery with RQ + exponential backoff

**Status:** accepted

**Decision:** Outbound webhooks to merchant endpoints are delivered asynchronously via RQ. Each delivery is retried up to 3 times with 5-minute and 30-minute delays. Order creation is never blocked by webhook delivery.

**Why:** Merchant endpoints are external and unreliable. Synchronous delivery would make order creation fragile. Async delivery with retry provides eventual consistency guarantees without coupling order creation latency to webhook delivery latency.

**Where:**
- `services/api/app/services/webhook_service.py`
- `services/api/app/worker/tasks.py` — `deliver_webhook()`
- `services/api/app/models/tables.py` — `WebhookEndpoint`, `WebhookDeliveryLog`

---

## ADR-012: BYO email — merchants own their sending infrastructure

**Status:** accepted

**Decision:** Every merchant configures their own SMTP or Resend credentials. IMS never sends email from a shared platform address. Credentials are stored in `TenantEmailConfig`.

**Why:** Shared sending infrastructure creates deliverability coupling — one merchant's spam behaviour can damage all merchants' domain reputation. BYO means each merchant controls their own SPF/DKIM/DMARC and sender reputation.

**Where:**
- `services/api/app/models/tables.py` — `TenantEmailConfig`
- `services/api/app/services/email_service.py`
- `services/api/app/routers/admin_email.py`

---

---

## ADR-013: Generic carrier shipping provider abstraction

**Status:** accepted

**Decision:** Carrier integrations live behind a `ShippingProvider` Protocol (`shipping/base.py`). The first implementation is Shiprocket. Adding a new carrier = implementing the protocol and registering a name in `registry.py`. Nothing else changes.

**Why:** Indian e-commerce requires multiple carrier options (Shiprocket, Delhivery, Bluedart, DTDC). Building to a generic interface from day one means the second carrier costs a fraction of the first. The pattern mirrors the existing payment provider abstraction (`payment_service.py` → Stripe/Razorpay).

**Key design choices:**
- Shiprocket auth token cached in Redis (9-day TTL) — never blocks dispatch at peak
- `shipment_events` table is append-only and idempotent on `(order_id, provider_event_id)` — duplicate inbound webhooks are safe
- Dispatch is always async via RQ — order creation latency is never affected by carrier API response time
- Credentials encrypted identically to payment provider keys

**Where:**
- `services/api/app/services/shipping/` — provider abstraction + Shiprocket implementation
- `services/api/app/routers/webhooks_shiprocket.py` — inbound webhook receiver
- `services/api/app/routers/admin_shipping_providers.py` — setup/config endpoints
- `services/api/app/models/tables.py` — `ShipmentEvent` model + order fulfillment columns

---

## Next ADR candidates

- **ADR-014:** Returns/inbound inventory workflow — RMA flow + return pickup via carrier
- **ADR-015:** Multi-shop transfer orders (stock movement across shops)
- **ADR-016:** Customer account linking across channels (unified identity)
- **ADR-017:** Advanced RBAC — custom role creation for per-operator permission sets
