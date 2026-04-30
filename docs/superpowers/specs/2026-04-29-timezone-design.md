# Domain 31 — Timezone per Tenant & Shop

**Date:** 2026-04-29
**Author:** Rushil Rana
**Status:** Approved

## Context

All datetimes in the IMS are stored as UTC (`timestamp with time zone`). The system has no per-tenant or per-shop timezone field. This causes three concrete problems:

1. **Analytics day-bucketing is wrong.** `date_trunc('day', created_at)` operates on UTC, so an Indian shop's 11 PM sale (IST = UTC+5:30) appears on the wrong calendar day.
2. **Financial year is hardcoded to Jan–Dec.** India's FY runs April–March. Reports cannot correctly compute "this financial year."
3. **Frontend and cashier display times in the wrong timezone.** All `toLocaleString` calls use the browser's system timezone; the Flutter cashier has no timezone context at all.

This spec covers the full Domain 31 implementation: schema, API, analytics fix, financial year helper, sync protocol, admin web, and Flutter cashier.

---

## What Is Already Built

- All `DateTime(timezone=True)` columns store UTC correctly — no migration of existing data needed.
- `python-dateutil` is not in use; only stdlib `datetime` with `UTC`. Python 3.12 ships `zoneinfo` in stdlib.
- Tenant settings endpoints live in `services/api/app/routers/admin_platform.py` at `/v1/admin/tenant-settings/*`.
- Shop CRUD lives in `services/api/app/routers/admin_web.py`. The shop edit page is at `apps/admin-web/src/app/(main)/shops/[id]/edit/page.tsx`.
- The hourly heatmap is in `services/api/app/routers/admin_analytics.py:412`; the sales series is in `services/api/app/routers/admin_web.py:392`.

---

## Design

### 1. Schema — 3 new columns

**`tenants` table:**
- `timezone: VARCHAR(64)` — IANA timezone string (e.g. `Asia/Kolkata`, `America/Toronto`). `NULL` treated as `UTC` at query time.
- `financial_year_start_month: SMALLINT` — 1–12. `NULL` treated as `1` (January). India uses `4` (April).

**`shops` table:**
- `timezone: VARCHAR(64)` — per-shop IANA override. `NULL` falls back to tenant's timezone, then `UTC`.

One Alembic migration covers all three columns. All columns are nullable with no server default (application-level defaulting is intentional — `NULL` means "not set, use parent default").

### 2. Timezone resolution helper

A shared function used throughout the API:

```python
# services/api/app/services/localisation.py (new file)
from zoneinfo import ZoneInfo, available_timezones

FALLBACK_TZ = "UTC"

def effective_timezone(shop: Shop | None, tenant: Tenant | None) -> str:
    """Return the resolved IANA timezone string for the given shop/tenant pair."""
    if shop and shop.timezone:
        return shop.timezone
    if tenant and tenant.timezone:
        return tenant.timezone
    return FALLBACK_TZ

def validate_iana_timezone(tz: str) -> bool:
    return tz in available_timezones()

def fy_range(financial_year_start_month: int, reference_date: date) -> tuple[date, date]:
    """Return (fy_start, fy_end) containing reference_date."""
    m = financial_year_start_month or 1
    year = reference_date.year
    fy_start = date(year, m, 1)
    if reference_date < fy_start:
        fy_start = date(year - 1, m, 1)
    fy_end = date(fy_start.year + 1, m, 1) - timedelta(days=1)
    return fy_start, fy_end
```

### 3. Tenant localisation settings endpoint (new)

`GET /v1/admin/tenant-settings/localisation` — returns `{ timezone, financial_year_start_month }`.

`PATCH /v1/admin/tenant-settings/localisation` — updates both fields. Timezone validated against `zoneinfo.available_timezones()`; invalid string returns 422. Month validated as 1–12.

Pattern matches the existing `tenant-settings/device-security` endpoint in `admin_platform.py`.

### 4. Shop timezone field

`PATCH /v1/admin/shops/{shop_id}` already exists in `admin_web.py`. Add `timezone: str | None` to `PatchShopBody`. Validated the same way. `ShopOut` response schema gains `timezone: str | None`.

### 5. Analytics — timezone-aware queries

**Sales series** (`admin_web.py:401`):

