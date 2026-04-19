# Auto-Resolve Reconciliation Variances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow tenant admins to configure shortage/overage thresholds (tenant-level with optional per-shop override) that auto-resolve reconciliation variances at shift close. Auto-resolved shifts still require admin approval and are visually distinguished in the UI.

**Architecture:** Add four columns (two on `tenants`, two nullable on `shops`). Seed one system `Role` + `User` per tenant for attribution. Inject auto-resolve logic at shift-close time in both admin and device paths via a shared service function. Attribution is recorded in the existing `ShiftClosing.notes` field with a `[AUTO-RESOLVED by …]` marker (mirroring the existing `[RESOLVED by …]` manual pattern). Frontend gets a settings section, a shop edit page, and a small badge.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL with RLS, pytest, Next.js 15, TypeScript, Tailwind.

**Reference spec:** [docs/superpowers/specs/2026-04-19-auto-resolve-reconciliation-variances-design.md](../specs/2026-04-19-auto-resolve-reconciliation-variances-design.md)

---

## File Structure

**Backend (services/api/):**
- `alembic/versions/{YYYYMMDDhhmmss}_auto_resolve_reconciliation.py` — schema + data migration (new)
- `app/models/tables.py` — `Tenant` and `Shop` model updates (modify)
- `app/services/tenant_system_user.py` — shared seed helper (new)
- `app/services/reconciliation_auto_resolve.py` — auto-resolve service function (new)
- `app/routers/admin_shifts.py` — hook into close endpoint (modify)
- `app/routers/device_shifts.py` — hook into close endpoint (modify)
- `app/routers/admin_reconciliation.py` — extend `_rec_status()`, add `auto_resolved` field (modify)
- `app/routers/admin_platform.py` — add reconciliation settings routes (modify)
- `app/routers/shops.py` — add `GET /{id}` and `PATCH /{id}` (modify)
- `app/scripts/reset_demo_showcase.py` — call seed helper on tenant create (modify)
- `tests/services/test_reconciliation_auto_resolve.py` — service-level tests (new)
- `tests/routers/test_admin_shifts_auto_resolve.py` — integration test through close endpoint (new)
- `tests/routers/test_admin_platform_reconciliation_settings.py` — settings route tests (new)
- `tests/routers/test_admin_shops_overrides.py` — shop CRUD override tests (new)
- `tests/routers/test_admin_reconciliation_auto_resolved_field.py` — list-response boolean test (new)

**Frontend (apps/admin-web/):**
- `src/app/(main)/settings/page.tsx` — new "Reconciliation" section (modify)
- `src/app/(main)/shops/[id]/edit/page.tsx` — new shop edit page with overrides (new)
- `src/app/(main)/shops/page.tsx` — link rows to edit page (modify)
- `src/app/(main)/reconciliation/page.tsx` — "Auto" badge (modify)

---

## Task 1: Alembic migration — schema + data migration

**Files:**
- Create: `services/api/alembic/versions/20260419120000_auto_resolve_reconciliation.py`

- [ ] **Step 1: Create the migration file**

Use Alembic's `alembic revision -m "auto resolve reconciliation"` to generate a file with the correct `down_revision` chain, then replace its body with the content below. The filename prefix must match the generated timestamp; the filename used in the File list above is a placeholder.

```python
"""auto resolve reconciliation

Revision ID: auto_resolve_rec
Revises: 20260417000001
Create Date: 2026-04-19 12:00:00.000000

"""
from __future__ import annotations

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "auto_resolve_rec"
down_revision = "20260417000001"  # verify against latest in alembic/versions/
branch_labels = None
depends_on = None


SYSTEM_ROLE_NAME = "system"
SYSTEM_USER_EMAIL_TEMPLATE = "system+{tenant_id}@internal.ims"
UNUSABLE_PASSWORD_HASH = "!auto-resolve-sentinel"  # cannot match any bcrypt/argon2 hash


def upgrade() -> None:
    # 1. Columns on tenants
    op.add_column(
        "tenants",
        sa.Column("auto_resolve_shortage_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenants",
        sa.Column("auto_resolve_overage_cents", sa.Integer(), nullable=False, server_default="0"),
    )

    # 2. Columns on shops (nullable = inherit from tenant)
    op.add_column(
        "shops",
        sa.Column("auto_resolve_shortage_cents_override", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shops",
        sa.Column("auto_resolve_overage_cents_override", sa.Integer(), nullable=True),
    )

    # 3. Data migration: one system Role + User per existing tenant
    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id FROM tenants")).fetchall()
    for (tenant_id,) in tenants:
        # Idempotent: skip if a system role already exists for this tenant
        existing_role = conn.execute(
            sa.text("SELECT id FROM roles WHERE tenant_id = :t AND name = :n"),
            {"t": tenant_id, "n": SYSTEM_ROLE_NAME},
        ).fetchone()

        if existing_role is None:
            role_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, tenant_id, name, display_name, is_system, created_at) "
                    "VALUES (:id, :t, :n, :d, :s, NOW())"
                ),
                {
                    "id": role_id,
                    "t": tenant_id,
                    "n": SYSTEM_ROLE_NAME,
                    "d": "System (automated actions)",
                    "s": True,
                },
            )
        else:
            role_id = existing_role[0]

        # Idempotent: skip if system user for this tenant's system role already exists
        existing_user = conn.execute(
            sa.text("SELECT id FROM users WHERE tenant_id = :t AND role_id = :r"),
            {"t": tenant_id, "r": role_id},
        ).fetchone()
        if existing_user is None:
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, tenant_id, role_id, email, name, password_hash, is_active, created_at, updated_at) "
                    "VALUES (:id, :t, :r, :e, :n, :p, :a, NOW(), NOW())"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "r": role_id,
                    "e": SYSTEM_USER_EMAIL_TEMPLATE.format(tenant_id=tenant_id),
                    "n": "System",
                    "p": UNUSABLE_PASSWORD_HASH,
                    "a": False,  # is_active=False prevents login
                },
            )


def downgrade() -> None:
    # Remove system users and system roles first (reverse of upgrade order)
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM users WHERE role_id IN (SELECT id FROM roles WHERE name = 'system')"
    ))
    conn.execute(sa.text("DELETE FROM roles WHERE name = 'system'"))

    op.drop_column("shops", "auto_resolve_overage_cents_override")
    op.drop_column("shops", "auto_resolve_shortage_cents_override")
    op.drop_column("tenants", "auto_resolve_overage_cents")
    op.drop_column("tenants", "auto_resolve_shortage_cents")
```

**Verify `down_revision`:** open the latest file in `services/api/alembic/versions/` (most recent by timestamp — currently `20260417000001_merge_users.py`) and copy its revision id into `down_revision`.

**Verify column names on `roles` table:** open `services/api/app/models/tables.py` and find the `Role` model. If fields like `is_system` or `display_name` are not present in `Role`, remove them from the INSERT (use only fields that exist). The INSERT is free to set only required columns; other columns use their defaults.

- [ ] **Step 2: Run the migration**

```bash
cd services/api
alembic upgrade head
```

