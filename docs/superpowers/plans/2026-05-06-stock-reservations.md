# Stock Reservation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add soft-TTL stock reservations so channels that let shoppers race for the same inventory (Shopify carts, headless storefronts, hosted checkout) can hold stock without committing it — released automatically on expiry, committed to a real stock movement on order completion.

**Architecture:** New `stock_reservations` table tracks held units per (tenant, channel, product, shop, cart_token) with `expires_at` and a status enum (`active | committed | released | expired`). A new `reservation_service.py` exposes `reserve()`, `commit()`, `release()`, and `sweep_expired()`. `available_stock_for_channel` (added in the channels sub-project) is extended to subtract active reservations atomically. A worker task `sweep_expired_reservations` marks expired rows; can be enqueued on a schedule (cron / RQ scheduler) or via an admin endpoint for manual / test runs.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL (with RLS), Redis (RQ), pytest

**Out of scope (deferred):**
- `variant_id` column — variants aren't a separate table yet (just a `Product.variant_label` text field). Add when variants get formalised in a future sub-project.
- Concurrent-reserve atomicity beyond what Postgres' default isolation level provides. The unique constraint on `(channel_id, cart_token, product_id, shop_id)` prevents accidental duplicate holds; harder concurrency (deduct-on-reserve under hot contention) is a Phase 1 hardening item.
- RQ scheduler integration — we ship the task callable but don't wire a cron/scheduler in this plan. The admin endpoint provides manual/test triggering; production scheduling is operator-configurable.

---

### Task 1: Migration + StockReservation model + contract test

**Files:**
- Create: `services/api/alembic/versions/20260508000001_stock_reservations.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write the failing contract test**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_stock_reservation_out_schema() -> None:
    from app.routers.admin_reservations import StockReservationOut

    r = StockReservationOut(
        id=uuid4(),
        tenant_id=uuid4(),
        channel_id=uuid4(),
        product_id=uuid4(),
        shop_id=uuid4(),
        quantity=3,
        cart_token="cart_abc123",
        purpose="cart",
        status="active",
        expires_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["quantity"] == 3
    assert d["status"] == "active"
    assert d["purpose"] == "cart"
```

Imports `from datetime import UTC, datetime` and `from uuid import uuid4` are already at the top of the file.

- [ ] **Step 2: Run test to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_stock_reservation_out_schema -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_reservations'`. Stays red until Task 5.

- [ ] **Step 3: Add the SQLAlchemy model**

In `services/api/app/models/tables.py`, append after `OrderPayment`:

```python
class StockReservation(Base):
    """A soft-TTL hold on stock for a channel cart / pending payment.

    States:
      active     — currently holds stock; subtracted from available
      committed  — converted to a real stock_movements row (sale completed)
      released   — explicitly cancelled (cart abandoned / order voided)
      expired    — TTL passed without commit; swept by background task

    The unique constraint on (channel_id, cart_token, product_id, shop_id) prevents
    accidental duplicate holds for the same cart line. Re-reserving the same line
    should update the existing row's quantity / expiry, not create a new one.
    """
    __tablename__ = "stock_reservations"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "cart_token", "product_id", "shop_id",
            name="uq_reservation_channel_cart_product_shop",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    cart_token: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), default="cart", server_default="cart", nullable=False)
    # purpose: 'cart' | 'payment_pending'
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Export the model**

In `services/api/app/models/__init__.py`, add `StockReservation` to BOTH the import block and `__all__` (alphabetical — between `Shop`/`ShopProductTax` and `Supplier`).

- [ ] **Step 5: Write the migration**

Create `services/api/alembic/versions/20260508000001_stock_reservations.py`:

```python
"""Stock reservations: soft-TTL holds on stock for channel carts / pending payments

Revision ID: 20260508000001
Revises: 20260507000001
Create Date: 2026-05-08 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260508000001"
down_revision = "20260507000001"
branch_labels = None
depends_on = None


_RLS_POLICY = """
COALESCE(current_setting('ims.is_admin', true), '') = 'true'
OR (
  NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
  AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
)
"""


def upgrade() -> None:
    op.create_table(
        "stock_reservations",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="cart"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "channel_id", "cart_token", "product_id", "shop_id",
            name="uq_reservation_channel_cart_product_shop",
        ),
    )
    # Indexes optimised for the two hot queries:
    # 1. available_stock_for_channel: active reservations summed across pool shops for a product
    # 2. sweep_expired: active rows past expiry
    op.create_index("ix_stock_reservations_tenant_id", "stock_reservations", ["tenant_id"])
    op.create_index(
        "ix_stock_reservations_active_lookup",
        "stock_reservations",
        ["product_id", "shop_id", "status"],
    )
    op.create_index(
        "ix_stock_reservations_expiry_sweep",
        "stock_reservations",
        ["status", "expires_at"],
    )

    # Seed permission for admin reservation management (debug / support tooling)
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'reservations:manage', 'Manage Stock Reservations', 'inventory',
                'View and manually release stock reservations (debug/support tool)')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    # Grant to the system 'owner' role (matches the channels:manage / inventory_pools:manage pattern
    # from migration 20260507000001).
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'reservations:manage'
        ON CONFLICT DO NOTHING
    """)

    # Enable RLS
    op.execute(f"""
        ALTER TABLE stock_reservations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE stock_reservations FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON stock_reservations
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON stock_reservations;")
    op.execute("ALTER TABLE stock_reservations NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE stock_reservations DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'reservations:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'reservations:manage'")

    op.drop_index("ix_stock_reservations_expiry_sweep", table_name="stock_reservations")
    op.drop_index("ix_stock_reservations_active_lookup", table_name="stock_reservations")
    op.drop_index("ix_stock_reservations_tenant_id", table_name="stock_reservations")
    op.drop_table("stock_reservations")
```

- [ ] **Step 6: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260508000001_stock_reservations.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260507000001 -> 20260508000001`

- [ ] **Step 7: Verify schema, RLS, and permission**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d stock_reservations"
docker compose exec postgres psql -U ims -d ims -c "SELECT codename FROM permissions WHERE codename='reservations:manage'"
docker compose exec postgres psql -U ims -d ims -c "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='stock_reservations'"
```
Expected: full table description, permission row, both `t` for RLS flags.

- [ ] **Step 8: Commit**

```bash
git add services/api/alembic/versions/20260508000001_stock_reservations.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(reservations): add stock_reservations table with RLS"
```

The contract test stays red until Task 5 (when the router is created).

---

### Task 2: Reservation service — reserve / commit / release / sweep_expired

**Files:**
- Create: `services/api/app/services/reservation_service.py`
- Create: `services/api/tests/services/test_reservation_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_reservation_service.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement,
    StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    """Mirror migration: POS channel + single-shop pool for the test shop."""
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
        type="pos",
        name=f"POS at {shop.name}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="USD",
        shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1000,
    )
    db.add(p)
    db.flush()
    return p


def test_reserve_creates_active_row_with_default_ttl(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import reserve

    res = reserve(
        db,
        tenant_id=tenant.id,
        channel_id=channel.id,
        product_id=product.id,
        shop_id=shop.id,
        quantity=2,
        cart_token="cart_abc",
        purpose="cart",
    )
    assert res.status == "active"
    assert res.quantity == 2
    assert res.purpose == "cart"
    # Default cart TTL is 15 min
    delta = (res.expires_at - datetime.now(UTC)).total_seconds()
    assert 800 < delta < 1000  # ~900s with some tolerance


def test_reserve_uses_payment_ttl_when_purpose_is_payment_pending(
    db, tenant: Tenant, shop: Shop, channel: Channel, product: Product,
) -> None:
    from app.services.reservation_service import reserve

    res = reserve(
        db,
        tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_pay",
        purpose="payment_pending",
    )
    delta = (res.expires_at - datetime.now(UTC)).total_seconds()
    assert 86_000 < delta < 87_000  # ~24h


def test_reserve_uses_channel_config_override(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    """Channel.config['cart_ttl_seconds'] overrides the default."""
    from app.services.reservation_service import reserve

    channel.config = {"cart_ttl_seconds": 60}
    db.flush()

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_override",
    )
    delta = (res.expires_at - datetime.now(UTC)).total_seconds()
    assert 50 < delta < 70


def test_reserve_is_idempotent_for_same_cart_line(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    """Reserving the same (channel, cart_token, product, shop) twice updates the existing row."""
    from sqlalchemy import select
    from app.services.reservation_service import reserve

    first = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=2, cart_token="cart_idem",
    )
    second = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=5, cart_token="cart_idem",
    )
    assert first.id == second.id
    assert second.quantity == 5

    rows = db.execute(
        select(StockReservation).where(StockReservation.cart_token == "cart_idem")
    ).scalars().all()
    assert len(rows) == 1


def test_commit_converts_reservation_to_stock_movement(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from sqlalchemy import select
    from app.services.reservation_service import reserve, commit_reservation

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=3, cart_token="cart_commit",
    )

    movement = commit_reservation(db, res.id)
    assert movement is not None
    assert movement.quantity_delta == -3
    assert movement.movement_type == "sale"
    assert movement.shop_id == shop.id
    assert movement.product_id == product.id
    assert movement.source_channel_id == channel.id

    # Reservation status flipped
    db.refresh(res)
    assert res.status == "committed"


def test_release_marks_reservation_released(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import reserve, release_reservation

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_release",
    )
    release_reservation(db, res.id)
    db.refresh(res)
    assert res.status == "released"


def test_sweep_expired_marks_past_due_active_rows(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    """An active reservation past its expires_at gets flipped to 'expired' on sweep."""
    from app.services.reservation_service import sweep_expired

    # Manually insert a past-expired active reservation (bypassing reserve's TTL logic)
    expired = StockReservation(
        tenant_id=tenant.id,
        channel_id=channel.id,
        product_id=product.id,
        shop_id=shop.id,
        quantity=1,
        cart_token="cart_old",
        purpose="cart",
        status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(expired)
    # And one that's still active
    fresh = StockReservation(
        tenant_id=tenant.id,
        channel_id=channel.id,
        product_id=product.id,
        shop_id=shop.id,
        quantity=1,
        cart_token="cart_fresh",
        purpose="cart",
        status="active",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    db.add(fresh)
    db.flush()

    count = sweep_expired(db)
    assert count == 1

    db.refresh(expired)
    db.refresh(fresh)
    assert expired.status == "expired"
    assert fresh.status == "active"


def test_commit_returns_none_for_already_committed(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    """Committing a reservation that's already committed/released/expired is a no-op."""
    from app.services.reservation_service import reserve, commit_reservation

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_double",
    )
    movement1 = commit_reservation(db, res.id)
    assert movement1 is not None

    movement2 = commit_reservation(db, res.id)
    assert movement2 is None  # Already committed
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_reservation_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.reservation_service'`

