# Storage Quota Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce per-tenant storage quotas on the platform-managed R2 bucket — hard block at 100%, warn at 80%, track usage via a client-declared counter corrected by a daily reconciliation job.

**Architecture:** Two new DB columns (`tenants.storage_bytes_used`, `product_images.file_size_bytes`) drive the counter. The presign endpoint reads the tenant's license cache limit and checks quota before issuing a URL. Atomic SQL `UPDATE ... SET col = col + X` increments/decrements the counter at image save/delete. A configurable RQ task reconciles drift daily via R2 `ListObjectsV2`. BYO tenants are fully skipped. The billing usage endpoint is wired to the real counter, and the already-existing billing page `UsageMeter` for storage starts showing live data automatically.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, boto3 (already installed), Next.js 15, TypeScript

---

## Codebase context

### Key files
- `services/api/app/routers/admin_media.py` — presign endpoint to modify
- `services/api/app/routers/admin_catalog.py` — image add/delete to modify
- `services/api/app/routers/admin_billing.py` — `get_billing_usage`, wire `storage_used_mb`
- `services/api/app/services/storage_service.py` — presign logic, add `sum_r2_prefix` helper
- `services/api/app/worker/tasks.py` — append reconciliation task
- `services/api/app/models/tables.py` — add columns to `Tenant` and `ProductImage`
- `services/api/app/config.py` — add `storage_reconcile_interval_hours`
- `apps/admin-web/src/app/(main)/products/page.tsx` — `ImageUploadSection` update
- `apps/admin-web/src/app/(main)/billing/page.tsx` — 80% warning banner
- `apps/admin-web/src/app/(main)/overview/page.tsx` — 80% warning banner

### Latest migration head
`20260524000001` — chain from this.

### Atomic counter pattern (SQLAlchemy)
```python
from sqlalchemy import update as sa_update
db.execute(
    sa_update(Tenant)
    .where(Tenant.id == tenant_id)
    .values(storage_bytes_used=Tenant.storage_bytes_used + delta)
)
db.commit()
```
Never use `tenant.storage_bytes_used += X` — that's a read-modify-write and causes race conditions under concurrent uploads.

### Where the limit lives
`TenantLicenseCache.storage_limit_mb` — already in DB, already synced from platform billing service. No changes to the limit source.

### BYO exemption
`tenant.storage_mode == "byo"` → skip all quota logic entirely.

---

## File map

| File | Change |
|------|--------|
| `services/api/app/models/tables.py` | Add `storage_bytes_used` to `Tenant`, `file_size_bytes` to `ProductImage` |
| `services/api/app/config.py` | Add `storage_reconcile_interval_hours: int = 24` |
| `services/api/alembic/versions/20260525000001_storage_quota_fields.py` | New migration |
| `services/api/app/services/storage_service.py` | Add `sum_r2_prefix()` helper |
| `services/api/app/routers/admin_media.py` | Add `file_size_bytes` to request, quota check, `storage_warning` in response |
| `services/api/app/routers/admin_catalog.py` | `ProductImageIn` gains `file_size_bytes`; add/delete increment/decrement counter |
| `services/api/app/routers/admin_billing.py` | Wire `storage_used_mb` from real counter |
| `services/api/app/worker/tasks.py` | Append `reconcile_storage_usage()` |
| `apps/admin-web/src/app/(main)/products/page.tsx` | Send `file_size_bytes`; handle 402 + `storage_warning` |
| `apps/admin-web/src/app/(main)/billing/page.tsx` | 80% storage warning banner |

---

## Task 1: DB migration + model + config changes

**Files:**
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/config.py`
- Create: `services/api/alembic/versions/20260525000001_storage_quota_fields.py`

- [ ] **Step 1: Add `storage_bytes_used` to `Tenant` model**

In `services/api/app/models/tables.py`, find `Tenant`. Add after `financial_year_start_month` (before the storage_mode columns we added earlier):

```python
    storage_bytes_used: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