Expected: migration applies cleanly. Verify with:
```bash
python -c "from sqlalchemy import create_engine, text; import os; e = create_engine(os.environ['DATABASE_URL']); print(e.connect().execute(text('SELECT auto_resolve_shortage_cents FROM tenants LIMIT 1')).fetchall())"
```
Expected: prints at least one `(0,)` row, or empty list if no tenants exist.

- [ ] **Step 3: Verify idempotency by running upgrade a second time**

```bash
alembic downgrade -1
alembic upgrade head
```

Expected: no duplicate role/user errors. Any pre-existing system role/user is detected and skipped.

- [ ] **Step 4: Commit**

```bash
git add services/api/alembic/versions/
git commit -m "feat(api): migrate tenants/shops for auto-resolve thresholds and seed system user"
```

---

## Task 2: Update `Tenant` and `Shop` SQLAlchemy models

**Files:**
- Modify: `services/api/app/models/tables.py:110-135` (Tenant)
- Modify: `services/api/app/models/tables.py:138-151` (Shop)

- [ ] **Step 1: Add columns to `Tenant` model**

Insert after `currency_conversion_rate` (around line 120):

```python
    auto_resolve_shortage_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    auto_resolve_overage_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
```

- [ ] **Step 2: Add columns to `Shop` model**

Insert after `default_tax_rate_bps` (around line 147):

```python
    auto_resolve_shortage_cents_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_resolve_overage_cents_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 3: Verify models match migration**

```bash
cd services/api
alembic check
```

Expected: exit code 0 (no pending autogen diff).

- [ ] **Step 4: Commit**

```bash
git add services/api/app/models/tables.py
git commit -m "feat(api): add auto-resolve threshold columns to Tenant and Shop models"
```

---

## Task 3: Create `seed_tenant_system_user` helper

**Files:**
- Create: `services/api/app/services/tenant_system_user.py`
- Create: `services/api/tests/services/test_tenant_system_user.py`

- [ ] **Step 1: Write the failing test**

```python
# services/api/tests/services/test_tenant_system_user.py
from __future__ import annotations

import uuid
from sqlalchemy.orm import Session

from app.models import Role, Tenant, User
from app.services.tenant_system_user import (
    SYSTEM_ROLE_NAME,
    get_tenant_system_user,
    seed_tenant_system_user,
)


def test_seed_creates_system_role_and_user(db: Session, tenant: Tenant) -> None:
    user = seed_tenant_system_user(db, tenant.id)
    db.commit()

    assert user.email.startswith("system+")
    assert user.email.endswith("@internal.ims")
    assert user.is_active is False
    role = db.get(Role, user.role_id)
    assert role is not None
    assert role.name == SYSTEM_ROLE_NAME


def test_seed_is_idempotent(db: Session, tenant: Tenant) -> None:
    first = seed_tenant_system_user(db, tenant.id)
    db.commit()
    second = seed_tenant_system_user(db, tenant.id)
    db.commit()

    assert first.id == second.id


def test_get_tenant_system_user_returns_seeded_user(db: Session, tenant: Tenant) -> None:
    seeded = seed_tenant_system_user(db, tenant.id)
    db.commit()
    fetched = get_tenant_system_user(db, tenant.id)
    assert fetched is not None
    assert fetched.id == seeded.id


def test_get_tenant_system_user_returns_none_if_not_seeded(db: Session) -> None:
    missing_tenant = uuid.uuid4()
    assert get_tenant_system_user(db, missing_tenant) is None
```

The `db` and `tenant` fixtures exist in the project's `conftest.py` (verify location; commonly `services/api/tests/conftest.py`). If `tenant` fixture is not named exactly that, find the equivalent that creates a Tenant and use its name.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/api
pytest tests/services/test_tenant_system_user.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.tenant_system_user'`.

- [ ] **Step 3: Write the helper**

```python
# services/api/app/services/tenant_system_user.py
"""Seed and fetch the per-tenant system user used for automated action attribution."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, User

SYSTEM_ROLE_NAME = "system"
SYSTEM_USER_EMAIL_TEMPLATE = "system+{tenant_id}@internal.ims"
UNUSABLE_PASSWORD_HASH = "!auto-resolve-sentinel"


def _get_system_role(db: Session, tenant_id: uuid.UUID) -> Optional[Role]:
    return db.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == SYSTEM_ROLE_NAME)
    ).scalar_one_or_none()


def get_tenant_system_user(db: Session, tenant_id: uuid.UUID) -> Optional[User]:
    role = _get_system_role(db, tenant_id)
    if role is None:
        return None
    return db.execute(
        select(User).where(User.tenant_id == tenant_id, User.role_id == role.id)
    ).scalar_one_or_none()


def seed_tenant_system_user(db: Session, tenant_id: uuid.UUID) -> User:
    """Idempotently create the system role and system user for a tenant."""
    role = _get_system_role(db, tenant_id)
    if role is None:
        role = Role(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=SYSTEM_ROLE_NAME,
            display_name="System (automated actions)",
        )
        db.add(role)
        db.flush()

    existing = db.execute(
        select(User).where(User.tenant_id == tenant_id, User.role_id == role.id)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        role_id=role.id,
        email=SYSTEM_USER_EMAIL_TEMPLATE.format(tenant_id=tenant_id),
        name="System",
        password_hash=UNUSABLE_PASSWORD_HASH,
        is_active=False,
    )
    db.add(user)
    db.flush()
    return user
```

**Verify `Role` constructor fields:** open `services/api/app/models/tables.py` and find the `Role` class. If `display_name` is not a column on `Role`, remove it from the constructor call. Only pass fields that exist on the model.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/services/test_tenant_system_user.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/tenant_system_user.py services/api/tests/services/test_tenant_system_user.py
git commit -m "feat(api): add tenant_system_user service for automated action attribution"
```

---

## Task 4: Create `reconciliation_auto_resolve` service

**Files:**
- Create: `services/api/app/services/reconciliation_auto_resolve.py`
- Create: `services/api/tests/services/test_reconciliation_auto_resolve.py`

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/services/test_reconciliation_auto_resolve.py
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import ShiftClosing, Shop, Tenant
from app.services.reconciliation_auto_resolve import (
    AUTO_RESOLVED_PREFIX,
    maybe_auto_resolve_shift,
)
from app.services.tenant_system_user import seed_tenant_system_user


def _make_shift(
    db: Session,
    tenant: Tenant,
    shop: Shop,
    discrepancy: int,
) -> ShiftClosing:
    shift = ShiftClosing(
        id=uuid4(),
        tenant_id=tenant.id,
        shop_id=shop.id,
        opened_at=datetime.now(UTC),
        closed_at=datetime.now(UTC),
        expected_cash_cents=10000,
        reported_cash_cents=10000 + discrepancy,
        discrepancy_cents=discrepancy,
        status="closed",
    )
    db.add(shift)
    db.flush()
    return shift


def test_zero_variance_does_not_append_note(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    tenant.auto_resolve_overage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=0)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False
    assert shift.notes is None or AUTO_RESOLVED_PREFIX not in (shift.notes or "")


def test_shortage_within_threshold_auto_resolves(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-4000)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True
    assert AUTO_RESOLVED_PREFIX in shift.notes
    assert "system+" in shift.notes
    assert "-4000" in shift.notes or "shortage" in shift.notes


def test_overage_within_threshold_auto_resolves(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_overage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=4000)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True
    assert AUTO_RESOLVED_PREFIX in shift.notes


def test_variance_exactly_at_threshold_is_inclusive(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-5000)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True


def test_variance_over_threshold_does_not_resolve(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-5001)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False
    assert shift.notes is None or AUTO_RESOLVED_PREFIX not in (shift.notes or "")


def test_threshold_of_zero_disables_direction(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 0  # disabled
    tenant.auto_resolve_overage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-1)  # 1 cent short

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False


def test_shop_override_wins_over_tenant(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    shop.auto_resolve_shortage_cents_override = 100  # much stricter
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-200)

    # Variance exceeds shop override (100) — no auto-resolve
    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False


def test_shop_override_of_zero_disables_when_tenant_has_value(
    db: Session, tenant: Tenant, shop: Shop
) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    shop.auto_resolve_shortage_cents_override = 0  # explicit off
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-100)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False


def test_shop_override_null_falls_back_to_tenant(
    db: Session, tenant: Tenant, shop: Shop
) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    shop.auto_resolve_shortage_cents_override = None
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-100)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True


def test_raises_if_system_user_missing(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    # Do NOT seed the system user
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-100)

    with pytest.raises(RuntimeError, match="system user"):
        maybe_auto_resolve_shift(db, shift, tenant, shop)
```

