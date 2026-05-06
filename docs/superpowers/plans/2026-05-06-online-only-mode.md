# Online-Only Mode + Conversion Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `business_type` field to tenants (`online | retail | hybrid`) and a `kind` field to shops (`virtual | physical`) so the system knows which UI surfaces to expose to each merchant — hiding POS/shop management from online-only merchants and hiding e-commerce details from retail-only merchants — plus a conversion API so online merchants can add a physical store without losing their online setup.

**Architecture:** Two new columns (`tenants.business_type`, `shops.kind`) with a migration that sets existing tenants to `retail` and existing shops to `physical`. A new `admin_business_type.py` router exposes three endpoints: one to read the tenant's current type + computed UI-feature-flag map, one to set the type (used during onboarding), and one to execute the online→hybrid conversion (creates a physical shop + POS channel atomically). The `retail→hybrid` conversion is just adding a channel via existing channel endpoints — no new endpoint needed. Admin web frontend gating consumes the feature-flag map endpoint.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL, pytest

**Out of scope (deferred):**
- Admin web (Next.js) frontend changes — the backend feature-flag endpoint is what the frontend reads; the frontend changes are a separate task for the Next.js codebase.
- Auto-creating a virtual shop at tenant-signup time — that's an onboarding flow change that touches platform-service provisioning; for now the `POST /v1/admin/tenant-settings/business-type` endpoint handles it on first-set.
- `hybrid→online` downgrade (requires deleting physical shops/channels with data — unlikely UX).

---

### Task 1: Migration + model columns

**Files:**
- Create: `services/api/alembic/versions/20260514000001_business_type.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write the failing contract test**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_business_type_out_schema() -> None:
    from app.routers.admin_business_type import BusinessTypeOut

    b = BusinessTypeOut(
        business_type="online",
        show_shops_management=False,
        show_pos_features=False,
        show_ecommerce_features=True,
        can_add_physical_store=True,
        can_add_online_channel=False,
    )
    d = b.model_dump(mode="json")
    assert d["business_type"] == "online"
    assert d["show_shops_management"] is False
    assert d["show_ecommerce_features"] is True
    assert d["can_add_physical_store"] is True
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_business_type_out_schema -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_business_type'`. Stays red until Task 2.

- [ ] **Step 3: Add columns to existing models**

In `services/api/app/models/tables.py`:

1. In the `Tenant` class, add after `billing_country` (the last billing field):
```python
    business_type: Mapped[str] = mapped_column(
        String(32), default="retail", server_default="retail", nullable=False
    )
    # business_type: 'online' | 'retail' | 'hybrid'
    # online  = sells only on e-commerce channels, no physical POS
    # retail  = physical stores only, no e-commerce
    # hybrid  = both channels active
```

2. In the `Shop` class, add after the `timezone` column:
```python
    kind: Mapped[str] = mapped_column(
        String(32), default="physical", server_default="physical", nullable=False
    )
    # kind: 'physical' | 'virtual'
    # virtual = auto-created for online-only tenants; has no physical address
```

- [ ] **Step 4: Write the migration**

Create `services/api/alembic/versions/20260514000001_business_type.py`:

```python
"""Add business_type to tenants and kind to shops

Revision ID: 20260514000001
Revises: 20260513000001
Create Date: 2026-05-14 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260514000001"
down_revision = "20260513000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # business_type on tenants — existing tenants are retail (they have POS shops)
    op.add_column("tenants", sa.Column(
        "business_type", sa.String(32), nullable=False, server_default="retail"
    ))

    # kind on shops — all existing shops are physical locations
    op.add_column("shops", sa.Column(
        "kind", sa.String(32), nullable=False, server_default="physical"
    ))
    op.create_index("ix_shops_kind", "shops", ["tenant_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_shops_kind", table_name="shops")
    op.drop_column("shops", "kind")
    op.drop_column("tenants", "business_type")
```