```

`BigInteger` is already imported (search for it — if not present, add it to the SQLAlchemy import line alongside `Integer`).

- [ ] **Step 2: Add `file_size_bytes` to `ProductImage` model**

In `tables.py`, find `ProductImage`. Add after `sort_order`:

```python
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
```

- [ ] **Step 3: Add config var**

In `services/api/app/config.py`, add after `license_sync_interval_seconds`:

```python
    storage_reconcile_interval_hours: int = 24
```

- [ ] **Step 4: Create migration**

Create `services/api/alembic/versions/20260525000001_storage_quota_fields.py`:

```python
"""add storage quota tracking fields

Revision ID: 20260525000001
Revises: 20260524000001
Create Date: 2026-05-25 00:00:01
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "20260525000001"
down_revision = "20260524000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants",
        sa.Column("storage_bytes_used", sa.BigInteger, nullable=False, server_default="0"))
    op.add_column("product_images",
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "storage_bytes_used")
    op.drop_column("product_images", "file_size_bytes")
```

- [ ] **Step 5: Deploy and run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/models/tables.py $CONTAINER:/app/app/models/tables.py
docker cp services/api/app/config.py $CONTAINER:/app/app/config.py
docker cp services/api/alembic/versions/20260525000001_storage_quota_fields.py \
    $CONTAINER:/app/alembic/versions/20260525000001_storage_quota_fields.py
docker compose exec api alembic upgrade head
```

Expected: `Running upgrade 20260524000001 -> 20260525000001, add storage quota tracking fields`

- [ ] **Step 6: Commit**

```bash
git add services/api/app/models/tables.py \
        services/api/app/config.py \
        services/api/alembic/versions/20260525000001_storage_quota_fields.py
git commit -m "feat(storage): add storage_bytes_used + file_size_bytes columns, reconcile interval config"
```

---

## Task 2: `sum_r2_prefix` helper in storage_service.py

**Files:**
- Modify: `services/api/app/services/storage_service.py`

This helper is used by both the reconciliation task and tests. It must paginate because R2 `list_objects_v2` returns at most 1000 keys per call.

- [ ] **Step 1: Add `sum_r2_prefix` to storage_service.py**

Append to `services/api/app/services/storage_service.py`:

```python
def sum_r2_prefix(prefix: str) -> int:
    """Return the total bytes of all objects under a key prefix in the platform R2 bucket.

    Paginates automatically. Returns 0 if the platform bucket is not configured
    or the prefix has no objects.
    """
    if not settings.r2_endpoint_url or not settings.r2_bucket_name:
        logger.debug("Platform R2 not configured — sum_r2_prefix returning 0")
        return 0

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name=settings.r2_region or "auto",
        config=Config(signature_version="s3v4"),
    )

    total_bytes = 0
    continuation_token: str | None = None

    while True:
        kwargs: dict = {"Bucket": settings.r2_bucket_name, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            total_bytes += obj.get("Size", 0)

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
        else:
            break

    return total_bytes
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('services/api/app/services/storage_service.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add services/api/app/services/storage_service.py
git commit -m "feat(storage): add sum_r2_prefix helper for reconciliation"
```

---

## Task 3: Quota enforcement in presign endpoint + tests

**Files:**
- Modify: `services/api/app/routers/admin_media.py`
- Create: `services/api/tests/routers/test_storage_quota.py`

- [ ] **Step 1: Write failing tests**

Create `services/api/tests/routers/test_storage_quota.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from math import ceil
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant, TenantLicenseCache


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin
    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def tenant_with_license(db, tenant: Tenant) -> Tenant:
    """Platform-mode tenant with a 10 MB storage limit."""
    tenant.storage_mode = "platform"
    tenant.storage_bytes_used = 0
    cache = TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="trial",
        storage_limit_mb=10,   # 10 MB limit for easy math
        max_shops=1,
        max_employees=5,
        last_synced_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    db.add(cache)
    db.commit()
    return tenant


def _presign(client, folder="products/abc", filename="img.jpg",
             content_type="image/jpeg", file_size_bytes=1024):
    with patch("app.routers.admin_media.presign_upload") as mock:
        mock.return_value = {
            "upload_url": "https://r2.example.com/presigned",
            "public_url": "https://media.example.com/key.jpg",
            "key": "tenant/products/abc/abc.jpg",
            "expires_in": 900,
            "content_type": content_type,
        }
        return client.post("/v1/admin/media/presign-upload", json={
            "folder": folder, "filename": filename,
            "content_type": content_type, "file_size_bytes": file_size_bytes,
        })


def test_presign_succeeds_under_quota(db, tenant_with_license: Tenant, auth) -> None:
    resp = _presign(TestClient(app), file_size_bytes=100)
    assert resp.status_code == 200, resp.text
    assert resp.json()["storage_warning"] is None


def test_presign_returns_warning_at_80_percent(db, tenant_with_license: Tenant, auth) -> None:
    # Set used to 85% of 10 MB
    limit_bytes = 10 * 1024 * 1024
    tenant_with_license.storage_bytes_used = int(limit_bytes * 0.85)
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    assert resp.status_code == 200, resp.text
    warning = resp.json()["storage_warning"]
    assert warning is not None
    assert warning["used_pct"] >= 80
    assert warning["limit_mb"] == 10


def test_presign_blocked_at_100_percent(db, tenant_with_license: Tenant, auth) -> None:
    limit_bytes = 10 * 1024 * 1024
    tenant_with_license.storage_bytes_used = limit_bytes  # exactly full
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    assert resp.status_code == 402
    body = resp.json()
    assert "limit reached" in body["detail"].lower()
    assert "used_bytes" in body
    assert "limit_bytes" in body


def test_presign_byo_tenant_skips_quota(db, tenant: Tenant, auth) -> None:
    """BYO tenants never get blocked regardless of any counter."""
    tenant.storage_mode = "byo"
    tenant.storage_bytes_used = 999_999_999_999  # huge number
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    # Should not 402 — BYO quota check is skipped entirely
    assert resp.status_code != 402


def test_presign_no_license_cache_skips_quota(db, tenant: Tenant, auth) -> None:
    """If no TenantLicenseCache exists, quota check is skipped (no limit known)."""
    tenant.storage_mode = "platform"
    tenant.storage_bytes_used = 0
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    assert resp.status_code != 402
```

- [ ] **Step 2: Update admin_media.py**

Replace the entire file with:

```python
"""Admin endpoint for getting presigned upload URLs for direct browser-to-R2 uploads."""
from __future__ import annotations

import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Tenant, TenantLicenseCache
from app.services.storage_service import presign_upload

router = APIRouter(
    prefix="/v1/admin/media",
    tags=["Media Upload"],
    dependencies=[require_permission("catalog:write")],
)


class PresignIn(BaseModel):
    folder: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=64)
    file_size_bytes: int = Field(ge=1, description="File size in bytes (from File.size in the browser)")


class StorageWarning(BaseModel):
    used_pct: int
    used_mb: int
    limit_mb: int


class PresignOut(BaseModel):
    upload_url: str
    public_url: str
    key: str
    expires_in: int
    content_type: str
    storage_warning: StorageWarning | None = None


class StorageQuotaError(BaseModel):
    detail: str
    used_bytes: int
    limit_bytes: int


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _check_quota(
    tenant: Tenant,
    file_size_bytes: int,
    db: Session,
) -> StorageWarning | None:
    """Check storage quota. Returns a StorageWarning if >= 80%, raises HTTP 402 if over limit.

    Returns None if under 80% or if quota check is skipped (BYO, no cache).
    """
    # BYO tenants: their bucket, their quota management
    if tenant.storage_mode == "byo":
        return None

    cache: TenantLicenseCache | None = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant.id)
    ).scalar_one_or_none()

    # No license cache = no known limit = skip quota check
    if cache is None:
        return None

    limit_bytes = cache.storage_limit_mb * 1_048_576
    used_bytes = tenant.storage_bytes_used
    projected = used_bytes + file_size_bytes

    if projected > limit_bytes:
        used_mb = math.ceil(used_bytes / 1_048_576)
        limit_mb = cache.storage_limit_mb
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Storage limit reached. You have used {used_mb} MB "
                f"of your {limit_mb} MB limit."
            ),
            headers={
                "X-Storage-Used-Bytes": str(used_bytes),
                "X-Storage-Limit-Bytes": str(limit_bytes),
            },
        )

    # Return warning detail if >= 80% after this upload
    if limit_bytes > 0 and projected / limit_bytes >= 0.80:
        used_pct = math.ceil(projected / limit_bytes * 100)
        return StorageWarning(
            used_pct=used_pct,
            used_mb=math.ceil(projected / 1_048_576),
            limit_mb=cache.storage_limit_mb,
        )

    return None


@router.post("/presign-upload", response_model=PresignOut)
def get_presign_upload_url(
    body: PresignIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PresignOut:
    """Get a presigned PUT URL for uploading an image directly to R2.

    Flow:
      1. Call this endpoint → get { upload_url, public_url, storage_warning }
      2. PUT file bytes to upload_url from the browser (no auth needed for the PUT)
      3. POST public_url to /v1/admin/catalog/products/{id}/images with file_size_bytes
    """
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    warning = _check_quota(tenant, body.file_size_bytes, db)

    try:
        result = presign_upload(
            tenant=tenant,
            folder=body.folder.strip("/"),
            filename=body.filename,
            content_type=body.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PresignOut(**result, storage_warning=warning)
```

Note: `_check_quota` raises an `HTTPException` with status 402, but FastAPI's default 422 response model for 402 won't match `StorageQuotaError`. The `detail` string and the headers carry the data the client needs. This is intentional — 402 is not in the router's declared response models, so FastAPI won't try to validate it.

- [ ] **Step 3: Deploy and run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_media.py $CONTAINER:/app/app/routers/admin_media.py
docker cp services/api/app/models/tables.py $CONTAINER:/app/app/models/tables.py
docker compose restart api && sleep 6
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/routers/test_storage_quota.py -v 2>&1 | tail -15
docker compose exec api rm -rf /app/tests
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add services/api/app/routers/admin_media.py \
        services/api/tests/routers/test_storage_quota.py
git commit -m "feat(storage): add quota enforcement (80% warn + 100% hard block) to presign endpoint"
```

---

## Task 4: Counter increment/decrement in catalog image endpoints

**Files:**
- Modify: `services/api/app/routers/admin_catalog.py`

- [ ] **Step 1: Update `ProductImageIn` and `add_product_image`**

Read `services/api/app/routers/admin_catalog.py`.

Update `ProductImageIn`:
```python
class ProductImageIn(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    alt_text: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    file_size_bytes: int | None = Field(default=None, ge=1)
```

Update `add_product_image` to store `file_size_bytes` and increment the counter atomically:

```python
@router.post(
    "/products/{product_id}/images",
    response_model=ProductImageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:write")],
)
def add_product_image(
    product_id: UUID,
    body: ProductImageIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductImage:
    from sqlalchemy import update as sa_update
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)

    img = ProductImage(
        tenant_id=tenant_id,
        product_id=product_id,
        url=body.url,
        alt_text=body.alt_text,
        sort_order=body.sort_order,
        file_size_bytes=body.file_size_bytes,
    )
    db.add(img)
    db.flush()

    # Atomically increment tenant storage counter for platform-mode tenants
    if body.file_size_bytes is not None:
        from app.models import Tenant
        tenant = db.get(Tenant, tenant_id)
        if tenant and tenant.storage_mode == "platform":
            db.execute(
                sa_update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(storage_bytes_used=Tenant.storage_bytes_used + body.file_size_bytes)
            )

    db.commit()
    db.refresh(img)
    return img
```

- [ ] **Step 2: Update `delete_product_image` to decrement counter**

Replace `delete_product_image` with:

```python
@router.delete(
    "/products/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:write")],
)
def delete_product_image(
    product_id: UUID,
    image_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    from sqlalchemy import update as sa_update
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)

    img = db.get(ProductImage, image_id)
    if img is None or img.product_id != product_id or img.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    file_size = img.file_size_bytes
    db.delete(img)
    db.flush()

    # Atomically decrement tenant storage counter (only if size is known)
    if file_size is not None:
        from app.models import Tenant
        tenant = db.get(Tenant, tenant_id)
        if tenant and tenant.storage_mode == "platform":
            db.execute(
                sa_update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(storage_bytes_used=Tenant.storage_bytes_used - file_size)
            )

    db.commit()
```

- [ ] **Step 3: Verify syntax and deploy**

```bash
python3 -c "import ast; ast.parse(open('services/api/app/routers/admin_catalog.py').read()); print('OK')"
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_catalog.py $CONTAINER:/app/app/routers/admin_catalog.py
docker compose restart api && sleep 6
docker compose logs api --tail=4
```

- [ ] **Step 4: Commit**

```bash
git add services/api/app/routers/admin_catalog.py
git commit -m "feat(storage): track file_size_bytes on images, increment/decrement storage counter atomically"
```

---

## Task 5: Wire storage_used_mb in billing usage endpoint

**Files:**
- Modify: `services/api/app/routers/admin_billing.py`

- [ ] **Step 1: Update `get_billing_usage`**

Find `get_billing_usage` in `admin_billing.py`. The return statement currently has `storage_used_mb=0`. Replace with:

```python
    # Read the real storage counter from the tenant row
    tenant = db.get(Tenant, tenant_id)
    storage_used_mb = math.ceil((tenant.storage_bytes_used if tenant else 0) / 1_048_576)

    return UsageOut(
        shops_used=shops_used,
        shops_limit=cache.max_shops if cache else 999,
        employees_used=employees_used,
        employees_limit=cache.max_employees if cache else 999,
        storage_used_mb=storage_used_mb,
        storage_limit_mb=cache.storage_limit_mb if cache else 999,
    )
```

Add `import math` at the top of the file if not already present (check with `grep "^import math" admin_billing.py`).

Also add `Tenant` to the models import line in that file:
```python
from app.models import Shop, Tenant, TenantLicenseCache, User
```
(It may already be there — check before adding.)

- [ ] **Step 2: Deploy**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/routers/admin_billing.py $CONTAINER:/app/app/routers/admin_billing.py
docker compose restart api && sleep 6
```

- [ ] **Step 3: Commit**

```bash
git add services/api/app/routers/admin_billing.py
git commit -m "feat(storage): wire real storage_bytes_used into billing usage endpoint"
```

---

## Task 6: Reconciliation RQ task

**Files:**
- Modify: `services/api/app/worker/tasks.py`

- [ ] **Step 1: Append `reconcile_storage_usage` to tasks.py**

```python
def reconcile_storage_usage() -> str:
    """RQ task: correct storage_bytes_used for all platform-mode tenants by
    listing their actual R2 prefix and setting the ground-truth byte count.

    Interval controlled by settings.storage_reconcile_interval_hours (default: 24).
    Safe to run at any time — idempotent, never deletes anything.
    """
    import logging
    from sqlalchemy import select, update as sa_update

    from app.db.session import SessionLocal
    from app.db.rls import set_rls_context
    from app.models import Tenant
    from app.services.storage_service import sum_r2_prefix

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    reconciled = 0
    errors = 0

    try:
        set_rls_context(db, is_admin=True, tenant_id=None)
        tenants = db.execute(
            select(Tenant).where(Tenant.storage_mode == "platform")
        ).scalars().all()

        for tenant in tenants:
            try:
                prefix = f"{tenant.id}/"
                actual_bytes = sum_r2_prefix(prefix)
                db.execute(
                    sa_update(Tenant)
                    .where(Tenant.id == tenant.id)
                    .values(storage_bytes_used=actual_bytes)
                )
                reconciled += 1
            except Exception:
                errors += 1
                logger.warning(
                    "Storage reconciliation failed for tenant %s", tenant.id, exc_info=True
                )

        db.commit()
        logger.info(
            "Storage reconciliation complete: %d tenants, %d errors", reconciled, errors
        )
        return f"reconciled {reconciled} tenants, {errors} errors"
    except Exception:
        logger.exception("reconcile_storage_usage failed")
        return "error"
    finally:
        db.close()
```

- [ ] **Step 2: Verify and deploy**

```bash
python3 -c "import ast; ast.parse(open('services/api/app/worker/tasks.py').read()); print('OK')"
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/worker/tasks.py $CONTAINER:/app/app/worker/tasks.py
```

- [ ] **Step 3: Commit**

```bash
git add services/api/app/worker/tasks.py
git commit -m "feat(storage): add reconcile_storage_usage RQ task (configurable interval, default 24h)"
```

---

## Task 7: Admin-web — upload UI + billing warning banner

**Files:**
- Modify: `apps/admin-web/src/app/(main)/products/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/billing/page.tsx`

- [ ] **Step 1: Update `ImageUploadSection` in products/page.tsx**

Read `apps/admin-web/src/app/(main)/products/page.tsx`. Find `ImageUploadSection`. Make three changes:

**a) Add `file_size_bytes` to the presign request body:**

Find the `body: JSON.stringify({...})` call in `handleFileChange`. Change to:
```tsx
body: JSON.stringify({
  folder: `products/${productId}`,
  filename: file.name,
  content_type: file.type,
  file_size_bytes: file.size,
}),
```

**b) Update the presign response type and handle `storage_warning`:**

Change the response type assertion after presign:
```tsx
const { upload_url, public_url, storage_warning } = (await presignResp.json()) as {
  upload_url: string;
  public_url: string;
  key: string;
  storage_warning: { used_pct: number; used_mb: number; limit_mb: number } | null;
};
```

After the successful `void loadImages()` call, add:
```tsx
if (storage_warning) {
  setUploadErr(
    `Storage ${storage_warning.used_pct}% used (${storage_warning.used_mb} MB of ${storage_warning.limit_mb} MB). Consider upgrading your plan.`
  );
}
```

(We reuse `uploadErr` for the warning text. The yellow styling will match since it's rendered the same way — the user can distinguish it by content. Optionally add a separate `uploadWarn` state, but `uploadErr` is simpler.)

**c) Add `file_size_bytes` to the image save call:**

Find the `body: JSON.stringify({ url: public_url, sort_order: images.length })` call. Change to:
```tsx
body: JSON.stringify({ url: public_url, sort_order: images.length, file_size_bytes: file.size }),
```

**d) Handle 402 specifically:**

In the `catch` block after the presign 402 check, add a special message. The presign response check already handles `!presignResp.ok` with `d.detail`. Since 402 detail includes "Storage limit reached", this works automatically. But for clarity, also update the error styling to differentiate — change the `uploadErr` paragraph class from `text-xs text-error` to show yellow for warnings vs red for blocks. This is optional UI polish; the functional behavior (blocking the upload) is already correct because the `throw` prevents the PUT.

- [ ] **Step 2: Add 80% warning banner to billing/page.tsx**

Read `apps/admin-web/src/app/(main)/billing/page.tsx`.

Find where `usage` state is used and `UsageMeter` components are rendered. Add a warning banner above the usage meters section, conditional on storage usage >= 80%:

```tsx
{usage && usage.storage_limit_mb > 0 &&
  usage.storage_used_mb / usage.storage_limit_mb >= 0.8 && (
  <div className="rounded-xl border border-warning/20 bg-warning/10 px-5 py-4 flex items-start gap-3">
    <span className="material-symbols-outlined text-xl text-warning mt-0.5">warning</span>
    <div>
      <p className="text-sm font-semibold text-on-surface">
        Storage {Math.ceil(usage.storage_used_mb / usage.storage_limit_mb * 100)}% used
      </p>
      <p className="text-xs text-on-surface-variant mt-0.5">
        You&apos;ve used {usage.storage_used_mb} MB of your {usage.storage_limit_mb} MB storage limit.
        Upgrade your plan to continue uploading images without interruption.
      </p>
    </div>
    <a
      href="#plans"
      className="ml-auto shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-on-primary hover:opacity-90"
    >
      Upgrade →
    </a>
  </div>
)}
```

If `warning` is not a Tailwind colour token in this project, use `amber` instead: `border-amber-400/20 bg-amber-50 text-amber-800`.

Check the Tailwind config first:
```bash
grep -r "warning\|amber" apps/admin-web/tailwind.config.ts | head -5
```

Use whichever colour is available; `amber-500` is a safe fallback.

- [ ] **Step 3: Commit**

```bash
git add "apps/admin-web/src/app/(main)/products/page.tsx" \
        "apps/admin-web/src/app/(main)/billing/page.tsx"
git commit -m "feat(admin-web): send file_size_bytes on upload, handle 402 block and 80% warning"
```

---

## Task 8: Full test suite + rebuild

- [ ] **Step 1: Run full API test suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/ -q 2>&1 | tail -6
docker compose exec api rm -rf /app/tests
```

Expected: 519+ passing, 1 pre-existing failure.

- [ ] **Step 2: Full rebuild**

```bash
docker compose down && docker compose up --build -d 2>&1 | grep -E "✓ Compiled|error|failed" | tail -5
sleep 15 && docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

Expected: admin-web ✓ Compiled, all containers Up.

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Self-review

**Spec coverage:**

| Requirement | Task |
|------------|------|
| `tenants.storage_bytes_used` column | Task 1 |
| `product_images.file_size_bytes` column | Task 1 |
| `STORAGE_RECONCILE_INTERVAL_HOURS` config var | Task 1 |
| Migration `20260525000001` | Task 1 |
| `sum_r2_prefix` helper | Task 2 |
| `file_size_bytes` required in presign request | Task 3 |
| Quota check: 402 at 100% | Task 3 |
| Quota check: `storage_warning` at 80% | Task 3 |
| BYO tenants skip quota | Task 3 |
| No license cache = skip quota | Task 3 |
| Counter increment on image save | Task 4 |
| Counter decrement on image delete (NULL-safe) | Task 4 |
| Wire `storage_used_mb` in billing usage endpoint | Task 5 |
| `reconcile_storage_usage` RQ task | Task 6 |
| `file_size_bytes` sent in frontend upload | Task 7 |
| 402 hard block message in upload UI | Task 7 |
| 80% warning banner on billing page | Task 7 |
| 80% inline warning after upload | Task 7 |

**No placeholders found.**

**Type consistency:**
- `StorageWarning` defined in `admin_media.py` (Task 3), referenced as the same shape in `products/page.tsx` (Task 7) ✅
- `file_size_bytes: int | None` on `ProductImageIn` (Task 4) matches the optional field sent by frontend (Task 7) ✅
- Atomic update uses `Tenant.storage_bytes_used + delta` (SQLAlchemy column expression) consistently in Tasks 4 and 6 ✅