The `shop` fixture is assumed — verify against `services/api/tests/conftest.py`. If named differently, adapt.

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/services/test_reconciliation_auto_resolve.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the service**

```python
# services/api/app/services/reconciliation_auto_resolve.py
"""Auto-resolve reconciliation variances under tenant-configured thresholds."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import ShiftClosing, Shop, Tenant
from app.services.tenant_system_user import get_tenant_system_user

AUTO_RESOLVED_PREFIX = "[AUTO-RESOLVED"


def _effective_thresholds(tenant: Tenant, shop: Shop) -> tuple[int, int]:
    """Return (shortage_threshold, overage_threshold) applying shop overrides."""
    shortage = (
        shop.auto_resolve_shortage_cents_override
        if shop.auto_resolve_shortage_cents_override is not None
        else tenant.auto_resolve_shortage_cents
    )
    overage = (
        shop.auto_resolve_overage_cents_override
        if shop.auto_resolve_overage_cents_override is not None
        else tenant.auto_resolve_overage_cents
    )
    return shortage, overage


def maybe_auto_resolve_shift(
    db: Session, shift: ShiftClosing, tenant: Tenant, shop: Shop
) -> bool:
    """Append an auto-resolve note to shift.notes iff variance is within threshold.

    Returns True if the shift was auto-resolved, False otherwise. Caller is
    responsible for committing.
    """
    discrepancy = shift.discrepancy_cents
    if discrepancy == 0:
        return False

    shortage_threshold, overage_threshold = _effective_thresholds(tenant, shop)

    if discrepancy < 0:
        threshold = shortage_threshold
        direction = "shortage"
    else:
        threshold = overage_threshold
        direction = "overage"

    if threshold <= 0 or abs(discrepancy) > threshold:
        return False

    system_user = get_tenant_system_user(db, tenant.id)
    if system_user is None:
        raise RuntimeError(
            f"Cannot auto-resolve: no system user seeded for tenant {tenant.id}"
        )

    scope = "shop" if (
        (direction == "shortage" and shop.auto_resolve_shortage_cents_override is not None)
        or (direction == "overage" and shop.auto_resolve_overage_cents_override is not None)
    ) else "tenant"

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    note = (
        f"\n{AUTO_RESOLVED_PREFIX} by {system_user.email} on {timestamp}] "
        f"Variance {discrepancy} within {scope} {direction} threshold of {threshold}."
    )
    shift.notes = (shift.notes or "") + note
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/services/test_reconciliation_auto_resolve.py -v
```
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/reconciliation_auto_resolve.py services/api/tests/services/test_reconciliation_auto_resolve.py
git commit -m "feat(api): add reconciliation auto-resolve service with shortage/overage thresholds"
```

---

## Task 5: Hook auto-resolve into admin shift-close endpoint

**Files:**
- Modify: `services/api/app/routers/admin_shifts.py:200-238`
- Create: `services/api/tests/routers/test_admin_shifts_auto_resolve.py`

- [ ] **Step 1: Write the failing integration test**

```python
# services/api/tests/routers/test_admin_shifts_auto_resolve.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import ShiftClosing, Tenant
from app.services.reconciliation_auto_resolve import AUTO_RESOLVED_PREFIX
from app.services.tenant_system_user import seed_tenant_system_user


def test_admin_close_shift_auto_resolves_small_shortage(
    client: TestClient,
    db,
    tenant: Tenant,
    shop,
    open_shift,            # fixture: open ShiftClosing with expected_cash via cash payments
    admin_auth_headers,    # fixture
    expected_cash_cents,   # fixture: cash owed during shift window, e.g. 10000
) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.commit()

    response = client.patch(
        f"/v1/admin/shifts/{open_shift.id}/close",
        json={"reported_cash_cents": expected_cash_cents - 3000},  # ₹30 short
        headers=admin_auth_headers,
    )
    assert response.status_code == 200

    db.refresh(open_shift)
    assert AUTO_RESOLVED_PREFIX in (open_shift.notes or "")
    assert open_shift.discrepancy_cents == -3000


def test_admin_close_shift_does_not_resolve_above_threshold(
    client: TestClient, db, tenant: Tenant, open_shift, admin_auth_headers, expected_cash_cents,
) -> None:
    tenant.auto_resolve_shortage_cents = 1000
    seed_tenant_system_user(db, tenant.id)
    db.commit()

    response = client.patch(
        f"/v1/admin/shifts/{open_shift.id}/close",
        json={"reported_cash_cents": expected_cash_cents - 5000},
        headers=admin_auth_headers,
    )
    assert response.status_code == 200

    db.refresh(open_shift)
    assert AUTO_RESOLVED_PREFIX not in (open_shift.notes or "")
```

Fixtures `open_shift`, `admin_auth_headers`, `expected_cash_cents` may not exist yet — if they don't, create them in the test file itself (self-contained) rather than relying on conftest. Inspect existing admin_shifts tests (search `tests/routers/` for shift tests) for the exact fixture patterns. If there are no existing admin shift tests, build minimal fixtures inline that create the open shift with a cash payment producing `expected_cash_cents == 10000`.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/routers/test_admin_shifts_auto_resolve.py -v
```
Expected: FAIL — the close endpoint does not yet invoke auto-resolve.

- [ ] **Step 3: Modify the close endpoint**

In `services/api/app/routers/admin_shifts.py`, update `close_shift` to call the service after computing `discrepancy_cents` and before committing:

```python
# Near the top of the file, add:
from app.services.reconciliation_auto_resolve import maybe_auto_resolve_shift
```

Replace lines 223-233 with:

```python
    shift.closed_at = now
    shift.status = "closed"
    shift.expected_cash_cents = expected
    shift.reported_cash_cents = body.reported_cash_cents
    shift.discrepancy_cents = body.reported_cash_cents - expected
    if body.notes:
        shift.notes = (shift.notes or "") + ("\n" if shift.notes else "") + body.notes
    if ctx.user_id:
        shift.closed_by_user_id = ctx.user_id

    tenant_obj = db.get(Tenant, tenant_id)
    shop_obj = db.get(Shop, shift.shop_id)
    if tenant_obj is not None and shop_obj is not None:
        maybe_auto_resolve_shift(db, shift, tenant_obj, shop_obj)

    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="close_shift", resource_type="shift", resource_id=str(shift_id))
```