- [ ] **Step 3: Implement the reservation service**

Create `services/api/app/services/reservation_service.py`:

```python
"""Stock reservation engine: reserve, commit, release, sweep_expired.

A reservation is a soft hold on stock for a (channel, cart_token, product, shop)
key. Active reservations are subtracted from `available_stock_for_channel` so
two shoppers can't race for the same unit. TTL is per-channel-configurable via
``Channel.config['cart_ttl_seconds']`` / `'payment_ttl_seconds'`; defaults are
15 min for carts, 24 h for pending payments.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Channel, StockMovement, StockReservation


DEFAULT_CART_TTL_SECONDS = 15 * 60          # 15 minutes
DEFAULT_PAYMENT_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _resolve_ttl_seconds(channel: Channel, purpose: str) -> int:
    """Pick the TTL for this channel + purpose.

    Looks up Channel.config[{purpose}_ttl_seconds] if present, else falls back
    to the module-level default for that purpose.
    """
    config = channel.config or {}
    if purpose == "payment_pending":
        return int(config.get("payment_ttl_seconds", DEFAULT_PAYMENT_TTL_SECONDS))
    return int(config.get("cart_ttl_seconds", DEFAULT_CART_TTL_SECONDS))


def reserve(
    db: Session,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    product_id: UUID,
    shop_id: UUID,
    quantity: int,
    cart_token: str,
    purpose: str = "cart",
) -> StockReservation:
    """Create or update a reservation for a (channel, cart_token, product, shop) line.

    If a reservation for that exact key already exists, its quantity, expiry, and
    status are updated (and status is forced back to 'active' even if it had
    expired — the caller is asserting they want this hold now). This makes the
    function safe to call from cart-update flows.
    """
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ValueError(f"Unknown channel_id {channel_id}")

    ttl = _resolve_ttl_seconds(channel, purpose)
    new_expiry = datetime.now(UTC) + timedelta(seconds=ttl)

    existing = db.execute(
        select(StockReservation).where(
            StockReservation.channel_id == channel_id,
            StockReservation.cart_token == cart_token,
            StockReservation.product_id == product_id,
            StockReservation.shop_id == shop_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.quantity = quantity
        existing.purpose = purpose
        existing.status = "active"
        existing.expires_at = new_expiry
        db.flush()
        return existing

    res = StockReservation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        product_id=product_id,
        shop_id=shop_id,
        quantity=quantity,
        cart_token=cart_token,
        purpose=purpose,
        status="active",
        expires_at=new_expiry,
    )
    db.add(res)
    db.flush()
    return res


def commit_reservation(db: Session, reservation_id: UUID) -> StockMovement | None:
    """Convert an active reservation to a real stock_movements row.

    Returns the new StockMovement, or None if the reservation was not active
    (already committed, released, or expired — caller can treat as no-op).
    """
    res = db.get(StockReservation, reservation_id)
    if res is None or res.status != "active":
        return None

    res.status = "committed"
    movement = StockMovement(
        tenant_id=res.tenant_id,
        shop_id=res.shop_id,
        product_id=res.product_id,
        quantity_delta=-res.quantity,
        movement_type="sale",
        idempotency_key=f"reservation-{res.id}",
        source_channel_id=res.channel_id,
    )
    db.add(movement)
    db.flush()
    return movement


def release_reservation(db: Session, reservation_id: UUID) -> bool:
    """Mark an active reservation as released. Returns True if changed, False if it was not active."""
    res = db.get(StockReservation, reservation_id)
    if res is None or res.status != "active":
        return False
    res.status = "released"
    db.flush()
    return True


def sweep_expired(db: Session) -> int:
    """Mark all past-expiry active reservations as 'expired'. Returns the count flipped.

    Idempotent and safe to run on any cadence. Subtraction in
    ``available_stock_for_channel`` already filters by status='active' AND
    expires_at > now, so correctness doesn't depend on this sweep — it only
    cleans up stale data so analytics / admin views see fresh state.
    """
    now = datetime.now(UTC)
    result = db.execute(
        update(StockReservation)
        .where(
            StockReservation.status == "active",
            StockReservation.expires_at <= now,
        )
        .values(status="expired", updated_at=now)
    )
    db.flush()
    return result.rowcount or 0
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/reservation_service.py $CONTAINER:/app/app/services/reservation_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_reservation_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/reservation_service.py \
        services/api/tests/services/test_reservation_service.py
git commit -m "feat(reservations): add reservation_service with reserve/commit/release/sweep_expired"
```

