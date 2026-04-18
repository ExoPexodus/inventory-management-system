# Auto-Resolve Reconciliation Variances — Design

**Date:** 2026-04-19
**Status:** Approved for planning
**Scope:** services/api, apps/admin-web

## Summary

Allow tenant admins to configure a monetary threshold below which cash reconciliation variances are auto-resolved at shift close. Shortages and overages have separate thresholds. Thresholds default to tenant-level and may be overridden per shop. Auto-resolution attributes the action to a per-tenant "system" user, applies a distinctive note marker, and renders a visible badge in the admin UI. Auto-resolved shifts still require manual admin approval before closing out.

## Motivation

Today every non-zero variance — even a ₹1 short — forces an admin to open the shift, type a resolution note, and click Resolve, then click Approve. For SMBs running many shifts per week, small variances ("pocket change" noise from rounding, miscounts) generate repetitive busywork with no real investigative value. Giving admins a configurable "this much is fine" threshold removes the busywork while preserving visibility — patterns of repeated small variances remain auditable via the badge and the resolution note.

## Non-Goals

- **Auto-approval.** Auto-resolved shifts still enter the approval queue. A human confirms before closing out.
- **Retroactive auto-resolve.** Applying a newly configured threshold to already-pending shifts is out of scope. Forward-only.
- **Asymmetric logic beyond shortage/overage.** Per-cashier, per-time-window, or pattern-based auto-resolve is out of scope.
- **Cashier-app changes.** Cashiers close shifts as they do today; the feature is invisible to them.

## Data Model

### `tenants` table — two new columns

| Column | Type | Nullable | Default | Meaning |
|---|---|---|---|---|
| `auto_resolve_shortage_cents` | integer | NOT NULL | `0` | Shortages with `|variance| ≤ this` auto-resolve. `0` = off. |
| `auto_resolve_overage_cents` | integer | NOT NULL | `0` | Overages with `variance ≤ this` auto-resolve. `0` = off. |

### `shops` table — two new nullable columns

| Column | Type | Nullable | Default | Meaning |
|---|---|---|---|---|
| `auto_resolve_shortage_cents_override` | integer | YES | `NULL` | Shop-specific shortage threshold. `NULL` = inherit tenant default. |
| `auto_resolve_overage_cents_override` | integer | YES | `NULL` | Shop-specific overage threshold. `NULL` = inherit tenant default. |

An override value of `0` disables auto-resolve for that shop even when the tenant default is nonzero. This is intentional: `NULL` = inherit, `0` = explicitly off.

### `users` table — new `system` role

The existing unified `User` model (post Employee→User migration) gains a `system` role value. One `system` user is seeded per tenant, used for attribution of automated actions. This sentinel is scoped to the tenant (respects RLS) and cannot log in (unusable password hash).

## Resolution Logic

Triggered synchronously inside the existing shift-close path in [services/api/app/routers/admin_shifts.py](services/api/app/routers/admin_shifts.py) where `discrepancy_cents` is computed.

```
shortage_threshold = shop.auto_resolve_shortage_cents_override ?? tenant.auto_resolve_shortage_cents
overage_threshold  = shop.auto_resolve_overage_cents_override  ?? tenant.auto_resolve_overage_cents

if discrepancy_cents == 0:
    # existing zero-variance path, no change
elif discrepancy_cents < 0 and shortage_threshold > 0 and abs(discrepancy_cents) <= shortage_threshold:
    auto_resolve(reason="shortage", threshold=shortage_threshold)
elif discrepancy_cents > 0 and overage_threshold > 0 and discrepancy_cents <= overage_threshold:
    auto_resolve(reason="overage", threshold=overage_threshold)
else:
    # existing manual-review path, no change
```

**`auto_resolve()` effect:**

1. Append a resolution note of the form `[AUTO-RESOLVED] Variance <signed amount> within <shop|tenant> <shortage|overage> threshold of <threshold amount>.`
2. Set `resolved_by_user_id` = tenant's system user id.
3. Set `resolved_at` = now.