Ensure `Tenant` is imported from `app.models` at the top of the file if not already present.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/routers/test_admin_shifts_auto_resolve.py -v
```
Expected: both tests PASS.

- [ ] **Step 5: Run the full admin_shifts test suite to check for regressions**

```bash
pytest tests/routers/ -v -k "shift" 2>&1 | tail -50
```
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_shifts.py services/api/tests/routers/test_admin_shifts_auto_resolve.py
git commit -m "feat(api): invoke auto-resolve in admin shift-close endpoint"
```

---

## Task 6: Hook auto-resolve into device shift-close endpoint

**Files:**
- Modify: `services/api/app/routers/device_shifts.py:133-161`
- Modify: `services/api/tests/routers/test_admin_shifts_auto_resolve.py` (add device-path test)

- [ ] **Step 1: Add a device-path test**

Append to `tests/routers/test_admin_shifts_auto_resolve.py`:

```python
def test_device_close_shift_auto_resolves_small_variance(
    client: TestClient, db, tenant: Tenant, open_shift, device_auth_headers, expected_cash_cents,
) -> None:
    tenant.auto_resolve_overage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.commit()

    response = client.patch(
        f"/v1/shifts/{open_shift.id}/close",
        json={"reported_cash_cents": expected_cash_cents + 2000},
        headers=device_auth_headers,
    )
    assert response.status_code == 200

    db.refresh(open_shift)
    assert AUTO_RESOLVED_PREFIX in (open_shift.notes or "")
```

`device_auth_headers` fixture: if not present, inspect existing device-auth tests to construct one.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/routers/test_admin_shifts_auto_resolve.py::test_device_close_shift_auto_resolves_small_variance -v
```
Expected: FAIL.

- [ ] **Step 3: Modify `device_shifts.py` to call the service**

Read `services/api/app/routers/device_shifts.py` around lines 133-161. After `discrepancy_cents` is computed and before the final `db.commit()`, add the same `maybe_auto_resolve_shift(db, shift, tenant_obj, shop_obj)` call. Import the service and any missing models.

Ensure the tenant and shop objects are loaded once — if the endpoint already has them in scope, reuse.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/routers/test_admin_shifts_auto_resolve.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routers/device_shifts.py services/api/tests/routers/test_admin_shifts_auto_resolve.py
git commit -m "feat(api): invoke auto-resolve in device shift-close endpoint"
```

---

## Task 7: Extend `_rec_status` and add `auto_resolved` field

**Files:**
- Modify: `services/api/app/routers/admin_reconciliation.py:35-48` (add field)
- Modify: `services/api/app/routers/admin_reconciliation.py:54-65` (extend _rec_status)
- Modify: `services/api/app/routers/admin_reconciliation.py:98-116` (set field in list handler)
- Create: `services/api/tests/routers/test_admin_reconciliation_auto_resolved_field.py`

- [ ] **Step 1: Write failing tests**

```python
# services/api/tests/routers/test_admin_reconciliation_auto_resolved_field.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import ShiftClosing
from app.services.reconciliation_auto_resolve import AUTO_RESOLVED_PREFIX


def test_auto_resolved_true_when_note_contains_prefix(
    client: TestClient, db, closed_shift_with_variance, admin_auth_headers,
) -> None:
    closed_shift_with_variance.notes = (
        f"\n{AUTO_RESOLVED_PREFIX} by system+x@internal.ims on 2026-04-19T00:00:00Z] Variance -100 within tenant shortage threshold of 5000."
    )
    db.commit()

    resp = client.get("/v1/admin/reconciliation", headers=admin_auth_headers)
    assert resp.status_code == 200
    rows = resp.json()["items"]
    row = next(r for r in rows if r["id"] == str(closed_shift_with_variance.id))
    assert row["auto_resolved"] is True
    assert row["rec_status"] == "resolved"


def test_auto_resolved_false_for_manual_resolution(
    client: TestClient, db, closed_shift_with_variance, admin_auth_headers,
) -> None:
    closed_shift_with_variance.notes = (
        "\n[RESOLVED by admin@example.com on 2026-04-19T00:00:00Z]: counted twice."
    )
    db.commit()

    resp = client.get("/v1/admin/reconciliation", headers=admin_auth_headers)
    rows = resp.json()["items"]
    row = next(r for r in rows if r["id"] == str(closed_shift_with_variance.id))
    assert row["auto_resolved"] is False
    assert row["rec_status"] == "resolved"


def test_auto_resolved_false_for_unresolved_variance(
    client: TestClient, db, closed_shift_with_variance, admin_auth_headers,
) -> None:
    closed_shift_with_variance.notes = None
    db.commit()

    resp = client.get("/v1/admin/reconciliation", headers=admin_auth_headers)
    rows = resp.json()["items"]
    row = next(r for r in rows if r["id"] == str(closed_shift_with_variance.id))
    assert row["auto_resolved"] is False
    assert row["rec_status"] == "variance"
```

`closed_shift_with_variance` fixture — create inline or in a conftest. Must be a `ShiftClosing` with `status="closed"`, non-zero `discrepancy_cents`, no resolution.

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/routers/test_admin_reconciliation_auto_resolved_field.py -v
```
Expected: FAIL — `auto_resolved` field does not exist on response.

- [ ] **Step 3: Update `ReconciliationRow`, `_rec_status`, and list handler**

In `services/api/app/routers/admin_reconciliation.py`:

Replace the `ReconciliationRow` class (lines 35-48) with:

```python
class ReconciliationRow(BaseModel):
    id: UUID
    period: str
    shop_id: UUID
    shop_name: str | None
    expected_cents: int
    actual_cents: int
    variance_cents: int
    rec_status: str
    auto_resolved: bool
    opened_at: str
    closed_at: str | None
    resolution_note: str | None
    reviewed_by: str | None
```

Replace `_rec_status` (lines 54-65) with:

```python
def _rec_status(shift: ShiftClosing) -> tuple[str, str | None, bool]:
    """Return (status, resolution_note, auto_resolved) from a closed shift."""
    notes = shift.notes or ""
    auto_resolved = "[AUTO-RESOLVED" in notes
    if auto_resolved:
        idx = notes.find("[AUTO-RESOLVED")
        return "resolved", notes[idx:], True
    if "[RESOLVED" in notes:
        idx = notes.find("[RESOLVED")
        return "resolved", notes[idx:], False
    if shift.discrepancy_cents != 0:
        return "variance", None, False
    if shift.reviewed_by_user_id is None:
        return "pending_review", None, False
    return "matched", None, False
