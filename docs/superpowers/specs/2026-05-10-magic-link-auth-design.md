# Magic-Link Auth Design

**Date:** 2026-05-10
**Phase:** Backend feature

## Problem
Customers logging into the storefront only have OTP — they receive an email with a 6-digit code, switch back to the storefront, type it in. A magic link (tap the email link → logged in) is faster on mobile and matches modern patterns. The locked decision was to add it as a coexisting alternative, not to replace OTP.

## Goals
1. New endpoints `POST /v1/storefront/auth/magic-link/request` and `POST /v1/storefront/auth/magic-link/verify`.
2. Same email infrastructure as OTP (TenantEmailConfig).
3. Single-use tokens, 15-minute TTL, hash-only storage.
4. Storefront SDK gains `requestMagicLink(email, redirectUrl)` and `verifyMagicLink(token)`.

## Non-goals
- Replacing or deprecating OTP — both flows coexist.
- Admin operator login changes (admins don't use storefront auth).
- SMS-delivered magic links (email only for now).

## Backend

### New model: `StorefrontMagicLink`
Migrated table mirroring `StorefrontOTP` but with `token_hash` instead of `code_hash`.

```python
class StorefrontMagicLink(Base):
    __tablename__ = "storefront_magic_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID]  # FK
    channel_id: Mapped[uuid.UUID]  # FK
    email: Mapped[str]
    token_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex
    redirect_url: Mapped[str] = mapped_column(String(1024))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

Migration chains from latest head.

### Endpoint: `POST /v1/storefront/auth/magic-link/request`

**Body:**
```json
{ "email": "...", "redirect_url": "https://yourstore.com/auth/magic" }
```

**Behaviour:**
- Channel-scoped (X-Channel-Id header, like other storefront endpoints)
- Generate URL-safe token: `secrets.token_urlsafe(32)`
- Hash with SHA-256, store in `storefront_magic_links`
- Send email containing `{redirect_url}?token={token}`
- Return `{ sent: bool, message: str }` (always `sent: true` even if email fails — never reveal whether the email exists)

### Endpoint: `POST /v1/storefront/auth/magic-link/verify`

**Body:**
```json
{ "token": "..." }
```

**Behaviour:**
- Hash incoming token, look up unused row not yet expired
- 401 if not found / expired / used
- Mark `used_at = now`, resolve-or-create customer (same as OTP), issue customer JWT
- Returns `{ access_token, token_type: "bearer", expires_in }` — same shape as `OTPVerifyOut`

### Email content
A new template that uses the existing `_send_via_smtp` / `_resend_send` helpers in `email_service.py`. Body: short copy with the magic link button. Subject: "Sign in to {tenant_name}". Falls back to plaintext text body for accessibility.

## Frontend (Storefront SDK)

`packages/storefront-sdk/src/client.ts` gains two methods on `StorefrontClient`:

```ts
async requestMagicLink(email: string, redirectUrl: string): Promise<{ sent: boolean; message: string }>
async verifyMagicLink(token: string): Promise<{ access_token: string; token_type: string; expires_in: number }>
```

Each calls the corresponding endpoint. Types updated in `packages/storefront-sdk/src/types.ts`.

## Files
| File | Status |
|---|---|
| `services/api/app/models/tables.py` | Add `StorefrontMagicLink` model |
| `services/api/alembic/versions/<new>.py` | Migration |
| `services/api/app/routers/storefront/customer_auth.py` | Add 2 magic-link endpoints |
| `services/api/email_templates/magic_link.html` | New email template (or inline string in code) |
| `packages/storefront-sdk/src/client.ts` | Add 2 methods |
| `packages/storefront-sdk/src/types.ts` | Add response types |

## Out of scope
SDK demo-app updates — tenants integrate the new methods themselves following the existing OTP pattern.