Replace:
```python
day_bucket = func.date_trunc("day", Transaction.created_at).label("day")
start = datetime.now(UTC) - timedelta(days=days)
```

With:
```python
tz = effective_timezone(shop_row, tenant)  # resolved from DB
day_bucket = func.date_trunc(
    "day",
    func.timezone(tz, Transaction.created_at)
).label("day")
# Window start: local midnight `days` days ago
local_now = datetime.now(ZoneInfo(tz))
start = (local_now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
start_utc = start.astimezone(UTC)
```

`sales_series` gains an optional `shop_id: UUID | None` query parameter so it can resolve the shop timezone. When absent, tenant timezone is used.

**Hourly heatmap** (`admin_analytics.py:432`):

Replace:
```python
hour_col = extract("hour", Transaction.created_at).label("hour")
distinct_days = ... func.date_trunc("day", Transaction.created_at) ...
```

With:
```python
local_ts = func.timezone(tz, Transaction.created_at)
hour_col = extract("hour", local_ts).label("hour")
distinct_days = ... func.date_trunc("day", local_ts) ...
```

**Dashboard 30-day window** (`admin_web.py:311`):

```python
tz = effective_timezone(None, tenant)
local_now = datetime.now(ZoneInfo(tz))
period_start = (local_now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
prev_start = (local_now - timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
```

### 6. Financial year helper — usage

`fy_range` is used in two places in Chunk 1:

1. **Report date range picker default** — when a report page loads, the default date range is "current FY" using `fy_range(tenant.financial_year_start_month, today)`.
2. **Invoice sequence reset** — not built yet (Domain 13, Chunk 2). The helper is defined now and called there later.

### 7. Sync pull — `shop_timezone` field

Add to `SyncPullResponse` in `sync.py`:

```python
shop_timezone: str  # resolved effective timezone, never null — always "UTC" minimum
```

Populated in the `sync_pull` handler:
```python
shop_timezone=effective_timezone(shop_row, tenant),
```

Update `packages/sync-protocol/openapi.yaml` — add `shop_timezone` to the `SyncPullResponse` schema.

### 8. Admin web — localisation settings panel

Add a "Localisation" card to `apps/admin-web/src/app/(main)/settings/page.tsx` (matches the existing currency, device security, reconciliation card pattern).

Fields:
- **Timezone** — a `<select>` populated from a curated list of IANA timezone strings grouped by region (not all 600+ — a curated list of ~60 commonly used ones covering India, Indonesia, Canada, and global cities).
- **Financial year start** — a `<select>` with 12 month options.

The curated timezone list lives in `apps/admin-web/src/lib/timezones.ts` — a plain exported array.

### 9. Admin web — shop edit page timezone field

`apps/admin-web/src/app/(main)/shops/[id]/edit/page.tsx` gains a **Timezone** `<select>` (same curated list). When left blank (`""`), `null` is sent to the API and the shop inherits the tenant's timezone.

### 10. Admin web — date/time display fix

**New hook:** `apps/admin-web/src/lib/use-timezone.ts`

```typescript
export function useShopTimezone(): string {
  // Reads from a context or falls back to "UTC".
  // Populated by a TenantSettingsProvider wrapping the (main) layout.
}
```

A `TenantSettingsProvider` in `apps/admin-web/src/app/(main)/layout.tsx` fetches `GET /v1/admin/tenant-settings/localisation` once on load and stores `{ timezone, financialYearStartMonth }` in React context.

**`fmtDatetime` updated** — all existing `toLocaleString("en-US", ...)` calls in the admin web gain `timeZone: shopTimezone`. Locale stays `undefined` (browser locale) since locale (number/date format style) is separate from timezone.

The `fmtDatetime` helper is currently defined inline in multiple page files. It is extracted to `apps/admin-web/src/lib/format.ts` as a shared export:

```typescript
export function fmtDatetime(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleString(undefined, {
    timeZone,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
```

Pages that use `fmtDatetime` (shifts, reconciliation, audit, orders, overview) call `useShopTimezone()` and pass it through.

### 11. Flutter cashier — local time rendering

Add the `timezone` Dart package to `apps/cashier/pubspec.yaml`. This package provides `TZDateTime` and a timezone database.