---

### Task 3: Subtract active reservations from available stock

**Files:**
- Modify: `services/api/app/services/inventory_pool_service.py`
- Create: `services/api/tests/services/test_available_stock_with_reservations.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_available_stock_with_reservations.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement,
    StockReservation, Tenant,
)


@pytest.fixture()
def channel_with_pool(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
        type="pos",
        name=f"POS at {shop.name}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="USD",
        shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product_with_stock(db, tenant: Tenant, shop: Shop) -> Product:
    """Product with 10 units of stock."""
    p = Product(tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=p.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.flush()
    return p


def _add_reservation(db, *, tenant_id, channel_id, product_id, shop_id, quantity, status, expires_at):
    db.add(StockReservation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        product_id=product_id,
        shop_id=shop_id,
        quantity=quantity,
        cart_token=f"cart-{uuid.uuid4().hex[:8]}",
        purpose="cart",
        status=status,
        expires_at=expires_at,
    ))
    db.flush()


def test_active_reservations_subtract_from_available(db, tenant: Tenant, shop: Shop, channel_with_pool: Channel, product_with_stock: Product) -> None:
    """10 stock - 3 active reservation = 7 available."""
    from app.services.inventory_pool_service import available_stock_for_channel

    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=3, status="active",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    assert available_stock_for_channel(db, channel_with_pool.id, product_with_stock.id) == 7


def test_expired_reservations_dont_subtract(db, tenant: Tenant, shop: Shop, channel_with_pool: Channel, product_with_stock: Product) -> None:
    """A reservation past expires_at no longer holds stock, even if status is still 'active'."""
    from app.services.inventory_pool_service import available_stock_for_channel

    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=3, status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    assert available_stock_for_channel(db, channel_with_pool.id, product_with_stock.id) == 10


def test_committed_or_released_reservations_dont_subtract(db, tenant: Tenant, shop: Shop, channel_with_pool: Channel, product_with_stock: Product) -> None:
    """Only status='active' reservations subtract from available."""
    from app.services.inventory_pool_service import available_stock_for_channel

    future = datetime.now(UTC) + timedelta(minutes=10)
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=2, status="committed", expires_at=future,
    )
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=2, status="released", expires_at=future,
    )
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=2, status="expired", expires_at=future,
    )
    assert available_stock_for_channel(db, channel_with_pool.id, product_with_stock.id) == 10


def test_reservations_summed_across_pool_shops(db, tenant: Tenant) -> None:
    """A multi-shop pool sums reservations across all its shops."""
    from app.services.inventory_pool_service import available_stock_for_channel

    shop_a = Shop(tenant_id=tenant.id, name=f"shop-a-{uuid.uuid4().hex[:6]}")
    shop_b = Shop(tenant_id=tenant.id, name=f"shop-b-{uuid.uuid4().hex[:6]}")
    db.add(shop_a)
    db.add(shop_b)
    db.flush()

    product = Product(tenant_id=tenant.id, name="Gadget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(product)
    db.flush()

    # 5 stock at each shop
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop_a.id, product_id=product.id,
        quantity_delta=5, movement_type="purchase_receipt",
        idempotency_key=f"a-{uuid.uuid4().hex}",
    ))
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop_b.id, product_id=product.id,
        quantity_delta=5, movement_type="purchase_receipt",
        idempotency_key=f"b-{uuid.uuid4().hex}",
    ))
    db.flush()

    pool = InventoryPool(tenant_id=tenant.id, name=f"multi-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop_a.id))
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop_b.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="manual", name=f"multi-channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(channel)
    db.flush()

    future = datetime.now(UTC) + timedelta(minutes=10)
    # 1 reserved at A, 2 reserved at B
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product.id, shop_id=shop_a.id,
        quantity=1, status="active", expires_at=future,
    )
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product.id, shop_id=shop_b.id,
        quantity=2, status="active", expires_at=future,
    )

    # 10 total - 3 reserved = 7
    assert available_stock_for_channel(db, channel.id, product.id) == 7
```

