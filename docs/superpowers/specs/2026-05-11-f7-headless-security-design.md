# Followup 7 — Headless Storefront Security Hardening

**Date:** 2026-05-11
**Driver:** Stickerize-UAT is live on headless integration; basic protections are missing.

## Current state
- Storefront API auth = a single `X-Channel-Id` UUID header. Anyone who learns the channel ID can hit any storefront endpoint.
- CORS middleware allows all origins (`allow_origins=["*"]`). A malicious site can call the storefront from a victim's browser.
- Rate limit: 120 req/min per IP across the whole `/v1/storefront/*` namespace. No per-channel and no per-email limits.
- OTP / magic-link endpoints don't have a separate rate limit — one IP at 120/min can request 7,200 OTPs/hour against arbitrary emails.

## Threat model for a headless store
| Risk | Severity | Mitigation in this PR |
|---|---|---|
| Browser-based scraping from any origin | Medium | Per-channel CORS allowlist |
| OTP/magic-link email abuse (spam from your sending domain) | High | Per-email rate limit (5/hr, 30/day) |
| Server-to-server price scraping | Low | Channel ID rotation (manual; not v1) |
| Inventory exhaustion via fake carts | Low | Existing reservation TTL + sweep job |
| Cart-token guessing | None | `uuid.uuid4()` — 122 bits entropy ✓ |

## Locked decisions
- Ship per-channel CORS allowlist + per-email OTP rate limit + docs. Defer per-channel-id rate limit until the existing IP limit actually saturates.
- All changes are backward-compatible: channels without an `allowed_origins` entry behave like today (`*`).

## Schema
No new tables. Configuration lives in `Channel.config`:
```json
{
  "allowed_origins": ["https://stickerize.com", "https://www.stickerize.com"]
}
```
Validation: each entry must be a valid HTTPS URL with no path. When empty / missing, behavior matches today (`*`).

## Implementation

### 1. CORS middleware — per-channel Origin check
File: `services/api/app/middleware/storefront_origin_check.py` (NEW).

Runs BEFORE the storefront router. For requests under `/v1/storefront/*`:
- Read `X-Channel-Id` and the `Origin` header.
- Load the channel. If `channel.config.allowed_origins` is non-empty AND the Origin doesn't match any entry → 403 with `{"detail": "Origin not allowed for this channel"}`.
- If `allowed_origins` is empty/missing → pass through (current behavior).
- Skip the check for non-browser requests (no Origin header) — server-to-server is allowed by default; if the merchant wants to lock that down too they can configure a stricter setup.

Also: extend the global CORS middleware to dynamically reflect the allowed Origin when the channel matches, so the browser's preflight succeeds. Keep `allow_credentials=False` (we use Bearer tokens, no cookies). `allow_methods=["GET","POST","DELETE","PUT","PATCH"]`.

### 2. OTP per-email rate limit
File: `services/api/app/middleware/otp_rate_limit.py` (NEW), called from the OTP and magic-link request handlers (not as middleware — direct helper).

Helper `check_otp_rate_limit(email: str, channel_id: UUID)`:
- Key prefix: `rl:otp:{channel_id}:{sha256(email)[:16]}`
- Two windows:
  - `_hr` suffix — 60-second TTL — limit 5 requests
  - `_day` suffix — 86400-second TTL — limit 30 requests
- Returns silently when under limit; raises `HTTPException(429, "Too many OTP requests. Try again later.")` when over.
- Fails open on Redis errors (same pattern as existing storefront rate limiter).

Call from `customer_auth.py` at the start of `otp_request` and `magic_link_request` handlers.

### 3. Channel config validation
File: `services/api/app/routers/admin_channels.py` — when creating/updating a channel, validate `config.allowed_origins`:
- Must be a list of strings
- Each entry must match `^https?://[a-zA-Z0-9.-]+(?::\d+)?$` (scheme + host + optional port, no path)
- Max 20 entries

### 4. Admin UI surfacing
Add an "Allowed origins" textarea (one per line) to the channel edit form in admin-web. Each line becomes one entry in `config.allowed_origins`.

### 5. Documentation
New doc: `docs/storefront-security.md` covering:
- Channel ID is public (it's in your storefront JS)
- CORS allowlist as the first line of defense for browser scrapers
- OTP rate limits and when to ask for more
- Recommended environment posture for headless integrations
- Configuration recipes for Stickerize-UAT specifically (paste-in JSON for `channel.config`)

Plus update `CLAUDE.md` Storefront API section to mention these protections.

## Verification
- `docker compose run` tests pass.
- Stickerize-UAT can configure their two origins and confirm a curl from a wrong Origin returns 403 while their actual domain works.
- Spamming OTP for the same email 6 times in a minute returns 429 on the 6th.

## Files
| File | Status |
|---|---|
| `services/api/app/middleware/storefront_origin_check.py` | NEW |
| `services/api/app/services/otp_rate_limit.py` | NEW |
| `services/api/app/routers/storefront/customer_auth.py` | Call OTP rate limit helper |
| `services/api/app/main.py` | Register new middleware |
| `services/api/app/routers/admin_channels.py` | Validate allowed_origins on save |
| `apps/admin-web/src/app/(main)/channels/...` | Origins textarea (find existing channel form) |
| `docs/storefront-security.md` | NEW |
| `CLAUDE.md` | Mention storefront protections |

## Out of scope
- Per-channel rate limit (defer until IP-based limit saturates)
- Channel-secret header (X-Channel-Secret) for server-to-server — would be opt-in per channel; add when a merchant asks for it
- Anti-bot challenges (Cloudflare Turnstile etc.) — infrastructure decision, not app-level
