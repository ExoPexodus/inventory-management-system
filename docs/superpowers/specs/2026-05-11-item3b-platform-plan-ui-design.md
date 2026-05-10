# Item 3b — Platform Plan-Feature UI

**Date:** 2026-05-11
**Effort:** 4-5 days (large; touches both codebases + platform-web)

## Goal
Move plan-feature mapping (the `PLAN_FEATURES` dict in IMS `services/api/app/billing/plans.py`) into the platform DB, expose CRUD UI for plan operators, and propagate changes to tenants. Drop the hardcoded constants entirely.

## Current state
- Plans CRUD already works (`services/platform/app/routers/plans.py`).
- Plans have `max_shops`, `max_employees`, `storage_limit_mb` columns. The 20+ richer features (`max_channels`, `shopify_connector`, `headless_api`, etc.) are NOT in the DB — they live in IMS `plans.py`.
- `TenantLimitOverride` exists with int-only `limit_value`. Doesn't support boolean/enum features.
- `LicenseResponse` carries only the 3 hardcoded limits. Plan-features section in platform-web reads from IMS's hardcoded constants via `/v1/internal/platform/plan-features`.
- `is_active` flag on Plan exists; no delete endpoint.

## Locked decisions (Q10–14)
- **Hotfix shipped first** ✓ (Item 3a done).
- **Apply to existing tenants:** per-change "Apply to existing: yes/no" checkbox on plan save. Yes triggers immediate license sync for all subscribed tenants.
- **Plan archive + delete:** archive (`is_active=false`) hides plan from new assignment; delete only allowed after archive AND no remaining tenants.
- **Drop `plans.py` constants entirely** once DB is source of truth.
- **Bulk overrides v1:** include cohort filter UI (filter by current plan / business type / region) + apply-to-all-matching.

## Schema

### `plan_features` (new, platform DB)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| plan_id | UUID FK plans CASCADE | |
| feature_key | String(128) | |
| value | JSONB | bool/int/string |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Composite unique: `(plan_id, feature_key)`. Index on `plan_id`.

### `tenant_limit_overrides` (extend, platform DB)
Add column:
| Column | Type | Notes |
|---|---|---|
| value_json | JSONB | nullable; preferred over the int `limit_value` |

Migration backfills `value_json = jsonb_build_object('value', limit_value)` for existing rows. Update the resolver to read `value_json` first, fall back to `limit_value` for legacy rows. New writes use `value_json` only.

Then add a `limit_key` migration to allow longer keys (feature codename names can be longer than the int-limit-only legacy ones). Current column is `String(64)` — fine; the FEATURE_CATALOG keys are all <30 chars.

### Migration `platform_..._plan_features.py`
Create `plan_features` table + add `value_json` to `tenant_limit_overrides` + data backfill:
1. Create `plan_features` table.
2. For each existing plan codename in `PLAN_FEATURES` (copy the dict literally into the migration), INSERT rows.
3. Add `value_json` column.
4. Backfill: `UPDATE tenant_limit_overrides SET value_json = jsonb_build_object('value', limit_value)`.

## Backend — platform service

### `plan_features` CRUD endpoints

```
GET    /v1/platform/plans/{plan_id}/features         → {feature_key: value, ...}
PUT    /v1/platform/plans/{plan_id}/features         → body: {feature_key: value, ...} (replace set)
```

PUT validates `feature_key` is in the known feature catalog (which IMS publishes via `/v1/internal/platform/plan-features`). Platform fetches that catalog once at startup and caches it for validation. Reject unknown keys with 422.