- [ ] **Step 2: Run test to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_available_stock_with_reservations.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL on at least the first test — `available_stock_for_channel` doesn't yet subtract reservations.

- [ ] **Step 3: Modify `available_stock_for_channel` to subtract active reservations**

In `services/api/app/services/inventory_pool_service.py`, replace the existing `available_stock_for_channel` function:

```python
def available_stock_for_channel(
    db: Session,
    channel_id: UUID,
    product_id: UUID,
) -> int:
    """Return the available stock for a product on a channel.

    Sums stock_movements.quantity_delta across all shops in the channel's pool,
    minus the sum of active (non-expired) StockReservation.quantity rows.
    Returns 0 if the channel doesn't exist or has no pool members.
    """
    channel = db.get(Channel, channel_id)
    if channel is None:
        return 0

    shop_ids = pool_shops(db, channel.inventory_pool_id)
    if not shop_ids:
        return 0

    on_hand = db.execute(
        select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
        .where(
            StockMovement.product_id == product_id,
            StockMovement.shop_id.in_(shop_ids),
        )
    ).scalar_one()

    now = datetime.now(UTC)
    held = db.execute(
        select(func.coalesce(func.sum(StockReservation.quantity), 0))
        .where(
            StockReservation.product_id == product_id,
            StockReservation.shop_id.in_(shop_ids),
            StockReservation.status == "active",
            StockReservation.expires_at > now,
        )
    ).scalar_one()

    return int((on_hand or 0) - (held or 0))
```

Add the new imports at the top of the file:

```python
from datetime import UTC, datetime
```

And update the model import to include `StockReservation`:

```python
from app.models import Channel, InventoryPool, InventoryPoolShop, StockMovement, StockReservation
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/inventory_pool_service.py $CONTAINER:/app/app/services/inventory_pool_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_available_stock_with_reservations.py tests/services/test_inventory_pool_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: all 4 new + 5 existing = 9 passed. (The pre-existing tests still pass because they have no reservations.)

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/inventory_pool_service.py \
        services/api/tests/services/test_available_stock_with_reservations.py
git commit -m "feat(reservations): subtract active reservations from available_stock_for_channel"
```

---

### Task 4: Worker task — periodic sweeper

**Files:**
- Modify: `services/api/app/worker/tasks.py`
- Create: `services/api/tests/worker/test_sweep_reservations_task.py`

- [ ] **Step 1: Write the failing test**

If `services/api/tests/worker/__init__.py` doesn't exist, create it as empty.