- [ ] **Step 5: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260514000001_business_type.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260513000001 -> 20260514000001`

- [ ] **Step 6: Verify**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d tenants" | grep business_type
docker compose exec postgres psql -U ims -d ims -c "\d shops" | grep kind
docker compose exec postgres psql -U ims -d ims -c "SELECT business_type, COUNT(*) FROM tenants GROUP BY business_type"
docker compose exec postgres psql -U ims -d ims -c "SELECT kind, COUNT(*) FROM shops GROUP BY kind"
```
Expected: column present on both tables, all tenants=retail, all shops=physical.

- [ ] **Step 7: Commit**

```bash
git add services/api/alembic/versions/20260514000001_business_type.py \
        services/api/app/models/tables.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(business-type): add business_type to tenants and kind to shops"
```

---

### Task 2: Business type settings API

**Files:**
- Create: `services/api/app/routers/admin_business_type.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_business_type.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_business_type.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Shop, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"business_type:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_get_business_type_defaults_to_retail(db, tenant: Tenant, auth_headers) -> None:
    """New tenants start as 'retail' (migration default)."""
    client = TestClient(app)
    resp = client.get("/v1/admin/tenant-settings/business-type", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "retail"
    # retail merchants see shop management and POS but not ecommerce
    assert body["show_shops_management"] is True
    assert body["show_pos_features"] is True
    assert body["show_ecommerce_features"] is False
    assert body["can_add_physical_store"] is False
    assert body["can_add_online_channel"] is True


def test_set_business_type_to_online(db, tenant: Tenant, auth_headers) -> None:
    """Setting business_type=online creates a virtual shop and flips the type."""
    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type", json={
        "business_type": "online",
    }, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "online"
    assert body["show_shops_management"] is False
    assert body["show_pos_features"] is False
    assert body["show_ecommerce_features"] is True
    assert body["can_add_physical_store"] is True
    assert body["can_add_online_channel"] is False

    # Verify a virtual shop was auto-created
    from sqlalchemy import select
    from app.db.session import SessionLocal
    db2 = SessionLocal()
    try:
        virtual_shops = db2.execute(
            select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
        ).scalars().all()
        assert len(virtual_shops) == 1
        assert virtual_shops[0].name == "Online Store"
    finally:
        db2.close()


def test_set_business_type_to_hybrid(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type", json={
        "business_type": "hybrid",
    }, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "hybrid"
    assert body["show_shops_management"] is True
    assert body["show_ecommerce_features"] is True


def test_get_feature_flags_for_online(db, tenant: Tenant, auth_headers) -> None:
    """After setting to online, GET returns the correct flag map."""
    client = TestClient(app)
    client.post("/v1/admin/tenant-settings/business-type", json={"business_type": "online"})

    resp = client.get("/v1/admin/tenant-settings/business-type", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "online"
    assert body["show_shops_management"] is False
    assert body["can_add_physical_store"] is True


def test_invalid_business_type_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type", json={
        "business_type": "moon",
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_contract_schema(db, tenant: Tenant) -> None:
    from app.routers.admin_business_type import BusinessTypeOut
    b = BusinessTypeOut(
        business_type="online",
        show_shops_management=False,
        show_pos_features=False,
        show_ecommerce_features=True,
        can_add_physical_store=True,
        can_add_online_channel=False,
    )
    assert b.business_type == "online"
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_business_type.py $CONTAINER:/app/tests/routers/test_admin_business_type.py
docker compose exec api python -m pytest tests/routers/test_admin_business_type.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_business_type.py
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_business_type.py`:

