# Currency Cleanup & Platform-Managed Currency — Design

**Date:** 2026-04-19
**Status:** Approved for planning
**Scope:** services/platform, services/api, apps/platform-web, apps/admin-web

## Summary

Tenant operating currency becomes a platform-managed setting. The SaaS operator (not the tenant admin) is the authoritative editor. The api service keeps the currency values in its own DB as a local cache, synced from platform via push (on every change) and, for cloud deployments, a periodic safety-net poll. The deprecated `display_mode: "convert"` multiplier feature is removed entirely. Admin-web's currency section becomes read-only.

Currency is the pilot for a broader pattern: platform owns SaaS-operator-controlled settings; api caches them locally; the rest of the system (admin-web, cashier sync, etc.) reads from api as today. Future specs will extend this pattern to additional settings (license date, plan flags, feature toggles), but only currency is in scope here.

## Motivation

Current pain:
1. The `display_mode: "convert"` / `currency_conversion_rate` multiplier feature is genuinely confusing. Tenants see "USD values multiplied by 1.5" displayed as another currency, which breaks mental models and creates support burden.
2. Currency changes in admin-web are cache-stale until page reload — a bug rooted in the `CurrencyContext` fetching once on mount and never refetching ([currency-context.tsx](apps/admin-web/src/lib/currency-context.tsx)).
3. Letting tenant admins self-serve currency changes is risky — historical data is stored in its original minor units (cents), so a tenant changing currency mid-operation invalidates receipts, cost bases, and margin reports without migrating the stored data.

Moving currency to platform-only editing:
- Makes currency a deliberate operator-gated decision (tenants contact support to change).
- Provides a clean seam for future platform-managed settings.
- Preserves stored historical data exactly (cents are never re-denominated).

## Scope

**In scope:**
- Currency becomes platform-owned; admin-web UI becomes read-only.
- Drop `currency_display_mode` and `currency_conversion_rate` from `api.tenants`.
- Drop all "convert" mode code paths from admin-web (`formatMoney`, settings UI, currency context types).
- New platform ↔ api sync infrastructure for currency: HMAC-signed push endpoint on api, HMAC-signed pull endpoint on platform.
- Per-tenant `deployment_mode` flag (`cloud` | `on_prem`) on `platform_tenants` — determines whether the api polls platform.
- `IMS_PLATFORM_SYNC_MODE` env var on api side (`polling` | `offline`) — must agree with platform's per-tenant deployment_mode at deploy time.
- Fix admin-web cache staleness — refetch currency context on route change.