### `plan_features` change → optional cascade
On PATCH plan or PUT features:
- Accept optional query param `apply_to_existing: bool = False`.
- When `true`, for every Subscription on this plan, increment a "needs-resync" flag (or trigger an immediate IMS HMAC-authenticated POST telling each tenant's IMS to call `sync_tenant_license`). Simplest implementation: enqueue a background job per affected tenant that hits the IMS `/v1/internal/license-sync-trigger` endpoint (new — see below).
- When `false`, no action; tenants pick up new values at next periodic sync.

### Plan delete

```
DELETE /v1/platform/plans/{plan_id}
```
Validation:
- 409 if plan has any active subscriptions (any Subscription with `cancelled_at IS NULL`)
- 409 if plan `is_active = true` (must archive first)
- On delete: cascade kills `plan_features` rows.

### Override CRUD + bulk

```
GET    /v1/platform/tenants/{id}/overrides           → list overrides
PUT    /v1/platform/tenants/{id}/overrides/{key}     → body: {value: any, reason?: str}
DELETE /v1/platform/tenants/{id}/overrides/{key}     → remove override

POST   /v1/platform/overrides/bulk                   → cohort-apply
  body: {
    filter: {plan_codename?, business_type?, region?},
    feature_key: str,
    value: any,
    reason: str,
  }
  → returns {affected_tenant_ids: [...]}
```

Bulk endpoint queries Subscriptions joined on PlatformTenant for matching filters, then upserts an override per matched tenant. Returns count + IDs for confirmation.

### Extend `LicenseResponse`

Add to platform's `LicenseResponse`:
```python
plan_features: dict[str, Any] = {}
```
`build_license_state` now joins `plan_features` for the resolved plan, applies overrides, returns the full feature map.

### Drop `subscription_service.build_license_state` int-only limits

The 3 hardcoded fields (`max_shops`, `max_employees`, `storage_limit_mb`) become entries in `plan_features` — but the LicenseResponse keeps the dedicated columns for backward compat with consumers (IMS license_service reads them directly). Just ensure `plan_features` also contains them for the new resolver path.

## Backend — IMS

### License sync update
`license_service._upsert_cache` already writes `raw_payload` to `TenantLicenseCache.raw_payload`. Add extraction of `plan_features` from the payload and persist into a new column `plan_features: JSONB` on `TenantLicenseCache` (so resolver doesn't have to parse raw_payload repeatedly).

Migration on IMS side: add `plan_features JSONB` column to `tenant_license_cache`.

### Resolver update
Update `app/billing/plans.py::resolve_plan_value` to take an extra `tenant_id` arg (or get the cache another way). The new logic:
1. Read `tenant_license_cache.plan_features` for the tenant
2. If `feature_key` is in that dict, return its value
3. Fall back to `resolve_default(feature_key)`

The hardcoded `PLAN_FEATURES` constant is removed.

Call sites of `resolve_plan_value` will need updating to pass tenant_id. Search for all call sites in `entitlements.py`.

### New endpoint for cascade trigger
```
POST /v1/internal/license-sync-trigger
  body: {tenant_id: UUID}
  auth: HMAC like the platform license fetch
```
Calls `sync_tenant_license(db, tenant_id)` synchronously. Used by platform's "apply to existing" path.

## Frontend — platform-web

### `/plans/page.tsx` updates
Existing page already lists plans + addons + feature matrix. Changes:

1. **Plan edit form** — extend the existing form to include a feature-value editor. Render each feature from the catalog with the right input control:
   - BOOL → toggle
   - NUMERIC → number input
   - ENUM → select (future-proof)
2. **"Apply to existing" checkbox** on the plan save form. Defaults unchecked.
3. **Archive button** per plan row (calls PATCH with `is_active=false`).
4. **Delete button** per archived plan (calls DELETE; shows 409 errors clearly with the count of remaining tenants).

### New page `/tenants/[id]/overrides` (platform-web)
Or extend the existing tenant detail page with an "Overrides" section:
- List current overrides for the tenant
- "Add override" form: feature dropdown + value input (typed by feature)
- "Remove" button per override

### New page `/overrides/bulk` (platform-web)
- Filter form: plan / business_type / region
- "Preview affected tenants" button → shows count
- Feature + value + reason
- "Apply to N tenants" button with confirmation

## Files

| File | Status |
|---|---|
| Platform side | |
| `services/platform/alembic/versions/..._plan_features.py` | NEW migration: table + override JSONB |
| `services/platform/app/models/tables.py` | Add `PlanFeature` model, extend `TenantLimitOverride` |
| `services/platform/app/routers/plans.py` | Add features GET/PUT, delete endpoint, apply_to_existing logic |
| `services/platform/app/routers/tenants.py` | Add overrides CRUD + bulk |
| `services/platform/app/services/subscription_service.py` | Include `plan_features` in build_license_state |
| `services/platform/app/services/feature_catalog.py` (NEW) | Cached fetch of IMS feature catalog for validation |
| IMS side | |
| `services/api/alembic/versions/..._tenant_license_cache_features.py` | NEW migration: add `plan_features` JSONB column |
| `services/api/app/models/tables.py` | Add `plan_features` field to `TenantLicenseCache` |
| `services/api/app/services/license_service.py` | Persist plan_features from payload |
| `services/api/app/billing/plans.py` | Replace constant + resolver to read from cache |
| `services/api/app/billing/entitlements.py` | Update call sites to pass tenant_id |
| `services/api/app/routers/internal_license_sync.py` (NEW) | HMAC-authenticated trigger endpoint |
| `services/api/app/main.py` | Register new router |
| Frontend | |
| `apps/platform-web/src/app/(main)/plans/page.tsx` | Feature editor + archive/delete UI + apply-to-existing |
| `apps/platform-web/src/app/(main)/tenants/[id]/page.tsx` | Add overrides section |
| `apps/platform-web/src/app/(main)/overrides/bulk/page.tsx` (NEW) | Bulk cohort apply page |

## Out of scope
- Plan versioning (snapshot a plan's features as v1, v2 to allow tenants to stay on older versions). Tabled as future enhancement.
- Custom feature catalog management (the feature catalog itself stays as code in IMS — only plan-feature MAPPING is in platform DB).
- Pricing tier complexity (multiple billing cycles per plan, regional pricing, etc.).
- Notification to tenants when their plan features change.