```python
"""Tenant business-type settings: read the current type + UI feature flags, set on onboarding.

Three endpoints:
  GET  /v1/admin/tenant-settings/business-type
       → returns the type and a flat feature-flag map the admin web uses for
         navigation gating (which surfaces to show/hide for this merchant).

  POST /v1/admin/tenant-settings/business-type
       → sets or changes the type. When setting to 'online' for the first time,
         auto-creates a virtual shop so the rest of the system has a shop to
         attach inventory pools and channels to.

  POST /v1/admin/setup/enable-physical-store
       → converts online → hybrid by creating a real physical shop + its POS
         channel. The merchant fills in the shop name (required) and optional
         timezone / address at this step.

Auth: `business_type:manage` permission, granted to system 'owner' role by migration.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Shop, Tenant

router = APIRouter(tags=["Tenant Business Type"])

_VALID_TYPES = {"online", "retail", "hybrid"}

_FLAG_MAP: dict[str, dict[str, bool]] = {
    "online": {
        "show_shops_management": False,
        "show_pos_features": False,
        "show_ecommerce_features": True,
        "can_add_physical_store": True,
        "can_add_online_channel": False,
    },
    "retail": {
        "show_shops_management": True,
        "show_pos_features": True,
        "show_ecommerce_features": False,
        "can_add_physical_store": False,
        "can_add_online_channel": True,
    },
    "hybrid": {
        "show_shops_management": True,
        "show_pos_features": True,
        "show_ecommerce_features": True,
        "can_add_physical_store": True,
        "can_add_online_channel": True,
    },
}


class BusinessTypeOut(BaseModel):
    business_type: str
    show_shops_management: bool
    show_pos_features: bool
    show_ecommerce_features: bool
    can_add_physical_store: bool
    can_add_online_channel: bool


class BusinessTypeIn(BaseModel):
    business_type: str = Field(pattern="^(online|retail|hybrid)$")


class EnablePhysicalStoreIn(BaseModel):
    shop_name: str = Field(min_length=1, max_length=255)
    timezone: str | None = None


def _require_tenant(ctx: AdminAuthDep, db: Session) -> Tenant:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return tenant


def _build_out(bt: str) -> BusinessTypeOut:
    flags = _FLAG_MAP.get(bt, _FLAG_MAP["retail"])
    return BusinessTypeOut(business_type=bt, **flags)


def _ensure_virtual_shop(db: Session, tenant: Tenant) -> None:
    """Create an 'Online Store' virtual shop if the tenant doesn't already have one."""
    existing = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalar_one_or_none()
    if existing is None:
        virtual_shop = Shop(
            tenant_id=tenant.id,
            name="Online Store",
            kind="virtual",
        )
        db.add(virtual_shop)
        db.flush()


# ── Routes ──

@router.get(
    "/v1/admin/tenant-settings/business-type",
    response_model=BusinessTypeOut,
    dependencies=[require_permission("business_type:manage")],
)
def get_business_type(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BusinessTypeOut:
    tenant = _require_tenant(ctx, db)
    return _build_out(tenant.business_type)


@router.post(
    "/v1/admin/tenant-settings/business-type",
    response_model=BusinessTypeOut,
    dependencies=[require_permission("business_type:manage")],
)
def set_business_type(
    body: BusinessTypeIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BusinessTypeOut:
    """Set or change the tenant's business type.

    When setting to 'online' for the first time, auto-creates a virtual shop.
    """
    tenant = _require_tenant(ctx, db)
    new_type = body.business_type

    if new_type in {"online", "hybrid"}:
        _ensure_virtual_shop(db, tenant)

    tenant.business_type = new_type
    db.commit()
    return _build_out(new_type)


@router.post(
    "/v1/admin/setup/enable-physical-store",
    response_model=BusinessTypeOut,
    dependencies=[require_permission("business_type:manage")],
)
def enable_physical_store(
    body: EnablePhysicalStoreIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BusinessTypeOut:
    """Convert an online-only tenant to hybrid by adding a physical shop + POS channel.

    Creates a Shop(kind=physical) and a POS channel for it, then flips the
    tenant's business_type to 'hybrid'. Safe to call multiple times — adds
    a new shop each call (merchants can have multiple physical locations).
    """
    tenant = _require_tenant(ctx, db)

    # Create the physical shop
    shop = Shop(
        tenant_id=tenant.id,
        name=body.shop_name,
        kind="physical",
        timezone=body.timezone,
    )
    db.add(shop)
    db.flush()

    # Auto-create POS channel + single-shop pool for this shop
    from app.services.channel_service import get_or_create_pos_channel
    get_or_create_pos_channel(db, shop)

    # Flip to hybrid
    tenant.business_type = "hybrid"
    db.commit()
    return _build_out("hybrid")
```