```

Update the list handler (lines 98-116). Replace the `for shift in shifts:` block with:

```python
    items = []
    for shift in shifts:
        rec_st, resolution_note, auto_resolved = _rec_status(shift)
        shop_name = shops.get(shift.shop_id)
        period = f"{shop_name or 'Unknown'} — {shift.closed_at.strftime('%b %d, %Y') if shift.closed_at else '?'}"
        items.append(ReconciliationRow(
            id=shift.id,
            period=period,
            shop_id=shift.shop_id,
            shop_name=shop_name,
            expected_cents=shift.expected_cash_cents,
            actual_cents=shift.reported_cash_cents,
            variance_cents=shift.discrepancy_cents,
            rec_status=rec_st,
            auto_resolved=auto_resolved,
            opened_at=shift.opened_at.isoformat(),
            closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
            resolution_note=resolution_note,
            reviewed_by=str(shift.reviewed_by_user_id) if shift.reviewed_by_user_id else None,
        ))
```

Update the `resolve_reconciliation` return (around line 160 where `_rec_status` is called). Replace:

```python
    rec_st, resolution_note = _rec_status(shift)
```
with:
```python
    rec_st, resolution_note, auto_resolved = _rec_status(shift)
```

And add `auto_resolved=auto_resolved,` to the `ReconciliationRow(...)` construction in the same function.

Also check `approve_reconciliation` (around line 179) for the same pattern — update if it calls `_rec_status` similarly.

- [ ] **Step 4: Run tests**

```bash
pytest tests/routers/test_admin_reconciliation_auto_resolved_field.py -v
pytest tests/routers/ -v -k "reconciliation" 2>&1 | tail -30
```
Expected: all PASS, no regressions in existing reconciliation tests.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routers/admin_reconciliation.py services/api/tests/routers/test_admin_reconciliation_auto_resolved_field.py
git commit -m "feat(api): expose auto_resolved flag on reconciliation list rows"
```

---

## Task 8: Reconciliation settings routes on admin_platform

**Files:**
- Modify: `services/api/app/routers/admin_platform.py` (add new GET and PATCH)
- Create: `services/api/tests/routers/test_admin_platform_reconciliation_settings.py`

- [ ] **Step 1: Write failing tests**

```python
# services/api/tests/routers/test_admin_platform_reconciliation_settings.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Tenant


def test_get_reconciliation_settings_returns_tenant_values(
    client: TestClient, db, tenant: Tenant, admin_auth_headers,
) -> None:
    tenant.auto_resolve_shortage_cents = 3000
    tenant.auto_resolve_overage_cents = 7000
    db.commit()

    resp = client.get("/v1/admin/tenant-settings/reconciliation", headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "auto_resolve_shortage_cents": 3000,
        "auto_resolve_overage_cents": 7000,
    }


def test_patch_reconciliation_settings_updates_both_fields(
    client: TestClient, db, tenant: Tenant, admin_auth_headers,
) -> None:
    resp = client.patch(
        "/v1/admin/tenant-settings/reconciliation",
        json={"auto_resolve_shortage_cents": 1500, "auto_resolve_overage_cents": 2500},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    db.refresh(tenant)
    assert tenant.auto_resolve_shortage_cents == 1500
    assert tenant.auto_resolve_overage_cents == 2500


def test_patch_accepts_partial_update(
    client: TestClient, db, tenant: Tenant, admin_auth_headers,
) -> None:
    tenant.auto_resolve_shortage_cents = 1000
    tenant.auto_resolve_overage_cents = 2000
    db.commit()

    resp = client.patch(
        "/v1/admin/tenant-settings/reconciliation",
        json={"auto_resolve_shortage_cents": 5000},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    db.refresh(tenant)
    assert tenant.auto_resolve_shortage_cents == 5000
    assert tenant.auto_resolve_overage_cents == 2000  # unchanged


def test_patch_rejects_negative_values(
    client: TestClient, tenant: Tenant, admin_auth_headers,
) -> None:
    resp = client.patch(
        "/v1/admin/tenant-settings/reconciliation",
        json={"auto_resolve_shortage_cents": -1},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify failure**

```bash
pytest tests/routers/test_admin_platform_reconciliation_settings.py -v
```
Expected: FAIL (404 — route not defined).

- [ ] **Step 3: Add routes to `admin_platform.py`**

Read `services/api/app/routers/admin_platform.py` (around lines 60-137 for the currency pattern). Add the following near the currency routes:

```python
class ReconciliationSettingsOut(BaseModel):
    auto_resolve_shortage_cents: int
    auto_resolve_overage_cents: int


class PatchReconciliationBody(BaseModel):
    auto_resolve_shortage_cents: int | None = Field(default=None, ge=0)
    auto_resolve_overage_cents: int | None = Field(default=None, ge=0)


