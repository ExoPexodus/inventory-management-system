# Storefront Security

This document covers the security controls available for headless storefronts
built on the IMS Storefront API.

## Threat model

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Browser-based scraping from any origin | Medium | Per-channel CORS allowlist |
| OTP/magic-link email abuse | High | Per-email rate limit (5/hr, 30/day) |
| Server-to-server price scraping | Low | Channel ID rotation (manual; future) |
| Inventory exhaustion via fake carts | Low | Existing reservation TTL + sweep job |
| Cart-token guessing | None | uuid4 — 122 bits entropy |

## Channel ID is public

The channel ID (`X-Channel-Id`) lives in your frontend JavaScript — anyone
visiting your storefront can find it. It is an identifier, not a secret.

**What an attacker can do with just a channel ID:**
- Browse your product catalog
- Create carts and request OTP codes (rate-limited)
- Add items to carts (stock is only reserved, not decremented, until checkout)

**What they cannot do without a customer JWT:**
- Access customer profile or order history
- Complete a checkout (requires payment)
- Submit a return request

## CORS allowlist

The `allowed_origins` field in `channel.config` restricts which browser
origins may call storefront endpoints. When set, requests from unlisted
origins receive HTTP 403. Requests without an `Origin` header (server-to-
server calls, curl, Postman) are always allowed through.

**How to configure:**

Via the admin API:
```bash
curl -X PATCH /v1/admin/channels/{channel_id} \
  -H "Authorization: Bearer ..." \
  -H "Content-Type: application/json" \
  -d '{"config": {"allowed_origins": ["https://stickerize.com", "https://www.stickerize.com"]}}'
```

Via admin-web: Channels → Security tab → select channel → enter one origin
per line → Save origins.

**Validation rules:**
- Each entry must match `scheme://host[:port]` with no path component
- Both `http://` and `https://` are accepted (use `https://` in production)
- Maximum 20 entries per channel

**Leave empty to preserve current behavior** (no origin restriction). This is
the default for all existing channels.

**Stickerize-UAT recipe:**
```json
{
  "allowed_origins": [
    "https://stickerize.com",
    "https://www.stickerize.com"
  ]
}
```

## OTP and magic-link rate limits

To prevent email abuse (using your sending domain to spam arbitrary addresses),
OTP and magic-link requests are rate-limited per email address per channel:

| Window | Limit |
|--------|-------|
| Hourly | 5 requests |
| Daily  | 30 requests |

When the limit is exceeded the API returns HTTP 429 with:
```json
{"detail": "Too many verification code requests. Try again later."}
```
and a `Retry-After: 3600` header.

The limit is keyed on `(channel_id, sha256(email)[:16])` — one channel's
burst cannot consume another channel's quota.

If Redis is unavailable the limiter fails open (requests are allowed through)
so a Redis outage never blocks legitimate logins.

## What is NOT protected

- **Server-side scraping:** A bot that never sends an `Origin` header bypasses
  the CORS allowlist. This is by design — server-to-server integrations need
  to call the API without a browser context.
- **Repeated cart creation:** The existing IP-based rate limit (120 req/min)
  and reservation TTL sweep job are the only defences here.
- **Channel ID enumeration:** Channel IDs are UUIDs (random, not sequential),
  but they are effectively public. Don't treat them as secrets.

## Requesting higher OTP limits

The per-email limits are currently fixed across all channels. If a merchant
needs higher limits (e.g. bulk SMS OTP campaigns), this would require a
per-channel limit ceiling — a future `channel.config.otp_hourly_limit` field.
Contact the platform team to discuss.

## Sample channel.config with all security fields

```json
{
  "allowed_origins": [
    "https://yourstore.com",
    "https://www.yourstore.com"
  ],
  "payment_provider": "stripe",
  "checkout_success_url": "https://yourstore.com/order/success"
}
```