- [ ] **Step 4: Seed the new permission in a migration (add to Task 1's migration)**

Since the migration is already committed, add the permission seed as a separate small migration or just add it to the router test's auth_headers fixture (it doesn't need to come from DB for tests). For the permission to work in production it must be seeded. Add an inline migration:

```bash
docker compose exec api python -c "
from app.db.session import SessionLocal
db = SessionLocal()
from sqlalchemy import text
db.execute(text(\"\"\"
    INSERT INTO permissions (id, codename, display_name, category, description)
    VALUES (gen_random_uuid(), 'business_type:manage', 'Manage Business Type', 'settings',
            'Set tenant business type and enable physical/online mode')
    ON CONFLICT (codename) DO NOTHING;
    INSERT INTO role_permissions (id, role_id, permission_id)
    SELECT gen_random_uuid(), r.id, p.id
    FROM roles r, permissions p
    WHERE r.name = 'owner' AND r.is_system = true
      AND p.codename = 'business_type:manage'
    ON CONFLICT DO NOTHING;
\"\"\"))
db.commit()
db.close()
print('Permission seeded')
"
```

Wait — instead of a runtime script, add the permission to a second migration file. Create `services/api/alembic/versions/20260514000002_business_type_permission.py`:

```python
"""Seed business_type:manage permission

Revision ID: 20260514000002
Revises: 20260514000001
Create Date: 2026-05-14 00:00:02.000000
"""
from __future__ import annotations

from alembic import op

revision = "20260514000002"
down_revision = "20260514000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'business_type:manage', 'Manage Business Type', 'settings',
                'Set tenant business type and enable physical/online conversion')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'business_type:manage'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'business_type:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'business_type:manage'")
```

Run it:
```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260514000002_business_type_permission.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```

- [ ] **Step 5: Mount the router**

In `services/api/app/main.py`, add `admin_business_type` to the imports (alphabetically, between `admin_billing` and `admin_catalog`) and add `app.include_router(admin_business_type.router)`.

- [ ] **Step 6: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_business_type.py $CONTAINER:/app/app/routers/admin_business_type.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest \
  tests/routers/test_admin_business_type.py \
  tests/test_admin_console_contracts.py::test_business_type_out_schema \
  -v
docker compose exec api rm -rf /app/tests
```
Expected: 6 router tests + 1 contract test = 7 passed.

Note: `test_set_business_type_to_online` uses a separate `SessionLocal()` to verify the virtual shop because the route handler's `get_db_admin` session commits and the test's conftest session might not see it. Adapt if needed — the core assertions about returned flags still pass even if the shop assertion is tricky.

- [ ] **Step 7: Commit**

```bash
git add services/api/alembic/versions/20260514000002_business_type_permission.py \
        services/api/app/routers/admin_business_type.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_business_type.py
git commit -m "feat(business-type): add business-type settings API with feature-flag map"
```

---

### Task 3: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_business_type_e2e.py`

- [ ] **Step 1: Write integration test**

Create `services/api/tests/integration/test_business_type_e2e.py`:

