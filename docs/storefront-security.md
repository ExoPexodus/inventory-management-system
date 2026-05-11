# Storefront Security

This document covers the security controls available for headless storefronts
built on the IMS Storefront API.

## Threat model

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Browser-based scraping from any origin | Medium | Per-channel CORS allowlist |
| OTP/magic-link email abuse | High | Per-email rate limit (5/hr, 30/day) |
| Discount code brute-force / enumeration | Medium | 5 failed attempts / 10 min per IP per channel → 429 |
| Cart-create flood (DB spam) | Medium | 20/min and 200/hr per IP per channel → 429 |
| Server-to-server price scraping | Low | Channel ID rotation (manual; future) |
| Inventory exhaustion via fake carts | Low | Existing reservation TTL + sweep job |
| Cart-token guessing | None | uuid4 — 122 bits entropy |
| Response sniffing / framing | Low | X-Content-Type-Options, X-Frame-Options, Referrer-Policy on every response |

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

## Discount code brute-force protection

The `POST /cart/{token}/discount` endpoint returns 404 for unknown codes and
200 for valid ones — a distinguishable signal an attacker could use to
enumerate codes. To prevent this:

- Every 404 increments a per-`(channel, ip)` counter in Redis.
- After **5 failed attempts in a 10-minute window** the endpoint returns
  HTTP 429 for that IP, regardless of whether the next code attempted is
  valid. Counter expires automatically.
- A successful application clears the counter — a real customer who
  mistyped their code a couple of times is not penalised after they get
  it right.
- 422 responses (code valid but not eligible for this cart) are NOT
  counted — the attacker already learned the code is real.

Fail-open on Redis errors.

## Cart-creation rate limit

A separate guard on `POST /cart` to bound DB spam from script abuse,
beyond the general 120-request/min storefront ceiling:

| Window | Limit |
|--------|-------|
| Per minute | 20 carts |
| Per hour   | 200 carts |

Keyed by `(channel_id, ip)`. Returns 429 with `Retry-After` when exceeded.
Other storefront endpoints are unaffected.

## Response security headers

Every response (storefront and admin) carries:

- `X-Content-Type-Options: nosniff` — browsers won't try to execute JSON as HTML
- `X-Frame-Options: DENY` — pages can't be framed
- `Referrer-Policy: strict-origin-when-cross-origin` — never leaks query strings
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` — only when the request was over HTTPS (auto-detected via `X-Forwarded-Proto` for proxied deployments)

The `Server` header is suppressed at the uvicorn level (`--no-server-header`)
so the API doesn't disclose its runtime version.

## What is NOT protected

- **Server-side scraping:** A bot that never sends an `Origin` header bypasses
  the CORS allowlist. This is by design — server-to-server integrations need
  to call the API without a browser context.
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