@router.get(
    "/tenant-settings/reconciliation",
    response_model=ReconciliationSettingsOut,
    dependencies=[require_permission("settings:read")],
)
def get_reconciliation_settings(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ReconciliationSettingsOut:
    tenant_id = _require_operator_tenant(ctx)  # reuse helper from this file
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return ReconciliationSettingsOut(
        auto_resolve_shortage_cents=tenant.auto_resolve_shortage_cents,
        auto_resolve_overage_cents=tenant.auto_resolve_overage_cents,
    )


@router.patch(
    "/tenant-settings/reconciliation",
    response_model=ReconciliationSettingsOut,
    dependencies=[require_permission("settings:write")],
)
def patch_reconciliation_settings(
    body: PatchReconciliationBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ReconciliationSettingsOut:
    tenant_id = _require_operator_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if body.auto_resolve_shortage_cents is not None:
        tenant.auto_resolve_shortage_cents = body.auto_resolve_shortage_cents
    if body.auto_resolve_overage_cents is not None:
        tenant.auto_resolve_overage_cents = body.auto_resolve_overage_cents

    write_audit(
        db, tenant_id=tenant_id, operator_id=ctx.operator_id,
        action="update_reconciliation_settings", resource_type="tenant", resource_id=str(tenant_id),
    )
    db.commit()
    db.refresh(tenant)

    return ReconciliationSettingsOut(
        auto_resolve_shortage_cents=tenant.auto_resolve_shortage_cents,
        auto_resolve_overage_cents=tenant.auto_resolve_overage_cents,
    )
```

**Verify permission names** (`settings:read`, `settings:write`) against existing permissions in this file. If they differ (e.g. `platform:settings:read`), use the same strings the currency routes use.

**Verify the tenant-resolving helper name** (`_require_operator_tenant`) — inspect existing routes in `admin_platform.py` and use whatever helper they use.

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/routers/test_admin_platform_reconciliation_settings.py -v
```
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routers/admin_platform.py services/api/tests/routers/test_admin_platform_reconciliation_settings.py
git commit -m "feat(api): add reconciliation tenant-settings GET/PATCH endpoints"
```

---

## Task 9: Admin shop GET and PATCH endpoints with overrides

**Files:**
- Modify: `services/api/app/routers/shops.py` (add two admin routes — confirm router prefix/tags)
- Create: `services/api/tests/routers/test_admin_shops_overrides.py`

- [ ] **Step 1: Inspect current shops router**

```bash
cat services/api/app/routers/shops.py
```

Confirm: is the router mounted under `/v1/admin/shops` or `/v1/shops`? The spec's API paths assume `/v1/admin/shops/{id}`. If `shops.py` is device-facing with `/v1/shops`, add the admin endpoints to a new router or extend the existing one. Most likely a new admin router is appropriate — if so, create `services/api/app/routers/admin_shops.py` and register it in `app/main.py`.

For the rest of this task, assume we are adding admin routes (either in a new file or in an admin-section within the existing file).

- [ ] **Step 2: Write failing tests**

```python
# services/api/tests/routers/test_admin_shops_overrides.py
from __future__ import annotations

from uuid import uuid4
from fastapi.testclient import TestClient


def test_get_shop_returns_override_fields(
    client: TestClient, shop, admin_auth_headers,
) -> None:
    resp = client.get(f"/v1/admin/shops/{shop.id}", headers=admin_auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "auto_resolve_shortage_cents_override" in body
    assert "auto_resolve_overage_cents_override" in body
    assert body["auto_resolve_shortage_cents_override"] is None
    assert body["auto_resolve_overage_cents_override"] is None


def test_patch_shop_sets_override(
    client: TestClient, db, shop, admin_auth_headers,
) -> None:
    resp = client.patch(
        f"/v1/admin/shops/{shop.id}",
        json={"auto_resolve_shortage_cents_override": 2500},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    db.refresh(shop)
    assert shop.auto_resolve_shortage_cents_override == 2500


def test_patch_shop_clears_override_with_null(
    client: TestClient, db, shop, admin_auth_headers,
) -> None:
    shop.auto_resolve_shortage_cents_override = 2500
    db.commit()

    resp = client.patch(
        f"/v1/admin/shops/{shop.id}",
        json={"auto_resolve_shortage_cents_override": None},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200
    db.refresh(shop)
    assert shop.auto_resolve_shortage_cents_override is None


def test_patch_shop_rejects_negative_override(
    client: TestClient, shop, admin_auth_headers,
) -> None:
    resp = client.patch(
        f"/v1/admin/shops/{shop.id}",
        json={"auto_resolve_shortage_cents_override": -5},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422


def test_get_shop_404_for_other_tenant(
    client: TestClient, admin_auth_headers,
) -> None:
    resp = client.get(f"/v1/admin/shops/{uuid4()}", headers=admin_auth_headers)
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests to verify failure**

```bash
pytest tests/routers/test_admin_shops_overrides.py -v
```
Expected: FAIL (404 route not found).

- [ ] **Step 4: Implement the admin shop routes**

Create `services/api/app/routers/admin_shops.py` (or extend the existing shops router — pick the cleanest location):

```python
"""Admin shop CRUD endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Shop
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/admin/shops", tags=["Admin Shops"])


def _require_tenant(ctx) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator has no tenant")
    return ctx.tenant_id


class ShopOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    default_tax_rate_bps: int
    auto_resolve_shortage_cents_override: int | None
    auto_resolve_overage_cents_override: int | None


class PatchShopBody(BaseModel):
    name: str | None = None
    default_tax_rate_bps: int | None = Field(default=None, ge=0)
    auto_resolve_shortage_cents_override: int | None = Field(default=None, ge=0)
    auto_resolve_overage_cents_override: int | None = Field(default=None, ge=0)

    # Distinguish "field not sent" from "field sent as null"
    model_config = {"extra": "forbid"}


@router.get("/{shop_id}", response_model=ShopOut, dependencies=[require_permission("shops:read")])
def get_shop(
    shop_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShopOut:
    tenant_id = _require_tenant(ctx)
    shop = db.get(Shop, shop_id)
    if shop is None or shop.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Shop not found")
    return ShopOut(
        id=shop.id,
        tenant_id=shop.tenant_id,
        name=shop.name,
        default_tax_rate_bps=shop.default_tax_rate_bps,
        auto_resolve_shortage_cents_override=shop.auto_resolve_shortage_cents_override,
        auto_resolve_overage_cents_override=shop.auto_resolve_overage_cents_override,
    )


@router.patch("/{shop_id}", response_model=ShopOut, dependencies=[require_permission("shops:write")])
def patch_shop(
    shop_id: UUID,
    body: PatchShopBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShopOut:
    tenant_id = _require_tenant(ctx)
    shop = db.get(Shop, shop_id)
    if shop is None or shop.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Shop not found")

    patch = body.model_dump(exclude_unset=True)
    for field, value in patch.items():
        setattr(shop, field, value)

    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="update_shop", resource_type="shop", resource_id=str(shop_id))
    db.commit()
    db.refresh(shop)

    return ShopOut(
        id=shop.id,
        tenant_id=shop.tenant_id,
        name=shop.name,
        default_tax_rate_bps=shop.default_tax_rate_bps,
        auto_resolve_shortage_cents_override=shop.auto_resolve_shortage_cents_override,
        auto_resolve_overage_cents_override=shop.auto_resolve_overage_cents_override,
    )
```

Register the router in `services/api/app/main.py`:

```python
from app.routers import admin_shops
app.include_router(admin_shops.router)
```

**Verify permission strings** `shops:read` / `shops:write` against this codebase's permission registry. Adapt to whatever matches existing admin routes (search for `require_permission(` to find the pattern).

- [ ] **Step 5: Run tests to verify pass**

```bash
pytest tests/routers/test_admin_shops_overrides.py -v
```
Expected: all 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_shops.py services/api/app/main.py services/api/tests/routers/test_admin_shops_overrides.py
git commit -m "feat(api): add admin shop GET/PATCH endpoints with override fields"
```

---

## Task 10: Wire system-user seeding into tenant provisioning

**Files:**
- Modify: `services/api/app/scripts/reset_demo_showcase.py:309-362` (call seed helper after role seeding)

- [ ] **Step 1: Add the call after existing role seeding**

Locate where `_seed_system_roles(db, tenant.id)` is called (approximately line 330 based on explore report). Add immediately after it:

```python
from app.services.tenant_system_user import seed_tenant_system_user
# ...
_seed_system_roles(db, tenant.id)
seed_tenant_system_user(db, tenant.id)
```

Place the import at the top of the file with other imports.

- [ ] **Step 2: Search for other tenant-creation sites**

Use Grep to find any other places where a `Tenant(...)` row is constructed (i.e. any path besides the demo script). This catches admin-triggered tenant provisioning, signup flows, etc:

Grep pattern: `Tenant\(` in `services/api/app/` (excluding tests).

For any production tenant-creation site found, add a `seed_tenant_system_user(db, tenant.id)` call immediately after the tenant insert. If none exist beyond the demo script, note it in the commit message and move on.

- [ ] **Step 3: Run demo reset to verify end-to-end**

```bash
docker compose exec -e IMS_DEMO_RESET_OK=1 api python -m app.scripts.reset_demo_showcase
```

Expected: runs cleanly. Verify the system user exists:

```bash
docker compose exec api python -c "
from app.db.session import SessionLocal
from app.services.tenant_system_user import get_tenant_system_user
from app.models import Tenant
db = SessionLocal()
tenants = db.query(Tenant).all()
for t in tenants:
    u = get_tenant_system_user(db, t.id)
    print(t.slug, '->', u.email if u else 'MISSING')
"
```

Expected: every tenant prints `system+<uuid>@internal.ims`, no `MISSING`.

- [ ] **Step 4: Commit**

```bash
git add services/api/app/scripts/reset_demo_showcase.py
git commit -m "feat(api): seed system user alongside system roles during tenant creation"
```

---

## Task 11: Admin web — Reconciliation section in tenant settings

**Files:**
- Modify: `apps/admin-web/src/app/(main)/settings/page.tsx`

- [ ] **Step 1: Add the settings state, fetcher, and save handler**

Read the existing currency-settings block in the page. Immediately after it (or in a parallel sibling card), add a new `ReconciliationSettings` section following the same pattern:

```tsx
type ReconciliationSettings = {
  auto_resolve_shortage_cents: number;
  auto_resolve_overage_cents: number;
};

// Inside the component:
const [reconSettings, setReconSettings] = useState<ReconciliationSettings | null>(null);
const [reconShortageInput, setReconShortageInput] = useState("");
const [reconOverageInput, setReconOverageInput] = useState("");
const [reconSaving, setReconSaving] = useState(false);
const [reconError, setReconError] = useState<string | null>(null);

useEffect(() => {
  fetch("/api/ims/v1/admin/tenant-settings/reconciliation")
    .then((r) => r.json())
    .then((data: ReconciliationSettings) => {
      setReconSettings(data);
      setReconShortageInput(String(data.auto_resolve_shortage_cents));
      setReconOverageInput(String(data.auto_resolve_overage_cents));
    })
    .catch(() => setReconError("Failed to load reconciliation settings"));
}, []);

const saveReconSettings = async () => {
  setReconSaving(true);
  setReconError(null);
  const shortage = parseInt(reconShortageInput, 10);
  const overage = parseInt(reconOverageInput, 10);
  if (Number.isNaN(shortage) || shortage < 0 || Number.isNaN(overage) || overage < 0) {
    setReconError("Values must be non-negative integers (in cents)");
    setReconSaving(false);
    return;
  }
  const resp = await fetch("/api/ims/v1/admin/tenant-settings/reconciliation", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      auto_resolve_shortage_cents: shortage,
      auto_resolve_overage_cents: overage,
    }),
  });
  if (!resp.ok) {
    setReconError("Save failed");
  } else {
    const data: ReconciliationSettings = await resp.json();
    setReconSettings(data);
  }
  setReconSaving(false);
};
```

- [ ] **Step 2: Add the section JSX**

Place inside the settings page, as a new card/section. Follow the same visual pattern as the existing currency section:

```tsx
<section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
  <h2 className="text-lg font-semibold text-slate-900">Reconciliation</h2>
  <p className="mt-1 text-sm text-slate-600">
    Configure variance thresholds that will be auto-resolved at shift close.
    Set to 0 to disable auto-resolve in that direction.
  </p>
  <div className="mt-4 grid gap-4 sm:grid-cols-2">
    <label className="block">
      <span className="text-sm font-medium text-slate-700">
        Shortage auto-resolve limit (in cents)
      </span>
      <input
        type="number"
        min={0}
        value={reconShortageInput}
        onChange={(e) => setReconShortageInput(e.target.value)}
        className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
      />
      <span className="mt-1 block text-xs text-slate-500">
        Variances where the cashier counted less than expected, up to this amount, auto-resolve.
      </span>
    </label>
    <label className="block">
      <span className="text-sm font-medium text-slate-700">
        Overage auto-resolve limit (in cents)
      </span>
      <input
        type="number"
        min={0}
        value={reconOverageInput}
        onChange={(e) => setReconOverageInput(e.target.value)}
        className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
      />
      <span className="mt-1 block text-xs text-slate-500">
        Variances where the cashier counted more than expected, up to this amount, auto-resolve.
      </span>
    </label>
  </div>
  {reconError && <p className="mt-3 text-sm text-red-600">{reconError}</p>}
  <div className="mt-4">
    <PrimaryButton onClick={saveReconSettings} disabled={reconSaving}>
      {reconSaving ? "Saving…" : "Save"}
    </PrimaryButton>
  </div>
</section>
```

Match the existing page's Tailwind/component conventions — the snippet above uses raw Tailwind; adapt to whatever primitives the page uses (e.g. `<TextInput>`, `<PrimaryButton>` from `@/components/ui/primitives`).

- [ ] **Step 3: Build and lint**

```bash
cd apps/admin-web
npm run build
npm run lint
```
Expected: clean build and lint.

- [ ] **Step 4: Manual verification**

Start the stack (`docker compose up`), log in as admin, navigate to Settings, confirm the Reconciliation card appears, set values, save, reload page, confirm values persist.

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/app/(main)/settings/page.tsx
git commit -m "feat(admin-web): add reconciliation thresholds section to tenant settings"
```

---

## Task 12: Admin web — Shop edit page with override controls

**Files:**
- Create: `apps/admin-web/src/app/(main)/shops/[id]/edit/page.tsx`
- Modify: `apps/admin-web/src/app/(main)/shops/page.tsx` (add link to edit page per row)

- [ ] **Step 1: Create the edit page**

```tsx
// apps/admin-web/src/app/(main)/shops/[id]/edit/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { PrimaryButton, SecondaryButton, Toggle } from "@/components/ui/primitives";

type ShopDetail = {
  id: string;
  tenant_id: string;
  name: string;
  default_tax_rate_bps: number;
  auto_resolve_shortage_cents_override: number | null;
  auto_resolve_overage_cents_override: number | null;
};

type TenantReconSettings = {
  auto_resolve_shortage_cents: number;
  auto_resolve_overage_cents: number;
};

export default function EditShopPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [shop, setShop] = useState<ShopDetail | null>(null);
  const [tenantRecon, setTenantRecon] = useState<TenantReconSettings | null>(null);
  const [shortageOverrideEnabled, setShortageOverrideEnabled] = useState(false);
  const [overageOverrideEnabled, setOverageOverrideEnabled] = useState(false);
  const [shortageValue, setShortageValue] = useState("");
  const [overageValue, setOverageValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(`/api/ims/v1/admin/shops/${id}`).then((r) => r.json()),
      fetch("/api/ims/v1/admin/tenant-settings/reconciliation").then((r) => r.json()),
    ]).then(([shopData, reconData]: [ShopDetail, TenantReconSettings]) => {
      setShop(shopData);
      setTenantRecon(reconData);
      setShortageOverrideEnabled(shopData.auto_resolve_shortage_cents_override !== null);
      setOverageOverrideEnabled(shopData.auto_resolve_overage_cents_override !== null);
      setShortageValue(String(shopData.auto_resolve_shortage_cents_override ?? ""));
      setOverageValue(String(shopData.auto_resolve_overage_cents_override ?? ""));
    });
  }, [id]);

  const save = async () => {
    setSaving(true);
    setError(null);
    const body: Record<string, number | null> = {};
    if (shortageOverrideEnabled) {
      const v = parseInt(shortageValue, 10);
      if (Number.isNaN(v) || v < 0) {
        setError("Shortage override must be a non-negative integer");
        setSaving(false);
        return;
      }
      body.auto_resolve_shortage_cents_override = v;
    } else {
      body.auto_resolve_shortage_cents_override = null;
    }
    if (overageOverrideEnabled) {
      const v = parseInt(overageValue, 10);
      if (Number.isNaN(v) || v < 0) {
        setError("Overage override must be a non-negative integer");
        setSaving(false);
        return;
      }
      body.auto_resolve_overage_cents_override = v;
    } else {
      body.auto_resolve_overage_cents_override = null;
    }
    const resp = await fetch(`/api/ims/v1/admin/shops/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      setError("Save failed");
      setSaving(false);
      return;
    }
    router.push("/shops");
  };

  if (!shop || !tenantRecon) return <div className="p-6">Loading…</div>;

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-2xl font-semibold">Edit shop: {shop.name}</h1>

      <section className="mt-6 rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold">Reconciliation overrides</h2>
        <p className="mt-1 text-sm text-slate-600">
          Override the tenant-level auto-resolve thresholds for this shop only.
        </p>

        <div className="mt-4 space-y-6">
          <div>
            <div className="flex items-center gap-3">
              <Toggle
                checked={!shortageOverrideEnabled}
                onChange={(v) => setShortageOverrideEnabled(!v)}
              />
              <span className="text-sm text-slate-700">
                Use tenant default (₹{(tenantRecon.auto_resolve_shortage_cents / 100).toFixed(2)})
              </span>
            </div>
            {shortageOverrideEnabled && (
              <input
                type="number"
                min={0}
                value={shortageValue}
                onChange={(e) => setShortageValue(e.target.value)}
                className="mt-2 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="Shortage threshold in cents (0 disables)"
              />
            )}
          </div>

          <div>
            <div className="flex items-center gap-3">
              <Toggle
                checked={!overageOverrideEnabled}
                onChange={(v) => setOverageOverrideEnabled(!v)}
              />
              <span className="text-sm text-slate-700">
                Use tenant default (₹{(tenantRecon.auto_resolve_overage_cents / 100).toFixed(2)})
              </span>
            </div>
            {overageOverrideEnabled && (
              <input
                type="number"
                min={0}
                value={overageValue}
                onChange={(e) => setOverageValue(e.target.value)}
                className="mt-2 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="Overage threshold in cents (0 disables)"
              />
            )}
          </div>
        </div>
      </section>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6 flex gap-3">
        <PrimaryButton onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </PrimaryButton>
        <SecondaryButton onClick={() => router.push("/shops")}>Cancel</SecondaryButton>
      </div>
    </div>
  );
}
```

Replace `₹` with the proper `formatMoney(value, currency)` call from [apps/admin-web/src/lib/format.ts:13](apps/admin-web/src/lib/format.ts#L13) if the shop edit page sits inside the `CurrencyProvider` context. Fetch currency config in the same `Promise.all` if not.

- [ ] **Step 2: Add "Edit" link on shops list**

Open `apps/admin-web/src/app/(main)/shops/page.tsx`. On each shop row, add a link to `/shops/{id}/edit`:

```tsx
import Link from "next/link";
// ...
<Link href={`/shops/${shop.id}/edit`} className="text-indigo-600 hover:underline">Edit</Link>
```

- [ ] **Step 3: Build and lint**

```bash
cd apps/admin-web
npm run build
npm run lint
```
Expected: clean build and lint.

- [ ] **Step 4: Manual verification**

Start the stack, navigate to Shops, click Edit on a shop, toggle overrides off/on, enter a value, save, reload page, confirm values persist. Confirm that turning the toggle back to "Use tenant default" and saving clears the override (GET returns null).

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/app/(main)/shops/
git commit -m "feat(admin-web): add shop edit page with auto-resolve threshold overrides"
```