`ProductRow.merged()` already receives `shop_timezone` from the sync payload (it flows through `SyncPullResponse`). Store it in a `LocalisationStore` singleton (or `InheritedWidget`) accessible app-wide.

Replace raw `DateTime` display in:
- Shift open/close time display
- Transaction timestamp on receipt preview

With:
```dart
import 'package:timezone/timezone.dart' as tz;

final location = tz.getLocation(shopTimezone);
final localDt = tz.TZDateTime.from(utcDateTime, location);
```

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `services/api/alembic/versions/20260429000002_tenant_shop_timezone.py` | Create | Migration: 3 new columns |
| `services/api/app/models/tables.py` | Modify | `Tenant.timezone`, `Tenant.financial_year_start_month`, `Shop.timezone` |
| `services/api/app/services/localisation.py` | Create | `effective_timezone()`, `validate_iana_timezone()`, `fy_range()` |
| `services/api/app/routers/admin_platform.py` | Modify | GET/PATCH `tenant-settings/localisation` endpoints |
| `services/api/app/routers/admin_web.py` | Modify | `PatchShopBody` + `ShopOut` gain `timezone`; sales series + dashboard gain timezone-aware queries |
| `services/api/app/routers/admin_analytics.py` | Modify | Hourly heatmap gains timezone-aware queries |
| `services/api/app/routers/sync.py` | Modify | `SyncPullResponse` gains `shop_timezone` |
| `packages/sync-protocol/openapi.yaml` | Modify | Add `shop_timezone` to `SyncPullResponse` schema |
| `apps/admin-web/src/lib/timezones.ts` | Create | Curated IANA timezone list (~60 entries) |
| `apps/admin-web/src/lib/format.ts` | Modify | Add `fmtDatetime(iso, timeZone)` shared export |
| `apps/admin-web/src/lib/use-timezone.ts` | Create | `useShopTimezone()` hook |
| `apps/admin-web/src/app/(main)/layout.tsx` | Modify | `TenantSettingsProvider` wrapping the layout |
| `apps/admin-web/src/app/(main)/settings/page.tsx` | Modify | Localisation settings card |
| `apps/admin-web/src/app/(main)/shops/[id]/edit/page.tsx` | Modify | Timezone field on shop edit |
| `apps/cashier/pubspec.yaml` | Modify | Add `timezone` package |
| `apps/cashier/lib/services/inventory_api.dart` | Modify | Parse `shop_timezone` from sync response |
| `apps/cashier/lib/services/localisation_store.dart` | Create | Singleton holding resolved shop timezone |
| `apps/cashier/lib/widgets/…` | Modify | Replace `DateTime` display with `TZDateTime` in shift and receipt widgets |

---

## Testing

**Contract tests** (no DB):
- `test_effective_timezone()` — shop override, tenant fallback, null fallback to UTC
- `test_fy_range()` — April–March boundary crossing, January FY, reference date exactly on FY start/end
- `test_validate_iana_timezone()` — valid string, invalid string
- `test_localisation_settings_schema()` — GET/PATCH response shapes

**Out of scope for this task:**
- Integration tests against a live DB (no integration test harness currently exists)
- Flutter widget tests

---

## Implementation Notes

- `func.timezone(tz, col)` is the SQLAlchemy / PostgreSQL idiom for `col AT TIME ZONE tz`. It returns a timezone-naive `timestamp` representing local time — `date_trunc` and `extract` then operate correctly on it.
- The curated timezone list should include at minimum: all Indian timezones (`Asia/Kolkata`), all Indonesian timezones (`Asia/Jakarta`, `Asia/Makassar`, `Asia/Jayapura`), all Canadian timezones (`America/Vancouver`, `America/Edmonton`, `America/Winnipeg`, `America/Toronto`, `America/Halifax`, `America/St_Johns`), and the major UTC offsets.
- `available_timezones()` from `zoneinfo` is the validation source of truth — never validate against the curated list, which is UI-only.
- The `timezone` Dart package requires `flutter pub run timezone:create_default_timezone_data` to bundle the IANA database. Add this as a step in the Flutter build notes.

---

## Out of Scope

- GSTR/FY-aware invoice numbering — Domain 23 Chunk 2
- Hindi/Bahasa/French locale strings — Domain 30 (i18n framework)
- Admin mobile app timezone display — follow-up after cashier is done