`_rec_status()` ([admin_reconciliation.py:54-65](services/api/app/routers/admin_reconciliation.py#L54-L65)) currently matches the substring `[RESOLVED` to promote status to `resolved`. Since `[AUTO-RESOLVED]` does not contain that substring, `_rec_status()` must be extended to also match `[AUTO-RESOLVED`. No change to the `resolved` status enumeration itself — both manual and auto-resolved paths land on the same status, with the `auto_resolved` boolean (see API Changes) being the distinguishing signal.

## API Changes

### Tenant-level settings (new)

- `GET /v1/admin/tenant-settings/reconciliation` →
  ```json
  { "auto_resolve_shortage_cents": 5000, "auto_resolve_overage_cents": 5000 }
  ```
- `PATCH /v1/admin/tenant-settings/reconciliation` — accepts either/both fields. Validates non-negative integers. Tenant admins only.

Implemented alongside the existing `/v1/admin/tenant-settings/currency` pattern in [services/api/app/routers/admin_platform.py](services/api/app/routers/admin_platform.py).

### Shop-level settings (extension)

- `GET /v1/admin/shops/{shop_id}` — response gains `auto_resolve_shortage_cents_override` and `auto_resolve_overage_cents_override` (nullable).
- `PATCH /v1/admin/shops/{shop_id}` — accepts either/both fields. `null` clears the override; non-null must be a non-negative integer.

### Reconciliation list response (extension)

Each shift row in the existing reconciliation list response gains a computed boolean:

```
auto_resolved = true iff
  resolution_note starts with "[AUTO-RESOLVED]"
  AND resolved_by_user_id == tenant's system user id
```

No new endpoints for the auto-resolve action itself — it is always inline during shift close.

## Admin Web UI Changes

### Tenant settings page — new "Reconciliation" section

Two money inputs, respecting the tenant currency formatting helper ([formatMoney](apps/admin-web/src/lib/format.ts#L13)):

- **Shortage auto-resolve limit** — help text: *"Variances where the cashier counted less than expected, up to this amount, will be auto-resolved. Set to 0 to disable."*
- **Overage auto-resolve limit** — help text: *"Variances where the cashier counted more than expected, up to this amount, will be auto-resolved. Set to 0 to disable."*

Single Save button, patches `PATCH /v1/admin/tenant-settings/reconciliation`.

### Shop edit page — new "Reconciliation overrides" section

Two optional money inputs, each paired with a "Use tenant default" toggle. Toggle on → input disabled, value sent as `null`. Toggle off → input enabled, non-negative integer required. Helper line under each input: *"Tenant default: ₹50"* (or whatever the tenant-level value is, formatted using the tenant currency).

### Reconciliation list page ([apps/admin-web/src/app/(main)/reconciliation/page.tsx](apps/admin-web/src/app/(main)/reconciliation/page.tsx))

- Rows with `auto_resolved === true` render a small "Auto" pill badge adjacent to the existing status chip. Muted/secondary color to avoid competing visually with status.
- The expanded details view already shows resolution notes ([reconciliation/page.tsx:267-292](apps/admin-web/src/app/(main)/reconciliation/page.tsx#L267-L292)). The `[AUTO-RESOLVED]` prefix in the note answers *why* at a glance — no additional UI needed there.
- Approve/Resolve button flow unchanged. Auto-resolved shifts still surface the "Approve" button (since they are `resolved` status, not `approved`).

### Cashier app

No changes.

## Migration & Rollout

### Alembic migration (single revision)

1. Add `auto_resolve_shortage_cents` and `auto_resolve_overage_cents` columns to `tenants` (`NOT NULL DEFAULT 0`).
2. Add `auto_resolve_shortage_cents_override` and `auto_resolve_overage_cents_override` columns to `shops` (nullable).
3. Add `system` to the `User.role` enum (or equivalent flag on the unified User model).
4. **Data migration:** for every existing `Tenant`, insert one `User` row with role=`system`, synthetic email `system+{tenant_id}@internal.ims`, and an unusable password hash (e.g. `!` prefix that cannot match any valid hash). Must run inside the same revision so the invariant "every tenant has a system user" holds immediately after upgrade.

### Tenant provisioning

Extend the tenant-creation flow to seed the system user as part of the same transaction. New tenants never exist without a system user.

### Feature flag / gating

None. The `0` default on both tenant columns means the feature is dormant on every existing tenant until an admin explicitly configures it. There is no risk of silent behavior change on deploy.

## Testing

Unit + integration tests covering:

- **No regression baseline:** zero-variance close behaves exactly as before.
- **Threshold matching:**
  - Variance strictly within threshold → auto-resolved.
  - Variance exactly at threshold → auto-resolved (inclusive `≤`).
  - Variance one cent over threshold → manual-review path.
- **Disabled path:** threshold of `0` never auto-resolves, even at 1 cent variance.
- **Direction isolation:**
  - Shortage threshold set, overage threshold `0`: overage variance routes to manual.
  - Overage threshold set, shortage threshold `0`: shortage variance routes to manual.
- **Shop override precedence:**
  - Shop override (non-null) wins over tenant default.
  - Shop override of `0` disables auto-resolve even when tenant default is nonzero.
  - Shop override `NULL` falls back to tenant default.
- **Attribution:** auto-resolved shifts have `resolved_by_user_id` = tenant system user id and note prefix `[AUTO-RESOLVED]`.
- **Status:** `_rec_status()` computes `resolved` (not `approved`) for auto-resolved shifts.
- **RLS:** tenant A's admin cannot see tenant B's system user.
- **API surface:**
  - `PATCH /v1/admin/tenant-settings/reconciliation` rejects negative integers.
  - `PATCH /v1/admin/shops/{id}` accepts `null` to clear overrides and rejects negative integers.
  - Reconciliation list response includes correct `auto_resolved` boolean.
- **UI:** badge renders iff `auto_resolved === true`; "Use tenant default" toggle correctly serializes to `null`.

## Files Touched (anticipated)

- `services/api/alembic/versions/` — one new revision file.
- `services/api/app/db/tables.py` — new columns on `Tenant`, `Shop`; new role on `User`.
- `services/api/app/routers/admin_platform.py` — new reconciliation settings routes.
- `services/api/app/routers/admin_shops.py` (or wherever shop CRUD lives) — override fields in GET/PATCH.
- `services/api/app/routers/admin_shifts.py` — auto-resolve branch at close time.
- `services/api/app/routers/admin_reconciliation.py` — `auto_resolved` field in list response; extend `_rec_status()` to match `[AUTO-RESOLVED` prefix.
- `services/api/app/services/tenant_provisioning.py` (or equivalent) — seed system user on tenant create.
- `apps/admin-web/src/app/(main)/settings/` — tenant settings "Reconciliation" section.
- `apps/admin-web/src/app/(main)/shops/[id]/edit/` — shop override section.
- `apps/admin-web/src/app/(main)/reconciliation/page.tsx` — "Auto" badge rendering.

Exact paths confirmed during plan writing.