---

## Task 13: Admin web — "Auto" badge on reconciliation list

**Files:**
- Modify: `apps/admin-web/src/app/(main)/reconciliation/page.tsx:239`

- [ ] **Step 1: Extend the row type**

Find the row TypeScript type in the file (near the top, likely `type ReconciliationRow = { ... }`). Add:

```tsx
auto_resolved: boolean;
```

- [ ] **Step 2: Render the badge next to status**

Around line 239 (`<Badge tone={recTone(r.rec_status)}>{r.rec_status}</Badge>`), wrap with a flex container and conditionally render an "Auto" pill:

```tsx
<div className="flex items-center gap-1.5">
  <Badge tone={recTone(r.rec_status)}>{r.rec_status}</Badge>
  {r.auto_resolved && (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
      Auto
    </span>
  )}
</div>
```

- [ ] **Step 3: Build and lint**

```bash
cd apps/admin-web
npm run build
npm run lint
```
Expected: clean.

- [ ] **Step 4: Manual verification**

Create a shift that auto-resolves (via API or through the app), reload the reconciliation page, confirm the "Auto" pill appears next to the `resolved` status. Manually resolve a different shift, confirm no pill.

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/app/(main)/reconciliation/page.tsx
git commit -m "feat(admin-web): show Auto badge on auto-resolved reconciliation rows"
```

---

## Task 14: End-to-end verification

**Files:** none (manual verification pass).

- [ ] **Step 1: Run the full backend test suite**

```bash
cd services/api
pytest -x 2>&1 | tail -40
```
Expected: all tests PASS. Any regressions should be diagnosed before declaring done.

- [ ] **Step 2: Start the full stack**

```bash
docker compose up --build
```

Wait for API (`http://localhost:8001/docs`) and admin web (`http://localhost:3100`) to be reachable.