Create `services/api/tests/worker/test_sweep_reservations_task.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="pos", name=f"POS at {shop.name}", config={},
        inventory_pool_id=pool.id, currency_code="USD", shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    return p


def test_sweep_task_marks_expired_reservations(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    """Calling the worker task wrapper has the same effect as calling sweep_expired directly."""
    expired = StockReservation(
        tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_old", purpose="cart",
        status="active", expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(expired)
    db.commit()

    from app.worker.tasks import sweep_expired_reservations

    result = sweep_expired_reservations()
    assert "swept" in result.lower()

    db.refresh(expired)
    assert expired.status == "expired"


def test_sweep_task_runs_clean_with_no_expired(db, tenant: Tenant) -> None:
    """No expired rows → task returns 0 cleanly."""
    from app.worker.tasks import sweep_expired_reservations
    result = sweep_expired_reservations()
    assert "0" in result or "swept" in result.lower()
```

- [ ] **Step 2: Run test to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
mkdir -p services/api/tests/worker && touch services/api/tests/worker/__init__.py 2>/dev/null || true
docker cp services/api/tests/worker $CONTAINER:/app/tests/worker
docker compose exec api python -m pytest tests/worker/test_sweep_reservations_task.py -v
docker compose exec api rm -rf /app/tests/worker
```
Expected: FAIL — `ImportError: cannot import name 'sweep_expired_reservations' from 'app.worker.tasks'`

- [ ] **Step 3: Add the task callable**

Append to `services/api/app/worker/tasks.py`:

```python
def sweep_expired_reservations() -> str:
    """Scheduled job: mark all past-expiry active reservations as 'expired'.

    Safe to call on any cadence. Recommended schedule: every 1-5 minutes via cron
    or rq-scheduler. Operators can also enqueue it on demand via the admin
    endpoint POST /v1/admin/reservations/sweep-expired (Task 5).
    """
    import logging

    from app.db.session import SessionLocal
    from app.services.reservation_service import sweep_expired

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        count = sweep_expired(db)
        db.commit()
        logger.info("Reservation sweep complete: %d expired", count)
        return f"swept {count} reservations"
    except Exception:
        logger.exception("Reservation sweep failed")
        return "error"
    finally:
        db.close()
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/worker/tasks.py $CONTAINER:/app/app/worker/tasks.py
docker cp services/api/tests/worker $CONTAINER:/app/tests/worker
docker compose exec api python -m pytest tests/worker/test_sweep_reservations_task.py -v
docker compose exec api rm -rf /app/tests/worker
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/worker/tasks.py \
        services/api/tests/worker/__init__.py \
        services/api/tests/worker/test_sweep_reservations_task.py
git commit -m "feat(reservations): worker task sweep_expired_reservations"
```

---

### Task 5: Admin endpoints — list + manual release + manual sweep

**Files:**
- Create: `services/api/app/routers/admin_reservations.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_reservations.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_reservations.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent — see same comment
# in test_entitlements_dep.py (PEP 563 + FastAPI inline-route type hints).

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="pos", name=f"POS at {shop.name}", config={},
        inventory_pool_id=pool.id, currency_code="USD", shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(tenant_id=tenant.id, name="W", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"reservations:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def _seed_reservation(db, *, tenant_id, channel_id, product_id, shop_id, status="active") -> StockReservation:
    res = StockReservation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        product_id=product_id,
        shop_id=shop_id,
        quantity=1,
        cart_token=f"cart-{uuid.uuid4().hex[:8]}",
        purpose="cart",
        status=status,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(res)
    db.flush()
    return res


def test_list_reservations(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id)
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="released")
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/reservations", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2


def test_filter_by_status(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="active")
    _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="expired")
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/reservations?status=expired", headers=auth_headers)
    assert resp.status_code == 200
    statuses = {r["status"] for r in resp.json()}
    assert statuses == {"expired"}


