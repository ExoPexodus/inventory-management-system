# Item 3a — Tenant Creation Gap Fixes (Hotfix)

**Date:** 2026-05-11
**Effort:** ½ day. Small focused PR shipped BEFORE Item 3b.

## Three bugs

### Gap 1 — Storage mode not forwarded
- Platform-web UI already POSTs `storage_mode` + 6 BYO fields to `POST /v1/platform/tenants`.
- Platform's `TenantCreate` Pydantic model at `services/platform/app/routers/tenants.py:31` only declares 11 fields, no storage fields. Pydantic's default `extra="ignore"` silently drops them.
- `services/platform/app/services/tenant_provision.py:36-46` passes only 5 fields onward to IMS.
- Result: tenant always provisions with `storage_mode="platform"`; BYO buckets never wire up.

### Gap 2 — No TenantLicenseCache seeded at provision time
- `TenantLicenseCache` is populated by the periodic `sync_all_tenant_licenses` task and on-demand via `sync_tenant_license` when stale.
- New tenants have NO cache row until the next sync, leaving a window where admin-web reads the cache and gets None.

### Gap 3 — No initial subscription on platform side
- `POST /v1/platform/tenants` creates a `PlatformTenant` row but no `Subscription` row.
- License sync endpoint on the platform side reads from `Subscription`; without one, the IMS-side sync returns generic defaults rather than the tenant's actual plan limits.

## Fixes

### Platform service (`services/platform/`)

**1. Extend `TenantCreate`** to accept storage fields (mirror the IMS provision body):
```python
storage_mode: str = Field(default="platform", pattern="^(platform|byo)$")
byo_storage_endpoint: str | None = None
byo_storage_bucket: str | None = None
byo_storage_access_key: str | None = None
byo_storage_secret_key: str | None = None
byo_storage_public_url: str | None = None
byo_storage_region: str | None = "auto"
plan_codename: str = "starter"  # default plan assigned at creation; operator can change later
trial_days: int = Field(default=14, ge=0, le=90)
```

**2. Update `provision_tenant()`** to forward all storage fields + the new license seed:
```python
def provision_tenant(
    tenant: PlatformTenant,
    admin_email: str,
    admin_password: str,
    *,
    storage_mode: str = "platform",
    byo_storage_endpoint: str | None = None,
    byo_storage_bucket: str | None = None,
    byo_storage_access_key: str | None = None,
    byo_storage_secret_key: str | None = None,
    byo_storage_public_url: str | None = None,
    byo_storage_region: str | None = "auto",
    initial_license: dict | None = None,
) -> ProvisionResult:
    ...
    json={
        "tenant_id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "admin_email": admin_email,
        "admin_password": admin_password,
        "storage_mode": storage_mode,
        "byo_storage_endpoint": byo_storage_endpoint,
        "byo_storage_bucket": byo_storage_bucket,
        "byo_storage_access_key": byo_storage_access_key,
        "byo_storage_secret_key": byo_storage_secret_key,
        "byo_storage_public_url": byo_storage_public_url,
        "byo_storage_region": byo_storage_region,
        "initial_license": initial_license,
    }
```

**3. Create initial `Subscription` row in `create_tenant`** after the tenant is flushed but before `provision_tenant`:
```python
plan = db.execute(
    select(Plan).where(Plan.codename == body.plan_codename, Plan.is_active == True)
).scalar_one_or_none()
if plan is None:
    db.rollback()
    raise HTTPException(404, f"Plan '{body.plan_codename}' not found or inactive")

now = datetime.now(UTC)
trial_end = now + timedelta(days=body.trial_days) if body.trial_days > 0 else None
sub = Subscription(
    tenant_id=tenant.id,
    plan_id=plan.id,
    status="trial" if trial_end else "active",
    billing_cycle="monthly",
    trial_ends_at=trial_end,
    current_period_start=now,
    current_period_end=trial_end or (now + timedelta(days=30)),
)
db.add(sub)
db.flush()
```

Then assemble `initial_license` from the plan + subscription and pass it to provision:
```python
initial_license = {
    "subscription_status": sub.status,
    "plan_codename": plan.codename,
    "billing_cycle": sub.billing_cycle,
    "max_shops": plan.max_shops,
    "max_employees": plan.max_employees,
    "storage_limit_mb": plan.storage_limit_mb,
    "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
    "current_period_end": sub.current_period_end.isoformat(),
    "grace_period_days": sub.grace_period_days,
}
```

### IMS service (`services/api/`)

**4. Extend `ProvisionTenantBody`** (`services/api/app/routers/platform_provision.py`):
```python
class InitialLicensePayload(BaseModel):
    subscription_status: str
    plan_codename: str
    billing_cycle: str | None = None
    max_shops: int = 1
    max_employees: int = 5
    storage_limit_mb: int = 500
    trial_ends_at: str | None = None
    current_period_end: str | None = None
    grace_period_days: int = 7

class ProvisionTenantBody(BaseModel):
    ...
    initial_license: InitialLicensePayload | None = None
```

**5. Seed `TenantLicenseCache`** at the end of `provision_tenant()`:
```python
if body.initial_license is not None and tenant_status == "created":
    from app.services.license_service import _upsert_cache
    _upsert_cache(db, tenant_id, body.initial_license.model_dump())
```

(Reuse the existing `_upsert_cache` helper so the schema mapping stays in one place.)

## Verification
1. Migration head unchanged (no schema changes here).
2. Tests pass.
3. Manual smoke: create a tenant from platform-web with BYO storage selected — verify the tenant row in IMS has the BYO fields populated AND a TenantLicenseCache row exists with the correct plan_codename.

## Files
| File | Status |
|---|---|
| `services/platform/app/routers/tenants.py` | Extend TenantCreate, add Subscription creation in create_tenant |
| `services/platform/app/services/tenant_provision.py` | Forward storage fields + initial_license |
| `services/api/app/routers/platform_provision.py` | Accept initial_license, seed TenantLicenseCache via _upsert_cache |
| `services/api/app/services/license_service.py` | Possibly extract _upsert_cache to public name if needed (or just import it as-is from inside `provision_tenant`) |

## Out of scope
- Plan/subscription editing UI (Item 3b)
- Tenant override seeding (Item 3b)
- Migration of hardcoded PLAN_FEATURES from `plans.py` (Item 3b)