- [ ] **Step 3: End-to-end happy path**

  1. Log in to admin web as an operator.
  2. Navigate to Settings → Reconciliation. Set shortage threshold to 5000 cents. Save.
  3. Navigate to Shops. Edit a shop. Leave toggles on "Use tenant default". Save.
  4. Open the cashier app (or simulate via API). Close a shift with variance of -3000 cents (within threshold).
  5. In admin web, go to Reconciliation. Verify the shift shows status `resolved` with an `Auto` badge.
  6. Click into the row and confirm the `[AUTO-RESOLVED by system+…@internal.ims on …] Variance -3000 within tenant shortage threshold of 5000.` note.
  7. Approve the shift. Confirm it moves to `matched` / `approved` status.

- [ ] **Step 4: End-to-end negative path**

  1. Close another shift with variance of -6000 cents (over threshold).
  2. Confirm the shift shows status `variance` in Reconciliation.
  3. Confirm no `Auto` badge.
  4. Manually Resolve + Approve as before.

- [ ] **Step 5: End-to-end shop override path**

  1. Edit the shop. Turn off "Use tenant default" on shortage. Set override to 1000 cents. Save.
  2. Close a shift with -3000 cents variance. Confirm it lands in `variance` status (override is stricter).
  3. Edit the shop again. Set override to 0 cents. Save. Close another shift with -100 cents. Confirm it still lands in `variance` (explicit zero disables).
  4. Edit the shop again. Toggle back to "Use tenant default". Save. Close another shift with -3000 cents. Confirm it auto-resolves.

- [ ] **Step 6: Commit any final adjustments from verification**

```bash
git status
# If any changes were made during verification, commit them.
```

---

## Completion

All tasks complete → feature is shippable. No feature flag needed; behavior is dormant until an admin sets a threshold.

**Future work (out of scope here):**
- Per-shop override UI inside the reconciliation list page (quick-edit).
- Surface the system user in the audit log viewer with a distinct icon.
- Remove the `[RESOLVED`/`[AUTO-RESOLVED` string marker system in favor of explicit columns (`resolved_by_user_id`, `resolved_at`, `auto_resolved`) — clean-up work once the feature has settled.