```python
"""End-to-end smoke test for the online-only mode + conversion path.

Covers:
- Fresh tenant defaults to 'retail' with correct feature flags
- Setting to 'online' creates a virtual shop and flips flags
- enable-physical-store converts online→hybrid with a real shop + POS channel
- hybrid flag map shows all surfaces
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, Shop, Tenant


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"business_type:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_retail_default_flags(db, tenant: Tenant, auth) -> None:
    """Newly-created tenant (migrated to retail) gets retail feature flags."""
    client = TestClient(app)
    resp = client.get("/v1/admin/tenant-settings/business-type")
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "retail"
    assert body["show_pos_features"] is True
    assert body["show_ecommerce_features"] is False
    assert body["can_add_online_channel"] is True


def test_set_online_creates_virtual_shop(db, tenant: Tenant, auth) -> None:
    """Setting business_type=online creates a virtual 'Online Store' shop."""
    from sqlalchemy import select

    client = TestClient(app)
    resp = client.post("/v1/admin/tenant-settings/business-type",
                       json={"business_type": "online"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "online"
    assert body["show_shops_management"] is False
    assert body["can_add_physical_store"] is True

    # Verify virtual shop exists
    virtual_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalars().all()
    assert len(virtual_shops) == 1
    assert virtual_shops[0].name == "Online Store"


def test_enable_physical_store_creates_shop_and_pos_channel(db, tenant: Tenant, auth) -> None:
    """After going online, enabling a physical store creates Shop(physical) + POS channel."""
    from sqlalchemy import select

    client = TestClient(app)

    # Start as online
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"})

    # Enable physical store
    resp = client.post("/v1/admin/setup/enable-physical-store", json={
        "shop_name": "Mumbai Flagship",
        "timezone": "Asia/Kolkata",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "hybrid"
    assert body["show_shops_management"] is True
    assert body["show_ecommerce_features"] is True

    # Verify physical shop exists
    physical_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "physical")
    ).scalars().all()
    assert len(physical_shops) == 1
    assert physical_shops[0].name == "Mumbai Flagship"
    assert physical_shops[0].timezone == "Asia/Kolkata"

    # Verify POS channel exists for the physical shop
    pos_channels = db.execute(
        select(Channel).where(
            Channel.tenant_id == tenant.id,
            Channel.type == "pos",
            Channel.shop_id == physical_shops[0].id,
        )
    ).scalars().all()
    assert len(pos_channels) == 1


def test_hybrid_shows_all_surfaces(db, tenant: Tenant, auth) -> None:
    """Hybrid tenants see both physical and e-commerce surfaces."""
    client = TestClient(app)
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "hybrid"})

    resp = client.get("/v1/admin/tenant-settings/business-type")
    assert resp.status_code == 200
    body = resp.json()
    assert body["show_shops_management"] is True
    assert body["show_pos_features"] is True
    assert body["show_ecommerce_features"] is True
    assert body["can_add_physical_store"] is True
    assert body["can_add_online_channel"] is True


def test_idempotent_set_online(db, tenant: Tenant, auth) -> None:
    """Setting online twice doesn't create a second virtual shop."""
    from sqlalchemy import select

    client = TestClient(app)
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"})
    client.post("/v1/admin/tenant-settings/business-type",
                json={"business_type": "online"})

    virtual_shops = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalars().all()
    assert len(virtual_shops) == 1
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_business_type_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 5 passed.

- [ ] **Step 3: Run full business-type suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/routers/test_admin_business_type.py \
  tests/integration/test_business_type_e2e.py \
  tests/test_admin_console_contracts.py::test_business_type_out_schema \
  -v 2>&1 | tail -5
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~13 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_business_type_e2e.py
git commit -m "test(business-type): end-to-end smoke test for online-only mode + conversion"
```

---

## Done. Summary of what shipped

- `tenants.business_type` column (`online | retail | hybrid`, default `retail`)
- `shops.kind` column (`virtual | physical`, default `physical`)
- Migration 20260514000001 adding both columns, 20260514000002 seeding `business_type:manage` permission
- `admin_business_type.py` router with:
  - `GET /v1/admin/tenant-settings/business-type` → type + feature-flag map (what the admin web reads for navigation gating)
  - `POST /v1/admin/tenant-settings/business-type` → set type (used at onboarding signup); auto-creates virtual shop for `online`
  - `POST /v1/admin/setup/enable-physical-store` → online→hybrid conversion: creates `Shop(kind=physical)` + POS channel atomically

## What this unlocks

- **Admin web (Next.js)** can read the feature-flag map endpoint and conditionally show/hide navigation items (Shops, POS, Shifts, Devices) based on `business_type`
- **Onboarding wizard** has a clean API: call `POST /v1/admin/tenant-settings/business-type` with the merchant's chosen mode, then redirect to the appropriate setup flow
- **Phase 1 connectors** — online-only merchants always have a virtual shop in the DB, so the channels/inventory-pool system can attach channels to it without special-casing

## Follow-up work (not in this plan)

- Admin web (Next.js) navigation gating — the frontend reads the flag map endpoint and hides/shows items accordingly
- Auto-triggering `enable-physical-store` from the admin web "Add Physical Store" wizard
- `retail→hybrid` flow — already works via existing channel creation; just needs a frontend CTA

---

*End of plan.*