def test_manual_release(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    res = _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/reservations/{res.id}/release", headers=auth_headers)
    assert resp.status_code == 204

    db.refresh(res)
    assert res.status == "released"


def test_release_already_released_returns_409(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    res = _seed_reservation(db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id, shop_id=shop.id, status="released")
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/reservations/{res.id}/release", headers=auth_headers)
    assert resp.status_code == 409
    assert "active" in resp.json()["detail"].lower()


def test_manual_sweep_expired(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    """POST /sweep-expired triggers the sweep and returns the count."""
    res = StockReservation(
        tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_old", purpose="cart",
        status="active", expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(res)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/reservations/sweep-expired", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["expired_count"] == 1


def test_cross_tenant_release_blocked(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product, auth_headers) -> None:
    """Release attempt for a reservation belonging to a different tenant returns 404."""
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_shop = Shop(tenant_id=other.id, name="other-shop")
    db.add(other_shop)
    db.flush()
    pool = InventoryPool(tenant_id=other.id, name="other-pool")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=other.id, pool_id=pool.id, shop_id=other_shop.id))
    db.flush()
    other_ch = Channel(
        tenant_id=other.id, type="pos", name="other-pos", config={},
        inventory_pool_id=pool.id, currency_code="USD", shop_id=other_shop.id,
    )
    db.add(other_ch)
    db.flush()
    other_prod = Product(tenant_id=other.id, name="P", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=100)
    db.add(other_prod)
    db.flush()
    other_res = _seed_reservation(
        db, tenant_id=other.id, channel_id=other_ch.id,
        product_id=other_prod.id, shop_id=other_shop.id,
    )
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/reservations/{other_res.id}/release", headers=auth_headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_reservations.py $CONTAINER:/app/tests/routers/test_admin_reservations.py
docker compose exec api python -m pytest tests/routers/test_admin_reservations.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_reservations.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_reservations'`

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_reservations.py`:

```python
"""Admin endpoints for stock reservation visibility + manual ops.

This is primarily a debug/support tool — normal reservation lifecycle (reserve
on cart-add, commit on order, release on cart-clear, expire via sweeper) runs
without admin intervention. These endpoints exist for ops to inspect in-flight
holds and force-release a stuck reservation.

Auth: requires `reservations:manage` permission. Granted to the system `owner`
role by migration 20260508000001.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import StockReservation
from app.services.reservation_service import release_reservation, sweep_expired

router = APIRouter(
    prefix="/v1/admin/reservations",
    tags=["Admin Reservations"],
    dependencies=[require_permission("reservations:manage")],
)


_ALLOWED_STATUSES = {"active", "committed", "released", "expired"}


class StockReservationOut(BaseModel):
    id: UUID
    tenant_id: UUID
    channel_id: UUID
    product_id: UUID
    shop_id: UUID
    quantity: int
    cart_token: str
    purpose: str
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SweepResponse(BaseModel):
    expired_count: int


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


@router.get("", response_model=list[StockReservationOut])
def list_reservations(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[StockReservation]:
    """List reservations for the operator's tenant.

    The query param is named ``status`` in the URL (via Query alias) but kept as
    ``status_filter`` in the function signature to avoid shadowing FastAPI's
    ``status`` HTTP-status module imported above.
    """
    tenant_id = _require_tenant(ctx)
    q = select(StockReservation).where(StockReservation.tenant_id == tenant_id)
    if status_filter:
        if status_filter not in _ALLOWED_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown status: {status_filter}. Allowed: {sorted(_ALLOWED_STATUSES)}",
            )
        q = q.where(StockReservation.status == status_filter)
    q = q.order_by(StockReservation.created_at.desc())
    return list(db.execute(q).scalars().all())


@router.post("/{reservation_id}/release", status_code=status.HTTP_204_NO_CONTENT)
def release(
    reservation_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    res = db.get(StockReservation, reservation_id)
    if res is None or res.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found",
        )
    if res.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot release a reservation with status={res.status!r}; only 'active' reservations can be released",
        )
    release_reservation(db, res.id)
    db.commit()


@router.post("/sweep-expired", response_model=SweepResponse)
def sweep(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SweepResponse:
    """Trigger an immediate sweep of all expired reservations across the tenant.

    Normally runs on a schedule via the worker task; this endpoint is for ops
    troubleshooting and end-to-end tests.
    """
    _require_tenant(ctx)
    count = sweep_expired(db)
    db.commit()
    return SweepResponse(expired_count=count)
```

- [ ] **Step 4: Mount the router**

In `services/api/app/main.py`, add `admin_reservations` to the imports list (alphabetical) and add `app.include_router(admin_reservations.router)` to the include block.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_reservations.py $CONTAINER:/app/app/routers/admin_reservations.py
docker cp services/api/app/services $CONTAINER:/app/app/services
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_reservations.py tests/test_admin_console_contracts.py::test_stock_reservation_out_schema -v
docker compose exec api rm -rf /app/tests
```
Expected: 6 router tests + 1 contract test = 7 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_reservations.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_reservations.py
git commit -m "feat(reservations): admin endpoints for list/release/sweep-expired"
```

---

### Task 6: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_reservations_e2e.py`

This task does not add product code — only an integration test exercising the full reservation lifecycle.

- [ ] **Step 1: Write the integration test**

Create `services/api/tests/integration/test_reservations_e2e.py`:

```python
"""End-to-end smoke test for the stock reservation engine.

Covers:
- Reserve → available stock drops by reserved quantity
- Commit → reservation flips to 'committed', stock_movement created with
  source_channel_id, available stock unchanged from commit (because the
  reservation no longer subtracts AND a new movement decremented stock)
- Release → reservation flips to 'released', available stock recovers
- Expire path: past-expires_at active reservation is excluded from
  available_stock immediately; sweep_expired flips its status
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement,
    StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="manual", name=f"E2E channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD", shop_id=None,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product_with_10_stock(db, tenant: Tenant, shop: Shop) -> Product:
    p = Product(tenant_id=tenant.id, name="E2E Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=p.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.flush()
    return p


def test_full_lifecycle_reserve_commit(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """Reserve 3 → available=7. Commit → status='committed', movement created, available=7 (10 stock - 3 sold)."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import commit_reservation, reserve

    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 10

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=3, cart_token="cart_lifecycle_commit",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 7

    movement = commit_reservation(db, res.id)
    db.flush()
    assert movement is not None
    assert movement.quantity_delta == -3
    assert movement.source_channel_id == channel.id

    db.refresh(res)
    assert res.status == "committed"
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 7


def test_full_lifecycle_reserve_release(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """Reserve → available drops, release → recovers."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import release_reservation, reserve

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=4, cart_token="cart_lifecycle_release",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 6

    release_reservation(db, res.id)
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 10


def test_full_lifecycle_reserve_expire(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """An active reservation past expires_at no longer holds stock; sweep_expired flips status."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import sweep_expired

    expired = StockReservation(
        tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=2, cart_token="cart_lifecycle_expire",
        purpose="cart", status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(expired)
    db.flush()

    # Even before the sweep, available stock ignores expired-by-time reservations
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 10

    count = sweep_expired(db)
    assert count == 1

    db.refresh(expired)
    assert expired.status == "expired"


def test_idempotent_reserve_updates_quantity(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """Re-reserving the same (channel, cart_token, product, shop) updates quantity, doesn't create a new row."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import reserve

    reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=2, cart_token="cart_idem_e2e",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 8

    reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=5, cart_token="cart_idem_e2e",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 5
```

- [ ] **Step 2: Run the integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_reservations_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 3: Run the full reservation suite as final sanity check**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_reservation_service.py \
  tests/services/test_available_stock_with_reservations.py \
  tests/worker/test_sweep_reservations_task.py \
  tests/routers/test_admin_reservations.py \
  tests/integration/test_reservations_e2e.py \
  tests/test_admin_console_contracts.py::test_stock_reservation_out_schema \
  -v 2>&1 | tail -10
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~28 tests passing across all layers.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_reservations_e2e.py
git commit -m "test(reservations): end-to-end smoke test for reserve/commit/release/expire"
```

---

## Done. Summary of what shipped

- New table `stock_reservations` with `(channel_id, cart_token, product_id, shop_id)` unique constraint, RLS, and 3 indexes (tenant lookup, active-stock lookup, expiry sweep)
- New permission `reservations:manage` granted to system `owner` role
- `app/services/reservation_service.py` — `reserve()`, `commit_reservation()`, `release_reservation()`, `sweep_expired()`
- `app/services/inventory_pool_service.py::available_stock_for_channel` — extended to subtract active non-expired reservations (the TODO from the channels sub-project)
- `app/worker/tasks.py::sweep_expired_reservations` — schedulable RQ task
- `app/routers/admin_reservations.py` — list (with status filter), manual release, manual sweep-expired
- ~28 tests across services, worker, router, and integration layers

## What this unlocks

- **Phase 1 connectors** (Shopify, WooCommerce, headless) can call `reserve()` on cart events from the channel and have shopper races handled
- **Hosted checkout** can soft-hold stock for the duration of the payment flow with `purpose="payment_pending"` (24h default TTL)
- **Order ingest** (when it lands in a future plan) can call `commit_reservation()` to atomically convert a hold into a stock movement
- **Available stock** queries are now reservation-aware everywhere — every consumer of `available_stock_for_channel` automatically gets the corrected number

## Follow-up work (not in this plan)

- **Variant support** — `variant_id` column on `stock_reservations`. Add when a separate `Variant` table ships.
- **RQ scheduler integration** — the worker task is shipped; production scheduling (cron / rq-scheduler) is operator-configurable.
- **High-contention atomicity** — for hot products under heavy concurrent reservation load, consider `SELECT FOR UPDATE` on the unique-constraint row or a Postgres advisory lock per (product, shop) pair. Not needed for current scale.

---

*End of plan.*