**Out of scope:**
- Migrating other tenant settings to platform (future specs).
- A "Create tenant" UI in platform-web — create endpoint already exists at [platform/tenants.py:102](services/platform/app/routers/tenants.py#L102); operators provision via the API today; a UI is a separate feature.
- Retroactive currency conversion of historical data — values stay in their original minor units forever.
- Cashier app changes — cashier pulls currency via `/v1/sync/pull` from api; no direct platform contact. Will pick up reformatted fields automatically.
- Background retry queue for failed pushes — single inline attempt + manual retry from platform-web is enough for v1.

## Data Model

### Platform DB — `platform_tenants` gains four new columns

| Column | Type | Nullable | Default | Meaning |
|---|---|---|---|---|
| `default_currency_code` | `String(3)` | NOT NULL | `"USD"` | ISO currency code. Authoritative. |
| `currency_exponent` | `Integer` | NOT NULL | `2` | Minor-unit exponent (2 for USD/INR, 0 for IDR). |
| `currency_symbol_override` | `String(8)` | YES | `NULL` | Custom display symbol, else derived from code. |
| `deployment_mode` | `String(16)` | NOT NULL | `"cloud"` | Values: `"cloud"` (push + poll) or `"on_prem"` (push only, no poll). |

### API DB — `tenants` column changes

Added:

| Column | Type | Nullable | Default | Meaning |
|---|---|---|---|---|
| `currency_synced_at` | `DateTime(timezone=True)` | YES | `NULL` | Timestamp of last authoritative sync from platform. Used for idempotency (reject older payloads) and staleness monitoring. |

Dropped (forward-only, destructive):
- `currency_display_mode`
- `currency_conversion_rate`

Kept (unchanged — remain as the api-side cache read by everything else):
- `default_currency_code`
- `currency_exponent`
- `currency_symbol_override`

### Tenant linkage

Platform and api identify the same tenant by `slug` (unique in both DBs). No new FK needed; existing slug-matching suffices for sync routing.

## Sync Protocol

### Push: platform → api (every change, both deployment modes)

- **API endpoint (new):** `POST /v1/internal/platform-config` on the api service.
- **Auth:** HMAC-SHA256 header `X-Platform-Signature: <hmac(api_shared_secret, body)>`, mirroring the existing HMAC pattern used by [platform/tenant_api.py:33](services/platform/app/routers/tenant_api.py#L33).
- **Body:**
  ```json
  {
    "tenant_id": "<uuid>",
    "default_currency_code": "INR",
    "currency_exponent": 2,
    "currency_symbol_override": null,
    "synced_at": "2026-04-19T14:30:00Z"
  }
  ```
- **Idempotency:** api compares payload `synced_at` to `tenants.currency_synced_at`. If payload is older or equal (within 2-second tolerance for clock skew), return 200 with `{ "applied": false }`. Else apply and return `{ "applied": true }`.
- **Retry policy:** platform attempts once inline on PATCH. On 4xx/5xx/timeout, logs the error and surfaces failure status in the PATCH response so platform-web can render a "Push failed — retry" indicator to the operator. No background retry queue in this spec.

### Poll: api → platform (cloud tenants only, safety net)

- **Platform endpoint (new):** `GET /v1/internal/tenants/{slug}/config`.
- **Auth:** HMAC-SHA256 header, api signs with its `api_shared_secret` (already issued at platform-side tenant provisioning). Platform verifies.
- **Response body:** same shape as push body, minus `tenant_id` (derived from slug on the platform side). Includes current `synced_at` = platform's last-update timestamp for that tenant's config.
- **Idempotency rule:** same as push — api compares `synced_at` to its stored value and skips no-op updates.
- **Gated by api env var `IMS_PLATFORM_SYNC_MODE`:**
  - `polling` (default for cloud): job registers with the scheduler and runs every `IMS_PLATFORM_SYNC_INTERVAL_SECONDS` (default `300`).
  - `offline` (for on-prem): job does not register; api never initiates calls to platform.
- **Worker:** runs inside the existing RQ worker ([app/worker.py](services/api/app/worker.py)).

### Failure handling

- Platform push failure → logged, surfaced in platform-web UI ("Last push failed: <ts>"). Next poll cycle (cloud only) will self-heal.
- api poll failure → warn-level log. Values stay at last-known-good. Monitoring can alert on sustained failures.
- Clock skew tolerance: 2 seconds on `synced_at` comparisons.

### Deployment-mode flag

Lives in two places (must agree, set at deployment time):

1. **`platform_tenants.deployment_mode`** — platform uses this for operator awareness and to differentiate push-failure severity (on-prem push failures are more serious — no safety-net poll).
2. **`IMS_PLATFORM_SYNC_MODE` env var on api instance** — `polling` or `offline`. Determines whether the api's poll job schedules itself.

Drift (e.g. platform thinks `cloud` but api is `offline`) is non-fatal — platform keeps pushing to a URL that doesn't respond, logs failures; monitoring alerts.

## API Changes

### Platform service

**New endpoints** on the existing admin/operator router:
- `GET /v1/platform/tenants/{tenant_id}/currency` → `{ default_currency_code, currency_exponent, currency_symbol_override }`. Operator-auth.
- `PATCH /v1/platform/tenants/{tenant_id}/currency` — accepts the three fields. Updates `platform_tenants` row, then triggers a single inline HMAC push to the tenant's api `api_base_url`. Returns `{ ...updated_values, push_status: "success" | "failed", push_error: "..." }`.

**Existing endpoints extended:**
- `POST /v1/platform/tenants` — body gains optional `deployment_mode` (default `"cloud"`), `default_currency_code` (default `"USD"`), `currency_exponent` (default `2`), `currency_symbol_override` (default `null`).
- `PATCH /v1/platform/tenants/{tenant_id}` — body accepts `deployment_mode` as editable.

**New internal endpoint** (HMAC-authenticated, called by api's poller):
- `GET /v1/internal/tenants/{slug}/config` — see Sync Protocol above.

### API service

**New internal endpoint** (HMAC-authenticated, called by platform's push):
- `POST /v1/internal/platform-config` — see Sync Protocol above.

**Existing admin endpoint changes:**
- `GET /v1/admin/tenant-settings/currency` — unchanged shape; drops `display_mode` and `conversion_rate` fields from response. Admin-web treats it as read-only now.
- `PATCH /v1/admin/tenant-settings/currency` — **removed.** Returns 410 Gone during a short deprecation window, then deleted. Admin-web stops calling it.

## UI Changes

### Platform-web

Tenant edit page ([apps/platform-web/](apps/platform-web/)):
- **New "Currency" section** with three controls:
  - Currency code dropdown (supported list hard-coded: USD, INR, IDR, EUR, GBP — matching admin-web's existing list).
  - Exponent — read-only display, derived automatically from selected currency.
  - Symbol override — optional text input.
  - Save button calls `PATCH /v1/platform/tenants/{id}/currency`. On success, shows "Pushed to tenant api (last synced: <ts>)". On push failure, shows "Push failed — click to retry."
- **Deployment-mode dropdown** — editable (`Cloud` / `On-prem`) with a confirmation dialog warning that changing mode requires matching the api instance's `IMS_PLATFORM_SYNC_MODE` env var.

No tenant-create UI work in this spec.

### Admin-web

Currency settings section in [settings/page.tsx](apps/admin-web/src/app/(main)/settings/page.tsx):
- **Becomes read-only.** No dropdowns or inputs — just a display of current code + symbol + exponent.
- Helper text: *"Your tenant's currency is managed by your platform administrator. To request a change, contact support."*
- Remove all code paths tied to `display_mode: "convert"` and `currency_conversion_rate`.

Currency context at [currency-context.tsx](apps/admin-web/src/lib/currency-context.tsx):
- Drop `display_mode` and `conversion_rate` from the type and hook API.
- **Expose a `refreshCurrency()` method** so components can trigger a refetch.
- **Refetch on route change** — use `usePathname()` to detect navigation and refetch in the background. Fixes the stale-until-reload bug.

Money formatter at [format.ts:13-21](apps/admin-web/src/lib/format.ts#L13-L21):
- Remove the `rate` multiplication branch entirely. `formatMoney(cents, currency)` does pure symbol + exponent formatting.

### Cashier app

No changes. Cashier pulls currency from api via `/v1/sync/pull`; once api's response drops `display_mode` / `conversion_rate`, the cashier picks up the cleaner shape without modification.

## Migration & Rollout

### Ordering constraint

The api-side column drops are destructive. The *code* that reads `display_mode` / `conversion_rate` must ship first, then the migration drops the columns, else app crashes.

### Step-by-step

1. **Deploy new admin-web** with:
   - Read-only currency section.
   - `formatMoney` cleanup (no more rate multiplication).
   - Currency context refactor (refetch on route change, `refreshCurrency()` exposed).
2. **Deploy api service update** with:
   - New `POST /v1/internal/platform-config` endpoint.
   - Poll worker (gated by `IMS_PLATFORM_SYNC_MODE`).
   - `GET /v1/admin/tenant-settings/currency` no longer includes deprecated fields.
   - `PATCH /v1/admin/tenant-settings/currency` returns 410 Gone.
   - Code no longer references `display_mode` / `conversion_rate`.
3. **Run api Alembic migration:**
   - Add `currency_synced_at` column to `tenants`.
   - Drop `currency_display_mode` and `currency_conversion_rate` columns.
4. **Deploy platform service update** with:
   - New currency GET/PATCH endpoints.
   - New `GET /v1/internal/tenants/{slug}/config` pull endpoint.
   - Tenant create/update endpoints extended to accept new fields.
5. **Run platform Alembic migration:**
   - Add `default_currency_code`, `currency_exponent`, `currency_symbol_override`, `deployment_mode` columns to `platform_tenants` with defaults.
6. **Run cross-DB backfill script** (`services/platform/app/scripts/backfill_tenant_currency.py`):
   - Takes both DB URLs as env vars.
   - For each `platform_tenants` row, look up corresponding `tenants` row in api DB by slug.
   - Copy `default_currency_code`, `currency_exponent`, `currency_symbol_override` from api into platform.
   - Skip + log any orphan `platform_tenants` without a matching api tenant.
7. **Deploy platform-web update** with the new Currency section on tenant-edit and the deployment-mode selector.
8. **Verification:** open admin-web for a test tenant, confirm currency displays read-only; edit from platform-web, confirm push succeeds and admin-web shows new values after next navigation.

### On-prem considerations

For any existing on-prem tenants:
- Flip their `platform_tenants.deployment_mode` to `"on_prem"` manually post-backfill.
- Set `IMS_PLATFORM_SYNC_MODE=offline` on the on-prem api instance's environment at the next config update.

### Rollback

Forward-only after the api migration. Rollback requires re-creating the dropped columns (both will be empty/NULL). Document in the migration file.

### Feature flag

None. Coordinated cutover across three services.

## Testing

### Backend (unit / integration)

**Platform:**
- `PATCH /v1/platform/tenants/{id}/currency`:
  - Updates `platform_tenants` correctly.
  - Triggers HMAC push to api — verify payload shape and signature.
  - Push failure (mock 500 / timeout) — PATCH returns 200 with `push_status: "failed"`.
- `POST /v1/platform/tenants` — accepts new optional fields with defaults.
- `PATCH /v1/platform/tenants/{id}` — accepts `deployment_mode`.
- `GET /v1/internal/tenants/{slug}/config` — HMAC-gated, returns correct shape.

**API:**
- `POST /v1/internal/platform-config`:
  - Valid HMAC + newer `synced_at` → currency columns updated, `currency_synced_at` bumped, `applied: true`.
  - Valid HMAC + older `synced_at` → no change, `applied: false`.
  - Valid HMAC + `synced_at` within 2-second tolerance → no change.
  - Invalid HMAC → 401.
  - Tenant not found → 404.
- Poll worker:
  - `IMS_PLATFORM_SYNC_MODE=offline` → job does not schedule.
  - `IMS_PLATFORM_SYNC_MODE=polling` → job runs, fetches, applies, logs.
  - Platform returns 5xx → warn log, no crash, values unchanged.
  - Platform returns newer config → applied; older config → skipped.
- `GET /v1/admin/tenant-settings/currency` → response does not include `display_mode` or `conversion_rate`.
- `PATCH /v1/admin/tenant-settings/currency` → 410 Gone.

### Frontend

**Admin-web:**
- Currency section renders read-only display of current code + symbol + exponent + helper text.
- `useCurrency().refreshCurrency()` triggers a network fetch and updates context state.
- Navigating between routes triggers a background refetch (simulate via direct platform-side DB update + router push, verify admin-web picks up the new value).
- `formatMoney(cents, currency)` returns pure symbol + exponent formatting — no multiplier path.

**Platform-web:**
- Tenant edit page's Currency section renders current values, saves updates, displays push-status indicator.
- Deployment-mode selector saves and displays the confirmation dialog before applying.

### End-to-end

1. Start with two test tenants: Tenant-A (cloud, USD) and Tenant-B (on-prem, USD).
2. In platform-web, change Tenant-A's currency USD → INR. Verify push succeeds.
3. Open admin-web for Tenant-A, navigate to Settings. Confirm INR displayed read-only with correct exponent and symbol.
4. Simulate a push failure for Tenant-A (mock api instance unreachable). Verify platform-web shows "Push failed — retry." Verify next poll cycle self-heals.
5. For Tenant-B (on-prem, `IMS_PLATFORM_SYNC_MODE=offline`):
   - Change currency via platform-web. Verify push still attempts and succeeds (on-prem still receives pushes).
   - Stop the on-prem api instance. Change currency again. Verify push fails, platform-web shows error. Restart api — no auto-heal (poll is disabled); operator must manually re-push from platform-web.
6. Cashier sync-pull for both tenants — verify new currency code in response.
7. Existing transactions denominated in original cents — verify amounts unchanged (no retroactive conversion).

## Files Touched (anticipated)

### services/platform/
- `alembic/versions/` — one new revision.
- `app/models/tables.py` — new columns on `PlatformTenant`.
- `app/routers/tenants.py` — extend create/update bodies, add currency GET/PATCH.
- `app/routers/tenant_api.py` (or new `internal_sync.py`) — add `GET /v1/internal/tenants/{slug}/config`.
- `app/services/tenant_config_push.py` — new service encapsulating HMAC push to api.
- `app/scripts/backfill_tenant_currency.py` — new cross-DB backfill script.

### services/api/
- `alembic/versions/` — one new revision.
- `app/models/tables.py` — add `currency_synced_at`, remove `currency_display_mode` and `currency_conversion_rate`.
- `app/routers/admin_platform.py` — remove PATCH currency route; update GET response shape.
- `app/routers/internal_sync.py` — new file, `POST /v1/internal/platform-config`.
- `app/worker.py` — register poll job gated on `IMS_PLATFORM_SYNC_MODE`.
- `app/services/platform_sync.py` — new service encapsulating HMAC pull from platform.
- `app/config.py` — `IMS_PLATFORM_SYNC_MODE`, `IMS_PLATFORM_SYNC_INTERVAL_SECONDS` env vars.

### apps/platform-web/
- New "Currency" section on tenant edit page.
- Deployment-mode selector on tenant edit page.

### apps/admin-web/
- `src/app/(main)/settings/page.tsx` — currency section becomes read-only.
- `src/lib/currency-context.tsx` — drop deprecated fields, add `refreshCurrency()`, refetch on route change.
- `src/lib/format.ts` — remove rate-multiplication branch.

Exact paths confirmed during plan writing.
